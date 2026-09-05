"""Contract tests for ``GET /v1/me/portals`` under CBA role presentation.

The route already existed; what this file pins is the property the CBA pivot
puts under pressure. Renaming what a portal is *called* is a presentation
change, and a presentation change must not become an authorization change —
so these tests assert both halves at once: the visible labels are the CBA
personas, the stored ``membership.role`` the server echoes back is unchanged,
and a listed portal still opens nothing the policy would refuse.

Structured like ``tests/contract/test_me.py`` and for its reasons: this
route's whole response is derived from a resolved principal, so it needs real
``tenant``/``org_unit``/``user_account``/``membership`` rows, is marked
``integration``, and skips cleanly when no database is reachable. The
fixtures are local rather than imported from ``tests/integration/conftest.py``,
which pytest scopes to that directory.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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

#: The org-unit subtree every membership below is granted over. One real row,
#: so ``units_in_subtree`` resolves a genuine ``default_unit_id`` rather than
#: the empty case.
UNIT_PATH = "cba"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A connected engine, or skip the whole module."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def client(engine: Engine) -> TestClient:
    """A client wired to the test database and a fixture token verifier."""
    verifier = FixtureTokenVerifier()
    test_client = TestClient(app)
    test_client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    test_client.app.state.token_verifier = verifier
    test_client.verifier = verifier  # type: ignore[attr-defined]
    return test_client


@pytest.fixture
def tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    """One isolated tenant with one org unit, cleaned up after the test."""
    tid = uuid.uuid4()
    slug = f"test-portals-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tid, "slug": slug},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'program', :name)"
            ),
            {"id": uuid.uuid4(), "tid": tid, "path": UNIT_PATH, "name": "CBA"},
        )
    yield tid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM membership WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM resource_grant WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def _unique_subject(name: str) -> str:
    """Suffix a subject so parallel runs cannot collide on ``external_subject``."""
    return f"{name}-{uuid.uuid4().hex[:8]}"


def _make_user(engine: Engine, tenant_id: uuid.UUID, *, subject: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {"id": user_id, "tid": tenant_id, "sub": subject, "email": f"{subject}@example.edu"},
        )
    return user_id


def _grant(
    engine: Engine,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    role: str,
    path: str = UNIT_PATH,
    valid_until: datetime | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership "
                "(id, tenant_id, user_id, granted_path, role, valid_from, valid_until) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role, NULL, :vu)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uid": user_id,
                "path": path,
                "role": role,
                "vu": valid_until,
            },
        )


def _portals(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID, *, role: str, name: str
) -> dict:
    """Seed one account holding ``role`` and return its portal mapping."""
    subject = _unique_subject(name)
    user_id = _make_user(engine, tenant_id, subject=subject)
    _grant(engine, tenant_id, user_id, role=role)
    token = f"tok-{subject}"
    client.verifier.register(token, subject)  # type: ignore[attr-defined]
    response = client.get("/v1/me/portals", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# 1. Visible labels are the CBA personas; stored roles are untouched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "portal", "display_name"),
    [
        ("student", "student", "Student Portal"),
        ("volunteer", "volunteer", "Event Host Portal"),
        ("coordinator", "coordinator", "Speaker Connector Portal"),
        ("admin", "admin", "CBA Administration"),
    ],
)
def test_each_stored_role_opens_its_portal_under_a_cba_label(
    client: TestClient,
    engine: Engine,
    tenant_id: uuid.UUID,
    role: str,
    portal: str,
    display_name: str,
) -> None:
    body = _portals(client, engine, tenant_id, role=role, name=f"sub-{role}")

    assert body["default_portal"] == portal
    assert len(body["portals"]) == 1
    descriptor = body["portals"][0]
    assert descriptor["portal"] == portal
    assert descriptor["display_name"] == display_name
    # The stored string is echoed back exactly. Presentation renamed nothing
    # in the database, which is the deferred decision this track must not make.
    assert descriptor["role"] == role
    assert descriptor["org_unit_path"] == UNIT_PATH
    assert descriptor["default_unit_id"] is not None


def test_no_visible_label_carries_ia_west_or_chapter_wording(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """Customer §4: the legacy institutional wording is gone from the wire."""
    for role in ("student", "volunteer", "coordinator", "admin"):
        body = _portals(client, engine, tenant_id, role=role, name=f"sub-wording-{role}")
        shown = body["portals"][0]["display_name"].lower()
        for banned in ("ia west", "iawest", "insights association", "chapter", "volunteer"):
            assert banned not in shown, f"{role} portal is still labelled {shown!r}"


def test_the_portal_ids_and_home_paths_are_unchanged(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """Labels moved; routing did not. The shells stay mounted where they are."""
    expected = {
        "student": "/student-portal",
        "volunteer": "/volunteer-portal",
        "coordinator": "/coordinator-portal",
        "admin": "/dashboard",
    }
    for role, home_path in expected.items():
        body = _portals(client, engine, tenant_id, role=role, name=f"sub-path-{role}")
        assert body["portals"][0]["home_path"] == home_path


# ---------------------------------------------------------------------------
# 2. Nothing is invented for a role the map does not know
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["speaker", "dean", "   ", "Student"])
def test_an_unmapped_or_blank_role_opens_no_portal(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID, role: str
) -> None:
    body = _portals(client, engine, tenant_id, role=role, name="sub-unmapped")
    assert body["portals"] == []
    assert body["default_portal"] is None


def test_an_expired_membership_opens_no_portal(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    subject = _unique_subject("sub-expired")
    user_id = _make_user(engine, tenant_id, subject=subject)
    _grant(
        engine,
        tenant_id,
        user_id,
        role="coordinator",
        valid_until=datetime.now(UTC) - timedelta(days=1),
    )
    token = f"tok-{subject}"
    client.verifier.register(token, subject)  # type: ignore[attr-defined]

    body = client.get("/v1/me/portals", headers={"Authorization": f"Bearer {token}"}).json()

    assert body["portals"] == []
    assert body["default_portal"] is None


# ---------------------------------------------------------------------------
# 3. A label is not a power: one login, no chooser, no widening
# ---------------------------------------------------------------------------


def test_the_route_takes_no_role_from_the_caller(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """A query string naming a persona changes nothing about the answer.

    There is no portal chooser and no request-body role (customer §3). The
    only input this route reads is the verified principal, so a caller who
    asks for the connector portal by name gets exactly the mapping their own
    memberships produce.
    """
    subject = _unique_subject("sub-nochooser")
    user_id = _make_user(engine, tenant_id, subject=subject)
    _grant(engine, tenant_id, user_id, role="student")
    token = f"tok-{subject}"
    client.verifier.register(token, subject)  # type: ignore[attr-defined]
    headers = {"Authorization": f"Bearer {token}"}

    plain = client.get("/v1/me/portals", headers=headers).json()
    asked = client.get(
        "/v1/me/portals?portal=admin&role=coordinator&persona=Speaker+Connector",
        headers=headers,
    ).json()

    assert plain == asked
    assert [entry["portal"] for entry in plain["portals"]] == ["student"]


def test_listing_a_portal_authorizes_nothing(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """The regression this whole track rests on.

    A student is listed a portal and is still refused an operation the policy
    gates on ``{admin, coordinator}``. Were a label ever wired into
    authorization, this is the test that would fail.
    """
    subject = _unique_subject("sub-noauth")
    user_id = _make_user(engine, tenant_id, subject=subject)
    _grant(engine, tenant_id, user_id, role="student")
    token = f"tok-{subject}"
    client.verifier.register(token, subject)  # type: ignore[attr-defined]
    headers = {"Authorization": f"Bearer {token}"}

    mapping = client.get("/v1/me/portals", headers=headers).json()
    assert mapping["portals"][0]["portal"] == "student"
    unit_id = mapping["portals"][0]["default_unit_id"]
    assert unit_id is not None

    refused = client.post(
        f"/v1/units/{unit_id}/imports",
        headers={**headers, "Idempotency-Key": f"key-{uuid.uuid4().hex}"},
        # A well-formed body, so the refusal below is the authorizer's and not
        # request validation's — a 422 would prove nothing about roles.
        json={"source_reference": "s3://bucket/object.csv", "dataset": "professionals"},
    )

    assert refused.status_code == 403
