"""Shared fixtures for tests that need a real PostgreSQL instance.

These tests are skipped automatically when no database is reachable, so the unit
suite still runs anywhere. Run them with ``make test-integration``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

#: Deleted in dependency order during teardown. Tenants are ON DELETE RESTRICT by
#: design — a tenant with live data must not vanish because a row was removed —
#: so children go first.
_TENANT_SCOPED_TABLES = (
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
)


@pytest.fixture(scope="session")
def engine() -> Engine:
    """A connected engine, or skip the whole module."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Session factory bound to the test engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True)
def _clean_dispatch_state(engine: Engine) -> Iterator[None]:
    """Clear jobs and outbox rows left by earlier runs.

    The dispatcher's claim query is deliberately global — it serves every tenant,
    and a per-tenant claim would let one tenant's backlog starve another. That
    makes dispatcher tests sensitive to rows an aborted earlier run left behind,
    so each test starts from a clean dispatch state rather than a merely clean
    tenant.

    Only the coordination tables are cleared. Tenants and their identity rows are
    owned by the fixtures that create them.
    """
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job_event"))
        conn.execute(text("DELETE FROM outbox_record"))
        conn.execute(text("DELETE FROM redrive_record"))
        conn.execute(text("DELETE FROM job"))
    yield


@pytest.fixture
def tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    """Create one isolated tenant, and clean up everything it owns."""
    tid = uuid.uuid4()
    slug = f"test-{tid.hex[:12]}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": tid, "slug": slug, "name": slug},
        )

    yield tid

    with engine.begin() as conn:
        for table in _TENANT_SCOPED_TABLES:
            conn.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tid"),
                {"tid": tid},
            )
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})
