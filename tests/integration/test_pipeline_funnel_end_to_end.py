"""End-to-end proof: the funnel metrics go non-zero because of this branch (Card 8, part A).

Every other integration test in this plan proves one card's own slice: Card 1
proves the column and its CHECK, Card 5 proves `provision_on_accept` in
isolation, Card 6 proves the route wires it in. None of them, on its own, is
the claim this branch actually makes — that `pipeline_funnel_rows_v1` and
`opportunities_rows_v1` can be **non-zero from a deployed path**. This file is
that proof, walked once, start to finish, through nothing but the routes a
real coordinator would call: `POST /v1/review-items/{id}/decision` to accept
two synthetic professionals and one in-list synthetic event, then
`GET /v1/units/{unit_id}/metrics` and its drill-down to read the numbers back
— never `PipelineRepository` — and finally `tools.seed_demo_pipeline.main`
(also a real, deployable entry point, not a shortcut) to walk the two opened
journeys to Attended and prove the remaining three funnel stages move too.

**Why the metric values must come from the routes and nowhere else.** A test
that asserted on `PipelineRepository.get(...)` after driving the accept would
be proving that the repository agrees with itself — the metrics binding
(`services/api/smartmatch_api/routers/metrics.py::_pipeline_funnel_rows_v1`)
could be broken, unreachable, or simply never wired to this data, and such a
test would still pass. ADR-0011 rule 4 exists precisely so a number a
stakeholder sees traces to one calculation; this file's own negative test
(`test_no_assertion_reads_a_metric_from_pipelinerepository`) enforces that
mechanically by scanning this module's own source for a call to that
repository's matched-stage writer — the one call this file must never make,
because making it would let a future edit here quietly start asserting
against the write path instead of the read path without anyone noticing in
review.

**Why two professionals, not one.** `pipeline_matched == 2` after one events
accept proves the fan-out in Decision 6 actually happened — one accepted
in-list event opens one journey *per linked professional*, not one journey
total. A single professional could not distinguish "the loop opened one
journey" from "the loop opened one journey per professional and there was
only one".

**What this file does not prove.** It does not prove matching quality —
there is no score anywhere in this path, by design (plan §1.3) — and it does
not prove anything about the real matching engine (`PR #12`), which is out of
scope and out of reach of every module this file imports.

Requires a live database, and is skipped when none is reachable
(`engine` fixture, `tests/integration/conftest.py`).
"""

from __future__ import annotations

import ast
import inspect
import itertools
import sys
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from conftest import DATABASE_URL, JOB_OWNING_UNIT_PATH, ensure_owning_unit
from fastapi.testclient import TestClient
from smartmatch_domain.metrics import OpportunityCategoryShape, shape_opportunity_category
from smartmatch_persistence.engine import create_session_factory
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker
from test_review_accept_opens_pipeline import (
    _decide,
    _get,
    _make_client,
    _register_coordinator,
    _seed_review_items,
)

from tools import seed_demo_pipeline

pytestmark = pytest.mark.integration

#: The two synthetic professionals this file accepts. Two, not one — see the
#: module docstring's note on why a single professional cannot distinguish
#: "fan-out happened" from "there was nothing to fan out to".
_PROFESSIONAL_ROWS: tuple[Mapping[str, Any], ...] = (
    {"name": "Ada Lovelace", "metro_region": "Portland"},
    {"name": "Grace Hopper", "metro_region": "Portland"},
)

#: An in-list category (`smartmatch_domain.metrics.OPPORTUNITY_IN_LIST_CATEGORIES`),
#: pre-normalized exactly as `smartmatch_domain.ingest.normalize_header` would
#: leave it — this file seeds the review item directly, the same way Card 6's
#: own `_seed_review_items` does, bypassing the import worker's normalization
#: step entirely (that step is not part of this file's claim).
_IN_LIST_EVENT_ROW: Mapping[str, Any] = {
    "event_program": "Portland Hackathon",
    "category": "hackathon",
}

