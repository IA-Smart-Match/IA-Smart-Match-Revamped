"""Migration ``0038_speaker_availability``: shape, constraints and lifecycle (B26 T2).

``0038`` adds two tables and one index, and writes no rows:

* ``speaker_availability`` — one row per speaker who has *said something*
  about their availability. No row means "said nothing" (``UNKNOWN``); a row
  with no windows is a real answer (``AVAILABLE``).
* ``speaker_availability_window`` — the inclusive date ranges a speaker cannot
  speak on, each carrying who wrote it and from which surface.

The upgrade and downgrade are run for real against a scratch database seeded at
``0037`` (the ``test_host_organization_migration.py`` shape). Every constraint
is then exercised against the suite's database at head: its forbidden half and
its permitted half, so a constraint that refuses everything fails as loudly as
one that refuses nothing. The pinned expressions live in
``test_check_constraints.py``, which points back here.

Requires a live database; skipped otherwise. A local skip is not proof — CI is.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit, unique_subject
from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0037_exercise_tables.py``.
REVISION_BEFORE = "0037_exercise_tables"

#: The revision under test, and the head it makes.
REVISION = "0038_speaker_availability"

_NEW_TABLES = ("speaker_availability", "speaker_availability_window")

_START = date(2026, 11, 2)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": unique_subject(f"availability-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _profile(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """A speaker: an account plus the ``speaker_profile`` row keyed by it."""
    professional_id = _user(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, full_name) "
            "VALUES (:tid, :pid, :unit, 'Dana Reyes')"
        ),
        {"tid": tenant_id, "pid": professional_id, "unit": ensure_owning_unit(conn, tenant_id)},
    )
    return professional_id


def _statement(
    conn,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    capacity: Decimal | None = None,
    source: str = "speaker",
    version: int | None = None,
) -> None:
    columns = "tenant_id, professional_id, declared_capacity_hours_per_90_days, "
    columns += "updated_source, updated_by_user_id"
    values = ":tid, :pid, :capacity, :source, :actor"
    params: dict[str, object] = {
        "tid": tenant_id,
        "pid": professional_id,
        "capacity": capacity,
        "source": source,
        "actor": actor_id,
    }
    if version is not None:
        columns += ", version"
        values += ", :version"
        params["version"] = version
    conn.execute(
        text(f"INSERT INTO speaker_availability ({columns}) VALUES ({values})"),
        params,
    )


def _window(
    conn,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    actor_id: uuid.UUID,
    starts_on: date,
    ends_on: date,
    *,
    source: str = "speaker",
) -> uuid.UUID:
    window_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO speaker_availability_window "
            "(id, tenant_id, professional_id, starts_on, ends_on, created_source, "
            " created_by_user_id) "
            "VALUES (:id, :tid, :pid, :starts, :ends, :source, :actor)"
        ),
        {
            "id": window_id,
            "tid": tenant_id,
            "pid": professional_id,
            "starts": starts_on,
            "ends": ends_on,
            "source": source,
            "actor": actor_id,
        },
    )
    return window_id


@pytest.fixture
def speaker(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """A speaker with a profile and no availability row yet."""
    with engine.begin() as conn:
        return _profile(conn, tenant_id)


@pytest.fixture
def stated(engine: Engine, tenant_id: uuid.UUID, speaker: uuid.UUID) -> uuid.UUID:
    """A speaker who has stated availability (self-authored, no windows)."""
    with engine.begin() as conn:
        _statement(conn, tenant_id, speaker, speaker)
    return speaker


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    """A second real tenant, cleaned up as ``conftest.tenant_id`` cleans its own."""
    tid = uuid.uuid4()
    slug = f"test-other-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": tid, "slug": slug, "name": slug},
        )
    yield tid
    with engine.begin() as conn:
        for table in _TENANT_SCOPED_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def _refused(engine: Engine, statement) -> str:
    """Run ``statement(conn)`` in its own transaction; return the refusal's text."""
    with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
        statement(conn)
    return str(raised.value)


def _tables(conn) -> set[str]:
    return {
        row.table_name
        for row in conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
    }


# ---------------------------------------------------------------------------
# 1-3. Upgrade and downgrade, for real, against a populated 0037 database
# ---------------------------------------------------------------------------


def _seed_profile_at_0037(scratch) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    with scratch.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
        )
        professional_id = _profile(conn, tenant_id)
    return tenant_id, professional_id


