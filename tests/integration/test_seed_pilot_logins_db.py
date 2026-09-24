"""``seed-pilot-logins`` against a live database, after one login gained two roles.

B26 T6b-5 plan §3.4 and §8.2. ``seed-logins`` runs on every VM deploy and its
exit code gates the release (``scripts/vm/deploy.sh``), so the case that must
not break is the re-run *after* an Event Host login accepted a Speaker
invitation, and the run at an address a Speaker activated first.

Subjects and addresses are unique per test: ``external_subject`` is globally
unique and addresses match across all tenants.
"""

from __future__ import annotations

import dataclasses
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from conftest import TEST_TENANT_SLUG_PREFIX, unique_subject
from smartmatch_domain.pilot_credentials import (
    MINIMUM_ITERATIONS,
    derive_password_hash,
    new_salt,
)
from smartmatch_persistence import login_accounts
from smartmatch_persistence.login_accounts import NewLogin
from smartmatch_persistence.pilot_auth import PilotCredentialRepository
from sqlalchemy import Engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import seed_pilot_logins

pytestmark = pytest.mark.integration

_UNIT_PATH = "pilot"
_SPEAKER_PATH = "pilot.speakers"


def _pw() -> str:
    return "pw-" + uuid.uuid4().hex


@pytest.fixture
def entries(monkeypatch: pytest.MonkeyPatch) -> dict[str, seed_pilot_logins.RoleCredential]:
    """The four entries with per-run subjects, so parallel runs cannot collide."""
    unique = tuple(
        dataclasses.replace(
            entry, subject=unique_subject(f"{entry.subject}-{uuid.uuid4().hex[:6]}")
        )
        for entry in seed_pilot_logins.ROLE_CREDENTIALS
    )
    monkeypatch.setattr(seed_pilot_logins, "ROLE_CREDENTIALS", unique)
    return {entry.role: entry for entry in unique}


def _environ(entries, **addresses: str) -> dict[str, str]:
    environ: dict[str, str] = {}
    for role, address in addresses.items():
        environ[entries[role].email_var] = address
        environ[entries[role].password_var] = _pw()
    return environ


def _seed(engine: Engine, tenant_id: uuid.UUID, environ: dict[str, str]):
    slug = f"{TEST_TENANT_SLUG_PREFIX}{tenant_id.hex[:12]}"
    with engine.begin() as conn:
        return seed_pilot_logins.seed_role_logins(
            conn,
            environ=environ,
            tenant_slug=slug,
            tenant_name=slug,
            unit_path=_UNIT_PATH,
            unit_type="program",
            unit_name="Synthetic Pilot Unit",
        )


def _account_id(engine: Engine, subject: str) -> uuid.UUID:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id FROM user_account WHERE external_subject = :s"), {"s": subject}
        ).scalar_one()


def _rows(engine: Engine, sql: str, **params) -> list:
    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).all())


def _speaker_unit(engine: Engine, tenant_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :t, CAST(:p AS ltree), 'department', 'Speakers') "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": uuid.uuid4(), "t": tenant_id, "p": _SPEAKER_PATH},
        )


def _grant_speaker(engine: Engine, tenant_id: uuid.UUID, address: str, **create) -> uuid.UUID:
    """What activation does: ``find_or_add_role('speaker')`` at the address."""
    with engine.begin() as conn:
        grant = login_accounts.find_or_add_role(
            conn,
            tenant_id=tenant_id,
            email=address,
            role="speaker",
            path=_SPEAKER_PATH,
            now=datetime.now(UTC),
            **create,
        )
    return grant.user_id


def test_rerun_after_a_host_gains_speaker_succeeds_and_leaves_speaker_alone(
    engine: Engine, tenant_id: uuid.UUID, entries
) -> None:
    address = f"host-{uuid.uuid4().hex[:10]}@seed.invalid"
    environ = _environ(entries, volunteer=address)
    _seed(engine, tenant_id, environ)
    host = _account_id(engine, entries["volunteer"].subject)
    _speaker_unit(engine, tenant_id)
    assert _grant_speaker(engine, tenant_id, address) == host
    speaker_before = _rows(
        engine, "SELECT * FROM membership WHERE user_id = :u AND role = 'speaker'", u=host
    )

    outcomes = _seed(engine, tenant_id, environ)

    assert [o.created for o in outcomes if o.role == "volunteer"] == [True]
    assert (
        _rows(engine, "SELECT * FROM membership WHERE user_id = :u AND role = 'speaker'", u=host)
        == speaker_before
    )
    assert [
        r.role for r in _rows(engine, "SELECT role FROM membership WHERE user_id = :u", u=host)
    ].count("volunteer") == 1


def test_seed_at_an_activated_speakers_address_creates_no_second_credential(
    engine: Engine, tenant_id: uuid.UUID, entries
) -> None:
    address = f"speaker-{uuid.uuid4().hex[:10]}@seed.invalid"
    _speaker_unit(engine, tenant_id)
    contact = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :t, :s, 'contact@placeholder.invalid')"
            ),
            {"id": contact, "t": tenant_id, "s": unique_subject(f"contact-{contact.hex}")},
        )
    stored = derive_password_hash(_pw(), salt=new_salt(), iterations=MINIMUM_ITERATIONS)
    _grant_speaker(engine, tenant_id, address, create=NewLogin(user_id=contact, password=stored))

    outcomes = _seed(engine, tenant_id, _environ(entries, volunteer=address))

    [outcome] = [o for o in outcomes if o.role == "volunteer"]
    assert outcome.created and outcome.foreign_login
    with engine.connect() as conn:
        from sqlalchemy.orm import Session

        with Session(bind=conn) as session:
            account = PilotCredentialRepository().load_by_email(session, email=address)
    assert account is not None and account.user_id == contact
    assert account.password.digest == stored.digest  # the seed's password was not applied
    assert sorted(
        r.role for r in _rows(engine, "SELECT role FROM membership WHERE user_id = :u", u=contact)
    ) == ["speaker", "volunteer"]
    assert (
        _rows(
            engine,
            "SELECT id FROM user_account WHERE external_subject = :s",
            s=entries["volunteer"].subject,
        )
        == []
    )


def test_two_runs_are_idempotent(engine: Engine, tenant_id: uuid.UUID, entries) -> None:
    addresses = {
        role: f"{role}-{uuid.uuid4().hex[:10]}@seed.invalid"
        for role in ("coordinator", "admin", "student", "volunteer")
    }
    environ = _environ(entries, **addresses)

    def state() -> list:
        return _rows(
            engine,
            "SELECT u.external_subject, u.email, m.role, m.granted_path::text AS path, "
            "m.valid_from, m.valid_until, (SELECT count(*) FROM pilot_credential c "
            " WHERE c.tenant_id = u.tenant_id AND c.user_id = u.id) AS creds "
            "FROM user_account u JOIN membership m ON m.tenant_id = u.tenant_id "
            "AND m.user_id = u.id WHERE u.tenant_id = :t ORDER BY 1, 3",
            t=tenant_id,
        )

    first = _seed(engine, tenant_id, environ)
    after_first = state()
    second = _seed(engine, tenant_id, environ)

    assert [o.created for o in first] == [o.created for o in second] == [True] * 4
    assert state() == after_first
    assert len(after_first) == 6  # two connector logins x two roles + student + volunteer
    assert {row.creds for row in after_first} == {1}
    assert all("password rotated" in o.reason for o in second)
