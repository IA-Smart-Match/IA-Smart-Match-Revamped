"""Outbox dispatcher.

Architecture v1.1 §1.6, component ``D`` in the dispatch sequence. Moves durable
intents from the outbox into Cloud Tasks, and records the evidence that it did.

The dispatcher is deliberately the *only* component that creates tasks. Nothing
in the API request path talks to Cloud Tasks, so a browser request can never
enqueue work that has not first been committed to PostgreSQL.

## Why each step is ordered the way it is

``run_once`` does three things per row, and the order is load-bearing:

1. **Claim, then commit.** The lease must be visible to other dispatchers
   *before* the slow provider call, or two dispatchers both dispatch the row.
2. **Enqueue.** Slow, and outside any transaction — holding one open across a
   network call to Cloud Tasks would pin a connection for the whole round trip.
3. **Record the outcome in a fresh transaction.** If the process dies between
   steps 2 and 3, the lease expires, another dispatcher retries, and the
   deterministic task name makes the retry a no-op rather than a double
   dispatch. That is the case the whole design exists to survive.

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

    The four fields always satisfy ``claimed == dispatched + already_existed +
    failed``. Operators alert on these numbers, and a pass that claimed five
    rows while accounting for four would look exactly like the silent loss the
    outbox exists to make impossible.
    """

    claimed: int = 0
    dispatched: int = 0
    already_existed: int = 0
    failed: int = 0

    @property
    def is_idle(self) -> bool:
        """Whether there was nothing to do."""
        return self.claimed == 0


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
                nothing to lose by letting the caller's poll loop see it.
        """
        with self._session_factory() as session:
            claimed = self._outbox.claim_batch(session, limit=batch_size, lease=self._lease)
            # Commit so the lease is visible to other dispatchers before the slow
            # provider call below. Without this, a concurrent dispatcher could
            # claim the same rows.
            session.commit()

        if not claimed:
            return DispatchOutcome()

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
        )

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
            self._record_dispatched(record.tenant_id, record.job_id, record.id)
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
        remaining rows their attempt. Nothing is lost by giving up here: an
        unrecorded failure leaves the row exactly as the claim left it, so the
        lease expires and it is retried — the same path a killed dispatcher
        takes.
        """
        try:
            self._record_failure(record, error, record.dispatch_attempts)
        except Exception:
            logger.exception("outbox row %s: recording the failure itself failed", record.id)
        return "failed"

    def _record_dispatched(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, record_id: uuid.UUID
    ) -> None:
        """Mark the outbox row dispatched and advance the job, atomically.

        Both in one transaction: a job left ``queued`` with a dispatched outbox
        row would never be picked up again, and a job marked ``dispatched`` with
        a pending outbox row would be dispatched twice.

        The job transition is conditional on the job still being ``queued``. It
        will not be if this is a retry after a crash, in which case the earlier
        attempt already advanced it — so a ``False`` result here is normal and
        not worth logging as a problem.
        """
        with self._session_factory() as session:
            self._jobs.transition(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                to_state=JobState.DISPATCHED,
                expected_from=JobState.QUEUED,
            )
            self._outbox.mark_dispatched(session, record_id=record_id)
            session.commit()

    def _record_failure(self, record: ClaimedOutboxRecord, error: str, attempts: int) -> None:
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
        """
        with self._session_factory() as session:
            self._outbox.mark_failed(session, record_id=record.id, error=error, attempts=attempts)
            if attempts >= MAX_DISPATCH_ATTEMPTS:
                self._jobs.transition(
                    session,
                    tenant_id=record.tenant_id,
                    job_id=record.job_id,
                    to_state=JobState.FAILED_PROVIDER,
                    expected_from=JobState.QUEUED,
                )
            session.commit()
