"""``PipelineRepository``, against a real PostgreSQL instance (P8 card O2 app writers).

Two things this file proves, over real storage rather than the adapter in
isolation:

* :class:`~smartmatch_persistence.pipeline.PipelineRepository` writes rows
  that satisfy every CHECK constraint migration ``0011`` added —
  ``ck_pipeline_record_stage_prefix``, ``ck_pipeline_record_stage_order``, and
  ``ck_pipeline_record_attendance_evidence`` — and refuses, before any SQL
  reaches the database, the writes that would violate them.
* Once this repository has written N rows for a unit, the metrics surface
  card O3 already bound (``services/api/smartmatch_api/routers/metrics.py``)
  reports exactly N for the matching aggregate, and its drill-down returns
  exactly those N rows — ADR-0011 rule 3, exercised end to end from a write
  path to the HTTP surface for the first time (``test_metrics_storage_binding.py``
  seeds rows with raw SQL; this file seeds them with the repository itself).

See ``smartmatch_persistence.pipeline``'s module docstring for why no
production route calls this repository yet: G1 (plan P5, matching) has not
closed, and "No matcher actions before G1" is a standing constraint of the
plan that owns this table.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

import httpx
from conftest import JOB_OWNING_UNIT_PATH, ensure_owning_unit, unique_subject
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.pipeline import InvalidPipelineStageTransitionError, PipelineStage
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.pipeline import (
    ConflictingOwningUnitError,
    PipelineRepository,
    PipelineStageOrderError,
    UnknownAttendanceEvidenceError,
)
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker
from test_pipeline_record_constraints import _insert_attendance, _make_unit, _make_user

pytestmark = pytest.mark.integration

#: The funnel in order, matching ``smartmatch_domain.pipeline.PIPELINE_STAGE_SEQUENCE``
#: — restated as a local constant rather than imported, so a change to that
#: sequence's order shows up here as a failing assertion rather than silently
#: reordering this file's own journeys along with it.
FUNNEL_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.MATCHED,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    PipelineStage.MEMBER_INQUIRY,
)

#: Metric name each funnel stage's aggregate is registered under
#: (``smartmatch_domain.metrics.METRIC_REGISTER``).
_STAGE_METRIC_NAMES: dict[PipelineStage, str] = {
    PipelineStage.MATCHED: "pipeline_matched",
    PipelineStage.CONTACTED: "pipeline_contacted",
    PipelineStage.CONFIRMED: "pipeline_confirmed",
    PipelineStage.ATTENDED: "pipeline_attended",
    PipelineStage.MEMBER_INQUIRY: "pipeline_member_inquiry",
}


@pytest.fixture(autouse=True)
def _clean_pipeline_and_attendance_tables(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's ``pipeline_record``/``attendance_record`` rows.

    Same arrangement, and the same reason, as
    ``test_pipeline_record_constraints.py``'s own cleanup fixture: both
    tables carry ``ON DELETE RESTRICT`` foreign keys back to ``org_unit`` and
    ``user_account``, so a row left behind here would make the ``tenant_id``
    fixture's own teardown fail.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )


@pytest.fixture(scope="module")
def repo() -> PipelineRepository:
    return PipelineRepository()


@pytest.fixture
def db_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the live test engine.

    Mirrors ``test_job_owning_unit.py``'s own ``create_session_factory(...)``
    call: the repository under test takes an ORM ``Session``, not the raw
    ``Connection`` most of this test suite's raw-SQL helpers use.
    """
    return create_session_factory(engine.url.render_as_string(hide_password=False))


def _advance_to(
    session: Session,
    engine: Engine,
    repo: PipelineRepository,
    *,
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    subject_id: uuid.UUID,
    reached_index: int,
    base: datetime,
) -> None:
    """Advance one journey from Matched up to ``FUNNEL_ORDER[reached_index]``.

    A real ``attendance_record`` row is inserted (via the same
    ``_insert_attendance`` helper ``test_pipeline_record_constraints.py``
    uses) the moment the journey reaches Attended, so
    ``ck_pipeline_record_attendance_evidence`` is satisfied with genuine
    evidence rather than an invented id.
    """
    for offset, stage in enumerate(FUNNEL_ORDER[1 : reached_index + 1], start=1):
        attended_attendance_id = None
        if stage is PipelineStage.ATTENDED:
            with engine.begin() as conn:
                attended_attendance_id = _insert_attendance(conn, tenant_id, subject_id)
        outcome = repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record_id,
            stage=stage,
            reached_at=base + timedelta(hours=offset),
            attended_attendance_id=attended_attendance_id,
        )
        assert outcome.transitioned, f"{stage.value} did not transition"
        session.commit()


# ---------------------------------------------------------------------------
# The repository writes rows that satisfy every 0011 CHECK constraint
# ---------------------------------------------------------------------------


