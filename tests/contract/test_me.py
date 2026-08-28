"""Contract tests for ``GET /v1/me``.

Unlike ``tests/contract/test_api_health.py`` and ``test_error_envelope.py``,
this route's entire response *is* a resolved principal — there is no way to
produce one without a real ``user_account`` row and the ``membership`` rows
behind it. So, the same call ``tests/integration/test_command_path.py`` makes
for ``/v1/units/{unit_id}/imports``, this file lives under ``tests/contract/``
(it asserts the wire contract, not the dispatch pipeline that other routes
also exercise) but is marked ``integration`` and skips cleanly when no
database is reachable.

Deliberately self-contained rather than importing from
``tests/integration/conftest.py``: that module's fixtures are scoped by
pytest to files under ``tests/integration/``, and this track owns this file
only. The setup below is the minimum ``GET /v1/me`` needs — one tenant, one
account, and its memberships — not a second copy of the shared harness.
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


# ---------------------------------------------------------------------------
# Fixtures — minimal and local to this file, see the module docstring
# ---------------------------------------------------------------------------


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
    """A client wired to the test database and a fixture token verifier.

    ``app.state`` is set directly rather than through FastAPI's lifespan,
    which only runs when ``TestClient`` is used as a context manager — the
    same approach ``tests/integration/test_command_path.py`` uses for the
    same reason.
    """
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
    """One isolated tenant, cleaned up after the test."""
    tid = uuid.uuid4()
    slug = f"test-me-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tid, "slug": slug},
        )
    yield tid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM membership WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM resource_grant WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def _unique_subject(name: str) -> str:
    """Suffix a subject so parallel test runs cannot collide.

    ``external_subject`` is globally unique (migration ``0003``), the same
    reason ``tests/integration/conftest.py::unique_subject`` exists; this is
    that function's reasoning without importing across the directory boundary
    it is scoped to.
    """
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
    path: str = "iawest",
    role: str = "coordinator",
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership "
                "(id, tenant_id, user_id, granted_path, role, valid_from, valid_until) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role, :vf, :vu)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uid": user_id,
                "path": path,
                "role": role,
                "vf": valid_from,
                "vu": valid_until,
            },
        )


# ---------------------------------------------------------------------------
# 1. A valid token returns the caller's identity and server-assigned memberships
# ---------------------------------------------------------------------------


def test_me_returns_identity_and_a_membership(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    subject = _unique_subject("sub-me")
    user_id = _make_user(engine, tenant_id, subject=subject)
    _grant(engine, tenant_id, user_id, path="iawest.cpp.engineering.ie", role="coordinator")
    client.verifier.register("tok-me", subject)  # type: ignore[attr-defined]

    response = client.get("/v1/me", headers={"Authorization": "Bearer tok-me"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user_id)
    assert body["tenant_id"] == str(tenant_id)
    assert body["email"] == f"{subject}@example.edu"
    assert body["memberships"] == [
        {
            "org_unit_path": "iawest.cpp.engineering.ie",
            "role": "coordinator",
            "valid_from": None,
            "valid_until": None,
            "is_active": True,
        }
    ]


def test_me_reports_every_membership_and_its_validity_window(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    """Server-assigned means every row comes back, not only the active ones.

    The client decides what to do with an inactive membership; this route's
    job is to tell the truth about what the database recorded, which is why
    ``is_active`` is a computed field rather than a filter.
    """
    subject = _unique_subject("sub-multi")
    user_id = _make_user(engine, tenant_id, subject=subject)
    _grant(engine, tenant_id, user_id, path="iawest", role="admin")
    _grant(
        engine,
        tenant_id,
        user_id,
        path="iawest.cpp.engineering.cs",
        role="coordinator",
        valid_until=datetime.now(UTC) - timedelta(days=1),
    )
    client.verifier.register("tok-multi", subject)  # type: ignore[attr-defined]

    body = client.get("/v1/me", headers={"Authorization": "Bearer tok-multi"}).json()

    assert len(body["memberships"]) == 2
    by_role = {membership["role"]: membership for membership in body["memberships"]}
    assert by_role["admin"]["is_active"] is True
    assert by_role["coordinator"]["is_active"] is False
    assert by_role["coordinator"]["valid_until"] is not None


def test_me_reports_no_memberships_as_an_empty_list(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    subject = _unique_subject("sub-none")
    _make_user(engine, tenant_id, subject=subject)
    client.verifier.register("tok-none", subject)  # type: ignore[attr-defined]

    body = client.get("/v1/me", headers={"Authorization": "Bearer tok-none"}).json()
    assert body["memberships"] == []


# ---------------------------------------------------------------------------
# 2. No token, or an invalid one, is 401 through the standard envelope
# ---------------------------------------------------------------------------


def test_me_without_a_token_is_401_in_the_standard_envelope(client: TestClient):
    response = client.get("/v1/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthenticated"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_an_invalid_token_is_the_same_401(client: TestClient):
    response = client.get("/v1/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_with_a_token_for_no_local_account_is_the_same_401(client: TestClient):
    """A verified subject with no local row is still a 401, not a 403 or 404.

    ``get_current_principal``'s own docstring: the three failure modes answer
    identically so the response cannot be used to learn which subjects exist.
    """
    client.verifier.register("tok-stranger", _unique_subject("sub-stranger"))  # type: ignore[attr-defined]

    response = client.get("/v1/me", headers={"Authorization": "Bearer tok-stranger"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# 3. Nothing caller-supplied can influence the response (MM-A01)
# ---------------------------------------------------------------------------


def test_query_and_header_supplied_identity_is_ignored(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    """A caller cannot pick their own tenant, user, or role by asking for one.

    ``GET /v1/me`` declares no path parameter, no query parameter, and no
    body, so there is nothing on the request a handler could read even by
    accident. This sends the values a caller-selected-identity client would
    have supplied — the exact pattern archived as MM-A01 — and asserts the
    response is identical to one that supplied nothing at all.
    """
    subject = _unique_subject("sub-mm-a01")
    user_id = _make_user(engine, tenant_id, subject=subject)
    _grant(engine, tenant_id, user_id, role="coordinator")
    client.verifier.register("tok-mm-a01", subject)  # type: ignore[attr-defined]

    spoofed_tenant = uuid.uuid4()
    spoofed_user = uuid.uuid4()

    honest = client.get("/v1/me", headers={"Authorization": "Bearer tok-mm-a01"}).json()
    spoofed = client.get(
        f"/v1/me?tenant_id={spoofed_tenant}&user_id={spoofed_user}&role=admin",
        headers={
            "Authorization": "Bearer tok-mm-a01",
            "X-Tenant-Id": str(spoofed_tenant),
            "X-User-Id": str(spoofed_user),
            "X-Role": "admin",
        },
    ).json()

    assert spoofed == honest
    assert spoofed["tenant_id"] == str(tenant_id)
    assert spoofed["user_id"] == str(user_id)
    assert all(membership["role"] != "admin" for membership in spoofed["memberships"])


def test_response_carries_nothing_beyond_identity_tenant_and_memberships(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    """An explicit resource grant the account holds does not leak into the response.

    The task names the response's scope as identity, tenant, and
    server-assigned memberships — a ``resource_grant`` is a narrower, separate
    kind of authorization data, and this asserts it is genuinely absent rather
    than merely undocumented.
    """
    subject = _unique_subject("sub-grant")
    user_id = _make_user(engine, tenant_id, subject=subject)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO resource_grant "
                "(id, tenant_id, user_id, resource_type, resource_id, effect) "
                "VALUES (:id, :tid, :uid, 'job', :rid, 'allow')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "rid": uuid.uuid4()},
        )
    client.verifier.register("tok-grant", subject)  # type: ignore[attr-defined]

    body = client.get("/v1/me", headers={"Authorization": "Bearer tok-grant"}).json()

    assert set(body) == {"user_id", "tenant_id", "email", "suspended", "memberships"}