def test_upgrade_from_0037_creates_both_tables_and_writes_no_row(engine: Engine):
    """Both tables appear empty; the seeded ``speaker_profile`` survives untouched.

    An upgrade that seeded a row per speaker would turn "said nothing" into
    "stated, nothing blocked" for every speaker at once.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            tenant_id, professional_id = _seed_profile_at_0037(scratch)
            alembic(url, "head", expect_success=True)
            with scratch.connect() as conn:
                tables = _tables(conn)
                counts = tuple(
                    conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                    for table in _NEW_TABLES
                )
                profile = conn.execute(
                    text(
                        "SELECT full_name FROM speaker_profile "
                        "WHERE tenant_id = :tid AND professional_id = :pid"
                    ),
                    {"tid": tenant_id, "pid": professional_id},
                ).scalar_one()
        assert applied_revision(url) == REVISION

    assert set(_NEW_TABLES) <= tables
    assert counts == (0, 0)
    assert profile == "Dana Reyes"


def test_downgrade_drops_both_tables_and_keeps_speaker_profile(engine: Engine):
    """Rolling back drops the new facts and nothing else — the profile stays."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            tenant_id, professional_id = _seed_profile_at_0037(scratch)
            alembic(url, "head", expect_success=True)
            with scratch.begin() as conn:
                _statement(conn, tenant_id, professional_id, professional_id)
                _window(conn, tenant_id, professional_id, professional_id, _START, _START)

            alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")

            with scratch.connect() as conn:
                tables = _tables(conn)
                profiles = conn.execute(
                    text("SELECT count(*) FROM speaker_profile WHERE professional_id = :pid"),
                    {"pid": professional_id},
                ).scalar_one()
                indexes = conn.execute(
                    text(
                        "SELECT count(*) FROM pg_indexes "
                        "WHERE indexname = 'ix_speaker_availability_window_ends'"
                    )
                ).scalar_one()
        assert applied_revision(url) == REVISION_BEFORE

    assert not set(_NEW_TABLES) & tables
    assert profiles == 1
    assert indexes == 0