def test_record_matched_writes_a_valid_row_and_is_idempotent(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    opportunity_id = uuid.uuid4()
    matched_at = datetime.now(UTC) - timedelta(days=1)

    with db_session_factory() as session:
        first = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_id,
            matched_at=matched_at,
        )
        session.commit()

    assert first.matched_at == matched_at
    assert first.reached() == frozenset({PipelineStage.MATCHED})
    assert first.contacted_at is None
    assert first.attended_attendance_id is None

    # A second call for the identical journey is a no-op, not a UniqueViolation
    # — the ON CONFLICT DO NOTHING idiom uq_pipeline_record_subject_opportunity backs.
    with db_session_factory() as session:
        second = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_id,
            matched_at=datetime.now(UTC),
        )
        session.commit()

    assert second.id == first.id
    assert second.matched_at == matched_at, "the second call must not overwrite the first row"


def test_advance_stage_walks_the_full_funnel_writing_valid_stage_timestamps(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    base = datetime.now(UTC) - timedelta(days=1)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=base,
        )
        session.commit()

        _advance_to(
            session,
            engine,
            repo,
            tenant_id=tenant_id,
            record_id=record.id,
            subject_id=subject_id,
            reached_index=len(FUNNEL_ORDER) - 1,
            base=base,
        )

        final = repo.get(session, tenant_id=tenant_id, record_id=record.id)

    assert final is not None
    assert final.reached() == frozenset(PipelineStage)
    assert final.attended_attendance_id is not None
    # ck_pipeline_record_stage_order: each timestamp is >= the one before it.
    assert final.matched_at <= final.contacted_at <= final.confirmed_at
    assert final.confirmed_at <= final.attended_at <= final.member_inquiry_at


def test_advance_stage_refuses_a_stage_whose_prerequisite_is_unreached(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """Refused in application code, before any SQL is issued.

    The database's own ``ck_pipeline_record_stage_prefix`` is proven
    separately, over raw SQL, in ``test_pipeline_record_constraints.py``; this
    is the repository's own precondition, which must refuse the identical
    write for the identical reason.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC),
        )
        session.commit()

        with pytest.raises(InvalidPipelineStageTransitionError):
            repo.advance_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=PipelineStage.CONFIRMED,
                reached_at=datetime.now(UTC),
            )


def test_advance_stage_refuses_attended_without_real_evidence(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """ck_pipeline_record_attendance_evidence's biconditional, refused up front."""
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC) - timedelta(hours=3),
        )
        session.commit()
        repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONTACTED,
            reached_at=datetime.now(UTC) - timedelta(hours=2),
        )
        repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONFIRMED,
            reached_at=datetime.now(UTC) - timedelta(hours=1),
        )
        session.commit()

        with pytest.raises(ValueError, match="attended_attendance_id"):
            repo.advance_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=PipelineStage.ATTENDED,
                reached_at=datetime.now(UTC),
            )


def test_advance_stage_reports_a_missing_record_rather_than_raising(
    tenant_id: uuid.UUID, repo: PipelineRepository, db_session_factory: sessionmaker[Session]
) -> None:
    with db_session_factory() as session:
        outcome = repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=uuid.uuid4(),
            stage=PipelineStage.CONTACTED,
            reached_at=datetime.now(UTC),
        )

    assert outcome.exists is False
    assert outcome.transitioned is False
    assert outcome.record is None


def test_advance_stage_reports_already_reached_without_transitioning(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """A second call for a stage already reached: exists=True, transitioned=False.

    Distinct from the missing-record case (exists=False) and from a lost race
    (also transitioned=False but reached concurrently) —
    ``PipelineStageOutcome.already_reached`` is what tells this apart from
    both, per that class's own docstring (CRITICAL 2).
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC) - timedelta(hours=2),
        )
        session.commit()

        first = repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONTACTED,
            reached_at=datetime.now(UTC) - timedelta(hours=1),
        )
        session.commit()
        assert first.transitioned is True
        assert first.already_reached is False
        assert first.record is not None

        second = repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONTACTED,
            reached_at=datetime.now(UTC),
        )

    assert second.exists is True
    assert second.transitioned is False
    assert second.already_reached is True
    assert second.record is not None
    assert second.record.contacted_at == first.record.contacted_at, (
        "the second call's own reached_at must not overwrite the first transition's"
    )


def test_advance_stage_refuses_reached_at_before_the_prerequisite(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """The application-code twin of ``ck_pipeline_record_stage_order`` (CRITICAL 1).

    Raised as :class:`PipelineStageOrderError`, not an ``IntegrityError`` —
    and the session must survive the refusal, unlike a statement that reached
    the database and aborted the transaction: a genuine transition right
    after still succeeds.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    matched_at = datetime.now(UTC) - timedelta(hours=1)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=matched_at,
        )
        session.commit()

        with pytest.raises(PipelineStageOrderError):
            repo.advance_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=PipelineStage.CONTACTED,
                reached_at=matched_at - timedelta(hours=1),
            )

        # The transaction is not aborted by the refusal above: a legitimate
        # transition immediately afterward still commits cleanly.
        outcome = repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONTACTED,
            reached_at=matched_at + timedelta(hours=1),
        )
        session.commit()

    assert outcome.transitioned is True


