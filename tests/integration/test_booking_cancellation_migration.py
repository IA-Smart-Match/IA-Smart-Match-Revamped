"""Migration ``0040_speaker_booking_cancellation``: shape, constraints, lifecycle (B26 T8a).

``0040`` gives a Speaker booking — a ``pipeline_record`` that reached Confirmed — a
way to be cancelled that is a **transition, not a deletion**, the way
``event_registration.status`` already is:

* ``cancelled_at`` / ``cancelled_by_user_id`` — both nullable, no default, set
  together (``ck_pipeline_record_cancellation_actor``).
* ``ck_pipeline_record_cancellation_confirmed`` — only a confirmed journey is a
  booking, so only it can be cancelled.
* ``ck_pipeline_record_cancellation_order`` — a cancellation never precedes the
  confirmation it cancels (owner ruling C4).
* ``ck_pipeline_record_cancellation_not_attended`` — attended and cancelled
  exclude each other (owner ruling C2).
* ``fk_pipeline_record_cancelled_by_user`` — composite, so a canceller from
  another tenant is unstorable; ``ON DELETE RESTRICT``.

The upgrade and downgrade run for real against a scratch database seeded at
``0039``. Every CHECK is exercised against the suite's database at head, with its
forbidden half and its permitted half. The pinned expressions live in
``test_check_constraints.py``, which points back here.

Requires a live database; skipped otherwise.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_event, ensure_owning_unit, unique_subject
from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0039_speaker_portal.py``.
REVISION_BEFORE = "0039_speaker_portal"

#: The revision under test, and the head it makes. Read off the ``revision =``
#: line of ``0040_speaker_booking_cancellation.py``: the file name is 33
#: characters and ``alembic_version`` is ``varchar(32)``, so the id is shorter.
REVISION = "0040_booking_cancellation"

_CHECKS = (
    "ck_pipeline_record_cancellation_actor",
    "ck_pipeline_record_cancellation_confirmed",
    "ck_pipeline_record_cancellation_order",
    "ck_pipeline_record_cancellation_not_attended",
)

_BASE = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


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
            "sub": unique_subject(f"cancel-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _attendance(conn, tenant_id: uuid.UUID, subject_id: uuid.UUID) -> uuid.UUID:
    record_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tid, :unit, :subject, :event, 'qr_scan')"
        ),
        {
            "id": record_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "subject": subject_id,
            "event": ensure_event(conn, tenant_id),
        },
    )
    return record_id


def _journey(conn, tenant_id: uuid.UUID, *, confirmed: bool = True, attended: bool = False):
    """One journey, matched → contacted (→ confirmed (→ attended)), an hour apart."""
    record_id = uuid.uuid4()
    subject_id = _user(conn, tenant_id)
    evidence = _attendance(conn, tenant_id, subject_id) if attended else None
    conn.execute(
        text(
            "INSERT INTO pipeline_record "
            "(id, tenant_id, owning_unit_id, subject_id, opportunity_event_id, matched_at, "
            " matched_provenance, contacted_at, confirmed_at, attended_at, "
            " attended_attendance_id) "
            "VALUES (:id, :tid, :unit, :subject, :event, :m, "
            " 'synthetic / coordinator-accepted', :c, :cf, :a, :evidence)"
        ),
        {
            "id": record_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "subject": subject_id,
            "event": ensure_event(conn, tenant_id, f"booking-{record_id.hex[:8]}"),
            "m": _BASE,
            "c": _BASE + timedelta(hours=1),
            "cf": _BASE + timedelta(hours=2) if confirmed else None,
            "a": _BASE + timedelta(hours=3) if attended else None,
            "evidence": evidence,
        },
    )
    return record_id


def _cancel(conn, tenant_id, record_id, *, at, by) -> None:
    conn.execute(
        text(
            "UPDATE pipeline_record SET cancelled_at = :at, cancelled_by_user_id = :by "
            "WHERE tenant_id = :tid AND id = :id"
        ),
        {"at": at, "by": by, "tid": tenant_id, "id": record_id},
    )


@pytest.fixture(autouse=True)
def _clean_pipeline_rows(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """``pipeline_record`` is not in the conftest sweep, and every key here is RESTRICT."""
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )


@pytest.fixture
def coordinator(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return _user(conn, tenant_id)


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
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
    with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
        statement(conn)
    return str(raised.value)


def _columns(conn) -> set[str]:
    return set(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'pipeline_record'"
            )
        ).scalars()
    )


def _constraints(conn) -> set[str]:
    return set(
        conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'pipeline_record'::regclass")
        ).scalars()
    )


# ---------------------------------------------------------------------------
# 1 — the upgrade writes nothing
# ---------------------------------------------------------------------------


def test_the_upgrade_writes_no_row_and_leaves_every_journey_uncancelled(engine: Engine):
    """Seeded at 0039 with a confirmed and an attended journey; neither is touched."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            tenant_id = uuid.uuid4()
            with scratch.begin() as conn:
                conn.execute(
                    text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :s, :s)"),
                    {"id": tenant_id, "s": f"scratch-{tenant_id.hex[:12]}"},
                )
                _journey(conn, tenant_id)
                _journey(conn, tenant_id, attended=True)
                before = conn.execute(
                    text("SELECT id, updated_at FROM pipeline_record ORDER BY id")
                ).all()

            alembic(url, "head", expect_success=True)
            assert applied_revision(url) == REVISION

            with scratch.connect() as conn:
                after = conn.execute(
                    text("SELECT id, updated_at FROM pipeline_record ORDER BY id")
                ).all()
                cancelled = conn.execute(
                    text(
                        "SELECT count(*) FROM pipeline_record "
                        "WHERE cancelled_at IS NOT NULL OR cancelled_by_user_id IS NOT NULL"
                    )
                ).scalar_one()
                defaults = conn.execute(
                    text(
                        "SELECT column_name, column_default, is_nullable "
                        "FROM information_schema.columns WHERE table_name = 'pipeline_record' "
                        "AND column_name IN ('cancelled_at', 'cancelled_by_user_id')"
                    )
                ).all()

    assert before == after, "the upgrade rewrote a pipeline_record row"
    assert cancelled == 0
    assert {row.column_name for row in defaults} == {"cancelled_at", "cancelled_by_user_id"}
    assert all(row.column_default is None and row.is_nullable == "YES" for row in defaults)


