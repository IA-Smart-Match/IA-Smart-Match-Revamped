"""The ``attendance_record`` writer, for the coordinator route and the synthetic seed.

Two callers, and they arrived in that order for a reason worth keeping:

* ``services/api/smartmatch_api/routers/attendance.py`` — ``POST
  /v1/units/{unit_id}/events/{event_id}/attendance``, gated to ``{admin,
  coordinator}``, which fixes ``method`` to ``coordinator_entry`` and credits
  the points ADR-0013 derives from the row in the same transaction;
* the demo seed flow (``tools/seed_demo_pipeline.py``,
  ``tools/generate_pilot_dataset.py``), which is what this module was built
  for and still serves.

Either way it exists so the Attended funnel stage's own precondition —
``ck_pipeline_record_attendance_evidence``, ``(attended_at IS NULL) =
(attended_attendance_id IS NULL)`` — can be satisfied with a real
``attendance_record`` row, where "real" means "a row PostgreSQL actually
holds".

## The prohibition this module used to carry, and what replaced it

This docstring used to close: "no route imports this repository, and none
may". It was built under
`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`
§4 item 6.3 — "minimal synthetic writer for Attended-stage CHECK constraints
in demo seed flow" — and a route plainly exceeds that item. The reason the
sentence was there is **OQ-102** in
``docs/plans/open-questions/pipeline-stage-writers-deferred.md``:
``attendance_record`` is the only input to points, so whatever writes it is
also what mints student rewards, and how much a wrong row costs is a program
decision rather than a technical one.

That decision was taken on **7 September 2026 by Danny Tran, program owner of
record**, and the register carries its closure: the coordinator is the writer,
through the route above, with the scanner and roster-upload writers still
unbuilt. The ratified 3 September authorization is **not** edited — a ratified
record that quietly acquires a later exception stops being a record of what was
ratified — and this paragraph, with the register entry, is where the later
authority is written down instead. The sentence is retired rather than merely
contradicted, because code that disagrees with its own comments is worse than
either state alone.

**What this module is still not.** It is **not** a QR-code scanning path — no
scanner, camera, or device integration reaches this module, and it neither
generates nor validates a QR payload. It is **not** a live event check-in —
nothing here observes a real person walking into a real room; what it records
is a named coordinator's assertion that somebody was present. It is **not**
identity: it writes no account and links nobody to a unit.

Those are not claims on trust. ``tests/unit/test_checkin_wiring.py`` holds
them: the route's path carries none of that file's check-in markers, and the
API composition root is asserted — by import reachability in a fresh
interpreter, not by reading route names — never to import
:mod:`smartmatch_domain.checkin`. B08's check-in flow remains behind S11 and
D8, and nothing here advances it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final, cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "ATTENDANCE_METHODS",
    "AttendanceRepository",
    "AttendanceWriteResult",
    "ConflictingOwningUnitError",
]

#: ``attendance_record.method``'s closed vocabulary — mirrors
#: ``ck_attendance_record_method`` (migration ``0009``) exactly. Checked in
#: application code before any statement is issued, for the same reason
#: ``PipelineRepository.advance_stage`` checks its own preconditions first: a
#: caller gets a catchable ``ValueError`` naming the constraint rather than a
#: database round-trip that would only end in ``IntegrityError``.
ATTENDANCE_METHODS: Final[frozenset[str]] = frozenset({"qr_scan", "coordinator_entry", "import"})


class ConflictingOwningUnitError(ValueError):
    """An ``attendance_record`` already exists under a different ``owning_unit_id``.

    ``uq_attendance_record_subject_event`` — this module's idempotency key —
    is ``(tenant_id, subject_id, event_id)`` and does not cover
    ``owning_unit_id``, the same shape
    :class:`~smartmatch_persistence.pipeline.ConflictingOwningUnitError`
    documents itself with for ``pipeline_record``. A second call naming a
    different unit for the same subject and event would otherwise be
    silently absorbed by ``ON CONFLICT DO NOTHING``: the row stays scoped
    under the first unit and never the second, with no signal a caller could
    see from the returned id alone. Refused rather than accepted silently,
    per §1.10's standing rule that a silent zero — here, silently
    discarding a caller's differing ``owning_unit_id`` — is a defect.
    """


@dataclass(frozen=True, slots=True)
class AttendanceWriteResult:
    """What one :meth:`AttendanceRepository.record_attendance` call did.

    The id alone cannot answer the question a caller most needs answered,
    because it is the same id whether this call inserted the row or found one
    an earlier call wrote. A route above this repository has to tell those
    apart: a first recording is a ``201`` and a replay is a ``200``, and
    reporting a creation that did not happen would make the two
    indistinguishable to a client.

    Attributes:
        attendance_id: ``attendance_record.id`` for this
            ``(tenant_id, subject_id, event_id)``.
        created: Whether *this* call's insert is the one that wrote it. Read
            from ``RETURNING id`` on the ``ON CONFLICT DO NOTHING`` insert — a
            row comes back only when the insert won — so it is decided by the
            single statement that did or did not insert, never by a ``SELECT``
            beforehand that a concurrent writer could invalidate between the
            two questions. That is the discipline
            :meth:`~smartmatch_persistence.events.EventRepository.upsert_returning_outcome`
            already applies, for the same reason.
    """

    attendance_id: uuid.UUID
    created: bool


class AttendanceRepository:
    """Writes ``attendance_record`` rows.

    Takes a session per call, like every other repository in this package
    (``jobs.py``, ``review.py``, ``redrive.py``, ``pipeline.py``,
    ``professionals.py``): transaction boundaries belong to the caller, and
    this method does not commit.
    """

    def record_attendance(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_id: uuid.UUID,
        method: str,
    ) -> AttendanceWriteResult:
        """Record ``subject_id``'s attendance at ``event_id``, idempotently.

        ``ON CONFLICT`` targets ``uq_attendance_record_subject_event`` —
        ``(tenant_id, subject_id, event_id)`` — so a second call for the
        identical subject and event is a no-op, not a ``UniqueViolation``:
        the same idiom :meth:`~smartmatch_persistence.pipeline.PipelineRepository.record_matched`
        already establishes for ``pipeline_record``. Does not write
        ``created_at``, which carries a server default.

        Refuses an unknown ``method`` before issuing any statement — the
        application-code twin of ``ck_attendance_record_method``, checked
        here for the identical reason
        :meth:`~smartmatch_persistence.pipeline.PipelineRepository.advance_stage`
        checks its own preconditions before its ``UPDATE``.

        ``owning_unit_id`` is checked against the row's own value after the
        read-back, whether this call's insert won or an earlier call's did:
        the idempotency key above does not include it, so a second call
        naming a different unit for the same subject and event is refused
        rather than silently kept under the first unit — see
        :class:`ConflictingOwningUnitError`.

        Returns:
            An :class:`AttendanceWriteResult` carrying
            ``attendance_record.id`` — freshly inserted by this call, or the
            one an earlier call already wrote for this exact
            ``(tenant_id, subject_id, event_id)`` — and ``created``, which says
            which of those two it was.

        Raises:
            ValueError: ``method`` is not one of :data:`ATTENDANCE_METHODS`.
            ConflictingOwningUnitError: a row already exists for this
                ``(tenant_id, subject_id, event_id)`` under a different
                ``owning_unit_id``.
            RuntimeError: the read-back after the insert found no row. This
                should be unreachable — the insert above is either the row
                that now exists or lost its own ``ON CONFLICT`` to one that
                does, so a row must be there either way — and is raised
                explicitly, not asserted, mirroring
                :meth:`~smartmatch_persistence.pipeline.PipelineRepository.record_matched`'s
                own unreachable branch: an ``assert`` is compiled out under
                ``python -O``, which would silently return ``None`` from a
                method typed to return an :class:`AttendanceWriteResult`.
        """
        if method not in ATTENDANCE_METHODS:
            raise ValueError(
                f"method must be one of {sorted(ATTENDANCE_METHODS)}, not {method!r} "
                "(ck_attendance_record_method)"
            )

        # `RETURNING id` on an `ON CONFLICT DO NOTHING` insert yields a row
        # only when the insert actually happened, so `inserted is not None` is
        # this call's own answer to "did I write it" — decided inside the one
        # statement that decided, with no window between two questions for a
        # concurrent writer to slip through.
        inserted = session.execute(
            postgresql.insert(schema.attendance_record)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                subject_id=subject_id,
                event_id=event_id,
                method=method,
            )
            .on_conflict_do_nothing(constraint="uq_attendance_record_subject_event")
            .returning(schema.attendance_record.c.id)
        ).scalar_one_or_none()
        row = session.execute(
            sa.select(
                schema.attendance_record.c.id, schema.attendance_record.c.owning_unit_id
            ).where(
                schema.attendance_record.c.tenant_id == tenant_id,
                schema.attendance_record.c.subject_id == subject_id,
                schema.attendance_record.c.event_id == event_id,
            )
        ).one_or_none()
        if row is None:
            # Unreachable: the insert above is either the row that now
            # exists or lost an ON CONFLICT to one that does — either way a
            # row must be there. Not asserted — see this method's own
            # docstring for why.
            raise RuntimeError(
                f"no attendance_record found for tenant {tenant_id}, subject {subject_id}, "
                f"event {event_id} immediately after an insert targeting that exact key "
                "— this should be unreachable"
            )
        if row.owning_unit_id != owning_unit_id:
            raise ConflictingOwningUnitError(
                f"attendance_record {row.id} already exists for tenant {tenant_id}, subject "
                f"{subject_id}, event {event_id} under owning unit {row.owning_unit_id}, not "
                f"the {owning_unit_id} this call named"
            )
        return AttendanceWriteResult(
            attendance_id=cast(uuid.UUID, row.id), created=inserted is not None
        )
