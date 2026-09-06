"""The two matching-weight routes, over HTTP, against a real database.

What this file is for that the unit and integration files are not: it drives the
composed application — routing, dependency resolution, quota, the authorizer, the
session lifecycle and the error envelope — and checks the two things only that
composition can get wrong.

**The write actually commits.** ``get_session`` rolls back unconditionally on
exit, so a handler that returned ``200`` without calling ``session.commit()``
would be indistinguishable, from the response alone, from one that worked. Two
earlier tracks in this repository shipped exactly that. So the assertions below
read ``match_weight_setting`` on a separate connection, and the response is
checked only for what a client is entitled to see.

**A screen grants nothing.** The role cells are exercised exhaustively in
``tests/authz/test_policy_matrix.py``; what is checked here is the part the
matrix structurally cannot reach — that the routes really are behind the
authorizer, and that a sibling department's coordinator and an unauthenticated
caller meet a refusal from the running application rather than a rendered form.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.factor_registry import (
    CBA_PHYSICAL_MODEL,
    CBA_VIRTUAL_MODEL,
    REGISTRY_VERSION,
    normalize_weights,
)
from smartmatch_domain.factors.cba_semantic_topic import CBA_SEMANTIC_TOPIC_FACTOR_KEY
from smartmatch_domain.factors.industry_match import INDUSTRY_MATCH_FACTOR_KEY
from smartmatch_domain.factors.proximity import CBA_PROXIMITY_FACTOR_KEY
from smartmatch_domain.factors.role_match import ROLE_MATCH_FACTOR_KEY
from smartmatch_domain.weight_settings import applied_weights, configurable_factor_keys
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.weights"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: The authorizer passes no ``tenant_wide_roles``, so ordinary subtree
#: containment applies and a coordinator here must not reach the weights unit.
SIBLING_UNIT_PATH = "iawest.weightssibling"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM match_weight_setting LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def weights_context(
    engine: Engine,
) -> Iterator[tuple[TestClient, uuid.UUID, str, uuid.UUID, str]]:
    """One tenant, one authorized coordinator, and a sibling department's own.

    Both tokens are derived at runtime rather than written as literals: a fixture
    credential spelled out in a source file is a credential in a commit patch.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()

    people = {
        UNIT_PATH: (uuid.uuid4(), f"sub-weights-{uuid.uuid4().hex}", f"tok-{uuid.uuid4().hex}"),
        SIBLING_UNIT_PATH: (
            uuid.uuid4(),
            f"sub-weights-sib-{uuid.uuid4().hex}",
            f"tok-{uuid.uuid4().hex}",
        ),
    }

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-weights-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Weights"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        for path, (user_id, subject, _token) in people.items():
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
                    "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
                ),
                {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": path},
            )

    verifier = FixtureTokenVerifier()
    for _user_id, subject, token in people.values():
        verifier.register(token, subject)

    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, people[UNIT_PATH][2], tenant_id, people[SIBLING_UNIT_PATH][2]

    with engine.begin() as conn:
        # The revision log before the settings row, and both before
        # `user_account` and `org_unit`, which they reference ON DELETE RESTRICT.
        for table in (
            "match_weight_setting_revision",
            "match_weight_setting",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "idempotency_record",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _path(unit_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/matching-weights"


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _get(client: TestClient, unit_id, token: str | None):
    return client.get(_path(unit_id), headers=_headers(token))


def _patch(client: TestClient, unit_id, token: str | None, body: dict):
    return client.patch(_path(unit_id), json=body, headers=_headers(token))


def _stored(engine: Engine, tenant_id: uuid.UUID):
    """The settings row, read on a connection the request never touched."""
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM match_weight_setting WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).one_or_none()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_a_unit_that_has_configured_nothing_reads_as_the_registrys_weights(weights_context):
    """A 200 with an empty override map, not a 404.

    Nothing is missing: the unit scores on the approved weights, and ``modes``
    is where the response says so.
    """
    client, unit_id, token, _tenant_id, _sibling = weights_context

    response = _get(client, unit_id, token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["overrides"] == {}
    assert body["version"] is None, "a unit that never configured anything has no version"
    assert body["updated_by_user_id"] is None
    assert body["updated_at"] is None
    assert body["registry_version"] == REGISTRY_VERSION
    assert body["configurable_factors"] == list(configurable_factor_keys())

    by_mode = {mode["scoring_mode"]: mode for mode in body["modes"]}
    assert set(by_mode) == {CBA_PHYSICAL_MODEL.scoring_mode, CBA_VIRTUAL_MODEL.scoring_mode}
    assert by_mode[CBA_PHYSICAL_MODEL.scoring_mode]["weights"] == pytest.approx(
        dict(normalize_weights(model=CBA_PHYSICAL_MODEL))
    )
    # §11's exclusion is visible on the wire: a virtual run has no proximity
    # weight to render at all, rather than one rendered as zero.
    assert CBA_PROXIMITY_FACTOR_KEY not in by_mode[CBA_VIRTUAL_MODEL.scoring_mode]["weights"]


def test_the_response_reports_effective_weights_not_only_what_was_stored(weights_context, engine):
    """``overrides`` and ``modes`` are different facts, and both are answered."""
    client, unit_id, token, tenant_id, _sibling = weights_context
    proposal = {INDUSTRY_MATCH_FACTOR_KEY: 5.0}

    assert _patch(client, unit_id, token, {"overrides": proposal}).status_code == 200

    body = _get(client, unit_id, token).json()
    assert body["overrides"] == proposal, "only what the Connector set is reported as stored"

    physical = next(
        mode for mode in body["modes"] if mode["scoring_mode"] == CBA_PHYSICAL_MODEL.scoring_mode
    )
    assert physical["weights"] == pytest.approx(
        dict(applied_weights(proposal, model=CBA_PHYSICAL_MODEL))
    )
    assert sum(physical["weights"].values()) == pytest.approx(1.0)
    assert set(physical["weights"]) > set(proposal), (
        "the un-overridden factors must still be reported, at the registry's own weights"
    )
    assert _stored(engine, tenant_id).overrides == proposal


# ---------------------------------------------------------------------------
# Writing, and whether it actually lands
# ---------------------------------------------------------------------------


def test_a_change_is_committed_and_not_merely_reported(weights_context, engine):
    """The failure two earlier tracks shipped: a clean 2xx that stored nothing."""
    client, unit_id, token, tenant_id, _sibling = weights_context

    response = _patch(client, unit_id, token, {"overrides": {ROLE_MATCH_FACTOR_KEY: 4.0}})

    assert response.status_code == 200, response.text
    row = _stored(engine, tenant_id)
    assert row is not None, "the route answered 200 and the row is not in the table"
    assert row.overrides == {ROLE_MATCH_FACTOR_KEY: 4.0}
    assert row.version == 1
    assert response.json()["version"] == 1


def test_the_change_is_attributed_to_the_caller_not_to_the_body(weights_context, engine):
    """Audit comes from the verified principal; there is no author field to send."""
    client, unit_id, token, tenant_id, _sibling = weights_context

    _patch(client, unit_id, token, {"overrides": {ROLE_MATCH_FACTOR_KEY: 4.0}})

    with engine.connect() as conn:
        caller = conn.execute(
            text(
                "SELECT u.id FROM user_account u JOIN membership m "
                "ON m.user_id = u.id AND m.tenant_id = u.tenant_id "
                "WHERE u.tenant_id = :tid AND m.granted_path = CAST(:path AS ltree)"
            ),
            {"tid": tenant_id, "path": UNIT_PATH},
        ).scalar_one()

    assert _stored(engine, tenant_id).updated_by_user_id == caller


def test_each_change_appends_a_revision(weights_context, engine):
    client, unit_id, token, tenant_id, _sibling = weights_context

    _patch(client, unit_id, token, {"overrides": {ROLE_MATCH_FACTOR_KEY: 4.0}})
    _patch(client, unit_id, token, {"overrides": {INDUSTRY_MATCH_FACTOR_KEY: 2.0}})

    with engine.connect() as conn:
        versions = (
            conn.execute(
                text(
                    "SELECT version FROM match_weight_setting_revision "
                    "WHERE tenant_id = :tid ORDER BY version"
                ),
                {"tid": tenant_id},
            )
            .scalars()
            .all()
        )

    assert versions == [1, 2]


def test_an_empty_override_map_resets_the_unit(weights_context, engine):
    client, unit_id, token, tenant_id, _sibling = weights_context

    _patch(client, unit_id, token, {"overrides": {ROLE_MATCH_FACTOR_KEY: 4.0}})
    response = _patch(client, unit_id, token, {"overrides": {}})

    assert response.status_code == 200, response.text
    assert _stored(engine, tenant_id).overrides == {}
    assert response.json()["modes"][0]["weights"], "a reset unit still scores, on the registry's"


# ---------------------------------------------------------------------------
# Refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"industry": 1.0},
        {INDUSTRY_MATCH_FACTOR_KEY: -1.0},
        {
            INDUSTRY_MATCH_FACTOR_KEY: 0.0,
            ROLE_MATCH_FACTOR_KEY: 0.0,
            CBA_SEMANTIC_TOPIC_FACTOR_KEY: 0.0,
            CBA_PROXIMITY_FACTOR_KEY: 0.0,
        },
    ],
    ids=["unknown-factor", "negative", "zero-total"],
)
def test_an_inadmissible_proposal_is_refused_and_stores_nothing(weights_context, engine, overrides):
    """422 in this API's own envelope, and the table is untouched.

    The refusal matters less than the second half: a proposal normalized into
    something plausible would have produced a 200 and a weighting nobody asked
    for.
    """
    client, unit_id, token, tenant_id, _sibling = weights_context

    response = _patch(client, unit_id, token, {"overrides": overrides})

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_matching_weights"
    assert _stored(engine, tenant_id) is None


