"""HTTP contracts for the Speaker's own channel consent (B26 T6b-3 plan §5.3, §9).

``GET /v1/me/contact-channels``, ``POST .../{channel_id}/opt-in`` and
``POST .../{channel_id}/opt-out``, mounted only under ``SPEAKER_PORTAL`` (off in
every scope), so this file builds its application from ``routers_for`` with that
one capability switched on, as ``test_speaker_self_api.py`` does.

Asserted here:

* **Scope.** The subject is the profile bound to the login (T6b-2's
  ``_authorize_speaker_self``); the Speaker sees their own channels across
  units, and nothing about who recorded what.
* **Opt-out** writes a ``speaker_portal`` suppression and a choice row, and is
  immediate: the next read and the next send refuse.
* **Opt-in** lifts only what the owner ruled (``speaker_portal`` anywhere;
  ``unsubscribe_link`` / ``one_click`` only on the login address; never a
  bounce, complaint or coordinator suppression) and walks the lifecycle with
  ``self_service`` consent.
* **Refusals** are one 404 for "not mine", T6b-2's 404/403 for the subject, 429
  after the write limit.

Speakers are bound by SQL. Bearer values are built at runtime.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.config import Settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.main import routers_for
from smartmatch_domain.product_scope import Capability
from smartmatch_domain.speaker_channel_consent import SELF_SERVICE_EVIDENCE
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.mychannels"
SECOND_UNIT_PATH = "iawest.mychannelstwo"
LIST = "/v1/me/contact-channels"

_CLEANUP = (
    "contact_channel_speaker_choice",
    "delivery_event",
    "outreach_send",
    "outreach_draft",
    "job_event",
    "outbox_record",
    "job",
    "idempotency_record",
    "contact_channel_transition",
    "contact_channel",
    "suppression_record",
    "speaker_profile",
    "membership",
    "user_account",
    "org_unit",
    "rate_limit_counter",
)

#: What the Speaker's view may carry, and nothing else (parent §2 privacy).
VIEW_KEYS = {
    "contact_channel_id",
    "channel_kind",
    "address",
    "contact_state",
    "send_eligible",
    "suppressed",
    "suppression_reason",
    "speaker_choice",
    "last_set_by",
    "can_opt_in",
    "can_opt_out",
    "updated_at",
}


class _PortalOn(Settings):
    def capability_enabled(self, capability: Capability) -> bool:  # type: ignore[override]
        return capability is Capability.SPEAKER_PORTAL or super().capability_enabled(capability)


def build_app(session_factory: Any, verifier: FixtureTokenVerifier, settings: Settings) -> FastAPI:
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(settings):
        app.include_router(router)
    app.state.session_factory = session_factory
    app.state.token_verifier = verifier
    return app


class _Speaker:
    def __init__(
        self,
        professional_id: uuid.UUID,
        login_id: uuid.UUID,
        login_email: str,
        headers: dict[str, str],
    ) -> None:
        self.professional_id = professional_id
        self.login_id = login_id
        self.login_email = login_email
        self.headers = headers


class _Ctx:
    def __init__(self, engine: Engine, settings: Settings | None = None) -> None:
        self.engine = engine
        self.tenant_id = uuid.uuid4()
        self.unit_id = uuid.uuid4()
        self.second_unit_id = uuid.uuid4()
        self.verifier = FixtureTokenVerifier()
        self.session_factory = create_session_factory(
            engine.url.render_as_string(hide_password=False)
        )
        self.client = TestClient(
            build_app(self.session_factory, self.verifier, settings or _PortalOn())
        )
        self.execute(
            "INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)",
            id=self.tenant_id,
            slug=f"test-mychan-{self.tenant_id.hex[:12]}",
        )
        for unit_id, path in (
            (self.unit_id, UNIT_PATH),
            (self.second_unit_id, SECOND_UNIT_PATH),
        ):
            self.execute(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :t, CAST(:p AS ltree), 'department', :p)",
                id=unit_id,
                t=self.tenant_id,
                p=path,
            )

    # -- SQL ---------------------------------------------------------------

    def execute(self, sql: str, **params: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)

    def scalar(self, sql: str, **params: Any) -> Any:
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params).scalar_one_or_none()

    def rows(self, sql: str, **params: Any) -> list[Any]:
        with self.engine.begin() as conn:
            return list(conn.execute(text(sql), params).all())

    # -- people ------------------------------------------------------------

    def account(self, email: str | None = None) -> tuple[uuid.UUID, str, str]:
        user_id = uuid.uuid4()
        subject = f"sub-mychan-{user_id.hex}"
        address = email or f"login-{user_id.hex[:8]}@synthetic.invalid"
        self.execute(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :t, :s, :e)",
            id=user_id,
            t=self.tenant_id,
            s=subject,
            e=address,
        )
        return user_id, subject, address

    def headers_for(self, subject: str) -> dict[str, str]:
        bearer = f"tok-mychan-{uuid.uuid4().hex}"
        self.verifier.register(bearer, subject)
        return {"Authorization": f"Bearer {bearer}"}

    def grant(
        self,
        user_id: uuid.UUID,
        role: str,
        *,
        path: str = UNIT_PATH,
        valid_until: datetime | None = None,
    ) -> None:
        self.execute(
            "INSERT INTO membership (id, tenant_id, user_id, granted_path, role, valid_until) "
            "VALUES (:id, :t, :u, CAST(:p AS ltree), :r, :until)",
            id=uuid.uuid4(),
            t=self.tenant_id,
            u=user_id,
            p=path,
            r=role,
            until=valid_until,
        )

    def user(self, role: str | None) -> dict[str, str]:
        user_id, subject, _ = self.account()
        if role is not None:
            self.grant(user_id, role)
        return self.headers_for(subject)

    def profile(self, *, unit_id: uuid.UUID | None = None) -> uuid.UUID:
        professional_id, _, _ = self.account()
        self.execute(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, full_name) "
            "VALUES (:t, :p, :u, 'Dana Reyes')",
            t=self.tenant_id,
            p=professional_id,
            u=unit_id or self.unit_id,
        )
        return professional_id

    def speaker(
        self,
        *,
        login_email: str | None = None,
        role: str | None = "speaker",
        valid_until: datetime | None = None,
    ) -> _Speaker:
        """A roster profile bound to a separate login holding ``role`` at the unit."""
        professional_id = self.profile()
        login_id, subject, address = self.account(login_email)
        self.execute(
            "UPDATE speaker_profile SET account_user_id = :l, account_bound_at = now() "
            "WHERE tenant_id = :t AND professional_id = :p",
            l=login_id,
            t=self.tenant_id,
            p=professional_id,
        )
        if role is not None:
            self.grant(login_id, role, valid_until=valid_until)
        return _Speaker(professional_id, login_id, address, self.headers_for(subject))

    def channel(
        self,
        professional_id: uuid.UUID,
        *,
        address: str | None = None,
        state: str = "active_candidate",
        unit_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        channel_id = uuid.uuid4()
        consented = state in {"consented", "active_candidate"}
        self.execute(
            "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
            "channel_kind, address, contact_state, consent_source, consent_recorded_at, "
            "consent_evidence) VALUES (:id, :t, :u, :p, 'email', :a, :s, :src, :at, :ev)",
            id=channel_id,
            t=self.tenant_id,
            u=unit_id or self.unit_id,
            p=professional_id,
            a=address or f"chan-{channel_id.hex[:8]}@synthetic.invalid",
            s=state,
            src="in_person" if consented else None,
            at=datetime.now(UTC) - timedelta(days=30) if consented else None,
            ev="signed consent form" if consented else None,
        )
        return channel_id

    def suppress(self, address: str, source: str) -> None:
        self.execute(
            "INSERT INTO suppression_record (id, tenant_id, address, suppressed_at, source) "
            "VALUES (:i, :t, :a, now() - interval '1 day', :s)",
            i=uuid.uuid4(),
            t=self.tenant_id,
            a=address,
            s=source,
        )

    def address(self, channel_id: uuid.UUID) -> str:
        return str(self.scalar("SELECT address FROM contact_channel WHERE id = :c", c=channel_id))

    def suppression(self, address: str) -> Any:
        found = self.rows(
            "SELECT source, lifted_at, lifted_by_user_id FROM suppression_record "
            "WHERE tenant_id = :t AND address = :a",
            t=self.tenant_id,
            a=address,
        )
        return found[0] if found else None

    def choices(self, channel_id: uuid.UUID) -> list[Any]:
        return self.rows(
            "SELECT sequence, choice, actor_user_id, professional_id, lifted_source "
            "FROM contact_channel_speaker_choice WHERE contact_channel_id = :c ORDER BY sequence",
            c=channel_id,
        )

    def transitions(self, channel_id: uuid.UUID) -> list[Any]:
        return self.rows(
            "SELECT from_state, to_state, consent_source, consent_evidence, actor_user_id "
            "FROM contact_channel_transition WHERE contact_channel_id = :c "
            "ORDER BY occurred_at, recorded_at, id",
            c=channel_id,
        )

    def state(self, channel_id: uuid.UUID) -> Any:
        return self.rows(
            "SELECT contact_state, consent_source, consent_evidence FROM contact_channel "
            "WHERE id = :c",
            c=channel_id,
        )[0]

    # -- routes ------------------------------------------------------------

    def list(self, speaker: _Speaker) -> Any:
        return self.client.get(LIST, headers=speaker.headers)

    def opt_in(self, headers: dict[str, str], channel_id: uuid.UUID) -> Any:
        return self.client.post(f"{LIST}/{channel_id}/opt-in", headers=headers)

    def opt_out(self, headers: dict[str, str], channel_id: uuid.UUID) -> Any:
        return self.client.post(f"{LIST}/{channel_id}/opt-out", headers=headers)

    def drop(self) -> None:
        with self.engine.begin() as conn:
            for table in _CLEANUP:
                conn.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": self.tenant_id}
                )
            conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": self.tenant_id})


@pytest.fixture(scope="module")
def engine() -> Engine:
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM contact_channel_speaker_choice LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def ctx(engine: Engine) -> Iterator[_Ctx]:
    context = _Ctx(engine)
    yield context
    context.drop()


def _code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def _by_id(response: Any) -> dict[str, Any]:
    return {c["contact_channel_id"]: c for c in response.json()["channels"]}


# ---------------------------------------------------------------------------
# 1. Scope
# ---------------------------------------------------------------------------


def test_lists_only_own_channels_across_units(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    mine = ctx.channel(speaker.professional_id)
    mine_elsewhere = ctx.channel(speaker.professional_id, unit_id=ctx.second_unit_id)
    other = ctx.speaker()
    ctx.channel(other.professional_id)
    ctx.channel(ctx.profile())

    response = ctx.list(speaker)

    assert response.status_code == 200, response.text
    assert set(_by_id(response)) == {str(mine), str(mine_elsewhere)}
    assert response.json()["truncated"] is False


def test_response_never_carries_evidence_actor_or_unit(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    ctx.opt_out(speaker.headers, channel)

    listed = ctx.list(speaker).json()
    assert set(listed) == {"channels", "truncated"}
    for view in listed["channels"]:
        assert set(view) == VIEW_KEYS
    result = ctx.opt_in(speaker.headers, channel).json()
    assert set(result) == {"channel", "changed"}
    assert set(result["channel"]) == VIEW_KEYS


def test_view_reports_the_live_suppression(ctx: _Ctx) -> None:
    """C11: the Speaker's view honours ``lifted_at`` like every other read."""
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, address=speaker.login_email)
    view = _by_id(ctx.list(speaker))[str(channel)]
    assert (view["send_eligible"], view["suppression_reason"]) == (True, None)

    ctx.suppress(speaker.login_email, "unsubscribe_link")
    view = _by_id(ctx.list(speaker))[str(channel)]
    assert (view["send_eligible"], view["suppressed"], view["suppression_reason"]) == (
        False,
        True,
        "unsubscribed",
    )

    ctx.execute(
        "UPDATE suppression_record SET lifted_at = now(), lifted_by_user_id = :u "
        "WHERE tenant_id = :t",
        u=speaker.login_id,
        t=ctx.tenant_id,
    )
    view = _by_id(ctx.list(speaker))[str(channel)]
    assert (view["send_eligible"], view["suppressed"], view["suppression_reason"]) == (
        True,
        False,
        None,
    )


