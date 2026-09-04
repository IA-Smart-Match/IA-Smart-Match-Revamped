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
from datetime import date
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from smartmatch_domain.events import normalize_title
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
    # Migration 0018. Before `job`, which it references ON DELETE RESTRICT, and
    # before `org_unit` for the same reason. It is deletable even though its
    # rows are immutable: 0018 blocks UPDATE only, because retention is a
    # question that card does not decide and a table nothing could delete from
    # would make its tenant undeletable.
    "match_run",
    # Migration 0021, in dependency order among themselves and all before
    # `job`, which `outreach_send` references ON DELETE RESTRICT — the same
    # ordering hazard `match_run` above records. `suppression_record` is listed
    # with them although it references only `tenant`: this tuple is read as the
    # full set of tenant-scoped tables, not as the minimum a cascade would miss.
    "delivery_event",
    "outreach_send",
    "outreach_draft",
    "contact_channel",
    "suppression_record",
    "job",
    "membership",
    "resource_grant",
    # Migration 0017. Both cascade from `event`, and are listed anyway so this
    # tuple stays the full set of tenant-scoped tables — which is how a reader
    # uses it — rather than only the rows a cascade would have reached.
    "event_tag",
    "discovery_review_item",
    # Before `user_account` and `org_unit`, both of which `event` and
    # `discovery_review_item` hold ON DELETE RESTRICT references to.
    # `attendance_record` is deliberately still not in this tuple: it also
    # references `event` under RESTRICT, and the test modules that write it
    # delete it in their own fixtures, which finalize before this one does.
    "event",
    # Migration 0020. Both cascade from `user_account`, and both are listed
    # before it for the reason `event_tag` is listed before `event`: this tuple
    # is read as the full set of tenant-scoped tables, not as the minimum set a
    # cascade would not already reach. Getting the *order* wrong here is the
    # failure PR #26 had to fix for `match_run`/`job`, so they go above
    # `user_account` rather than beside it.
    "pilot_session",
    "pilot_credential",
    "user_account",
    "org_unit",
    "tenant_budget",
    "spend_reservation",
    "spend_ceiling_bucket",
    "concurrency_lease",
    "idempotency_record",
    # Belt and braces rather than a leak fixed: this table's tenant foreign key
    # is ON DELETE CASCADE, so deleting the tenant below already removed its
    # counters. Listed anyway so the tuple is the full set of tenant-scoped
    # tables, which is how a reader will use it.
    "rate_limit_counter",
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

    ``match_run`` is cleared here too, and it is the one table in this sweep that
    is not itself a coordination table. Migration ``0018`` gives it an
    ``ON DELETE RESTRICT`` foreign key to ``job``, so a run left behind by an
    aborted earlier run would make the ``DELETE FROM job`` below fail — in
    *every* test, including every test written before that table existed. It is
    deleted first for that reason, and it is safe to delete globally for the
    same reason ``job`` is: nothing but these tests writes one today.
    """
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job_event"))
        conn.execute(text("DELETE FROM outbox_record"))
        conn.execute(text("DELETE FROM redrive_record"))
        conn.execute(text("DELETE FROM match_run"))
        # Migration 0021, for exactly the reason `match_run` is here: both hold
        # an ON DELETE RESTRICT foreign key to `job`, so a send left behind by
        # an aborted earlier run would make the `DELETE FROM job` below fail in
        # *every* test, including every test written before these tables
        # existed. `delivery_event` first, since it RESTRICTs against
        # `outreach_send` in turn.
        conn.execute(text("DELETE FROM delivery_event"))
        conn.execute(text("DELETE FROM outreach_send"))
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


#: Path of the unit :func:`ensure_owning_unit` creates. Fixed rather than
#: generated, which is what makes that function idempotent: every tenant gets one
#: unit at this path and `uq_org_unit_tenant_path` is scoped per tenant, so two
#: tests in the same tenant converge on the same row instead of colliding.
JOB_OWNING_UNIT_PATH = "iawest.jobs"


def ensure_owning_unit(executor: Any, tenant_id: uuid.UUID) -> uuid.UUID:
    """Return the test tenant's job-owning unit, creating it once if absent.

    Migration ``0006`` made ``job.owning_unit_id`` ``NOT NULL``, so a job now
    needs a unit the way it has always needed a tenant. Most integration tests
    are not *about* the unit — they are about dispatch, re-drive, or worker
    execution — and threading one through their signatures would have changed a
    hundred call sites to say the same uninteresting thing. So the helpers that
    build a job call this instead, and the tests are left alone.

    Takes any object with SQLAlchemy's ``.execute(text, params)`` — a ``Session``
    or a ``Connection`` — because the callers have one or the other and neither
    should have to care.

    Tests that are genuinely *about* unit scoping (``test_job_owning_unit.py``,
    the authorization matrix) create their own units at their own paths, since
    the point there is that two units differ.

    No cleanup: ``org_unit`` is in :data:`_TENANT_SCOPED_TABLES`, and ``job`` is
    deleted before it in that order, so ``fk_job_owning_unit``'s ``ON DELETE
    RESTRICT`` never blocks teardown.
    """
    existing = executor.execute(
        text("SELECT id FROM org_unit WHERE tenant_id = :tid AND path = CAST(:path AS ltree)"),
        {"tid": tenant_id, "path": JOB_OWNING_UNIT_PATH},
    ).scalar_one_or_none()
    if existing is not None:
        return uuid.UUID(str(existing))

    unit_id = uuid.uuid4()
    executor.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Test Jobs Unit')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": JOB_OWNING_UNIT_PATH},
    )
    return unit_id


#: Title of the synthetic event :func:`ensure_event` creates, before the ``slug``
#: suffix. Fixed rather than generated, for the same reason
#: :data:`JOB_OWNING_UNIT_PATH` is: `uq_event_identity` is scoped per tenant, so
#: two tests in one tenant asking for the same slug converge on the same row
#: instead of colliding.
SYNTHETIC_EVENT_TITLE = "Synthetic Pilot Event"

#: The date :func:`ensure_event` resolves its events to. A fixed literal, not
#: `date.today()`: the identity key folds this date in, so a generated one would
#: make the helper non-idempotent across a midnight boundary — the kind of
#: once-a-day flake nobody reproduces.
SYNTHETIC_EVENT_DATE = date(2026, 9, 14)


def ensure_event(executor: Any, tenant_id: uuid.UUID, slug: str = "default") -> uuid.UUID:
    """Return a synthetic ``event`` row for this tenant, creating it once if absent.

    Migration ``0017`` gave ``attendance_record.event_id`` the foreign key
    ``0009`` said "whichever migration adds one should also add", which means an
    attendance row now needs an event the way a job has needed a unit since
    ``0006``. Most tests that write attendance are not *about* the event — they
    are about points, funnel stages, or the method vocabulary — and threading a
    real event through their signatures would have changed a lot of call sites
    to say the same uninteresting thing. So they call this, exactly as they
    already call :func:`ensure_owning_unit`, and the tests are left alone.

    ``slug`` distinguishes events within one tenant, for the tests that are
    genuinely about two *different* events —
    ``uq_attendance_record_subject_event`` needs a second one to prove a student
    can attend twice at different events. It varies the title, so each slug
    resolves to its own ADR-0012 identity key.

    The event is ``date_only`` and ``coordinator_entry``: the honest shape for a
    row a test fixture typed in. It carries no provenance, because nothing
    fetched it — ``ck_event_provenance_evidence`` would refuse a source URL on a
    ``coordinator_entry`` row, and inventing one to satisfy a column would be
    the fabricated-field defect arriving through a test helper.

    Takes any object with SQLAlchemy's ``.execute(text, params)`` — a ``Session``
    or a ``Connection`` — as :func:`ensure_owning_unit` does.

    Cleanup: ``event`` is in :data:`_TENANT_SCOPED_TABLES`, listed after the
    tables that cite it, so teardown removes it once the attendance rows a test
    module owns are already gone.
    """
    title = f"{SYNTHETIC_EVENT_TITLE} {slug}"
    normalized = normalize_title(title)
    existing = executor.execute(
        text(
            "SELECT id FROM event WHERE tenant_id = :tid AND normalized_title = :title "
            "AND resolved_date = :on_date"
        ),
        {"tid": tenant_id, "title": normalized, "on_date": SYNTHETIC_EVENT_DATE},
    ).scalar_one_or_none()
    if existing is not None:
        return uuid.UUID(str(existing))

    event_id = uuid.uuid4()
    executor.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "on_date, time_zone, time_precision, resolved_date, origin) "
            "VALUES (:id, :tid, :unit, :title, :normalized, :on_date, "
            "'America/Los_Angeles', 'date_only', :on_date, 'coordinator_entry')"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(executor, tenant_id),
            "title": title,
            "normalized": normalized,
            "on_date": SYNTHETIC_EVENT_DATE,
        },
    )
    return event_id


@pytest.fixture
def owning_unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """The test tenant's job-owning unit, as a fixture.

    The fixture form for tests that want to name the unit; the function form for
    helpers that just need a job to exist.
    """
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)
