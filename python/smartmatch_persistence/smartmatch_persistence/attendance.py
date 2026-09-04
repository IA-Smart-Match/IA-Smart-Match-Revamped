"""The minimal ``attendance_record`` writer the synthetic pilot authorization allows.

`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`
§4 item 6.3 authorizes an ``attendance_record`` write path: "minimal
synthetic writer for Attended-stage CHECK constraints in demo seed flow."
This module is exactly that, and nothing more. It exists so that the
Attended funnel stage's own precondition —
``ck_pipeline_record_attendance_evidence``,
``(attended_at IS NULL) = (attended_attendance_id IS NULL)`` — can be
satisfied with a real ``attendance_record`` row in a demo seed flow, where
"real" means "a row PostgreSQL actually holds", not "produced by a live
attendance-taking event".

**What this module is not.** It is **not** a QR-code scanning path — no
scanner, camera, or device integration reaches this module, and it neither
generates nor validates a QR payload. It is **not** a live event check-in —
nothing here observes a real person walking into a real room. It is **not**
an engagement API: ``services/api/smartmatch_api/routers/engagement.py``
remains a declared-empty stub (its own module docstring: "This module
deliberately declares no handlers yet"), and this module gives it nothing —
no route imports this repository, and none may.
"""

from __future__ import annotations

import uuid
from typing import Final, cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["ATTENDANCE_METHODS", "AttendanceRepository", "ConflictingOwningUnitError"]

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
    ) -> uuid.UUID:
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
            ``attendance_record.id`` — freshly inserted by this call, or the
            one an earlier call already wrote for this exact
            ``(tenant_id, subject_id, event_id)``.

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
                method typed to return ``uuid.UUID``.
        """
        if method not in ATTENDANCE_METHODS:
            raise ValueError(
                f"method must be one of {sorted(ATTENDANCE_METHODS)}, not {method!r} "
                "(ck_attendance_record_method)"
            )

        session.execute(
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
        )
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
        return cast(uuid.UUID, row.id)
