"""The S12 funnel and Opportunities metrics, bound to storage (P8 card O3).

Card O2 (migration ``0011``) gave the five Pipeline metrics an evidence table
and card O3 (``services/api/smartmatch_api/routers/metrics.py``) bound
``pipeline_funnel_rows_v1`` and ``opportunities_rows_v1`` to it. This file
proves the two claims that binding makes, over the real HTTP surface and a
real database, rather than over the adapter functions in isolation:

* an **empty table measures 0**, not unknown -- the honest-unknown stub these
  two owning queries used to return is gone, and the difference between "no
  evidence source" and "a source that says zero" is the entire point of this
  card (see the module docstring of ``smartmatch_domain.metrics``);
* ADR-0011 rule 3, for every metric this card binds: the aggregate a caller
  sees on ``GET /metrics`` and the row count a caller sees on the matching
  ``drill-down`` route are the same number, because both come from the one
  query this file's ``_pipeline_funnel_rows_v1``/``_opportunities_rows_v1``
  adapters run.

The seeded-rows assertions are cross-checked against ``funnel_counts`` and
``funnel_rows`` from ``test_pipeline_record_constraints.py`` -- the same
predicate card O3's docstring says the adapter must use ("reached stage X" is
``<stage>_at IS NOT NULL``, ordered by ``matched_at, id``) -- imported rather
than restated, so a drift between the router and that spec shows up as a
failing assertion instead of two competing definitions of the same query.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")

from conftest import JOB_OWNING_UNIT_PATH, ensure_owning_unit, unique_subject
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, text
from test_pipeline_record_constraints import (
    STAGES,
    _insert_pipeline_record,
    _make_unit,
    funnel_counts,
    funnel_rows,
)

pytestmark = pytest.mark.integration

#: The stage-column -> canonical-name pairing this file checks the router
#: against. Written independently of
#: ``routers.metrics._PIPELINE_STAGE_COLUMNS`` -- importing that constant here
#: and asserting it equals itself would prove nothing about whether the
#: binding is *correct*, only that it is self-consistent.
_STAGE_METRIC_NAMES: dict[str, str] = {
    "matched_at": "pipeline_matched",
    "contacted_at": "pipeline_contacted",
    "confirmed_at": "pipeline_confirmed",
    "attended_at": "pipeline_attended",
    "member_inquiry_at": "pipeline_member_inquiry",
}

_ALL_STORAGE_BOUND_METRICS: tuple[str, ...] = (*_STAGE_METRIC_NAMES.values(), "opportunities")

#: A second unit, sibling to the tenant's ordinary job-owning unit. Named once
#: here so both the fixture and the isolation test agree on it.
_OTHER_UNIT_PATH = "iawest.metrics-storage-other"


@pytest.fixture(autouse=True)
def _clean_pipeline_and_attendance_tables(engine: Engine, tenant_id):
    """Delete this file's ``pipeline_record``/``attendance_record`` rows.

    Same arrangement, and the same reason, as
    ``test_pipeline_record_constraints.py``'s own cleanup fixture:
    ``conftest.py``'s ``_TENANT_SCOPED_TABLES`` does not include either table
    (nothing outside this file and that one references ``pipeline_record``
    yet), and both carry ``ON DELETE RESTRICT`` foreign keys back to
    ``org_unit`` and ``user_account`` -- rows left behind here would make the
    ``tenant_id`` fixture's own teardown fail. ``job``, by contrast, needs no
    matching cleanup: it is already in ``_TENANT_SCOPED_TABLES``, and
    ``import_batch``/``review_item`` cascade from it (``ON DELETE CASCADE``,
    migration ``0008``), so deleting the tenant's jobs clears this file's
    Opportunities rows too.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )


def _make_client(engine: Engine) -> TestClient:
    """A ``TestClient`` wired to a real session factory and a fixture verifier.

    Mirrors ``tests/contract/test_metrics.py``'s ``metric_context`` fixture:
    this file is deliberately not reusing that fixture, because it needs two
    *separately scoped* coordinators (one per unit) for the isolation
    assertion below, which that fixture's single-principal shape does not
    build.
    """
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = FixtureTokenVerifier()
    return client


