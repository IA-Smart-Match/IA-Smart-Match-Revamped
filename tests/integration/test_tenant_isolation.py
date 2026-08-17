"""Integration tests proving tenant isolation is enforced by the database.

Architecture v1.1 §2.2 claims tenant isolation is *structural* — that a
cross-tenant reference is invalid at the database layer rather than prevented by
a ``WHERE tenant_id = ?`` clause someone might forget. These tests hold that
claim to account against a real PostgreSQL instance.

Requires a live database. Skipped automatically when one is not configured, so
the unit suite still runs anywhere.

Run locally with::

    make db-up && make test-integration
"""

from __future__ import annotations

import os
import uuid

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)


@pytest.fixture(scope="module")
def engine():
    """Connect, or skip the module if no database is reachable."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def tenants(engine):
    """Create two isolated tenants, and clean them up afterwards."""
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        for tid, slug in ((tenant_a, f"a-{tid_slug()}"), (tenant_b, f"b-{tid_slug()}")):
            conn.execute(
                text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
                {"id": tid, "slug": slug, "name": slug},
            )
    yield tenant_a, tenant_b

    # Tenants are ON DELETE RESTRICT by design — a tenant with live data must
    # not vanish because someone deleted a row. Teardown therefore removes
    # children explicitly, in dependency order.
    with engine.begin() as conn:
        for table in (
            "job_event",
            "outbox_record",
            "redrive_record",
            "job",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "tenant_budget",
            "concurrency_lease",
            "idempotency_record",
        ):
            conn.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )
        for tid in (tenant_a, tenant_b):
            conn.execute(text("DELETE FROM tenant WHERE id = :id"), {"id": tid})


def tid_slug() -> str:
    return uuid.uuid4().hex[:8]


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
            "sub": f"sub-{user_id.hex[:8]}",
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _make_job(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status) "
            "VALUES (:id, :tenant_id, 'noop', 'queued')"
        ),
        {"id": job_id, "tenant_id": tenant_id},
    )
    return job_id


# ---------------------------------------------------------------------------
# The core claim
# ---------------------------------------------------------------------------


def test_membership_cannot_reference_a_user_in_another_tenant(engine, tenants):
    """The composite foreign key rejects the cross-tenant write outright."""
    tenant_a, tenant_b = tenants
    with engine.begin() as conn:
        user_in_a = _make_user(conn, tenant_a)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tenant_id, :user_id, 'root'::ltree, 'coordinator')"
            ),
            # tenant_b claiming a user that belongs to tenant_a
            {"id": uuid.uuid4(), "tenant_id": tenant_b, "user_id": user_in_a},
        )


def test_job_event_cannot_reference_a_job_in_another_tenant(engine, tenants):
    tenant_a, tenant_b = tenants
    with engine.begin() as conn:
        job_in_a = _make_job(conn, tenant_a)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                "VALUES (:id, :tenant_id, :job_id, 1, '{}'::jsonb)"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_b, "job_id": job_in_a},
        )


def test_outbox_cannot_reference_a_job_in_another_tenant(engine, tenants):
    tenant_a, tenant_b = tenants
    with engine.begin() as conn:
        job_in_a = _make_job(conn, tenant_a)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO outbox_record (id, tenant_id, job_id, task_name) "
                "VALUES (:id, :tenant_id, :job_id, :task)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_b,
                "job_id": job_in_a,
                "task": f"task-{uuid.uuid4().hex[:8]}",
            },
        )


def test_same_tenant_references_are_accepted(engine, tenants):
    """The constraint blocks cross-tenant writes without blocking correct ones."""
    tenant_a, _ = tenants
    with engine.begin() as conn:
        job = _make_job(conn, tenant_a)
        conn.execute(
            text(
                "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                "VALUES (:id, :tenant_id, :job_id, 1, '{}'::jsonb)"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_a, "job_id": job},
        )


# ---------------------------------------------------------------------------
# Supporting constraints
# ---------------------------------------------------------------------------


def test_job_status_check_rejects_an_unknown_state(engine, tenants):
    """The CHECK constraint mirrors the domain state machine."""
    tenant_a, _ = tenants
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job (id, tenant_id, command_type, status) "
                "VALUES (:id, :tenant_id, 'noop', 'not_a_real_state')"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_a},
        )


def test_job_event_sequence_is_unique_per_job(engine, tenants):
    """SSE reconnect correctness depends on a monotonic, gapless-per-job sequence."""
    tenant_a, _ = tenants
    with engine.begin() as conn:
        job = _make_job(conn, tenant_a)
        conn.execute(
            text(
                "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                "VALUES (:id, :tenant_id, :job_id, 1, '{}'::jsonb)"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_a, "job_id": job},
        )

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                "VALUES (:id, :tenant_id, :job_id, 1, '{}'::jsonb)"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_a, "job_id": job},
        )


def test_outbox_task_name_is_globally_unique(engine, tenants):
    """Deterministic task names are what make duplicate dispatch a no-op."""
    tenant_a, tenant_b = tenants
    shared_name = f"task-{uuid.uuid4().hex[:8]}"

    with engine.begin() as conn:
        job_a = _make_job(conn, tenant_a)
        conn.execute(
            text(
                "INSERT INTO outbox_record (id, tenant_id, job_id, task_name) "
                "VALUES (:id, :tenant_id, :job_id, :task)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_a,
                "job_id": job_a,
                "task": shared_name,
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as conn:
        job_b = _make_job(conn, tenant_b)
        conn.execute(
            text(
                "INSERT INTO outbox_record (id, tenant_id, job_id, task_name) "
                "VALUES (:id, :tenant_id, :job_id, :task)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_b,
                "job_id": job_b,
                "task": shared_name,
            },
        )


def test_budget_ceiling_cannot_go_negative(engine, tenants):
    tenant_a, _ = tenants
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling) "
                "VALUES (:tenant_id, 'email', -5)"
            ),
            {"tenant_id": tenant_a},
        )


def test_transactional_budget_reservation_cannot_exceed_the_ceiling(engine, tenants):
    """v1.1 §2.4: budget is enforced with `UPDATE ... WHERE spent + x <= ceiling`.

    Proves the pattern works — the over-limit update matches zero rows rather
    than succeeding, which is what makes it correct across any number of
    instances.
    """
    tenant_a, _ = tenants
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling, spent) "
                "VALUES (:tenant_id, 'email', 100, 90)"
            ),
            {"tenant_id": tenant_a},
        )

    with engine.begin() as conn:
        over = conn.execute(
            text(
                "UPDATE tenant_budget SET spent = spent + 20 "
                "WHERE tenant_id = :tenant_id AND provider = 'email' "
                "AND spent + 20 <= ceiling"
            ),
            {"tenant_id": tenant_a},
        )
        assert over.rowcount == 0, "an over-ceiling reservation must not succeed"

        within = conn.execute(
            text(
                "UPDATE tenant_budget SET spent = spent + 5 "
                "WHERE tenant_id = :tenant_id AND provider = 'email' "
                "AND spent + 5 <= ceiling"
            ),
            {"tenant_id": tenant_a},
        )
        assert within.rowcount == 1


def test_ltree_subtree_query_works(engine, tenants):
    """The tree must actually be queryable by subtree containment."""
    tenant_a, _ = tenants
    with engine.begin() as conn:
        for path in ("iawest", "iawest.cpp", "iawest.cpp.eng", "iawest.other"):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tenant_id, CAST(:path AS ltree), 'unit', :path)"
                ),
                {"id": uuid.uuid4(), "tenant_id": tenant_a, "path": path},
            )

        rows = (
            conn.execute(
                text(
                    "SELECT path::text FROM org_unit "
                    "WHERE tenant_id = :tenant_id AND path <@ 'iawest.cpp'::ltree "
                    "ORDER BY path"
                ),
                {"tenant_id": tenant_a},
            )
            .scalars()
            .all()
        )

    assert rows == ["iawest.cpp", "iawest.cpp.eng"]


def test_org_unit_path_is_unique_per_tenant_not_globally(engine, tenants):
    """Two tenants may each have a unit at the same path; names are not identities."""
    tenant_a, tenant_b = tenants
    with engine.begin() as conn:
        for tid in (tenant_a, tenant_b):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tenant_id, 'shared.path'::ltree, 'unit', 'x')"
                ),
                {"id": uuid.uuid4(), "tenant_id": tid},
            )