# ---------------------------------------------------------------------------
# 2. Opt-out
# ---------------------------------------------------------------------------


def test_opt_out_writes_speaker_portal_suppression_and_choice(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)

    response = ctx.opt_out(speaker.headers, channel)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True
    assert body["channel"]["suppression_reason"] == "your_opt_out"
    assert body["channel"]["speaker_choice"] == "opt_out"
    assert body["channel"]["last_set_by"] == "speaker"
    assert body["channel"]["contact_state"] == "active_candidate"
    stored = ctx.suppression(ctx.address(channel))
    assert (stored.source, stored.lifted_at) == ("speaker_portal", None)
    [choice] = ctx.choices(channel)
    assert (choice.choice, choice.actor_user_id, choice.professional_id) == (
        "opt_out",
        speaker.login_id,
        speaker.professional_id,
    )


def test_opt_out_is_immediate(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    assert _by_id(ctx.list(speaker))[str(channel)]["send_eligible"] is True

    ctx.opt_out(speaker.headers, channel)

    assert _by_id(ctx.list(speaker))[str(channel)]["send_eligible"] is False
    # The send path reads the same predicate.
    from smartmatch_persistence.outreach import OutreachRepository

    with ctx.session_factory() as session:
        facts = OutreachRepository().load_recipient(
            session, tenant_id=ctx.tenant_id, contact_channel_id=channel
        )
    assert facts is not None and facts.suppressed is True


def test_opt_out_is_idempotent(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    ctx.opt_out(speaker.headers, channel)

    again = ctx.opt_out(speaker.headers, channel)

    assert again.status_code == 200, again.text
    assert again.json()["changed"] is False
    assert again.json()["channel"]["can_opt_out"] is False
    assert len(ctx.choices(channel)) == 1


def test_opt_out_over_a_bounce_keeps_bounce_and_logs_the_choice(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    ctx.suppress(ctx.address(channel), "bounce")

    response = ctx.opt_out(speaker.headers, channel)

    assert response.status_code == 200, response.text
    assert response.json()["changed"] is True
    assert ctx.suppression(ctx.address(channel)).source == "bounce"
    assert [c.choice for c in ctx.choices(channel)] == ["opt_out"]


# ---------------------------------------------------------------------------
# 3. Opt-in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "moves"),
    [("relationship_recorded", 2), ("consented", 1), ("active_candidate", 0)],
)
def test_opt_in_from(ctx: _Ctx, start: str, moves: int) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, state=start)
    before = len(ctx.transitions(channel))

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True
    assert body["channel"]["contact_state"] == "active_candidate"
    assert body["channel"]["send_eligible"] is True
    assert body["channel"]["speaker_choice"] == "opt_in"
    new = ctx.transitions(channel)[before:]
    assert len(new) == moves
    for entry in new:
        assert entry.consent_source == "self_service"
        assert entry.consent_evidence == SELF_SERVICE_EVIDENCE
        assert entry.actor_user_id == speaker.login_id
    if moves:
        stored = ctx.state(channel)
        assert (stored.consent_source, stored.consent_evidence) == (
            "self_service",
            SELF_SERVICE_EVIDENCE,
        )
    assert [c.choice for c in ctx.choices(channel)] == ["opt_in"]


@pytest.mark.parametrize("source", ["speaker_portal", "unsubscribe_link", "one_click"])
def test_opt_in_lifts_on_the_login_address(ctx: _Ctx, source: str) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, address=speaker.login_email)
    ctx.suppress(speaker.login_email, source)

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 200, response.text
    assert response.json()["channel"]["send_eligible"] is True
    stored = ctx.suppression(speaker.login_email)
    assert stored.lifted_at is not None
    assert stored.lifted_by_user_id == speaker.login_id
    [choice] = ctx.choices(channel)
    assert choice.lifted_source == source


