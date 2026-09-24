"""An Event Host's own routes do not change when their login becomes a Speaker's too.

B26 T6b-5 plan §8.1 item 7 (parent §4.5 "neither widens the other"). One login,
two roles: the Host binds as a Speaker through existing-login activation, and
the Connector later removes the Speaker access. ``speaker_request.list_own``
and ``host_organization.read_own`` answer the same status and body before the
bind, after it, and after the unbind; and the Host can still file a request
while bound.

``SPEAKER_PORTAL`` is off in every scope, so the application is built from
``routers_for`` with that one capability on, as ``test_speaker_self_api.py``
does. Password- and token-shaped values are built at runtime.
"""

from __future__ import annotations

import os
import secrets
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.config import Settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.main import routers_for
from smartmatch_api.routers import speaker_portal as portal_router
from smartmatch_domain.pilot_credentials import (
    MINIMUM_ITERATIONS,
    derive_password_hash,
    new_salt,
)
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

UNIT_PATH = "iawest.merge"

_CLEANUP = (
    "speaker_request_classification",
    "event_tag",
    "event",
    "host_organization_member",
    "host_organization",
    "pilot_session",
    "pilot_credential",
    "speaker_portal_invitation",
    "delivery_event",
    "outreach_send",
    "outreach_draft",
    "contact_channel_transition",
    "contact_channel",
    "job_event",
    "outbox_record",
    "job",
    "idempotency_record",
    "speaker_profile",
    "membership",
    "resource_grant",
    "user_account",
    "org_unit",
    "rate_limit_counter",
)

_REQUEST = {
    "title": "Analytics Careers Panel",
    "time_zone": "America/Los_Angeles",
    "on_date": "2026-10-14",
    "is_virtual": False,
    "location_city": "Pomona",
    "industry_codes": ["52"],
    "role_codes": ["finance"],
    "description": "A panel on analytics careers for CBA students.",
}


class _PortalOn(Settings):
    def capability_enabled(self, capability: Capability) -> bool:  # type: ignore[override]
        return capability is Capability.SPEAKER_PORTAL or super().capability_enabled(capability)


def _new_pw() -> str:
    return "pw-" + uuid.uuid4().hex


