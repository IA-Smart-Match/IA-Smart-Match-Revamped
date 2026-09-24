"""Activation's transaction and locks, against a live database (B26 T6b-1 plan §5).

Concurrency is made deterministic by holding one session's transaction open
while a second one runs on a thread, then committing the first.
"""

from __future__ import annotations

import secrets
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit, unique_subject
from smartmatch_api import speaker_portal_activation as activation
from smartmatch_api.speaker_portal_activation import ActivationRefused, activate_new_login
from smartmatch_domain.speaker_portal import derive_token, token_hash
from smartmatch_persistence.speaker_portal import SpeakerPortalRepository
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

_NOW = datetime.now(UTC).replace(microsecond=0)
_SECRET = secrets.token_urlsafe(40)
_BLOCK_SECONDS = 1.0


def _new_pw() -> str:
    return "pw-" + uuid.uuid4().hex


def _speaker(engine: Engine, tenant_id: uuid.UUID, *, address: str) -> tuple[uuid.UUID, str]:
    """A contact with a live invitation. Returns ``(professional_id, token)``."""
    professional_id, channel_id, issuer_id, invitation_id = (uuid.uuid4() for _ in range(4))
    with engine.begin() as conn:
        unit = ensure_owning_unit(conn, tenant_id)
        for user_id in (professional_id, issuer_id):
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :t, :s, :e)"
                ),
                {
                    "id": user_id,
                    "t": tenant_id,
                    "s": unique_subject(f"act-{user_id.hex[:8]}"),
                    "e": f"{user_id.hex[:8]}@placeholder.invalid",
                },
            )
        conn.execute(
            text(
                "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                "full_name) VALUES (:t, :p, :u, 'Dana Reyes')"
            ),
            {"t": tenant_id, "p": professional_id, "u": unit},
        )
        conn.execute(
            text(
                "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
                "channel_kind, address, contact_state, consent_source, consent_recorded_at) "
                "VALUES (:id, :t, :u, :p, 'email', :a, 'active_candidate', 'in_person', :now)"
            ),
            {
                "id": channel_id,
                "t": tenant_id,
                "u": unit,
                "p": professional_id,
                "a": address,
                "now": _NOW,
            },
        )
        token = derive_token(_SECRET, invitation_id)
        conn.execute(
            text(
                "INSERT INTO speaker_portal_invitation (id, tenant_id, professional_id, "
                "contact_channel_id, issued_by_user_id, token_hash, issued_at, expires_at) "
                "VALUES (:id, :t, :p, :c, :i, :h, :now, :exp)"
            ),
            {
                "id": invitation_id,
                "t": tenant_id,
                "p": professional_id,
                "c": channel_id,
                "i": issuer_id,
                "h": token_hash(token),
                "now": _NOW,
                "exp": _NOW + timedelta(days=7),
            },
        )
    return professional_id, token


def _activate(session: Session, token: str) -> None:
    activate_new_login(
        session,
        token=token,
        new_password=_new_pw(),
        secret=_SECRET,
        now=datetime.now(UTC),
        issue_session=False,
    )


def _in_thread(factory: sessionmaker[Session], token: str) -> tuple[threading.Thread, list]:
    outcome: list = []

    def run() -> None:
        with factory() as session:
            try:
                _activate(session, token)
                session.commit()
                outcome.append("activated")
            except ActivationRefused:
                session.rollback()
                outcome.append("refused")

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :s, :s)"),
            {"id": tid, "s": f"test-act-other-{tid.hex[:12]}"},
        )
    yield tid
    with engine.begin() as conn:
        for table in ("pilot_session", "pilot_credential", *_TENANT_SCOPED_TABLES):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": tid})


@pytest.fixture(autouse=True)
def _drop_credentials(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        for table in ("pilot_session", "pilot_credential"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant_id})