# ---------------------------------------------------------------------------
# 2 — actor and time are set together
# ---------------------------------------------------------------------------


def test_cancellation_needs_both_actor_and_time(engine: Engine, tenant_id):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
    refused = _refused(
        engine,
        lambda conn: _cancel(conn, tenant_id, record_id, at=_BASE + timedelta(hours=5), by=None),
    )
    assert "ck_pipeline_record_cancellation_actor" in refused


def test_an_actor_without_a_time_is_refused(engine: Engine, tenant_id, coordinator):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
    refused = _refused(
        engine, lambda conn: _cancel(conn, tenant_id, record_id, at=None, by=coordinator)
    )
    assert "ck_pipeline_record_cancellation_actor" in refused


# ---------------------------------------------------------------------------
# 3 — only a confirmed journey is a booking
# ---------------------------------------------------------------------------


def test_an_unconfirmed_journey_cannot_be_cancelled(engine: Engine, tenant_id, coordinator):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id, confirmed=False)
    refused = _refused(
        engine,
        lambda conn: _cancel(
            conn, tenant_id, record_id, at=_BASE + timedelta(hours=5), by=coordinator
        ),
    )
    assert "ck_pipeline_record_cancellation_confirmed" in refused


def test_a_confirmed_journey_can_be_cancelled(engine: Engine, tenant_id, coordinator):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
        _cancel(conn, tenant_id, record_id, at=_BASE + timedelta(hours=5), by=coordinator)
        stored = conn.execute(
            text("SELECT cancelled_at, cancelled_by_user_id FROM pipeline_record WHERE id = :id"),
            {"id": record_id},
        ).one()
    assert stored.cancelled_at == _BASE + timedelta(hours=5)
    assert stored.cancelled_by_user_id == coordinator


# ---------------------------------------------------------------------------
# 4 — the order CHECK (C4)
# ---------------------------------------------------------------------------


