"""HTTP contracts for the Event Host's organization and the Connector's directory.

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
all three operations and needs no database to run it. What this file adds is the
part that only exists over HTTP, which on this surface is most of the contract:

* **Self-scope is a row question, not a principal question.** ``evaluate``
  reasons about principals and paths; it cannot express "the organization whose
  member row carries this caller's own id". That predicate is asserted here —
  including the 404 a host gets when their one organization files into a
  *different* unit, which is indistinguishable from having none on purpose.
* **Self-asserted membership.** Every member row this release can write carries
  ``granted_by_user_id IS NULL``, and the response says so through
  ``self_asserted``. Joining somebody else's organization is a membership grant
  nothing here can make, so a colliding folded name is ``409
  host_organization_name_taken`` and an organization in another unit is ``409
  host_organization_unit_conflict`` rather than a silent re-homing.
* **The directory is the Connector's**, disjoint from the host routes: a host
  is refused it, a coordinator is refused the host routes, and the listing is
  scoped to its unit and capped the same way the request queue is.

``tests/integration/test_host_organization_migration.py`` owns what migration
``0036`` does to the rows. Nothing here re-asserts that; what it asserts is
that the responses describe those rows rather than the request body, and that
owner decision 4 holds end to end — an organization is a description a host
typed, never a permit.

Structured like ``tests/contract/test_speaker_requests_api.py`` and for its
reasons: real ``tenant``/``org_unit``/``user_account``/``membership`` rows, a
``FixtureTokenVerifier``, marked ``integration``, skipping cleanly when no
database is reachable.
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

UNIT_PATH = "iawest.hosts"
#: A second department in the same tenant. None of the three routes passes
#: ``tenant_wide_roles``, so ordinary subtree containment applies and an actor
#: here must not reach the host unit — while a membership at ``iawest`` covers
#: both, which is how one host comes to own an organization in the *wrong*
#: unit for the conflict and cross-unit assertions.
SIBLING_UNIT_PATH = "iawest.hostssibling"
#: The ancestor both units sit under. A membership granted here reaches either
#: — needed by the host whose organization files into the sibling.
TENANT_ROOT_PATH = "iawest"

ORGANIZATION = {
    "name": "Accounting Society",
    "department": "College of Business",
    "default_location": "Bldg 42, Room 7",
    "logistics_contact": "Ask for Priya at the front desk",
}


def _body(**overrides) -> dict[str, object]:
    """A complete organization description. Overrides replace whole fields."""
    body: dict[str, object] = dict(ORGANIZATION)
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM host_organization LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def organization_context(
    engine: Engine,
) -> Iterator[tuple[TestClient, uuid.UUID, uuid.UUID, str, uuid.UUID]]:
    """One tenant, one unit, one sibling unit, and an Event Host in the unit.

    Yields ``(client, unit_id, sibling_unit_id, host_token, tenant_id)``. The
    default principal is a ``volunteer`` — the stored role
    ``smartmatch_domain.role_presentation`` maps onto the **Event Host**
    persona — because the own-organization routes exist for that caller and
    nobody else. A fixture that defaulted to a coordinator would let a route
    that quietly dropped ``volunteer`` from its role set pass every test but
    one.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    subject = f"sub-hostorg-{uuid.uuid4().hex}"
    token = f"tok-hostorg-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-hostorg-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Hosts"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Hosts Sibling"),
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
            {
                "id": user_id,
                "tid": tenant_id,
                "subject": subject,
                "email": f"{subject}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'volunteer')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, sibling_unit_id, token, tenant_id

    with engine.begin() as conn:
        # Delete order is foreign-key order: event references the organization
        # RESTRICT, member rows reference both the organization and the
        # account, and the account references nothing below it.
        for table in (
            "speaker_request_classification",
            "event_tag",
            "event",
            "host_organization_member",
            "host_organization",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _get(client: TestClient, path: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.get(path, headers=headers)


def _put(client: TestClient, path: str, token: str | None, body: dict[str, object]):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.put(path, json=body, headers=headers)


def _own_path(unit_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/host/organization"


def _directory_path(unit_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/host-organizations"


def _register_principal(
    engine: Engine,
    client: TestClient,
    tenant_id: uuid.UUID,
    *,
    role: str | None,
    membership_path: str = UNIT_PATH,
    resource_grant_unit_id: uuid.UUID | None = None,
) -> str:
    """Create one more principal in ``tenant_id`` and return a bearer token.

    The same shape ``tests/contract/test_speaker_requests_api.py`` and
    ``tests/contract/test_events_api.py`` use, and deliberately so: the
    interesting variation between these tests is the principal, and a second
    way of building one would make three contract files disagree about what "a
    coordinator" is. ``role=None`` builds the bare-``resource_grant`` shape
    S-007 says a role-gated operation must refuse.
    """
    user_id = uuid.uuid4()
    subject = f"sub-hostorg-{uuid.uuid4().hex}"
    token = f"tok-hostorg-{uuid.uuid4().hex}"

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
        if resource_grant_unit_id is not None:
            conn.execute(
                text(
                    "INSERT INTO resource_grant "
                    "(id, tenant_id, user_id, resource_type, resource_id, effect) "
                    "VALUES (:id, :tid, :uid, 'org_unit', :rid, 'allow')"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "uid": user_id,
                    "rid": resource_grant_unit_id,
                },
            )

    client.app.state.token_verifier.register(token, subject)
    return token


def _membership_row(engine: Engine, tenant_id: uuid.UUID, organization_id: str) -> dict:
    """The member row behind an organization id, read straight off the table."""
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT user_id, granted_by_user_id, created_at "
                    "FROM host_organization_member "
                    "WHERE tenant_id = :tid AND organization_id = :oid"
                ),
                {"tid": tenant_id, "oid": organization_id},
            )
            .mappings()
            .all()
        )
    assert len(row) == 1, f"expected exactly one member row, found {len(row)}"
    return dict(row[0])


# ---------------------------------------------------------------------------
# The host's own organization — GET and PUT /v1/units/{unit_id}/host/organization
# ---------------------------------------------------------------------------


def test_a_host_with_no_organization_gets_a_404(organization_context) -> None:
    """``host_organization_not_found`` is the absence of the resource, as a 404."""
    client, unit_id, _, host, _ = organization_context

    response = _get(client, _own_path(unit_id), host)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "host_organization_not_found"


def test_a_host_describes_their_organization_and_reads_it_back(organization_context) -> None:
    """``201`` on the first PUT, and the response describes the row not the body.

    ``member_count``, ``self_asserted`` and ``member_since`` are the tell:
    nothing in the request could produce them.
    """
    client, unit_id, _, host, _ = organization_context

    created = _put(client, _own_path(unit_id), host, _body())

    assert created.status_code == 201
    body = created.json()
    organization = body["organization"]
    assert organization["unit_id"] == str(unit_id)
    assert organization["name"] == ORGANIZATION["name"]
    assert organization["department"] == ORGANIZATION["department"]
    assert organization["default_location"] == ORGANIZATION["default_location"]
    assert organization["logistics_contact"] == ORGANIZATION["logistics_contact"]
    assert organization["member_count"] == 1
    assert body["self_asserted"] is True
    assert body["member_since"] is not None

    read_back = _get(client, _own_path(unit_id), host)
    assert read_back.status_code == 200
    assert read_back.json() == body


def test_the_membership_is_self_asserted_in_the_row_not_only_the_response(
    engine: Engine, organization_context
) -> None:
    """``granted_by_user_id IS NULL`` is where the distinction lives (ADR-0011).

    The response's ``self_asserted`` is derived from that column rather than
    stored, so this asserts the column itself: the day a coordinator can grant
    membership, a granted row will name them, and a fixture that only ever
    checked the boolean could not tell the two populations apart.
    """
    client, unit_id, _, host, tenant_id = organization_context

    created = _put(client, _own_path(unit_id), host, _body())
    assert created.status_code == 201

    member = _membership_row(engine, tenant_id, created.json()["organization"]["organization_id"])
    assert member["granted_by_user_id"] is None


def test_a_second_put_updates_in_place_and_answers_200(organization_context) -> None:
    """Re-describing your club is not re-joining it.

    The status code is how the caller learns which happened; the member row is
    untouched — ``member_since`` is the first call's, and ``member_count``
    stays 1 because an update writes no second membership.
    """
    client, unit_id, _, host, _ = organization_context
    first = _put(client, _own_path(unit_id), host, _body())
    assert first.status_code == 201

    updated = _put(
        client,
        _own_path(unit_id),
        host,
        _body(name="Accounting and Finance Society", default_location="Bldg 9"),
    )

    assert updated.status_code == 200
    body = updated.json()
    assert (
        body["organization"]["organization_id"] == first.json()["organization"]["organization_id"]
    )
    assert body["organization"]["name"] == "Accounting and Finance Society"
    assert body["organization"]["default_location"] == "Bldg 9"
    assert body["organization"]["member_count"] == 1
    assert body["self_asserted"] is True
    assert body["member_since"] == first.json()["member_since"]


def test_fields_are_stored_trimmed_and_an_all_whitespace_field_is_absent(
    organization_context,
) -> None:
    """The repository's own rule, over HTTP: ``"  "`` is "they did not say"."""
    client, unit_id, _, host, _ = organization_context

    created = _put(
        client,
        _own_path(unit_id),
        host,
        _body(name="  Accounting Society  ", department="   ", logistics_contact=""),
    )

    assert created.status_code == 201
    organization = created.json()["organization"]
    assert organization["name"] == "Accounting Society"
    assert organization["department"] is None
    assert organization["logistics_contact"] is None


def test_a_whitespace_only_name_is_a_422_not_a_false_409(organization_context) -> None:
    """``min_length`` counts characters, so a blank-in-substance name gets here.

    Without the model's own refusal this fell through to
    ``ck_host_organization_name_shape`` and the ``IntegrityError`` catch
    answered ``host_organization_name_taken`` — which claims another host
    holds a name nobody holds. A malformed request is a 422.
    """
    client, unit_id, _, host, _ = organization_context

    response = _put(client, _own_path(unit_id), host, _body(name="   "))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_name_above_the_stored_limit_is_refused_by_the_schema(organization_context) -> None:
    """``max_length=200`` is the same number ``ck_host_organization_name_shape`` holds."""
    client, unit_id, _, host, _ = organization_context

    response = _put(client, _own_path(unit_id), host, _body(name="x" * 201))

    assert response.status_code == 422


def test_a_body_naming_no_name_is_refused_by_the_schema(organization_context) -> None:
    client, unit_id, _, host, _ = organization_context

    response = _put(client, _own_path(unit_id), host, {"department": "CBA"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The two 409s — distinguishable, and neither is a case to guess through
# ---------------------------------------------------------------------------


def test_a_folded_name_collision_is_name_taken(engine: Engine, organization_context) -> None:
    """``uq_host_organization_unit_name``: joining is a grant nobody can make.

    Two hosts describing one club in one department would split its requests
    with nothing to say they belong together, and adding the second caller to
    the first's row would be a membership grant — so the second caller gets a
    409 naming the conflict, case-folded because the constraint is.
    """
    client, unit_id, _, host_a, tenant_id = organization_context
    host_b = _register_principal(engine, client, tenant_id, role="volunteer")
    assert _put(client, _own_path(unit_id), host_a, _body()).status_code == 201

    refused = _put(client, _own_path(unit_id), host_b, _body(name="ACCOUNTING SOCIETY"))

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "host_organization_name_taken"

    # And a distinguishing name still succeeds — the constraint is on the
    # folded name, not on how many organizations a unit may hold.
    other = _put(client, _own_path(unit_id), host_b, _body(name="Finance Club"))
    assert other.status_code == 201


def test_an_organization_in_another_unit_is_a_unit_conflict(
    engine: Engine, organization_context
) -> None:
    """``host_organization_unit_conflict``: one organization per account, full stop.

    A membership at the tenant root reaches both departments, so this host can
    write in either — and the second write is still refused, because moving
    the organization would move every other member with it.
    """
    client, unit_id, sibling_unit_id, _, tenant_id = organization_context
    roving = _register_principal(
        engine, client, tenant_id, role="volunteer", membership_path=TENANT_ROOT_PATH
    )
    created = _put(client, _own_path(sibling_unit_id), roving, _body())
    assert created.status_code == 201

    refused = _put(client, _own_path(unit_id), roving, _body(name="Finance Club"))

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "host_organization_unit_conflict"

    # And the organization still answers where it was filed — the conflict
    # moved nothing.
    there = _get(client, _own_path(sibling_unit_id), roving)
    assert there.status_code == 200
    assert there.json()["organization"]["name"] == ORGANIZATION["name"]


def test_a_host_whose_organization_is_elsewhere_gets_the_plain_404(
    engine: Engine, organization_context
) -> None:
    """No organization *in this unit* gets the same 404 as none at all.

    ``evaluate`` cannot express it — the permit is against the unit in the
    path, and the membership is real — so the row's own ``unit_id`` answers.
    Saying "you have one, elsewhere" from a route authorized against this unit
    would report a row in a department nobody authorized the caller against.
    """
    client, unit_id, sibling_unit_id, _, tenant_id = organization_context
    roving = _register_principal(
        engine, client, tenant_id, role="volunteer", membership_path=TENANT_ROOT_PATH
    )
    assert _put(client, _own_path(sibling_unit_id), roving, _body()).status_code == 201

    response = _get(client, _own_path(unit_id), roving)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "host_organization_not_found"


# ---------------------------------------------------------------------------
# Who may not use the host routes — the disjoint half of the role split
# ---------------------------------------------------------------------------


def test_a_coordinator_is_refused_the_host_routes(engine: Engine, organization_context) -> None:
    """They hold the directory, which is strictly wider; this door is narrower."""
    client, unit_id, _, _, tenant_id = organization_context
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")

    assert _get(client, _own_path(unit_id), coordinator).status_code == 403
    refused = _put(client, _own_path(unit_id), coordinator, _body())
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "forbidden"


def test_an_admin_is_refused_the_host_routes(engine: Engine, organization_context) -> None:
    client, unit_id, _, _, tenant_id = organization_context
    admin = _register_principal(engine, client, tenant_id, role="admin")

    assert _get(client, _own_path(unit_id), admin).status_code == 403
    assert _put(client, _own_path(unit_id), admin, _body()).status_code == 403


def test_a_student_is_refused_the_host_routes(engine: Engine, organization_context) -> None:
    """Customer §15 gives a Student browsing and feedback; they do not host."""
    client, unit_id, _, _, tenant_id = organization_context
    student = _register_principal(engine, client, tenant_id, role="student")

    assert _get(client, _own_path(unit_id), student).status_code == 403
    assert _put(client, _own_path(unit_id), student, _body()).status_code == 403


def test_a_bare_resource_grant_is_refused_the_host_routes(
    engine: Engine, organization_context
) -> None:
    """S-007: a grant conveys reach, not authority."""
    client, unit_id, _, _, tenant_id = organization_context
    granted = _register_principal(
        engine, client, tenant_id, role=None, resource_grant_unit_id=unit_id
    )

    assert _get(client, _own_path(unit_id), granted).status_code == 403
    assert _put(client, _own_path(unit_id), granted, _body()).status_code == 403


def test_a_host_in_a_sibling_unit_is_refused(engine: Engine, organization_context) -> None:
    """Unit scoping is a path question, asked of the loaded row."""
    client, unit_id, _, _, tenant_id = organization_context
    sibling_host = _register_principal(
        engine, client, tenant_id, role="volunteer", membership_path=SIBLING_UNIT_PATH
    )

    assert _get(client, _own_path(unit_id), sibling_host).status_code == 403
    assert _put(client, _own_path(unit_id), sibling_host, _body()).status_code == 403


def test_the_host_routes_answer_404_for_a_unit_in_another_tenant(organization_context) -> None:
    """A 403 would confirm the id names something real in somebody else's tenant."""
    client, _, _, host, _ = organization_context

    assert _get(client, _own_path(uuid.uuid4()), host).status_code == 404
    assert _put(client, _own_path(uuid.uuid4()), host, _body()).status_code == 404


def test_an_unauthenticated_caller_is_refused_the_host_routes(organization_context) -> None:
    client, unit_id, _, _, _ = organization_context

    assert _get(client, _own_path(unit_id), None).status_code == 401
    assert _put(client, _own_path(unit_id), None, _body()).status_code == 401


def test_a_refused_write_leaves_no_row(engine: Engine, organization_context) -> None:
    """Authorization is reached before anything is written, asserted by reading back.

    A route that validated first and authorized second would still refuse —
    but only after doing work against the unit. This is the observable half of
    the ordering promise: the refused caller's organization does not exist.
    """
    client, unit_id, _, _, tenant_id = organization_context
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")
    refused = _put(client, _own_path(unit_id), coordinator, _body())
    assert refused.status_code == 403

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM host_organization WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()
    assert count == 0


# ---------------------------------------------------------------------------
# The Connector's directory — GET /v1/units/{unit_id}/host-organizations
# ---------------------------------------------------------------------------


def test_a_coordinator_reads_the_directory(engine: Engine, organization_context) -> None:
    """Customer §13's counterpart: who is asking, across the whole unit."""
    client, unit_id, _, host, tenant_id = organization_context
    _put(client, _own_path(unit_id), host, _body())
    host_b = _register_principal(engine, client, tenant_id, role="volunteer")
    _put(client, _own_path(unit_id), host_b, _body(name="Finance Club"))
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")

    response = _get(client, _directory_path(unit_id), coordinator)

    assert response.status_code == 200
    body = response.json()
    assert body["unit_id"] == str(unit_id)
    assert body["truncated"] is False
    # Folded-name order, the repository's documented sort.
    assert [item["name"] for item in body["organizations"]] == [
        "Accounting Society",
        "Finance Club",
    ]
    assert {item["member_count"] for item in body["organizations"]} == {1}


def test_the_directory_carries_no_member_list(engine: Engine, organization_context) -> None:
    """What a Connector learns: that organizations exist and what they say.

    Who belongs to one is a second question with a second answer, and this
    route does not answer it — asserted here by inserting a second member row
    no route could have written, and watching the count rise while no account
    identifier appears.
    """
    client, unit_id, _, host, tenant_id = organization_context
    created = _put(client, _own_path(unit_id), host, _body())
    organization_id = created.json()["organization"]["organization_id"]
    other_user_id = uuid.uuid4()
    subject = f"sub-hostorg-{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {
                "id": other_user_id,
                "tid": tenant_id,
                "subject": subject,
                "email": f"{subject}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO host_organization_member "
                "(organization_id, user_id, tenant_id, unit_id, granted_by_user_id) "
                "VALUES (:oid, :uid, :tid, :unit, NULL)"
            ),
            {"oid": organization_id, "uid": other_user_id, "tid": tenant_id, "unit": unit_id},
        )
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")

    body = _get(client, _directory_path(unit_id), coordinator).json()

    assert len(body["organizations"]) == 1
    entry = body["organizations"][0]
    assert entry["member_count"] == 2
    for key, value in entry.items():
        assert "member" not in key or key == "member_count"
        if isinstance(value, str):
            assert str(other_user_id) != value, (
                "a member's account id appeared in the directory entry. The "
                "directory says how many accounts belong, never which."
            )


def test_the_directory_is_scoped_to_its_unit(engine: Engine, organization_context) -> None:
    """An organization in one department is not a sibling's directory entry."""
    client, unit_id, sibling_unit_id, host, tenant_id = organization_context
    _put(client, _own_path(unit_id), host, _body())
    admin = _register_principal(
        engine, client, tenant_id, role="admin", membership_path=TENANT_ROOT_PATH
    )

    theirs = _get(client, _directory_path(unit_id), admin).json()
    siblings = _get(client, _directory_path(sibling_unit_id), admin).json()

    assert [item["name"] for item in theirs["organizations"]] == [ORGANIZATION["name"]]
    assert siblings["organizations"] == []
    assert siblings["truncated"] is False


def test_the_directory_reports_truncation(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, organization_context
) -> None:
    """``truncated`` is answered by the same query, exactly as the queue answers it.

    ``MAX_ROWS`` is patched down rather than PUTting 201 organizations over
    HTTP; the route reads ``MAX_ROWS + 1`` at call time, so patching the module
    global exercises the real branch.
    """
    from smartmatch_api.routers import host_organizations as module

    client, unit_id, _, host, tenant_id = organization_context
    host_b = _register_principal(engine, client, tenant_id, role="volunteer")
    _put(client, _own_path(unit_id), host, _body())
    _put(client, _own_path(unit_id), host_b, _body(name="Finance Club"))
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")

    monkeypatch.setattr(module, "MAX_ROWS", 1)
    body = _get(client, _directory_path(unit_id), coordinator).json()

    assert len(body["organizations"]) == 1
    assert body["truncated"] is True


def test_a_host_may_not_read_the_directory(organization_context) -> None:
    """The one cell where the directory refuses the caller the own-routes serve.

    The directory carries every host's organization in the unit; handing one
    host the others' is a widening no committed artifact supports.
    """
    client, unit_id, _, host, _ = organization_context
    _put(client, _own_path(unit_id), host, _body())

    response = _get(client, _directory_path(unit_id), host)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_a_student_may_not_read_the_directory(engine: Engine, organization_context) -> None:
    client, unit_id, _, _, tenant_id = organization_context
    student = _register_principal(engine, client, tenant_id, role="student")

    assert _get(client, _directory_path(unit_id), student).status_code == 403


def test_the_directory_answers_404_for_a_unit_in_another_tenant(
    engine: Engine, organization_context
) -> None:
    client, _, _, _, tenant_id = organization_context
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")

    assert _get(client, _directory_path(uuid.uuid4()), coordinator).status_code == 404


def test_an_unauthenticated_caller_may_not_read_the_directory(organization_context) -> None:
    client, unit_id, _, _, _ = organization_context

    assert _get(client, _directory_path(unit_id), None).status_code == 401
