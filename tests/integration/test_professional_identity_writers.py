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

import ast
import inspect
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from types import ModuleType

import pytest

pytest.importorskip("sqlalchemy")

from conftest import JOB_OWNING_UNIT_PATH, ensure_owning_unit, unique_subject
from smartmatch_domain.synthetic_pilot import (
    SYNTHETIC_BOARD_ROLE,
    synthetic_professional_email,
    synthetic_professional_external_subject,
    synthetic_professional_subject_id,
)
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

#: Score-shaped identifier fragments — see
#: :func:`_fabricated_score_identifiers`'s own docstring for why these are
#: checked against identifiers only, never against prose.
_FABRICATED_SCORE_TOKENS = ("score", "confidence", "match_score", "rank", "weight")


def _fabricated_score_identifiers(module: ModuleType) -> list[str]:
    """Score-shaped names used as assignment targets, parameters, or keyword/column names.

    Walks the module's AST rather than grepping its raw source text, so a
    docstring or comment stating that the module computes no score of any
    kind cannot fail this check for containing the word. Only identifiers —
    variables, attributes, function parameters, keyword/column arguments to
    a call, and function names — are inspected.
    """
    tree = ast.parse(inspect.getsource(module))
    offenders: list[str] = []
    for node in ast.walk(tree):
        name: str | None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            name = node.id
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            name = node.attr
        elif isinstance(node, ast.arg | ast.keyword):
            name = node.arg
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = node.name
        else:
            name = None
        if name is not None and any(token in name.lower() for token in _FABRICATED_SCORE_TOKENS):
            offenders.append(name)
    return offenders


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
            board_role=SYNTHETIC_BOARD_ROLE,
        )
        session.commit()

    with db_session_factory() as session:
        second = repo.link_to_unit(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            unit_id=unit_id,
            board_role=SYNTHETIC_BOARD_ROLE,
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
    assert rows[0].board_role == SYNTHETIC_BOARD_ROLE


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
                board_role=SYNTHETIC_BOARD_ROLE,
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
            board_role=SYNTHETIC_BOARD_ROLE,
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
# Derived values — Card 2's derivation exercised against this writer, live
# ---------------------------------------------------------------------------
#
# Every test above mints its own ad hoc external_subject/email pair via
# _account_kwargs, never the real derivation a production caller would use.
# The two tests below close that gap: they call
# smartmatch_domain.synthetic_pilot's actual derivation functions and assert
# on the persistence-layer consequences ensure_account's own docstring
# claims for each direction of the "external_subject derived from
# subject_id" argument.


def test_ensure_account_with_derived_values_does_not_collide_across_tenants(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """The safe direction: two tenants, one name, real derived values, no collision.

    ``synthetic_professional_subject_id`` folds ``tenant_id`` into its hash
    input precisely so that two tenants' same-named professionals derive
    different subject ids — and therefore, because ``external_subject`` is
    derived *from* ``subject_id``, different external subjects. This is what
    keeps ``uq_user_account_external_subject`` (globally unique, not
    per-tenant) from firing here. Proven against a live database, not just
    asserted at the derivation layer (``test_synthetic_pilot_identity.py``
    already covers that the *ids* differ; this covers that the *persisted
    rows* do not collide).
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)

    other_tenant = uuid.uuid4()
    slug = f"test-professionals-derived-{other_tenant.hex[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": other_tenant, "slug": slug, "name": slug},
        )
        other_unit_id = _make_unit(conn, other_tenant, JOB_OWNING_UNIT_PATH)

    name = "Ada Lovelace"
    subject_id_a = synthetic_professional_subject_id(
        tenant_id=tenant_id, unit_id=unit_id, name=name
    )
    subject_id_b = synthetic_professional_subject_id(
        tenant_id=other_tenant, unit_id=other_unit_id, name=name
    )
    assert subject_id_a != subject_id_b, "the derivation itself must separate tenants"

    try:
        with db_session_factory() as session:
            created_a = repo.ensure_account(
                session,
                tenant_id=tenant_id,
                subject_id=subject_id_a,
                external_subject=synthetic_professional_external_subject(subject_id_a),
                email=synthetic_professional_email(subject_id_a),
            )
            created_b = repo.ensure_account(
                session,
                tenant_id=other_tenant,
                subject_id=subject_id_b,
                external_subject=synthetic_professional_external_subject(subject_id_b),
                email=synthetic_professional_email(subject_id_b),
            )
            session.commit()
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": other_tenant}
            )
            conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant})

    assert created_a is True
    assert created_b is True


def test_ensure_account_keeps_first_external_subject_on_repeat(
    tenant_id: uuid.UUID,
    engine: Engine,
    repo: ProfessionalIdentityRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """The unsafe direction ``ensure_account``'s own docstring now names.

    A repeated call for the same ``subject_id`` conflicts on
    ``user_account_pkey`` before ``uq_user_account_external_subject`` is
    ever consulted, so a *different* ``external_subject`` on the second call
    is silently discarded: the method returns ``False``, and the row keeps
    the first call's value. This is intentional first-write-wins behaviour —
    the same idiom ``PipelineRepository.record_matched`` documents for
    ``matched_provenance`` under idempotency — proven here rather than left
    as an unchecked assumption in the module's docstring.
    """
    first_kwargs = _account_kwargs("divergence-first")
    subject_id = first_kwargs["subject_id"]
    assert isinstance(subject_id, uuid.UUID)

    with db_session_factory() as session:
        first = repo.ensure_account(session, tenant_id=tenant_id, **first_kwargs)
        session.commit()

    different_external_subject = unique_subject(
        f"synthetic-professional-divergence-second-{subject_id.hex[:8]}"
    )
    different_email = f"different-{subject_id}@synthetic.invalid"

    with db_session_factory() as session:
        second = repo.ensure_account(
            session,
            tenant_id=tenant_id,
            subject_id=subject_id,
            external_subject=different_external_subject,
            email=different_email,
        )
        session.commit()

    assert first is True
    assert second is False

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT external_subject, email FROM user_account WHERE id = :id"),
            {"id": subject_id},
        ).one()

    assert row.external_subject == first_kwargs["external_subject"], (
        "the second call's differing external_subject must not overwrite the first"
    )
    assert row.email == first_kwargs["email"]
    assert row.external_subject != different_external_subject


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
                board_role=SYNTHETIC_BOARD_ROLE,
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


def test_module_stores_no_fabricated_score_identifier() -> None:
    offenders = _fabricated_score_identifiers(professionals_module)
    assert not offenders, f"score-shaped identifier(s) found in professionals.py: {offenders}"
