"""Contract tests for ``GET /v1/me/portals`` under CBA role presentation.

The route already existed; what this file pins is the property the CBA pivot
puts under pressure. Renaming what a portal is *called* is a presentation
change, and a presentation change must not become an authorization change —
so these tests assert both halves at once: the visible labels are the CBA
personas, the stored ``membership.role`` the server echoes back is unchanged,
and a listed portal still opens nothing the policy would refuse.

What this file additionally pins, since the CBA pivot merged the connector
persona into one shell: ``coordinator`` and ``admin`` open the **same** portal,
an account holding both gets **one** descriptor for it, and that descriptor is
byte-for-byte identical whichever order the two ``membership`` rows were
inserted in. The order matters because nothing guarantees one —
``smartmatch_persistence.principals`` loads memberships with no ``ORDER BY`` —
so "it worked when I tried it" is not evidence, and both orders are seeded and
compared here instead.

The merge also must not overstate reach. A descriptor carries one winning
``role``, so each unit additionally carries the roles granted **over that
unit**: an account that is ``coordinator`` over one subtree and ``admin`` over
another must not have the ``admin`` grant smeared across the coordinator-only
unit, or the UI offers an action the route then refuses.

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
        ("coordinator", "coordinator", "Connector Dashboard"),
        # One persona, one shell: `admin` opens the connector portal under the
        # connector's own name. Administration is a section inside it, revealed
        # by the role on `GET /v1/me`, not a portal with a name of its own.
        ("admin", "coordinator", "Connector Dashboard"),
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
    assert descriptor["roles"] == [role]
    assert descriptor["org_unit_path"] == UNIT_PATH
    assert descriptor["default_unit_id"] is not None
    # Per-unit provenance, even in the single-membership case: the unit is
    # reached by exactly the role that was granted over it.
    assert [unit["roles"] for unit in descriptor["units"]] == [[role]]


def test_no_visible_label_carries_ia_west_or_chapter_wording(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """Customer §4: the legacy institutional wording is gone from the wire."""
    for role in ("student", "volunteer", "coordinator", "admin"):
        body = _portals(client, engine, tenant_id, role=role, name=f"sub-wording-{role}")
        shown = body["portals"][0]["display_name"].lower()
        for banned in ("ia west", "iawest", "insights association", "chapter", "volunteer"):
            assert banned not in shown, f"{role} portal is still labelled {shown!r}"


def test_the_portal_ids_and_home_paths_are_the_pinned_ones(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """Where each stored role lands, pinned as literals.

    Three of the four are unchanged. ``admin`` moved, once, on purpose — see
    the module docstring — and it is written out here rather than derived so
    that moving it again has to come through this line.
    """
    expected = {
        "student": "/student-portal",
        "volunteer": "/volunteer-portal",
        "coordinator": "/coordinator-portal",
        # Changed deliberately from `/dashboard`: the administration surface is
        # no longer a shell of its own to land in.
        "admin": "/coordinator-portal",
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


# ---------------------------------------------------------------------------
# 4. One persona, one shell: the coordinator/admin merge
# ---------------------------------------------------------------------------


def _portals_for_roles(
    client: TestClient,
    engine: Engine,
    tenant_id: uuid.UUID,
    *,
    name: str,
    grants: list[tuple[str, str]],
) -> dict:
    """One account holding every ``(role, path)`` in ``grants``, in that order.

    The insertion order is the caller's, which is the whole point: two callers
    differing only in that order must get the same response.
    """
    subject = _unique_subject(name)
    user_id = _make_user(engine, tenant_id, subject=subject)
    for role, path in grants:
        _grant(engine, tenant_id, user_id, role=role, path=path)
    token = f"tok-{subject}"
    client.verifier.register(token, subject)  # type: ignore[attr-defined]
    response = client.get("/v1/me/portals", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


def test_an_account_holding_coordinator_and_admin_gets_one_connector_descriptor(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """The deliverable: one persona, one shell, one entry in the list.

    Before the merge this account received two descriptors — ``coordinator``
    at ``/coordinator-portal`` and ``admin`` at ``/dashboard`` — and landed in
    whichever the database returned first.
    """
    body = _portals_for_roles(
        client,
        engine,
        tenant_id,
        name="sub-both",
        grants=[("coordinator", UNIT_PATH), ("admin", UNIT_PATH)],
    )

    assert [entry["portal"] for entry in body["portals"]] == ["coordinator"]
    assert body["default_portal"] == "coordinator"
    descriptor = body["portals"][0]
    assert descriptor["home_path"] == "/coordinator-portal"
    assert descriptor["display_name"] == "Connector Dashboard"
    # `role` is the highest held, by reach; `roles` is what was actually held,
    # which is the part a single winner cannot express.
    assert descriptor["role"] == "admin"
    assert descriptor["roles"] == ["admin", "coordinator"]
    # Both memberships cover the same path, so the unit carries both.
    assert [unit["roles"] for unit in descriptor["units"]] == [["admin", "coordinator"]]


def test_the_merged_descriptor_is_identical_in_both_insertion_orders(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """Membership rows arrive in no defined order, so neither may the answer.

    ``PrincipalRepository`` issues no ``ORDER BY`` when it loads memberships.
    An account whose landing depended on which row came back first is the
    landing bug in its purest form, and it reproduces intermittently — which
    is why the two orders are compared as whole JSON rather than spot-checked.
    """
    coordinator_first = _portals_for_roles(
        client,
        engine,
        tenant_id,
        name="sub-order-a",
        grants=[("coordinator", UNIT_PATH), ("admin", UNIT_PATH)],
    )
    admin_first = _portals_for_roles(
        client,
        engine,
        tenant_id,
        name="sub-order-b",
        grants=[("admin", UNIT_PATH), ("coordinator", UNIT_PATH)],
    )

    assert coordinator_first == admin_first


def test_a_unit_reports_the_roles_granted_over_that_unit_not_the_portals(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """The merge must not smear the stronger grant over the weaker unit.

    ``admin`` is tenant-wide for aggregates and ``coordinator`` is
    subtree-scoped (``smartmatch_authz.policy``). An account holding them over
    *different* subtrees opens one shell and has genuinely different reach in
    each, so the portal-level winner cannot be the whole answer: a unit
    labelled ``admin`` that only a ``coordinator`` row covers would have the UI
    offer an action every route then refuses.

    The extra org unit needs no cleanup of its own: the ``tenant_id`` fixture
    is per-test and removes every row it owns.
    """
    other_path = f"{UNIT_PATH}.branch"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'program', :name)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "path": other_path, "name": "Branch"},
        )

    body = _portals_for_roles(
        client,
        engine,
        tenant_id,
        name="sub-split",
        # `coordinator` over the branch only; `admin` over the branch's parent,
        # which therefore also covers the branch.
        grants=[("coordinator", other_path), ("admin", UNIT_PATH)],
    )

    assert [entry["portal"] for entry in body["portals"]] == ["coordinator"]
    descriptor = body["portals"][0]
    assert descriptor["roles"] == ["admin", "coordinator"]
    by_path = {unit["path"]: unit["roles"] for unit in descriptor["units"]}
    # The root is covered by the admin grant alone...
    assert by_path[UNIT_PATH] == ["admin"]
    # ...and the branch by both, because the admin grant's subtree contains it.
    assert by_path[other_path] == ["admin", "coordinator"]
    # Ancestors precede descendants, and `default_unit_id` names the first.
    assert [unit["path"] for unit in descriptor["units"]] == [UNIT_PATH, other_path]
    assert descriptor["default_unit_id"] == next(
        unit["unit_id"] for unit in descriptor["units"] if unit["path"] == UNIT_PATH
    )


def test_a_coordinator_only_account_is_never_labelled_an_administrator(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """The merge gave a shell away; it must not give a role away with it.

    The connector portal is now reachable by two roles, so this is the check
    that ``roles`` reports what the account holds rather than what the portal
    can be opened by — the difference between "you are in the connector shell"
    and "you are an administrator".
    """
    body = _portals(client, engine, tenant_id, role="coordinator", name="sub-plain-coord")

    descriptor = body["portals"][0]
    assert descriptor["roles"] == ["coordinator"]
    assert "admin" not in descriptor["roles"]
    assert all("admin" not in unit["roles"] for unit in descriptor["units"])


def test_holding_every_role_lists_the_three_portals_in_a_fixed_order(
    client: TestClient, engine: Engine, tenant_id: uuid.UUID
) -> None:
    """Four stored roles, three shells, one fixed order — and a stable default.

    Seeded in an order that matches neither the output order nor role
    precedence, so a response that merely echoed insertion order would fail.
    """
    body = _portals_for_roles(
        client,
        engine,
        tenant_id,
        name="sub-all",
        grants=[
            ("student", UNIT_PATH),
            ("admin", UNIT_PATH),
            ("volunteer", UNIT_PATH),
            ("coordinator", UNIT_PATH),
        ],
    )

    assert [entry["portal"] for entry in body["portals"]] == [
        "coordinator",
        "volunteer",
        "student",
    ]
    assert body["default_portal"] == "coordinator"