def test_a_stale_expected_version_is_a_conflict(weights_context, engine):
    client, unit_id, token, tenant_id, _sibling = weights_context

    _patch(client, unit_id, token, {"overrides": {ROLE_MATCH_FACTOR_KEY: 4.0}})
    response = _patch(
        client,
        unit_id,
        token,
        {"overrides": {INDUSTRY_MATCH_FACTOR_KEY: 9.0}, "expected_version": 1},
    )
    assert response.status_code == 200, "the current version is not stale"

    stale = _patch(
        client,
        unit_id,
        token,
        {"overrides": {INDUSTRY_MATCH_FACTOR_KEY: 1.0}, "expected_version": 1},
    )

    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "matching_weights_stale"
    assert _stored(engine, tenant_id).overrides == {INDUSTRY_MATCH_FACTOR_KEY: 9.0}


# ---------------------------------------------------------------------------
# A screen grants nothing
# ---------------------------------------------------------------------------


def test_an_unauthenticated_caller_reaches_neither_route(weights_context):
    client, unit_id, _token, _tenant_id, _sibling = weights_context

    assert _get(client, unit_id, None).status_code == 401
    assert _patch(client, unit_id, None, {"overrides": {}}).status_code == 401


def test_a_sibling_departments_coordinator_reaches_neither_route(weights_context, engine):
    """Containment, over HTTP. The role is right and the path is not.

    Asserted on both routes and against the table, because the interesting
    failure is not a wrong status code — it is a 403 on the read and a silent
    write on the change.
    """
    client, unit_id, _token, tenant_id, sibling_token = weights_context

    assert _get(client, unit_id, sibling_token).status_code == 403
    assert (
        _patch(client, unit_id, sibling_token, {"overrides": {ROLE_MATCH_FACTOR_KEY: 4.0}})
    ).status_code == 403
    assert _stored(engine, tenant_id) is None


def test_a_unit_in_another_tenant_is_a_404_rather_than_a_403(weights_context):
    """A 403 would confirm that the id names something real."""
    client, _unit_id, token, _tenant_id, _sibling = weights_context

    assert _get(client, uuid.uuid4(), token).status_code == 404
