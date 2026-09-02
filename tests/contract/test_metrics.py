"""HTTP contracts for accountable metrics and same-query drill-downs.

The load-bearing test writes real ``review_item`` rows. It then compares the
aggregate returned by the collection route with the number of rows returned by
the drill-down route, exercising the storage query rather than a fake adapter.
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
UNIT_PATH = "iawest.metrics"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """Return a live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM review_item LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def metric_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, str, uuid.UUID]]:
    """Create one authorized unit and the minimum import ancestry for rows."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    job_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    subject = f"sub-metrics-{uuid.uuid4().hex}"
    token = f"tok-metrics-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-metrics-{tenant_id.hex[:12]}"},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Metrics')"
            ),
            {"id": unit_id, "tid": tenant_id, "path": UNIT_PATH},
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
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )
        conn.execute(
            text(
                "INSERT INTO job "
                "(id, tenant_id, command_type, status, actor_id, owning_unit_id, payload) "
                "VALUES (:id, :tid, 'import.create', 'succeeded', :actor, :unit, '{}'::jsonb)"
            ),
            {
                "id": job_id,
                "tid": tenant_id,
                "actor": user_id,
                "unit": unit_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO import_batch "
                "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
                "VALUES (:id, :tid, :unit, :job, 'professionals', 3, false)"
            ),
            {"id": batch_id, "tid": tenant_id, "unit": unit_id, "job": job_id},
        )
        for row_index, status in enumerate(("pending", "accepted", "pending")):
            conn.execute(
                text(
                    "INSERT INTO review_item "
                    "(id, tenant_id, import_batch_id, row_index, row_data, status) "
                    "VALUES (:id, :tid, :batch, :idx, CAST(:data AS jsonb), :status)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "batch": batch_id,
                    "idx": row_index,
                    "data": f'{{"full_name": "Person {row_index}"}}',
                    "status": status,
                },
            )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, token, tenant_id

    with engine.begin() as conn:
        for table in (
            "review_item",
            "import_batch",
            "job_event",
            "outbox_record",
            "redrive_record",
            "job",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "tenant_budget",
            "concurrency_lease",
            "idempotency_record",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _get(client: TestClient, path: str, token: str):
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


def _register_principal(
    engine: Engine,
    client: TestClient,
    tenant_id: uuid.UUID,
    *,
    role: str | None,
    resource_grant_unit_id: uuid.UUID | None = None,
) -> str:
    """Create one more user in ``tenant_id`` and return a bearer token for it.

    ``role`` is ``None`` for a principal that holds no membership at all — the
    bare-``resource_grant`` shape the ratified metrics authorization decision
    (§4) says must be refused for aggregates. ``resource_grant_unit_id`` adds
    an explicit ``allow`` grant on that unit; the S-007 rule (pinned in
    ``tests/authz/test_policy_matrix.py``) is that a grant conveys reach, not
    membership, so it must not substitute for the role check either.

    Registers the new token on the same ``FixtureTokenVerifier`` instance the
    ``metric_context`` fixture already wired onto ``client.app.state`` — this
    does not create a second app or a second engine, only a second principal
    the existing client can authenticate as.
    """
    user_id = uuid.uuid4()
    subject = f"sub-metrics-{uuid.uuid4().hex}"
    token = f"tok-metrics-{uuid.uuid4().hex}"

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
                    "path": UNIT_PATH,
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

    verifier = client.app.state.token_verifier
    verifier.register(token, subject)
    return token


def test_pending_review_drill_down_count_equals_real_aggregate(metric_context) -> None:
    client, unit_id, token, _tenant_id = metric_context

    aggregate_response = _get(client, f"/v1/units/{unit_id}/metrics", token)
    assert aggregate_response.status_code == 200
    by_name = {item["name"]: item for item in aggregate_response.json()["metrics"]}
    aggregate = by_name["pending_review_items"]["value"]

    drill_response = _get(
        client,
        f"/v1/units/{unit_id}/metrics/pending_review_items/drill-down",
        token,
    )
    assert drill_response.status_code == 200
    drill_down = drill_response.json()

    assert aggregate == 2
    assert drill_down["aggregate_value"] == aggregate
    assert len(drill_down["rows"]) == aggregate
    assert {row["status"] for row in drill_down["rows"]} == {"pending"}


def test_pipeline_unknown_is_null_with_an_empty_drill_down(metric_context) -> None:
    client, unit_id, token, _tenant_id = metric_context

    aggregate_response = _get(client, f"/v1/units/{unit_id}/metrics", token)
    assert aggregate_response.status_code == 200
    by_name = {item["name"]: item for item in aggregate_response.json()["metrics"]}
    matched = by_name["pipeline_matched"]

    assert matched["value"] is None
    assert matched["value"] != 0
    assert "S12" in matched["unknown_reason"]

    drill_response = _get(
        client,
        f"/v1/units/{unit_id}/metrics/pipeline_matched/drill-down",
        token,
    )
    assert drill_response.status_code == 200
    drill_down = drill_response.json()
    assert drill_down["aggregate_value"] is None
    assert drill_down["rows"] == []
    assert "S12" in drill_down["unknown_reason"]


def test_a_student_reads_aggregates_but_is_refused_drill_down(
    metric_context, engine: Engine
) -> None:
    """The ratified decision's Option B split (§4), against a live database.

    Any active unit membership with a role reads aggregates — a ``student``
    role is not special-cased, it is simply *a* role. Drill-down is different:
    only ``admin``/``coordinator`` may see row-level data (``row_data`` may
    carry contact fields, P9 Gate B), so the same student is refused there,
    in the standard error envelope rather than an empty ``rows`` list — an
    empty list would be indistinguishable from "no pending rows exist",
    which is exactly the ambiguity ADR-0011 (unknown vs. zero) exists to rule
    out for aggregates and this task's negative coverage rules out for
    refusals too.
    """
    client, unit_id, _coordinator_token, tenant_id = metric_context
    student_token = _register_principal(engine, client, tenant_id, role="student")

    aggregate_response = _get(client, f"/v1/units/{unit_id}/metrics", student_token)
    assert aggregate_response.status_code == 200
    by_name = {item["name"]: item for item in aggregate_response.json()["metrics"]}
    assert by_name["pending_review_items"]["value"] == 2

    drill_response = _get(
        client,
        f"/v1/units/{unit_id}/metrics/pending_review_items/drill-down",
        student_token,
    )
    assert drill_response.status_code == 403
    body = drill_response.json()
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["details"]["reason"] == "no_grant"
    assert "rows" not in body


def test_a_bare_resource_grant_is_refused_aggregates(metric_context, engine: Engine) -> None:
    """The decision's negative, live: a bare `resource_grant` does not read aggregates.

    Mirrors ``tests/authz/test_policy_matrix.py``'s
    ``test_a_bare_resource_grant_never_satisfies_a_membership_only_operation``
    against the real HTTP surface and a real database, rather than the
    in-memory policy call: a principal with an explicit ``allow`` grant on
    this unit and no membership anywhere gets the standard error envelope
    naming ``resource_grant_lacks_membership``, not a 200 with metrics in it.
    """
    client, unit_id, _coordinator_token, tenant_id = metric_context
    grant_only_token = _register_principal(
        engine, client, tenant_id, role=None, resource_grant_unit_id=unit_id
    )

    response = _get(client, f"/v1/units/{unit_id}/metrics", grant_only_token)
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["details"]["reason"] == "resource_grant_lacks_membership"
    assert "metrics" not in body


def test_an_authorized_coordinator_keeps_equal_aggregate_and_drill_down_counts(
    metric_context,
) -> None:
    """Option B's admin/coordinator path is unchanged: today's behaviour, preserved.

    The ``metric_context`` fixture's own token already carries a
    ``coordinator`` membership at the owning unit, so this is the same
    equality ``test_pending_review_drill_down_count_equals_real_aggregate``
    already proves, restated here to name explicitly what this task's
    acceptance list (decision record §6) requires: authorization did not
    change the count for the population it continues to admit.
    """
    client, unit_id, coordinator_token, _tenant_id = metric_context

    aggregate_response = _get(client, f"/v1/units/{unit_id}/metrics", coordinator_token)
    assert aggregate_response.status_code == 200
    by_name = {item["name"]: item for item in aggregate_response.json()["metrics"]}
    aggregate = by_name["pending_review_items"]["value"]

    drill_response = _get(
        client,
        f"/v1/units/{unit_id}/metrics/pending_review_items/drill-down",
        coordinator_token,
    )
    assert drill_response.status_code == 200
    drill_down = drill_response.json()

    assert aggregate == 2
    assert drill_down["aggregate_value"] == aggregate
    assert len(drill_down["rows"]) == aggregate


def _insert_pending_review_item(engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> None:
    """Add one more pending review row under ``unit_id``'s existing batch."""
    with engine.begin() as conn:
        batch_id = conn.execute(
            text("SELECT id FROM import_batch WHERE tenant_id = :tid AND owning_unit_id = :unit"),
            {"tid": tenant_id, "unit": unit_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO review_item "
                "(id, tenant_id, import_batch_id, row_index, row_data, status) "
                "VALUES (:id, :tid, :batch, :idx, CAST(:data AS jsonb), 'pending')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "batch": batch_id,
                "idx": 99,
                "data": '{"full_name": "Extra Person"}',
            },
        )