def _state(engine: Engine, professional_id: uuid.UUID) -> tuple:
    with engine.connect() as conn:
        return tuple(
            conn.execute(
                text(
                    "SELECT (SELECT email FROM user_account WHERE id = :p), "
                    "(SELECT count(*) FROM pilot_credential WHERE user_id = :p), "
                    "(SELECT count(*) FROM membership WHERE user_id = :p), "
                    "(SELECT account_user_id FROM speaker_profile WHERE professional_id = :p), "
                    "(SELECT count(*) FROM speaker_portal_invitation "
                    " WHERE professional_id = :p AND accepted_at IS NOT NULL)"
                ),
                {"p": professional_id},
            ).one()
        )


def test_activation_is_atomic(
    engine: Engine, session_factory, tenant_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail the bind, after ``find_or_add_role`` wrote the email, credential and
    membership: nothing from steps 10–14 persists (T6b-5 moved those writes)."""
    professional_id, token = _speaker(
        engine, tenant_id, address=f"atomic-{uuid.uuid4().hex[:8]}@example.invalid"
    )
    before = _state(engine, professional_id)

    def boom(*args, **kwargs):
        raise RuntimeError("injected failure at the bind")

    monkeypatch.setattr(activation._portal, "bind_profile", boom)
    with session_factory() as session:
        with pytest.raises(RuntimeError):
            _activate(session, token)
        session.rollback()

    assert _state(engine, professional_id) == before


def test_concurrent_activation_of_one_token_binds_once(
    engine: Engine, session_factory, tenant_id
) -> None:
    professional_id, token = _speaker(
        engine, tenant_id, address=f"once-{uuid.uuid4().hex[:8]}@example.invalid"
    )
    with session_factory() as first:
        _activate(first, token)
        thread, outcome = _in_thread(session_factory, token)
        thread.join(_BLOCK_SECONDS)
        assert thread.is_alive(), "the second activation should wait on the profile lock"
        first.commit()
    thread.join(10)

    assert outcome == ["refused"]
    assert _state(engine, professional_id)[1:3] == (1, 1)


def test_concurrent_new_login_for_one_address_creates_one_credential(
    engine: Engine, session_factory, tenant_id, other_tenant_id
) -> None:
    """Two tenants, one mailbox: the address lock serializes them, and the second refuses."""
    address = f"shared-{uuid.uuid4().hex[:8]}@example.invalid"
    first_id, first_token = _speaker(engine, tenant_id, address=address)
    _second_id, second_token = _speaker(engine, other_tenant_id, address=address.upper())

    with session_factory() as first:
        _activate(first, first_token)
        thread, outcome = _in_thread(session_factory, second_token)
        thread.join(_BLOCK_SECONDS)
        assert thread.is_alive(), "the second activation should wait on the address lock"
        first.commit()
    thread.join(10)

    assert outcome == ["refused"]
    with engine.connect() as conn:
        holders = conn.execute(
            text(
                "SELECT count(*) FROM user_account u JOIN pilot_credential c "
                "ON c.tenant_id = u.tenant_id AND c.user_id = u.id "
                "WHERE lower(btrim(u.email)) = lower(btrim(:a))"
            ),
            {"a": address},
        ).scalar_one()
    assert holders == 1
    assert _state(engine, first_id)[3] == first_id


def test_invite_and_activation_take_the_profile_lock_first(
    engine: Engine, session_factory, tenant_id
) -> None:
    """An invite blocked behind an activation's profile lock proceeds after the commit
    and sees the profile bound (the route's ``409 speaker_portal_already_active``)."""
    professional_id, token = _speaker(
        engine, tenant_id, address=f"order-{uuid.uuid4().hex[:8]}@example.invalid"
    )
    repository = SpeakerPortalRepository()
    seen: list = []

    def invite_first_lock() -> None:
        with session_factory() as session:
            profile = repository.lock_profile(
                session, tenant_id=tenant_id, professional_id=professional_id
            )
            seen.append(profile.account_user_id if profile else "missing")
            session.rollback()

    with session_factory() as first:
        _activate(first, token)
        thread = threading.Thread(target=invite_first_lock)
        thread.start()
        thread.join(_BLOCK_SECONDS)
        assert thread.is_alive(), "the invite should wait on the profile lock"
        first.commit()
    thread.join(10)

    assert seen == [professional_id]
