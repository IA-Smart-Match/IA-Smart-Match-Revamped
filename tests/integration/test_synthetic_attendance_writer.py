"""``AttendanceRepository``, against a real PostgreSQL instance (Card 4).

Proves ``python/smartmatch_persistence/smartmatch_persistence/attendance.py``'s
own claim: this is the minimal ``attendance_record`` writer that lets the
Attended funnel stage's own precondition
(``ck_pipeline_record_attendance_evidence``) be satisfied with a real row,
that the application-code refusal of an unknown ``method`` does not replace
the database's own ``ck_attendance_record_method`` CHECK, and that
``PipelineRepository.advance_stage``'s Attended biconditional still holds
end to end against a row this writer produced.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from smartmatch_domain.pipeline import PipelineStage
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence import attendance as attendance_module
from smartmatch_persistence.attendance import ATTENDANCE_METHODS, AttendanceRepository
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.pipeline import (
    MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
    PipelineRepository,
    UnknownAttendanceEvidenceError,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_attendance_tables(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's rows for the test tenant, in dependency order.

    ``pipeline_record`` goes first (it cites both ``attendance_record`` and
    ``user_account`` via ``ON DELETE RESTRICT``), then ``attendance_record``,
    then ``user_account`` — so the ``tenant_id`` fixture's own teardown never
    trips over a row this file left behind.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture(scope="module")
def repo() -> AttendanceRepository:
    return AttendanceRepository()


@pytest.fixture
def db_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the live test engine, mirroring the sibling cards' fixture."""
    return create_session_factory(engine.url.render_as_string(hide_password=False))


def _make_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"attendance-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@synthetic.invalid",
        },
    )
    return user_id


# ---------------------------------------------------------------------------
# record_attendance
# ---------------------------------------------------------------------------


def test_record_attendance_writes_one_row_and_returns_its_id(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: AttendanceRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    event_id = uuid.uuid4()

    with db_session_factory() as session:
        record_id = repo.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            event_id=event_id,
            method="coordinator_entry",
        )
        session.commit()

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, method FROM attendance_record WHERE id = :id"), {"id": record_id}
        ).one()

    assert row.id == record_id
    assert row.method == "coordinator_entry"


def test_record_attendance_is_idempotent_for_the_same_subject_and_event(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: AttendanceRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    event_id = uuid.uuid4()

    with db_session_factory() as session:
        first_id = repo.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            event_id=event_id,
            method="coordinator_entry",
        )
        session.commit()

    with db_session_factory() as session:
        second_id = repo.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            event_id=event_id,
            method="coordinator_entry",
        )
        session.commit()

    assert second_id == first_id

    with engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM attendance_record "
                "WHERE tenant_id = :tid AND subject_id = :sid AND event_id = :eid"
            ),
            {"tid": tenant_id, "sid": subject_id, "eid": event_id},
        ).scalar_one()
    assert count == 1


def test_record_attendance_writes_a_second_row_for_a_different_event(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: AttendanceRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        first_id = repo.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            event_id=uuid.uuid4(),
            method="coordinator_entry",
        )
        session.commit()

        second_id = repo.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            event_id=uuid.uuid4(),
            method="coordinator_entry",
        )
        session.commit()

    assert second_id != first_id

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM attendance_record WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()
    assert count == 2


def test_record_attendance_refuses_an_unknown_method(
    tenant_id: uuid.UUID,
    repo: AttendanceRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with (
        db_session_factory() as session,
        pytest.raises(ValueError, match="ck_attendance_record_method"),
    ):
        repo.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            event_id=uuid.uuid4(),
            method="fabricated",
        )


def test_record_attendance_accepts_every_legal_method_but_the_synthetic_path_uses_only_one(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: AttendanceRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """The writer accepts the full vocabulary; the synthetic path uses only one member."""
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        for method in ("qr_scan", "import"):
            record_id = repo.record_attendance(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=subject_id,
                event_id=uuid.uuid4(),
                method=method,
            )
            session.commit()
            assert record_id is not None

    assert SYNTHETIC_ATTENDANCE_METHOD == "coordinator_entry"
    assert SYNTHETIC_ATTENDANCE_METHOD in ATTENDANCE_METHODS
    assert {"qr_scan", "import"} <= ATTENDANCE_METHODS


# ---------------------------------------------------------------------------
# Negative — CHECK still enforced at the database
# ---------------------------------------------------------------------------


def test_a_raw_insert_with_a_fabricated_method_is_refused_by_the_database(
    tenant_id: uuid.UUID,
    engine: Engine,
) -> None:
    """The Python guard is a courtesy; the database's own CHECK is the backstop."""
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with (
        pytest.raises(IntegrityError, match="ck_attendance_record_method"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO attendance_record "
                "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                "VALUES (:id, :tid, :uid, :sid, :eid, 'fabricated')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uid": unit_id,
                "sid": subject_id,
                "eid": uuid.uuid4(),
            },
        )


# ---------------------------------------------------------------------------
# Negative — the Attended biconditional still holds
# ---------------------------------------------------------------------------


def test_advance_stage_to_attended_requires_and_accepts_this_writers_evidence(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: AttendanceRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    base = datetime.now(UTC) - timedelta(hours=4)

    pipeline_repo = PipelineRepository()

    with db_session_factory() as session:
        record = pipeline_repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=base,
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        session.commit()

        pipeline_repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONTACTED,
            reached_at=base + timedelta(hours=1),
        )
        pipeline_repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONFIRMED,
            reached_at=base + timedelta(hours=2),
        )
        session.commit()

        with pytest.raises(ValueError, match="attended_attendance_id"):
            pipeline_repo.advance_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=PipelineStage.ATTENDED,
                reached_at=base + timedelta(hours=3),
                attended_attendance_id=None,
            )

        attendance_id = repo.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            event_id=record.opportunity_event_id,
            method="coordinator_entry",
        )
        session.commit()

        outcome = pipeline_repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.ATTENDED,
            reached_at=base + timedelta(hours=3),
            attended_attendance_id=attendance_id,
        )
        session.commit()

    assert outcome.transitioned is True
    assert outcome.record is not None
    assert outcome.record.attended_at is not None
    assert outcome.record.attended_attendance_id == attendance_id


def test_advance_stage_to_attended_refuses_an_orphan_attendance_id(
    tenant_id: uuid.UUID,
    engine: Engine,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    base = datetime.now(UTC) - timedelta(hours=4)

    pipeline_repo = PipelineRepository()

    with db_session_factory() as session:
        record = pipeline_repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=base,
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        session.commit()

        pipeline_repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONTACTED,
            reached_at=base + timedelta(hours=1),
        )
        pipeline_repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONFIRMED,
            reached_at=base + timedelta(hours=2),
        )
        session.commit()

        with pytest.raises(UnknownAttendanceEvidenceError):
            pipeline_repo.advance_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=PipelineStage.ATTENDED,
                reached_at=base + timedelta(hours=3),
                attended_attendance_id=uuid.uuid4(),
            )


# ---------------------------------------------------------------------------
# Negative — no fabricated score
# ---------------------------------------------------------------------------


def test_module_contains_no_fabricated_score_vocabulary() -> None:
    source = inspect.getsource(attendance_module).lower()

    for forbidden in ("score", "confidence", "match_score", "rank", "weight"):
        assert forbidden not in source, f"forbidden token {forbidden!r} found in attendance.py"
