"""Job and job-event repository.

Architecture v1.1 §1.6 and §1.7. Two properties matter here and are tested
against a real database:

* **State transitions are validated against the domain state machine** before
  they are written, and the database's own CHECK constraint is the backstop.
* **Claiming a job is atomic.** ``claim`` moves ``dispatched -> running`` with a
  conditional UPDATE, so a duplicate Cloud Tasks delivery finds zero rows
  matching and does not double-execute. Cloud Tasks guarantees at-least-once
  delivery, which makes this the load-bearing check, not a nicety.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.jobs import JobState, assert_transition
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["JobEventRecord", "JobRecord", "JobRepository"]


@dataclass(frozen=True, slots=True)
class JobRecord:
    """A durable job."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    command_type: str
    status: JobState
    actor_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class JobEventRecord:
    """One entry in a job's event stream."""

    job_id: uuid.UUID
    sequence: int
    payload: dict[str, Any]
    created_at: datetime


class JobRepository:
    """Reads and writes jobs and their event streams.

    The repository takes a :class:`~sqlalchemy.orm.Session` per call rather than
    holding one. Transaction boundaries belong to the caller: the API needs the
    idempotency check, the job row, and the outbox row in *one* transaction
    (v1.1 §1.6), and a repository that opened its own could not provide that.
    """

    def create(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        command_type: str,
        actor_id: uuid.UUID | None = None,
        deadline: datetime | None = None,
        job_id: uuid.UUID | None = None,
    ) -> JobRecord:
        """Insert a job in ``queued``.

        Does not commit. The caller commits once, with the outbox row, so a
        crash can never leave a job with no outbox entry to dispatch it.
        """
        job_id = job_id or uuid.uuid4()
        now = datetime.now(UTC)

        session.execute(
            sa.insert(schema.job).values(
                id=job_id,
                tenant_id=tenant_id,
                command_type=command_type,
                status=JobState.QUEUED.value,
                actor_id=actor_id,
                deadline=deadline,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )

        return JobRecord(
            id=job_id,
            tenant_id=tenant_id,
            command_type=command_type,
            status=JobState.QUEUED,
            actor_id=actor_id,
            created_at=now,
            updated_at=now,
        )

    def get(self, session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> JobRecord | None:
        """Fetch one job, scoped to its tenant.

        ``tenant_id`` is part of the lookup, not a filter applied afterwards, so
        a caller cannot accidentally read another tenant's job by id.
        """
        row = session.execute(
            sa.select(schema.job).where(
                schema.job.c.tenant_id == tenant_id, schema.job.c.id == job_id
            )
        ).one_or_none()

        if row is None:
            return None
        return _to_job_record(row)

    def transition(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        to_state: JobState,
        expected_from: JobState | None = None,
    ) -> bool:
        """Move a job to ``to_state``, validating the transition first.

        Args:
            expected_from: When given, the UPDATE additionally requires the row
                to still be in this state. That makes the move a compare-and-set
                and is how concurrent workers are prevented from both advancing
                the same job.

        Returns:
            ``True`` if a row was updated. ``False`` means another actor moved
            the job first — a normal race outcome, not an error.

        Raises:
            InvalidTransitionError: if the transition is illegal per the domain
                state machine. Validated before touching the database so an
                illegal move is a programming error surfaced in the caller's
                stack, not a constraint violation surfaced in the driver's.
        """
        if expected_from is not None:
            assert_transition(expected_from, to_state)

        conditions = [
            schema.job.c.tenant_id == tenant_id,
            schema.job.c.id == job_id,
        ]
        if expected_from is not None:
            conditions.append(schema.job.c.status == expected_from.value)

        # Returning the id rather than reading ``rowcount`` keeps this typed and
        # portable: ``rowcount`` lives on CursorResult, which ``Session.execute``
        # is not statically known to produce.
        updated = session.execute(
            sa.update(schema.job)
            .where(*conditions)
            .values(
                status=to_state.value,
                updated_at=datetime.now(UTC),
                version=schema.job.c.version + 1,
            )
            .returning(schema.job.c.id)
        ).one_or_none()

        return updated is not None

    def claim(self, session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> bool:
        """Claim a dispatched job for execution.

        This is the guard against double execution. Cloud Tasks delivers
        at-least-once, so the same task can arrive twice; only the delivery whose
        conditional UPDATE matches a ``dispatched`` row proceeds. The second
        finds zero rows and returns ``False``, and the worker acknowledges it
        without re-running the work.
        """
        return self.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.RUNNING,
            expected_from=JobState.DISPATCHED,
        )

    def append_event(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> JobEventRecord:
        """Append an event, assigning the next sequence number for this job.

        The sequence is computed inside the statement
        (``SELECT coalesce(max(sequence), 0) + 1``) rather than read and then
        written, so two concurrent appends cannot both compute the same number.
        If they race, the ``(job_id, sequence)`` unique constraint rejects the
        loser and the caller retries — which is correct, and cheaper than
        serializing every append behind a lock.
        """
        next_sequence = (
            sa.select(sa.func.coalesce(sa.func.max(schema.job_event.c.sequence), 0) + 1)
            .where(schema.job_event.c.job_id == job_id)
            .scalar_subquery()
        )

        row = session.execute(
            sa.insert(schema.job_event)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                job_id=job_id,
                sequence=next_sequence,
                payload=payload,
            )
            .returning(
                schema.job_event.c.sequence,
                schema.job_event.c.created_at,
            )
        ).one()

        return JobEventRecord(
            job_id=job_id,
            sequence=row.sequence,
            payload=payload,
            created_at=row.created_at,
        )

    def latest_sequence(self, session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> int:
        """Return the highest event sequence for a job, or 0 when it has none.

        Lets a status response tell a client where to resume from without
        shipping the whole event history alongside it.
        """
        highest: int | None = session.execute(
            sa.select(sa.func.max(schema.job_event.c.sequence)).where(
                schema.job_event.c.tenant_id == tenant_id,
                schema.job_event.c.job_id == job_id,
            )
        ).scalar_one_or_none()
        return highest or 0

    def events_since(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[JobEventRecord]:
        """Read events after ``after_sequence``, oldest first.

        This is the single source for both SSE and polling (v1.1 §1.6): an SSE
        reconnect passes ``Last-Event-ID`` as ``after_sequence`` and a polling
        client reads the same rows, so the two cannot disagree.
        """
        rows = session.execute(
            sa.select(schema.job_event)
            .where(
                schema.job_event.c.tenant_id == tenant_id,
                schema.job_event.c.job_id == job_id,
                schema.job_event.c.sequence > after_sequence,
            )
            .order_by(schema.job_event.c.sequence)
            .limit(limit)
        ).all()

        return [
            JobEventRecord(
                job_id=row.job_id,
                sequence=row.sequence,
                payload=row.payload,
                created_at=row.created_at,
            )
            for row in rows
        ]


def _to_job_record(row: sa.Row[Any]) -> JobRecord:
    return JobRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        command_type=row.command_type,
        status=JobState(row.status),
        actor_id=row.actor_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
