"""ADR-0011 contract checks for the pure metric register."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from smartmatch_domain.metrics import (
    METRIC_REGISTER,
    OPPORTUNITY_IN_LIST_CATEGORIES,
    OpportunityCategoryShape,
    get_metric,
    shape_opportunity_category,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "opportunities"


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
def test_pipeline_metrics_are_bound_and_no_longer_unknown(name: str) -> None:
    """P8 card O3: the register itself no longer carries an unknown reason.

    Migration ``0011`` gave Pipeline a real evidence table and card O3 bound
    the owning query to it, so every Pipeline entry's ``unknown_reason`` is
    gone from the register — the adapter, not the definition, is where the
    "no application code writes pipeline_record yet" caveat now lives (see
    ``smartmatch_domain.metrics``'s module docstring and
    ``_pipeline_funnel_rows_v1``).
    """
    metric = get_metric(name)

    assert metric is not None
    assert metric.unknown_reason is None


def test_register_entries_are_frozen() -> None:
    metric = METRIC_REGISTER[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        metric.canonical_name = "changed"  # type: ignore[misc]


def test_opportunities_is_registered_and_bound_not_unknown() -> None:
    """P8 card O3: ``opportunities`` is bound to storage; the register agrees."""
    metric = get_metric("opportunities")

    assert metric is not None
    # Renamed by CBA-TERMINOLOGY (customer §4: Volunteer Opportunity -> Speaker
    # Request). `canonical_name` is the identifier and is unchanged, which is
    # why the binding assertions below still read "opportunities".
    assert metric.display_name == "Speaker Requests"
    assert metric.unknown_reason is None


def test_opportunities_owning_query_is_exact() -> None:
    metric = get_metric("opportunities")

    assert metric is not None
    assert metric.owning_query == "opportunities_rows_v1"


@pytest.mark.parametrize(
    "category",
    [
        "hackathon",
        "datathon",
        "competition",
        "guest lecturer event",
        "school event",
    ],
)
def test_opportunities_definition_names_every_in_list_category(category: str) -> None:
    metric = get_metric("opportunities")

    assert metric is not None
    assert category in metric.definition
    assert category in OPPORTUNITY_IN_LIST_CATEGORIES


def test_opportunities_definition_carries_the_ratified_counting_rule() -> None:
    metric = get_metric("opportunities")

    assert metric is not None
    assert "CBA coordinator" in metric.definition
    assert "non-exhaustive" in metric.definition
    assert "does not mean invalid" in metric.definition


def _read_opportunity_fixture(name: str) -> dict[str, str]:
    path = FIXTURES_DIR / name
    data: dict[str, str] = json.loads(path.read_text())
    return data


@pytest.mark.parametrize(
    "fixture_name",
    [
        "in_list_hackathon.json",
        "in_list_datathon.json",
        "in_list_competition.json",
        "in_list_guest_lecturer_event.json",
        "in_list_school_event.json",
    ],
)
def test_in_list_fixtures_shape_as_in_list(fixture_name: str) -> None:
    fixture = _read_opportunity_fixture(fixture_name)

    assert shape_opportunity_category(fixture["category"]) is OpportunityCategoryShape.IN_LIST


def test_out_of_list_raw_example_shapes_as_out_of_list_not_invalid() -> None:
    fixture = _read_opportunity_fixture("out_of_list_raw_example.json")

    # out-of-list is pending coordinator review, never invalid and never IN_LIST
    assert shape_opportunity_category(fixture["category"]) is OpportunityCategoryShape.OUT_OF_LIST


def test_absent_category_shapes_as_absent_not_out_of_list() -> None:
    # a missing category is a different work item from an unmapped label:
    # it needs a category assigned before a coordinator can even review it.
    assert shape_opportunity_category(None) is OpportunityCategoryShape.ABSENT
    assert shape_opportunity_category(None) is not OpportunityCategoryShape.OUT_OF_LIST


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n  "])
def test_blank_category_shapes_as_absent_not_out_of_list(blank: str) -> None:
    """A blank string recorded no category, exactly as ``None`` did.

    The bug this pins: ``shape_opportunity_category`` used to return
    ``ABSENT`` only for ``None``, so an import that wrote ``""`` — or a
    whitespace-only cell — into the column came back ``OUT_OF_LIST`` and was
    filed as an *unmapped label* for a coordinator to map to an in-list
    category. There is no label there to map; the row needs a category
    assigned first, which is what ``ABSENT`` means. This also restores the
    convention the repository already states in
    ``smartmatch_domain.ingest.assess_columns``: "only ``None`` and
    whitespace are blank on their own".
    """
    assert shape_opportunity_category(blank) is OpportunityCategoryShape.ABSENT
    assert shape_opportunity_category(blank) is not OpportunityCategoryShape.OUT_OF_LIST


def test_the_category_shape_enum_still_has_exactly_three_members() -> None:
    """Blank folds into ``ABSENT``; it does not earn a fourth outcome."""
    assert {shape.value for shape in OpportunityCategoryShape} == {
        "in-list",
        "out-of-list",
        "absent",
    }


def test_category_comparison_is_case_insensitive() -> None:
    assert shape_opportunity_category("HACKATHON") is OpportunityCategoryShape.IN_LIST
    assert shape_opportunity_category("  Datathon  ") is OpportunityCategoryShape.IN_LIST
