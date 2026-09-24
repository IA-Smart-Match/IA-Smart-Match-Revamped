"""``EngagementLabelRepository`` against a real PostgreSQL instance (B26 T8d §4.3, L1–L6).

T8b names the engagements whose hours are unknown by ``pipeline_record`` id.
This read labels them for the availability surfaces: the event's title, date,
precision, host unit and origin, or nothing when the event row is missing.
Tenant-scoped, ordered by date then id with unresolved dates last, limited in
SQL, one statement, and none for an empty list.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit
from smartmatch_domain.events import DateOnlyTime, EventTime, UnresolvedTime
from smartmatch_persistence.engagement_labels import EngagementLabel, EngagementLabelRepository
from smartmatch_persistence.events import (
    ORIGIN_COORDINATOR_ENTRY,
    ORIGIN_EXTRACTION,
    EventProvenance,
    EventRepository,
)
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from test_engagement_load_read import _exact, _journey, _user
from test_pipeline_record_constraints import _make_unit

pytestmark = pytest.mark.integration

AS_OF = date(2026, 10, 15)
ZONE = "America/Los_Angeles"


def _delete_journeys(engine: Engine, tenant: uuid.UUID) -> None:
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
    slug = f"test-labels-{tid.hex[:12]}"
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
def labels() -> EngagementLabelRepository:
    return EngagementLabelRepository()


def _event(
    session_factory: sessionmaker[Session],
    tenant: uuid.UUID,
    event_time: EventTime,
    *,
    title: str,
    host: uuid.UUID | None = None,
    extracted: bool = False,
) -> uuid.UUID:
    with session_factory() as session:
        host_unit = host or ensure_owning_unit(session, tenant)
        event_id = EventRepository().upsert(
            session,
            tenant_id=tenant,
            host_org_unit_id=host_unit,
            title=title,
            event_time=event_time,
            origin=ORIGIN_EXTRACTION if extracted else ORIGIN_COORDINATOR_ENTRY,
            provenance=(
                EventProvenance(
                    source_url=f"https://calendar.example.invalid/{uuid.uuid4().hex}",
                    fetched_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
                    extractor_version="synthetic-json-1",
                )
                if extracted
                else None
            ),
        )
        session.commit()
    return event_id


def _missing_event_journey(engine: Engine, tenant: uuid.UUID, subject: uuid.UUID) -> uuid.UUID:
    """A journey naming an event id with no row (``opportunity_event_id`` has no FK)."""
    return _journey(engine, tenant, subject_id=subject, event_id=uuid.uuid4())


def _read(
    session_factory: sessionmaker[Session],
    repo: EngagementLabelRepository,
    tenant: uuid.UUID,
    record_ids: list[uuid.UUID],
    *,
    limit: int = 21,
) -> tuple[EngagementLabel, ...]:
    with session_factory() as session:
        return repo.labels_for(session, tenant_id=tenant, record_ids=record_ids, limit=limit)


# ---------------------------------------------------------------------------
# L1–L6
# ---------------------------------------------------------------------------


def test_labels_carry_title_date_precision_unit_and_origin(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    labels: EngagementLabelRepository,
) -> None:
    """L1: every label field comes off the event row; a second unit and origin too."""
    subject = _user(engine, tenant_id)
    with engine.begin() as conn:
        other_unit = _make_unit(conn, tenant_id, "iawest.labelread")
    own_event = _event(
        session_factory,
        tenant_id,
        DateOnlyTime(on_date=AS_OF + timedelta(days=3), time_zone=ZONE),
        title="Corporate treasury guest lecture",
    )
    away_event = _event(
        session_factory,
        tenant_id,
        _exact(AS_OF + timedelta(days=4), hours=None),
        title="Audit committee panel",
        host=other_unit,
        extracted=True,
    )
    own = _journey(engine, tenant_id, subject_id=subject, event_id=own_event)
    away = _journey(engine, tenant_id, subject_id=subject, event_id=away_event)
    with engine.connect() as conn:
        own_unit = ensure_owning_unit(conn, tenant_id)

    result = _read(session_factory, labels, tenant_id, [away, own])

    assert isinstance(result, tuple)
    assert result == (
        EngagementLabel(
            record_id=own,
            event_id=own_event,
            title="Corporate treasury guest lecture",
            resolved_date=AS_OF + timedelta(days=3),
            time_precision="date_only",
            host_org_unit_id=own_unit,
            origin="coordinator_entry",
        ),
        EngagementLabel(
            record_id=away,
            event_id=away_event,
            title="Audit committee panel",
            resolved_date=AS_OF + timedelta(days=4),
            time_precision="exact",
            host_org_unit_id=other_unit,
            origin="extraction",
        ),
    )


def test_a_record_naming_no_event_returns_null_event_fields(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    labels: EngagementLabelRepository,
) -> None:
    """L2: the record is labelled, every event field null (T8c OQ3)."""
    subject = _user(engine, tenant_id)
    record = _missing_event_journey(engine, tenant_id, subject)

    (label,) = _read(session_factory, labels, tenant_id, [record])

    assert label == EngagementLabel(
        record_id=record,
        event_id=None,
        title=None,
        resolved_date=None,
        time_precision=None,
        host_org_unit_id=None,
        origin=None,
    )


def test_another_tenants_records_are_invisible(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
    labels: EngagementLabelRepository,
) -> None:
    """L3: an id from another tenant labels nothing here."""
    foreign_subject = _user(engine, other_tenant_id)
    foreign = _journey(
        engine,
        other_tenant_id,
        subject_id=foreign_subject,
        event_id=_event(
            session_factory,
            other_tenant_id,
            _exact(AS_OF, hours=None),
            title="Foreign tenant lecture",
        ),
    )

    assert _read(session_factory, labels, tenant_id, [foreign]) == ()
    assert [
        label.record_id for label in _read(session_factory, labels, other_tenant_id, [foreign])
    ] == [foreign]


def test_order_is_date_then_id_with_unresolved_last(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    labels: EngagementLabelRepository,
) -> None:
    """L4: ``resolved_date`` ascending, NULLs (unresolved or missing) last, ties by id."""
    subject = _user(engine, tenant_id)
    late = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(
            session_factory, tenant_id, _exact(AS_OF + timedelta(days=9), hours=None), title="Late"
        ),
    )
    early = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(
            session_factory, tenant_id, _exact(AS_OF + timedelta(days=1), hours=None), title="Early"
        ),
    )
    same_day = sorted(
        _journey(
            engine,
            tenant_id,
            subject_id=subject,
            event_id=_event(
                session_factory,
                tenant_id,
                _exact(AS_OF + timedelta(days=5), hours=None),
                title=title,
            ),
        )
        for title in ("Middle morning", "Middle evening")
    )
    unresolved = _journey(
        engine,
        tenant_id,
        subject_id=subject,
        event_id=_event(session_factory, tenant_id, UnresolvedTime(), title="Undated"),
    )
    missing = _missing_event_journey(engine, tenant_id, subject)

    result = _read(
        session_factory, labels, tenant_id, [missing, unresolved, late, *same_day, early]
    )

    ordered = [label.record_id for label in result]
    assert ordered[:4] == [early, *same_day, late]
    assert set(ordered[4:]) == {unresolved, missing}
    assert ordered[4:] == sorted(ordered[4:])


def test_limit_is_applied_in_sql(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    labels: EngagementLabelRepository,
) -> None:
    """L5: ``LIMIT`` is in the statement, and the first rows by the order are kept."""
    subject = _user(engine, tenant_id)
    records = [
        _journey(
            engine,
            tenant_id,
            subject_id=subject,
            event_id=_event(
                session_factory,
                tenant_id,
                _exact(AS_OF + timedelta(days=offset), hours=None),
                title=f"Lecture {chr(ord('a') + offset)}",
            ),
        )
        for offset in range(4)
    ]
    statements: list[str] = []

    def _capture(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        result = _read(session_factory, labels, tenant_id, list(reversed(records)), limit=2)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert [label.record_id for label in result] == records[:2]
    assert any("LIMIT" in statement.upper() for statement in statements), statements


def test_empty_input_issues_no_statement(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    labels: EngagementLabelRepository,
) -> None:
    """L6a: no ids, no statement, and an empty tuple."""
    statements: list[str] = []

    def _capture(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    with session_factory() as session:
        event.listen(engine, "before_cursor_execute", _capture)
        try:
            result = labels.labels_for(session, tenant_id=tenant_id, record_ids=[], limit=21)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

    assert result == ()
    assert statements == []


def test_one_statement_for_twenty_one_ids(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    labels: EngagementLabelRepository,
) -> None:
    """L6b: twenty-one ids cost one statement; the session is never committed."""
    shared_event = _event(
        session_factory, tenant_id, _exact(AS_OF + timedelta(days=2), hours=None), title="Shared"
    )
    # One journey per subject: a subject has at most one journey per event.
    records = [
        _journey(engine, tenant_id, subject_id=_user(engine, tenant_id), event_id=shared_event)
        for _ in range(21)
    ]
    statements: list[str] = []

    def _capture(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    with session_factory() as session:
        event.listen(engine, "before_cursor_execute", _capture)
        try:
            result = labels.labels_for(session, tenant_id=tenant_id, record_ids=records, limit=21)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)
        assert session.in_transaction()

    assert len(statements) == 1, statements
    assert [label.record_id for label in result] == sorted(records)
