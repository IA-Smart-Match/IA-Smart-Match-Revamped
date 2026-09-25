"""Unit tests for the class exercise's per-profile points counter.

The requirements row "Points" is *Not required*; its **nice to have** is "a
points counter per profile that rises with attendance and card completion".
These tests pin the two behaviours that phrase actually fixes — it rises with
attendance, it rises with card completion — and the one rule the platform
fixes for it: ADR-0011's ``unknown`` is never silently read as "no".

The point *values* are not fixed by any document. They live in
``exercise_points`` as clearly named placeholder constants, and these tests
assert relationships (monotonicity, additivity, unknown-earns-nothing) rather
than the literal numbers, so confirming the values is a register row and not a
test rewrite.
"""

from __future__ import annotations

import dataclasses

import pytest
from smartmatch_domain.exercise_points import (
    POINTS_PER_ATTENDANCE,
    POINTS_PER_COMPLETED_CARD,
    CardCompletion,
    ProfilePoints,
    ProfilePointsInput,
    profile_points,
)


def _events(
    attended: int = 0,
    card: CardCompletion = CardCompletion.UNKNOWN,
) -> ProfilePointsInput:
    return ProfilePointsInput(attended_count=attended, card_completion=card)


class TestRisesWithAttendance:
    def test_no_attendance_earns_no_attendance_points(self) -> None:
        assert profile_points(_events(attended=0)).attendance_points == 0

    def test_each_attendance_adds_the_same_named_amount(self) -> None:
        assert profile_points(_events(attended=3)).attendance_points == (3 * POINTS_PER_ATTENDANCE)

    @pytest.mark.parametrize("attended", [0, 1, 2, 5, 40])
    def test_points_never_fall_as_attendance_rises(self, attended: int) -> None:
        lower = profile_points(_events(attended=attended)).total
        higher = profile_points(_events(attended=attended + 1)).total
        assert higher > lower


class TestRisesWithCardCompletion:
    def test_a_completed_card_earns_the_named_amount(self) -> None:
        assert (
            profile_points(_events(card=CardCompletion.COMPLETED)).card_points
            == POINTS_PER_COMPLETED_CARD
        )

    def test_an_incomplete_card_earns_nothing(self) -> None:
        assert profile_points(_events(card=CardCompletion.NOT_COMPLETED)).card_points == 0

    def test_completing_a_card_raises_the_total_at_equal_attendance(self) -> None:
        without = profile_points(_events(attended=2, card=CardCompletion.NOT_COMPLETED))
        with_card = profile_points(_events(attended=2, card=CardCompletion.COMPLETED))
        assert with_card.total > without.total

    def test_total_is_the_sum_of_its_two_parts(self) -> None:
        points = profile_points(_events(attended=4, card=CardCompletion.COMPLETED))
        assert points.total == points.attendance_points + points.card_points


class TestUnknownStaysUnknown:
    """ADR-0011 rule 1: ``unknown`` is not ``0`` and is not "no"."""

    def test_unknown_card_earns_nothing(self) -> None:
        assert profile_points(_events(card=CardCompletion.UNKNOWN)).card_points == 0

    def test_unknown_card_is_reported_as_unknown_not_as_not_completed(self) -> None:
        unknown = profile_points(_events(attended=1, card=CardCompletion.UNKNOWN))
        answered = profile_points(_events(attended=1, card=CardCompletion.NOT_COMPLETED))
        assert unknown.card_completion_known is False
        assert answered.card_completion_known is True
        assert unknown.total == answered.total

    def test_the_card_completion_the_caller_gave_is_carried_back_verbatim(self) -> None:
        for card in CardCompletion:
            assert profile_points(_events(card=card)).card_completion is card


class TestInputValidationAndImmutability:
    def test_a_negative_attendance_count_is_refused(self) -> None:
        with pytest.raises(ValueError):
            profile_points(_events(attended=-1))

    @pytest.mark.parametrize("bad", [2.7, 2.0, True, "3", None])
    def test_an_attendance_count_that_is_not_a_whole_number_is_refused(self, bad: object) -> None:
        with pytest.raises(TypeError):
            profile_points(_events(attended=bad))  # type: ignore[arg-type]

    def test_the_input_is_frozen(self) -> None:
        events = _events(attended=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            events.attended_count = 2  # type: ignore[misc]

    def test_the_result_is_frozen(self) -> None:
        points = profile_points(_events(attended=1))
        with pytest.raises(dataclasses.FrozenInstanceError):
            points.total = 999  # type: ignore[misc]

    def test_the_result_is_a_profile_points_value(self) -> None:
        assert isinstance(profile_points(_events()), ProfilePoints)


class TestSurfaceStaysWithinTheExerciseInvariants:
    def test_the_result_carries_no_score_percentage_or_confidence(self) -> None:
        # ADR-0025 D8: points and head counts are the only numbers a class
        # participant may see. A rate on this object would be a second one.
        fields = {field.name for field in dataclasses.fields(ProfilePoints)}
        assert fields == {
            "attendance_points",
            "card_points",
            "total",
            "card_completion",
        }


def test_the_point_values_are_no_longer_marked_placeholders() -> None:
    """OQ-CE-10 closed 2026-09-25: one point each, confirmed by Ann."""
    from pathlib import Path

    from smartmatch_domain import exercise_points

    source = Path(exercise_points.__file__).read_text(encoding="utf-8")
    assert "PLACEHOLDER" not in source
    assert "OQ-CE-10 closed 2026-09-25" in source
