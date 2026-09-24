"""The engagement load read: ``pipeline_record`` + ``event`` → ELI engagements (B26 T8c §4).

At run time a match run needs each candidate's bookings as the
:class:`~smartmatch_domain.eli.Engagement` values
:func:`~smartmatch_domain.eli.compute_eli` counts. This module reads them.

## One statement, never a commit

:meth:`EngagementLoadRepository.engagements_for` issues exactly one ``SELECT``
for any number of professionals (≤ 200, ``MAX_CANDIDATES``) and none for an
empty list. It takes the caller's :class:`~sqlalchemy.orm.Session` and never
commits: transaction boundaries belong to the caller.

## What counts as a booking

A journey that reached Confirmed (``confirmed_at IS NOT NULL``) and was not
cancelled (``cancelled_at IS NULL``, any cancellation time — a cancelled
booking drops out immediately). ``subject_id`` is the professional id. The scope
is **tenant-wide** (OQ2): load is the person's, so every unit's bookings of that
person count.

## The date prefilter is a prefilter

The ``WHERE`` keeps events whose ``resolved_date`` lies in
``[as_of - COMPLETED_WINDOW_DAYS, as_of + CONFIRMED_WINDOW_DAYS - 1]``, computed
here in Python from :mod:`smartmatch_domain.eli`'s constants and bound as two
dates — no date arithmetic in SQL, no ``now()``. A journey whose event row is
missing (``opportunity_event_id`` has no foreign key) or whose date is
unresolved always passes. Python stays authoritative: the window and
attendance rules are decided in ``compute_eli``, not here.

## Missing and unresolved events are unknown hours

A journey naming no event row becomes :class:`~smartmatch_domain.events.UnresolvedTime`
(OQ3) — never dropped, never zero hours (ADR-0011).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from datetime import date, timedelta
from types import MappingProxyType
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.availability_verdict import event_time_from_columns
from smartmatch_domain.eli import COMPLETED_WINDOW_DAYS, CONFIRMED_WINDOW_DAYS, Engagement
from smartmatch_domain.events import EventTime, UnresolvedTime
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["EngagementLoadRepository"]


def _load_window(as_of: date) -> tuple[date, date]:
    """The inclusive ``resolved_date`` range the prefilter keeps for ``as_of``.

    ``[as_of - 45, as_of + 44]``: the completed window's first day through the
    confirmed window's last, from T8b's constants.
    """
    window_start = as_of - timedelta(days=COMPLETED_WINDOW_DAYS)
    window_end = as_of + timedelta(days=CONFIRMED_WINDOW_DAYS - 1)
    return window_start, window_end


class EngagementLoadRepository:
    """Reads confirmed, not-cancelled bookings as ELI engagements.

    Takes a session per call, like every other repository in this package; no
    method here commits.
    """

    def engagements_for(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_ids: Collection[uuid.UUID],
        as_of: date,
    ) -> Mapping[uuid.UUID, tuple[Engagement, ...]]:
        """Each professional's bookings in play for ``as_of``, as engagements.

        Args:
            session: The caller's session; never committed.
            tenant_id: The tenant; every unit in it counts (OQ2).
            professional_ids: The subjects to read. Empty issues no query.
            as_of: The run's UTC date, the same one ``compute_eli`` receives.

        Returns:
            A read-only mapping keyed by professional id, holding only subjects
            that have rows; an absent key means no engagements. Each value is a
            tuple ordered by ``pipeline_record.id``.
        """
        ids = list(dict.fromkeys(professional_ids))
        if not ids:
            return MappingProxyType({})

        grouped: dict[uuid.UUID, list[Engagement]] = {}
        for row in session.execute(_statement(tenant_id, ids, as_of)):
            grouped.setdefault(row.subject_id, []).append(_to_engagement(row))
        return MappingProxyType({pid: tuple(rows) for pid, rows in grouped.items()})


def _statement(tenant_id: uuid.UUID, ids: list[uuid.UUID], as_of: date) -> sa.Select[Any]:
    """The one ``SELECT`` of plan §4, with the window bound as two dates."""
    record = schema.pipeline_record
    ev = schema.event
    window_start, window_end = _load_window(as_of)
    subject_ids = sa.bindparam(
        "professional_ids", ids, type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True))
    )
    return (
        sa.select(
            record.c.id,
            record.c.subject_id,
            record.c.attended_at,
            ev.c.id.label("event_id"),
            ev.c.time_precision,
            ev.c.starts_at,
            ev.c.ends_at,
            ev.c.on_date,
            ev.c.time_zone,
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
        .where(
            record.c.tenant_id == tenant_id,
            record.c.subject_id == sa.any_(subject_ids),
            record.c.confirmed_at.is_not(None),
            record.c.cancelled_at.is_(None),
            sa.or_(
                ev.c.id.is_(None),
                ev.c.resolved_date.is_(None),
                ev.c.resolved_date.between(
                    sa.bindparam("window_start", window_start, type_=sa.Date),
                    sa.bindparam("window_end", window_end, type_=sa.Date),
                ),
            ),
        )
        .order_by(record.c.subject_id, record.c.id)
    )


def _event_time(row: sa.Row[Any]) -> EventTime:
    """The row's event time; a journey naming no event row is unresolved (OQ3)."""
    if row.event_id is None:
        return UnresolvedTime()
    return event_time_from_columns(
        time_precision=row.time_precision,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        on_date=row.on_date,
        time_zone=row.time_zone,
    )


def _to_engagement(row: sa.Row[Any]) -> Engagement:
    """One row as a confirmed, not-cancelled engagement."""
    return Engagement.from_event_time(
        ref=str(row.id),
        event_time=_event_time(row),
        confirmed=True,
        attended=row.attended_at is not None,
        cancelled=False,
    )
