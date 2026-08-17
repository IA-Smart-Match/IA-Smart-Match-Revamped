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
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from smartmatch_domain.jobs import JobState
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import DEFAULT_LEASE, OutboxRepository
from smartmatch_providers.tasks import (
    TaskAlreadyExists,
    TaskQueue,
    TaskQueueError,
    TaskRequest,
)
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["DispatchOutcome", "DispatcherLag", "OutboxDispatcher"]

logger = logging.getLogger(__name__)


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
        failed: Rows whose enqueue failed and will be retried after the lease
            expires, or parked once attempts are exhausted.
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
        """
        with self._session_factory() as session:
            claimed = self._outbox.claim_batch(session, limit=batch_size, lease=self._lease)
            # Commit so the lease is visible to other dispatchers before the slow
            # provider call below. Without this, a concurrent dispatcher could
            # claim the same rows.
            session.commit()

        if not claimed:
            return DispatchOutcome()

        dispatched = already_existed = failed = 0

        for record in claimed:
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
                outcome = "dispatched"
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
                self._record_failure(record.id, str(exc))
                failed += 1
                continue

            self._record_dispatched(record.tenant_id, record.job_id, record.id)
            if outcome == "dispatched":
                dispatched += 1
            else:
                already_existed += 1

        return DispatchOutcome(
            claimed=len(claimed),
            dispatched=dispatched,
            already_existed=already_existed,
            failed=failed,
        )

    def lag(self) -> DispatcherLag:
        """Measure how far behind dispatch has fallen."""
        with self._session_factory() as session:
            return DispatcherLag(
                pending=self._outbox.pending_count(session),
                oldest_age=self._outbox.oldest_pending_age(session),
            )

    # -- internals ---------------------------------------------------------

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

    def _record_failure(self, record_id: uuid.UUID, error: str) -> None:
        """Record a dispatch failure without touching the job's state.

        The job stays ``queued``: it has not been dispatched, and saying
        otherwise would strand it.
        """
        with self._session_factory() as session:
            self._outbox.mark_failed(session, record_id=record_id, error=error)
            session.commit()