def test_opt_in_lifts_speaker_portal_on_another_address(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    ctx.opt_out(speaker.headers, channel)

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 200, response.text
    assert response.json()["channel"]["send_eligible"] is True
    assert [c.choice for c in ctx.choices(channel)] == ["opt_out", "opt_in"]


@pytest.mark.parametrize("source", ["unsubscribe_link", "one_click"])
def test_opt_in_refuses_unsubscribe_on_another_address(ctx: _Ctx, source: str) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, state="consented")
    ctx.suppress(ctx.address(channel), source)

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 409, response.text
    assert _code(response) == "speaker_contact_channel_address_unverified"
    assert "Speaker Connector" in response.json()["error"]["message"]
    assert ctx.suppression(ctx.address(channel)).lifted_at is None
    assert ctx.choices(channel) == []
    assert ctx.state(channel).contact_state == "consented"


def test_login_address_match_ignores_case_and_surrounding_space(ctx: _Ctx) -> None:
    speaker = ctx.speaker(login_email=f"Dana.Reyes-{uuid.uuid4().hex[:6]}@Synthetic.Invalid")
    address = f"  {speaker.login_email.lower()} "
    channel = ctx.channel(speaker.professional_id, address=address)
    ctx.suppress(address, "unsubscribe_link")

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 200, response.text
    assert ctx.suppression(address).lifted_at is not None


