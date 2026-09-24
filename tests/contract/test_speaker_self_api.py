"""HTTP contracts for the signed-in Speaker's own routes (B26 T6b-2 plan §7.3).

``SPEAKER_PORTAL`` is off in every scope, so this file builds its application
from ``routers_for`` with that one capability switched on, the way
``test_speaker_portal_composition.py`` proves the mount.

``tests/authz/test_policy_matrix.py`` owns the role rectangle. What only exists
over HTTP, and is asserted here:

* **The subject is the bound profile.** The login is looked up, never a request
  field; an unbound login is ``404 speaker_profile_not_linked`` whatever its
  role, and every row returned is keyed by the profile's ``professional_id``.
* **Own rows only.** Another Speaker's invitation is the same 404, byte for
  byte, as an unknown id.
* **An answer records ``speaker_portal`` and the login**, and a first answer
  stands (OQ-CBA-044).
* **Availability is T3's statement**, written with source ``speaker``.

Speakers are bound by SQL (``account_user_id``, ``account_bound_at``, a
``speaker`` membership at the profile unit's path), except in the one test that
activates through T6b-1's route. Token- and password-shaped values are built at
runtime (forbidden-behaviour scanner, gitleaks).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.config import Settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.main import routers_for
from smartmatch_api.routers import speaker_portal as portal_router
from smartmatch_api.routers import speaker_self
from smartmatch_domain.product_scope import Capability
from smartmatch_domain.speaker_portal import derive_token
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.selfsvc"
SIBLING_UNIT_PATH = "iawest.selfsvcsibling"
EVENT_DATE_TEXT = "Thursday 12 March 2027"
#: The Speaker Request's own date, the one EVENT_DATE_TEXT spells (B26 T4).
EVENT_DATE = date(2027, 3, 12)
#: 03:00 UTC: still 1 November in Los Angeles, already 2 November in UTC.
FROZEN_NOW = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
TODAY = FROZEN_NOW.date()

ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/v1/me/availability"),
    ("PATCH", "/v1/me/availability"),
    ("GET", "/v1/me/invitations"),
    ("POST", "/v1/me/invitations/{invitation_id}/response"),
    ("GET", "/v1/me/engagements"),
)

_CLEANUP = (
    "pipeline_record",
    "attendance_record",
    "pilot_session",
    "pilot_credential",
    "speaker_portal_invitation",
    "cba_invitation",
    "cba_invitation_batch",
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
    "speaker_availability_window",
    "speaker_availability",
    "speaker_profile",
    "event",
    "membership",
    "user_account",
    "org_unit",
    "rate_limit_counter",
)


class _PortalOn(Settings):
    """Default settings with ``SPEAKER_PORTAL`` switched on."""

    def capability_enabled(self, capability: Capability) -> bool:  # type: ignore[override]
        return capability is Capability.SPEAKER_PORTAL or super().capability_enabled(capability)


def build_app(
    session_factory: Any, verifier: FixtureTokenVerifier, secret: str, settings: Settings
) -> FastAPI:
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(settings):
        app.include_router(router)
    app.state.session_factory = session_factory
    app.state.token_verifier = verifier
    app.state.speaker_portal_token_secret = secret
    return app


def _bearer() -> str:
    return f"tok-self-{uuid.uuid4().hex}"


def _new_pw() -> str:
    return "pw-" + uuid.uuid4().hex


class _Speaker:
    def __init__(self, professional_id: uuid.UUID, login_id: uuid.UUID, headers: dict[str, str]):
        self.professional_id = professional_id
        self.login_id = login_id
        self.headers = headers


class _Ctx:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.tenant_id = uuid.uuid4()
        self.unit_id = uuid.uuid4()
        self.sibling_unit_id = uuid.uuid4()
        self.verifier = FixtureTokenVerifier()
        self.secret = secrets.token_urlsafe(40)
        self.session_factory = create_session_factory(
            engine.url.render_as_string(hide_password=False)
        )
        self.client = TestClient(
            build_app(self.session_factory, self.verifier, self.secret, _PortalOn())
        )
        self.execute(
            "INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)",
            id=self.tenant_id,
            slug=f"test-self-{self.tenant_id.hex[:12]}",
        )
        for unit_id, path in ((self.unit_id, UNIT_PATH), (self.sibling_unit_id, SIBLING_UNIT_PATH)):
            self.execute(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :t, CAST(:p AS ltree), 'department', :p)",
                id=unit_id,
                t=self.tenant_id,
                p=path,
            )
        self.coordinator_id, self.coordinator = self.user("coordinator", path="iawest")

    # -- SQL ---------------------------------------------------------------

    def execute(self, sql: str, **params: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)

    def scalar(self, sql: str, **params: Any) -> Any:
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params).scalar_one_or_none()

    def row(self, sql: str, **params: Any) -> Any:
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params).one()

    # -- people ------------------------------------------------------------

    def account(self) -> tuple[uuid.UUID, str]:
        user_id = uuid.uuid4()
        subject = f"sub-self-{user_id.hex}"
        self.execute(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :t, :s, :e)",
            id=user_id,
            t=self.tenant_id,
            s=subject,
            e=f"{user_id.hex[:8]}@placeholder.invalid",
        )
        return user_id, subject

    def headers_for(self, subject: str) -> dict[str, str]:
        bearer = _bearer()
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

    def user(self, role: str | None, *, path: str = UNIT_PATH) -> tuple[uuid.UUID, dict[str, str]]:
        user_id, subject = self.account()
        if role is not None:
            self.grant(user_id, role, path=path)
        return user_id, self.headers_for(subject)

    def contact(self, name: str) -> tuple[uuid.UUID, uuid.UUID]:
        """A roster contact with a consented email: ``(professional_id, channel_id)``."""
        professional_id, _ = self.account()
        channel_id = uuid.uuid4()
        self.execute(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, full_name) "
            "VALUES (:t, :p, :u, :n)",
            t=self.tenant_id,
            p=professional_id,
            u=self.unit_id,
            n=name,
        )
        self.execute(
            "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
            "channel_kind, address, contact_state, consent_source, consent_recorded_at) "
            "VALUES (:id, :t, :u, :p, 'email', :a, 'active_candidate', 'self_service', now())",
            id=channel_id,
            t=self.tenant_id,
            u=self.unit_id,
            p=professional_id,
            a=self.address_of(professional_id),
        )
        return professional_id, channel_id

    def address_of(self, professional_id: uuid.UUID) -> str:
        return f"speaker-{professional_id.hex[:8]}@synthetic.invalid"

    def bind(self, professional_id: uuid.UUID, login_id: uuid.UUID) -> None:
        self.execute(
            "UPDATE speaker_profile SET account_user_id = :l, account_bound_at = now() "
            "WHERE tenant_id = :t AND professional_id = :p",
            l=login_id,
            t=self.tenant_id,
            p=professional_id,
        )

    def speaker(
        self,
        name: str = "Dana Reyes",
        *,
        role: str | None = "speaker",
        merged_login: bool = False,
        valid_until: datetime | None = None,
    ) -> _Speaker:
        """A roster contact bound to a login holding ``role`` at the unit.

        ``merged_login``: the login is a separate account (T6b-5's shape), so
        the login id differs from ``professional_id``.
        """
        professional_id, _ = self.contact(name)
        if merged_login:
            login_id, subject = self.account()
        else:
            login_id = professional_id
            subject = f"sub-self-{professional_id.hex}"
        self.bind(professional_id, login_id)
        if role is not None:
            self.grant(login_id, role, valid_until=valid_until)
        return _Speaker(professional_id, login_id, self.headers_for(subject))

    # -- Connector side ----------------------------------------------------

    def speaker_request(self) -> uuid.UUID:
        """The unit's Speaker Request a batch invites for (B26 T4 requires one).

        A Connector-entered, date-only event on the date the invitation spells.
        """
        request_id = getattr(self, "_speaker_request_id", None)
        if request_id is None:
            request_id = uuid.uuid4()
            title = f"Accounting Society Spring Mixer {request_id.hex[:8]}"
            self.execute(
                "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
                "on_date, time_zone, time_precision, resolved_date, origin) VALUES (:id, :t, "
                ":u, :title, :norm, :d, 'America/Los_Angeles', 'date_only', :d, "
                "'coordinator_entry')",
                id=request_id,
                t=self.tenant_id,
                u=self.unit_id,
                title=title,
                norm=title.lower(),
                d=EVENT_DATE,
            )
            self._speaker_request_id = request_id
        return request_id

    def invite(self, *professional_ids: uuid.UUID) -> dict[uuid.UUID, str]:
        """Compose and dispatch one batch over HTTP; ``{professional_id: invitation_id}``."""
        created = self.client.post(
            f"/v1/units/{self.unit_id}/speaker-invitations/batches",
            json={
                "speaker_request_id": str(self.speaker_request()),
                "professional_ids": [str(pid) for pid in professional_ids],
                "event_name": "Accounting Society Spring Mixer",
                "event_date": EVENT_DATE_TEXT,
                "coordinator_name": "Dana Okafor",
            },
            headers={**self.coordinator, "Idempotency-Key": f"key-{uuid.uuid4().hex}"},
        )
        assert created.status_code == 201, created.text
        batch = created.json()
        dispatched = self.client.post(
            f"/v1/units/{self.unit_id}/speaker-invitations/batches/{batch['batch_id']}/dispatch",
            headers=self.coordinator,
        )
        assert dispatched.status_code == 202, dispatched.text
        return {
            uuid.UUID(entry["professional_id"]): str(entry["invitation_id"])
            for entry in batch["invitations"]
        }

    def pending_invitation(self, professional_id: uuid.UUID) -> str:
        created = self.client.post(
            f"/v1/units/{self.unit_id}/speaker-invitations/batches",
            json={
                "speaker_request_id": str(self.speaker_request()),
                "professional_ids": [str(professional_id)],
                "event_name": "Composed, never sent",
                "event_date": EVENT_DATE_TEXT,
                "coordinator_name": "Dana Okafor",
            },
            headers={**self.coordinator, "Idempotency-Key": f"key-{uuid.uuid4().hex}"},
        )
        assert created.status_code == 201, created.text
        return str(created.json()["invitations"][0]["invitation_id"])

    def connector_record(self, invitation_id: str, response: str) -> Any:
        return self.client.post(
            f"/v1/units/{self.unit_id}/speaker-invitations/{invitation_id}/response",
            json={"response": response},
            headers=self.coordinator,
        )

    def stored(self, invitation_id: str) -> Any:
        return self.row(
            "SELECT status, response_status, response_channel, response_recorded_at, "
            "response_recorded_by_user_id FROM cba_invitation WHERE id = :i",
            i=invitation_id,
        )

    def connector_availability(self, professional_id: uuid.UUID, method: str = "GET", **kw: Any):
        return self.client.request(
            method,
            f"/v1/units/{self.unit_id}/speaker-contacts/{professional_id}/availability",
            headers=self.coordinator,
            **kw,
        )

    # -- journeys ----------------------------------------------------------

    def event(self, on: date | None, *, title: str | None = None) -> uuid.UUID:
        event_id = uuid.uuid4()
        title = title or f"Guest lecture {event_id.hex[:8]}"
        self.execute(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "on_date, time_zone, time_precision, resolved_date, origin) VALUES (:id, :t, :u, "
            ":title, :norm, :on, CASE WHEN CAST(:on AS date) IS NULL THEN NULL "
            "ELSE 'America/Los_Angeles' END, :prec, :on, 'coordinator_entry')",
            id=event_id,
            t=self.tenant_id,
            u=self.unit_id,
            title=title,
            norm=title.lower(),
            on=on,
            prec="unresolved" if on is None else "date_only",
        )
        return event_id

    def journey(
        self,
        professional_id: uuid.UUID,
        event_id: uuid.UUID,
        *,
        confirmed: bool = True,
        cancelled: bool = False,
        attended: bool = False,
    ) -> uuid.UUID:
        record_id = uuid.uuid4()
        start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        attendance_id = None
        if attended:
            attendance_id = uuid.uuid4()
            self.execute(
                "INSERT INTO attendance_record (id, tenant_id, owning_unit_id, subject_id, "
                "event_id, method) VALUES (:id, :t, :u, :s, :e, 'coordinator_entry')",
                id=attendance_id,
                t=self.tenant_id,
                u=self.unit_id,
                s=professional_id,
                e=event_id,
            )
        self.execute(
            "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
            "opportunity_event_id, matched_at, matched_provenance, contacted_at, confirmed_at, "
            "attended_at, attended_attendance_id, cancelled_at, cancelled_by_user_id) "
            "VALUES (:id, :t, :u, :s, :e, :m, 'synthetic / coordinator-accepted', :c, :conf, "
            ":att, :att_id, :canc, :canc_by)",
            id=record_id,
            t=self.tenant_id,
            u=self.unit_id,
            s=professional_id,
            e=event_id,
            m=start,
            c=start + timedelta(hours=1),
            conf=start + timedelta(hours=2) if confirmed else None,
            att=start + timedelta(hours=3) if attended else None,
            att_id=attendance_id,
            canc=start + timedelta(hours=4) if cancelled else None,
            canc_by=self.coordinator_id if cancelled else None,
        )
        return record_id

    # -- the Speaker's routes ---------------------------------------------

    def call(self, method: str, path: str, headers: dict[str, str], **kw: Any):
        return self.client.request(method, path, headers=headers, **kw)

    def answer(self, speaker: _Speaker, invitation_id: str, response: str):
        return self.client.post(
            f"/v1/me/invitations/{invitation_id}/response",
            json={"response": response},
            headers=speaker.headers,
        )

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
            conn.execute(text("SELECT 1 FROM speaker_portal_invitation LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def ctx(engine: Engine) -> Iterator[_Ctx]:
    context = _Ctx(engine)
    yield context
    context.drop()


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr("smartmatch_api.routers.speaker_self.utc_now", lambda: FROZEN_NOW)
    return FROZEN_NOW


def _request_for(method: str, path: str) -> tuple[str, dict[str, Any]]:
    kwargs: dict[str, Any] = {}
    if method == "PATCH":
        kwargs["json"] = {
            "expected_version": None,
            "invitations_paused_until": None,
            "declared_capacity_hours_per_90_days": None,
            "unavailable": [],
        }
    if method == "POST":
        kwargs["json"] = {"response": "accept"}
    return path.format(invitation_id=uuid.uuid4()), kwargs


def _code(response: Any) -> str:
    return response.json()["error"]["code"]


def _quota(ctx: _Ctx, operation: str) -> int:
    return int(
        ctx.scalar(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE tenant_id = :t AND operation = :op",
            t=ctx.tenant_id,
            op=operation,
        )
    )


# ---------------------------------------------------------------------------
# Subject and roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["volunteer", "coordinator", "student", "admin"])
def test_unlinked_caller_is_404_on_every_route(ctx: _Ctx, role: str) -> None:
    _, headers = ctx.user(role)
    for method, template in ROUTES:
        path, kwargs = _request_for(method, template)
        response = ctx.call(method, path, headers, **kwargs)
        assert response.status_code == 404, (method, template, response.text)
        body = response.json()["error"]
        assert body["code"] == "speaker_profile_not_linked"
        assert "details" not in body


@pytest.mark.parametrize("role", ["volunteer", "coordinator"])
def test_bound_login_without_speaker_membership_is_403(ctx: _Ctx, role: str) -> None:
    speaker = ctx.speaker(role=role)
    for method, template in ROUTES:
        path, kwargs = _request_for(method, template)
        response = ctx.call(method, path, speaker.headers, **kwargs)
        assert response.status_code == 403, (method, template, response.text)
        assert response.json()["error"]["details"] == {"reason": "no_grant"}


def test_expired_speaker_membership_is_403(ctx: _Ctx) -> None:
    speaker = ctx.speaker(valid_until=datetime(2020, 1, 1, tzinfo=UTC))
    response = ctx.call("GET", "/v1/me/availability", speaker.headers)
    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"reason": "no_grant"}


def test_suspended_speaker_is_403_principal_suspended(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    ctx.execute("UPDATE user_account SET suspended = true WHERE id = :u", u=speaker.login_id)
    response = ctx.call("GET", "/v1/me/invitations", speaker.headers)
    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"reason": "principal_suspended"}


def test_unauthenticated_is_401(ctx: _Ctx) -> None:
    for method, template in ROUTES:
        path, kwargs = _request_for(method, template)
        response = ctx.client.request(method, path, **kwargs)
        assert response.status_code == 401, (method, template)


def test_quota_is_charged_before_the_404(ctx: _Ctx) -> None:
    _, headers = ctx.user("volunteer")
    assert _quota(ctx, "speaker_self.read") == 0
    assert ctx.call("GET", "/v1/me/invitations", headers).status_code == 404
    assert _quota(ctx, "speaker_self.read") == 1
    path, kwargs = _request_for("POST", ROUTES[3][1])
    assert ctx.call("POST", path, headers, **kwargs).status_code == 404
    assert _quota(ctx, "speaker_self.write") == 1


def test_merged_login_resolves_to_the_bound_profile(ctx: _Ctx) -> None:
    speaker = ctx.speaker(merged_login=True)
    assert speaker.login_id != speaker.professional_id
    invitations = ctx.invite(speaker.professional_id)
    response = ctx.call("GET", "/v1/me/invitations", speaker.headers)
    assert response.status_code == 200, response.text
    ids = [item["invitation_id"] for item in response.json()["invitations"]]
    assert ids == [invitations[speaker.professional_id]]
    availability = ctx.call("GET", "/v1/me/availability", speaker.headers).json()
    assert availability["professional_id"] == str(speaker.professional_id)


def test_one_activated_speaker_reads_own_availability(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        portal_router, "_activation_caller_key", lambda request: f"test-{ctx.tenant_id.hex}"
    )
    professional_id, channel_id = ctx.contact("Dana Reyes")
    invited = ctx.client.post(
        f"/v1/units/{ctx.unit_id}/speaker-contacts/{professional_id}/portal-invitations",
        json={"contact_channel_id": str(channel_id)},
        headers=ctx.coordinator,
    )
    assert invited.status_code == 202, invited.text
    token = derive_token(ctx.secret, uuid.UUID(invited.json()["invitation_id"]))
    activated = ctx.client.post(
        "/v1/speaker-portal/activate", json={"token": token, "new_password": _new_pw()}
    )
    assert activated.status_code == 200, activated.text
    session = {"Authorization": f"Bearer {activated.json()['access_token']}"}

    response = ctx.call("GET", "/v1/me/availability", session)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["professional_id"] == str(professional_id)
    assert body["stated"] is False


# ---------------------------------------------------------------------------
# Own rows only
# ---------------------------------------------------------------------------


def test_invitations_list_only_own_rows(ctx: _Ctx) -> None:
    a = ctx.speaker("Avery Stone")
    b = ctx.speaker("Blake Moreno")
    unbound, _ = ctx.contact("Casey Unbound")
    first = ctx.invite(a.professional_id, b.professional_id, unbound)
    second = ctx.invite(a.professional_id)

    body = ctx.call("GET", "/v1/me/invitations", a.headers).json()

    ids = {item["invitation_id"] for item in body["invitations"]}
    assert ids == {first[a.professional_id], second[a.professional_id]}
    assert body["truncated"] is False


def test_pending_and_skipped_invitations_are_not_listed(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    ctx.pending_invitation(speaker.professional_id)
    ctx.execute(
        "INSERT INTO suppression_record (id, tenant_id, address, suppressed_at, source) "
        "VALUES (:i, :t, :a, now(), 'unsubscribe_link')",
        i=uuid.uuid4(),
        t=ctx.tenant_id,
        a=ctx.address_of(speaker.professional_id),
    )
    created = ctx.client.post(
        f"/v1/units/{ctx.unit_id}/speaker-invitations/batches",
        json={
            "speaker_request_id": str(ctx.speaker_request()),
            "professional_ids": [str(speaker.professional_id)],
            "event_name": "Skipped",
            "event_date": EVENT_DATE_TEXT,
            "coordinator_name": "Dana Okafor",
        },
        headers={**ctx.coordinator, "Idempotency-Key": f"key-{uuid.uuid4().hex}"},
    )
    assert created.json()["invitations"][0]["status"] == "skipped"

    body = ctx.call("GET", "/v1/me/invitations", speaker.headers).json()

    assert body["invitations"] == []


def test_invitation_json_carries_no_batch_or_other_speaker_field(ctx: _Ctx) -> None:
    a = ctx.speaker("Avery Stone")
    b = ctx.speaker("Blake Moreno")
    invitations = ctx.invite(a.professional_id, b.professional_id)

    response = ctx.call("GET", "/v1/me/invitations", a.headers)

    item = response.json()["invitations"][0]
    assert set(item) == {
        "invitation_id",
        "event",
        "dispatched_at",
        "status",
        "response",
        "answerable",
    }
    assert item["event"] == {
        "title": "Accounting Society Spring Mixer",
        "date_text": EVENT_DATE_TEXT,
        "local_date": None,
        "time_zone": None,
    }
    assert item["status"] == "awaiting_response"
    assert item["answerable"] is True
    raw = response.text
    for leaked in (
        "Blake Moreno",
        ctx.address_of(b.professional_id),
        ctx.address_of(a.professional_id),
        invitations[b.professional_id],
        str(a.professional_id),
        str(ctx.unit_id),
        str(ctx.coordinator_id),
    ):
        assert leaked not in raw


def test_engagements_list_only_own_rows(ctx: _Ctx) -> None:
    a = ctx.speaker("Avery Stone")
    b = ctx.speaker("Blake Moreno")
    mine = ctx.journey(a.professional_id, ctx.event(date(2030, 1, 1)))
    ctx.journey(b.professional_id, ctx.event(date(2030, 1, 2)))

    body = ctx.call("GET", "/v1/me/engagements", a.headers).json()

    assert [item["engagement_id"] for item in body["engagements"]] == [str(mine)]


def test_query_parameters_cannot_select_another_speaker(ctx: _Ctx) -> None:
    a = ctx.speaker("Avery Stone")
    b = ctx.speaker("Blake Moreno")
    invitations = ctx.invite(a.professional_id, b.professional_id)
    ctx.journey(b.professional_id, ctx.event(date(2030, 1, 2)))
    mine = ctx.journey(a.professional_id, ctx.event(date(2030, 1, 1)))
    other = f"?professional_id={b.professional_id}&user_id={b.login_id}"

    listed = ctx.call("GET", f"/v1/me/invitations{other}", a.headers).json()
    engaged = ctx.call("GET", f"/v1/me/engagements{other}", a.headers).json()
    stated = ctx.call("GET", f"/v1/me/availability{other}", a.headers).json()

    assert [i["invitation_id"] for i in listed["invitations"]] == [invitations[a.professional_id]]
    assert [e["engagement_id"] for e in engaged["engagements"]] == [str(mine)]
    assert stated["professional_id"] == str(a.professional_id)


# ---------------------------------------------------------------------------
# Cross-Speaker 404
# ---------------------------------------------------------------------------


def test_answering_another_speakers_invitation_is_404_and_writes_nothing(ctx: _Ctx) -> None:
    a = ctx.speaker("Avery Stone")
    b = ctx.speaker("Blake Moreno")
    invitations = ctx.invite(a.professional_id, b.professional_id)

    response = ctx.answer(a, invitations[b.professional_id], "accept")

    assert response.status_code == 404
    assert _code(response) == "speaker_invitation_not_found"
    assert ctx.stored(invitations[b.professional_id]).response_status == "awaiting_response"


def test_that_404_is_byte_identical_to_an_unknown_id(ctx: _Ctx) -> None:
    a = ctx.speaker("Avery Stone")
    b = ctx.speaker("Blake Moreno")
    invitations = ctx.invite(b.professional_id)

    theirs = ctx.answer(a, invitations[b.professional_id], "accept")
    unknown = ctx.answer(a, str(uuid.uuid4()), "accept")

    assert theirs.status_code == unknown.status_code == 404
    assert theirs.content == unknown.content


def test_own_undispatched_invitation_is_404(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    pending = ctx.pending_invitation(speaker.professional_id)

    response = ctx.answer(speaker, pending, "accept")

    assert response.status_code == 404
    assert _code(response) == "speaker_invitation_not_found"


# ---------------------------------------------------------------------------
# Response rules
# ---------------------------------------------------------------------------


def test_accept_records_the_portal_channel_and_actor(ctx: _Ctx) -> None:
    speaker = ctx.speaker(merged_login=True)
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]

    response = ctx.answer(speaker, invitation_id, "accept")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recorded"] is True
    assert body["invitation"]["status"] == "accepted_invitation"
    assert body["invitation"]["answerable"] is False
    assert body["invitation"]["response"]["recorded_by"] == "speaker"
    stored = ctx.stored(invitation_id)
    assert stored.response_channel == "speaker_portal"
    assert stored.response_recorded_by_user_id == speaker.login_id
    assert stored.response_recorded_by_user_id != speaker.professional_id


def test_repeating_the_same_answer_is_200_and_keeps_the_first_time(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]
    ctx.answer(speaker, invitation_id, "decline")
    first = ctx.stored(invitation_id).response_recorded_at

    again = ctx.answer(speaker, invitation_id, "decline")

    assert again.status_code == 200
    assert again.json()["recorded"] is False
    assert ctx.stored(invitation_id).response_recorded_at == first


def test_a_different_second_answer_is_409_and_changes_nothing(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]
    ctx.answer(speaker, invitation_id, "accept")

    response = ctx.answer(speaker, invitation_id, "decline")

    assert response.status_code == 409
    assert _code(response) == "speaker_invitation_already_answered"
    assert ctx.stored(invitation_id).response_status == "accepted_invitation"


def test_a_link_answer_then_a_different_portal_answer_is_409(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]
    link_token = secrets.token_urlsafe(32)
    ctx.execute(
        "UPDATE cba_invitation SET response_token_hash = :h WHERE id = :i",
        h=hashlib.sha256(link_token.encode("utf-8")).hexdigest(),
        i=invitation_id,
    )
    by_link = ctx.client.post(
        "/v1/speaker-invitations/respond", json={"token": link_token, "response": "decline"}
    )
    assert by_link.status_code == 200, by_link.text

    response = ctx.answer(speaker, invitation_id, "accept")

    assert response.status_code == 409
    assert _code(response) == "speaker_invitation_already_answered"
    stored = ctx.stored(invitation_id)
    assert stored.response_channel == "speaker_link"
    assert stored.response_status == "declined_invitation"


@pytest.mark.parametrize(("theirs", "status_code"), [("accept", 200), ("decline", 409)])
def test_a_lost_race_is_classified_not_silent(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch, theirs: str, status_code: int
) -> None:
    speaker = ctx.speaker()
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]
    real = speaker_self._invites.record_response
    stored_word = "accepted_invitation" if theirs == "accept" else "declined_invitation"

    def racing(*args: Any, **kwargs: Any) -> bool:
        # A Connector's answer commits, on its own connection, between the
        # route's read and its guarded write.
        ctx.execute(
            "UPDATE cba_invitation SET response_status = :s, response_channel = "
            "'connector_recorded', response_recorded_at = now(), "
            "response_recorded_by_user_id = :u WHERE id = :i",
            s=stored_word,
            u=ctx.coordinator_id,
            i=invitation_id,
        )
        return real(*args, **kwargs)

    monkeypatch.setattr(speaker_self._invites, "record_response", racing)

    response = ctx.answer(speaker, invitation_id, "accept")

    assert response.status_code == status_code, response.text
    if status_code == 200:
        assert response.json()["recorded"] is False
        assert response.json()["invitation"]["response"]["recorded_by"] == "speaker_connector"
    else:
        assert _code(response) == "speaker_invitation_already_answered"
    assert ctx.stored(invitation_id).response_channel == "connector_recorded"


def test_a_lost_race_that_leaves_the_row_awaiting_fails_closed(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    speaker = ctx.speaker()
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]
    reads: list[Any] = []
    real_get = speaker_self._invites.get_for_professional

    def counting_get(*args: Any, **kwargs: Any) -> Any:
        reads.append(kwargs.get("invitation_id"))
        return real_get(*args, **kwargs)

    monkeypatch.setattr(speaker_self._invites, "get_for_professional", counting_get)
    monkeypatch.setattr(speaker_self._invites, "record_response", lambda *a, **k: False)

    response = ctx.answer(speaker, invitation_id, "accept")

    assert response.status_code == 409
    assert _code(response) == "speaker_invitation_response_conflict"
    assert len(reads) == 2
    assert ctx.stored(invitation_id).response_status == "awaiting_response"


def test_accepting_writes_no_pipeline_stage_and_no_consent(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]
    state_before = ctx.scalar(
        "SELECT contact_state FROM contact_channel WHERE professional_id = :p",
        p=speaker.professional_id,
    )

    assert ctx.answer(speaker, invitation_id, "accept").status_code == 200

    assert (
        ctx.scalar("SELECT count(*) FROM pipeline_record WHERE tenant_id = :t", t=ctx.tenant_id)
        == 0
    )
    assert (
        ctx.scalar(
            "SELECT contact_state FROM contact_channel WHERE professional_id = :p",
            p=speaker.professional_id,
        )
        == state_before
    )


@pytest.mark.parametrize(
    "body", [{"response": "maybe"}, {}, {"response": "accept", "channel": "speaker_link"}]
)
def test_bad_response_body_is_422(ctx: _Ctx, body: dict[str, Any]) -> None:
    speaker = ctx.speaker()
    invitation_id = ctx.invite(speaker.professional_id)[speaker.professional_id]

    response = ctx.client.post(
        f"/v1/me/invitations/{invitation_id}/response", json=body, headers=speaker.headers
    )

    assert response.status_code == 422
    assert _code(response) == "invalid_request"
    assert ctx.stored(invitation_id).response_status == "awaiting_response"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def _statement(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "expected_version": None,
        "invitations_paused_until": None,
        "declared_capacity_hours_per_90_days": None,
        "unavailable": [],
    }
    body.update(overrides)
    return body


def test_get_unstated_is_stated_false(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    body = ctx.call("GET", "/v1/me/availability", speaker.headers).json()
    assert body["stated"] is False
    assert body["version"] is None
    assert body["professional_id"] == str(speaker.professional_id)


def test_patch_writes_speaker_source_on_row_and_new_windows(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    window = {"starts_on": "2026-12-01", "ends_on": "2026-12-03"}

    response = ctx.call(
        "PATCH",
        "/v1/me/availability",
        speaker.headers,
        json=_statement(declared_capacity_hours_per_90_days=12.5, unavailable=[window]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stated"] is True
    assert body["updated_source"] == "speaker"
    assert body["unavailable"] == [{**window, "source": "speaker"}]
    assert (
        ctx.scalar(
            "SELECT updated_by_user_id FROM speaker_availability WHERE professional_id = :p",
            p=speaker.professional_id,
        )
        == speaker.login_id
    )


def test_connector_window_keeps_its_source_after_a_speaker_replace(
    ctx: _Ctx, frozen: datetime
) -> None:
    speaker = ctx.speaker()
    kept = {"starts_on": "2026-12-01", "ends_on": "2026-12-03"}
    added = {"starts_on": "2027-01-10", "ends_on": "2027-01-10"}
    by_connector = ctx.connector_availability(
        speaker.professional_id, "PATCH", json=_statement(unavailable=[kept])
    )
    assert by_connector.status_code == 200, by_connector.text

    response = ctx.call(
        "PATCH",
        "/v1/me/availability",
        speaker.headers,
        json=_statement(expected_version=by_connector.json()["version"], unavailable=[kept, added]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["unavailable"] == [
        {**kept, "source": "connector"},
        {**added, "source": "speaker"},
    ]


def test_connector_route_reads_the_speakers_write(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    written = ctx.call(
        "PATCH",
        "/v1/me/availability",
        speaker.headers,
        json=_statement(invitations_paused_until="2026-12-31"),
    )
    assert written.status_code == 200, written.text

    read = ctx.connector_availability(speaker.professional_id).json()

    assert read["updated_source"] == "speaker"
    assert read["invitations_paused_until"] == "2026-12-31"
    assert read["version"] == written.json()["version"]


def test_stale_version_is_409_without_details(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    ctx.call("PATCH", "/v1/me/availability", speaker.headers, json=_statement())

    response = ctx.call("PATCH", "/v1/me/availability", speaker.headers, json=_statement())

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "speaker_availability_stale"
    assert "details" not in error


@pytest.mark.parametrize(
    ("overrides", "code", "details"),
    [
        (
            {"unavailable": [{"starts_on": "2026-12-05", "ends_on": "2026-12-01"}]},
            "speaker_availability_window_invalid",
            {"field": "unavailable", "index": 0},
        ),
        (
            {
                "unavailable": [
                    {"starts_on": f"2027-01-{day:02d}", "ends_on": f"2027-01-{day:02d}"}
                    for day in range(1, 22)
                ]
            },
            "speaker_availability_too_many_windows",
            {"field": "unavailable", "limit": 20},
        ),
        (
            {"invitations_paused_until": "2030-01-01"},
            "speaker_availability_pause_invalid",
            {"field": "invitations_paused_until"},
        ),
        (
            {"declared_capacity_hours_per_90_days": 0},
            "speaker_availability_capacity_invalid",
            {"field": "declared_capacity_hours_per_90_days"},
        ),
    ],
)
def test_each_domain_code_is_422_with_t3_details(
    ctx: _Ctx, frozen: datetime, overrides: dict[str, Any], code: str, details: dict[str, Any]
) -> None:
    speaker = ctx.speaker()

    response = ctx.call(
        "PATCH", "/v1/me/availability", speaker.headers, json=_statement(**overrides)
    )

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["details"] == details


def test_today_is_the_utc_date(ctx: _Ctx, frozen: datetime) -> None:
    """At 03:00 UTC on 2 November it is still 1 November in Los Angeles."""
    speaker = ctx.speaker()
    yesterday_utc = (TODAY - timedelta(days=1)).isoformat()

    refused = ctx.call(
        "PATCH",
        "/v1/me/availability",
        speaker.headers,
        json=_statement(invitations_paused_until=yesterday_utc),
    )
    accepted = ctx.call(
        "PATCH",
        "/v1/me/availability",
        speaker.headers,
        json=_statement(invitations_paused_until=TODAY.isoformat()),
    )

    assert refused.status_code == 422
    assert _code(refused) == "speaker_availability_pause_invalid"
    assert accepted.status_code == 200, accepted.text


def test_patch_body_naming_a_professional_is_422_invalid_request(ctx: _Ctx) -> None:
    a = ctx.speaker("Avery Stone")
    b = ctx.speaker("Blake Moreno")

    response = ctx.call(
        "PATCH",
        "/v1/me/availability",
        a.headers,
        json=_statement(professional_id=str(b.professional_id)),
    )

    assert response.status_code == 422
    assert _code(response) == "invalid_request"
    assert (
        ctx.scalar(
            "SELECT count(*) FROM speaker_availability WHERE tenant_id = :t", t=ctx.tenant_id
        )
        == 0
    )


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------


def test_upcoming_and_past_split_on_local_date_vs_utc_today(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    past = ctx.journey(speaker.professional_id, ctx.event(TODAY - timedelta(days=1)))
    today = ctx.journey(speaker.professional_id, ctx.event(TODAY))
    unresolved = ctx.journey(speaker.professional_id, ctx.event(None))

    upcoming = ctx.call("GET", "/v1/me/engagements?when=upcoming", speaker.headers).json()
    earlier = ctx.call("GET", "/v1/me/engagements?when=past", speaker.headers).json()

    assert upcoming["as_of"] == TODAY.isoformat()
    assert upcoming["when"] == "upcoming"
    assert [e["engagement_id"] for e in upcoming["engagements"]] == [str(today), str(unresolved)]
    assert [e["engagement_id"] for e in earlier["engagements"]] == [str(past)]
    assert (
        earlier["engagements"][0]["event"]["local_date"] == (TODAY - timedelta(days=1)).isoformat()
    )


def test_when_defaults_to_upcoming(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    body = ctx.call("GET", "/v1/me/engagements", speaker.headers).json()
    assert body["when"] == "upcoming"
    assert body["engagements"] == []
    assert body["truncated"] is False


def test_bad_when_is_422(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    response = ctx.call("GET", "/v1/me/engagements?when=soon", speaker.headers)
    assert response.status_code == 422
    assert _code(response) == "invalid_request"


def test_cancelled_booking_shows_cancelled_without_canceller(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    ctx.journey(speaker.professional_id, ctx.event(TODAY + timedelta(days=3)), cancelled=True)

    response = ctx.call("GET", "/v1/me/engagements", speaker.headers)

    item = response.json()["engagements"][0]
    assert item["state"] == "cancelled"
    assert item["cancelled_at"] is not None
    assert set(item) == {
        "engagement_id",
        "event",
        "state",
        "confirmed_at",
        "attended_at",
        "cancelled_at",
    }
    assert str(ctx.coordinator_id) not in response.text
    assert str(ctx.unit_id) not in response.text


def test_attended_booking_shows_attended(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    ctx.journey(speaker.professional_id, ctx.event(TODAY - timedelta(days=3)), attended=True)

    item = ctx.call("GET", "/v1/me/engagements?when=past", speaker.headers).json()["engagements"][0]

    assert item["state"] == "attended"
    assert item["attended_at"] is not None


def test_contacted_only_journey_is_not_listed(ctx: _Ctx, frozen: datetime) -> None:
    speaker = ctx.speaker()
    ctx.journey(speaker.professional_id, ctx.event(TODAY + timedelta(days=3)), confirmed=False)

    body = ctx.call("GET", "/v1/me/engagements", speaker.headers).json()

    assert body["engagements"] == []


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def test_routes_unmounted_when_capability_off(ctx: _Ctx) -> None:
    speaker = ctx.speaker()
    off = TestClient(build_app(ctx.session_factory, ctx.verifier, ctx.secret, Settings()))
    for method, template in ROUTES:
        path, kwargs = _request_for(method, template)
        response = off.request(method, path, headers=speaker.headers, **kwargs)
        assert response.status_code in (404, 405), (method, template)
        if response.status_code == 404:
            assert response.json()["error"]["code"] != "speaker_profile_not_linked"


def test_routes_mounted_when_on() -> None:
    mounted = {
        (method, route.path)
        for router in routers_for(_PortalOn())
        for route in router.routes
        for method in getattr(route, "methods", ())
    }
    assert set(ROUTES) <= mounted


# ---------------------------------------------------------------------------
# B26 T6b-5: /v1/me/* after activation, in both modes (plan §8.1 item 6)
# ---------------------------------------------------------------------------


def _host_login_at(ctx: _Ctx, address: str) -> tuple[uuid.UUID, str]:
    """An Event Host login already holding ``address``: ``(user_id, password)``."""
    from smartmatch_domain.pilot_credentials import (
        MINIMUM_ITERATIONS,
        derive_password_hash,
        new_salt,
    )

    user_id = uuid.uuid4()
    pw = _new_pw()
    stored = derive_password_hash(pw, salt=new_salt(), iterations=MINIMUM_ITERATIONS)
    ctx.execute(
        "INSERT INTO user_account (id, tenant_id, external_subject, email) "
        "VALUES (:id, :t, :s, :e)",
        id=user_id,
        t=ctx.tenant_id,
        s=f"sub-self-host-{user_id.hex}",
        e=address,
    )
    ctx.execute(
        "INSERT INTO pilot_credential (id, tenant_id, user_id, algorithm, iterations, salt, "
        "password_hash) VALUES (:id, :t, :u, :a, :i, :s, :h)",
        id=uuid.uuid4(),
        t=ctx.tenant_id,
        u=user_id,
        a=stored.algorithm,
        i=stored.iterations,
        s=stored.salt,
        h=stored.digest,
    )
    ctx.grant(user_id, "volunteer")
    return user_id, pw


def _activated(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch, *, existing: bool
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """Invite and activate through the real routes: ``(professional_id, login_id, headers)``."""
    monkeypatch.setattr(
        portal_router, "_activation_caller_key", lambda request: f"test-{ctx.tenant_id.hex}"
    )
    professional_id, channel_id = ctx.contact("Dana Reyes")
    if existing:
        login_id, pw = _host_login_at(ctx, ctx.address_of(professional_id).upper())
        body = {"existing_password": pw}
    else:
        login_id = professional_id
        body = {"new_password": _new_pw()}
    invited = ctx.client.post(
        f"/v1/units/{ctx.unit_id}/speaker-contacts/{professional_id}/portal-invitations",
        json={"contact_channel_id": str(channel_id)},
        headers=ctx.coordinator,
    )
    assert invited.status_code == 202, invited.text
    token = derive_token(ctx.secret, uuid.UUID(invited.json()["invitation_id"]))
    activated = ctx.client.post("/v1/speaker-portal/activate", json={"token": token, **body})
    assert activated.status_code == 200, activated.text
    return (
        professional_id,
        login_id,
        {"Authorization": f"Bearer {activated.json()['access_token']}"},
    )


def _batch_for(ctx: _Ctx, professional_id: uuid.UUID) -> tuple[str, str]:
    created = ctx.client.post(
        f"/v1/units/{ctx.unit_id}/speaker-invitations/batches",
        json={
            "professional_ids": [str(professional_id)],
            "event_name": "Accounting Society Spring Mixer",
            "event_date": EVENT_DATE_TEXT,
            "coordinator_name": "Dana Okafor",
        },
        headers={**ctx.coordinator, "Idempotency-Key": f"key-{uuid.uuid4().hex}"},
    )
    assert created.status_code == 201, created.text
    batch = created.json()
    dispatched = ctx.client.post(
        f"/v1/units/{ctx.unit_id}/speaker-invitations/batches/{batch['batch_id']}/dispatch",
        headers=ctx.coordinator,
    )
    assert dispatched.status_code == 202, dispatched.text
    return str(batch["batch_id"]), str(batch["invitations"][0]["invitation_id"])


def _assert_own_rows_through_the_login(
    ctx: _Ctx, professional_id: uuid.UUID, login_id: uuid.UUID, headers: dict[str, str]
) -> None:
    other = ctx.speaker("Other Speaker")
    batch_id, invitation_id = _batch_for(ctx, professional_id)
    ctx.invite(other.professional_id)

    listed = ctx.call("GET", "/v1/me/invitations", headers)
    assert listed.status_code == 200, listed.text
    assert [item["invitation_id"] for item in listed.json()["invitations"]] == [invitation_id]
    availability = ctx.call("GET", "/v1/me/availability", headers)
    assert availability.status_code == 200, availability.text
    assert availability.json()["professional_id"] == str(professional_id)
    engagements = ctx.call("GET", "/v1/me/engagements", headers)
    assert engagements.status_code == 200, engagements.text

    answered = ctx.client.post(
        f"/v1/me/invitations/{invitation_id}/response",
        json={"response": "accept"},
        headers=headers,
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["invitation"]["response"]["recorded_by"] == "speaker"
    assert ctx.stored(invitation_id).response_recorded_by_user_id == login_id

    connector = ctx.client.get(
        f"/v1/units/{ctx.unit_id}/speaker-invitations/batches/{batch_id}",
        headers=ctx.coordinator,
    )
    assert connector.status_code == 200, connector.text
    [row] = [
        item
        for item in connector.json()["invitations"]
        if str(item["invitation_id"]) == invitation_id
    ]
    assert row["speaker_response"]["recorded_by_user_id"] is None
    if login_id != professional_id:
        # The Host's login id never reaches the Connector view (T6b-2's rule).
        assert str(login_id) not in connector.text


def test_availability_and_invitations_after_existing_login_activation(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    professional_id, login_id, headers = _activated(ctx, monkeypatch, existing=True)
    assert login_id != professional_id
    _assert_own_rows_through_the_login(ctx, professional_id, login_id, headers)


def test_after_new_login_activation(ctx: _Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    professional_id, login_id, headers = _activated(ctx, monkeypatch, existing=False)
    assert login_id == professional_id
    _assert_own_rows_through_the_login(ctx, professional_id, login_id, headers)


def test_after_unbind_the_speaker_routes_answer_not_linked(
    ctx: _Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T6b-5 §4.4: the next request by the (still signed-in) Host login loses the portal."""
    professional_id, _login_id, headers = _activated(ctx, monkeypatch, existing=True)
    assert ctx.call("GET", "/v1/me/availability", headers).status_code == 200

    unbound = ctx.client.delete(
        f"/v1/units/{ctx.unit_id}/speaker-contacts/{professional_id}/portal-access",
        headers=ctx.coordinator,
    )
    assert unbound.json() == {"unbound": True}

    for method, path in ROUTES:
        concrete, kwargs = _request_for(method, path)
        response = ctx.call(method, concrete, headers, **kwargs)
        assert response.status_code == 404, (method, path, response.text)
        assert _code(response) == "speaker_profile_not_linked"
    portals = ctx.call("GET", "/v1/me/portals", headers).json()
    assert [p["portal"] for p in portals["portals"]] == ["volunteer"]


def test_a_suspended_merged_login_is_refused_on_host_and_speaker_routes(ctx: _Ctx) -> None:
    """R-L: suspension is per login, so one suspended login loses both roles.

    (Plan §8.1 names ``test_me_suspended.py``; it lives here because this module
    builds the application with ``SPEAKER_PORTAL`` on.)
    """
    speaker = ctx.speaker(merged_login=True)
    ctx.grant(speaker.login_id, "volunteer")
    assert ctx.call("GET", "/v1/me/availability", speaker.headers).status_code == 200
    host_read = f"/v1/units/{ctx.unit_id}/host/speaker-requests"
    assert ctx.call("GET", host_read, speaker.headers).status_code == 200

    ctx.execute("UPDATE user_account SET suspended = true WHERE id = :u", u=speaker.login_id)

    for path in ("/v1/me/availability", host_read):
        response = ctx.call("GET", path, speaker.headers)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"]["details"]["reason"] == "principal_suspended", path