def test_a_cancellation_cannot_precede_the_confirmation(engine: Engine, tenant_id, coordinator):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
    confirmed_at = _BASE + timedelta(hours=2)
    refused = _refused(
        engine,
        lambda conn: _cancel(
            conn, tenant_id, record_id, at=confirmed_at - timedelta(microseconds=1), by=coordinator
        ),
    )
    assert "ck_pipeline_record_cancellation_order" in refused


def test_a_cancellation_at_the_confirmation_instant_is_permitted(
    engine: Engine, tenant_id, coordinator
):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
        _cancel(conn, tenant_id, record_id, at=_BASE + timedelta(hours=2), by=coordinator)


# ---------------------------------------------------------------------------
# 5 — attended and cancelled exclude each other (C2), tenancy, RESTRICT, downgrade
# ---------------------------------------------------------------------------


def test_an_attended_journey_cannot_be_cancelled(engine: Engine, tenant_id, coordinator):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id, attended=True)
    refused = _refused(
        engine,
        lambda conn: _cancel(
            conn, tenant_id, record_id, at=_BASE + timedelta(hours=5), by=coordinator
        ),
    )
    assert "ck_pipeline_record_cancellation_not_attended" in refused


def test_a_cancelled_journey_cannot_be_attended(engine: Engine, tenant_id, coordinator):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
        _cancel(conn, tenant_id, record_id, at=_BASE + timedelta(hours=5), by=coordinator)
        subject_id = conn.execute(
            text("SELECT subject_id FROM pipeline_record WHERE id = :id"), {"id": record_id}
        ).scalar_one()
        evidence = _attendance(conn, tenant_id, subject_id)

    refused = _refused(
        engine,
        lambda conn: conn.execute(
            text(
                "UPDATE pipeline_record SET attended_at = :at, attended_attendance_id = :ev "
                "WHERE tenant_id = :tid AND id = :id"
            ),
            {"at": _BASE + timedelta(hours=6), "ev": evidence, "tid": tenant_id, "id": record_id},
        ),
    )
    assert "ck_pipeline_record_cancellation_not_attended" in refused


def test_a_canceller_from_another_tenant_is_refused(engine: Engine, tenant_id, other_tenant_id):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
        intruder = _user(conn, other_tenant_id)
    refused = _refused(
        engine,
        lambda conn: _cancel(
            conn, tenant_id, record_id, at=_BASE + timedelta(hours=5), by=intruder
        ),
    )
    assert "fk_pipeline_record_cancelled_by_user" in refused


def test_the_cancelling_account_cannot_be_deleted(engine: Engine, tenant_id, coordinator):
    with engine.begin() as conn:
        record_id = _journey(conn, tenant_id)
        _cancel(conn, tenant_id, record_id, at=_BASE + timedelta(hours=5), by=coordinator)
    refused = _refused(
        engine,
        lambda conn: conn.execute(
            text("DELETE FROM user_account WHERE tenant_id = :tid AND id = :id"),
            {"tid": tenant_id, "id": coordinator},
        ),
    )
    assert "fk_pipeline_record_cancelled_by_user" in refused


def test_downgrade_drops_both_columns_and_all_four_checks(engine: Engine):
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        with connected(url) as scratch:
            with scratch.connect() as conn:
                assert {"cancelled_at", "cancelled_by_user_id"} <= _columns(conn)
                assert set(_CHECKS) | {"fk_pipeline_record_cancelled_by_user"} <= _constraints(conn)

            alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
            assert applied_revision(url) == REVISION_BEFORE
            with scratch.connect() as conn:
                assert not {"cancelled_at", "cancelled_by_user_id"} & _columns(conn)
                assert not (set(_CHECKS) | {"fk_pipeline_record_cancelled_by_user"}) & _constraints(
                    conn
                )
                index = conn.execute(
                    text("SELECT count(*) FROM pg_indexes WHERE indexname = :n"),
                    {"n": "ix_pipeline_record_cancelled_by"},
                ).scalar_one()
            assert index == 0

            alembic(url, "head", expect_success=True)
            assert applied_revision(url) == REVISION
