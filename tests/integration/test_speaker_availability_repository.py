"""The ``speaker_availability`` repository contract (B26 T2, plan §3 and §4.2).

What is pinned here, each for a failure it would otherwise allow:

* **No row is an answer of its own.** ``get`` returns ``None`` for a speaker
  who has said nothing, and a row with zero windows for one who said
  "nothing blocked" — two different verdicts downstream.
* **``expected_version`` is always checked** (plan C1). ``None`` means "I
  believe there is no row", so two writers (the speaker and a Connector)
  cannot silently overwrite each other, including on the very first write.
* **Window provenance survives a replace.** A range kept across an edit keeps
  who wrote it and from where; only new ranges take the current writer.
* **A read is one statement.** Under READ COMMITTED two queries can straddle a
  writer's commit and return fields at version *n* with windows at *n+1*;
  test 15 forces exactly that interleaving.
* **The repository never commits.** The caller owns the transaction.

Requires a live database; skipped otherwise. A local skip is not proof — CI is.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit, unique_subject
from smartmatch_domain.speaker_availability import AvailabilityStatement, UnavailableWindow
from smartmatch_persistence.speaker_availability import (
    AvailabilitySource,
    SpeakerAvailabilityRepository,
    StaleSpeakerAvailabilityError,
    StoredSpeakerAvailability,
)
from sqlalchemy import Engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

REPO = SpeakerAvailabilityRepository()

_D = date(2026, 11, 2)
W1 = UnavailableWindow(_D, _D + timedelta(days=2))
W2 = UnavailableWindow(_D + timedelta(days=10), _D + timedelta(days=12))
W3 = UnavailableWindow(_D + timedelta(days=20), _D + timedelta(days=20))

T0 = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)


# ---------------------------------------------------------------------------
# Builders and fixtures
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
            "sub": unique_subject(f"availability-repo-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _profile(conn, tenant_id: uuid.UUID) -> uuid.UUID:
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
    *windows: UnavailableWindow,
    paused: date | None = None,
    capacity: Decimal | None = None,
) -> AvailabilityStatement:
    return AvailabilityStatement(
        invitations_paused_until=paused,
        declared_capacity_hours_per_90_days=capacity,
        unavailable=tuple(windows),
    )


@pytest.fixture
def speaker(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return _profile(conn, tenant_id)


@pytest.fixture
def connector(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
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


def _write(
    factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    statement: AvailabilityStatement,
    *,
    actor: uuid.UUID,
    source: AvailabilitySource = AvailabilitySource.SPEAKER,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> StoredSpeakerAvailability:
    """One committed upsert in its own session."""
    with factory() as session:
        stored = REPO.upsert(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            statement=statement,
            source=source,
            actor_user_id=actor,
            expected_version=expected_version,
            now=now,
        )
        session.commit()
    return stored


def _read(
    factory: sessionmaker[Session], tenant_id: uuid.UUID, professional_id: uuid.UUID
) -> StoredSpeakerAvailability | None:
    with factory() as session:
        return REPO.get(session, tenant_id=tenant_id, professional_id=professional_id)


def _window_rows(engine: Engine, tenant_id: uuid.UUID, professional_id: uuid.UUID) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM speaker_availability_window "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).scalar_one()


# ---------------------------------------------------------------------------
# 1-6. Reads, first writes and the version check
# ---------------------------------------------------------------------------


def test_get_returns_none_when_no_row(session_factory, tenant_id, speaker):
    assert _read(session_factory, tenant_id, speaker) is None


def test_first_upsert_with_none_creates_version_1(session_factory, tenant_id, speaker):
    stored = _write(session_factory, tenant_id, speaker, _statement(W1), actor=speaker, now=T0)

    assert stored.version == 1
    assert stored.tenant_id == tenant_id
    assert stored.professional_id == speaker
    assert stored.statement == _statement(W1)
    assert stored.updated_source is AvailabilitySource.SPEAKER
    assert stored.updated_by_user_id == speaker
    assert stored.created_at == T0 and stored.updated_at == T0
    assert _read(session_factory, tenant_id, speaker) == stored


def test_first_upsert_with_version_raises_stale(engine, session_factory, tenant_id, speaker):
    with pytest.raises(StaleSpeakerAvailabilityError), session_factory() as session:
        REPO.upsert(
            session,
            tenant_id=tenant_id,
            professional_id=speaker,
            statement=_statement(),
            source=AvailabilitySource.SPEAKER,
            actor_user_id=speaker,
            expected_version=1,
        )
    assert _read(session_factory, tenant_id, speaker) is None


def test_upsert_with_none_when_row_exists_raises_stale(session_factory, tenant_id, speaker):
    _write(session_factory, tenant_id, speaker, _statement(W1), actor=speaker)
    with pytest.raises(StaleSpeakerAvailabilityError):
        _write(session_factory, tenant_id, speaker, _statement(), actor=speaker)
    stored = _read(session_factory, tenant_id, speaker)
    assert stored is not None and stored.version == 1 and stored.statement == _statement(W1)


def test_upsert_with_old_version_raises_stale_and_writes_nothing(
    engine, session_factory, tenant_id, speaker, connector
):
    _write(session_factory, tenant_id, speaker, _statement(W1), actor=speaker)
    second = _write(
        session_factory,
        tenant_id,
        speaker,
        _statement(W2),
        actor=speaker,
        expected_version=1,
    )
    with pytest.raises(StaleSpeakerAvailabilityError):
        _write(
            session_factory,
            tenant_id,
            speaker,
            _statement(W3, capacity=Decimal("4")),
            actor=connector,
            source=AvailabilitySource.CONNECTOR,
            expected_version=1,
        )
    assert _read(session_factory, tenant_id, speaker) == second
    assert _window_rows(engine, tenant_id, speaker) == 1


def test_upsert_bumps_version_and_sets_provenance(session_factory, tenant_id, speaker, connector):
    _write(session_factory, tenant_id, speaker, _statement(W1), actor=speaker, now=T0)
    stored = _write(
        session_factory,
        tenant_id,
        speaker,
        _statement(W1, paused=_D, capacity=Decimal("6.5")),
        actor=connector,
        source=AvailabilitySource.CONNECTOR,
        expected_version=1,
        now=T1,
    )

    assert stored.version == 2
    assert stored.updated_source is AvailabilitySource.CONNECTOR
    assert stored.updated_by_user_id == connector
    assert stored.created_at == T0
    assert stored.updated_at == T1
    assert stored.statement.invitations_paused_until == _D
    assert stored.statement.declared_capacity_hours_per_90_days == Decimal("6.5")

    # Every accepted call bumps, even an identical one.
    again = _write(
        session_factory,
        tenant_id,
        speaker,
        stored.statement,
        actor=connector,
        source=AvailabilitySource.CONNECTOR,
        expected_version=2,
    )
    assert again.version == 3


# ---------------------------------------------------------------------------
# 7-9. Window replace and value round trips
# ---------------------------------------------------------------------------


def test_window_replace_keeps_unchanged_provenance_deletes_absent_inserts_new(
    session_factory, tenant_id, speaker, connector
):
    _write(session_factory, tenant_id, speaker, _statement(W1, W2), actor=speaker, now=T0)
    stored = _write(
        session_factory,
        tenant_id,
        speaker,
        _statement(W3, W2),
        actor=connector,
        source=AvailabilitySource.CONNECTOR,
        expected_version=1,
        now=T1,
    )

    assert stored.statement.unavailable == (W2, W3)
    kept, added = stored.windows
    assert (kept.starts_on, kept.ends_on) == (W2.starts_on, W2.ends_on)
    assert kept.created_source is AvailabilitySource.SPEAKER
    assert kept.created_by_user_id == speaker
    assert kept.created_at == T0
    assert (added.starts_on, added.ends_on) == (W3.starts_on, W3.ends_on)
    assert added.created_source is AvailabilitySource.CONNECTOR
    assert added.created_by_user_id == connector
    assert added.created_at == T1


def test_empty_windows_clears_all_windows_but_keeps_row(
    engine, session_factory, tenant_id, speaker
):
    _write(session_factory, tenant_id, speaker, _statement(W1, W2), actor=speaker)
    stored = _write(
        session_factory, tenant_id, speaker, _statement(), actor=speaker, expected_version=1
    )

    assert stored.version == 2
    assert stored.statement.unavailable == ()
    assert stored.windows == ()
    assert _window_rows(engine, tenant_id, speaker) == 0
    assert _read(session_factory, tenant_id, speaker) == stored


def test_capacity_round_trips_as_decimal(session_factory, tenant_id, speaker):
    _write(session_factory, tenant_id, speaker, _statement(capacity=Decimal("12.5")), actor=speaker)
    stored = _read(session_factory, tenant_id, speaker)
    assert stored is not None
    capacity = stored.statement.declared_capacity_hours_per_90_days
    assert isinstance(capacity, Decimal)
    assert capacity == Decimal("12.5")


def test_null_pause_and_capacity_round_trip(session_factory, tenant_id, speaker):
    _write(session_factory, tenant_id, speaker, _statement(), actor=speaker)
    stored = _read(session_factory, tenant_id, speaker)
    assert stored is not None
    assert stored.statement.invitations_paused_until is None
    assert stored.statement.declared_capacity_hours_per_90_days is None


# ---------------------------------------------------------------------------
# 10-12. get_many
# ---------------------------------------------------------------------------


def _count_statements(session: Session) -> list[str]:
    statements: list[str] = []
    conn = session.connection()

    def _hook(_conn, _cursor, statement, _params, _context, _executemany):
        statements.append(statement)

    event.listen(conn, "before_cursor_execute", _hook)
    return statements


def test_get_many_returns_only_present_ids_in_one_query(
    engine, session_factory, tenant_id, speaker
):
    with engine.begin() as conn:
        second = _profile(conn, tenant_id)
        silent = _profile(conn, tenant_id)
    _write(session_factory, tenant_id, speaker, _statement(W1), actor=speaker)
    _write(session_factory, tenant_id, second, _statement(W2, W3), actor=second)

    with session_factory() as session:
        statements = _count_statements(session)
        found = REPO.get_many(
            session, tenant_id=tenant_id, professional_ids=[speaker, second, silent]
        )
        assert len(statements) == 1

        statements.clear()
        single = REPO.get(session, tenant_id=tenant_id, professional_id=speaker)
        assert len(statements) == 1

    assert set(found) == {speaker, second}
    assert found[speaker].statement.unavailable == (W1,)
    assert found[second].statement.unavailable == (W2, W3)
    assert single == found[speaker]


def test_get_many_keeps_a_row_with_zero_windows(session_factory, tenant_id, speaker):
    _write(session_factory, tenant_id, speaker, _statement(), actor=speaker)
    with session_factory() as session:
        found = REPO.get_many(session, tenant_id=tenant_id, professional_ids=[speaker])
    assert set(found) == {speaker}
    assert found[speaker].statement.unavailable == ()
    assert found[speaker].windows == ()


def test_get_many_empty_input_issues_no_query(session_factory, tenant_id):
    with session_factory() as session:
        statements = _count_statements(session)
        found = REPO.get_many(session, tenant_id=tenant_id, professional_ids=[])
    assert dict(found) == {}
    assert statements == []


def test_get_many_never_returns_other_tenant_rows(
    engine, session_factory, tenant_id, speaker, other_tenant_id
):
    with engine.begin() as conn:
        foreign = _profile(conn, other_tenant_id)
    _write(session_factory, tenant_id, speaker, _statement(), actor=speaker)
    _write(session_factory, other_tenant_id, foreign, _statement(W1), actor=foreign)

    with session_factory() as session:
        found = REPO.get_many(session, tenant_id=tenant_id, professional_ids=[speaker, foreign])
        cross = REPO.get(session, tenant_id=tenant_id, professional_id=foreign)

    assert set(found) == {speaker}
    assert cross is None


# ---------------------------------------------------------------------------
# 13-15. Transactions and concurrency
# ---------------------------------------------------------------------------


def test_concurrent_first_writes_one_wins_other_stale(
    session_factory, tenant_id, speaker, connector
):
    """B checks for a row, A's first write commits, B's insert must report stale.

    The hook fires once, straight after B's ``SELECT … FOR UPDATE`` found
    nothing (so nothing is locked), and runs A's whole first write on its own
    connection. B's ``INSERT … ON CONFLICT DO NOTHING`` then returns no row;
    that must surface as :class:`StaleSpeakerAvailabilityError`, not as an
    ``IntegrityError`` that would abort B's transaction.
    """
    counter = 0

    def _a_writes_first(_conn, _cursor, statement, _params, _context, _executemany):
        nonlocal counter
        if counter or "FOR UPDATE" not in statement:
            return
        counter += 1
        _write(session_factory, tenant_id, speaker, _statement(W1), actor=speaker)

    with session_factory() as session_b:
        conn = session_b.connection()
        event.listen(conn, "after_cursor_execute", _a_writes_first)
        with pytest.raises(StaleSpeakerAvailabilityError):
            REPO.upsert(
                session_b,
                tenant_id=tenant_id,
                professional_id=speaker,
                statement=_statement(W2),
                source=AvailabilitySource.CONNECTOR,
                actor_user_id=connector,
                expected_version=None,
            )
        event.remove(conn, "after_cursor_execute", _a_writes_first)
        assert session_b.execute(select(1)).scalar_one() == 1
        session_b.rollback()

    stored = _read(session_factory, tenant_id, speaker)
    assert stored is not None
    assert stored.version == 1
    assert stored.updated_by_user_id == speaker
    assert stored.statement == _statement(W1)
    assert counter == 1


def test_repository_never_commits(session_factory, tenant_id, speaker):
    with session_factory() as session:
        REPO.upsert(
            session,
            tenant_id=tenant_id,
            professional_id=speaker,
            statement=_statement(W1),
            source=AvailabilitySource.SPEAKER,
            actor_user_id=speaker,
            expected_version=None,
        )
        session.rollback()
    assert _read(session_factory, tenant_id, speaker) is None


def test_a_duplicate_range_reaching_the_database_is_an_integrity_error(
    session_factory, tenant_id, speaker
):
    """The repository does not validate; a duplicate is the caller's bug, loudly."""
    with pytest.raises(IntegrityError), session_factory() as session:
        REPO.upsert(
            session,
            tenant_id=tenant_id,
            professional_id=speaker,
            statement=_statement(W1, W1),
            source=AvailabilitySource.SPEAKER,
            actor_user_id=speaker,
            expected_version=None,
        )


