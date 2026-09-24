"""``EngagementLoadRepository`` against a real PostgreSQL instance (B26 T8c §4, L1–L9).

The load read turns a professional's confirmed, not-cancelled journeys into the
:class:`~smartmatch_domain.eli.Engagement` values ELI counts. These tests pin
what it returns — and what it must never return — over real storage:
cancelled and unconfirmed journeys stay out, the date prefilter on
``event.resolved_date`` agrees with the domain's own window, event times map to
durations, missing and unresolved events come back as unknown hours, another
tenant is invisible, another unit's booking counts (OQ2), and 200 subjects
cost one statement.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit
from smartmatch_domain.eli import Engagement, LoadInputs, compute_eli
from smartmatch_domain.events import DateOnlyTime, EventTime, ExactTime, UnresolvedTime
from smartmatch_persistence.engagement_load import EngagementLoadRepository
from smartmatch_persistence.events import ORIGIN_COORDINATOR_ENTRY, EventRepository
from smartmatch_persistence.pipeline import PipelineRepository
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from test_pipeline_record_constraints import _make_unit, _make_user

pytestmark = pytest.mark.integration

#: A fixed run date, independent of the wall clock, so every offset is exact.
AS_OF = date(2026, 10, 15)
ZONE = "America/Los_Angeles"
#: When every seeded journey was matched; each later stage is an hour on.
JOURNEY_BASE = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _delete_journeys(engine: Engine, tenant: uuid.UUID) -> None:
    """Delete journeys and their attendance before the tenant sweep (RESTRICT FKs)."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant})
        conn.execute(text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant})


@pytest.fixture(autouse=True)
def _clean_journeys(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    yield
    _delete_journeys(engine, tenant_id)


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    tid = uuid.uuid4()
    slug = f"test-other-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": tid, "slug": slug, "name": slug},
        )
    yield tid
    _delete_journeys(engine, tid)
    with engine.begin() as conn:
        for table in _TENANT_SCOPED_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


@pytest.fixture
def reader() -> EngagementLoadRepository:
    return EngagementLoadRepository()


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _exact(day: date, *, hours: float | None = 2) -> ExactTime:
    """Noon local on ``day``; ``hours=None`` states no end."""
    starts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=ZoneInfo(ZONE))
    ends = None if hours is None else starts + timedelta(hours=hours)
    return ExactTime(starts_at=starts, time_zone=ZONE, ends_at=ends)


