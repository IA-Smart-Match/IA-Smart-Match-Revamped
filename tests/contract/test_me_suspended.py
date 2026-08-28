"""Contract test: a suspended caller can distinguish its own state via ``GET /v1/me``.

``routers/me.py``'s own docstring states the reason a suspended account is
admitted to this route at all rather than rejected alongside every other
authorized route: "a suspended caller needs to be able to tell it is
suspended, not receive a second, differently shaped 401 for asking." Before
``MeResponse`` carried a ``suspended`` field, that admission fulfilled none of
that rationale — the response body a suspended caller received was
byte-identical to an active caller's, so being let in bought it nothing it
could act on. This file is the reproduction: a suspended account calling
``GET /v1/me`` must see ``suspended: true`` and not learn its own state some
other way (a 401, a missing field, a body indistinguishable from an active
caller's).

Deliberately its own file rather than an addition to ``tests/contract/test_me.py``:
this track owns ``routers/me.py`` and this new test file, not the pre-existing
one another track's fixtures might still be touching. Self-contained for the
same reason ``test_me.py`` gives for being self-contained — the shared
fixtures under ``tests/integration/conftest.py`` are scoped to that directory.
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
    """One isolated tenant, cleaned up after the test."""
    tid = uuid.uuid4()
    slug = f"test-me-susp-{tid.hex[:12]}"
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
    """Suffix a subject so parallel test runs cannot collide (see test_me.py)."""
    return f"{name}-{uuid.uuid4().hex[:8]}"


def _make_user(
    engine: Engine, tenant_id: uuid.UUID, *, subject: str, suspended: bool = False
) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email, suspended) "
                "VALUES (:id, :tid, :sub, :email, :suspended)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "sub": subject,
                "email": f"{subject}@example.edu",
                "suspended": suspended,
            },
        )
    return user_id


def _grant(
    engine: Engine,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    path: str = "iawest",
    role: str = "admin",
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": path, "role": role},
        )


# ---------------------------------------------------------------------------
# The finding, reproduced and fixed: a suspended caller can tell it is suspended
# ---------------------------------------------------------------------------


def test_a_suspended_caller_is_admitted_and_told_it_is_suspended(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    """The core claim: admission without disclosure is not what the docstring promises.

    A suspended account still holding an admin membership is used deliberately
    — the same shape ``tests/authz/test_policy_matrix.py``'s ``suspended_admin``
    shape uses — so this is not merely "an account with nothing is denied
    everything"; it isolates suspension as the reason ``GET /v1/me`` still
    answers 200 while every *other* authorized route would answer 403 with
    ``principal_suspended`` for this same caller.
    """
    subject = _unique_subject("sub-suspended")
    user_id = _make_user(engine, tenant_id, subject=subject, suspended=True)
    _grant(engine, tenant_id, user_id, role="admin")
    client.verifier.register("tok-suspended", subject)  # type: ignore[attr-defined]

    response = client.get("/v1/me", headers={"Authorization": "Bearer tok-suspended"})

    assert response.status_code == 200, (
        "a suspended account must still be admitted here — routers/me.py's own "
        "docstring is explicit that authentication, not authorization, is the "
        "gate on this route"
    )
    body = response.json()
    assert body["user_id"] == str(user_id)
    assert body["suspended"] is True, (
        "the response is the only way a suspended caller can learn its own "
        "state from this route; admitting it and then answering with a body "
        "indistinguishable from an active caller's would leave that unfulfilled"
    )
    # Admission is not silence about everything else either — the membership
    # that suspension makes inert everywhere else is still reported honestly.
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "admin"


def test_an_active_caller_is_told_it_is_not_suspended(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    """The field means something in both directions, not just when it fires.

    Without this, ``suspended`` could be hardcoded ``True`` or otherwise
    disconnected from the account row and the test above would still pass.
    """
    subject = _unique_subject("sub-active")
    _make_user(engine, tenant_id, subject=subject, suspended=False)
    client.verifier.register("tok-active", subject)  # type: ignore[attr-defined]

    response = client.get("/v1/me", headers={"Authorization": "Bearer tok-active"})

    assert response.status_code == 200
    assert response.json()["suspended"] is False


def test_suspension_state_cannot_be_spoofed_by_the_caller(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
):
    """MM-A01 applies to ``suspended`` exactly as it does to every other field.

    A caller cannot un-suspend itself, or make an active account appear
    suspended, by supplying anything on the request — there is no path,
    query, or header parameter this route reads at all (see ``test_me.py``'s
    ``test_query_and_header_supplied_identity_is_ignored`` for the same
    property on the rest of the response).
    """
    subject = _unique_subject("sub-spoof")
    _make_user(engine, tenant_id, subject=subject, suspended=True)
    client.verifier.register("tok-spoof", subject)  # type: ignore[attr-defined]

    response = client.get(
        "/v1/me?suspended=false",
        headers={"Authorization": "Bearer tok-spoof", "X-Suspended": "false"},
    )

    assert response.json()["suspended"] is True
