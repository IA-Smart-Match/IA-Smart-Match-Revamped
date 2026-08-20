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
    """An outbox row claimed by a dispatcher, with its lease running."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    job_id: uuid.UUID
    task_name: str
    dispatch_attempts: int
    lease_expires_at: datetime


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
                dispatch_attempts=schema.outbox_record.c.dispatch_attempts + 1,
            )
            .returning(
                schema.outbox_record.c.id,
                schema.outbox_record.c.tenant_id,
                schema.outbox_record.c.job_id,
                schema.outbox_record.c.task_name,
                schema.outbox_record.c.dispatch_attempts,
                schema.outbox_record.c.lease_expires_at,
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
            )
            for row in ordered
        ]

    def mark_dispatched(self, session: Session, *, record_id: uuid.UUID) -> None:
        """Record that the task now exists in Cloud Tasks.

        This is the dispatch evidence v1.1 §1.6 requires. Clearing the lease
        matters as much as setting the status: a dispatched row with a live lease
        would look claimable again the moment the lease expired.
        """
        session.execute(
            sa.update(schema.outbox_record)
            .where(schema.outbox_record.c.id == record_id)
            .values(
                status=OutboxStatus.DISPATCHED.value,
                lease_expires_at=None,
                last_error=None,
            )
        )

    def mark_failed(
        self,
        session: Session,
        *,
        record_id: uuid.UUID,
        error: str,
        attempts: int,
        now: datetime | None = None,
    ) -> None:
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

        Args:
            attempts: The attempt count this failure belongs to, as returned by
                :meth:`claim_batch`. Passed in rather than recomputed in SQL so
                the backoff schedule is plain Python and unit-testable without a
                database.
        """
        moment = now or datetime.now(UTC)
        exhausted = attempts >= MAX_DISPATCH_ATTEMPTS

        session.execute(
            sa.update(schema.outbox_record)
            .where(schema.outbox_record.c.id == record_id)
            .values(
                status=(OutboxStatus.FAILED.value if exhausted else OutboxStatus.LEASED.value),
                lease_expires_at=(None if exhausted else moment + backoff_for(attempts)),
                last_error=error[:2000],
            )
        )

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