def _event(
    session_factory: sessionmaker[Session],
    tenant: uuid.UUID,
    event_time: EventTime,
    *,
    title: str | None = None,
) -> uuid.UUID:
    """Write an event through the events repository, so ``resolved_date`` is set."""
    with session_factory() as session:
        unit_id = ensure_owning_unit(session, tenant)
        event_id = EventRepository().upsert(
            session,
            tenant_id=tenant,
            host_org_unit_id=unit_id,
            title=title or f"Load read {uuid.uuid4().hex[:10]}",
            event_time=event_time,
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        session.commit()
    return event_id


def _user(engine: Engine, tenant: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        user_id: uuid.UUID = _make_user(conn, tenant)
    return user_id


def _journey(
    engine: Engine,
    tenant: uuid.UUID,
    *,
    subject_id: uuid.UUID,
    event_id: uuid.UUID,
    reached: str = "confirmed",
    unit_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one journey that reached ``matched``/``contacted``/``confirmed``/``attended``.

    An attended journey cites a real ``attendance_record`` at its own event, so
    ``ck_pipeline_record_attendance_evidence`` holds with genuine evidence.
    """
    order = ("matched", "contacted", "confirmed", "attended")
    reached_index = order.index(reached)
    stamps: dict[str, Any] = {
        f"{stage}_at": (JOURNEY_BASE + timedelta(hours=i) if i <= reached_index else None)
        for i, stage in enumerate(order)
    }
    record_id = uuid.uuid4()
    with engine.begin() as conn:
        owning_unit = unit_id or ensure_owning_unit(conn, tenant)
        attendance_id = None
        if reached == "attended":
            attendance_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO attendance_record "
                    "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                    "VALUES (:id, :tid, :unit, :subject, :event, 'qr_scan')"
                ),
                {
                    "id": attendance_id,
                    "tid": tenant,
                    "unit": owning_unit,
                    "subject": subject_id,
                    "event": event_id,
                },
            )
        conn.execute(
            text(
                "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
                "opportunity_event_id, matched_provenance, matched_at, contacted_at, "
                "confirmed_at, attended_at, attended_attendance_id) "
                "VALUES (:id, :tid, :unit, :subject, :event, "
                "'synthetic / coordinator-accepted', :matched_at, :contacted_at, "
                ":confirmed_at, :attended_at, :attendance)"
            ),
            {
                "id": record_id,
                "tid": tenant,
                "unit": owning_unit,
                "subject": subject_id,
                "event": event_id,
                "attendance": attendance_id,
                **stamps,
            },
        )
    return record_id


def _read(
    session_factory: sessionmaker[Session],
    reader: EngagementLoadRepository,
    tenant: uuid.UUID,
    subject_ids: list[uuid.UUID],
) -> Any:
    with session_factory() as session:
        return reader.engagements_for(
            session, tenant_id=tenant, professional_ids=subject_ids, as_of=AS_OF
        )


def _refs(engagements: tuple[Engagement, ...]) -> set[str]:
    return {e.ref for e in engagements}


# ---------------------------------------------------------------------------
# L1–L9
# ---------------------------------------------------------------------------


def test_a_cancelled_booking_is_never_returned(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L1: cancelled through T8a's ``cancel_booking``; the kept booking still reads."""
    subject = _user(engine, tenant_id)
    kept = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, _exact(AS_OF + timedelta(days=1))),
    )
    cancelled = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, _exact(AS_OF + timedelta(days=2))),
    )
    with session_factory() as session:
        outcome = PipelineRepository().cancel_booking(
            session,
            tenant_id=tenant_id,
            record_id=cancelled,
            actor_user_id=_user(engine, tenant_id),
            at=datetime.now(UTC),
        )
        session.commit()
    assert outcome.transitioned

    result = _read(session_factory, reader, tenant_id, [subject])

    assert _refs(result[subject]) == {str(kept)}


