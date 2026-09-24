"""``login_accounts``, the one ``pilot_credential`` writer, against a live database.

B26 T6b-5 plan §3 and §8.2. Every address is unique per test: ``holders_for_address``
matches across **all** tenants, like ``load_by_email``, so a fixed address would
see another test's rows.

Password material is built at runtime (forbidden-behaviour scanner).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit, unique_subject
from smartmatch_domain.pilot_credentials import (
    MINIMUM_ITERATIONS,
    StoredPassword,
    derive_password_hash,
    new_salt,
)
from smartmatch_persistence import login_accounts
from smartmatch_persistence.login_accounts import (
    AccountAlreadyCredentialed,
    AddressAmbiguous,
    AddressInOtherTenant,
    AddressState,
    NewLogin,
    NoLoginForAddress,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

_NOW = datetime.now(UTC).replace(microsecond=0)
_PATH = "iawest.jobs"
_BLOCK_SECONDS = 1.0


def _stored() -> StoredPassword:
    return derive_password_hash(
        "pw-" + uuid.uuid4().hex, salt=new_salt(), iterations=MINIMUM_ITERATIONS
    )


def _address(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:10]}@login-accounts.invalid"


def _account(engine: Engine, tenant_id: uuid.UUID, email: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as conn:
        ensure_owning_unit(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :t, :s, :e)"
            ),
            {"id": user_id, "t": tenant_id, "s": unique_subject(f"la-{user_id.hex}"), "e": email},
        )
    return user_id


def _credential(engine: Engine, tenant_id: uuid.UUID, user_id: uuid.UUID) -> StoredPassword:
    stored = _stored()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pilot_credential (id, tenant_id, user_id, algorithm, iterations, "
                "salt, password_hash) VALUES (:id, :t, :u, :alg, :it, :salt, :h)"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant_id,
                "u": user_id,
                "alg": stored.algorithm,
                "it": stored.iterations,
                "salt": stored.salt,
                "h": stored.digest,
            },
        )
    return stored


def _login(engine: Engine, tenant_id: uuid.UUID, email: str) -> uuid.UUID:
    user_id = _account(engine, tenant_id, email)
    _credential(engine, tenant_id, user_id)
    return user_id


def _snapshot(engine: Engine, *user_ids: uuid.UUID) -> tuple:
    with engine.connect() as conn:
        return tuple(
            tuple(
                conn.execute(
                    text(
                        "SELECT (SELECT email FROM user_account WHERE id = :u), "
                        "(SELECT version FROM user_account WHERE id = :u), "
                        "(SELECT count(*) FROM pilot_credential WHERE user_id = :u), "
                        "(SELECT count(*) FROM membership WHERE user_id = :u)"
                    ),
                    {"u": user_id},
                ).one()
            )
            for user_id in user_ids
        )


def _memberships(engine: Engine, user_id: uuid.UUID) -> list:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT role, granted_path::text AS path, valid_from, valid_until, created_at "
                    "FROM membership WHERE user_id = :u ORDER BY created_at, role"
                ),
                {"u": user_id},
            ).all()
        )


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :s, :s)"),
            {"id": tid, "s": f"test-la-other-{tid.hex[:12]}"},
        )
    yield tid
    with engine.begin() as conn:
        for table in _TENANT_SCOPED_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": tid})


def _grant(session: Session, tenant_id: uuid.UUID, email: str, role: str, **kwargs):
    return login_accounts.find_or_add_role(
        session, tenant_id=tenant_id, email=email, role=role, path=_PATH, now=_NOW, **kwargs
    )


# ---------------------------------------------------------------------------
# holders_for_address
# ---------------------------------------------------------------------------


def test_holders_classify_none_one_other_and_ambiguous(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id, other_tenant_id
) -> None:
    free, mine, theirs, shared = (_address(n) for n in ("free", "mine", "theirs", "shared"))
    holder = _login(engine, tenant_id, mine)
    _account(engine, tenant_id, free)  # an account without a credential holds nothing
    _login(engine, other_tenant_id, theirs)
    _login(engine, tenant_id, shared)
    _login(engine, other_tenant_id, shared.upper())

    with session_factory() as session:
        states = {
            address: login_accounts.holders_for_address(
                session, tenant_id=tenant_id, address=address, lock=False
            )
            for address in (free, mine, theirs, shared)
        }
        session.rollback()

    assert states[free].state is AddressState.NONE and states[free].holder is None
    assert states[mine].state is AddressState.ONE_IN_TENANT
    assert states[mine].holder is not None and states[mine].holder.user_id == holder
    assert states[theirs].state is AddressState.OTHER_TENANT and states[theirs].holder is None
    assert states[shared].state is AddressState.AMBIGUOUS and states[shared].holder is None


def test_holders_report_whether_the_extra_account_is_credentialed(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("extra")
    bare = _account(engine, tenant_id, _address("bare"))
    credentialed = _login(engine, tenant_id, _address("cred"))
    with session_factory() as session:
        without = login_accounts.holders_for_address(
            session, tenant_id=tenant_id, address=address, lock=True, also_lock_user_id=bare
        )
        with_row = login_accounts.holders_for_address(
            session,
            tenant_id=tenant_id,
            address=address,
            lock=True,
            also_lock_user_id=credentialed,
        )
        session.rollback()

    assert without.state is AddressState.NONE and without.also_locked_credentialed is False
    # The extra row is locked, but it never counts as an address holder.
    assert with_row.state is AddressState.NONE and with_row.also_locked_credentialed is True


# ---------------------------------------------------------------------------
# find_or_add_role
# ---------------------------------------------------------------------------


def test_none_with_create_credentials_the_account_and_adds_the_role(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("new")
    contact = _account(engine, tenant_id, "contact@placeholder.invalid")
    stored = _stored()
    with session_factory() as session:
        grant = _grant(
            session,
            tenant_id,
            address,
            "speaker",
            create=NewLogin(user_id=contact, password=stored),
        )
        session.commit()

    assert grant.user_id == contact
    assert grant.login_created is True and grant.role_added is True
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT u.email, u.version, c.salt, c.password_hash FROM user_account u "
                "JOIN pilot_credential c ON c.tenant_id = u.tenant_id AND c.user_id = u.id "
                "WHERE u.id = :u"
            ),
            {"u": contact},
        ).one()
    assert row.email == address
    assert row.version == 2
    assert bytes(row.salt) == stored.salt and bytes(row.password_hash) == stored.digest
    assert [(m.role, m.path) for m in _memberships(engine, contact)] == [("speaker", _PATH)]


def test_none_without_create_raises_and_writes_nothing(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    with session_factory() as session:
        with pytest.raises(NoLoginForAddress):
            _grant(session, tenant_id, _address("nobody"), "speaker")
        session.rollback()


def test_one_in_tenant_adds_the_role_once(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("host")
    host = _login(engine, tenant_id, address)
    before = _snapshot(engine, host)[0][:3]

    with session_factory() as session:
        first = _grant(session, tenant_id, address, "speaker")
        session.commit()
    with session_factory() as session:
        second = _grant(session, tenant_id, address, "speaker")
        session.commit()

    assert (first.user_id, first.login_created, first.role_added) == (host, False, True)
    assert (second.user_id, second.login_created, second.role_added) == (host, False, False)
    assert first.external_subject == second.external_subject
    assert [m.role for m in _memberships(engine, host)] == ["speaker"]
    # Email, version and the credential are untouched.
    assert _snapshot(engine, host)[0][:3] == before


def test_an_expired_role_row_gets_a_new_active_row(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("expired")
    host = _login(engine, tenant_id, address)
    ended = _NOW - timedelta(days=1)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role, valid_until, "
                "created_at) VALUES (:id, :t, :u, CAST(:p AS ltree), 'speaker', :vu, :ca)"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant_id,
                "u": host,
                "p": _PATH,
                "vu": ended,
                "ca": ended - timedelta(days=1),
            },
        )

    with session_factory() as session:
        grant = _grant(session, tenant_id, address, "speaker")
        session.commit()

    assert grant.role_added is True
    rows = _memberships(engine, host)
    assert [(r.role, r.valid_until) for r in rows] == [("speaker", ended), ("speaker", None)]


def test_ambiguous_raises_and_writes_nothing(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("amb")
    first = _login(engine, tenant_id, address)
    second = _login(engine, tenant_id, f"  {address.upper()} ")
    contact = _account(engine, tenant_id, "c@placeholder.invalid")
    before = _snapshot(engine, first, second, contact)

    with session_factory() as session:
        with pytest.raises(AddressAmbiguous):
            _grant(
                session,
                tenant_id,
                address,
                "speaker",
                create=NewLogin(user_id=contact, password=_stored()),
            )
        session.rollback()

    assert _snapshot(engine, first, second, contact) == before


def test_other_tenant_raises_and_writes_nothing(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id, other_tenant_id
) -> None:
    address = _address("other")
    theirs = _login(engine, other_tenant_id, address)
    contact = _account(engine, tenant_id, "c@placeholder.invalid")
    before = _snapshot(engine, theirs, contact)

    with session_factory() as session:
        with pytest.raises(AddressInOtherTenant):
            _grant(
                session,
                tenant_id,
                address,
                "speaker",
                create=NewLogin(user_id=contact, password=_stored()),
            )
        session.rollback()

    assert _snapshot(engine, theirs, contact) == before


def test_create_for_an_already_credentialed_account_raises(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    """T6b-1's round-2 rule: a credentialed contact account is never re-passworded."""
    contact = _login(engine, tenant_id, "c@placeholder.invalid")
    before = _snapshot(engine, contact)
    with session_factory() as session:
        with pytest.raises(AccountAlreadyCredentialed):
            _grant(
                session,
                tenant_id,
                _address("free"),
                "speaker",
                create=NewLogin(user_id=contact, password=_stored()),
            )
        session.rollback()
    assert _snapshot(engine, contact) == before


