"""Tests for the class exercise's "nobody on this list is ..." notice.

Requirements row "Who is on the list"
(`docs/product/class-exercise-requirements.md`): *"A one-line notice when a
major or year that exists among the 300 has nobody on the list."* The design
spec §7 records the notice itself as backlog behind the counts table; this
module is that backlog item built as a pure function, with the grouping
values passed in rather than read from a table: the vocabularies are closed
at ingest, and a notice that counts labels needs none of them.

The ADR-0011 rule the whole platform runs on applies here too: a profile
whose major or year is not on file is **unknown**, not a group. It is never
coerced to a label and never counted as a zero-sized group, so an absent
value can never produce a notice claiming nobody of that kind is on the list.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.exercise_list_coverage import (
    GroupValues,
    ListCoverage,
    find_uncovered_groups,
    uncovered_labels,
)


def test_label_present_in_all_profiles_but_absent_from_list_is_uncovered():
    values = GroupValues(
        dimension="major",
        all_profiles=("Finance", "Marketing", "Finance"),
        on_list=("Marketing",),
    )
    assert uncovered_labels(values) == ("Finance",)


def test_label_present_on_the_list_is_not_uncovered():
    values = GroupValues(
        dimension="major",
        all_profiles=("Finance", "Marketing"),
        on_list=("Finance", "Marketing"),
    )
    assert uncovered_labels(values) == ()


def test_unknown_is_never_a_group_on_either_side():
    """A profile with no major on file is unknown, not an uncovered group."""
    values = GroupValues(
        dimension="major",
        all_profiles=("Finance", None, None),
        on_list=("Finance", None),
    )
    assert uncovered_labels(values) == ()


def test_unknown_on_the_list_does_not_cover_a_label():
    """An unknown value on the list covers nothing; it is not a wildcard."""
    values = GroupValues(
        dimension="major",
        all_profiles=("Finance", "Marketing"),
        on_list=("Finance", None),
    )
    assert uncovered_labels(values) == ("Marketing",)


def test_order_follows_first_appearance_among_all_profiles():
    """Deterministic without hardcoding a vocabulary.

    The caller decides the order by the order it hands over the whole set, so
    once Ann's year vocabulary lands the caller can impose it without this
    module learning a single major or year name.
    """
    values = GroupValues(
        dimension="class_year",
        all_profiles=("senior", "first-year", "junior", "first-year", "senior"),
        on_list=("junior",),
    )
    assert uncovered_labels(values) == ("senior", "first-year")


def test_empty_list_leaves_every_known_label_uncovered():
    values = GroupValues(
        dimension="major",
        all_profiles=("Finance", "Marketing", None),
        on_list=(),
    )
    assert uncovered_labels(values) == ("Finance", "Marketing")


def test_label_on_the_list_but_not_in_the_whole_set_is_not_reported():
    """The notice is about the 300, so the whole set is the only source."""
    values = GroupValues(
        dimension="major",
        all_profiles=("Finance",),
        on_list=("Finance", "Economics"),
    )
    assert uncovered_labels(values) == ()


def test_blank_string_is_rejected_rather_than_read_as_unknown():
    with pytest.raises(ValueError, match="use None for unknown"):
        GroupValues(dimension="major", all_profiles=("Finance", "  "), on_list=())


def test_blank_dimension_is_rejected():
    with pytest.raises(ValueError, match="dimension"):
        GroupValues(dimension="  ", all_profiles=(), on_list=())


def test_group_values_is_frozen():
    values = GroupValues(dimension="major", all_profiles=("Finance",), on_list=())
    with pytest.raises((AttributeError, TypeError)):
        values.dimension = "class_year"  # type: ignore[misc]


def test_find_uncovered_groups_reports_both_dimensions():
    coverage = find_uncovered_groups(
        majors=GroupValues(
            dimension="major",
            all_profiles=("Finance", "Marketing"),
            on_list=("Marketing",),
        ),
        class_years=GroupValues(
            dimension="class_year",
            all_profiles=("first-year", "senior"),
            on_list=("senior",),
        ),
    )
    assert coverage == ListCoverage(
        missing_majors=("Finance",),
        missing_class_years=("first-year",),
    )
    assert coverage.has_uncovered_group is True


def test_find_uncovered_groups_reports_nothing_when_the_list_covers_everything():
    coverage = find_uncovered_groups(
        majors=GroupValues(
            dimension="major",
            all_profiles=("Finance", None),
            on_list=("Finance",),
        ),
        class_years=GroupValues(
            dimension="class_year",
            all_profiles=("senior",),
            on_list=("senior", None),
        ),
    )
    assert coverage.missing_majors == ()
    assert coverage.missing_class_years == ()
    assert coverage.has_uncovered_group is False


def test_inputs_are_not_mutated():
    all_profiles = ["Finance", "Marketing"]
    on_list = ["Marketing"]
    values = GroupValues(
        dimension="major",
        all_profiles=all_profiles,
        on_list=on_list,
    )
    uncovered_labels(values)
    assert all_profiles == ["Finance", "Marketing"]
    assert on_list == ["Marketing"]
    assert values.all_profiles == ("Finance", "Marketing")


def test_no_numeric_score_is_exposed():
    """ADR-0025 D8: the notice names groups, never counts or percentages."""
    coverage = find_uncovered_groups(
        majors=GroupValues(dimension="major", all_profiles=("Finance",), on_list=()),
        class_years=GroupValues(dimension="class_year", all_profiles=("senior",), on_list=()),
    )
    assert all(isinstance(label, str) for label in coverage.missing_majors)
    assert all(isinstance(label, str) for label in coverage.missing_class_years)