class _Ctx:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.tenant_id = uuid.uuid4()
        self.unit_id = uuid.uuid4()
        self.verifier = FixtureTokenVerifier()
        self.secret = secrets.token_urlsafe(40)
        app = FastAPI()
        for exception_type, handler in EXCEPTION_HANDLERS.items():
            app.add_exception_handler(exception_type, handler)
        for router in routers_for(_PortalOn()):
            app.include_router(router)
        app.state.session_factory = create_session_factory(
            engine.url.render_as_string(hide_password=False)
        )
        app.state.token_verifier = self.verifier
        app.state.speaker_portal_token_secret = self.secret
        self.client = TestClient(app)
        self.execute(
            "INSERT INTO tenant (id, slug, display_name) VALUES (:id, :s, :s)",
            id=self.tenant_id,
            s=f"test-merge-{self.tenant_id.hex[:12]}",
        )
        self.execute(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :t, CAST(:p AS ltree), 'department', 'Merge')",
            id=self.unit_id,
            t=self.tenant_id,
            p=UNIT_PATH,
        )
        _, self.coordinator = self.person("coordinator")
        self.host_id, self.host = self.person("volunteer")
        self.host_address = f"Host-{self.host_id.hex[:8]}@Synthetic.invalid"
        self.host_pw = _new_pw()
        stored = derive_password_hash(self.host_pw, salt=new_salt(), iterations=MINIMUM_ITERATIONS)
        self.execute(
            "UPDATE user_account SET email = :e WHERE id = :u", e=self.host_address, u=self.host_id
        )
        self.execute(
            "INSERT INTO pilot_credential (id, tenant_id, user_id, algorithm, iterations, salt, "
            "password_hash) VALUES (:id, :t, :u, :a, :i, :s, :h)",
            id=uuid.uuid4(),
            t=self.tenant_id,
            u=self.host_id,
            a=stored.algorithm,
            i=stored.iterations,
            s=stored.salt,
            h=stored.digest,
        )

    def execute(self, sql: str, **params: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)

    def person(self, role: str) -> tuple[uuid.UUID, dict[str, str]]:
        user_id = uuid.uuid4()
        subject = f"sub-merge-{user_id.hex}"
        self.execute(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :t, :s, :e)",
            id=user_id,
            t=self.tenant_id,
            s=subject,
            e=f"{user_id.hex[:8]}@placeholder.invalid",
        )
        self.execute(
            "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
            "VALUES (:id, :t, :u, CAST(:p AS ltree), :r)",
            id=uuid.uuid4(),
            t=self.tenant_id,
            u=user_id,
            p=UNIT_PATH,
            r=role,
        )
        bearer = f"tok-merge-{uuid.uuid4().hex}"
        self.verifier.register(bearer, subject)
        return user_id, {"Authorization": f"Bearer {bearer}"}

    def contact_at_host_address(self) -> tuple[uuid.UUID, uuid.UUID]:
        professional_id, channel_id = uuid.uuid4(), uuid.uuid4()
        self.execute(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :t, :s, :e)",
            id=professional_id,
            t=self.tenant_id,
            s=f"sub-merge-contact-{professional_id.hex}",
            e=f"{professional_id.hex[:8]}@placeholder.invalid",
        )
        self.execute(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, full_name) "
            "VALUES (:t, :p, :u, 'Dana Reyes')",
            t=self.tenant_id,
            p=professional_id,
            u=self.unit_id,
        )
        self.execute(
            "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
            "channel_kind, address, contact_state, consent_source, consent_recorded_at) "
            "VALUES (:id, :t, :u, :p, 'email', :a, 'active_candidate', 'in_person', now())",
            id=channel_id,
            t=self.tenant_id,
            u=self.unit_id,
            p=professional_id,
            a=self.host_address.lower(),
        )
        return professional_id, channel_id

    def bind_host_as_speaker(self) -> uuid.UUID:
        professional_id, channel_id = self.contact_at_host_address()
        invited = self.client.post(
            f"/v1/units/{self.unit_id}/speaker-contacts/{professional_id}/portal-invitations",
            json={"contact_channel_id": str(channel_id)},
            headers=self.coordinator,
        )
        assert invited.status_code == 202, invited.text
        token = derive_token(self.secret, uuid.UUID(invited.json()["invitation_id"]))
        activated = self.client.post(
            "/v1/speaker-portal/activate",
            json={"token": token, "existing_password": self.host_pw},
        )
        assert activated.status_code == 200, activated.text
        return professional_id

    def unbind(self, professional_id: uuid.UUID) -> None:
        response = self.client.delete(
            f"/v1/units/{self.unit_id}/speaker-contacts/{professional_id}/portal-access",
            headers=self.coordinator,
        )
        assert response.json() == {"unbound": True}

    def host_view(self) -> tuple:
        """What the Host's two own reads answer, as ``(status, body)`` pairs."""
        answers = []
        for path in (
            f"/v1/units/{self.unit_id}/host/speaker-requests",
            f"/v1/units/{self.unit_id}/host/organization",
        ):
            response = self.client.get(path, headers=self.host)
            answers.append((response.status_code, response.content))
        return tuple(answers)

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
def ctx(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Ctx]:
    context = _Ctx(engine)
    monkeypatch.setattr(
        portal_router, "_activation_caller_key", lambda request: f"test-{context.tenant_id.hex}"
    )
    yield context
    context.drop()


def test_host_routes_answer_the_same_before_bind_after_bind_and_after_unbind(
    ctx: _Ctx,
) -> None:
    filed = ctx.client.post(
        f"/v1/units/{ctx.unit_id}/speaker-requests", json=_REQUEST, headers=ctx.host
    )
    assert filed.status_code == 201, filed.text
    before = ctx.host_view()
    assert before[0][0] == 200

    professional_id = ctx.bind_host_as_speaker()
    after_bind = ctx.host_view()
    ctx.unbind(professional_id)
    after_unbind = ctx.host_view()

    assert after_bind == before
    assert after_unbind == before


def test_host_can_still_file_a_request_after_bind(ctx: _Ctx) -> None:
    ctx.bind_host_as_speaker()

    filed = ctx.client.post(
        f"/v1/units/{ctx.unit_id}/speaker-requests", json=_REQUEST, headers=ctx.host
    )

    assert filed.status_code == 201, filed.text
    listed = ctx.client.get(f"/v1/units/{ctx.unit_id}/host/speaker-requests", headers=ctx.host)
    assert listed.status_code == 200
    assert filed.json()["request_id"] in listed.text
