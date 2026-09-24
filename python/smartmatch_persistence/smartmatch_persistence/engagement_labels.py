"""Labels for the engagements whose hours are unknown (B26 T8d §4.3).

T8b's :class:`~smartmatch_domain.eli.LoadAssessment` names every counted
engagement without an end time by its ``pipeline_record`` id. The availability
surfaces need to say *which* engagement that is: the event's title, date and
time precision, and — so a Connector's view can be scoped to their own unit —
the event's host unit and origin.

## One statement, never a commit

:meth:`EngagementLabelRepository.labels_for` issues exactly one ``SELECT`` for
any number of ids, and none for an empty list. It takes the caller's
:class:`~sqlalchemy.orm.Session` and never commits.

## What it deliberately is not

It is not T8c's :class:`~smartmatch_persistence.engagement_load.EngagementLoadRepository`:
the run's hot path stays exactly as T8c pinned it, and this second read happens
only on the availability routes, only when some engagement lacks an end time.

Which of these fields a caller may *see* is not decided here: the API's
``speaker_load_view`` anonymizes another unit's engagements for a Connector.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["EngagementLabel", "EngagementLabelRepository"]


@dataclass(frozen=True, slots=True)
class EngagementLabel:
    """One ``pipeline_record`` and the event it names.

    Every event field is ``None`` when the record names no event row
    (``opportunity_event_id`` has no foreign key; T8c OQ3).

    Attributes:
        record_id: The ``pipeline_record`` id (T8b's ``ref``).
        event_id: The event's id, or ``None`` when the row is missing.
        title: The event's title.
        resolved_date: The event's first local date; ``None`` when unresolved.
        time_precision: ``exact``, ``date_only`` or ``unresolved``.
        host_org_unit_id: The unit hosting the event.
        origin: ``coordinator_entry`` or ``extraction``.
    """

    record_id: uuid.UUID
    event_id: uuid.UUID | None
    title: str | None
    resolved_date: date | None
    time_precision: str | None
    host_org_unit_id: uuid.UUID | None
    origin: str | None


class EngagementLabelRepository:
    """Reads the event behind each named ``pipeline_record``. Never commits."""

    def labels_for(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        record_ids: Collection[uuid.UUID],
        limit: int,
    ) -> tuple[EngagementLabel, ...]:
        """Label each named record, ordered by event date then record id.

        Args:
            session: The caller's session; never committed.
            tenant_id: The tenant; an id from another tenant labels nothing.
            record_ids: The records to label. Empty issues no query.
            limit: At most this many labels, applied in SQL.

        Returns:
            Labels ordered by ``event.resolved_date`` (unresolved and missing
            events last), then by ``pipeline_record.id``.

        Raises:
            ValueError: when ``limit`` is not positive.
        """
        if limit < 1:
            raise ValueError(f"limit must be positive, got {limit}")
        ids = list(dict.fromkeys(record_ids))
        if not ids:
            return ()
        return tuple(
            EngagementLabel(
                record_id=row.record_id,
                event_id=row.event_id,
                title=row.title,
                resolved_date=row.resolved_date,
                time_precision=row.time_precision,
                host_org_unit_id=row.host_org_unit_id,
                origin=row.origin,
            )
            for row in session.execute(_statement(tenant_id, ids, limit))
        )


def _statement(tenant_id: uuid.UUID, ids: list[uuid.UUID], limit: int) -> sa.Select[Any]:
    """The one ``SELECT`` of plan §4.3."""
    record = schema.pipeline_record
    ev = schema.event
    record_ids = sa.bindparam(
        "record_ids", ids, type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True))
    )
    return (
        sa.select(
            record.c.id.label("record_id"),
            ev.c.id.label("event_id"),
            ev.c.title,
            ev.c.resolved_date,
            ev.c.time_precision,
            ev.c.host_org_unit_id,
            ev.c.origin,
        )
        .select_from(
            record.outerjoin(
                ev,
                sa.and_(
                    ev.c.tenant_id == record.c.tenant_id,
                    ev.c.id == record.c.opportunity_event_id,
                ),
            )
        )
        .where(record.c.tenant_id == tenant_id, record.c.id == sa.any_(record_ids))
        .order_by(ev.c.resolved_date.asc().nulls_last(), record.c.id)
        .limit(sa.bindparam("label_limit", limit, type_=sa.Integer))
    )