def test_get_and_advance_stage_refuse_a_valid_record_id_under_a_foreign_tenant(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """The composite ``(tenant_id, id)`` scope, proven for the write path too.

    ``test_pipeline_record_constraints.py`` proves this isolation for writes
    at the schema layer; this is the identical property for
    :meth:`PipelineRepository.get` and :meth:`PipelineRepository.advance_stage`
    — a real ``record_id`` paired with a tenant that does not own it must be
    invisible, not found by mistake.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC),
        )
        session.commit()

    foreign_tenant = uuid.uuid4()
    slug = f"test-pipeline-foreign-{foreign_tenant.hex[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": foreign_tenant, "slug": slug, "name": slug},
        )
    try:
        with db_session_factory() as session:
            assert repo.get(session, tenant_id=foreign_tenant, record_id=record.id) is None

            outcome = repo.advance_stage(
                session,
                tenant_id=foreign_tenant,
                record_id=record.id,
                stage=PipelineStage.CONTACTED,
                reached_at=datetime.now(UTC),
            )
        assert outcome.exists is False
        assert outcome.transitioned is False
        assert outcome.record is None
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": foreign_tenant})


def test_advance_stage_refuses_the_matched_stage(
    tenant_id: uuid.UUID, repo: PipelineRepository, db_session_factory: sessionmaker[Session]
) -> None:
    """MATCHED is opened by record_matched; advance_stage must never accept it."""
    with db_session_factory() as session, pytest.raises(ValueError, match="MATCHED"):
        repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=uuid.uuid4(),
            stage=PipelineStage.MATCHED,
            reached_at=datetime.now(UTC),
        )


def test_advance_stage_refuses_attended_attendance_id_on_a_non_attended_stage(
    tenant_id: uuid.UUID, repo: PipelineRepository, db_session_factory: sessionmaker[Session]
) -> None:
    """A claim citing evidence for a stage that is not Attended has nowhere valid to put it."""
    with (
        db_session_factory() as session,
        pytest.raises(ValueError, match="attended_attendance_id"),
    ):
        repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=uuid.uuid4(),
            stage=PipelineStage.CONTACTED,
            reached_at=datetime.now(UTC),
            attended_attendance_id=uuid.uuid4(),
        )


def test_advance_stage_refuses_a_bogus_attended_attendance_id(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """A present but bogus id is refused before the UPDATE (HIGH 4).

    Distinct from ``test_advance_stage_refuses_attended_without_real_evidence``,
    which exercises the id's *absence*. Here the id is present but names no
    real ``attendance_record`` row, which a composite foreign key alone would
    otherwise turn into an aborted transaction; the session must survive the
    refusal, so a real attendance row can advance the same journey right
    after.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC) - timedelta(hours=3),
        )
        session.commit()
        repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONTACTED,
            reached_at=datetime.now(UTC) - timedelta(hours=2),
        )
        repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.CONFIRMED,
            reached_at=datetime.now(UTC) - timedelta(hours=1),
        )
        session.commit()

        with pytest.raises(UnknownAttendanceEvidenceError):
            repo.advance_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=PipelineStage.ATTENDED,
                reached_at=datetime.now(UTC),
                attended_attendance_id=uuid.uuid4(),
            )

        with engine.begin() as conn:
            attendance_id = _insert_attendance(conn, tenant_id, subject_id)
        outcome = repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record.id,
            stage=PipelineStage.ATTENDED,
            reached_at=datetime.now(UTC),
            attended_attendance_id=attendance_id,
        )
        session.commit()

    assert outcome.transitioned is True


def test_record_matched_refuses_a_naive_matched_at(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session, pytest.raises(ValueError, match="timezone-aware"):
        repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(),
        )


def test_advance_stage_refuses_a_naive_reached_at(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC),
        )
        session.commit()

        with pytest.raises(ValueError, match="timezone-aware"):
            repo.advance_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=PipelineStage.CONTACTED,
                reached_at=datetime.now(),
            )