def test_unconfirmed_journeys_are_not_returned(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L2: Matched and Contacted journeys are not bookings; the subject has no key."""
    subject = _user(engine, tenant_id)
    for reached in ("matched", "contacted"):
        _journey(
            engine,
            tenant_id,
            subject_id=subject,
            event_id=_event(session_factory, tenant_id, _exact(AS_OF)),
            reached=reached,
        )

    result = _read(session_factory, reader, tenant_id, [subject])

    assert subject not in result
    assert dict(result) == {}


def test_prefilter_matches_the_domain_window(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L3: events at -46, -45, -1, 0, +44, +45; the read returns -45 ... +44 only.

    The past journeys are attended so the completed window counts them; the
    assessment over what was read equals the assessment over every journey
    built in Python, so the SQL prefilter drops nothing ELI would count.
    """
    subject = _user(engine, tenant_id)
    offsets = (-46, -45, -1, 0, 44, 45)
    by_offset: dict[int, uuid.UUID] = {}
    everything: list[Engagement] = []
    for offset in offsets:
        when = _exact(AS_OF + timedelta(days=offset))
        attended = offset < 0
        record_id = _journey(
            engine,
            tenant_id,
            subject_id=subject,
            event_id=_event(session_factory, tenant_id, when),
            reached="attended" if attended else "confirmed",
        )
        by_offset[offset] = record_id
        everything.append(
            Engagement.from_event_time(
                str(record_id), when, confirmed=True, attended=attended, cancelled=False
            )
        )

    result = _read(session_factory, reader, tenant_id, [subject])

    assert _refs(result[subject]) == {str(by_offset[o]) for o in (-45, -1, 0, 44)}
    capacity = Decimal(100)
    from_read = compute_eli(
        LoadInputs(as_of=AS_OF, engagements=result[subject], declared_capacity_hours=capacity)
    )
    from_all = compute_eli(
        LoadInputs(as_of=AS_OF, engagements=tuple(everything), declared_capacity_hours=capacity)
    )
    assert from_read == from_all
    assert from_read.completed_hours == Decimal(4)
    assert from_read.confirmed_hours == Decimal(4)


def test_event_time_maps_to_duration(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L4: exact with an end → exact ``timedelta``; exact without end and date_only → None."""
    subject = _user(engine, tenant_id)
    day = AS_OF + timedelta(days=3)
    with_end = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, _exact(day, hours=2.5)),
    )
    no_end = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, _exact(day, hours=None)),
    )
    date_only = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, DateOnlyTime(on_date=day, time_zone=ZONE)),
    )

    result = _read(session_factory, reader, tenant_id, [subject])
    by_ref = {e.ref: e for e in result[subject]}

    assert by_ref[str(with_end)].duration == timedelta(hours=2, minutes=30)
    assert by_ref[str(no_end)].duration is None
    assert by_ref[str(date_only)].duration is None
    assert {e.event_date for e in result[subject]} == {day}
    assert all(e.confirmed and not e.attended and not e.cancelled for e in result[subject])


def test_a_journey_naming_no_event_is_unresolved(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L5 (OQ3): no event row → unresolved time → unknown hours, never dropped."""
    subject = _user(engine, tenant_id)
    record_id = _journey(engine, tenant_id, subject_id=subject, event_id=uuid.uuid4())

    result = _read(session_factory, reader, tenant_id, [subject])

    assert result[subject] == (
        Engagement.from_event_time(
            str(record_id), UnresolvedTime(), confirmed=True, attended=False, cancelled=False
        ),
    )
    assert result[subject][0].event_date is None
    assert result[subject][0].duration is None


def test_unresolved_events_are_always_returned(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L6: an unresolved event has no ``resolved_date``; the prefilter lets it through."""
    subject = _user(engine, tenant_id)
    record_id = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, UnresolvedTime()),
    )

    result = _read(session_factory, reader, tenant_id, [subject])

    assert _refs(result[subject]) == {str(record_id)}
    assert result[subject][0].event_date is None


def test_another_tenants_rows_are_invisible(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L7: asking in one tenant for another tenant's subject returns nothing."""
    foreign_subject = _user(engine, other_tenant_id)
    foreign_record = _journey(
        engine,
        other_tenant_id,
        subject_id=foreign_subject,
        event_id=_event(session_factory, other_tenant_id, _exact(AS_OF)),
    )

    assert dict(_read(session_factory, reader, tenant_id, [foreign_subject])) == {}
    own = _read(session_factory, reader, other_tenant_id, [foreign_subject])
    assert _refs(own[foreign_subject]) == {str(foreign_record)}


def test_another_units_booking_counts(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L8 (OQ2): load is the person's, tenant-wide — every unit's booking counts."""
    subject = _user(engine, tenant_id)
    with engine.begin() as conn:
        other_unit = _make_unit(conn, tenant_id, "iawest.loadread")
    home = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, _exact(AS_OF + timedelta(days=5))),
    )
    away = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, _exact(AS_OF + timedelta(days=6))),
        unit_id=other_unit,
    )

    result = _read(session_factory, reader, tenant_id, [subject])

    assert _refs(result[subject]) == {str(home), str(away)}


def test_one_query_for_two_hundred_subjects(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    reader: EngagementLoadRepository,
) -> None:
    """L9: 200 ids cost one statement; an empty list costs none."""
    subject = _user(engine, tenant_id)
    record_id = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, _exact(AS_OF)),
    )
    subject_ids = [subject, *(uuid.uuid4() for _ in range(199))]
    statements: list[str] = []

    def _count(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        with session_factory() as session:
            result = reader.engagements_for(
                session, tenant_id=tenant_id, professional_ids=subject_ids, as_of=AS_OF
            )
            assert len(statements) == 1, statements
            statements.clear()
            empty = reader.engagements_for(
                session, tenant_id=tenant_id, professional_ids=[], as_of=AS_OF
            )
            assert statements == []
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert isinstance(result, MappingProxyType)
    assert set(result) == {subject}
    assert isinstance(result[subject], tuple)
    assert _refs(result[subject]) == {str(record_id)}
    assert dict(empty) == {}