#: The five funnel metrics, outermost stage last — mirrors
#: `smartmatch_domain.pipeline.PIPELINE_STAGE_SEQUENCE`, restated as a local
#: literal rather than imported so a reordering upstream shows up here as a
#: failing assertion instead of silently reordering this file's own checks
#: along with it (the same reasoning `test_pipeline_record_writers.py`'s
#: `FUNNEL_ORDER` docstring gives).
_FUNNEL_METRIC_NAMES: tuple[str, ...] = (
    "pipeline_matched",
    "pipeline_contacted",
    "pipeline_confirmed",
    "pipeline_attended",
    "pipeline_member_inquiry",
)


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the live test engine, for `_seed_review_items`."""
    return create_session_factory(engine.url.render_as_string(hide_password=False))


def _delete_this_files_rows(engine: Engine, tenant_id: uuid.UUID) -> None:
    """Delete `pipeline_record` / `professional_unit_relationship` / `attendance_record`.

    `pipeline_record` is deleted first because it is the row
    `attendance_record` is cited from (`attended_attendance_id`, constraint 8
    in plan §1.4); deleting it out of that order would leave
    `attendance_record` still referenced.
    """
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )


@pytest.fixture(autouse=True)
def _clean_funnel_rows(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's provisioned rows both before and after each test.

    `pipeline_record`, `professional_unit_relationship`, and
    `attendance_record` all sit outside `conftest.py`'s
    `_TENANT_SCOPED_TABLES`, and all three carry `ON DELETE RESTRICT`
    foreign keys back to `org_unit` and `user_account` — the same
    arrangement, for the same reason, `test_review_accept_opens_pipeline.py`
    and `test_seed_demo_pipeline.py` both already use. `tenant_id` is a
    fresh, per-test tenant, so the pre-yield delete here ordinarily has
    nothing to do; it exists so a prior run that crashed mid-test (and so
    never reached its own post-yield delete) cannot leave rows behind that
    would corrupt this test's `== 2`/`== 1` counts on a re-run — the same
    reasoning `pipeline_matched_baseline` gives in `compose_smoke.sh`.
    """
    _delete_this_files_rows(engine, tenant_id)
    yield
    _delete_this_files_rows(engine, tenant_id)


@dataclass(frozen=True, slots=True)
class _Context:
    client: TestClient
    engine: Engine
    tenant_id: uuid.UUID
    tenant_slug: str
    unit_id: uuid.UUID
    session_factory: sessionmaker[Session]
    coordinator_token: str


@pytest.fixture
def ctx(engine: Engine, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]) -> _Context:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        tenant_slug = str(
            conn.execute(
                text("SELECT slug FROM tenant WHERE id = :id"), {"id": tenant_id}
            ).scalar_one()
        )
    client = _make_client(engine)
    token, _ = _register_coordinator(engine, client, tenant_id, JOB_OWNING_UNIT_PATH)
    return _Context(
        client=client,
        engine=engine,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        unit_id=unit_id,
        session_factory=session_factory,
        coordinator_token=token,
    )


def _metrics_by_name(ctx: _Context) -> dict[str, dict[str, Any]]:
    response = _get(ctx.client, f"/v1/units/{ctx.unit_id}/metrics", ctx.coordinator_token)
    assert response.status_code == 200
    return {item["name"]: item for item in response.json()["metrics"]}


def _drill_down(ctx: _Context, metric_name: str) -> dict[str, Any]:
    path = f"/v1/units/{ctx.unit_id}/metrics/{metric_name}/drill-down"
    response = _get(ctx.client, path, ctx.coordinator_token)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


# ---------------------------------------------------------------------------
# The whole path, in one walk: seed review items (professionals, events) ->
# accept through the routes -> metrics read back through the routes -> the
# seed tool -> metrics read back again.
# ---------------------------------------------------------------------------