def _register_coordinator(
    engine: Engine, client: TestClient, tenant_id: uuid.UUID, unit_path: str
) -> tuple[str, uuid.UUID]:
    """Create one coordinator membership rooted at ``unit_path``, and its token.

    Rooted exactly at ``unit_path`` -- not at the tenant root -- so this
    principal's reach is bounded to one unit's subtree, which is what makes
    the isolation test below meaningful: a coordinator who could reach both
    units would not distinguish "scoped correctly" from "scoped at all".
    """
    user_id = uuid.uuid4()
    subject = unique_subject(f"metrics-storage-{user_id.hex[:8]}")
    token = f"tok-metrics-storage-{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "sub": subject,
                "email": f"{user_id.hex[:8]}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": unit_path},
        )
    client.app.state.token_verifier.register(token, subject)
    return token, user_id


@dataclass(frozen=True, slots=True)
class _StorageBindingContext:
    """Two units in one tenant, each with a coordinator scoped to only it."""

    client: TestClient
    tenant_id: uuid.UUID
    mine: uuid.UUID
    theirs: uuid.UUID
    mine_token: str
    theirs_token: str
    mine_actor: uuid.UUID
    theirs_actor: uuid.UUID


@pytest.fixture
def storage_binding_context(engine: Engine, tenant_id) -> Iterator[_StorageBindingContext]:
    with engine.begin() as conn:
        mine = ensure_owning_unit(conn, tenant_id)
        theirs = _make_unit(conn, tenant_id, _OTHER_UNIT_PATH)

    client = _make_client(engine)
    mine_token, mine_actor = _register_coordinator(engine, client, tenant_id, JOB_OWNING_UNIT_PATH)
    theirs_token, theirs_actor = _register_coordinator(engine, client, tenant_id, _OTHER_UNIT_PATH)

    yield _StorageBindingContext(
        client=client,
        tenant_id=tenant_id,
        mine=mine,
        theirs=theirs,
        mine_token=mine_token,
        theirs_token=theirs_token,
        mine_actor=mine_actor,
        theirs_actor=theirs_actor,
    )


def _get(client: TestClient, path: str, token: str):
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


def _insert_review_item(
    conn,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    category: str | None,
    status: str = "accepted",
    row_index: int = 0,
    dataset: str = "events",
) -> uuid.UUID:
    """One job -> import_batch -> review_item chain, for the Opportunities binding.

    ``dataset`` defaults to ``"events"`` (the ratified dataset that carries
    ``"Category"``) but a test below sets it to something else on purpose:
    ``_opportunities_rows_v1`` must not filter on it (the router's own
    docstring argues why), and the only way to prove that is a row whose
    dataset name is not what a filter would expect.

    ``decided_at``/``decided_by`` (migration 0013) are set together whenever
    ``status`` is not ``"pending"`` -- ``ck_review_item_decision_evidence``
    requires exactly that biconditional, and ``actor_id`` stands in for the
    deciding coordinator since nothing in this file is testing *who* decided.
    """
    job_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    item_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job "
            "(id, tenant_id, command_type, status, actor_id, owning_unit_id, payload) "
            "VALUES (:id, :tid, 'import.create', 'succeeded', :actor, :unit, '{}'::jsonb)"
        ),
        {"id": job_id, "tid": tenant_id, "actor": actor_id, "unit": unit_id},
    )
    conn.execute(
        text(
            "INSERT INTO import_batch "
            "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
            "VALUES (:id, :tid, :unit, :job, :dataset, 1, false)"
        ),
        {"id": batch_id, "tid": tenant_id, "unit": unit_id, "job": job_id, "dataset": dataset},
    )
    row_data = {"category": category} if category is not None else {}
    decided = status != "pending"
    conn.execute(
        text(
            "INSERT INTO review_item "
            "(id, tenant_id, import_batch_id, row_index, row_data, status, "
            "decided_at, decided_by) "
            "VALUES (:id, :tid, :batch, :idx, CAST(:data AS jsonb), :status, "
            ":decided_at, :decided_by)"
        ),
        {
            "id": item_id,
            "tid": tenant_id,
            "batch": batch_id,
            "idx": row_index,
            "data": json.dumps(row_data),
            "status": status,
            "decided_at": datetime.now(UTC) if decided else None,
            "decided_by": actor_id if decided else None,
        },
    )
    return item_id