def test_upgrade_is_repeatable_after_a_downgrade(engine: Engine):
    """Down then up again, with a profile present the whole time."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            _seed_profile_at_0037(scratch)
            alembic(url, "head", expect_success=True)
            alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
            alembic(url, "head", expect_success=True)
            with scratch.connect() as conn:
                tables = _tables(conn)
        assert applied_revision(url) == REVISION

    assert set(_NEW_TABLES) <= tables


# ---------------------------------------------------------------------------
# 4-6. ck_speaker_availability_capacity
# ---------------------------------------------------------------------------


def test_capacity_rejects_zero(engine, tenant_id, speaker):
    message = _refused(
        engine, lambda conn: _statement(conn, tenant_id, speaker, speaker, capacity=Decimal("0"))
    )
    assert "ck_speaker_availability_capacity" in message


def test_capacity_rejects_negative(engine, tenant_id, speaker):
    message = _refused(
        engine,
        lambda conn: _statement(conn, tenant_id, speaker, speaker, capacity=Decimal("-0.5")),
    )
    assert "ck_speaker_availability_capacity" in message


def test_capacity_rejects_720_1(engine, tenant_id, speaker):
    message = _refused(
        engine,
        lambda conn: _statement(conn, tenant_id, speaker, speaker, capacity=Decimal("720.1")),
    )
    assert "ck_speaker_availability_capacity" in message


@pytest.mark.parametrize("capacity", [None, Decimal("0.1"), Decimal("720")])
def test_capacity_accepts_null_0_1_and_720(engine, tenant_id, speaker, capacity):
    """The permitted half. ``NULL`` means "not stated", never a default."""
    with engine.begin() as conn:
        _statement(conn, tenant_id, speaker, speaker, capacity=capacity)
        stored = conn.execute(
            text(
                "SELECT declared_capacity_hours_per_90_days FROM speaker_availability "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": speaker},
        ).scalar_one()
    assert stored == capacity


def test_capacity_rounds_before_check(engine, tenant_id, speaker):
    """``numeric(5,1)`` rounds first: ``720.04`` lands as ``720.0``, ``0.04`` is refused.

    Pins the column's scale (plan C5). T1's validator rejects more than one
    decimal before a value reaches here; this proves what the database does
    if one ever did.
    """
    with engine.begin() as conn:
        _statement(conn, tenant_id, speaker, speaker, capacity=Decimal("720.04"))
        stored = conn.execute(
            text(
                "SELECT declared_capacity_hours_per_90_days FROM speaker_availability "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": speaker},
        ).scalar_one()
        conn.execute(
            text(
                "DELETE FROM speaker_availability WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": speaker},
        )
    assert stored == Decimal("720.0")

    message = _refused(
        engine,
        lambda conn: _statement(conn, tenant_id, speaker, speaker, capacity=Decimal("0.04")),
    )
    assert "ck_speaker_availability_capacity" in message


# ---------------------------------------------------------------------------
# 7-8. ck_speaker_availability_source, ck_speaker_availability_version
# ---------------------------------------------------------------------------


def test_updated_source_rejects_unknown(engine, tenant_id, speaker):
    message = _refused(
        engine, lambda conn: _statement(conn, tenant_id, speaker, speaker, source="import")
    )
    assert "ck_speaker_availability_source" in message


@pytest.mark.parametrize("source", ["speaker", "connector"])
def test_updated_source_accepts_speaker_and_connector(engine, tenant_id, speaker, source):
    with engine.begin() as conn:
        _statement(conn, tenant_id, speaker, speaker, source=source)
        stored = conn.execute(
            text(
                "SELECT updated_source FROM speaker_availability "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": speaker},
        ).scalar_one()
    assert stored == source


def test_version_rejects_zero(engine, tenant_id, speaker):
    message = _refused(
        engine, lambda conn: _statement(conn, tenant_id, speaker, speaker, version=0)
    )
    assert "ck_speaker_availability_version" in message


def test_version_defaults_to_one(engine, tenant_id, stated):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT version, invitations_paused_until, declared_capacity_hours_per_90_days, "
                "       created_at, updated_at "
                "FROM speaker_availability WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": stated},
        ).one()
    assert row.version == 1
    assert row.invitations_paused_until is None
    assert row.declared_capacity_hours_per_90_days is None
    assert row.created_at is not None and row.updated_at is not None


# ---------------------------------------------------------------------------
# 9-12. The window's CHECKs and its uniqueness
# ---------------------------------------------------------------------------


def test_window_rejects_end_before_start(engine, tenant_id, stated):
    message = _refused(
        engine,
        lambda conn: _window(conn, tenant_id, stated, stated, _START, _START - timedelta(days=1)),
    )
    assert "ck_speaker_availability_window_order" in message


def test_window_accepts_single_day(engine, tenant_id, stated):
    with engine.begin() as conn:
        _window(conn, tenant_id, stated, stated, _START, _START)


def test_window_rejects_span_367(engine, tenant_id, stated):
    message = _refused(
        engine,
        lambda conn: _window(conn, tenant_id, stated, stated, _START, _START + timedelta(days=367)),
    )
    assert "ck_speaker_availability_window_span" in message


def test_window_accepts_span_366(engine, tenant_id, stated):
    with engine.begin() as conn:
        _window(conn, tenant_id, stated, stated, _START, _START + timedelta(days=366))


def test_window_source_rejects_unknown(engine, tenant_id, stated):
    message = _refused(
        engine,
        lambda conn: _window(conn, tenant_id, stated, stated, _START, _START, source="calendar"),
    )
    assert "ck_speaker_availability_window_source" in message


@pytest.mark.parametrize("source", ["speaker", "connector"])
def test_window_source_accepts_both(engine, tenant_id, stated, source):
    with engine.begin() as conn:
        _window(conn, tenant_id, stated, stated, _START, _START, source=source)


def test_window_rejects_duplicate_range(engine, tenant_id, stated):
    with engine.begin() as conn:
        _window(conn, tenant_id, stated, stated, _START, _START + timedelta(days=3))
    message = _refused(
        engine,
        lambda conn: _window(conn, tenant_id, stated, stated, _START, _START + timedelta(days=3)),
    )
    assert "uq_speaker_availability_window_range" in message


def test_window_accepts_overlapping_distinct_ranges(engine, tenant_id, stated):
    """Overlap is not a duplicate. Merging ranges is the caller's choice, not the schema's."""
    with engine.begin() as conn:
        _window(conn, tenant_id, stated, stated, _START, _START + timedelta(days=3))
        _window(
            conn, tenant_id, stated, stated, _START + timedelta(days=1), _START + timedelta(days=5)
        )
        count = conn.execute(
            text(
                "SELECT count(*) FROM speaker_availability_window "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": stated},
        ).scalar_one()
    assert count == 2


# ---------------------------------------------------------------------------
# 13-15. Tenant isolation is structural
# ---------------------------------------------------------------------------


def test_availability_for_other_tenant_profile_is_refused(engine, tenant_id, other_tenant_id):
    """A row in tenant A cannot name a profile that lives in tenant B."""
    with engine.begin() as conn:
        foreign_speaker = _profile(conn, other_tenant_id)
        actor = _user(conn, tenant_id)
    message = _refused(engine, lambda conn: _statement(conn, tenant_id, foreign_speaker, actor))
    assert "fk_speaker_availability_profile" in message


def test_updated_by_from_other_tenant_is_refused(engine, tenant_id, speaker, other_tenant_id):
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(engine, lambda conn: _statement(conn, tenant_id, speaker, intruder))
    assert "fk_speaker_availability_updated_by" in message


def test_window_created_by_from_other_tenant_is_refused(engine, tenant_id, stated, other_tenant_id):
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(
        engine, lambda conn: _window(conn, tenant_id, stated, intruder, _START, _START)
    )
    assert "fk_speaker_availability_window_created_by" in message


def test_window_for_other_tenant_statement_is_refused(engine, tenant_id, stated, other_tenant_id):
    """A window filed under tenant B cannot attach to tenant A's statement."""
    with engine.begin() as conn:
        foreign_actor = _user(conn, other_tenant_id)
    message = _refused(
        engine, lambda conn: _window(conn, other_tenant_id, stated, foreign_actor, _START, _START)
    )
    assert "fk_speaker_availability_window_statement" in message