@pytest.mark.parametrize("reader", ["get", "get_many"])
def test_read_is_one_committed_state_under_concurrent_write(
    session_factory, tenant_id, speaker, connector, reader
):
    """A write committed mid-read must not leak into the result.

    The hook commits v2 (different pause, capacity and windows) straight after
    the reader's first statement. A one-statement read has already seen v1 in
    full; a two-statement read would pair v1's fields with v2's windows.
    """
    v1 = _statement(W1, paused=_D, capacity=Decimal("3"))
    v2 = _statement(W2, W3, paused=_D + timedelta(days=30), capacity=Decimal("9.5"))
    _write(session_factory, tenant_id, speaker, v1, actor=speaker)
    counter = 0

    def _writer_commits_v2(_conn, _cursor, _statement_sql, _params, _context, _executemany):
        nonlocal counter
        if counter:
            return
        counter += 1
        _write(
            session_factory,
            tenant_id,
            speaker,
            v2,
            actor=connector,
            source=AvailabilitySource.CONNECTOR,
            expected_version=1,
        )

    with session_factory() as reader_session:
        conn = reader_session.connection()
        event.listen(conn, "after_cursor_execute", _writer_commits_v2)
        if reader == "get":
            result = REPO.get(reader_session, tenant_id=tenant_id, professional_id=speaker)
        else:
            result = REPO.get_many(
                reader_session, tenant_id=tenant_id, professional_ids=[speaker]
            ).get(speaker)
        event.remove(conn, "after_cursor_execute", _writer_commits_v2)

    assert counter == 1
    assert result is not None
    assert result.version == 1
    assert result.statement == v1
    assert result.updated_source is AvailabilitySource.SPEAKER

    fresh = _read(session_factory, tenant_id, speaker)
    assert fresh is not None
    assert fresh.version == 2
    assert fresh.statement == v2
