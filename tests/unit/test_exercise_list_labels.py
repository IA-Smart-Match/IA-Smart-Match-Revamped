"""What the list response says about the factors, and what it no longer says.

Ann's revisions of 2026-10-02 (item 4b) removed the rule that gave an
"Undecided" career goal half of "career goal fits this event" on a broad event.
With the rule went its plumbing: the ``undecided_goal_half`` flag on each list
entry and the extra ``factor_labels`` entry that worded it. This file pins the
response after the removal, on Ann's 300-row file, through the same
row-to-input steps the route uses.
"""

from __future__ import annotations

from functools import cache

from smartmatch_api.exercise_dependencies import ExerciseEventRow, TeamProfileRow
from smartmatch_api.routers.exercise_matching_models import (
    ListEntryView,
    RankedListView,
    event_evidence,
    rankable_set,
    ranked_list_view,
)
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.registry import EXERCISE_FACTOR_LABELS

from tests.unit.exercise_workbooks import ann_full_parsed

#: Card holders whose card says "Undecided" (see the Ann-dataset golden test).
_UNDECIDED_CARDS = (16, 30, 197, 202, 233, 289)
#: Card holders whose card goal fits Northline.
_FITTING_ON_NORTHLINE = (4, 108, 131, 178, 224)

_GOAL_ONLY = {
    "same_major": 0.0,
    "stated_interest_overlap": 0.0,
    "career_goal_fit": 1.0,
    "past_event_topic_overlap": 0.0,
}


@cache
def _rows() -> tuple[TeamProfileRow, ...]:
    return tuple(
        TeamProfileRow(
            profile_no=p.profile_no,
            display_name=p.display_name,
            major=p.major,
            class_year=p.class_year,
            past_event_keys=p.past_event_keys,
            stated_interests=p.stated_interests,
            career_goal=p.career_goal,
            overlay_added_event_topics=(),
            overlay_card_interests=None,
            overlay_card_career_goal=None,
            non_responding=False,
            tiebreak_order=p.tiebreak_order,
        )
        for p in ann_full_parsed().profiles
    )


@cache
def _events() -> tuple[ExerciseEventRow, ...]:
    return tuple(
        ExerciseEventRow(
            event_key=e.event_key,
            name=e.name,
            topic_tags=e.topic_tags,
            target_majors=e.target_majors,
            is_exercise_event=e.is_exercise_event,
            sequence=e.sequence,
        )
        for e in ann_full_parsed().events
    )


def _view(event_key: str) -> RankedListView:
    """The whole class ranked for one event on the career goal alone."""
    event = next(e for e in _events() if e.event_key == event_key)
    rankable = rankable_set(_rows(), _events())
    ranked = exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=_GOAL_ONLY,
        invite_limit=300,
        year_rank=rankable.year_rank,
        dataset_checksum=ann_full_parsed().checksum,
    )
    return ranked_list_view(ranked, rankable, event=event, weights=_GOAL_ONLY, setting_name=None)


def test_the_list_response_labels_exactly_the_four_factors() -> None:
    assert _view("E11").factor_labels == dict(EXERCISE_FACTOR_LABELS)


def test_the_response_carries_no_undecided_flag() -> None:
    assert "undecided_goal_half" not in ListEntryView.model_fields
    assert "undecided_goal_half" not in _view("E11").factor_labels


def test_an_undecided_card_is_never_told_its_goal_counted() -> None:
    """On Northline and Harbor alike: the two events the old rule reached."""
    for event_key in ("E11", "E12"):
        by_no = {entry.profile_no: entry for entry in _view(event_key).entries}
        for number in _UNDECIDED_CARDS:
            assert by_no[number].contributing_factor_keys == [], (event_key, number)
            assert "goal" not in by_no[number].reason.lower(), (event_key, number)


def test_a_goal_that_fits_northline_still_counts() -> None:
    by_no = {entry.profile_no: entry for entry in _view("E11").entries}
    for number in _FITTING_ON_NORTHLINE:
        assert by_no[number].contributing_factor_keys == ["career_goal_fit"], number


def test_the_csv_download_keeps_its_six_columns() -> None:
    """Design spec §8 names six columns."""
    from smartmatch_api.routers.exercise_matching_csv import CSV_LIST_COLUMNS

    assert len(CSV_LIST_COLUMNS) == 6


def test_each_list_row_carries_points_from_exercise_points() -> None:
    from smartmatch_domain.exercise_points import ProfilePointsInput, profile_points

    view = _view(_events()[0].event_key)
    rows = {r.profile_no: r for r in _rows()}
    for entry in view.entries:
        assert entry.points is not None
        expected = profile_points(
            ProfilePointsInput(
                attended_count=len(rows[entry.profile_no].past_event_keys),
                card_completion=_completion(entry.marker),
            )
        )
        assert entry.points.total == expected.total
        assert entry.points.attendance_points == expected.attendance_points


def _completion(marker: str):  # type: ignore[no-untyped-def]
    from smartmatch_domain.exercise_points import CardCompletion

    return CardCompletion.COMPLETED if marker == "completed_card" else CardCompletion.UNKNOWN