# ---------------------------------------------------------------------------
# An empty table measures 0, not unknown
# ---------------------------------------------------------------------------


def test_empty_storage_measures_zero_not_unknown(
    storage_binding_context: _StorageBindingContext,
) -> None:
    """No ``pipeline_record`` and no accepted ``review_item`` rows exist yet.

    Every one of the six metrics this card binds must answer a measured 0
    with no ``unknown_reason`` -- the claim the old honest-unknown stub could
    never make, and the whole reason this card exists.
    """
    ctx = storage_binding_context
    response = _get(ctx.client, f"/v1/units/{ctx.mine}/metrics", ctx.mine_token)
    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()["metrics"]}

    for name in _ALL_STORAGE_BOUND_METRICS:
        assert by_name[name]["value"] == 0, name
        assert by_name[name]["unknown_reason"] is None, name

        drill_response = _get(
            ctx.client, f"/v1/units/{ctx.mine}/metrics/{name}/drill-down", ctx.mine_token
        )
        assert drill_response.status_code == 200
        drill_down = drill_response.json()
        assert drill_down["aggregate_value"] == 0, name
        assert drill_down["rows"] == [], name
        assert drill_down["unknown_reason"] is None, name


# ---------------------------------------------------------------------------
# ADR-0011 rule 3: aggregate == drill-down, cross-checked against the spec
# ---------------------------------------------------------------------------


def test_pipeline_seeded_rows_aggregate_equals_drill_down_per_stage(
    storage_binding_context: _StorageBindingContext, engine: Engine
) -> None:
    """Five journeys stopping at five stages; every stage's number agrees twice over.

    Once between the HTTP aggregate and the HTTP drill-down (ADR-0011 rule 3
    at the API), and once between the HTTP aggregate and ``funnel_counts`` /
    ``funnel_rows`` (the router is measuring what card O3's own docstring
    says it must).
    """
    ctx = storage_binding_context
    with engine.begin() as conn:
        for stage in STAGES:
            _insert_pipeline_record(conn, ctx.tenant_id, reached=stage, owning_unit_id=ctx.mine)
        # A row in the other unit -- present so a query that forgot the
        # owning_unit_id filter would be caught by every assertion below,
        # not only by the dedicated isolation test.
        _insert_pipeline_record(
            conn, ctx.tenant_id, reached="member_inquiry_at", owning_unit_id=ctx.theirs
        )

    with engine.begin() as conn:
        expected_counts = funnel_counts(conn, ctx.tenant_id, ctx.mine)

    for stage, metric_name in _STAGE_METRIC_NAMES.items():
        aggregate_response = _get(ctx.client, f"/v1/units/{ctx.mine}/metrics", ctx.mine_token)
        assert aggregate_response.status_code == 200
        by_name = {item["name"]: item for item in aggregate_response.json()["metrics"]}
        value = by_name[metric_name]["value"]

        drill_response = _get(
            ctx.client, f"/v1/units/{ctx.mine}/metrics/{metric_name}/drill-down", ctx.mine_token
        )
        assert drill_response.status_code == 200
        drill_down = drill_response.json()

        assert value == expected_counts[stage[:-3]], metric_name
        assert drill_down["aggregate_value"] == value, metric_name
        assert len(drill_down["rows"]) == value, metric_name

        with engine.begin() as conn:
            expected_ids = {
                str(row_id) for row_id in funnel_rows(conn, ctx.tenant_id, ctx.mine, stage)
            }
        assert {row["id"] for row in drill_down["rows"]} == expected_ids, metric_name


