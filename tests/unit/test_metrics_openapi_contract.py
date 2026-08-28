"""OpenAPI contract for accountable metrics consumed by the legacy frontend."""

from __future__ import annotations

import json
from pathlib import Path

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"


def _schema(name: str) -> dict:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    return document["components"]["schemas"][name]


def test_metric_summary_fields_match_frontend_client() -> None:
    properties = _schema("MetricSummary")["properties"]
    assert set(properties) >= {
        "name",
        "display_name",
        "definition",
        "value",
        "unknown_reason",
        "drill_down_url",
    }
    assert "null" in json.dumps(properties["value"])


def test_metrics_response_fields_match_frontend_client() -> None:
    properties = _schema("MetricsResponse")["properties"]
    assert set(properties) >= {"unit_id", "metrics"}
    assert properties["metrics"]["type"] == "array"


def test_metric_drill_down_response_fields_match_frontend_client() -> None:
    properties = _schema("MetricDrillDownResponse")["properties"]
    assert set(properties) >= {
        "unit_id",
        "name",
        "definition",
        "aggregate_value",
        "unknown_reason",
        "rows",
    }
