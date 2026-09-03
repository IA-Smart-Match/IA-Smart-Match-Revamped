"""``ProfessionalIdentityRepository``, against a real PostgreSQL instance (Card 3).

Proves what ``python/smartmatch_persistence/smartmatch_persistence/professionals.py``'s
own module docstring claims: every synthetic professional this repository
writes gets a real ``user_account`` row, so ``pipeline_record.subject_id``'s
``ON DELETE RESTRICT`` foreign key to ``(user_account.tenant_id,
user_account.id)`` always has something real to point at, and an orphan
``subject_id`` cannot be stored. See
:func:`test_record_matched_succeeds_for_a_linked_subject_and_refuses_an_orphan_subject`
for that property exercised end to end against ``PipelineRepository``.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")

from conftest import JOB_OWNING_UNIT_PATH, ensure_owning_unit, unique_subject
from smartmatch_persistence import professionals as professionals_module
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.pipeline import (
    MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
    PipelineRepository,
)
from smartmatch_persistence.professionals import ProfessionalIdentityRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_professional_identity_tables(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's rows for the test tenant, in dependency order.

    ``pipeline_record`` goes first (it cites ``user_account`` via
    ``ON DELETE RESTRICT``), then ``professional_unit_relationship``, then
    ``user_account`` itself — so the ``tenant_id`` fixture's own teardown,
    which also deletes ``user_account`` for this tenant, never trips over a
    row this file left behind.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture(scope="module")
def repo() -> ProfessionalIdentityRepository:
    return ProfessionalIdentityRepository()


@pytest.fixture
def db_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the live test engine.

    Mirrors ``test_pipeline_record_writers.py``'s own fixture: the
    repository under test takes an ORM ``Session``, not the raw
    ``Connection`` most of this test suite's raw-SQL helpers use.
    """
    return create_session_factory(engine.url.render_as_string(hide_password=False))


def _make_unit(conn, tenant_id: uuid.UUID, path: str) -> uuid.UUID:
    """A second unit in ``tenant_id``, for the unit-isolation tests."""
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Other Unit')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": path},
    )
    return unit_id


def _account_kwargs(label: str) -> dict[str, uuid.UUID | str]:
    """A fresh subject id plus a synthetic-shaped external_subject/email pair for it."""
    subject_id = uuid.uuid4()
    return {
        "subject_id": subject_id,
        "external_subject": unique_subject(f"synthetic-professional-{label}-{subject_id.hex[:8]}"),
        "email": f"professional-{subject_id}@synthetic.invalid",
    }


# ---------------------------------------------------------------------------
# ensure_account
# ---------------------------------------------------------------------------


def test_ensure_account_creates_once_and_is_idempotent(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    kwargs = _account_kwargs("idempotent")

    with db_session_factory() as session:
        first = repo.ensure_account(session, tenant_id=tenant_id, **kwargs)
        session.commit()

    with db_session_factory() as session:
        second = repo.ensure_account(session, tenant_id=tenant_id, **kwargs)
        session.commit()

    assert first is True
    assert second is False

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM user_account WHERE id = :id"), {"id": kwargs["subject_id"]}
        ).scalar_one()
    assert count == 1


def test_ensure_account_writes_exactly_the_values_passed(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    kwargs = _account_kwargs("exact")

    with db_session_factory() as session:
        repo.ensure_account(session, tenant_id=tenant_id, **kwargs)
        session.commit()

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, external_subject, email FROM user_account WHERE id = :id"),
            {"id": kwargs["subject_id"]},
        ).one()

    assert row.id == kwargs["subject_id"]
    assert row.external_subject == kwargs["external_subject"]
    assert row.email == kwargs["email"]


# ---------------------------------------------------------------------------
# link_to_unit
# ---------------------------------------------------------------------------


def test_link_to_unit_creates_once_and_is_idempotent(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
    kwargs = _account_kwargs("link")
    professional_id = kwargs["subject_id"]

    with db_session_factory() as session:
        repo.ensure_account(session, tenant_id=tenant_id, **kwargs)
        first = repo.link_to_unit(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            unit_id=unit_id,
            board_role="synthetic_pilot_participant",
        )
        session.commit()

    with db_session_factory() as session:
        second = repo.link_to_unit(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            unit_id=unit_id,
            board_role="synthetic_pilot_participant",
        )
        session.commit()

    assert first is True
    assert second is False

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT board_role FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :pid AND unit_id = :uid"
            ),
            {"tid": tenant_id, "pid": professional_id, "uid": unit_id},
        ).all()

    assert len(rows) == 1
    assert rows[0].board_role == "synthetic_pilot_participant"


# ---------------------------------------------------------------------------
# professional_ids_for_unit
# ---------------------------------------------------------------------------