def test_window_without_statement_is_refused(engine, tenant_id, speaker):
    """No statement, no windows: a window alone would be an answer with no author row."""
    message = _refused(
        engine, lambda conn: _window(conn, tenant_id, speaker, speaker, _START, _START)
    )
    assert "fk_speaker_availability_window_statement" in message


# ---------------------------------------------------------------------------
# 16-19. Delete actions
# ---------------------------------------------------------------------------


def _counts(conn, tenant_id: uuid.UUID, professional_id: uuid.UUID) -> tuple[int, int]:
    return tuple(  # type: ignore[return-value]
        conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tid AND professional_id = :pid"),
            {"tid": tenant_id, "pid": professional_id},
        ).scalar_one()
        for table in _NEW_TABLES
    )


def test_deleting_speaker_profile_cascades_to_availability_and_windows(engine, tenant_id, stated):
    with engine.begin() as conn:
        _window(conn, tenant_id, stated, stated, _START, _START)
        assert _counts(conn, tenant_id, stated) == (1, 1)
        conn.execute(
            text("DELETE FROM speaker_profile WHERE tenant_id = :tid AND professional_id = :pid"),
            {"tid": tenant_id, "pid": stated},
        )
        assert _counts(conn, tenant_id, stated) == (0, 0)


def test_deleting_statement_cascades_to_windows(engine, tenant_id, stated):
    with engine.begin() as conn:
        _window(conn, tenant_id, stated, stated, _START, _START)
        conn.execute(
            text(
                "DELETE FROM speaker_availability WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": stated},
        )
        assert _counts(conn, tenant_id, stated) == (0, 0)


def test_deleting_updating_user_account_is_restricted(engine, tenant_id, speaker):
    """Deleting the account that wrote a statement must not erase its authorship."""
    with engine.begin() as conn:
        connector = _user(conn, tenant_id)
        _statement(conn, tenant_id, speaker, connector, source="connector")
    message = _refused(
        engine,
        lambda conn: conn.execute(
            text("DELETE FROM user_account WHERE tenant_id = :tid AND id = :uid"),
            {"tid": tenant_id, "uid": connector},
        ),
    )
    assert "fk_speaker_availability_updated_by" in message


def test_deleting_window_creator_account_is_restricted(engine, tenant_id, speaker):
    """The window's creator differs from the statement's author, so this RESTRICT stands alone."""
    with engine.begin() as conn:
        statement_author = _user(conn, tenant_id)
        window_creator = _user(conn, tenant_id)
        _statement(conn, tenant_id, speaker, statement_author, source="connector")
        _window(conn, tenant_id, speaker, window_creator, _START, _START, source="connector")
    message = _refused(
        engine,
        lambda conn: conn.execute(
            text("DELETE FROM user_account WHERE tenant_id = :tid AND id = :uid"),
            {"tid": tenant_id, "uid": window_creator},
        ),
    )
    assert "fk_speaker_availability_window_created_by" in message


# ---------------------------------------------------------------------------
# 20. The index the drift test does not compare
# ---------------------------------------------------------------------------


def test_window_ends_index_exists(engine):
    indexes = {
        index["name"]: index["column_names"]
        for index in inspect(engine).get_indexes("speaker_availability_window")
    }
    assert indexes.get("ix_speaker_availability_window_ends") == [
        "tenant_id",
        "professional_id",
        "ends_on",
    ]
