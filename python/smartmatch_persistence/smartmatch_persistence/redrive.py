"""Parked-work repository: the dead-letter queue Cloud Tasks does not have.

Architecture v1.1 §1.6. Cloud Tasks offers no native dead-letter queue, so work
that fails terminally does not disappear into a queue nobody reads — it parks in
``redrive_record``, and restarting it is an explicit command that names an actor
and a reason. ``dead_letter``, the v1.0 state this replaces, was a label with no
recorded decision behind it: nothing said who had decided to re-run the work, or
why, or how many times it had already failed.

## Three properties this module exists to hold

**Re-drive must actually re-drive.** The hard part is not the row; it is the
task name. ``derive_task_name`` was a pure function of ``(job_id, command_type)``
(ADR-0007), so re-driving a job under its own identifiers derived the name its
own failed attempt already used. ``uq_outbox_task_name`` is global, so
PostgreSQL refuses the second outbox row outright; and even past the database,
Cloud Tasks rejects a duplicate name and the dispatcher counts that rejection as
*success* — the row is marked ``dispatched``, the job advances, and the work
never runs. A re-drive that produced an audit record and no execution would be
worse than one that failed loudly.

The fix is the ``redrive_generation`` this module passes to
:meth:`~smartmatch_persistence.outbox.OutboxRepository.enqueue`: the count of
outbox rows the job already has. Each deliberate re-drive is a new generation
and therefore a new name; every *accidental* repeat — the dispatcher retrying
one dispatch after an ambiguous enqueue — stays within a generation and keeps
the identical name ADR-0007 depends on. The dispatcher never derives a name at
all; it reads the one stored on the row it claimed.

**Attempt history accumulates and is never overwritten.** Each parking opens its
own ``redrive_record``, and operator decisions are written with
``attempt_history = attempt_history || …`` — appended in SQL, so there is no
statement in this module capable of dropping an earlier entry. A new parking
carries every earlier decision forward and rebuilds the per-attempt entries from
the outbox, which is the authoritative record of what was dispatched. The
question an operator actually asks — "how many times has this failed, and on
what?" — is answerable from the newest record alone.

**A re-drive cannot double-run.** The move out of ``redrive_pending`` is a
compare-and-set on the job row (``REDRIVE_PENDING -> QUEUED``, conditional on
the job still being ``redrive_pending``). Two coordinators pressing the button
generate two different idempotency keys, so keys cannot arbitrate this; the job
state can, and does. The loser is refused rather than queuing a second run.

Transitions are never invented here. ``FAILED_PROVIDER -> REDRIVE_PENDING``,
``TIMED_OUT -> REDRIVE_PENDING``, ``REDRIVE_PENDING -> QUEUED`` and
``REDRIVE_PENDING -> ABANDONED`` are declared in
:mod:`smartmatch_domain.jobs`, and :func:`~smartmatch_domain.jobs.assert_transition`
is what rejects a job in any other state — so "is this job re-drivable?" has one
answer, held in the domain, rather than a second copy here that could drift.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from smartmatch_domain.jobs import JobState, assert_transition
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import OutboxRepository

__all__ = [
    "ParkedRecord",
    "RedriveConflictError",
    "RedriveOutcome",
    "RedriveRepository",
]

#: Entry kinds in ``attempt_history``. ``attempt`` entries are rebuilt from the
#: outbox at every parking, because the outbox is what actually dispatched;
#: everything else is a human decision and is carried forward verbatim.
_ATTEMPT_EVENT: Final[str] = "attempt"


class RedriveConflictError(RuntimeError):
    """Another actor moved the job before this command could complete.

    Distinct from an illegal transition. The caller's request was legal when it
    was checked and lost a race — a 409 either way at the edge, but only this one
    means "try again and you may well succeed".
    """


@dataclass(frozen=True, slots=True)
class ParkedRecord:
    """One parking of one job, with everything known about it at that point."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    job_id: uuid.UUID
    attempt_history: list[dict[str, Any]]
    parked_at: datetime
    redriven_at: datetime | None
    redriven_by: uuid.UUID | None
    redrive_reason: str | None

    @property
    def is_open(self) -> bool:
        """Whether this parking is still awaiting a decision.

        Two ways a parking is closed, and only one of them has a column. A
        re-drive stamps ``redriven_at``; an abandonment cannot, because
        ``redriven_at``/``redriven_by``/``redrive_reason`` mean *re-driven* and
        borrowing them would make ``WHERE redriven_at IS NOT NULL`` count
        abandonments as re-runs. So an abandonment is recorded in the history,
        and this reads both — otherwise an abandoned parking would look open
        forever and the next decision would be stamped onto it.
        """
        if self.redriven_at is not None:
            return False
        return not any(entry.get("event") == "abandoned" for entry in self.attempt_history)


