"""Contract tests for Speaker portal invite, revoke, access and activation (B26 T6b-1).

``SPEAKER_PORTAL`` is off in every scope, so ``smartmatch_api.main.app`` mounts
none of these routes. This file builds its own application from the three
routers plus ``/v1/me`` and ``/v1/auth/login``, with the token secret on
``app.state`` exactly as ``main.py`` sets it when the capability is on.

Token-, password- and secret-shaped values are built at runtime, never written
as literals (forbidden-behaviour scanner, gitleaks).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.routers import auth as auth_router
from smartmatch_api.routers import me as me_router
from smartmatch_api.routers import speaker_portal as portal_router
from smartmatch_domain.pilot_credentials import derive_password_hash, new_salt
from smartmatch_domain.speaker_portal import ACTIVATION_URL_SENTINEL, derive_token
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.portal"
SIBLING_UNIT_PATH = "iawest.portalsibling"
FROZEN_NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)

_CLEANUP = (
    "pilot_session",
    "pilot_credential",
    "speaker_portal_invitation",
    "delivery_event",
    "outreach_send",
    "outreach_draft",
    "contact_channel_transition",
    "contact_channel",
    "suppression_record",
    "job_event",
    "outbox_record",
    "job",
    "idempotency_record",
    "speaker_profile",
    "membership",
    "user_account",
    "org_unit",
    "rate_limit_counter",
)


def _new_secret() -> str:
    return secrets.token_urlsafe(40)


def _new_pw() -> str:
    return "pw-" + uuid.uuid4().hex


def build_app(session_factory: Any, verifier: FixtureTokenVerifier, secret: str) -> FastAPI:
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in (
        portal_router.router,
        portal_router.public_router,
        portal_router.pages_router,
        me_router.router,
        auth_router.router,
    ):
        app.include_router(router)
    app.state.session_factory = session_factory
    app.state.token_verifier = verifier
    app.state.speaker_portal_token_secret = secret
    return app


class _Ctx:
    def __init__(self, engine: Engine, tenant_id: uuid.UUID, unit_id, sibling_id, token: str):
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.sibling_unit_id = sibling_id
        self.bearer = token
        self.coordinator_id: uuid.UUID
        self.secret = _new_secret()
        self.verifier = FixtureTokenVerifier()
        self.session_factory = create_session_factory(
            engine.url.render_as_string(hide_password=False)
        )
        self.client = self.rebuild(self.secret)

    def rebuild(self, secret: str) -> TestClient:
        self.secret = secret
        self.client = TestClient(build_app(self.session_factory, self.verifier, secret))
        return self.client

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer}"}

    # -- set-up ------------------------------------------------------------

    def contact(
        self,
        *,
        state: str = "active_candidate",
        unit_id: uuid.UUID | None = None,
        address: str | None = None,
        consent_source: str | None = "in_person",
    ) -> tuple[uuid.UUID, uuid.UUID, str]:
        """``(professional_id, channel_id, address)`` for a new roster contact."""
        professional_id = uuid.uuid4()
        channel_id = uuid.uuid4()
        owning = unit_id or self.unit_id
        address = address or f"Speaker-{professional_id.hex[:8]}@Synthetic.invalid"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :t, :s, :e)"
                ),
                {
                    "id": professional_id,
                    "t": self.tenant_id,
                    "s": f"sub-portal-{professional_id.hex}",
                    "e": f"{professional_id.hex[:8]}@placeholder.invalid",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                    "full_name) VALUES (:t, :p, :u, 'Dana Reyes')"
                ),
                {"t": self.tenant_id, "p": professional_id, "u": owning},
            )
            conn.execute(
                text(
                    "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
                    "channel_kind, address, contact_state, consent_source, consent_recorded_at) "
                    "VALUES (:id, :t, :u, :p, 'email', :a, :s, :src, "
                    " CASE WHEN CAST(:src AS text) IS NULL THEN NULL ELSE now() END)"
                ),
                {
                    "id": channel_id,
                    "t": self.tenant_id,
                    "u": owning,
                    "p": professional_id,
                    "a": address,
                    "s": state,
                    "src": consent_source,
                },
            )
        return professional_id, channel_id, address

    def execute(self, sql: str, **params: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)

    def scalar(self, sql: str, **params: Any) -> Any:
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params).scalar_one_or_none()

    def rows(self, sql: str, **params: Any) -> list[Any]:
        with self.engine.begin() as conn:
            return list(conn.execute(text(sql), params).all())

    def other_credentialed_account(self, email: str, *, tenant_id: uuid.UUID | None = None):
        """An account in any tenant that already holds a pilot credential for ``email``."""
        user_id = uuid.uuid4()
        tid = tenant_id or self.tenant_id
        self.execute(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :t, :s, :e)",
            id=user_id,
            t=tid,
            s=f"sub-other-{user_id.hex}",
            e=email,
        )
        self.credential_for(user_id, tenant_id=tid)
        return user_id

    def credential_for(self, user_id: uuid.UUID, *, tenant_id: uuid.UUID | None = None) -> None:
        stored = derive_password_hash(_new_pw(), salt=new_salt())
        self.execute(
            "INSERT INTO pilot_credential (id, tenant_id, user_id, algorithm, iterations, "
            "salt, password_hash) VALUES (:id, :t, :u, :alg, :it, :salt, :h)",
            id=uuid.uuid4(),
            t=tenant_id or self.tenant_id,
            u=user_id,
            alg=stored.algorithm,
            it=stored.iterations,
            salt=stored.salt,
            h=stored.digest,
        )

    # -- requests ----------------------------------------------------------

    def base(self, professional_id: uuid.UUID, unit_id: uuid.UUID | None = None) -> str:
        return f"/v1/units/{unit_id or self.unit_id}/speaker-contacts/{professional_id}"

    def invite(self, professional_id, channel_id, *, unit_id=None):
        return self.client.post(
            f"{self.base(professional_id, unit_id)}/portal-invitations",
            json={"contact_channel_id": str(channel_id)},
            headers=self.headers,
        )

    def revoke(self, professional_id):
        return self.client.delete(
            f"{self.base(professional_id)}/portal-invitations/current", headers=self.headers
        )

    def access(self, professional_id):
        return self.client.get(f"{self.base(professional_id)}/portal-access", headers=self.headers)

    def activate(self, token: str, pw: str | None = None):
        return self.client.post(
            "/v1/speaker-portal/activate",
            json={"token": token, "new_password": pw or _new_pw()},
        )

    def invited(self, **contact_kwargs: Any) -> tuple[uuid.UUID, uuid.UUID, str, str]:
        """``(professional_id, invitation_id, token, address)`` after a successful invite."""
        professional_id, channel_id, address = self.contact(**contact_kwargs)
        response = self.invite(professional_id, channel_id)
        assert response.status_code == 202, response.text
        invitation_id = response.json()["invitation_id"]
        return professional_id, uuid.UUID(invitation_id), self.token_for(invitation_id), address

    def token_for(self, invitation_id: Any) -> str:
        return derive_token(self.secret, uuid.UUID(str(invitation_id)))


@pytest.fixture(scope="module")
def engine() -> Engine:
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM speaker_portal_invitation LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


def _make_tenant(engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str]:
    tenant_id, unit_id, sibling_id, user_id = (uuid.uuid4() for _ in range(4))
    subject = f"sub-portal-conn-{uuid.uuid4().hex}"
    bearer = f"tok-portal-{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-portal-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "College of Business"),
            (sibling_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {"id": user_id, "tid": tenant_id, "subject": subject, "email": f"{subject}@x.edu"},
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )
    return tenant_id, unit_id, sibling_id, user_id, subject + "|" + bearer


def _drop_tenant(engine: Engine, tenant_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        for table in _CLEANUP:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": tenant_id})


@pytest.fixture
def ctx(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Ctx]:
    tenant_id, unit_id, sibling_id, user_id, pair = _make_tenant(engine)
    subject, bearer = pair.split("|")
    context = _Ctx(engine, tenant_id, unit_id, sibling_id, bearer)
    context.coordinator_id = user_id
    context.verifier.register(bearer, subject)
    # Activation charges a pre-authentication bucket keyed by client address;
    # give each test its own so the suite does not exhaust one bucket.
    monkeypatch.setattr(
        portal_router, "_activation_caller_key", lambda request: f"test-{tenant_id.hex}"
    )
    yield context
    _drop_tenant(engine, tenant_id)


@pytest.fixture
def other_tenant(engine: Engine) -> Iterator[uuid.UUID]:
    tenant_id, *_ = _make_tenant(engine)
    yield tenant_id
    _drop_tenant(engine, tenant_id)


# ---------------------------------------------------------------------------
# Invite, revoke, access
# ---------------------------------------------------------------------------


def test_invite_returns_202_and_one_live_invitation(ctx: _Ctx) -> None:
    professional_id, channel_id, _ = ctx.contact()
    response = ctx.invite(professional_id, channel_id)

    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) == {"invitation_id", "status", "expires_at", "job_id", "events_url"}
    assert body["status"] == "invited"
    assert body["events_url"] == f"/v1/jobs/{body['job_id']}/events"
    live = ctx.rows(
        "SELECT id, contact_channel_id, issued_by_user_id FROM speaker_portal_invitation "
        "WHERE tenant_id = :t AND accepted_at IS NULL AND revoked_at IS NULL",
        t=ctx.tenant_id,
    )
    assert [(str(r.id), r.contact_channel_id, r.issued_by_user_id) for r in live] == [
        (body["invitation_id"], channel_id, ctx.coordinator_id)
    ]


def test_invite_stores_explicit_timestamps_from_one_clock(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(portal_router, "utc_now", lambda: FROZEN_NOW)
    professional_id, channel_id, _ = ctx.contact()
    response = ctx.invite(professional_id, channel_id)
    assert response.status_code == 202, response.text

    row = ctx.rows(
        "SELECT i.issued_at, i.expires_at, d.approved_at FROM speaker_portal_invitation i "
        "JOIN outreach_draft d ON d.tenant_id = i.tenant_id AND d.contact_channel_id = "
        "i.contact_channel_id WHERE i.id = :i",
        i=response.json()["invitation_id"],
    )[0]
    assert row.issued_at == FROZEN_NOW
    assert row.expires_at == FROZEN_NOW + timedelta(days=7)
    assert row.approved_at == FROZEN_NOW


def test_invite_draft_body_holds_only_the_placeholder(ctx: _Ctx) -> None:
    _professional_id, invitation_id, token, _ = ctx.invited()
    draft = ctx.rows(
        "SELECT d.subject, d.body, d.template_id, d.status FROM outreach_draft d "
        "JOIN speaker_portal_invitation i ON i.contact_channel_id = d.contact_channel_id "
        "WHERE i.id = :i",
        i=invitation_id,
    )[0]
    assert draft.template_id == "cba.speaker_portal_invite.v1"
    assert draft.status == "approved"
    assert draft.body.count(ACTIVATION_URL_SENTINEL) == 1
    assert ACTIVATION_URL_SENTINEL not in draft.subject
    assert token not in draft.body and "/s/" not in draft.body


def test_outreach_drafts_list_never_contains_the_token(ctx: _Ctx) -> None:
    """Raw text search across every stored draft for the token and its hash."""
    _, _invitation_id, token, _ = ctx.invited()
    digest_hex = hashlib.sha256(token.encode()).hexdigest()
    dumped = " ".join(
        f"{r.subject} {r.body}"
        for r in ctx.rows(
            "SELECT subject, body FROM outreach_draft WHERE tenant_id = :t", t=ctx.tenant_id
        )
    )
    assert token not in dumped and digest_hex not in dumped


def test_job_payload_and_invite_response_never_contain_the_token(ctx: _Ctx) -> None:
    professional_id, channel_id, _ = ctx.contact()
    response = ctx.invite(professional_id, channel_id)
    token = ctx.token_for(response.json()["invitation_id"])
    assert token not in response.text
    payload = ctx.scalar("SELECT payload::text FROM job WHERE id = :j", j=response.json()["job_id"])
    assert token not in payload
    assert response.json()["invitation_id"] in payload
    access = ctx.access(professional_id)
    assert token not in access.text


@pytest.mark.parametrize(
    "case", ["suppressed", "not_active", "other_prof", "other_unit", "unknown"]
)
def test_invite_refuses_ineligible_channel(ctx: _Ctx, case: str) -> None:
    professional_id, channel_id, address = ctx.contact(
        state="consented" if case == "not_active" else "active_candidate"
    )
    if case == "suppressed":
        ctx.execute(
            "INSERT INTO suppression_record (id, tenant_id, address, suppressed_at, source) "
            "VALUES (:i, :t, :a, now(), 'unsubscribe_link')",
            i=uuid.uuid4(),
            t=ctx.tenant_id,
            a=address,
        )
    elif case == "other_prof":
        _, channel_id, _ = ctx.contact()
    elif case == "other_unit":
        _, channel_id, _ = ctx.contact(unit_id=ctx.sibling_unit_id)
    elif case == "unknown":
        channel_id = uuid.uuid4()

    response = ctx.invite(professional_id, channel_id)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "speaker_portal_channel_not_eligible"
    assert (
        ctx.scalar(
            "SELECT count(*) FROM speaker_portal_invitation WHERE tenant_id = :t", t=ctx.tenant_id
        )
        == 0
    )


def test_invite_other_unit_profile_is_404(ctx: _Ctx) -> None:
    professional_id, channel_id, _ = ctx.contact(unit_id=ctx.sibling_unit_id)
    response = ctx.invite(professional_id, channel_id)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "speaker_contact_not_found"


def test_invite_bound_profile_is_409(ctx: _Ctx) -> None:
    professional_id, _, token, _ = ctx.invited()
    assert ctx.activate(token).status_code == 200
    channel_id = ctx.scalar(
        "SELECT id FROM contact_channel WHERE professional_id = :p", p=professional_id
    )
    response = ctx.invite(professional_id, channel_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "speaker_portal_already_active"


def test_live_unique_violation_maps_to_409_conflict(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5: forced past the profile lock (revoke disabled), the unique index answers 409."""
    professional_id, channel_id, _ = ctx.contact()
    assert ctx.invite(professional_id, channel_id).status_code == 202
    monkeypatch.setattr(portal_router._portal, "revoke_live", lambda *a, **k: False)
    response = ctx.invite(professional_id, channel_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "speaker_portal_invitation_conflict"


def test_second_invite_revokes_the_first(ctx: _Ctx) -> None:
    professional_id, first_id, first_token, _ = ctx.invited()
    channel_id = ctx.scalar(
        "SELECT id FROM contact_channel WHERE professional_id = :p", p=professional_id
    )
    second = ctx.invite(professional_id, channel_id)
    assert second.status_code == 202
    assert ctx.scalar(
        "SELECT revoked_at IS NOT NULL FROM speaker_portal_invitation WHERE id = :i", i=first_id
    )
    assert ctx.activate(first_token).status_code == 400
    assert ctx.activate(ctx.token_for(second.json()["invitation_id"])).status_code == 200


def test_revoke_is_idempotent(ctx: _Ctx) -> None:
    professional_id, _invitation_id, token, _ = ctx.invited()
    assert ctx.revoke(professional_id).json() == {"revoked": True}
    assert ctx.revoke(professional_id).json() == {"revoked": False}
    assert ctx.activate(token).status_code == 400
    other, _, _ = ctx.contact(unit_id=ctx.sibling_unit_id)
    assert ctx.revoke(other).status_code == 404


def test_access_status_transitions(ctx: _Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    professional_id, channel_id, _ = ctx.contact()
    assert ctx.access(professional_id).json() == {"status": "none"}

    invited = ctx.invite(professional_id, channel_id).json()
    body = ctx.access(professional_id).json()
    assert body["status"] == "invited"
    assert body["contact_channel_id"] == str(channel_id)
    assert body["expires_at"] and body["issued_at"]

    later = datetime.now(UTC) + timedelta(days=8)
    monkeypatch.setattr(portal_router, "utc_now", lambda: later)
    assert ctx.access(professional_id).json()["status"] == "expired"
    monkeypatch.undo()
    monkeypatch.setattr(
        portal_router, "_activation_caller_key", lambda request: f"test-{ctx.tenant_id.hex}"
    )

    assert ctx.activate(ctx.token_for(invited["invitation_id"])).status_code == 200
    body = ctx.access(professional_id).json()
    assert body["status"] == "active" and body["bound_at"]


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def test_activate_new_login_binds_and_issues_session(ctx: _Ctx) -> None:
    professional_id, invitation_id, token, _ = ctx.invited()
    response = ctx.activate(token)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer" and body["access_token"] and body["expires_at"]

    row = ctx.rows(
        "SELECT accepted_at, bound_account_user_id, binding_mode FROM "
        "speaker_portal_invitation WHERE id = :i",
        i=invitation_id,
    )[0]
    assert row.accepted_at is not None
    assert row.bound_account_user_id == professional_id
    assert row.binding_mode == "new_login"
    assert (
        ctx.scalar(
            "SELECT account_user_id FROM speaker_profile WHERE professional_id = :p",
            p=professional_id,
        )
        == professional_id
    )
    roles = ctx.rows(
        "SELECT role, granted_path::text AS path FROM membership WHERE user_id = :p",
        p=professional_id,
    )
    assert [(r.role, r.path) for r in roles] == [("speaker", UNIT_PATH)]


def test_activated_speaker_sees_speaker_membership_in_me(ctx: _Ctx) -> None:
    _, _, token, _ = ctx.invited()
    session_token = ctx.activate(token).json()["access_token"]
    me = ctx.client.get("/v1/me", headers={"Authorization": f"Bearer {session_token}"})
    assert me.status_code == 200, me.text
    assert [m["role"] for m in me.json()["memberships"]] == ["speaker"]


def test_activation_stores_the_trimmed_address_and_login_works(ctx: _Ctx) -> None:
    professional_id, _, token, address = ctx.invited(
        address=f"  Mixed.Case-{uuid.uuid4().hex[:6]}@Example.invalid "
    )
    pw = _new_pw()
    assert ctx.activate(token, pw).status_code == 200
    stored = ctx.scalar("SELECT email FROM user_account WHERE id = :p", p=professional_id)
    assert stored == address.strip()
    login = ctx.client.post(
        "/v1/auth/login", json={"email": address.strip().lower(), "password": pw}
    )
    assert login.status_code == 200, login.text


def _refusal_setup(ctx: _Ctx, case: str, other_tenant: uuid.UUID) -> tuple[str, uuid.UUID]:
    """Return ``(token, professional_id)`` arranged so activation must refuse."""
    if case == "unknown":
        return derive_token(ctx.secret, uuid.uuid4()), uuid.uuid4()
    if case == "malformed":
        return "not-a-token-" + uuid.uuid4().hex[:10], uuid.uuid4()
    state = {"rejected": "rejected", "stale": "stale", "discovered": "discovered"}.get(case)
    professional_id, invitation_id, token, address = ctx.invited()
    if case == "expired":
        ctx.execute(
            "UPDATE speaker_portal_invitation SET issued_at = issued_at - interval '8 days', "
            "expires_at = expires_at - interval '8 days' WHERE id = :i",
            i=invitation_id,
        )
    elif case == "accepted":
        assert ctx.activate(token).status_code == 200
    elif case == "revoked":
        ctx.revoke(professional_id)
    elif case == "profile_bound":
        ctx.execute(
            "UPDATE speaker_profile SET account_user_id = :p, account_bound_at = now() "
            "WHERE professional_id = :p",
            p=professional_id,
        )
    elif case == "address_held":
        ctx.other_credentialed_account(address, tenant_id=other_tenant)
    elif case == "address_held_case":
        ctx.other_credentialed_account(f"  {address.upper()}  ")
    elif case == "suspended":
        ctx.execute("UPDATE user_account SET suspended = true WHERE id = :p", p=professional_id)
    elif case == "already_credentialed":
        ctx.credential_for(professional_id)
    elif state is not None:
        ctx.execute(
            "UPDATE contact_channel SET contact_state = :s, consent_source = NULL, "
            "consent_recorded_at = NULL WHERE professional_id = :p",
            s=state,
            p=professional_id,
        )
    elif case == "rotated":
        ctx.rebuild(_new_secret())
    return token, professional_id


_REFUSALS = [
    "unknown",
    "malformed",
    "expired",
    "accepted",
    "revoked",
    "profile_bound",
    "address_held",
    "address_held_case",
    "suspended",
    "already_credentialed",
    "rejected",
    "stale",
    "discovered",
    "rotated",
]


@pytest.mark.parametrize("case", _REFUSALS)
def test_activate_refuses_every_bad_token_identically(
    ctx: _Ctx, other_tenant: uuid.UUID, case: str
) -> None:
    reference = ctx.activate(derive_token(ctx.secret, uuid.uuid4()))
    token, professional_id = _refusal_setup(ctx, case, other_tenant)

    before = ctx.rows(
        "SELECT (SELECT email FROM user_account WHERE id = :p) AS email, "
        "(SELECT count(*) FROM pilot_credential WHERE user_id = :p) AS creds, "
        "(SELECT count(*) FROM membership WHERE user_id = :p) AS roles",
        p=professional_id,
    )[0]
    response = ctx.activate(token)
    after = ctx.rows(
        "SELECT (SELECT email FROM user_account WHERE id = :p) AS email, "
        "(SELECT count(*) FROM pilot_credential WHERE user_id = :p) AS creds, "
        "(SELECT count(*) FROM membership WHERE user_id = :p) AS roles",
        p=professional_id,
    )[0]

    assert response.status_code == 400
    assert response.content == reference.content
    assert response.json()["error"]["code"] == "speaker_portal_invitation_invalid"
    assert tuple(after) == tuple(before)


def test_rotating_the_secret_invalidates_a_live_invitation(ctx: _Ctx) -> None:
    _, _, token, _ = ctx.invited()
    ctx.rebuild(_new_secret())
    assert ctx.activate(token).status_code == 400


@pytest.mark.parametrize("pw", ["x" * 11, "y" * 257, " " * 20], ids=["11", "257", "blank"])
def test_weak_password_is_422_for_any_token(ctx: _Ctx, pw: str) -> None:
    _, _, token, _ = ctx.invited()
    for candidate in (token, derive_token(ctx.secret, uuid.uuid4())):
        response = ctx.activate(candidate, pw)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "password_too_weak"


def test_activate_refuses_address_held_by_a_credentialed_account(ctx: _Ctx) -> None:
    professional_id, invitation_id, token, address = ctx.invited()
    ctx.other_credentialed_account(address)
    before_email = ctx.scalar("SELECT email FROM user_account WHERE id = :p", p=professional_id)

    assert ctx.activate(token).status_code == 400
    assert ctx.scalar("SELECT email FROM user_account WHERE id = :p", p=professional_id) == (
        before_email
    )
    assert (
        ctx.scalar("SELECT count(*) FROM pilot_credential WHERE user_id = :p", p=professional_id)
        == 0
    )
    assert ctx.scalar("SELECT count(*) FROM membership WHERE user_id = :p", p=professional_id) == 0
    assert (
        ctx.scalar(
            "SELECT accepted_at FROM speaker_portal_invitation WHERE id = :i", i=invitation_id
        )
        is None
    )


def test_activate_never_echoes_the_token(ctx: _Ctx) -> None:
    _, _, token, _ = ctx.invited()
    ok = ctx.activate(token)
    refused = ctx.activate(token)
    assert token not in ok.text and token not in refused.text
    assert all(token not in value for value in ok.headers.values())


def test_activation_is_rate_limited_separately_from_login(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = f"rl-{uuid.uuid4().hex}"
    monkeypatch.setattr(portal_router, "_activation_caller_key", lambda request: key)
    statuses = [ctx.activate(derive_token(ctx.secret, uuid.uuid4())).status_code for _ in range(11)]
    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429
    assert (
        ctx.scalar(
            "SELECT count(*) FROM pilot_login_attempt WHERE caller_key = :k",
            k=f"speaker_portal.activate:{key}",
        )
        == 1
    )
    assert ctx.scalar("SELECT count(*) FROM pilot_login_attempt WHERE caller_key = :k", k=key) == 0
    ctx.execute(
        "DELETE FROM pilot_login_attempt WHERE caller_key = :k", k=f"speaker_portal.activate:{key}"
    )


# ---------------------------------------------------------------------------
# /s pages
# ---------------------------------------------------------------------------


def _form(ctx: _Ctx, token: str, fields: dict[str, str] | str):
    return ctx.client.post(
        f"/s/{token}",
        data=fields if isinstance(fields, dict) else None,
        content=fields if isinstance(fields, str) else None,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_s_page_is_identical_for_every_token(ctx: _Ctx) -> None:
    _, _, token, _ = ctx.invited()
    pages = [ctx.client.get(f"/s/{t}") for t in (token, "x" * 43, "nope")]
    assert {p.status_code for p in pages} == {200}
    assert len({p.content for p in pages}) == 1
    page = pages[0]
    assert token not in page.text
    assert 'method="post"' in page.text and "action=" not in page.text
    assert 'autocomplete="new-password"' in page.text
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"


def test_s_form_activates_without_issuing_a_session(ctx: _Ctx) -> None:
    professional_id, _, token, _ = ctx.invited()
    pw = _new_pw()
    response = _form(ctx, token, {"new_password": pw, "confirm_password": pw})
    assert response.status_code == 200, response.text
    assert "/login" in response.text
    assert (
        ctx.scalar("SELECT count(*) FROM pilot_session WHERE user_id = :p", p=professional_id) == 0
    )
    assert (
        ctx.scalar(
            "SELECT account_user_id FROM speaker_profile WHERE professional_id = :p",
            p=professional_id,
        )
        == professional_id
    )


def test_s_form_refuses_mismatched_confirmation(ctx: _Ctx) -> None:
    professional_id, _, token, _ = ctx.invited()
    response = _form(ctx, token, {"new_password": _new_pw(), "confirm_password": _new_pw()})
    assert response.status_code == 422
    assert (
        ctx.scalar(
            "SELECT account_user_id FROM speaker_profile WHERE professional_id = :p",
            p=professional_id,
        )
        is None
    )


@pytest.mark.parametrize("case", _REFUSALS)
def test_s_form_refuses_every_bad_token_with_one_page(
    ctx: _Ctx, other_tenant: uuid.UUID, case: str
) -> None:
    """The form route's refusals, over the same cases as the JSON route: one page."""
    pw = _new_pw()
    fields = {"new_password": pw, "confirm_password": pw}
    reference = _form(ctx, derive_token(ctx.secret, uuid.uuid4()), fields)
    token, professional_id = _refusal_setup(ctx, case, other_tenant)
    before = _account_state(ctx, professional_id)

    response = _form(ctx, token, fields)

    assert response.status_code == 400
    assert response.content == reference.content
    assert _account_state(ctx, professional_id) == before


def _account_state(ctx: _Ctx, professional_id: uuid.UUID) -> tuple:
    return tuple(
        ctx.rows(
            "SELECT (SELECT email FROM user_account WHERE id = :p) AS email, "
            "(SELECT count(*) FROM pilot_credential WHERE user_id = :p) AS creds, "
            "(SELECT count(*) FROM membership WHERE user_id = :p) AS roles",
            p=professional_id,
        )[0]
    )


@pytest.mark.parametrize("trailing", ["\t", "\n"], ids=["tab", "newline"])
def test_activation_normalises_a_trailing_tab_or_newline(ctx: _Ctx, trailing: str) -> None:
    """One normalised address for the lock, the duplicate check and the stored email."""
    base = f"Dana-{uuid.uuid4().hex[:8]}@Example.invalid"
    professional_id, _, token, _ = ctx.invited(address=base + trailing)
    pw = _new_pw()

    assert ctx.activate(token, pw).status_code == 200
    stored = ctx.scalar("SELECT email FROM user_account WHERE id = :p", p=professional_id)
    assert stored == base.lower()
    login = ctx.client.post("/v1/auth/login", json={"email": base, "password": pw})
    assert login.status_code == 200, login.text


@pytest.mark.parametrize("trailing", ["\t", "\n"], ids=["tab", "newline"])
def test_a_trailing_tab_or_newline_does_not_escape_the_duplicate_check(
    ctx: _Ctx, trailing: str
) -> None:
    base = f"Held-{uuid.uuid4().hex[:8]}@Example.invalid"
    _, _, token, _ = ctx.invited(address=base + trailing)
    ctx.other_credentialed_account(base)
    assert ctx.activate(token).status_code == 400


@pytest.mark.parametrize("route", ["json", "form"])
def test_each_activation_reads_the_clock_once(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """R6: the rate-limit charge and the activation share one ``now``."""
    _, _, token, _ = ctx.invited()
    readings: list[datetime] = []

    def clock() -> datetime:
        readings.append(datetime.now(UTC))
        return readings[-1]

    monkeypatch.setattr(portal_router, "utc_now", clock)
    pw = _new_pw()
    if route == "json":
        response = ctx.activate(token, pw)
    else:
        response = _form(ctx, token, {"new_password": pw, "confirm_password": pw})
    assert response.status_code == 200, response.text
    assert len(readings) == 1


def test_s_form_body_over_2048_bytes_is_413(ctx: _Ctx) -> None:
    _, _, token, _ = ctx.invited()
    response = _form(ctx, token, "new_password=" + "a" * 2100 + "&confirm_password=a")
    assert response.status_code == 413


def test_s_form_accepts_two_256_char_ascii_passwords(ctx: _Ctx) -> None:
    """R9 arithmetic: two fully percent-encoded 256-char passwords fit in 2048 bytes."""
    _, _, token, _ = ctx.invited()
    pw = "!" * 256  # every character percent-encodes to three bytes
    encoded = "new_password=" + "%21" * 256 + "&confirm_password=" + "%21" * 256
    assert len(encoded) < 2048
    response = _form(ctx, token, encoded)
    assert response.status_code == 200, response.text
    assert pw not in response.text
