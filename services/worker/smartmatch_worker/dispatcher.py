"""Outbox dispatcher.

Architecture v1.1 §1.6, component ``D`` in the dispatch sequence. Moves durable
intents from the outbox into Cloud Tasks, and records the evidence that it did.

The dispatcher is deliberately the *only* component that creates tasks. Nothing
in the API request path talks to Cloud Tasks, so a browser request can never
enqueue work that has not first been committed to PostgreSQL.

## Why each step is ordered the way it is

``run_once`` begins by reclaiming: before it claims anything it writes off rows
whose attempts were spent without any attempt ever recording an outcome. That is
not a tidy-up. While attempts remain, a dispatcher that dies mid-row is handled
by lease expiry and a retry; on the *final* attempt there is no retry, because
the claim predicate requires attempts remaining — so the row would sit ``leased``
forever, uncounted by the lag metric and invisible as ``failed``, with its job
stuck ``queued``. See :meth:`OutboxDispatcher.reclaim_stranded`.

The sweep is guarded, because it is janitorial: a deadlock or a lock timeout
while tidying up yesterday's wreckage must not cost a healthy row today's
dispatch. And because an expired lease does not prove the dispatcher holding it
is dead, both evidence writes — ``mark_dispatched`` and ``mark_failed`` — are
compare-and-set on the row still being ``leased``, so an instance that was
mid-enqueue when the sweep ran cannot write over a row that was written off.

It then does three things per row, and the order is load-bearing:

1. **Claim, then commit.** The lease must be visible to other dispatchers
   *before* the slow provider call, or two dispatchers both dispatch the row.
2. **Enqueue.** Slow, and outside any transaction — holding one open across a
   network call to Cloud Tasks would pin a connection for the whole round trip.
3. **Record the outcome in a fresh transaction.** If the process dies between
   steps 2 and 3, the lease expires, another dispatcher retries, and the
   deterministic task name makes the retry a no-op rather than a double
   dispatch. That is the case the whole design exists to survive — on every
   attempt but the last, where the reclaim above is what survives it instead.

Also worth stating plainly: the job's ``queued -> dispatched`` transition happens
here, in the same transaction as ``mark_dispatched``. Doing it before the enqueue
would claim the job was dispatched when it might not be.

## One row's failure is never the batch's failure

Every row in a claimed batch is attempted, whatever the previous row did. A row
that escapes with an exception takes its lease with it: the row is not lost —
the lease expires and someone retries it — but the remaining rows sit ``leased``
for a lease's length having never been attempted, and the pass reports nothing
about them. So the per-row guard catches ``Exception``, from the enqueue *and*
from recording the outcome, and turns it into a counted failure.

``BaseException`` is deliberately not caught. ``KeyboardInterrupt`` and
``SystemExit`` are how a process is asked to stop; a dispatcher that worked
through the rest of the batch first would be ignoring the request.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from smartmatch_domain.jobs import JobState
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import (
    DEFAULT_LEASE,
    MAX_DISPATCH_ATTEMPTS,
    ClaimedOutboxRecord,
    OutboxRepository,
    OutboxStatus,
    ReclaimedOutboxRecord,
)
from smartmatch_providers.tasks import (
    TaskAlreadyExists,
    TaskQueue,
    TaskQueueError,
    TaskRequest,
)
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["DispatchOutcome", "DispatcherLag", "OutboxDispatcher"]

logger = logging.getLogger(__name__)

#: What one row's processing amounted to. Exactly one of these per claimed row,
#: which is what keeps ``claimed == dispatched + already_existed + failed`` true
#: on every path through the loop.
_RowOutcome = Literal["dispatched", "already_existed", "failed"]

#: What happened when a dispatcher tried to record a dispatch it had performed.
#:
#: The compare-and-set in ``mark_dispatched`` can fail for two reasons that look
#: identical from the return value and are opposite in meaning, so they are named
#: apart here rather than collapsed into a bool. Reporting ``superseded`` as
#: ``reclaimed`` would have an operator re-drive a job that is already running,
#: which duplicates live work — the one outcome ADR-0007 exists to prevent.
_RecordResult = Literal[
    # This dispatcher still owned the row and recorded its dispatch.
    "recorded",
    # A peer dispatcher claimed the row after this one's lease expired and
    # finalised it correctly. Convergence, not a problem.
    "superseded",
    # The reclaim wrote the row off. The job is parked and needs a human.
    "reclaimed",
    # The row moved on in some other way, or is gone. Not understood, so nothing
    # is asserted about it beyond "this dispatcher did not record a dispatch".
    "unresolved",
]


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """What one dispatcher pass accomplished.

    Attributes:
        claimed: Rows claimed this pass.
        dispatched: Rows whose task now exists in the queue.
        already_existed: Rows whose task was already present — a previous
            attempt succeeded before crashing. Counted separately because it is
            the *expected* recovery path, and folding it into failures would
            make a healthy recovery look like an incident.
        failed: Rows this pass did not finish: the enqueue failed, or it
            succeeded but the evidence could not be written. Both are retried
            after the lease expires, and parked once attempts are exhausted. An
            unrecorded dispatch is counted here rather than as a success,
            because the dispatcher's own record is what the rest of the system
            reads — a dispatch nothing recorded is one nothing can act on.
        reclaimed: Rows written off at the start of this pass because their
            attempts were spent and no attempt had ever recorded an outcome.

    ``claimed``, ``dispatched``, ``already_existed`` and ``failed`` always
    satisfy ``claimed == dispatched + already_existed + failed``. Operators alert
    on these numbers, and a pass that claimed five rows while accounting for four
    would look exactly like the silent loss the outbox exists to make impossible.

    **``reclaimed`` is deliberately outside that identity, and is not a bug.** A
    reclaimed row was not claimed on this pass — it was claimed on some earlier
    pass by a dispatcher that never came back, and this pass is disposing of the
    wreckage. Adding it to the left-hand side would say a row was picked up for
    dispatch when it was not; adding it to the right would say it reached one of
    the three outcomes, when its whole problem is that it reached none.

    A non-zero ``reclaimed`` is a real signal and deserves an alert of its own.
    It means a dispatcher died, or the database refused a write, at the one
    moment in a row's life when that is unrecoverable — the final attempt. It
    should normally be zero, and a rising count is a statement about the
    dispatcher's own health rather than about the queue's.
    """

    claimed: int = 0
    dispatched: int = 0
    already_existed: int = 0
    failed: int = 0
    reclaimed: int = 0

    @property
    def is_idle(self) -> bool:
        """Whether there was nothing to do.

        ``reclaimed`` counts here even though it is outside the accounting
        identity: a pass that wrote off stranded work did something, and a poll
        loop that backed off on the strength of ``is_idle`` would be sleeping
        through the one signal that says a dispatcher is dying.
        """
        return self.claimed == 0 and self.reclaimed == 0


@dataclass(frozen=True, slots=True)
class DispatcherLag:
    """The dispatcher's lag metric (v1.1 §1.6 requires one, with an alert).

    Attributes:
        pending: Rows awaiting dispatch.
        oldest_age: Age of the oldest, or ``None`` when the outbox is empty.
            A count alone cannot distinguish a healthy burst from one row stuck
            for an hour, which is why both are reported.
    """

    pending: int
    oldest_age: timedelta | None

    def exceeds(self, *, max_pending: int, max_age: timedelta) -> bool:
        """Whether this lag warrants an alert."""
        if self.pending > max_pending:
            return True
        return self.oldest_age is not None and self.oldest_age > max_age


class OutboxDispatcher:
    """Polls the outbox and creates Cloud Tasks entries.

    Args:
        session_factory: Produces sessions. The dispatcher opens and closes its
            own transactions, unlike the repositories it calls, because the
            ordering described in the module docstring *is* its job.
        task_queue: Where tasks are created.
        lease: How long a claim is held before another dispatcher may take it.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        task_queue: TaskQueue,
        *,
        lease: timedelta = DEFAULT_LEASE,
    ) -> None:
        self._session_factory = session_factory
        self._task_queue = task_queue
        self._lease = lease
        self._outbox = OutboxRepository()
        self._jobs = JobRepository()

    def run_once(self, *, batch_size: int = 20) -> DispatchOutcome:
        """Claim and dispatch one batch.

        Returns:
            A :class:`DispatchOutcome` summarizing the pass. Never raises for an
            individual row's failure — one bad row must not stall the batch, so
            failures are recorded and counted.

        Raises:
            Exception: whatever the *claim* raised. A batch that could not be
                claimed never started, so there is nothing to summarize and
                nothing to lose by letting the caller's poll loop see it — with
                one exception, which is annotated onto the error rather than
                swallowed with it: any rows the reclaim had already committed
                before the claim failed. Those are done, and a note on the
                exception says how many.
        """
        # Before the claim, not after, so a pass that rescues a row also reports
        # it in the outcome the operator is reading — rather than in the next
        # one, which may be a poll interval away or may never come.
        #
        # This rides ``run_once`` rather than living in a scheduled sweeper of
        # its own because nothing in this system runs on a timer yet (backlog
        # J8), so a standalone sweeper would be dead code the day it was written.
        # The coupling is real and is recorded against J8: a dispatcher that is
        # not running is precisely the condition that strands rows, and is then
        # also the condition under which nothing reclaims them.
        # Guarded, because the sweep is janitorial and this method's contract is
        # that only a failed *claim* aborts a pass. The reclaim touches rows this
        # pass has no other interest in and takes job-row locks other paths also
        # take, so a deadlock or a lock timeout in it is entirely possible —
        # and letting yesterday's wreckage stop today's dispatch would be a
        # worse failure than the one being swept up. Same reasoning as
        # ``_record_failure_safely``. ``BaseException`` is deliberately not
        # caught, for the reason the module docstring gives.
        #
        # ``reclaimed`` stays 0 on failure: the repository call and the job
        # transitions share one transaction, so a raise means nothing was
        # committed, and reporting otherwise would credit the pass with work it
        # did not do.
        try:
            reclaimed = self.reclaim_stranded(batch_size=batch_size)
        except Exception:
            logger.exception(
                "reclaim sweep failed; continuing with the claim. Stranded rows "
                "remain stranded until a later pass succeeds"
            )
            reclaimed = 0

        try:
            with self._session_factory() as session:
                claimed = self._outbox.claim_batch(session, limit=batch_size, lease=self._lease)
                # Commit so the lease is visible to other dispatchers before the
                # slow provider call below. Without this, a concurrent
                # dispatcher could claim the same rows.
                session.commit()
        except Exception as exc:
            # The claim still propagates — a batch that could not be claimed
            # never started, and the caller's poll loop must see that rather than
            # be told the pass was quiet. But the reclaim above already
            # committed, and it is a fact regardless of what happened next.
            #
            # Losing it here would be exactly backwards: a database under enough
            # strain to fail a claim is the same database that strands rows, so
            # the signal would vanish precisely when it is most informative. It
            # is carried out on the exception, where it travels with the
            # traceback the poll loop logs, and stated in a line of its own so it
            # is greppable without parsing one.
            if reclaimed:
                logger.warning(
                    "the claim failed after %d stranded row(s) had already been "
                    "reclaimed and committed; that reclaim stands",
                    reclaimed,
                )
                exc.add_note(
                    f"{reclaimed} stranded outbox row(s) were reclaimed and committed "
                    "by this pass before the claim failed; that work is done and "
                    "should not be counted as lost."
                )
            raise

        if not claimed:
            return DispatchOutcome(reclaimed=reclaimed)

        # One outcome per row, counted here rather than accumulated inside the
        # per-row code, so no path can return without contributing exactly one.
        #
        # When the database is unreachable every row will fail — each enqueue
        # may well succeed, and each attempt to record it will not. That is
        # accepted rather than circuit-broken: the loop is bounded by
        # ``batch_size``, each failure is a fast error against a dead pool, and
        # the tasks created without evidence are the crash-recovery case the
        # deterministic task name already handles. The pass after it claims
        # nothing, because ``claim_batch`` needs the same database and raises
        # before a single row is touched, so this cannot spin.
        counts: Counter[_RowOutcome] = Counter()
        for record in claimed:
            counts[self._dispatch_row(record)] += 1

        return DispatchOutcome(
            claimed=len(claimed),
            dispatched=counts["dispatched"],
            already_existed=counts["already_existed"],
            failed=counts["failed"],
            reclaimed=reclaimed,
        )

    def reclaim_stranded(self, *, batch_size: int = 20) -> int:
        """Write off rows that exhausted their attempts without recording one.

        The recovery path for the state nothing else can reach. A row is claimed,
        its attempt counter incremented and committed, and then the dispatcher
        stops before writing what happened — a killed process, an evicted pod, an
        OOM, a drained node, or a failure-write that itself failed. While
        attempts remain that is survivable and by design: the lease expires and
        another dispatcher retries. **On the final attempt it is not.** The claim
        predicate requires strictly fewer than ``MAX_DISPATCH_ATTEMPTS``, so the
        row is never claimed again, never counted by the lag metric that shares
        that predicate, and never visible as ``failed`` — while its job sits
        ``queued``. ``TRANSITIONS[QUEUED]`` is ``{dispatched, cancelled,
        failed_provider}`` — which is what makes this method's own parking write
        legal — and it notably does **not** include ``redrive_pending``, so even
        the re-drive command answers 409 on such a job forever.

        The two writes share one transaction, for the reason
        :meth:`_record_failure` gives at exhaustion and which applies unchanged
        here: *a parked row beside a ``queued`` job, or a failed job beside a
        live row, are each a state nothing would reconcile.* This is the same
        pair of writes ``_record_failure`` performs when attempts run out; the
        difference is only that nothing was alive to perform them.

        The job transition is conditional on the job still being ``queued``. It
        will not be if an earlier attempt of this row did manage to record a
        dispatch before the row was later stranded, so a ``False`` result is
        normal and not worth logging as a problem — the same reasoning
        :meth:`_record_dispatched` gives for its own conditional transition.

        Logged at ``warning``, one line per row. A reclaim is never routine: it
        means a dispatcher died, or the database refused a write, at the one
        moment in a row's life when that cannot be retried away.

        **Logged after the commit, and only about what the commit did.** A
        reclaim is not a fact until it commits, and the lines were being written
        inside the loop: anything raising part-way through a batch — a deadlock
        on a job row, a failed commit — left up to ``batch_size`` WARNINGs
        announcing rows as reclaimed while the transaction rolled back, every one
        of those rows stayed ``leased``, and this method reported nothing. An
        operator reconciling the log against the metric would find them
        contradicting each other, with the log the one that was wrong.

        Each line also reports what the *job* transition actually did rather than
        assuming it. The transition is conditional on the job still being
        ``queued``, and a job that has moved on — cancelled, or advanced by an
        earlier attempt of this row that did record a dispatch — is not parked by
        this sweep. Saying "its job parked" regardless would be describing a
        write that did not happen.

        Returns:
            How many rows were written off.
        """
        with self._session_factory() as session:
            stranded = self._outbox.reclaim_stranded(session, limit=batch_size)
            # (record, whether this sweep also parked its job), collected inside
            # the transaction and reported only once it has committed.
            outcomes: list[tuple[ReclaimedOutboxRecord, bool]] = []
            for record in stranded:
                parked = self._jobs.transition(
                    session,
                    tenant_id=record.tenant_id,
                    job_id=record.job_id,
                    to_state=JobState.FAILED_PROVIDER,
                    expected_from=JobState.QUEUED,
                )
                outcomes.append((record, parked))
            session.commit()

        for record, parked in outcomes:
            logger.warning(
                "outbox row %s: task %s exhausted %d attempts without ever "
                "recording an outcome; reclaimed as failed and %s",
                record.id,
                record.task_name,
                record.dispatch_attempts,
                "its job parked" if parked else "its job left as it was, already past 'queued'",
            )

        return len(outcomes)

    def lag(self) -> DispatcherLag:
        """Measure how far behind dispatch has fallen."""
        with self._session_factory() as session:
            return DispatcherLag(
                pending=self._outbox.pending_count(session),
                oldest_age=self._outbox.oldest_pending_age(session),
            )

    # -- internals ---------------------------------------------------------

    def _dispatch_row(self, record: ClaimedOutboxRecord) -> _RowOutcome:
        """Enqueue one row's task and record what happened.

        Returns rather than raises, for every failure short of a
        ``BaseException``: the caller is iterating a claimed batch, and an
        exception escaping here abandons every row after this one.

        The unexpected-exception arm is the load-bearing one. ``TaskQueueError``
        and ``TaskAlreadyExists`` are the failures this dispatcher was written
        for; a live queue client can also raise a credentials refresh failure, a
        transport error, or a ``ValueError`` about a payload it dislikes, and
        none of those are a reason to stop dispatching everyone else's work. It
        is recorded like any other failure so the row backs off, retries, and is
        eventually parked for a human rather than retried forever.
        """
        try:
            self._task_queue.enqueue(
                TaskRequest(
                    name=record.task_name,
                    # Identifiers only. The worker re-reads authoritative
                    # state from PostgreSQL, because a task can sit in the
                    # queue while consent, budget, or approval change.
                    payload={
                        "tenant_id": str(record.tenant_id),
                        "job_id": str(record.job_id),
                    },
                )
            )
            outcome: _RowOutcome = "dispatched"
        except TaskAlreadyExists:
            # A previous attempt created the task and crashed before
            # recording it. The work is enqueued exactly once; converge.
            logger.info(
                "outbox row %s: task %s already existed; treating as dispatched",
                record.id,
                record.task_name,
            )
            outcome = "already_existed"
        except TaskQueueError as exc:
            logger.warning("outbox row %s: dispatch failed: %s", record.id, exc)
            return self._record_failure_safely(record, str(exc))
        except Exception as exc:
            # Logged with the row id and a traceback: an error nobody predicted
            # is the one an operator most needs to be able to find.
            logger.exception("outbox row %s: unexpected dispatch failure", record.id)
            return self._record_failure_safely(record, f"{type(exc).__name__}: {exc}")

        try:
            recorded = self._record_dispatched(record.tenant_id, record.job_id, record.id)
            if recorded == "superseded":
                # A peer dispatcher claimed the row once this one's lease expired
                # and finalised it correctly. Nothing is wrong: the row is
                # ``dispatched``, the job is ``dispatched``, and the work is on
                # its way. Exactly the convergence the deterministic task name
                # exists to make safe, arrived at from the other side.
                #
                # Counted ``already_existed`` for the reason that bucket exists —
                # "folding it into failures would make a healthy recovery look
                # like an incident" — and logged at ``info``, with no advice to
                # act. Telling an operator to re-drive here would duplicate live
                # work, which is the one outcome ADR-0007 is built to prevent.
                logger.info(
                    "outbox row %s: task %s was finalised by another dispatcher "
                    "while this one was enqueuing; converging",
                    record.id,
                    record.task_name,
                )
                return "already_existed"

            if recorded == "reclaimed":
                # The other losing case, and the opposite situation. While this
                # enqueue was in flight the row's lease expired and the sweep
                # wrote it off as ``failed`` with the job parked.
                #
                # Counted ``failed`` because that is what the database now says
                # and what this pass achieved — reporting ``dispatched`` would
                # contradict a row that reads ``failed``, a disagreement an
                # operator has to debug instead of act on.
                #
                # Nothing is recorded, and that is the difference from every
                # other ``failed`` return here. Elsewhere returning "failed"
                # without recording it would leave the row as the claim left it —
                # ``leased``, drifting toward the invisible state J12 exists to
                # close. Here the row is already terminal and already carries a
                # truer explanation than this attempt could write.
                #
                # The task is real and may still deliver. It will execute
                # nothing: the job is ``failed_provider`` and
                # ``JobRepository.claim`` moves only a ``dispatched`` job. Here a
                # re-drive genuinely is what an operator should do, and this log
                # line is the only place this dispatcher can say so.
                logger.warning(
                    "outbox row %s: task %s was created, but the row had already "
                    "been reclaimed and its job parked; not recording a dispatch. "
                    "The task will claim nothing. Re-drive the job to re-run it.",
                    record.id,
                    record.task_name,
                )
                return "failed"

            if recorded == "unresolved":
                # The row moved on in a way this dispatcher does not understand,
                # or is gone. Nothing is asserted about it and no advice is
                # given — guessing here is how an operator gets told to duplicate
                # live work. Counted ``failed`` only in the sense that this pass
                # did not complete the row.
                logger.warning(
                    "outbox row %s: task %s was created, but the row is no longer "
                    "in a state this dispatcher can record against; leaving it "
                    "alone. Inspect the row before acting.",
                    record.id,
                    record.task_name,
                )
                return "failed"
        except Exception as exc:
            # The task exists but nothing says so. Recorded as a failure — not
            # merely counted as one — because the row has consumed an attempt
            # and something must say so durably.
            #
            # Returning "failed" without recording it was a real defect. The row
            # would be left exactly as the claim left it: ``leased``, with a
            # lease that expires and an attempt count that keeps climbing. That
            # is harmless while attempts remain, and silently wrong at the end —
            # ``_claimable_predicate`` also requires ``dispatch_attempts <
            # MAX_DISPATCH_ATTEMPTS``, so on the final attempt the row stops
            # being claimable while its status still reads ``leased``. It would
            # then never be retried, never be counted by the lag metric (which
            # shares that predicate), and never appear as ``failed`` in an
            # operations view: invisible work, silently stuck.
            #
            # Recording it means the row backs off and retries while attempts
            # remain, and parks as ``failed`` when they run out. The retry finds
            # the task already present and converges on 'dispatched', which is
            # exactly the crash-recovery path the deterministic name exists for.
            logger.exception(
                "outbox row %s: task %s was created but recording it failed",
                record.id,
                record.task_name,
            )
            return self._record_failure_safely(
                record, f"dispatch recorded no evidence: {type(exc).__name__}: {exc}"
            )

        return outcome

    def _record_failure_safely(self, record: ClaimedOutboxRecord, error: str) -> _RowOutcome:
        """Record a failure, tolerating a failure to record it.

        A database blip while writing the evidence for one row must not cost the
        remaining rows their attempt, so the error is swallowed rather than
        raised. Re-raising was considered and rejected: it would break the
        module's rule that one row's failure is never the batch's failure, and
        the rows behind it would lose their attempt to a problem that is
        recoverable anyway.

        **Why giving up is safe, stated correctly.** While attempts remain, an
        unrecorded failure leaves the row exactly as the claim left it, so the
        lease expires and another pass retries it — the same path a killed
        dispatcher takes. That was once the whole story, and on the final attempt
        it was never true: a row at ``MAX_DISPATCH_ATTEMPTS`` is not claimable,
        so "the lease expires and it is retried" described something that could
        not happen, and the row stayed ``leased`` forever.

        What makes swallowing safe now is :meth:`reclaim_stranded`, which runs at
        the top of every pass and writes such a row off as ``failed`` with its
        job parked. So: while attempts remain the row is *retried*; on the last
        attempt it is *reclaimed*. Neither is lost, but they are not the same
        thing, and the difference is the whole of J12.
        """
        try:
            recorded = self._record_failure(record, error, record.dispatch_attempts)
        except Exception:
            logger.exception("outbox row %s: recording the failure itself failed", record.id)
            return "failed"

        if recorded == "superseded":
            # A peer dispatcher claimed the row once this one's lease expired and
            # dispatched it successfully, while this one's own attempt failed.
            # The work is enqueued and the job is ``dispatched``: convergence,
            # not this pass's failure. Counted and logged exactly as the same
            # discovery is on the dispatch path — ``already_existed``, at
            # ``info``, with no advice to act, because re-driving a job that is
            # already running duplicates live work.
            logger.info(
                "outbox row %s: task %s was dispatched by another dispatcher "
                "while this one's attempt was failing; converging",
                record.id,
                record.task_name,
            )
            return "already_existed"

        if recorded == "reclaimed":
            # The sweep wrote the row off while this attempt was in flight. Its
            # ``last_error`` already explains what happened more accurately than
            # this attempt could, so nothing is written over it. The job is
            # parked and needs a human, and unlike the case above that advice is
            # correct here.
            logger.warning(
                "outbox row %s: recording a failure found the row already "
                "reclaimed and its job parked; leaving the reclaim's record "
                "intact. Re-drive the job to re-run it.",
                record.id,
            )
            return "failed"

        if recorded == "unresolved":
            # The row moved on in a way this dispatcher does not understand, or
            # is gone. Nothing is asserted and no advice is given: guessing here
            # is how an operator gets told to duplicate live work.
            logger.warning(
                "outbox row %s: recording a failure found the row no longer in a "
                "state this dispatcher can write to; leaving it alone. Inspect "
                "the row before acting.",
                record.id,
            )
            return "failed"

        return "failed"

    def _record_dispatched(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, record_id: uuid.UUID
    ) -> _RecordResult:
        """Mark the outbox row dispatched and advance the job, atomically.

        Both in one transaction: a job left ``queued`` with a dispatched outbox
        row would never be picked up again, and a job marked ``dispatched`` with
        a pending outbox row would be dispatched twice.

        The job transition is conditional on the job still being ``queued``. It
        will not be if this is a retry after a crash, in which case the earlier
        attempt already advanced it — so a ``False`` result there is normal and
        not worth logging as a problem.

        **The outbox write goes first, and is also conditional.** It is the one
        that decides whether this dispatcher still owns the row:
        :meth:`~OutboxRepository.mark_dispatched` moves it only while it is still
        ``leased``, so a row :meth:`reclaim_stranded` has already written off is
        left alone and nothing is committed. Ordering it first is what makes that
        check meaningful — and it also puts this method's locks in the same order
        as the reclaim's and :meth:`_record_failure`'s, ``outbox_record`` then
        ``job``. It was the only one of the three taking them the other way
        round, which is a deadlock waiting for the traffic to find it.

        **Losing the compare-and-set is not one situation but two**, and they
        are opposite. The row may have been written off by
        :meth:`reclaim_stranded` — the job is parked, no worker will touch it,
        and a human has to re-drive it. Or a peer dispatcher may have claimed the
        row once this one's lease expired and finalised it correctly, which is
        the ordinary recovery path the deterministic task name exists to make
        safe: the row is ``dispatched``, the job is ``dispatched``, and the work
        is on its way. So the row's status is read before anything is reported.
        Announcing the second as the first would have an operator re-drive a job
        that is already running.

        Returns:
            One of :data:`_RecordResult`.
        """
        with self._session_factory() as session:
            if self._outbox.mark_dispatched(session, record_id=record_id):
                self._jobs.transition(
                    session,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    to_state=JobState.DISPATCHED,
                    expected_from=JobState.QUEUED,
                )
                session.commit()
                return "recorded"

            # Nothing was written, so nothing needs committing. Read what the row
            # moved to instead: it is the only thing that distinguishes a peer
            # that succeeded from a sweep that gave up.
            status = self._outbox.status_of(session, record_id=record_id)

        if status is OutboxStatus.DISPATCHED:
            return "superseded"
        if status is OutboxStatus.FAILED:
            return "reclaimed"
        return "unresolved"

    def _record_failure(
        self, record: ClaimedOutboxRecord, error: str, attempts: int
    ) -> _RecordResult:
        """Record a dispatch failure, and park the job once attempts run out.

        While attempts remain the job stays ``queued``: it has not been
        dispatched, and saying otherwise would strand it. The row backs off and
        another pass will try again.

        **At exhaustion that stops being true.** The row becomes ``failed`` and
        no dispatcher will look at it again, so a job left ``queued`` is
        describing a state it is no longer in — and ``queued`` reaches neither a
        terminal state nor ``redrive_pending``, so the re-drive command answers
        409 forever on precisely the work the dispatcher gave up on. The job is
        moved to ``failed_provider``: the queue is the provider that failed, and
        it is one of the two states with a route back through re-drive.

        Both writes share one transaction. A parked row beside a ``queued`` job,
        or a failed job beside a live row, are each a state nothing would
        reconcile.

        Like :meth:`_record_dispatched`, the outbox write is a compare-and-set,
        and losing it is **two situations rather than one** — the identical
        ambiguity, down the other branch. The row may have been reclaimed by the
        sweep, or dispatched by a healthy peer that claimed it once this
        caller's lease expired. ``mark_failed`` loses to the second as readily as
        to the first, so the row's status is read before anything is reported;
        reporting a peer's success as a reclaim would count a dispatched row as
        a failure and send an operator to re-drive live work.

        Either way nothing is written and the method returns early, which also
        avoids taking a job-row lock for a transition that would no-op.

        Returns:
            One of :data:`_RecordResult`.
        """
        with self._session_factory() as session:
            if not self._outbox.mark_failed(
                session, record_id=record.id, error=error, attempts=attempts
            ):
                status = self._outbox.status_of(session, record_id=record.id)
                if status is OutboxStatus.DISPATCHED:
                    return "superseded"
                return "reclaimed" if status is OutboxStatus.FAILED else "unresolved"
            if attempts >= MAX_DISPATCH_ATTEMPTS:
                self._jobs.transition(
                    session,
                    tenant_id=record.tenant_id,
                    job_id=record.job_id,
                    to_state=JobState.FAILED_PROVIDER,
                    expected_from=JobState.QUEUED,
                )
            session.commit()
        return "recorded"
