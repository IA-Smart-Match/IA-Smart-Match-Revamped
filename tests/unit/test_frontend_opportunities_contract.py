"""Source contract for the opportunities/pipeline UI surfaces.

**These guards moved forward at P8 card O4 (2026-09-03).**

Before O4 they asserted a *pre-S12* world: that `Opportunities.tsx` said the
count was unknown "until S12", that `metrics.ts` exported an
``OPPORTUNITIES_UNKNOWN_REASON`` claiming "the canonical opportunities metric
is not registered", and that `Dashboard.tsx` imported that same constant. That
world no longer exists:

* ``smartmatch_domain.metrics.METRIC_REGISTER`` registers
  ``canonical_name="opportunities"`` with ``owning_query="opportunities_rows_v1"``,
* ``smartmatch_api.routers.metrics`` binds that owning query to accepted
  ``review_item`` rows and wires it into the dispatch table, and
* ``docs/decisions/p8-opportunities-decision-draft.md`` is **CLOSED — 2026-09-02**
  (canonical definition ratified by the product owner).

So the guards now assert the *post-O4* contract positively: each surface reads
the registered metric from ``GET /v1/units/{unit_id}/metrics`` and offers the
drill-down of that same owning query, and no surface can render a bare ``0``
for a value nobody measured (ADR-0011 rule 1 — unknown is not zero).

The forbidden-pattern lists are the half that did not need flipping: they still
name the fabrications these pages must never regain, and O4 added more of them.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"
OPPORTUNITIES_PAGE = FRONTEND_SRC / "app" / "pages" / "Opportunities.tsx"
DASHBOARD_PAGE = FRONTEND_SRC / "app" / "pages" / "Dashboard.tsx"
METRICS_LIB = FRONTEND_SRC / "lib" / "metrics.ts"
API_LIB = FRONTEND_SRC / "lib" / "api.ts"
DRILLDOWN_SHEET = FRONTEND_SRC / "app" / "components" / "provenance" / "MetricDrilldownSheet.tsx"
PIPELINE_PAGE = FRONTEND_SRC / "app" / "pages" / "Pipeline.tsx"

OPPORTUNITIES_FORBIDDEN_PATTERNS = (
    "fetchCrawlerResults",
    "fetchEvents",
    "mapCrawlerToOpportunity",
    "mapEventToOpportunity",
    'date: "See link for details"',
    'role: "Guest speaker"',
    "/ai-matching",
    "live dataset",
    "Showing ",
    "of {opportunities.length}",
)

#: Fabrications the dashboard must never regain. The first three predate O4;
#: the rest name merges O4 removed — a browser-side join of legacy `/api`
#: pipeline rows with the specialists/events CSVs, which produced counts no
#: server query owned (`docs/plans/frontend-broken-buttons.md` B41/B42), and
#: the crawler feed (B38/B39, "do not port").
DASHBOARD_OPPORTUNITIES_FORBIDDEN_PATTERNS = (
    "Loaded from CPP events",
    "Active Opportunities",
    "value={eventCount}",
    "uniqueMatchedSpeakers",
    "Volunteer Utilization",
    "stageCounts(",
    "matchVolume(",
    "<CrawlerFeed",
    "demo rows",
)

#: Ways a page can silently turn "we did not measure this" into a rendered 0.
#: Banned on every surface below. Note this deliberately does not ban `?? 0`
#: outright: `Dashboard.tsx` legitimately uses it for a CSS bar width and a
#: sort comparator, neither of which is a displayed measurement.
ZERO_COERCION_PATTERNS = (
    "summary.value ?? 0",
    "metric.value ?? 0",
    ".value ?? 0",
    "aggregate_value ?? 0",
    "total_feedback ?? 0",
    "total_generated ?? 0",
)

# Conversion rates need their own registered definitions and server-owned
# queries. Dividing registered counts in the browser is still client-owned
# metric logic and must not return as a helper or a visible tile.
CLIENT_SIDE_PIPELINE_CONVERSION_PATTERNS = (
    "stageConversionMetric",
    "STAGE_TRANSITIONS",
    "Stage-to-Stage Conversion Rates",
    "toSummary.value / fromSummary.value",
)

# Generic member-value division catches renamed helpers such as
# `pipelineRate = downstream.value / upstream.value`. Server-returned rates may
# be formatted in the browser, but two metric values may not be divided there.
CLIENT_SIDE_VALUE_DIVISION = re.compile(
    r"\b[A-Za-z_$][\w$]*\.value\s*/\s*[A-Za-z_$][\w$]*\.value\b"
)
PIPELINE_METRIC_CONTEXT = (
    "PIPELINE_FUNNEL_METRIC_NAMES",
    "PipelineFunnelMetricName",
    "pipeline_matched",
    "pipeline_contacted",
    "pipeline_confirmed",
    "pipeline_attended",
    "pipeline_member_inquiry",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontend_value_divisions(sources: dict[str, str]) -> list[str]:
    return [
        f"{name}: {match.group(0)}"
        for name, source in sources.items()
        if any(marker in source for marker in PIPELINE_METRIC_CONTEXT)
        for match in CLIENT_SIDE_VALUE_DIVISION.finditer(source)
    ]


def test_opportunities_page_does_not_fabricate_legacy_merge() -> None:
    source = _read(OPPORTUNITIES_PAGE)
    for pattern in OPPORTUNITIES_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"Opportunities page still contains fabricated-list pattern: {pattern!r}"
        )


def test_opportunities_page_reads_the_registered_metric_and_drill_down() -> None:
    """O4a: the count is the registered metric, the list is its drill-down.

    Flipped at O4 from ``test_opportunities_page_shows_unknown_until_s12``,
    which asserted the page still hard-coded an "unknown until S12" panel. The
    page now subscribes to the register, so the guard asserts the subscription
    rather than the placeholder — while keeping the two claims that are still
    true: an unavailable register falls back to an *accountable unknown*, and
    match scores stay off this page until gate G1.
    """
    source = _read(OPPORTUNITIES_PAGE)

    # Reads the registered metric by its canonical name.
    assert "useUnitMetrics" in source
    assert "OPPORTUNITIES_METRIC_NAME" in source

    # Offers the drill-down of that same owning query.
    assert "openDrilldown(OPPORTUNITIES_METRIC_NAME)" in source
    assert "MetricDrilldownSheet" in source

    # A missing register still yields unknown, never a locally derived count.
    assert "unavailableOpportunitiesMetric" in source
    assert "AccountableValue" in source

    # Matching remains G1-gated on this surface.
    assert "gate G1" in source


def test_metrics_lib_binds_opportunities_to_the_register() -> None:
    """O4: `metrics.ts` names the registered metric and drops the stale claim.

    Flipped at O4 from ``test_metrics_lib_exports_opportunities_unknown_reason``.
    That test asserted the reason string still read "S12 Pipeline persistence is
    not started" and "the canonical opportunities metric is not registered" —
    both false since the P8 decision closed and `opportunities_rows_v1` was
    bound. Asserting their *absence* is what keeps the stale claim from coming
    back.
    """
    source = _read(METRICS_LIB)

    # The canonical name the register uses, spelled exactly.
    assert 'OPPORTUNITIES_METRIC_NAME = "opportunities"' in source

    # The unknown reason still exists — a client-side fallback is still needed
    # when the register cannot be read — but must no longer deny the metric.
    assert "OPPORTUNITIES_UNKNOWN_REASON" in source
    assert "S12 Pipeline persistence is not started" not in source, (
        "Stale pre-O4 claim: S12 is not what gates the opportunities metric; "
        "it is bound to accepted review_item rows via opportunities_rows_v1."
    )
    assert "canonical opportunities metric is not registered" not in source, (
        "Stale pre-O4 claim: METRIC_REGISTER registers `opportunities` and the "
        "P8 decision record closed 2026-09-02."
    )

    # ADR-0011 rule 1: a null measurement becomes unknown, never zero.
    assert "if (summary.value === null)" in source
    assert "return unknownValue(" in source
    for pattern in ZERO_COERCION_PATTERNS:
        assert pattern not in source, f"metrics.ts coerces an unmeasured value to zero: {pattern!r}"


def test_pipeline_does_not_compute_unregistered_conversion_metrics_in_browser() -> None:
    metrics = _read(METRICS_LIB)
    pipeline = _read(PIPELINE_PAGE)

    for pattern in CLIENT_SIDE_PIPELINE_CONVERSION_PATTERNS:
        assert pattern not in metrics, (
            f"metrics.ts contains client-owned pipeline conversion logic: {pattern!r}"
        )
        assert pattern not in pipeline, (
            f"Pipeline page renders an unregistered conversion metric: {pattern!r}"
        )

    # The five registered funnel metrics and their drill-down surface remain.
    assert "PIPELINE_FUNNEL_METRIC_NAMES" in metrics
    assert "PipelineFunnelTiles" in pipeline

    frontend_sources = {
        str(path.relative_to(FRONTEND_SRC)): _read(path)
        for extension in ("*.ts", "*.tsx")
        for path in FRONTEND_SRC.rglob(extension)
    }
    assert _frontend_value_divisions(frontend_sources) == [], (
        "frontend computes a browser-owned metric rate by dividing two .value operands: "
        f"{_frontend_value_divisions(frontend_sources)}"
    )


def test_pipeline_conversion_guard_catches_generically_named_helper() -> None:
    """Mutation check: renaming the old helper and operands cannot evade the guard."""
    mutated_source = {
        "lib/renamedMetrics.ts": (
            "const stages = PIPELINE_FUNNEL_METRIC_NAMES;\n"
            "const pipelineRate = downstream.value / upstream.value;"
        )
    }

    assert _frontend_value_divisions(mutated_source) == [
        "lib/renamedMetrics.ts: downstream.value / upstream.value"
    ]


def test_pipeline_conversion_guard_ignores_unrelated_value_division() -> None:
    unrelated_source = {"components/ImageSizer.tsx": "const scale = image.value / container.value;"}

    assert _frontend_value_divisions(unrelated_source) == []


def test_dashboard_reads_registered_opportunities_without_fabricating() -> None:
    """O4b: registered metric name + drill-down, no browser-side merge.

    Flipped at O4 from ``test_dashboard_does_not_fabricate_opportunities_count``.
    The forbidden-pattern half is kept verbatim and extended with the merges O4
    removed; the "still imports OPPORTUNITIES_UNKNOWN_REASON" half is replaced
    by the positive subscription assertions, since the dashboard now reads the
    metric instead of importing a constant that explained why it could not.
    """
    source = _read(DASHBOARD_PAGE)

    for pattern in DASHBOARD_OPPORTUNITIES_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"Dashboard still contains fabricated opportunities pattern: {pattern!r}"
        )

    # Reads the registered metric and drills into the same owning query.
    assert "useUnitMetrics" in source
    assert "OPPORTUNITIES_METRIC_NAME" in source
    assert "accountableMetricFromSummary" in source
    assert "openDrilldown(metricName)" in source
    assert "MetricDrilldownSheet" in source

    # An unreadable register still degrades to an accountable unknown.
    assert "unavailableOpportunitiesMetric" in source

    for pattern in ZERO_COERCION_PATTERNS:
        assert pattern not in source, f"Dashboard coerces an unmeasured value to zero: {pattern!r}"


def test_api_lib_exposes_the_metrics_and_drill_down_routes() -> None:
    """The two routes every flipped guard above depends on actually exist.

    Without this, the assertions that a page "reads the registered metric and
    its drill-down" could pass against a client that calls nothing real.
    """
    source = _read(API_LIB)
    assert "fetchUnitMetrics" in source
    assert "fetchMetricDrillDown" in source
    assert "/v1/units/" in source
    assert "/drill-down" in source


def test_drilldown_sheet_enforces_the_aggregate_row_invariant() -> None:
    """ADR-0011 rule 4 is enforced on the client, not just server-side.

    Added at O4 fix round 3. ``assertDrilldownMatchesAggregate`` had exactly one
    occurrence in the whole frontend — its own definition — so the sheet
    rendered whatever rows came back and the invariant ("clicked N lists exactly
    N rows; an unknown aggregate implies an empty row set") was checked only in
    ``tests/contract/test_metrics.py``. A dead helper that looks like
    enforcement is the same class of defect as a fabricated number, so this
    guard exists to stop it rotting back into a dead export.
    """
    sheet = _read(DRILLDOWN_SHEET)
    metrics = _read(METRICS_LIB)

    # The helper still exists and is still the single definition of the rule.
    assert "export function assertDrilldownMatchesAggregate" in metrics

    # The sheet imports it and actually calls it.
    assert "assertDrilldownMatchesAggregate" in sheet, (
        "MetricDrilldownSheet no longer references the rule 4 check; the helper "
        "is a dead export again."
    )
    assert "assertDrilldownMatchesAggregate(drilldown)" in sheet, (
        "The rule 4 helper is imported but never invoked on the payload."
    )

    # A mismatch must reach the user, not a console warning or a swallow.
    assert "console.warn" not in sheet
    assert "console.error" not in sheet
    assert 'role="alert"' in sheet
    assert "does not reconcile with its aggregate" in sheet

    # Rows are gated on the check, so a mismatch cannot render them anyway.
    assert "rowsAreShowable" in sheet
    assert "rowsAreShowable && drilldown.rows.length > 0" in sheet

    # Rule 4's unknown case: an unknown aggregate is not a measured zero.
    assert "aggregateIsUnknown" in sheet
    assert "An unknown aggregate is not a measured zero." in sheet


def test_the_page_is_labelled_speaker_requests_without_renaming_the_metric() -> None:
    """CBA-TERMINOLOGY: customer §4 maps *volunteer opportunity* to *Speaker
    Request*, and §25 lists that rename as P0.

    The label and the identifier are deliberately allowed to disagree. What the
    user reads is the customer's word; what the page cites as its source is the
    registered ``opportunities`` metric, spelled exactly as the register spells
    it. Renaming ``canonical_name`` to match the label would break the binding
    this whole module exists to protect — the number would stop being traceable
    to the query that owns it, which is the defect O4 closed.
    """
    source = _read(OPPORTUNITIES_PAGE)

    assert 'className="text-3xl font-semibold text-gray-900">Speaker Requests</h1>' in source, (
        "the visible heading no longer uses the customer-approved term"
    )
    # The identifier survives the rename, in the import and on screen.
    assert "OPPORTUNITIES_METRIC_NAME" in source
    assert "Registered metric · {OPPORTUNITIES_METRIC_NAME}" in source
    assert "<code>opportunities</code>" in source

    # And the retired term is gone from what the user reads. The word still
    # appears in the accountability line above, so this is asserted on the
    # heading rather than the file.
    assert ">Opportunities</h1>" not in source