def test_professional_ids_for_unit_returns_linked_ids_ascending_and_honours_limit(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)

    linked_ids: list[uuid.UUID] = []
    with db_session_factory() as session:
        for i in range(3):
            kwargs = _account_kwargs(f"limit-{i}")
            professional_id = kwargs["subject_id"]
            linked_ids.append(professional_id)
            repo.ensure_account(session, tenant_id=tenant_id, **kwargs)
            repo.link_to_unit(
                session,
                tenant_id=tenant_id,
                professional_id=professional_id,
                unit_id=unit_id,
                board_role="synthetic_pilot_participant",
            )
        session.commit()

    with db_session_factory() as session:
        all_ids = repo.professional_ids_for_unit(
            session, tenant_id=tenant_id, unit_id=unit_id, limit=10
        )
        limited_ids = repo.professional_ids_for_unit(
            session, tenant_id=tenant_id, unit_id=unit_id, limit=2
        )

    expected_sorted = tuple(sorted(linked_ids))
    assert all_ids == expected_sorted
    assert limited_ids == expected_sorted[:2]


def test_professional_ids_for_unit_returns_empty_for_a_unit_with_no_links(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unlinked_unit_id = _make_unit(conn, tenant_id, "iawest.profnolinks")
        linked_unit_id = ensure_owning_unit(conn, tenant_id)
    kwargs = _account_kwargs("other-unit")
    professional_id = kwargs["subject_id"]

    with db_session_factory() as session:
        repo.ensure_account(session, tenant_id=tenant_id, **kwargs)
        repo.link_to_unit(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            unit_id=linked_unit_id,
            board_role="synthetic_pilot_participant",
        )
        session.commit()

        result = repo.professional_ids_for_unit(
            session, tenant_id=tenant_id, unit_id=unlinked_unit_id, limit=10
        )

    assert result == ()


def test_professional_ids_for_unit_refuses_a_non_positive_limit(
    tenant_id: uuid.UUID,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with (
        db_session_factory() as session,
        pytest.raises(ValueError, match="limit must be at least 1"),
    ):
        repo.professional_ids_for_unit(session, tenant_id=tenant_id, unit_id=uuid.uuid4(), limit=0)


# ---------------------------------------------------------------------------
# Negative — no orphan subject_id
# ---------------------------------------------------------------------------


def test_record_matched_succeeds_for_a_linked_subject_and_refuses_an_orphan_subject(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """``ensure_account`` is what makes a ``pipeline_record`` write storable.

    A ``subject_id`` with a real ``user_account`` row succeeds; a bare
    ``uuid4()`` with no such row is refused by the database's own foreign
    key, not merely by convention. The failing call runs in its own
    session/transaction so its rollback does not poison the rest of the
    test.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
    kwargs = _account_kwargs("fk")
    subject_id = kwargs["subject_id"]

    with db_session_factory() as session:
        repo.ensure_account(session, tenant_id=tenant_id, **kwargs)
        session.commit()

    pipeline_repo = PipelineRepository()

    with db_session_factory() as session:
        record = pipeline_repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC),
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        session.commit()
    assert record.subject_id == subject_id

    orphan_subject_id = uuid.uuid4()
    with (
        db_session_factory() as session,
        pytest.raises(IntegrityError, match="pipeline_record_tenant_id_subject_id_fkey"),
    ):
        pipeline_repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=orphan_subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC),
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        session.commit()


# ---------------------------------------------------------------------------
# Negative — a foreign-tenant unit is not reachable
# ---------------------------------------------------------------------------


def test_professional_ids_for_unit_does_not_reach_a_foreign_tenants_unit(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    foreign_tenant = uuid.uuid4()
    slug = f"test-professionals-foreign-{foreign_tenant.hex[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": foreign_tenant, "slug": slug, "name": slug},
        )
        foreign_unit_id = _make_unit(conn, foreign_tenant, JOB_OWNING_UNIT_PATH)
        foreign_kwargs = _account_kwargs("foreign")
    try:
        with db_session_factory() as session:
            repo.ensure_account(session, tenant_id=foreign_tenant, **foreign_kwargs)
            repo.link_to_unit(
                session,
                tenant_id=foreign_tenant,
                professional_id=foreign_kwargs["subject_id"],
                unit_id=foreign_unit_id,
                board_role="synthetic_pilot_participant",
            )
            session.commit()

            # tenant_id (the fixture's own tenant) scoped against the
            # *foreign* tenant's unit id must see nothing.
            result = repo.professional_ids_for_unit(
                session, tenant_id=tenant_id, unit_id=foreign_unit_id, limit=10
            )
        assert result == ()
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
                {"tid": foreign_tenant},
            )
            conn.execute(
                text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": foreign_tenant}
            )
            conn.execute(
                text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": foreign_tenant}
            )
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": foreign_tenant})


# ---------------------------------------------------------------------------
# Negative — no fabricated score
# ---------------------------------------------------------------------------


def test_module_contains_no_fabricated_score_vocabulary() -> None:
    source = inspect.getsource(professionals_module).lower()

    for forbidden in ("score", "confidence", "match_score", "rank", "weight"):
        assert forbidden not in source, f"forbidden token {forbidden!r} found in professionals.py"
