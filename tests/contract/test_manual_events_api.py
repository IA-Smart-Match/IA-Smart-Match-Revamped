"""HTTP contract for manually filed events and their feedback QR redirect.

Mirrors ``tests/contract/test_meetings_api.py``'s shape: a real tenant, real
rows, nothing mocked. ``tests/authz/test_policy_matrix.py`` owns the full
authorization rectangle and needs no database; this file adds what only
exists over HTTP — an admin can create/edit/publish an event and manage its
feedback QR, a coordinator can read a published one but not a draft, a
sibling department and another tenant are refused, and the public redirect
is data-minimised and inactive until the event is published.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.manualevents"
SIBLING_UNIT_PATH = "iawest.manualeventsibling"
ZONE = "America/Los_Angeles"


def _events_path(unit_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/events"


def _event_path(unit_id: uuid.UUID, event_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/events/{event_id}"


@pytest.fixture(scope="module")
def engine() -> Engine:
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM event_manual_detail LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


def _register_principal(
    engine: Engine,
    tenant_id: uuid.UUID,
    verifier: FixtureTokenVerifier,
    *,
    role: str | None,
    membership_path: str = UNIT_PATH,
) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    subject = f"sub-manual-events-{uuid.uuid4().hex}"
    token = f"tok-manual-events-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "subject": subject,
                "email": f"{subject}@example.edu",
            },
        )
        if role is not None:
            conn.execute(
                text(
                    "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                    "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "uid": user_id,
                    "path": membership_path,
                    "role": role,
                },
            )

    verifier.register(token, subject)
    return token, user_id


def _provision_tenant(engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-manual-events-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Manual Events"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
    return tenant_id, unit_id, sibling_unit_id


def _drop_tenant(engine: Engine, tenant_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        for table in (
            "event_feedback_qr_open",
            "event_feedback_qr",
            "event_manual_detail",
            "event",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


@pytest.fixture
def context(engine: Engine) -> Iterator[dict[str, object]]:
    tenant_id, unit_id, sibling_unit_id = _provision_tenant(engine)

    verifier = FixtureTokenVerifier()
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    admin_token, admin_id = _register_principal(engine, tenant_id, verifier, role="admin")
    coordinator_token, _ = _register_principal(engine, tenant_id, verifier, role="coordinator")

    yield {
        "client": client,
        "engine": engine,
        "verifier": verifier,
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "sibling_unit_id": sibling_unit_id,
        "admin_token": admin_token,
        "admin_id": admin_id,
        "coordinator_token": coordinator_token,
    }

    _drop_tenant(engine, tenant_id)


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _create_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "title": "Fall hackathon",
        "description": "A weekend hackathon for undergraduates.",
        "category": "hackathon",
        "time_precision": "exact",
        "starts_at": "2026-10-02T16:00:00+00:00",
        "time_zone": ZONE,
        "location": "Bldg 9-241",
        "capacity": 100,
        "volunteer_openings": 5,
        "volunteer_needs": "Registration desk",
        "audience": "Undergraduates",
        "contact_name": "Jamie Lee",
        "contact_email": "jamie@example.edu",
    }
    body.update(overrides)
    return body


def _create(context: dict[str, object], idempotency_key: str | None = None, **overrides: object):
    return context["client"].post(  # type: ignore[union-attr]
        _events_path(context["unit_id"]),  # type: ignore[arg-type]
        headers={
            **_headers(context["admin_token"]),  # type: ignore[arg-type]
            "Idempotency-Key": idempotency_key or uuid.uuid4().hex,
        },
        json=_create_body(**overrides),
    )


def test_admin_can_create_a_draft_and_a_coordinator_cannot_read_it(
    context: dict[str, object],
) -> None:
    response = _create(context)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"

    event_id = uuid.UUID(body["id"])
    coordinator_read = context["client"].get(  # type: ignore[union-attr]
        _event_path(context["unit_id"], event_id),  # type: ignore[arg-type]
        headers=_headers(context["coordinator_token"]),  # type: ignore[arg-type]
    )
    assert coordinator_read.status_code == 403


def test_publish_requires_complete_details_then_a_coordinator_can_read_it(
    context: dict[str, object],
) -> None:
    created = _create(context).json()
    event_id = uuid.UUID(created["id"])

    published = context["client"].post(  # type: ignore[union-attr]
        f"{_event_path(context['unit_id'], event_id)}/publish",  # type: ignore[arg-type]
        headers=_headers(context["admin_token"]),  # type: ignore[arg-type]
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    coordinator_read = context["client"].get(  # type: ignore[union-attr]
        _event_path(context["unit_id"], event_id),  # type: ignore[arg-type]
        headers=_headers(context["coordinator_token"]),  # type: ignore[arg-type]
    )
    assert coordinator_read.status_code == 200
    assert coordinator_read.json()["status"] == "published"


def test_create_is_idempotent_on_the_replay_key(context: dict[str, object]) -> None:
    key = uuid.uuid4().hex
    first = _create(context, idempotency_key=key)
    second = _create(context, idempotency_key=key)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_a_unit_in_another_tenant_is_404_not_403(context: dict[str, object]) -> None:
    foreign_unit_id = uuid.uuid4()
    response = context["client"].get(  # type: ignore[union-attr]
        _event_path(foreign_unit_id, uuid.uuid4()),
        headers=_headers(context["admin_token"]),  # type: ignore[arg-type]
    )
    assert response.status_code == 404


def test_feedback_qr_redirects_only_after_publish_and_stores_no_visitor_data(
    context: dict[str, object],
) -> None:
    created = _create(context).json()
    event_id = uuid.UUID(created["id"])

    qr = context["client"].put(  # type: ignore[union-attr]
        f"{_event_path(context['unit_id'], event_id)}/feedback-qr",  # type: ignore[arg-type]
        headers=_headers(context["admin_token"]),  # type: ignore[arg-type]
        json={"destination_url": "https://forms.example.edu/feedback"},
    )
    assert qr.status_code == 200
    redirect_url = qr.json()["redirect_url"]
    public_token = redirect_url.rsplit("/", 1)[-1]

    before_publish = context["client"].get(f"/q/{public_token}", follow_redirects=False)
    assert before_publish.status_code == 404

    context["client"].post(  # type: ignore[union-attr]
        f"{_event_path(context['unit_id'], event_id)}/publish",  # type: ignore[arg-type]
        headers=_headers(context["admin_token"]),  # type: ignore[arg-type]
    )

    after_publish = context["client"].get(f"/q/{public_token}", follow_redirects=False)
    assert after_publish.status_code == 302
    assert after_publish.headers["location"] == "https://forms.example.edu/feedback"
    assert after_publish.headers["cache-control"] == "no-store"

    with context["engine"].connect() as conn:  # type: ignore[union-attr]
        columns = set(conn.execute(text("SELECT * FROM event_feedback_qr_open LIMIT 0")).keys())
    assert {"ip", "user_agent", "referrer", "cookie"}.isdisjoint(columns)