def test_pipeline_funnel_end_to_end_through_the_real_routes(
    ctx: _Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ---- Steps 1-2: two professionals, accepted through the route --------
    professional_item_ids = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="professionals",
        rows=_PROFESSIONAL_ROWS,
    )
    assert len(professional_item_ids) == 2
    for item_id in professional_item_ids:
        response = _decide(ctx.client, ctx.coordinator_token, item_id, "accepted")
        assert response.status_code == 200

    # ---- Step 3: one in-list events row, accepted through the route ------
    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )
    response = _decide(ctx.client, ctx.coordinator_token, event_item_id, "accepted")
    assert response.status_code == 200

    # ---- Step 4: metrics read back through the route, before the seed tool
    metrics = _metrics_by_name(ctx)
    assert metrics["pipeline_matched"]["value"] == 2
    assert metrics["pipeline_matched"]["unknown_reason"] is None
    assert metrics["opportunities"]["value"] == 1
    assert metrics["opportunities"]["unknown_reason"] is None
    # A measured zero, not an unknown — the honest state before the seed
    # tool runs (plan §1.10, and this metric's own docstring in
    # `routers/metrics.py`).
    for name in (
        "pipeline_contacted",
        "pipeline_confirmed",
        "pipeline_attended",
        "pipeline_member_inquiry",
    ):
        assert metrics[name]["value"] == 0, name
        assert metrics[name]["unknown_reason"] is None, name

    # ---- Step 5: drill-down id sets match the database, for both metrics -
    with ctx.engine.connect() as conn:
        db_pipeline_ids = {
            str(row.id)
            for row in conn.execute(
                text(
                    "SELECT id FROM pipeline_record "
                    "WHERE tenant_id = :tid AND owning_unit_id = :uid"
                ),
                {"tid": ctx.tenant_id, "uid": ctx.unit_id},
            )
        }
        accepted_review_rows = conn.execute(
            text(
                "SELECT ri.id, ri.row_data FROM review_item ri "
                "JOIN import_batch ib "
                "  ON ib.tenant_id = ri.tenant_id AND ib.id = ri.import_batch_id "
                "WHERE ri.tenant_id = :tid AND ib.owning_unit_id = :uid AND ri.status = 'accepted'"
            ),
            {"tid": ctx.tenant_id, "uid": ctx.unit_id},
        ).all()
    # Shared-rule limitation, noted rather than hidden: this filter calls the
    # same `shape_opportunity_category` the metrics binding itself calls
    # (`routers/metrics.py::_opportunities_rows_v1`), so a wrong IN_LIST rule
    # would move both sides of the comparison below together rather than
    # being caught by it. What this comparison *does* still prove is that
    # the metric and the drill-down agree with each other and with a direct
    # read of the same table — and the adjacent `== 1` / `== 2` assertions
    # above are literal expected counts, not derived from this rule, so this
    # file cannot pass at zero even if the shared rule were wrong.
    db_opportunity_ids = {
        str(row.id)
        for row in accepted_review_rows
        if shape_opportunity_category((row.row_data or {}).get("category"))
        is OpportunityCategoryShape.IN_LIST
    }
    assert len(db_pipeline_ids) == 2
    assert len(db_opportunity_ids) == 1

    matched_drill_down = _drill_down(ctx, "pipeline_matched")
    assert matched_drill_down["aggregate_value"] == 2 == len(matched_drill_down["rows"])
    assert {row["id"] for row in matched_drill_down["rows"]} == db_pipeline_ids

    opportunities_drill_down = _drill_down(ctx, "opportunities")
    assert opportunities_drill_down["aggregate_value"] == 1 == len(opportunities_drill_down["rows"])
    assert {row["id"] for row in opportunities_drill_down["rows"]} == db_opportunity_ids

    # ---- Step 6: provenance is persisted, read from the database ---------
    with ctx.engine.connect() as conn:
        provenance_values = {
            row.matched_provenance
            for row in conn.execute(
                text(
                    "SELECT matched_provenance FROM pipeline_record "
                    "WHERE tenant_id = :tid AND owning_unit_id = :uid"
                ),
                {"tid": ctx.tenant_id, "uid": ctx.unit_id},
            )
        }
    assert provenance_values == {"synthetic / coordinator-accepted"}

    # ---- Step 7: the seed tool walks both journeys to Attended -----------
    monkeypatch.setenv("SMARTMATCH_EDITION", "dev")
    monkeypatch.setenv("SMARTMATCH_USE_FIXTURE_PROVIDERS", "true")
    monkeypatch.setenv("SMARTMATCH_DATABASE_URL", DATABASE_URL)
    exit_code = seed_demo_pipeline.main(
        [
            "--tenant-slug",
            ctx.tenant_slug,
            "--unit-path",
            JOB_OWNING_UNIT_PATH,
            "--through",
            "attended",
            "--limit",
            "2",
        ]
    )
    assert exit_code == 0

    metrics_after_seed = _metrics_by_name(ctx)
    assert metrics_after_seed["pipeline_matched"]["value"] == 2
    assert metrics_after_seed["pipeline_contacted"]["value"] == 2
    assert metrics_after_seed["pipeline_confirmed"]["value"] == 2
    assert metrics_after_seed["pipeline_attended"]["value"] == 2
    assert metrics_after_seed["pipeline_member_inquiry"]["value"] == 0
    for name in _FUNNEL_METRIC_NAMES:
        assert metrics_after_seed[name]["unknown_reason"] is None, name
        drill_down = _drill_down(ctx, name)
        # ADR-0011 rule 3: the aggregate and the drill-down are the same query.
        assert (
            drill_down["aggregate_value"]
            == len(drill_down["rows"])
            == metrics_after_seed[name]["value"]
        )

    # ---- Step 8: the funnel never widens ----------------------------------
    values = [metrics_after_seed[name]["value"] for name in _FUNNEL_METRIC_NAMES]
    assert all(earlier >= later for earlier, later in itertools.pairwise(values))

    # ---- Step 10: no orphan subject_id reached storage through the HTTP path
    with ctx.engine.connect() as conn:
        orphan_count = conn.execute(
            text(
                "SELECT count(*) FROM pipeline_record pr "
                "LEFT JOIN user_account ua "
                "  ON ua.tenant_id = pr.tenant_id AND ua.id = pr.subject_id "
                "WHERE pr.tenant_id = :tid AND pr.owning_unit_id = :uid AND ua.id IS NULL"
            ),
            {"tid": ctx.tenant_id, "uid": ctx.unit_id},
        ).scalar_one()
    assert orphan_count == 0