def test_record_matched_refuses_a_conflicting_owning_unit_id(
    engine: Engine,
    tenant_id: uuid.UUID,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """A second call naming a different unit for the same journey is refused, not absorbed.

    ``ON CONFLICT DO NOTHING`` would otherwise silently keep the first call's
    ``owning_unit_id`` — see :class:`ConflictingOwningUnitError`'s own
    docstring for why that is a funnel miscount rather than a harmless
    replay.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        other_unit_id = _make_unit(conn, tenant_id, "iawest.pipelineconflict")
        subject_id = _make_user(conn, tenant_id)
    opportunity_id = uuid.uuid4()

    with db_session_factory() as session:
        repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_id,
            matched_at=datetime.now(UTC),
        )
        session.commit()

        with pytest.raises(ConflictingOwningUnitError):
            repo.record_matched(
                session,
                tenant_id=tenant_id,
                owning_unit_id=other_unit_id,
                subject_id=subject_id,
                opportunity_event_id=opportunity_id,
                matched_at=datetime.now(UTC),
            )


# ---------------------------------------------------------------------------
# ADR-0011 rule 3, end to end: repository write -> HTTP aggregate == drill-down
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _WriterContext:
    client: TestClient
    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    token: str
    actor_id: uuid.UUID
    session_factory: sessionmaker[Session]


def _make_client(engine: Engine) -> TestClient:
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = FixtureTokenVerifier()
    return client


def _register_coordinator(
    engine: Engine, client: TestClient, tenant_id: uuid.UUID, unit_path: str
) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    subject = unique_subject(f"pipeline-writer-{user_id.hex[:8]}")
    token = f"tok-pipeline-writer-{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "sub": subject,
                "email": f"{user_id.hex[:8]}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": unit_path},
        )
    client.app.state.token_verifier.register(token, subject)
    return token, user_id


def _get(client: TestClient, path: str, token: str) -> httpx.Response:
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def writer_context(
    engine: Engine, tenant_id: uuid.UUID, db_session_factory: sessionmaker[Session]
) -> Iterator[_WriterContext]:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
    client = _make_client(engine)
    token, actor_id = _register_coordinator(engine, client, tenant_id, JOB_OWNING_UNIT_PATH)
    yield _WriterContext(
        client=client,
        tenant_id=tenant_id,
        unit_id=unit_id,
        token=token,
        actor_id=actor_id,
        session_factory=db_session_factory,
    )


def test_metrics_aggregate_and_drill_down_each_return_n_rows_for_n_pipeline_records(
    writer_context: _WriterContext, engine: Engine, repo: PipelineRepository
) -> None:
    """Five journeys stopping at five different stages, written by the repository.

    Expected counts are ``[5, 4, 3, 2, 1]`` — the same cumulative-funnel shape
    ``test_the_funnel_never_widens_as_it_deepens`` proves at the storage layer
    — and every stage's HTTP aggregate must equal its drill-down's row count,
    which is ADR-0011 rule 3 exercised against rows this file's own write path
    produced rather than rows a raw-SQL test helper produced on its behalf.
    """
    ctx = writer_context
    base = datetime.now(UTC) - timedelta(days=2)
    written_ids: dict[PipelineStage, set[str]] = {stage: set() for stage in FUNNEL_ORDER}

    for reached_index, _stage in enumerate(FUNNEL_ORDER):
        with engine.begin() as conn:
            subject_id = _make_user(conn, ctx.tenant_id)

        with ctx.session_factory() as session:
            record = repo.record_matched(
                session,
                tenant_id=ctx.tenant_id,
                owning_unit_id=ctx.unit_id,
                subject_id=subject_id,
                opportunity_event_id=uuid.uuid4(),
                matched_at=base,
            )
            session.commit()

            _advance_to(
                session,
                engine,
                repo,
                tenant_id=ctx.tenant_id,
                record_id=record.id,
                subject_id=subject_id,
                reached_index=reached_index,
                base=base,
            )

        # This journey reached every stage up to and including reached_index.
        for i in range(reached_index + 1):
            written_ids[FUNNEL_ORDER[i]].add(str(record.id))

    expected_counts = {stage: len(ids) for stage, ids in written_ids.items()}
    assert list(expected_counts.values()) == [5, 4, 3, 2, 1]

    aggregate_response = _get(ctx.client, f"/v1/units/{ctx.unit_id}/metrics", ctx.token)
    assert aggregate_response.status_code == 200
    by_name = {item["name"]: item for item in aggregate_response.json()["metrics"]}

    for stage, metric_name in _STAGE_METRIC_NAMES.items():
        assert by_name[metric_name]["value"] == expected_counts[stage], metric_name
        assert by_name[metric_name]["unknown_reason"] is None, metric_name

        drill_response = _get(
            ctx.client, f"/v1/units/{ctx.unit_id}/metrics/{metric_name}/drill-down", ctx.token
        )
        assert drill_response.status_code == 200
        drill_down = drill_response.json()

        assert drill_down["aggregate_value"] == expected_counts[stage], metric_name
        assert len(drill_down["rows"]) == expected_counts[stage], metric_name
        assert {row["id"] for row in drill_down["rows"]} == written_ids[stage], metric_name
