"""Each list entry says whether its goal counted only as an undecided half.

OQ-CE-14 / D2: an "Undecided" career goal earns half of "career goal fits this
event" on an exploratory event. The reason line already words that half
differently; the screen also needs a flag to put a chip beside the name, so
``ListEntryView`` carries ``undecided_goal_half``.

The flag is true only when the half actually *counted*: the goal factor was
the undecided half **and** the team weighted it above zero. A chip saying
"undecided goal counted" beside a name whose goal weight is off would claim
something that did not happen — the same rule ``contributing_factor_keys``
follows.

Run on Ann's 300-row file, through the same row-to-input steps the route uses.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache

import pytest
from smartmatch_api.exercise_dependencies import ExerciseEventRow, TeamProfileRow
from smartmatch_api.routers.exercise_matching_models import (
    ListEntryView,
    event_evidence,
    rankable_set,
    ranked_list_view,
)
from smartmatch_domain.exercise.matching import ExerciseList, exercise_ranked_list

from tests.unit.exercise_workbooks import ann_full_parsed

#: Card holders whose card says "Undecided" (see the Ann-dataset golden test).
_UNDECIDED_CARDS = (16, 30, 197, 202, 233, 289)
#: Card holders whose card goal fits Northline.
_FITTING_ON_NORTHLINE = (4, 108, 131, 178, 224)
#: Card holders whose card says "Graduate school".
_GRADUATE_SCHOOL = (40, 44, 225, 239, 249)

_GOAL_ONLY = {
    "same_major": 0.0,
    "stated_interest_overlap": 0.0,
    "career_goal_fit": 1.0,
    "past_event_topic_overlap": 0.0,
}
_GOAL_OFF = {
    "same_major": 1.0,
    "stated_interest_overlap": 1.0,
    "career_goal_fit": 0.0,
    "past_event_topic_overlap": 1.0,
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
            is_exploratory=e.is_exploratory,
        )
        for e in ann_full_parsed().events
    )


def _event(event_key: str) -> ExerciseEventRow:
    return next(e for e in _events() if e.event_key == event_key)


def _ranked(event_key: str, weights: Mapping[str, float]) -> ExerciseList:
    rankable = rankable_set(_rows(), _events())
    return exercise_ranked_list(
        event_evidence(_event(event_key)),
        rankable.profiles,
        weights=weights,
        invite_limit=300,
        year_rank=rankable.year_rank,
        dataset_checksum=ann_full_parsed().checksum,
    )


def _flags(event_key: str, weights: Mapping[str, float]) -> dict[int, bool]:
    listing = _ranked(event_key, weights)
    return {int(entry.profile_id): entry.undecided_goal_half for entry in listing.entries}


@pytest.mark.parametrize("event_key", ["E11", "E12"])
def test_an_undecided_card_on_an_exploratory_round_is_flagged(event_key: str) -> None:
    flags = _flags(event_key, _GOAL_ONLY)
    assert all(flags[number] for number in _UNDECIDED_CARDS)
    assert not any(flags[number] for number in _GRADUATE_SCHOOL)


def test_a_goal_that_fits_is_not_flagged() -> None:
    flags = _flags("E11", _GOAL_ONLY)
    assert not any(flags[number] for number in _FITTING_ON_NORTHLINE)


def test_only_undecided_cards_are_flagged() -> None:
    """Undecided is the only goal that earns the half, so nobody else carries it."""
    flagged = {number for number, flag in _flags("E11", _GOAL_ONLY).items() if flag}
    undecided = {
        p.profile_no
        for p in ann_full_parsed().profiles
        if p.stated_interests is not None and p.career_goal == "Undecided"
    }
    assert flagged == undecided
    assert flagged


def test_nothing_is_flagged_on_an_event_that_is_not_exploratory() -> None:
    """E06, "Pitch Night: Student Startups", is a Competition."""
    assert not any(_flags("E06", _GOAL_ONLY).values())


def test_nothing_is_flagged_when_the_team_turned_the_goal_off() -> None:
    assert not any(_flags("E11", _GOAL_OFF).values())


def test_the_response_carries_the_flag() -> None:
    assert "undecided_goal_half" in ListEntryView.model_fields
    rankable = rankable_set(_rows(), _events())
    view = ranked_list_view(
        _ranked("E11", _GOAL_ONLY),
        rankable,
        event=_event("E11"),
        weights=_GOAL_ONLY,
        setting_name=None,
    )
    by_no = {entry.profile_no: entry.undecided_goal_half for entry in view.entries}
    assert all(by_no[number] for number in _UNDECIDED_CARDS)
    assert not any(by_no[number] for number in _FITTING_ON_NORTHLINE)


def test_the_flag_stays_off_the_csv_download() -> None:
    """Design spec §8 names six columns; a screen chip is not one of them."""
    from smartmatch_api.routers.exercise_matching_csv import CSV_LIST_COLUMNS

    assert "undecided_goal_half" not in CSV_LIST_COLUMNS
    assert len(CSV_LIST_COLUMNS) == 6
