"""Transactional outbox repository.

Architecture v1.1 §1.6. The outbox exists because **a PostgreSQL transaction and
a Cloud Tasks task creation are not atomic.** Writing the job and then creating
the task means a crash in between loses the work silently; creating the task and
then writing the job means a crash leaves a task referencing a job that does not
exist.

The outbox resolves this by making the *intent to dispatch* part of the same
transaction as the job. A separate dispatcher then moves intents to Cloud Tasks,
and because the intent is durable, a crash at any point is recoverable:

* Crash before commit — nothing happened; the client's command was never accepted.
* Crash after commit, before dispatch — the outbox row is ``pending`` and the
  next dispatcher poll picks it up.
* Crash while dispatching — the lease expires and another dispatcher retries.
  The task name is deterministic, so if the task *was* created before the crash,
  Cloud Tasks rejects the duplicate rather than running the work twice.

Claiming uses ``FOR UPDATE SKIP LOCKED``, so several dispatcher instances can
run concurrently without coordinating and without any row being claimed twice.

Concurrency needs one thing beyond that, because a lease can expire while the
dispatcher holding it is merely slow rather than dead: each claim mints a
``lease_token`` onto the row, and the two writers that finish a row require it
back. That is what lets them prove *this caller* holds the row rather than that
*someone* does — see :func:`_held_by`, which is where the reasoning lives,
including what a ``NULL`` token means and the rollout constraint that comes with
it.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "DEFAULT_LEASE",
    "MAX_DISPATCH_ATTEMPTS",
    "ClaimedOutboxRecord",
    "OutboxRepository",
    "OutboxStatus",
    "ReclaimedOutboxRecord",
    "backoff_for",
    "derive_task_name",
]

#: How long a dispatcher may hold a claimed row before another may take it.
#: Long enough to cover a slow Cloud Tasks call, short enough that a crashed
#: dispatcher's work resumes promptly.
DEFAULT_LEASE: Final[timedelta] = timedelta(seconds=60)

#: Dispatch attempts before a row is parked as ``failed`` for human attention.
#: Dispatch failures are almost always systemic (bad queue configuration, denied
#: credentials), so retrying forever floods the logs without ever succeeding.
MAX_DISPATCH_ATTEMPTS: Final[int] = 5

#: What :meth:`OutboxRepository.reclaim_stranded` writes over the row's
#: ``last_error``.
#:
#: The text is load-bearing, not decoration. A stranded row still carries the
#: error from the attempt *before* the one that stranded it, so an operator
#: reading it would conclude the queue rejected the dispatch — when in fact
#: nothing recorded the final attempt at all, and the queue may well have
#: accepted it. Saying which of those happened is the difference between
#: "investigate the queue" and "check whether a dispatcher died".
_STRANDED_ERROR: Final[str] = (
    "dispatch attempts exhausted; the final attempt recorded no outcome — the "
    "dispatcher process ended, or its write failed — so the row was reclaimed "
    "rather than retried. Any earlier error text on this row belonged to an "
    "earlier attempt and has been replaced. The task may or may not exist in "
    "the queue — nothing here can tell. A re-drive is safe either way, but not "
    "because of the task name: a re-drive derives a *new* name by generation "
    "(ADR-0007), precisely so it does not dedupe against a possibly-live task "
    "from this attempt. What makes it safe is that this job is now "
    "'failed_provider', and JobRepository.claim moves only a 'dispatched' job — "
    "so if the original task is still live and delivers, it claims nothing and "
    "executes nothing."
)

#: Ceiling on the exponential retry backoff, in seconds. Without a cap the last
#: attempts would wait far longer than an operator would tolerate for work that
#: is merely waiting on a recovered dependency.
_MAX_BACKOFF_SECONDS: Final[float] = 300.0


class OutboxStatus(StrEnum):
    """Lifecycle of one outbox row."""

    #: Committed with its job, not yet claimed.
    PENDING = "pending"
    #: Claimed by a dispatcher; the lease is running.
    LEASED = "leased"
    #: The task exists in Cloud Tasks. Terminal.
    DISPATCHED = "dispatched"
    #: Attempts exhausted. Needs a human. Terminal without intervention.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ClaimedOutboxRecord:
    """An outbox row claimed by a dispatcher, with its lease running.

    ``lease_token`` is what makes this record a *claim* rather than a copy of the
    row. It is minted by :meth:`OutboxRepository.claim_batch`, one value per row
    per claim, and both writers require it back — so the token is the caller's
    only proof that the row it is finishing is still the row it took. Losing the
    record loses the right to write to the row, which is the intended shape: the
    lease may have expired and a peer may hold it now.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    job_id: uuid.UUID
    task_name: str
    dispatch_attempts: int
    lease_expires_at: datetime
    lease_token: uuid.UUID