# ---------------------------------------------------------------------------
# Step 9 — mechanical: no assertion above obtains a metric value from
# PipelineRepository. Enforced by scanning this module's own source, not by
# convention, so a future edit that adds a call to that repository's
# matched-stage writer fails loudly rather than quietly starting to assert
# against the write path instead of the route.
# ---------------------------------------------------------------------------

#: The forbidden call, assembled rather than spelled as one literal — so this
#: constant's own definition, and the docstrings above that talk *about* the
#: rule in prose, do not themselves trip the scan they describe.
_FORBIDDEN_WRITE_CALL: str = "record_matched" + "("


def test_no_assertion_reads_a_metric_from_pipelinerepository() -> None:
    """The brief's own mechanical rule: this file never calls the matched-stage writer.

    Scoped to the one call this file must never make, not to the name of the
    repository that owns it — this module's docstring talks *about* that
    repository (to say why it is deliberately absent from the assertions
    below), and a broader string ban would make that explanation
    unwritable.
    """
    source = inspect.getsource(sys.modules[__name__])
    assert _FORBIDDEN_WRITE_CALL not in source


def test_module_never_imports_pipelinerepository() -> None:
    """The property that actually matters: nothing in this file can even reach it.

    Banning the literal call (above) bans one *plausible-looking* way a
    future edit might fake a metric read; it does not by itself prove the
    read path was the only path available, because a value could in
    principle come from `PipelineRepository.get(...)` instead of that
    repository's matched-stage writer. This test proves the stronger claim
    directly:
    parse this module's own import statements with `ast` (not a substring
    scan, which the docstrings above would trip — they talk *about*
    `PipelineRepository` in prose) and assert the name was never imported at
    all. If it isn't imported, no assertion below can call any of its
    methods, `record_matched` included.
    """
    tree = ast.parse(inspect.getsource(sys.modules[__name__]))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert "PipelineRepository" not in imported_names
