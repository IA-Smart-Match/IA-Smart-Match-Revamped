""" "How much we know" and "who is on the list" (requirements; design spec §7)."""

from __future__ import annotations

from smartmatch_domain.exercise.markers import (
    INFORMATION_RANK,
    InformationMarker,
    derive_marker,
    information_rank,
    list_composition,
)
from smartmatch_domain.student_factors import ProfileCard, ProfileEvidence


def _profile(**kwargs: object) -> ProfileEvidence:
    return ProfileEvidence("p1", "Marketing", **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The marker
# ---------------------------------------------------------------------------


def test_major_only_when_nothing_else_is_on_file() -> None:
    assert derive_marker(_profile()) is InformationMarker.MAJOR_ONLY


def test_major_plus_events_when_a_past_event_was_attended() -> None:
    profile = _profile(attended_event_topics=(("analytics",),))
    assert derive_marker(profile) is InformationMarker.MAJOR_PLUS_EVENTS


def test_completed_card_wins_over_past_events() -> None:
    profile = _profile(card=ProfileCard(), attended_event_topics=(("analytics",),))
    assert derive_marker(profile) is InformationMarker.COMPLETED_CARD


def test_an_empty_card_is_still_a_completed_card() -> None:
    """The three-state rule: an empty card is not no card."""
    assert derive_marker(_profile(card=ProfileCard())) is InformationMarker.COMPLETED_CARD
    assert derive_marker(_profile(card=None)) is InformationMarker.MAJOR_ONLY


def test_an_attendance_record_naming_no_event_is_major_only() -> None:
    assert derive_marker(_profile(attended_event_topics=())) is InformationMarker.MAJOR_ONLY
    assert derive_marker(_profile(attended_event_topics=None)) is InformationMarker.MAJOR_ONLY


def test_information_rank_orders_the_three_groups() -> None:
    assert information_rank(InformationMarker.COMPLETED_CARD) == 2
    assert information_rank(InformationMarker.MAJOR_PLUS_EVENTS) == 1
    assert information_rank(InformationMarker.MAJOR_ONLY) == 0
    assert set(INFORMATION_RANK) == set(InformationMarker)


# ---------------------------------------------------------------------------
# The "who is on the list" table
# ---------------------------------------------------------------------------

EVERYONE = [
    ("Marketing", "Senior", InformationMarker.COMPLETED_CARD),
    ("Marketing", "Junior", InformationMarker.MAJOR_ONLY),
    ("Finance", "Senior", InformationMarker.MAJOR_PLUS_EVENTS),
    ("History", "Sophomore", InformationMarker.MAJOR_ONLY),
]
LISTED = EVERYONE[:2]


def test_counts_are_reported_for_the_list_beside_the_whole_set() -> None:
    composition = list_composition(LISTED, EVERYONE)
    assert dict(composition.by_major.on_list) == {"Marketing": 2}
    assert dict(composition.by_major.all_profiles) == {
        "Marketing": 2,
        "Finance": 1,
        "History": 1,
    }
    assert dict(composition.by_class_year.on_list) == {"Senior": 1, "Junior": 1}


def test_every_marker_row_exists_even_when_nobody_is_in_it() -> None:
    composition = list_composition(LISTED, EVERYONE)
    assert set(composition.by_marker.on_list) == {str(marker) for marker in InformationMarker}
    assert composition.by_marker.on_list["major_plus_events"] == 0
    assert composition.by_marker.all_profiles["major_only"] == 2


def test_the_empty_group_notice_is_composed_not_re_derived() -> None:
    """#161's coverage module answers this; §7 does not answer it again."""
    composition = list_composition(LISTED, EVERYONE)
    assert composition.coverage.missing_majors == ("Finance", "History")
    assert composition.coverage.missing_class_years == ("Sophomore",)
    assert composition.coverage.has_uncovered_group


def test_an_empty_list_leaves_every_group_uncovered() -> None:
    composition = list_composition([], EVERYONE)
    assert dict(composition.by_major.on_list) == {}
    assert composition.coverage.missing_majors == ("Marketing", "Finance", "History")
