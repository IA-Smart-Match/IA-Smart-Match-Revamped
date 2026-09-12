"""OpenAPI contract for the Speaker Pipeline read consumed by the frontend.

The committed document is what a client generator reads, so these assertions
are made against it rather than against the Python models: a field that is
optional in the schema but required by the screen is a break the models alone
cannot show. The nullability assertions are the load-bearing ones — ADR-0011
rule 1 survives into the contract only if "no rate" is expressible as ``null``
rather than defaulted to ``0``.

``tests/unit/test_metrics_openapi_contract.py`` is its neighbour and covers
the register listing (``MetricSummary``, ``MetricsResponse`` and the
drill-down); nothing there mentions this route or any schema below.
"""

from __future__ import annotations

import json
from pathlib import Path

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"


def _document() -> dict:
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


def _schema(name: str) -> dict:
    return _document()["components"]["schemas"][name]


def test_the_route_is_published() -> None:
    paths = _document()["paths"]
    assert "/v1/units/{unit_id}/speaker-pipeline" in paths
    assert "get" in paths["/v1/units/{unit_id}/speaker-pipeline"]


def test_one_read_carries_the_whole_screen() -> None:
    """Six cards, a funnel, a conversions panel and insights, in one payload."""
    properties = _schema("SpeakerPipelineResponse")["properties"]
    assert set(properties) >= {
        "unit_id",
        "range",
        "metrics",
        "baseline_metric",
        "stages",
        "companions",
        "conversions",
        "insights",
    }


def test_a_rate_that_does_not_exist_is_expressible_as_null() -> None:
    conversion = _schema("ConversionOut")["properties"]
    assert set(conversion) >= {
        "from_metric",
        "to_metric",
        "label",
        "numerator",
        "denominator",
        "rate_pct",
        "display",
        "unavailable_reason",
    }
    assert "null" in json.dumps(conversion["rate_pct"])
    assert "null" in json.dumps(conversion["unavailable_reason"])


def test_a_stage_carries_both_its_value_and_why_it_might_be_missing() -> None:
    stage = _schema("FunnelStageOut")["properties"]
    assert set(stage) >= {
        "metric_name",
        "display_name",
        "description",
        "value",
        "unknown_reason",
        "share_of_baseline_pct",
        "share_display",
    }
    assert "null" in json.dumps(stage["value"])
    assert "null" in json.dumps(stage["share_of_baseline_pct"])


def test_companion_metrics_are_a_separate_field_from_stages() -> None:
    """The review counts must not be reachable as funnel stages by shape."""
    response = _schema("SpeakerPipelineResponse")["properties"]
    assert "companions" in response
    companion = _schema("CompanionMetricOut")["properties"]
    assert set(companion) >= {
        "metric_name",
        "display_name",
        "description",
        "definition",
        "value",
        "unknown_reason",
    }
    assert "null" in json.dumps(companion["value"])


def test_insights_carry_a_stable_code_for_the_client_to_switch_on() -> None:
    """The client picks an icon from ``code``, never by matching on prose."""
    assert set(_schema("InsightOut")["properties"]) >= {"code", "tone", "title", "detail"}


def test_the_range_states_itself_rather_than_leaving_the_client_to_label_it() -> None:
    assert set(_schema("SpeakerPipelineRange")["properties"]) >= {"kind", "label", "note"}