@dataclass(frozen=True, slots=True)
class RedriveOutcome:
    """What a completed re-drive produced.

    Attributes:
        record_id: The audit record stamped with the actor and reason.
        generation: Which dispatch of this job the re-drive created. ``1`` is
            the first re-drive; generation ``0`` was the original submission.
        task_name: The name of the task the dispatcher will create. Recorded in
            the audit trail so a re-drive can be tied to the task that ran, and
            distinct from every earlier generation's name — which is the whole
            reason a re-drive reaches the queue at all.
    """

    record_id: uuid.UUID
    generation: int
    task_name: str


class RedriveRepository:
    """Parks terminally-failed jobs and restarts them under audit.

    Takes a session per call, like every other repository here: parking, the
    state transition, the new outbox row and the audit stamp all belong to the
    caller's single transaction. A re-drive that committed the outbox row but not
    the audit record would be work nobody authorized, and one that committed the
    audit record but not the outbox row would be an audit trail describing work
    that never ran.
    """

    def __init__(self) -> None:
        self._jobs = JobRepository()
        self._outbox = OutboxRepository()

    # -- commands ----------------------------------------------------------

    def redrive(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
        now: datetime | None = None,
    ) -> RedriveOutcome:
        """Re-queue a parked job as a new, genuinely dispatchable attempt.

        Parks the job first when it is still sitting in a terminal failure state,
        so an operator does not have to perform a two-step ritual to restart work
        that plainly failed. Both moves are declared transitions; neither is
        invented here.

        Does not commit — the caller owns the transaction.

        Args:
            actor_id: The authenticated caller. Required: an anonymous re-drive
                is not auditable, and the column pairs with ``redriven_at`` under
                a CHECK constraint precisely so half an attribution cannot be
                written.
            reason: Why this work is being re-run. Required for the same reason.

        Returns:
            A :class:`RedriveOutcome` naming the new generation and task name.

        Raises:
            InvalidTransitionError: when the job is in a state the domain does
                not route into ``redrive_pending`` — the rejection path for a
                job that is not re-drivable at all.
            RedriveConflictError: when another actor moved the job first.
            ValueError: on a blank reason.
        """
        moment = now or datetime.now(UTC)
        reason = _require_reason(reason)
        record_id = self._open_parking(session, tenant_id, job_id, moment)

        if not self._jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.QUEUED,
            expected_from=JobState.REDRIVE_PENDING,
        ):
            raise RedriveConflictError(
                f"job {job_id} was moved by another actor before this re-drive "
                "could re-queue it; nothing was re-driven"
            )

        command_type = self._command_type(session, tenant_id, job_id)
        generation = self._next_generation(session, tenant_id, job_id)
        task_name = self._outbox.enqueue(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            command_type=command_type,
            redrive_generation=generation,
        )

        self._append(
            session,
            record_id=record_id,
            entry={
                "event": "redriven",
                "at": moment.isoformat(),
                "actor_id": str(actor_id),
                "reason": reason,
                "generation": generation,
                "task_name": task_name,
            },
            columns={
                "redriven_at": moment,
                "redriven_by": actor_id,
                "redrive_reason": reason,
            },
        )

        return RedriveOutcome(record_id=record_id, generation=generation, task_name=task_name)

    def abandon(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
        now: datetime | None = None,
    ) -> uuid.UUID:
        """Close a parked job permanently: this will never work, stop showing it.

        The counterpart to :meth:`redrive`, and the reason
        ``REDRIVE_PENDING -> ABANDONED`` exists. Without it a job that genuinely
        cannot succeed stays in the operations view forever, and a queue of
        undismissable items is a queue people stop reading — which costs
        attention on the items that *are* actionable.

        The decision is appended to ``attempt_history`` with its actor and
        reason. It is deliberately **not** written to ``redriven_at`` /
        ``redriven_by`` / ``redrive_reason``: abandoning is not re-driving, and
        borrowing those columns would make ``WHERE redriven_at IS NOT NULL``
        count abandonments as re-runs. See the module note in the router about
        the schema gap this leaves.

        Returns:
            The audit record's id.

        Raises:
            InvalidTransitionError: when the job cannot reach ``redrive_pending``.
            RedriveConflictError: when another actor moved the job first.
            ValueError: on a blank reason.
        """
        moment = now or datetime.now(UTC)
        reason = _require_reason(reason)
        record_id = self._open_parking(session, tenant_id, job_id, moment)

        if not self._jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.ABANDONED,
            expected_from=JobState.REDRIVE_PENDING,
        ):
            raise RedriveConflictError(
                f"job {job_id} was moved by another actor before it could be abandoned"
            )

        self._append(
            session,
            record_id=record_id,
            entry={
                "event": "abandoned",
                "at": moment.isoformat(),
                "actor_id": str(actor_id),
                "reason": reason,
            },
        )
        return record_id

    # -- reads -------------------------------------------------------------

    def history(
        self, session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> list[ParkedRecord]:
        """Every parking of this job, oldest first.

        Scoped by ``tenant_id`` in the query rather than filtered afterwards, so
        one tenant's parked work is not reachable by guessing another's job id.
        """
        rows = session.execute(
            sa.select(schema.redrive_record)
            .where(
                schema.redrive_record.c.tenant_id == tenant_id,
                schema.redrive_record.c.job_id == job_id,
            )
            .order_by(schema.redrive_record.c.parked_at, schema.redrive_record.c.id)
        ).all()

        return [
            ParkedRecord(
                id=row.id,
                tenant_id=row.tenant_id,
                job_id=row.job_id,
                attempt_history=list(row.attempt_history),
                parked_at=row.parked_at,
                redriven_at=row.redriven_at,
                redriven_by=row.redriven_by,
                redrive_reason=row.redrive_reason,
            )
            for row in rows
        ]

    # -- internals ---------------------------------------------------------

    def _open_parking(
        self, session: Session, tenant_id: uuid.UUID, job_id: uuid.UUID, moment: datetime
    ) -> uuid.UUID:
        """Return the id of the audit record this decision belongs to.

        Three cases, and the third is why this is not simply "insert a row":

        * The job still sits in a terminal failure. Park it — a declared
          transition — and open a record.
        * The job is already ``redrive_pending`` with an open record, because a
          previous decision parked it. Use that record.
        * The job is ``redrive_pending`` with **no** open record. Something moved
          it there without writing one; the worker owns that transition and need
          not know this table exists. Backfilling a record here is better than
          refusing: the alternative is a job an operator can see and cannot act
          on, and the record honestly says the attempt evidence was collected at
          this moment rather than at the parking.
        """
        job = self._jobs.get(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            raise RedriveConflictError(f"job {job_id} no longer exists in tenant {tenant_id}")

        if job.status is not JobState.REDRIVE_PENDING:
            # Raises InvalidTransitionError for every state the domain refuses to
            # route into redrive_pending — succeeded, cancelled, abandoned, and
            # everything still in flight. This is the rejection path for a job
            # that is not re-drivable, and it is the domain's answer, not ours.
            assert_transition(job.status, JobState.REDRIVE_PENDING)

            parked_from = job.status
            if not self._jobs.transition(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                to_state=JobState.REDRIVE_PENDING,
                expected_from=parked_from,
            ):
                raise RedriveConflictError(
                    f"job {job_id} left {parked_from.value!r} before it could be parked"
                )
            return self._insert_record(session, tenant_id, job_id, parked_from, moment)

        for record in reversed(self.history(session, tenant_id=tenant_id, job_id=job_id)):
            if record.is_open:
                return record.id

        return self._insert_record(session, tenant_id, job_id, JobState.REDRIVE_PENDING, moment)

    def _insert_record(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        parked_from: JobState,
        moment: datetime,
    ) -> uuid.UUID:
        """Open an audit record for this parking, seeded with the full history.

        The seed is every earlier *decision* on this job, carried forward
        verbatim, plus a freshly rebuilt entry per outbox row. Decisions are
        carried rather than re-derived because nothing else records them;
        attempts are rebuilt rather than carried because the outbox is what
        actually dispatched, and a copy of it could go stale.

        Entries are sorted by their timestamp, so the column reads as one
        chronological narrative — "queued, dispatched, failed, re-driven by X
        because Y, dispatched again, failed again" — rather than as two
        interleaved logs an operator has to merge in their head.
        """
        # Only the **most recent** record is carried, not every record.
        #
        # Each record was itself seeded this way, so the latest one already
        # contains every decision made before it. Concatenating all of them
        # re-adds each earlier decision once per record that already carried it,
        # and the column grows super-linearly with duplicate entries: three
        # re-drive cycles produced 3, then 6, then 11 entries, with the first
        # parking appearing twice by the third. A two-cycle test does not reach
        # it, which is why it survived one.
        previous = self.history(session, tenant_id=tenant_id, job_id=job_id)
        carried = [
            entry
            for entry in (previous[-1].attempt_history if previous else [])
            if entry.get("event") != _ATTEMPT_EVENT
        ]
        entries = carried + self._attempt_entries(session, tenant_id, job_id)
        entries.append(
            {
                "event": "parked",
                "at": moment.isoformat(),
                "from_state": parked_from.value,
            }
        )
        entries.sort(key=lambda entry: str(entry.get("at", "")))

        record_id = uuid.uuid4()
        session.execute(
            sa.insert(schema.redrive_record).values(
                id=record_id,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_history=entries,
                parked_at=moment,
            )
        )
        return record_id

    def _attempt_entries(
        self, session: Session, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Rebuild one history entry per dispatch this job has had.

        Read from the outbox rather than from job events: the outbox is the
        durable record of *dispatch*, carries the task name that ties an attempt
        to the queue, and holds ``last_error`` — which is the field an operator
        reads before deciding whether re-driving is worth anything.
        """
        rows = session.execute(
            sa.select(
                schema.outbox_record.c.task_name,
                schema.outbox_record.c.status,
                schema.outbox_record.c.dispatch_attempts,
                schema.outbox_record.c.last_error,
                schema.outbox_record.c.created_at,
            )
            .where(
                schema.outbox_record.c.tenant_id == tenant_id,
                schema.outbox_record.c.job_id == job_id,
            )
            .order_by(schema.outbox_record.c.created_at, schema.outbox_record.c.task_name)
        ).all()

        return [
            {
                "event": _ATTEMPT_EVENT,
                "at": row.created_at.isoformat(),
                "generation": generation,
                "task_name": row.task_name,
                "outbox_status": row.status,
                "dispatch_attempts": row.dispatch_attempts,
                "last_error": row.last_error,
            }
            for generation, row in enumerate(rows)
        ]

    def _append(
        self,
        session: Session,
        *,
        record_id: uuid.UUID,
        entry: dict[str, Any],
        columns: dict[str, Any] | None = None,
    ) -> None:
        """Append one entry to a record's history, and stamp any audit columns.

        The append is ``attempt_history || :entry`` in SQL, not read-modify-write
        in Python. That is deliberate: there is no code path here that *can*
        overwrite an earlier entry, and no lost update if two statements ever
        touch the same record. History that a bug could silently truncate is not
        history — the entire value of this column is being able to see that
        something failed four times, not just that it failed.
        """
        addition = schema.redrive_record.c.attempt_history.op("||", return_type=postgresql.JSONB)(
            sa.cast(sa.literal(json.dumps([entry])), postgresql.JSONB)
        )
        session.execute(
            sa.update(schema.redrive_record)
            .where(schema.redrive_record.c.id == record_id)
            .values(attempt_history=addition, **(columns or {}))
        )

    def _command_type(self, session: Session, tenant_id: uuid.UUID, job_id: uuid.UUID) -> str:
        """Read the job's command type, which the task name is derived from."""
        job = self._jobs.get(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:  # pragma: no cover - the caller has just transitioned it
            raise RedriveConflictError(f"job {job_id} vanished mid-re-drive")
        return job.command_type

    def current_generation(self, session: Session, tenant_id: uuid.UUID, job_id: uuid.UUID) -> int:
        """The generation of this job's most recent dispatch.

        ``0`` while the job has only its original submission; ``n`` once ``n``
        re-drives have been recorded.

        Exists for the idempotent replay path, which answers a repeated request
        identically to the first. "Identically" has to include the generation:
        reporting the default ``0`` there would tell the caller their re-drive
        was the original submission, which is the one thing it is not.
        """
        return max(0, self._next_generation(session, tenant_id, job_id) - 1)

    def _next_generation(self, session: Session, tenant_id: uuid.UUID, job_id: uuid.UUID) -> int:
        """How many times this job has already been enqueued.

        Counted from the outbox rather than from the re-drive records, because
        the outbox is exactly the table whose ``uq_outbox_task_name`` the derived
        name must not collide with. Generations ``0 … n-1`` already have rows, so
        ``n`` is free — and if a re-drive record were ever written without its
        outbox row, or vice versa, this counts the thing that matters.

        Two concurrent re-drives could read the same count, but cannot both use
        it: the ``REDRIVE_PENDING -> QUEUED`` compare-and-set lets exactly one
        proceed, and ``uq_outbox_task_name`` is the backstop if that ever failed.
        """
        return int(
            session.execute(
                sa.select(sa.func.count())
                .select_from(schema.outbox_record)
                .where(
                    schema.outbox_record.c.tenant_id == tenant_id,
                    schema.outbox_record.c.job_id == job_id,
                )
            ).scalar_one()
        )


def _require_reason(reason: str) -> str:
    """Return the trimmed reason, or refuse.

    Enforced here as well as at the edge because the audit value of the column is
    the entire justification for the command existing. A repository that accepted
    ``""`` would let a future caller write an unattributable decision without
    touching this file.
    """
    trimmed = reason.strip()
    if not trimmed:
        raise ValueError("a re-drive decision must record why it was made")
    return trimmed
