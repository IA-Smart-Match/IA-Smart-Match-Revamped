"""Shared fixtures for tests that need a real PostgreSQL instance.

These tests are skipped automatically when no database is reachable, so the unit
suite still runs anywhere. Run them with ``make test-integration``.

Besides the fixtures, this module exports :func:`unique_subject`, which every
test that writes a ``user_account`` should route its identity-provider subject
through. See its docstring for why a fixed literal is no longer safe.
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

#: A token distinguishing this pytest session's rows from any earlier session's.
#: Regenerated on every run, so a row left behind by a run that was killed —
#: which on this project is the ordinary case, not the edge case — cannot collide
#: with a row this run creates.
_RUN_TOKEN = uuid.uuid4().hex[:8]


def unique_subject(name: str) -> str:
    """Suffix an identity-provider subject so it cannot collide across runs.

    ``external_subject`` is globally unique as of migration ``0003``, which
    removed the tenant from the uniqueness key. That is what makes
    ``load_by_subject`` correct, and it is also what turns a single stale
    ``user_account`` row into a suite-wide failure: before ``0003`` a leftover
    ``'sub-coordinator'`` in some abandoned tenant was invisible to a test
    creating ``'sub-coordinator'`` in its own tenant, and now it is a
    ``UniqueViolation`` at fixture setup, in every test that builds that account.
    The failure names the constraint rather than the leftover row, so the cause
    is not obvious from the output.

    The suffix is per *session*, not per call, so the same name resolves to the
    same subject everywhere within one run — the account insert and the token
    registration that must agree about it, and the tests that look an account up
    by subject in SQL. Readability is deliberately preserved: the literal is
    still the first thing in the string, so ``sub-coordinator-9f3a1c07`` reads in
    a failure message the way ``sub-coordinator`` did.

    This is a per-run namespace and not a cleanup: nothing here deletes a row it
    does not own. ``_clean_dispatch_state`` clears the coordination tables for
    the same reason, and identity rows are the half it deliberately leaves alone.
    """
    return f"{name}-{_RUN_TOKEN}"


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