@pytest.mark.parametrize(
    "path_suffix",
    ["metrics", "metrics/pending_review_items/drill-down"],
)
def test_200_carries_private_revalidation_headers(metric_context, path_suffix: str) -> None:
    client, unit_id, token, _tenant_id = metric_context

    response = _get(client, f"/v1/units/{unit_id}/{path_suffix}", token)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, max-age=0, must-revalidate"
    etag = response.headers["ETag"]
    assert etag.startswith('W/"')
    assert etag.endswith('"')


@pytest.mark.parametrize(
    "path_suffix",
    ["metrics", "metrics/pending_review_items/drill-down"],
)
def test_matching_if_none_match_yields_304_with_empty_body(
    metric_context, path_suffix: str
) -> None:
    client, unit_id, token, _tenant_id = metric_context
    path = f"/v1/units/{unit_id}/{path_suffix}"

    first = _get(client, path, token)
    etag = first.headers["ETag"]

    second = client.get(
        path,
        headers={"Authorization": f"Bearer {token}", "If-None-Match": etag},
    )

    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["ETag"] == etag
    assert second.headers["Cache-Control"] == "private, max-age=0, must-revalidate"


@pytest.mark.parametrize(
    "path_suffix",
    ["metrics", "metrics/pending_review_items/drill-down"],
)
def test_stale_if_none_match_yields_fresh_200_with_new_etag(
    metric_context, engine: Engine, path_suffix: str
) -> None:
    client, unit_id, token, tenant_id = metric_context
    path = f"/v1/units/{unit_id}/{path_suffix}"

    first = _get(client, path, token)
    old_etag = first.headers["ETag"]

    _insert_pending_review_item(engine, tenant_id, unit_id)

    second = client.get(
        path,
        headers={"Authorization": f"Bearer {token}", "If-None-Match": old_etag},
    )

    assert second.status_code == 200
    assert second.headers["ETag"] != old_etag
    if path_suffix == "metrics":
        by_name = {item["name"]: item for item in second.json()["metrics"]}
        assert by_name["pending_review_items"]["value"] == 3
    else:
        assert second.json()["aggregate_value"] == 3


def test_unauthorized_unit_never_short_circuits_to_304(metric_context) -> None:
    client, _unit_id, token, _tenant_id = metric_context
    bogus_unit_id = uuid.uuid4()

    first = client.get(
        f"/v1/units/{bogus_unit_id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 404

    replay = client.get(
        f"/v1/units/{bogus_unit_id}/metrics",
        headers={"Authorization": f"Bearer {token}", "If-None-Match": '"anything"'},
    )
    assert replay.status_code == 404

    wildcard_replay = client.get(
        f"/v1/units/{bogus_unit_id}/metrics",
        headers={"Authorization": f"Bearer {token}", "If-None-Match": "*"},
    )
    assert wildcard_replay.status_code == 404


def test_unknown_metric_stays_null_through_the_cache_layer(metric_context) -> None:
    client, unit_id, token, _tenant_id = metric_context

    response = _get(client, f"/v1/units/{unit_id}/metrics", token)
    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()["metrics"]}
    matched = by_name["pipeline_matched"]

    assert matched["value"] is None
    assert matched["value"] != 0
    assert matched["unknown_reason"] is not None
    assert "S12" in matched["unknown_reason"]