def test_view_can_opt_in_is_false_for_an_unverified_unsubscribe(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    ctx.suppress(ctx.address(channel), "unsubscribe_link")

    view = _by_id(ctx.list(speaker))[str(channel)]

    assert (view["can_opt_in"], view["can_opt_out"]) == (False, True)


@pytest.mark.parametrize(
    ("source", "reason"),
    [("bounce", "delivery"), ("complaint", "delivery"), ("coordinator", "connector")],
)
def test_opt_in_refuses_non_liftable(ctx: _Ctx, source: str, reason: str) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(
        speaker.professional_id, address=speaker.login_email, state="relationship_recorded"
    )
    ctx.suppress(speaker.login_email, source)
    before = len(ctx.transitions(channel))

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 409, response.text
    assert _code(response) == "speaker_contact_channel_suppression_not_liftable"
    assert response.json()["error"]["details"] == {"reason": reason}
    assert ctx.suppression(speaker.login_email).lifted_at is None
    assert len(ctx.transitions(channel)) == before
    assert ctx.choices(channel) == []


@pytest.mark.parametrize("state", ["discovered", "corroborated", "reviewed", "rejected", "stale"])
def test_opt_in_unavailable(ctx: _Ctx, state: str) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, state=state)

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 409, response.text
    assert _code(response) == "speaker_contact_channel_opt_in_unavailable"
    assert response.json()["error"]["details"] == {"contact_state": state}
    assert ctx.choices(channel) == []


