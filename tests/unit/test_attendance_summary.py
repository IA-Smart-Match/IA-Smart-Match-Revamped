"""The attendance fold: what it computes, and what it refuses to assert.

Covers :mod:`smartmatch_domain.attendance`. Two properties carry most of the
weight and each gets its own class: the total is *derived from* the breakdown
the same object carries, so a response cannot contradict itself; and a set of
counts that could not have come from one set of rows is refused rather than
summarized.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.attendance import (
    ATTENDANCE_METHODS,
    summarize_attendance,
)
from smartmatch_persistence.attendance import (
    ATTENDANCE_METHODS as PERSISTENCE_ATTENDANCE_METHODS,
)

FIRST = datetime(2026, 9, 1, 17, 0, tzinfo=UTC)
LAST = FIRST + timedelta(days=2)


def _summarize(**overrides: object):
    """Fold a canonical reading, with named parts replaced."""
    kwargs: dict[str, object] = {
        "method_counts": {"qr_scan": 12, "coordinator_entry": 3},
        "distinct_subjects": 9,
        "distinct_events": 4,
        "first_recorded_at": FIRST,
        "last_recorded_at": LAST,
    }
    kwargs.update(overrides)
    return summarize_attendance(**kwargs)  # type: ignore[arg-type]


class TestTheVocabularyIsSharedWithTheSchema:
    """One vocabulary, stated twice, held in step by this test."""

    def test_the_domain_and_persistence_method_sets_agree(self):
        """The convention `tests/authz/test_route_roles.py` states, applied here.

        Two literals rather than one import, because the layering contract
        forbids the domain reaching into persistence — and because two sets
        agreeing today is not a reason a widening of one should silently widen
        the other. Widening either without the other fails here.
        """
        assert ATTENDANCE_METHODS == PERSISTENCE_ATTENDANCE_METHODS

    def test_the_vocabulary_is_the_three_the_check_constraint_allows(self):
        """Pinned as a literal against `ck_attendance_record_method` (migration 0009)."""
        assert frozenset({"qr_scan", "coordinator_entry", "import"}) == ATTENDANCE_METHODS


class TestTheTotalIsAFoldOverTheBreakdown:
    """Fix #9's rule at the coordinator's level: the number is derived, not asserted."""

    def test_the_total_is_the_sum_of_the_breakdown_this_summary_carries(self):
        summary = _summarize()

        assert summary.total == sum(summary.by_method.values()) == 15

    def test_every_method_is_reported_even_with_no_rows(self):
        """ADR-0011 rule 1: a measured zero, not an absent key a client may misread."""
        summary = _summarize(method_counts={"qr_scan": 5}, distinct_subjects=4, distinct_events=2)

        assert summary.by_method == {"coordinator_entry": 0, "import": 0, "qr_scan": 5}

    def test_the_breakdown_is_read_only(self):
        """The response copies it; the fold's own mapping cannot be edited in place."""
        summary = _summarize()

        with pytest.raises(TypeError):
            summary.by_method["qr_scan"] = 999  # type: ignore[index]

    def test_a_unit_with_nothing_recorded_folds_to_a_measured_zero(self):
        """Zero rows is a fact about the unit, not an absence of one."""
        summary = _summarize(
            method_counts={},
            distinct_subjects=0,
            distinct_events=0,
            first_recorded_at=None,
            last_recorded_at=None,
        )

        assert summary.total == 0
        assert summary.by_method == {"coordinator_entry": 0, "import": 0, "qr_scan": 0}
        assert summary.first_recorded_at is None
        assert summary.last_recorded_at is None

    def test_the_bounds_are_carried_through_unchanged(self):
        summary = _summarize()

        assert (summary.first_recorded_at, summary.last_recorded_at) == (FIRST, LAST)

    def test_one_row_may_have_equal_bounds(self):
        """A single row is its own earliest and latest; that is not a contradiction."""
        summary = _summarize(
            method_counts={"import": 1},
            distinct_subjects=1,
            distinct_events=1,
            first_recorded_at=FIRST,
            last_recorded_at=FIRST,
        )

        assert summary.total == 1


class TestItRefusesWhatCannotBeTrue:
    """Counts that could not have come from one set of rows get no summary."""

    def test_a_method_outside_the_check_constraint_is_refused(self):
        with pytest.raises(ValueError, match="ck_attendance_record_method"):
            _summarize(method_counts={"self_reported": 1})

    def test_a_negative_method_count_is_refused(self):
        with pytest.raises(ValueError, match="negative"):
            _summarize(method_counts={"qr_scan": -1})

    @pytest.mark.parametrize("field", ["distinct_subjects", "distinct_events"])
    def test_a_negative_distinct_count_is_refused(self, field: str):
        with pytest.raises(ValueError, match="cannot be negative"):
            _summarize(**{field: -1})

    @pytest.mark.parametrize("field", ["distinct_subjects", "distinct_events"])
    def test_a_distinct_count_above_the_total_is_refused(self, field: str):
        """Distinct values cannot outnumber their rows; the two readings disagree."""
        with pytest.raises(ValueError, match="did not come from the same rows"):
            _summarize(**{field: 16})

    def test_a_bound_without_its_pair_is_refused(self):
        with pytest.raises(ValueError, match="both present or both absent"):
            _summarize(last_recorded_at=None)

    def test_a_bound_with_no_rows_is_refused(self):
        with pytest.raises(ValueError, match="no instant to report"):
            _summarize(
                method_counts={},
                distinct_subjects=0,
                distinct_events=0,
            )

    def test_rows_with_no_bounds_are_refused(self):
        """`created_at` is NOT NULL, so counted rows always have both bounds."""
        with pytest.raises(ValueError, match="both bounds must be present"):
            _summarize(first_recorded_at=None, last_recorded_at=None)

    def test_a_naive_bound_is_refused(self):
        with pytest.raises(ValueError, match="naive"):
            _summarize(first_recorded_at=datetime(2026, 9, 1, 17, 0))

    def test_a_first_bound_after_the_last_is_refused(self):
        with pytest.raises(ValueError, match="is after"):
            _summarize(first_recorded_at=LAST, last_recorded_at=FIRST)


class TestWhatASummaryNeverCarries:
    """The D8 claim in the module docstring, held as a test."""

    def test_the_summary_has_no_field_naming_a_person(self):
        summary = _summarize()
        fields = set(type(summary).__slots__)

        assert not {name for name in fields if "subject_id" in name or "name" in name}
        assert fields == {
            "total",
            "by_method",
            "distinct_subjects",
            "distinct_events",
            "first_recorded_at",
            "last_recorded_at",
        }