def test_create_when_the_address_is_held_raises(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("held")
    host = _login(engine, tenant_id, address)
    contact = _account(engine, tenant_id, "c@placeholder.invalid")
    before = _snapshot(engine, host, contact)
    with session_factory() as session:
        with pytest.raises(AccountAlreadyCredentialed):
            _grant(
                session,
                tenant_id,
                address,
                "speaker",
                create=NewLogin(user_id=contact, password=_stored()),
            )
        session.rollback()
    assert _snapshot(engine, host, contact) == before


def test_create_for_a_suspended_or_foreign_account_raises(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id, other_tenant_id
) -> None:
    suspended = _account(engine, tenant_id, "s@placeholder.invalid")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE user_account SET suspended = true WHERE id = :u"), {"u": suspended}
        )
    foreign = _account(engine, other_tenant_id, "f@placeholder.invalid")
    for user_id in (suspended, foreign, uuid.uuid4()):
        with session_factory() as session:
            with pytest.raises(login_accounts.LoginAccountError):
                _grant(
                    session,
                    tenant_id,
                    _address("x"),
                    "speaker",
                    create=NewLogin(user_id=user_id, password=_stored()),
                )
            session.rollback()
    assert _snapshot(engine, suspended, foreign) == (
        ("s@placeholder.invalid", 1, 0, 0),
        ("f@placeholder.invalid", 1, 0, 0),
    )