def test_opt_in_asks_suppression_before_legality(ctx: _Ctx) -> None:
    """Both refusals apply: the suppression one answers, as ``assert_transition`` orders it."""
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, address=speaker.login_email, state="discovered")
    ctx.suppress(speaker.login_email, "bounce")

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 409, response.text
    assert _code(response) == "speaker_contact_channel_suppression_not_liftable"
    assert ctx.choices(channel) == []


def test_opt_in_unavailable_leaves_a_liftable_suppression_in_place(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, state="discovered")
    ctx.suppress(ctx.address(channel), "speaker_portal")
    before = len(ctx.transitions(channel))

    response = ctx.opt_in(speaker.headers, channel)

    assert response.status_code == 409, response.text
    assert _code(response) == "speaker_contact_channel_opt_in_unavailable"
    assert ctx.suppression(ctx.address(channel)).lifted_at is None
    assert len(ctx.transitions(channel)) == before
    assert ctx.choices(channel) == []


def test_opt_in_is_idempotent(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    assert ctx.opt_in(speaker.headers, channel).json()["changed"] is True

    again = ctx.opt_in(speaker.headers, channel)

    assert again.status_code == 200, again.text
    assert again.json()["changed"] is False
    assert again.json()["channel"]["can_opt_in"] is False
    assert len(ctx.choices(channel)) == 1


# ---------------------------------------------------------------------------
# 4. Refusals
# ---------------------------------------------------------------------------


def test_not_mine_is_404(ctx: _Ctx, engine: Engine) -> None:
    speaker = ctx.speaker()
    other = ctx.speaker()
    theirs = ctx.channel(other.professional_id)
    stranger = _Ctx(engine)
    try:
        foreign = stranger.channel(stranger.profile())
        bodies = []
        for channel in (theirs, uuid.uuid4(), foreign):
            for call in (ctx.opt_in, ctx.opt_out):
                response = call(speaker.headers, channel)
                assert response.status_code == 404, response.text
                bodies.append(response.content)
        assert len(set(bodies)) == 1
        assert _code(response) == "speaker_contact_channel_not_found"
        assert ctx.choices(theirs) == []
    finally:
        stranger.drop()


@pytest.mark.parametrize("role", ["volunteer", "coordinator", "admin", "student"])
def test_unlinked_caller_is_404_on_every_route(ctx: _Ctx, role: str) -> None:
    headers = ctx.user(role)
    channel = uuid.uuid4()
    for response in (
        ctx.client.get(LIST, headers=headers),
        ctx.opt_in(headers, channel),
        ctx.opt_out(headers, channel),
    ):
        assert response.status_code == 404, response.text
        assert _code(response) == "speaker_profile_not_linked"


def test_bound_without_active_speaker_membership_is_403(ctx: _Ctx) -> None:
    expired = ctx.speaker(valid_until=datetime(2020, 1, 1, tzinfo=UTC))
    suspended = ctx.speaker()
    ctx.execute("UPDATE user_account SET suspended = true WHERE id = :u", u=suspended.login_id)
    for speaker, reason in ((expired, "no_grant"), (suspended, "principal_suspended")):
        channel = ctx.channel(speaker.professional_id)
        for response in (
            ctx.list(speaker),
            ctx.opt_in(speaker.headers, channel),
            ctx.opt_out(speaker.headers, channel),
        ):
            assert response.status_code == 403, response.text
            assert response.json()["error"]["details"] == {"reason": reason}


def test_unbind_between_authorize_and_share_lock_is_404(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7 race 8: the share lock re-checks the binding the authorizer read."""
    from smartmatch_api.routers import me_contact_channels

    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    real = me_contact_channels._authorize_speaker_self

    def authorize_then_unbind(session: Any, principal: Any) -> Any:
        bound = real(session, principal)
        ctx.execute(
            "UPDATE speaker_profile SET account_user_id = NULL, account_bound_at = NULL "
            "WHERE tenant_id = :t AND professional_id = :p",
            t=ctx.tenant_id,
            p=speaker.professional_id,
        )
        return bound

    monkeypatch.setattr(me_contact_channels, "_authorize_speaker_self", authorize_then_unbind)

    response = ctx.opt_out(speaker.headers, channel)

    assert response.status_code == 404, response.text
    assert _code(response) == "speaker_profile_not_linked"
    assert ctx.choices(channel) == []
    assert ctx.suppression(ctx.address(channel)) is None


def _quota(ctx: _Ctx, operation: str) -> int:
    return int(
        ctx.scalar(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE tenant_id = :t AND operation = :op",
            t=ctx.tenant_id,
            op=operation,
        )
    )


def test_quota_is_charged_before_the_404(ctx: _Ctx) -> None:
    headers = ctx.user("volunteer")
    assert ctx.client.get(LIST, headers=headers).status_code == 404
    assert _quota(ctx, "me.contact_channels.read") == 1
    assert ctx.opt_out(headers, uuid.uuid4()).status_code == 404
    assert _quota(ctx, "me.contact_channels.write") == 1


def test_write_rate_limit_is_429_after_10(ctx: _Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    from smartmatch_api.routers import me_contact_channels
    from smartmatch_persistence.rate_limit import RateLimit

    shipped = me_contact_channels.ME_CONTACT_CHANNELS_WRITE_RATE_LIMIT
    assert (shipped.max_requests, shipped.window) == (10, timedelta(minutes=1))
    # A one-day window, so 11 requests cannot straddle a minute boundary.
    monkeypatch.setattr(
        me_contact_channels,
        "ME_CONTACT_CHANNELS_WRITE_RATE_LIMIT",
        RateLimit(operation=shipped.operation, max_requests=10, window=timedelta(days=1)),
    )
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    codes = [ctx.opt_out(speaker.headers, channel).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429


# ---------------------------------------------------------------------------
# 5. Gate
# ---------------------------------------------------------------------------


def test_capability_off_mounts_nothing(engine: Engine) -> None:
    off = _Ctx(engine, settings=Settings())
    try:
        speaker = off.speaker()
        channel = off.channel(speaker.professional_id)
        assert off.list(speaker).status_code == 404
        assert off.opt_out(speaker.headers, channel).status_code == 404
        assert off.opt_in(speaker.headers, channel).status_code == 404
        assert off.choices(channel) == []
    finally:
        off.drop()


# ---------------------------------------------------------------------------
# 6. View fields
# ---------------------------------------------------------------------------


def test_last_set_by_is_connector_after_a_later_connector_move(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id)
    ctx.opt_out(speaker.headers, channel)
    assert _by_id(ctx.list(speaker))[str(channel)]["last_set_by"] == "speaker"

    coordinator, _, _ = ctx.account()
    ctx.execute(
        "INSERT INTO contact_channel_transition (id, tenant_id, contact_channel_id, "
        "from_state, to_state, consent_source, actor_user_id, occurred_at) "
        "VALUES (:i, :t, :c, 'active_candidate', 'stale', 'in_person', :u, "
        "now() + interval '1 minute')",
        i=uuid.uuid4(),
        t=ctx.tenant_id,
        c=channel,
        u=coordinator,
    )

    assert _by_id(ctx.list(speaker))[str(channel)]["last_set_by"] == "connector"


def test_list_is_capped_at_50_and_says_so(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    for _ in range(51):
        ctx.channel(speaker.professional_id)

    body = ctx.list(speaker).json()

    assert body["truncated"] is True
    assert len(body["channels"]) == 50


def test_can_opt_in_on_a_fresh_consented_channel(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    channel = ctx.channel(speaker.professional_id, state="consented")

    view = _by_id(ctx.list(speaker))[str(channel)]

    assert (view["can_opt_in"], view["can_opt_out"], view["last_set_by"]) == (
        True,
        True,
        "connector",
    )
