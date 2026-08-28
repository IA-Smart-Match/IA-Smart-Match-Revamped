"""ADR-0011 contract checks for the pure metric register."""

from __future__ import annotations

import dataclasses

import pytest
from smartmatch_domain.metrics import METRIC_REGISTER, get_metric


def test_every_metric_has_one_name_definition_query_and_drill_down() -> None:
    names = [metric.canonical_name for metric in METRIC_REGISTER]

    assert len(names) == len(set(names))
    for metric in METRIC_REGISTER:
        assert metric.canonical_name.strip()
        assert metric.definition.strip()
        assert metric.owning_query.strip()
        assert metric.drill_down.strip()


@pytest.mark.parametrize(
    "name",
    [
        "pipeline_matched",
        "pipeline_contacted",
        "pipeline_confirmed",
        "pipeline_attended",
        "pipeline_member_inquiry",
    ],
)
def test_pipeline_metrics_explain_why_they_are_unknown(name: str) -> None:
    metric = get_metric(name)

    assert metric is not None
    assert metric.unknown_reason is not None
    assert "S12" in metric.unknown_reason


def test_register_entries_are_frozen() -> None:
    metric = METRIC_REGISTER[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        metric.canonical_name = "changed"  # type: ignore[misc]