@dataclass(frozen=True, slots=True)
class ReclaimedOutboxRecord:
    """An outbox row that was written off because nothing ever finished it.

    Deliberately **not** a :class:`ClaimedOutboxRecord`. That type means "claimed
    by a dispatcher, with its lease running", and a reclaimed row is the exact
    opposite: its lease has been cleared and no dispatcher will touch it again.
    Reusing it would have put a ``None`` in a field typed ``datetime`` and given
    two opposite states one name.

    Carries only what the caller needs to finish the job side of the reclaim.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    job_id: uuid.UUID
    task_name: str
    dispatch_attempts: int


def _claimable_predicate(now: datetime) -> sa.ColumnElement[bool]:
    """The single definition of "this row still needs dispatching".

    Used by both the claim query and the lag metric, so a row can never be
    claimable but uncounted, or counted but unclaimable. When these drifted
    apart, the lag metric reported a stuck row that no dispatcher would ever
    pick up.

    A row qualifies when it is ``pending``, or ``leased`` with an expired lease
    (the crashed-dispatcher recovery path), and has attempts remaining.
    """
    return sa.and_(
        sa.or_(
            schema.outbox_record.c.status == OutboxStatus.PENDING.value,
            sa.and_(
                schema.outbox_record.c.status == OutboxStatus.LEASED.value,
                schema.outbox_record.c.lease_expires_at < now,
            ),
        ),
        schema.outbox_record.c.dispatch_attempts < MAX_DISPATCH_ATTEMPTS,
    )


def _stranded_predicate(now: datetime) -> sa.ColumnElement[bool]:
    """The single definition of "this row is finished with and nobody said so".

    Deliberately adjacent to :func:`_claimable_predicate`, because the two are
    only correct read together. That one says which rows a dispatcher may still
    pick up; this one says which rows it never will. Between them they must
    account for every ``leased`` row, or work goes missing in the gap — which is
    exactly what happened before this existed.

    A row qualifies when its lease has expired *and* its attempts are spent.
    Both halves matter:

    * **The expired lease** is what makes this safe. A row whose lease is still
      running may have a live dispatcher mid-enqueue behind it, and parking that
      row would produce the failed-job-beside-a-live-row state
      ``_record_failure`` shares a transaction to prevent. It is the same guard
      the ordinary recovery path already relies on.
    * **The exhausted attempts** are what make it necessary rather than
      duplicative. With attempts remaining, an expired lease is already handled:
      :func:`_claimable_predicate` matches the row and a dispatcher retries it.
      At ``MAX_DISPATCH_ATTEMPTS`` that stops, because the claim requires
      strictly fewer — and nothing else was looking.

    **NULL is not "expired".** A ``leased`` row carrying no lease at all fails
    the ``<`` comparison and is skipped, so this never touches it. ADR-0005's
    invariant says such a row cannot exist; if one ever does, its state is not
    understood, and writing off work nothing can explain is worse than leaving it
    to be found. That is a deliberate choice, not an accident of SQL's NULL
    semantics, and :func:`test_a_leased_row_with_no_lease_is_left_alone` holds it
    in place.
    """
    return sa.and_(
        schema.outbox_record.c.status == OutboxStatus.LEASED.value,
        schema.outbox_record.c.lease_expires_at < now,
        schema.outbox_record.c.dispatch_attempts >= MAX_DISPATCH_ATTEMPTS,
    )


def _held_by(record_id: uuid.UUID, lease_token: uuid.UUID) -> sa.ColumnElement[bool]:
    """The single definition of "*this* caller still holds this row" (J17).

    Shared by :meth:`OutboxRepository.mark_dispatched` and
    :meth:`OutboxRepository.mark_failed` for the reason
    :func:`_claimable_predicate` is shared: two writers that must agree about
    who owns a row will eventually disagree if each spells it out itself.

    Both halves are required, and the ``status`` half is **not** made redundant
    by the token:

    * ``status = 'leased'`` is a *liveness* test. It is what keeps a late writer
      off a row :meth:`reclaim_stranded` has already written off, which is a
      ``failed`` row still carrying no token at all.
    * ``lease_token = :token`` is the *ownership* test J17 adds. ``leased`` alone
      is satisfied by a **peer's** claim as readily as by this caller's, so a
      dispatcher whose lease expired mid-enqueue could overwrite the peer's
      fresh lease with its own older attempt count's much shorter backoff — 56
      seconds cut off a 60-second lease in the measurement J17 records — and
      replace the peer's ``last_error``. The row then became claimable while the
      peer was still working it, burning an attempt it should not have spent.

    ## What a ``NULL`` token means here, and what it deliberately does not

    **A ``NULL`` token is not "no dispatcher holds this row".** It is tempting to
    read it that way and it is false: a dispatcher running pre-J17 code claims
    rows against this schema without writing a token and *actively holds* them.
    So ``NULL`` means "held by someone this code cannot identify", and the safe
    move is to refuse the write.

    That is what this predicate does, by construction rather than by a special
    case: ``lease_token = :token`` is ``NULL`` — never true — when the column is
    ``NULL``, so a tokenless row matches nothing and the caller takes the
    ordinary lost-the-race path and reads the row back. No ``IS NOT DISTINCT
    FROM`` and no ``OR lease_token IS NULL``: either would hand the row to
    whichever writer arrived, which is precisely the defect.

    Refusing costs this code nothing, because a caller on this code always has a
    token — :meth:`claim_batch` mints one in the same UPDATE that takes the
    lease, so there is no path to a ``ClaimedOutboxRecord`` without one. The only
    rows carrying ``leased`` with a ``NULL`` token are rows an old dispatcher
    holds, and leaving those alone is the correct answer.

    **The rollout constraint, because the token alone does not close J17.** The
    residual exposure runs the other way and no change here can reach it: the old
    dispatcher's own ``mark_dispatched``/``mark_failed`` still guard on
    ``status = 'leased'`` alone, so it can overwrite a *new* dispatcher's
    tokenized lease exactly as J17 describes. **J17's ownership guarantee holds
    only once every dispatcher runs this code.** The column makes the fix
    possible; draining the old dispatchers is what makes it true. Recorded in
    migration ``0004``'s docstring, which is where the expand-phase reasoning for
    the column lives.
    """
    return sa.and_(
        schema.outbox_record.c.id == record_id,
        schema.outbox_record.c.status == OutboxStatus.LEASED.value,
        schema.outbox_record.c.lease_token == lease_token,
    )


def backoff_for(attempts: int) -> timedelta:
    """Return how long to wait before retrying after ``attempts`` failures.

    Exponential — ``2 ** attempts`` seconds — capped at
    :data:`_MAX_BACKOFF_SECONDS`. Exponential rather than fixed so a persistent
    outage is not hammered, and capped so the last attempts do not wait longer
    than an operator would tolerate for work merely awaiting a recovered
    dependency.
    """
    return timedelta(seconds=min(2.0**attempts, _MAX_BACKOFF_SECONDS))


def derive_task_name(job_id: uuid.UUID, command_type: str, *, redrive_generation: int = 0) -> str:
    """Derive a deterministic Cloud Tasks task name for one dispatch generation.

    Determinism is the dedupe mechanism: Cloud Tasks rejects a task whose name
    already exists, so a retried dispatch after an ambiguous failure cannot
    enqueue the work a second time. A random name would silently double-execute
    in exactly the case retries exist to handle.

    The name is a hash rather than the raw job id so it carries no tenant or
    command information into the queue's metadata, which is visible in Cloud
    Console to anyone with queue-viewer access.

    ## Why a generation, and why it does not cost determinism

    ADR-0007 records the consequence that bites: because the name was a pure
    function of ``(job_id, command_type)``, a job **re-driven under its original
    identifiers derived the name its own failed attempt already used**. That
    fails twice over. ``uq_outbox_task_name`` is global, so PostgreSQL refuses
    the second outbox row before the queue is ever consulted; and past the
    database the queue rejects the duplicate, which the dispatcher counts as
    *success* — marking the row ``dispatched`` and advancing the job while the
    work never runs. An audit trail saying the job was re-driven, and nothing
    executed, is the worst outcome available here.

    ``redrive_generation`` separates the two kinds of repeat:

    * An **accidental** repeat — the dispatcher retrying one dispatch after an
      ambiguous enqueue — stays inside a single generation. The name is
      identical, the queue rejects the duplicate, and ADR-0007's guarantee is
      untouched. Nothing in the dispatch path chooses a generation: the name is
      computed once by :meth:`OutboxRepository.enqueue` and *stored* in
      ``outbox_record.task_name``, and every retry reads that stored value. The
      dispatcher never calls this function at all.
    * A **deliberate** repeat — an authorized, audited re-drive — is a new
      generation, so it derives a different name and is genuinely new work.

    So determinism is preserved exactly where it is load-bearing (within one
    attempt) and broken only where it was actively harmful (across attempts a
    human explicitly asked for). ADR-0007 anticipates precisely this shape:
    "any input that varies between attempts of the same dispatch destroys the
    property"; the generation varies between *dispatches*, never within one.

    Generation ``0`` — the original attempt — derives byte-identically to the
    pre-re-drive formula. The change is additive: no name any existing row or
    queue entry carries shifts underneath it.

    Args:
        redrive_generation: How many times this job has already been enqueued.
            ``0`` is the first attempt.

    Raises:
        ValueError: on a negative generation, which is a caller bug that would
            otherwise silently derive a plausible-looking name.
    """
    if redrive_generation < 0:
        raise ValueError(f"redrive_generation must not be negative, got {redrive_generation}")

    suffix = "" if redrive_generation == 0 else f"|r{redrive_generation}"
    digest = hashlib.sha256(f"{job_id}|{command_type}{suffix}".encode()).hexdigest()[:40]
    return f"sm-{digest}"


class OutboxRepository:
    """Reads and writes outbox rows.

    Like :class:`~smartmatch_persistence.jobs.JobRepository`, this takes a
    session per call: ``enqueue`` must join the caller's transaction, since the
    whole point is that the outbox row and the job row commit together.
    """

    def enqueue(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        command_type: str,
        redrive_generation: int = 0,
    ) -> str:
        """Record the intent to dispatch a job. Does not commit.

        Must be called inside the same transaction that inserted the job. The
        caller commits both at once; there is no valid state in which a job
        exists without its outbox row.

        Args:
            redrive_generation: Which dispatch of this job this row represents.
                ``0`` is the original submission, which is why every caller on
                the command path can ignore it. Re-drive passes the next
                generation so the derived task name differs from the failed
                attempt's — see :func:`derive_task_name` for why that is
                necessary and why it does not weaken retry determinism.

        Returns:
            The deterministic task name that will be used for this dispatch.
            It is stored on the row, and the dispatcher reads it from there
            rather than recomputing it, so a retry can never derive a different
            name than the attempt it is retrying.
        """
        task_name = derive_task_name(job_id, command_type, redrive_generation=redrive_generation)

        session.execute(
            sa.insert(schema.outbox_record).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                job_id=job_id,
                task_name=task_name,
                status=OutboxStatus.PENDING.value,
                dispatch_attempts=0,
            )
        )
        return task_name

    def claim_batch(
        self,
        session: Session,
        *,
        limit: int = 20,
        lease: timedelta = DEFAULT_LEASE,
        now: datetime | None = None,
    ) -> list[ClaimedOutboxRecord]:
        """Claim up to ``limit`` dispatchable rows, taking a lease on each.

        A row is claimable when it is ``pending``, or ``leased`` with an expired
        lease — the latter being how a crashed dispatcher's work is recovered
        without any liveness detection.

        ``FOR UPDATE SKIP LOCKED`` lets concurrent dispatchers claim disjoint
        batches: each skips rows another has locked instead of blocking on them.
        Without ``SKIP LOCKED`` a second dispatcher would serialize behind the
        first and add no throughput.

        The selection is a **CTE**, not an ``IN (SELECT ... LIMIT n)`` subquery.
        That is not a style preference. PostgreSQL cannot hash a subplan
        containing ``FOR UPDATE``, so it may re-execute the subquery while
        evaluating the ``IN``, and each execution returns a fresh batch of up to
        ``limit`` rows — the update then touches far more rows than requested.
        Materializing the selection once in a CTE is the standard SKIP LOCKED
        queue pattern and bounds the batch as intended.

        ## Why the result is re-sorted in Python

        The CTE's ``ORDER BY created_at`` chooses *which* rows are claimed under
        ``LIMIT``. It does not decide the order they come back in: the rows are
        returned by ``UPDATE ... RETURNING``, and **SQL does not define
        ``RETURNING``'s output order**. In practice PostgreSQL plans this as a
        hash join whose outer side is a sequential scan of ``outbox_record``, so
        the rows arrive in *heap* order — which diverges from ``created_at``
        order as soon as an update rewrites an older row's tuple behind a newer
        one, exactly what a busy outbox does. A claim of the twenty oldest rows
        would then be handed to the dispatcher as an arbitrary permutation.

        Nothing about dispatch correctness depends on the order — each row is
        independent, and a wrong order costs latency on the oldest row, not
        safety. But FIFO is what this method's contract says, what the lag metric
        in :meth:`oldest_pending_age` measures against, and what ADR-0005 assumes
        when it talks about the oldest row. Sorting here makes the documented
        guarantee real rather than incidental, at the cost of ordering at most
        ``limit`` records.

        ``id`` breaks ``created_at`` ties so the order is total: two rows
        committed inside the same transaction share a ``now()``, and without the
        tiebreak their relative order would still be whatever the heap decided.

        ## Why the claim mints a token (J17)

        Taking the lease and recording *who* took it are the same write, because
        a row that is ``leased`` without saying by whom is the state J17 is
        about: both writers could then prove only that someone held the row, and
        a dispatcher whose lease had expired would win against the peer that
        legitimately re-claimed it. The token is minted here, returned on the
        :class:`ClaimedOutboxRecord`, and required back by
        :meth:`mark_dispatched` and :meth:`mark_failed` — see :func:`_held_by`,
        including what a ``NULL`` token means and the rollout constraint that
        comes with it.

        ``gen_random_uuid()`` rather than :func:`uuid.uuid4` — the one place this
        module generates an identifier in SQL rather than in Python — because the
        claim is a single set-based ``UPDATE`` over a batch, so a Python value
        would be one token shared by every row it touched. PostgreSQL evaluates
        the function once per row, which is what ``0004`` specifies ("writes a
        fresh one per row") and what makes the token mean *this claim of this
        row* rather than *this pass*. Stated honestly: a batch-wide token would
        also be sound today, because :func:`_held_by` pins the row id as well —
        per-row is the stronger of two working options, not the only one that
        works, and it is the one an operator reading the column can interpret
        without knowing how batches were cut. ``gen_random_uuid()`` is core since
        PostgreSQL 13 and needs no extension.

        Args:
            now: Injected for tests so lease expiry is exercised without waiting.

        Returns:
            The claimed rows, at most ``limit`` of them, oldest first. Does not
            commit — the caller commits to make the lease visible, then
            dispatches.
        """
        now = now or datetime.now(UTC)
        deadline = now + lease

        claimable = (
            sa.select(schema.outbox_record.c.id)
            .where(_claimable_predicate(now))
            .order_by(schema.outbox_record.c.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .cte("claimable")
        )

        rows = session.execute(
            sa.update(schema.outbox_record)
            .where(schema.outbox_record.c.id == claimable.c.id)
            .values(
                status=OutboxStatus.LEASED.value,
                lease_expires_at=deadline,
                # Minted in the same write that takes the lease, never a step
                # later: a row that is `leased` without saying by whom is the
                # window J17 exists to close.
                lease_token=sa.func.gen_random_uuid(),
                dispatch_attempts=schema.outbox_record.c.dispatch_attempts + 1,
            )
            .returning(
                schema.outbox_record.c.id,
                schema.outbox_record.c.tenant_id,
                schema.outbox_record.c.job_id,
                schema.outbox_record.c.task_name,
                schema.outbox_record.c.dispatch_attempts,
                schema.outbox_record.c.lease_expires_at,
                schema.outbox_record.c.lease_token,
                schema.outbox_record.c.created_at,
            )
        ).all()

        ordered = sorted(rows, key=lambda row: (row.created_at, row.id))

        return [
            ClaimedOutboxRecord(
                id=row.id,
                tenant_id=row.tenant_id,
                job_id=row.job_id,
                task_name=row.task_name,
                dispatch_attempts=row.dispatch_attempts,
                lease_expires_at=row.lease_expires_at,
                lease_token=row.lease_token,
            )
            for row in ordered
        ]

    def reclaim_stranded(
        self,
        session: Session,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[ReclaimedOutboxRecord]:
        """Write off rows that exhausted their attempts without recording one.

        The recovery path for the state :func:`_stranded_predicate` describes: a
        row left ``leased`` with its attempts spent, which
        :meth:`claim_batch` will never pick up again and
        :meth:`pending_count` will never count. Reached whenever a dispatcher
        stops between the claim's commit and the outcome write on the *final*
        attempt — a killed process, an evicted pod, a drained node, or a
        failure-write that itself failed. Before this existed the row stayed
        there permanently, its job stuck ``queued``, with no symptom anywhere.

        Marks the row ``failed`` and clears the lease — and with it the lease
        token, which goes wherever the lease goes — which is precisely what
        :meth:`mark_failed` does at exhaustion — the same terminal state, reached
        by the row that never got there. ``last_error`` is overwritten with
        :data:`_STRANDED_ERROR` rather than left alone; see that constant for why
        keeping the previous attempt's text would actively mislead.

        Uses the same CTE + ``FOR UPDATE SKIP LOCKED`` shape as
        :meth:`claim_batch`, for the reason ADR-0005 gives there and which
        applies identically here: PostgreSQL cannot hash a subplan containing
        ``FOR UPDATE``, so an ``IN (SELECT ... LIMIT n)`` may re-execute and
        update far more rows than asked. ``SKIP LOCKED`` also makes concurrent
        reclaims safe by construction — two dispatchers sweeping at once take
        disjoint sets rather than fighting over one.

        Results are sorted oldest-first for the same reason
        :meth:`claim_batch`'s are: ``UPDATE ... RETURNING`` has no defined output
        order, and the caller writes one job transition per row.

        **Does not touch the job.** The row and its job must move together, and
        the caller owns that transaction — see
        ``OutboxDispatcher.reclaim_stranded``.

        Args:
            now: Injected for tests so lease expiry is exercised without waiting.

        Returns:
            The rows written off, at most ``limit`` of them, oldest first. Does
            not commit.
        """
        now = now or datetime.now(UTC)

        stranded = (
            sa.select(schema.outbox_record.c.id)
            .where(_stranded_predicate(now))
            .order_by(schema.outbox_record.c.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .cte("stranded")
        )

        rows = session.execute(
            sa.update(schema.outbox_record)
            .where(schema.outbox_record.c.id == stranded.c.id)
            .values(
                status=OutboxStatus.FAILED.value,
                lease_expires_at=None,
                # The token goes with the lease, always. A terminal row nobody
                # holds must not keep a token that would let a late writer
                # satisfy `_held_by` — the status check already refuses it, and
                # leaving a token behind would make the row read as though a
                # dispatcher were still on it.
                lease_token=None,
                last_error=_STRANDED_ERROR[:2000],
            )
            .returning(
                schema.outbox_record.c.id,
                schema.outbox_record.c.tenant_id,
                schema.outbox_record.c.job_id,
                schema.outbox_record.c.task_name,
                schema.outbox_record.c.dispatch_attempts,
                schema.outbox_record.c.created_at,
            )
        ).all()

        ordered = sorted(rows, key=lambda row: (row.created_at, row.id))

        return [
            ReclaimedOutboxRecord(
                id=row.id,
                tenant_id=row.tenant_id,
                job_id=row.job_id,
                task_name=row.task_name,
                dispatch_attempts=row.dispatch_attempts,
            )
            for row in ordered
        ]

    def mark_dispatched(
        self, session: Session, *, record_id: uuid.UUID, lease_token: uuid.UUID
    ) -> bool:
        """Record that the task now exists in Cloud Tasks. Compare-and-set.

        This is the dispatch evidence v1.1 §1.6 requires. Clearing the lease
        matters as much as setting the status: a dispatched row with a live lease
        would look claimable again the moment the lease expired.

        **Only a row still ``leased`` *and still carrying this caller's token* is
        moved, and that guard is load-bearing.**
        An expired lease is not proof the dispatcher holding it is dead — the
        lease bounds how long a dispatcher may *hold* a row, not how long Cloud
        Tasks may take to answer. So a dispatcher can still be mid-enqueue on a
        row that :meth:`reclaim_stranded` has just written off, and without this
        guard its evidence write would land on a terminal row: back to
        ``dispatched`` while the job stays ``failed_provider``, because the
        caller's ``queued -> dispatched`` transition no-ops against a job that is
        already parked. That is the "failed job beside a live row" state
        ``OutboxDispatcher._record_failure`` shares a transaction to prevent.

        This is the same compare-and-set discipline used everywhere else here —
        :meth:`JobRepository.claim`, the conditional job transitions, the
        ``redrive_pending -> queued`` set — rather than a new mechanism. Widening
        the lease would not have fixed it, only made the window smaller.

        **The token is the ownership half, and J17 closed it here for symmetry
        rather than for a defect.** ``status = 'leased'`` alone is a liveness
        test: it is satisfied by a *peer's* claim as readily as by this caller's.
        On this path that was harmless — a stale write reaching a re-claimed row
        asserts the row is ``dispatched``, and it is, because this caller only
        gets here having enqueued the task or found it already present, so the
        peer's own write would then lose and converge on the same answer. The
        token is required anyway, because a rule about who may finish a row that
        one of its two writers is exempt from is a rule nobody can rely on, and
        the exemption's safety rests on a chain of reasoning about the enqueue
        that a later change could quietly break.

        It is not free, and the cost is named rather than hidden: a stale write
        that used to win now loses, so this dispatcher reports the row as one it
        could not complete — see ``OutboxDispatcher._record_dispatched``'s
        ``unresolved`` branch, which is where a peer's *live* claim now lands.
        The row still ends up ``dispatched``, by the peer that holds it.

        Returns:
            Whether the row was still ``leased``, still carried this caller's
            token, and was moved. ``False`` means this caller lost the race and
            the row has moved on without it. It is not an error, and it is **not
            one situation but two** — the row may have been reclaimed, or
            finalised by a healthy peer. (Since J17 it can also be a peer that
            re-claimed the row and is still working it, which reads as neither.)
            The caller must read :meth:`status_of` before reporting anything,
            because those call for opposite responses; see
            ``OutboxDispatcher._record_dispatched``.
        """
        # ``RETURNING`` rather than ``rowcount``: it is the shape the rest of this
        # module already uses to learn what an UPDATE touched, and it types
        # cleanly, where ``rowcount`` lives on the cursor result and not on the
        # ``Result`` the session is declared to return.
        moved = session.execute(
            sa.update(schema.outbox_record)
            .where(_held_by(record_id, lease_token))
            .values(
                status=OutboxStatus.DISPATCHED.value,
                lease_expires_at=None,
                lease_token=None,
                last_error=None,
            )
            .returning(schema.outbox_record.c.id)
        ).one_or_none()
        return moved is not None

    def status_of(self, session: Session, *, record_id: uuid.UUID) -> OutboxStatus | None:
        """Read one row's current status, or ``None`` if it no longer exists.

        Exists for one caller and one question: a dispatcher whose
        compare-and-set found nothing to move needs to know *what* the row moved
        to, because the answer decides whether anything is wrong. ``failed``
        means the row was written off and the work needs a human; ``dispatched``
        means a peer dispatcher finished it correctly and nothing is wrong at
        all. Reporting the second as the first would have an operator re-drive a
        job that is already running.

        Deliberately not folded into :meth:`mark_dispatched`'s return.
        ``RETURNING`` reports only rows the ``UPDATE`` touched, so the losing
        case returns nothing by construction, and a second read is the honest
        way to ask. It runs only on the losing path, which is rare.
        """
        status = session.execute(
            sa.select(schema.outbox_record.c.status).where(schema.outbox_record.c.id == record_id)
        ).scalar_one_or_none()
        return None if status is None else OutboxStatus(status)

    def mark_failed(
        self,
        session: Session,
        *,
        record_id: uuid.UUID,
        lease_token: uuid.UUID,
        error: str,
        attempts: int,
        now: datetime | None = None,
    ) -> bool:
        """Record a dispatch failure, backing off before the next attempt.

        While attempts remain the row is re-armed as ``leased`` with a lease
        expiring :func:`backoff_for` seconds out. The claim predicate already
        treats a live lease as "not yet claimable", so the lease doubles as the
        backoff timer — no new mechanism and no new column.

        Backoff is not a refinement here, it is correctness. Re-arming
        immediately meant a dispatcher polling every couple of seconds burned all
        five attempts within about ten seconds, permanently parking work for an
        outage that may have resolved a minute later — turning a survivable blip
        into lost work requiring manual re-drive.

        The row must never be left ``leased`` with a NULL lease: the predicate
        matches a leased row only when ``lease_expires_at < now``, and NULL never
        satisfies that comparison, so such a row would be permanently
        unclaimable — invisible work, silently stuck.

        Once attempts are exhausted the row becomes ``failed`` with its lease
        cleared: terminal, no longer claimable, and visible in the operations
        view rather than looping. Leaving a lease on a terminal row would make it
        look claimable again once the timer elapsed.

        **Only a row still ``leased`` and still carrying this caller's token is
        moved**, the same compare-and-set guard :meth:`mark_dispatched` carries
        and for the same race — a dispatcher can
        still be working a row that :meth:`reclaim_stranded` has written off. The
        asymmetry worth naming is what each guard protects, because it is not the
        same thing:

        * For :meth:`mark_dispatched` the guard protects the **status**. Without
          it a terminal row is resurrected to ``dispatched`` beside a parked job.
        * Here the status was never at risk. A late failure-write on a reclaimed
          row necessarily carries ``attempts >= MAX_DISPATCH_ATTEMPTS`` — that is
          what made the row reclaimable — so it takes the exhausted branch and
          writes ``failed`` with a cleared lease: byte-for-byte the state the
          reclaim already put there. What the guard protects is the
          **explanation**. ``last_error`` would be replaced by this attempt's
          queue error, which is exactly the misleading text
          :data:`_STRANDED_ERROR` exists to replace: an operator would read
          "queue unavailable" and go and investigate the queue, when what
          happened is that nothing recorded the final attempt at all.

        So the guard is here for a quieter reason than its twin, not for
        symmetry's sake — but the row it refuses to touch is the same row.

        **This is the writer J17 was actually filed against, and the token is
        what closes it.** ``status = 'leased'`` is a *liveness* test, not an
        *ownership* test: it proves someone holds the row, not that the caller
        does. It closes the race against :meth:`reclaim_stranded`, because a
        reclaimed row is ``failed`` and so fails the check. It never closed the
        race against a peer dispatcher that re-claimed the row after this
        caller's lease expired — that peer's own claim satisfies ``leased``, so a
        stale failure-write landed on it. Measured before the fix: a peer
        re-claims with a fresh 60-second lease, a stale write carrying the
        *older* attempt count then overwrites the lease with that count's much
        shorter backoff, cutting 56 seconds off it and replacing the peer's
        ``last_error``. The row became claimable again while the peer was still
        working it, and the extra claim burned an attempt the row should not have
        spent — repeated near the limit, a row could be parked as exhausted
        having had fewer real attempts than :data:`MAX_DISPATCH_ATTEMPTS`
        promises.

        ``lease_token`` (migration ``0004``) is that missing identity: minted per
        row by :meth:`claim_batch`, carried on the
        :class:`ClaimedOutboxRecord`, and required back here. The peer holds a
        different token, so the stale writer now matches zero rows and takes the
        lost-the-race path instead of corrupting the winner's state. See
        :func:`_held_by` for what a ``NULL`` token means and for the rollout
        constraint the column does not remove.

        **The re-armed row keeps its token, deliberately.** The backoff branch
        writes ``leased`` again with a later lease, and that is the same claim
        cooling off rather than a new one — this caller is still the last
        dispatcher to have held the row. Clearing it would leave a ``leased`` row
        with a ``NULL`` token, which is the shape :func:`_held_by` reads as "held
        by someone unidentifiable", and would say something false about the row.
        The next :meth:`claim_batch` overwrites it with a fresh token, which is
        where the new claim's ownership begins.

        Args:
            lease_token: The token :meth:`claim_batch` minted for this claim, off
                the :class:`ClaimedOutboxRecord`. Required, not optional: a
                default would let a caller silently opt out of the ownership
                check J17 exists to add.
            attempts: The attempt count this failure belongs to, as returned by
                :meth:`claim_batch`. Passed in rather than recomputed in SQL so
                the backoff schedule is plain Python and unit-testable without a
                database.

        Returns:
            Whether the row was still ``leased``, still carried this caller's
            token, and was moved. ``False`` means the row was written off, or
            finished, or re-claimed by a peer while this attempt was in flight.
        """
        moment = now or datetime.now(UTC)
        exhausted = attempts >= MAX_DISPATCH_ATTEMPTS

        moved = session.execute(
            sa.update(schema.outbox_record)
            .where(_held_by(record_id, lease_token))
            .values(
                status=(OutboxStatus.FAILED.value if exhausted else OutboxStatus.LEASED.value),
                lease_expires_at=(None if exhausted else moment + backoff_for(attempts)),
                # Cleared only where the lease is cleared. On the backoff branch
                # the row stays `leased` and keeps this caller's token — see the
                # docstring for why a `leased` row must never carry a NULL one.
                lease_token=(None if exhausted else lease_token),
                last_error=error[:2000],
            )
            .returning(schema.outbox_record.c.id)
        ).one_or_none()
        return moved is not None

    def pending_count(self, session: Session, *, now: datetime | None = None) -> int:
        """Count rows still awaiting dispatch.

        Half of the dispatcher's lag metric (v1.1 §1.6 requires one, with an
        alert). A rising count means dispatch is falling behind the rate commands
        are accepted, which is the failure this system can otherwise hide.

        Deliberately **not** tenant-scoped: this measures the dispatcher, which
        serves every tenant. A per-tenant view would hide a global backlog.
        """
        now = now or datetime.now(UTC)
        return int(
            session.execute(
                sa.select(sa.func.count())
                .select_from(schema.outbox_record)
                .where(_claimable_predicate(now))
            ).scalar_one()
        )

    def oldest_pending_age(
        self, session: Session, *, now: datetime | None = None
    ) -> timedelta | None:
        """Age of the oldest undispatched row, or ``None`` when there are none.

        The other half of the lag metric. A count alone cannot distinguish a
        healthy burst from one row stuck for an hour.

        Uses exactly the predicate :meth:`pending_count` uses. When the two
        disagreed, a zero count could accompany a non-null age, which is
        nonsense an operator would have to debug rather than act on.
        """
        now = now or datetime.now(UTC)
        oldest: datetime | None = session.execute(
            sa.select(sa.func.min(schema.outbox_record.c.created_at)).where(
                _claimable_predicate(now)
            )
        ).scalar_one_or_none()

        if oldest is None:
            return None
        return now - oldest