def test_one_units_pipeline_funnel_does_not_count_another_units(
    storage_binding_context: _StorageBindingContext, engine: Engine
) -> None:
    """Two journeys, both reaching Attended, one per unit -- read back through two principals.

    Each coordinator is rooted at exactly one unit (see
    ``_register_coordinator``), so this is not only a storage-layer filter
    check: it proves the unit that owns a journey is the only one whose
    caller can see it, aggregate and drill-down alike.
    """
    ctx = storage_binding_context
    with engine.begin() as conn:
        _insert_pipeline_record(conn, ctx.tenant_id, reached="attended_at", owning_unit_id=ctx.mine)
        _insert_pipeline_record(
            conn, ctx.tenant_id, reached="attended_at", owning_unit_id=ctx.theirs
        )

    mine_response = _get(ctx.client, f"/v1/units/{ctx.mine}/metrics", ctx.mine_token)
    theirs_response = _get(ctx.client, f"/v1/units/{ctx.theirs}/metrics", ctx.theirs_token)
    mine_by_name = {item["name"]: item for item in mine_response.json()["metrics"]}
    theirs_by_name = {item["name"]: item for item in theirs_response.json()["metrics"]}

    assert mine_by_name["pipeline_attended"]["value"] == 1
    assert theirs_by_name["pipeline_attended"]["value"] == 1

    mine_drill = _get(
        ctx.client, f"/v1/units/{ctx.mine}/metrics/pipeline_attended/drill-down", ctx.mine_token
    )
    assert len(mine_drill.json()["rows"]) == 1


def test_opportunities_seeded_rows_aggregate_equals_drill_down_count(
    storage_binding_context: _StorageBindingContext, engine: Engine
) -> None:
    """Accepted in-list rows count; out-of-list/absent, pending, and another unit's rows do not.

    Also proves ``import_batch.dataset`` is not part of the filter: the
    ``"Datathon"`` row below is submitted under a dataset name
    (``"some-other-dataset"``) that names no real dataset, and it still
    counts, because only the category shape governs.
    """
    ctx = storage_binding_context
    with engine.begin() as conn:
        _insert_review_item(
            conn, ctx.tenant_id, ctx.mine, ctx.mine_actor, category="hackathon", row_index=0
        )
        _insert_review_item(
            conn,
            ctx.tenant_id,
            ctx.mine,
            ctx.mine_actor,
            category="Datathon",
            row_index=1,
            dataset="some-other-dataset",
        )
        _insert_review_item(
            conn,
            ctx.tenant_id,
            ctx.mine,
            ctx.mine_actor,
            category="raw unmapped label",
            row_index=2,
        )
        _insert_review_item(
            conn, ctx.tenant_id, ctx.mine, ctx.mine_actor, category=None, row_index=3
        )
        _insert_review_item(
            conn,
            ctx.tenant_id,
            ctx.mine,
            ctx.mine_actor,
            category="hackathon",
            status="pending",
            row_index=4,
        )
        # In-list, but owned by the other unit -- must not count toward `mine`.
        _insert_review_item(
            conn, ctx.tenant_id, ctx.theirs, ctx.theirs_actor, category="hackathon", row_index=0
        )

    aggregate_response = _get(ctx.client, f"/v1/units/{ctx.mine}/metrics", ctx.mine_token)
    assert aggregate_response.status_code == 200
    by_name = {item["name"]: item for item in aggregate_response.json()["metrics"]}
    value = by_name["opportunities"]["value"]

    drill_response = _get(
        ctx.client, f"/v1/units/{ctx.mine}/metrics/opportunities/drill-down", ctx.mine_token
    )
    assert drill_response.status_code == 200
    drill_down = drill_response.json()

    assert value == 2
    assert drill_down["aggregate_value"] == value
    assert len(drill_down["rows"]) == value
    assert {row["row_data"]["category"] for row in drill_down["rows"]} == {"hackathon", "Datathon"}
