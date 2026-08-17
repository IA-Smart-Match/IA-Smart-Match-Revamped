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


def derive_task_name(job_id: uuid.UUID, command_type: str) -> str:
    """Derive a deterministic Cloud Tasks task name.

    Determinism is the dedupe mechanism: Cloud Tasks rejects a task whose name
    already exists, so a retried dispatch after an ambiguous failure cannot
    enqueue the work a second time. A random name would silently double-execute
    in exactly the case retries exist to handle.

    The name is a hash rather than the raw job id so it carries no tenant or
    command information into the queue's metadata, which is visible in Cloud
    Console to anyone with queue-viewer access.
    """
    digest = hashlib.sha256(f"{job_id}|{command_type}".encode()).hexdigest()[:40]
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
    ) -> str:
        """Record the intent to dispatch a job. Does not commit.

        Must be called inside the same transaction that inserted the job. The
        caller commits both at once; there is no valid state in which a job
        exists without its outbox row.

        Returns:
            The deterministic task name that will be used for this job.
        """
        task_name = derive_task_name(job_id, command_type)

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

        Args:
            now: Injected for tests so lease expiry is exercised without waiting.

        Returns:
            The claimed rows, at most ``limit`` of them. Does not commit — the
            caller commits to make the lease visible, then dispatches.
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
            )
        ).all()

        return [
            ClaimedOutboxRecord(
                id=row.id,
                tenant_id=row.tenant_id,
                job_id=row.job_id,
                task_name=row.task_name,
                dispatch_attempts=row.dispatch_attempts,
                lease_expires_at=row.lease_expires_at,
            )
            for row in rows
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

    def mark_failed(self, session: Session, *, record_id: uuid.UUID, error: str) -> None:
        """Record a dispatch failure.

        While attempts remain the row returns to ``pending`` and its lease is
        cleared, so the next poll retries it immediately rather than waiting out
        a lease that no longer protects anything — the dispatcher that held it
        has already finished with it.

        Returning it to ``pending`` rather than leaving it ``leased`` matters:
        the claim predicate matches a leased row only when
        ``lease_expires_at < now``, and a NULL lease never satisfies that
        comparison. A leased row with a cleared lease would be permanently
        unclaimable — invisible work, silently stuck.

        Once attempts are exhausted the row becomes ``failed``: no longer
        claimable, and visible in the operations view rather than looping.
        """
        session.execute(
            sa.update(schema.outbox_record)
            .where(schema.outbox_record.c.id == record_id)
            .values(
                status=sa.case(
                    (
                        schema.outbox_record.c.dispatch_attempts >= MAX_DISPATCH_ATTEMPTS,
                        OutboxStatus.FAILED.value,
                    ),
                    else_=OutboxStatus.PENDING.value,
                ),
                lease_expires_at=None,
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
