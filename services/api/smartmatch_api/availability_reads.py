"""The database half of B26 T4's availability checks.

Reads the event a match run or an invitation batch is for, and today's
availability verdicts for a set of Speakers. The pure half — the verdict, its
payload, "changed since" — is :mod:`smartmatch_domain.availability_verdict`.

Every read is scoped by tenant **and** unit in the query itself, the discipline
``load_speaker_request`` states. Plan ``docs/plans/b26-tracks/T4-plan.md`` §3-§4.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

import sqlalchemy as sa
from smartmatch_domain.availability_verdict import (
    StoredVerdict,
    event_time_from_columns,
    verdicts_for_pool,
)
from smartmatch_domain.events import EventTime
from smartmatch_domain.speaker_availability import event_local_span
from smartmatch_persistence import schema
from smartmatch_persistence.speaker_availability import (
    SpeakerAvailabilityRepository,
    StoredSpeakerAvailability,
)
from sqlalchemy.orm import Session

__all__ = [
    "RunRequest",
    "current_verdicts",
    "load_batch_request_event_time",
    "load_request_event_time",
    "parse_request_id",
    "request_for_run",
]

#: ``event.origin`` for a Speaker Request (``match_run_evidence``'s constant).
_COORDINATOR_ENTRY: Final[str] = "coordinator_entry"

_availability: Final[SpeakerAvailabilityRepository] = SpeakerAvailabilityRepository()

_TIME_COLUMNS = (
    schema.event.c.time_precision,
    schema.event.c.starts_at,
    schema.event.c.ends_at,
    schema.event.c.on_date,
    schema.event.c.time_zone,
)


@dataclass(frozen=True, slots=True)
class RunRequest:
    """A match run in this unit, and the Speaker Request its need names.

    Attributes:
        match_run_id: The run.
        event_need_id: The run's stored need, verbatim.
        speaker_request_id: The Speaker Request in this unit the need names, or
            ``None`` for a pre-OQ-CBA-031 run whose need is free text (or names
            nothing readable here).
    """

    match_run_id: uuid.UUID
    event_need_id: str
    speaker_request_id: uuid.UUID | None


def parse_request_id(event_need_id: str) -> uuid.UUID | None:
    """The need as a UUID, or ``None`` when it is free text (pre-OQ-CBA-031)."""
    try:
        return uuid.UUID(event_need_id)
    except (ValueError, AttributeError, TypeError):
        return None


def _event_time(row: Any) -> EventTime:
    return event_time_from_columns(
        time_precision=row.time_precision,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        on_date=row.on_date,
        time_zone=row.time_zone,
    )


def load_request_event_time(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    speaker_request_id: uuid.UUID,
) -> EventTime | None:
    """The Speaker Request's time, or ``None`` when this unit has no such request.

    Scoped like ``load_speaker_request``: tenant, ``host_org_unit_id`` and
    ``origin = 'coordinator_entry'``. An extracted event is not a request.
    """
    row = session.execute(
        sa.select(*_TIME_COLUMNS).where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            schema.event.c.id == speaker_request_id,
            schema.event.c.origin == _COORDINATOR_ENTRY,
        )
    ).one_or_none()
    return None if row is None else _event_time(row)


def load_batch_request_event_time(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    speaker_request_id: uuid.UUID,
) -> EventTime | None:
    """The time of the request a stored batch names, for dispatch (§4.4).

    Tenant + unit + id, **without** the ``origin`` predicate: the event upsert
    can rewrite ``origin`` to ``extraction`` while the row's dates stay the
    event's dates, and the batch already recorded which request it was for.
    """
    row = session.execute(
        sa.select(*_TIME_COLUMNS).where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            schema.event.c.id == speaker_request_id,
        )
    ).one_or_none()
    return None if row is None else _event_time(row)


def request_for_run(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    match_run_id: uuid.UUID,
) -> RunRequest | None:
    """The run in this unit and the request it names, or ``None`` for no such run here."""
    need = session.execute(
        sa.select(schema.match_run.c.event_need_id).where(
            schema.match_run.c.tenant_id == tenant_id,
            schema.match_run.c.owning_unit_id == unit_id,
            schema.match_run.c.id == match_run_id,
        )
    ).scalar_one_or_none()
    if need is None:
        return None
    candidate = parse_request_id(str(need))
    request_id: uuid.UUID | None = None
    if candidate is not None:
        found = session.execute(
            sa.select(schema.event.c.id).where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.host_org_unit_id == unit_id,
                schema.event.c.id == candidate,
                schema.event.c.origin == _COORDINATOR_ENTRY,
            )
        ).scalar_one_or_none()
        request_id = None if found is None else uuid.UUID(str(found))
    return RunRequest(
        match_run_id=match_run_id, event_need_id=str(need), speaker_request_id=request_id
    )


def current_verdicts(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    subject_ids: Sequence[str],
    event_time: EventTime,
    as_of: date,
    statements: Mapping[uuid.UUID, StoredSpeakerAvailability] | None = None,
) -> tuple[StoredVerdict, ...]:
    """Today's verdict for each subject, in order: one ``get_many`` query.

    A subject id that is not a UUID can hold no statement and reads as not
    stated. No query is issued for an empty pool.

    ``statements`` (B26 T8c) is a ``get_many`` result the caller already read
    over a superset of ``subject_ids`` (the 3.x create route reads it once for
    capacity); it is reused and no query is issued. ``None`` reads it here.
    """
    parsed = {subject: parse_request_id(subject) for subject in subject_ids}
    stored = (
        _availability.get_many(
            session,
            tenant_id=tenant_id,
            professional_ids=[pid for pid in parsed.values() if pid is not None],
        )
        if statements is None
        else statements
    )
    by_subject = {
        subject: stored[pid].statement
        for subject, pid in parsed.items()
        if pid is not None and pid in stored
    }
    return verdicts_for_pool(subject_ids, by_subject, event_local_span(event_time), as_of)
