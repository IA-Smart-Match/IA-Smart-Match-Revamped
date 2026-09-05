"""Read-only aggregates over ``attendance_record`` for one org unit.

The counting half of the R2 engagement surface. Migration ``0009`` created
``attendance_record``;
:class:`~smartmatch_persistence.attendance.AttendanceRepository` writes rows
into it under the synthetic-pilot authorization; this module reads them back as
*counts*, and :func:`smartmatch_domain.attendance.summarize_attendance` folds
those counts into the object a response carries.

## Why a separate module from ``attendance.py``

``attendance.py``'s own docstring states its scope narrowly and closes it: "It
is **not** an engagement API: ``routers/engagement.py`` ... gives it nothing —
no route imports this repository, and none may." That sentence is still true
after this module exists, and it stays true precisely because the reader lives
here. Widening the synthetic writer into something a route calls would have
retracted the sentence rather than honoured it, and the two have genuinely
different exposure: one is reachable only from a seed script, the other from an
authenticated HTTP read.

## No row this module returns names a person

Every method returns counts. ``subject_id`` and ``event_id`` are counted with
``count(distinct ...)`` inside the database and never selected, so there is no
projection through which a student identifier could reach a caller — which is
the property that lets this surface exist while **D8**, the disclosure-consent
policy, is still open (``docs/architecture/engagement-model.md`` §8). It is a
structural guarantee rather than a filter the router is trusted to apply.

## Scoped by ``owning_unit_id``, and by tenant, in the query itself

``attendance_record.owning_unit_id`` is A5-shaped and populated at write time
(migration ``0009``), so a unit-scoped count is a ``WHERE`` clause over a column
this table already carries rather than a join back through ``event``. Both
predicates are in the ``WHERE``: a caller cannot ask for one unit and be
answered about another, and cross-tenant reach is refused by the query and not
only by the route that calls it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["AttendanceCounts", "EngagementRepository"]


@dataclass(frozen=True, slots=True)
class AttendanceCounts:
    """What the database counted, before the domain folds it.

    Deliberately *not* :class:`~smartmatch_domain.attendance.AttendanceSummary`:
    this is the raw reading, with ``method_counts`` carrying only the methods
    that actually occur, and the summary is what completes the vocabulary and
    sums the total. Keeping them apart is what makes the fold a function of the
    reading rather than a rearrangement of a summary the storage layer already
    decided.

    Attributes:
        method_counts: ``attendance_record.method`` -> row count, for the
            methods present. A method with no rows is absent here.
        distinct_subjects: ``count(distinct subject_id)`` over the same rows.
        distinct_events: ``count(distinct event_id)`` over the same rows.
        first_recorded_at: ``min(created_at)``, or ``None`` for no rows.
        last_recorded_at: ``max(created_at)``, or ``None`` for no rows.
    """

    method_counts: Mapping[str, int]
    distinct_subjects: int
    distinct_events: int
    first_recorded_at: datetime | None
    last_recorded_at: datetime | None


class EngagementRepository:
    """Reads ``attendance_record`` aggregates. Writes nothing, by construction.

    Takes a session per call, like every other repository in this package: the
    transaction boundary belongs to the caller. There is no writer here and no
    method that issues anything but a ``SELECT`` — an engagement *command*
    surface is B08's, and B08 is blocked on S11 and D8.
    """

    def attendance_counts_for_unit(
        self, session: Session, *, tenant_id: uuid.UUID, owning_unit_id: uuid.UUID
    ) -> AttendanceCounts:
        """Count one unit's attendance evidence, three ways, in two statements.

        The first statement groups by ``method``; the second takes the distinct
        subject and event counts and the two ``created_at`` bounds over the same
        predicate. Two statements rather than one because the per-method
        breakdown and the distinct counts aggregate at different grains —
        ``count(distinct subject_id)`` *within* each method group would answer a
        different question than the unit-wide figure a summary reports, and
        deriving one from the other is exactly the arithmetic
        :mod:`smartmatch_domain.attendance` exists to keep honest.

        A unit with no attendance rows is a measured zero, not an absence: the
        aggregates return ``0`` and two ``None`` bounds, and
        :func:`~smartmatch_domain.attendance.summarize_attendance` accepts that
        combination as consistent. Nothing here distinguishes "no rows" from "no
        such unit" — that is the route's job, and it is why the route loads the
        unit through ``load_unit_or_404`` before calling this at all.

        Args:
            session: The caller's session. Not committed here.
            tenant_id: The caller's own tenant, from the verified principal.
            owning_unit_id: The unit the caller was authorized against.

        Returns:
            The :class:`AttendanceCounts` for that tenant and unit.
        """
        attendance = schema.attendance_record
        scope = (
            attendance.c.tenant_id == tenant_id,
            attendance.c.owning_unit_id == owning_unit_id,
        )

        grouped = session.execute(
            sa.select(attendance.c.method, sa.func.count().label("rows"))
            .where(*scope)
            .group_by(attendance.c.method)
        ).all()

        totals = session.execute(
            sa.select(
                sa.func.count(sa.distinct(attendance.c.subject_id)).label("subjects"),
                sa.func.count(sa.distinct(attendance.c.event_id)).label("events"),
                sa.func.min(attendance.c.created_at).label("first_recorded_at"),
                sa.func.max(attendance.c.created_at).label("last_recorded_at"),
            ).where(*scope)
        ).one()

        return AttendanceCounts(
            method_counts={str(row.method): int(row.rows) for row in grouped},
            distinct_subjects=int(totals.subjects),
            distinct_events=int(totals.events),
            first_recorded_at=totals.first_recorded_at,
            last_recorded_at=totals.last_recorded_at,
        )