def test_addresses_match_case_and_whitespace_insensitively_and_are_stored_trimmed(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("Mixed.Case")
    contact = _account(engine, tenant_id, "c@placeholder.invalid")
    with session_factory() as session:
        _grant(
            session,
            tenant_id,
            f"  {address}\t",
            "speaker",
            create=NewLogin(user_id=contact, password=_stored()),
        )
        session.commit()
    assert _snapshot(engine, contact)[0][0] == address

    with session_factory() as session:
        again = _grant(session, tenant_id, f" {address.upper()} ", "volunteer")
        session.commit()
    assert again.user_id == contact and again.login_created is False


def test_inserted_memberships_have_null_valid_from_and_created_at_now(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("window")
    host = _login(engine, tenant_id, address)
    with session_factory() as session:
        _grant(session, tenant_id, address, "speaker")
        session.commit()
    [row] = _memberships(engine, host)
    assert row.valid_from is None and row.valid_until is None
    assert row.created_at == _NOW


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


def test_the_address_lock_serializes_two_writers(
    session_factory: sessionmaker[Session],
) -> None:
    address = _address("lock")
    order: list[str] = []

    def second() -> None:
        with session_factory() as session:
            login_accounts.lock_address(session, address=f" {address.upper()} ")
            order.append("second")
            session.rollback()

    with session_factory() as first:
        login_accounts.lock_address(first, address=address)
        thread = threading.Thread(target=second)
        thread.start()
        thread.join(_BLOCK_SECONDS)
        assert thread.is_alive(), "the second writer should wait on the address lock"
        order.append("first")
        first.commit()
    thread.join(10)
    assert order == ["first", "second"]


def test_a_locked_credential_row_blocks_a_concurrent_update(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    address = _address("rowlock")
    host = _login(engine, tenant_id, address)
    finished: list[float] = []

    def rotate() -> None:
        with session_factory() as session:
            login_accounts.rotate_own_password(
                session, tenant_id=tenant_id, user_id=host, password=_stored(), now=_NOW
            )
            session.commit()
            finished.append(time.monotonic())

    with session_factory() as first:
        login_accounts.holders_for_address(first, tenant_id=tenant_id, address=address, lock=True)
        thread = threading.Thread(target=rotate)
        thread.start()
        thread.join(_BLOCK_SECONDS)
        assert thread.is_alive(), "the update should wait on the FOR UPDATE row lock"
        released = time.monotonic()
        first.commit()
    thread.join(10)
    assert finished and finished[0] >= released


# ---------------------------------------------------------------------------
# rotate_own_password, retire_login
# ---------------------------------------------------------------------------


def test_rotate_own_password_updates_only_that_row(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    mine = _login(engine, tenant_id, _address("mine"))
    other = _login(engine, tenant_id, _address("other"))
    fresh = _stored()
    later = _NOW + timedelta(hours=1)

    def rows() -> dict:
        with engine.connect() as conn:
            return {
                r.user_id: (bytes(r.salt), bytes(r.password_hash), r.updated_at)
                for r in conn.execute(
                    text(
                        "SELECT user_id, salt, password_hash, updated_at FROM pilot_credential "
                        "WHERE user_id IN (:a, :b)"
                    ),
                    {"a": mine, "b": other},
                )
            }

    before = rows()
    with session_factory() as session:
        login_accounts.rotate_own_password(
            session, tenant_id=tenant_id, user_id=mine, password=fresh, now=later
        )
        session.commit()
    after = rows()

    assert after[mine] == (fresh.salt, fresh.digest, later)
    assert after[other] == before[other]


def test_rotate_without_a_credential_raises(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    bare = _account(engine, tenant_id, _address("bare"))
    with session_factory() as session:
        with pytest.raises(NoLoginForAddress):
            login_accounts.rotate_own_password(
                session, tenant_id=tenant_id, user_id=bare, password=_stored(), now=_NOW
            )
        session.rollback()


def test_retire_login_revokes_sessions_and_deletes_the_credential(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id
) -> None:
    login = _login(engine, tenant_id, _address("retire"))
    keep = _login(engine, tenant_id, _address("keep"))
    with engine.begin() as conn:
        for user_id in (login, login, keep):
            conn.execute(
                text(
                    "INSERT INTO pilot_session (id, tenant_id, user_id, token_hash, issued_at, "
                    "expires_at) VALUES (:id, :t, :u, :h, :i, :e)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "u": user_id,
                    "h": uuid.uuid4().bytes + uuid.uuid4().bytes,
                    "i": _NOW,
                    "e": _NOW + timedelta(hours=12),
                },
            )
    later = _NOW + timedelta(minutes=5)
    with session_factory() as session:
        login_accounts.retire_login(session, tenant_id=tenant_id, user_id=login, now=later)
        session.commit()

    with engine.connect() as conn:
        sessions = conn.execute(
            text("SELECT user_id, revoked_at FROM pilot_session WHERE user_id IN (:a, :b)"),
            {"a": login, "b": keep},
        ).all()
        credentials = conn.execute(
            text("SELECT user_id FROM pilot_credential WHERE user_id IN (:a, :b)"),
            {"a": login, "b": keep},
        ).all()
    assert sorted((r.user_id == login, r.revoked_at) for r in sessions) == [
        (False, None),
        (True, later),
        (True, later),
    ]
    assert [r.user_id for r in credentials] == [keep]
