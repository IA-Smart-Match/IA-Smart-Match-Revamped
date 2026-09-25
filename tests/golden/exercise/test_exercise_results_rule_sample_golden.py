"""The OQ-CE-03 sample result, pinned so the document Chau forwards stays true.

``docs/plans/open-questions/oq-ce-03-sample-result.md`` reports what the
shipped coefficient set does on Ann's 300-row file: for Northline (E11) and
Harbor (E12), three invited lists of thirty — the default equal weights, "said
they are interested" alone, and "same major" alone — each run through the
results rule. Every number in that document is computed here, through the
production path (ingest, the API's row-to-input steps, the ranker, the rule),
and pinned. If a change moves one of them, the document is regenerated with it:
it is what Ann and Chau were shown.

Two readings are pinned: one example team (a fixed seed), and the average over
:data:`TEAMS` teams, which is what "a typical team" means in the document.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache

import pytest
from smartmatch_api.exercise_dependencies import SimulationProfileRow
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_api.routers.exercise_results_models import simulation_event, simulation_profiles
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.simulation import (
    EXERCISE_SIMULATION_COEFFICIENTS,
    SimulationProfile,
    seats_empty,
    simulate_results,
)

from tests.golden.exercise.test_exercise_ann_dataset_golden import _dataset, _events, _rows

#: The example team's seed. Any fixed number; this one is the date of Ann's answer.
EXAMPLE_SEED = 20260925

#: How many teams the average is taken over. Seeds 1 to this.
TEAMS = 1000

#: The invite limit of the case: "time to personally invite only 30 people".
INVITE_LIMIT = 30

#: The three lists, by the plain words the document uses.
WEIGHTINGS: Mapping[str, Mapping[str, float] | None] = {
    "equal weights": None,
    "said they are interested": {
        "same_major": 0.0,
        "stated_interest_overlap": 1.0,
        "career_goal_fit": 0.0,
        "past_event_topic_overlap": 0.0,
    },
    "same major": {
        "same_major": 1.0,
        "stated_interest_overlap": 0.0,
        "career_goal_fit": 0.0,
        "past_event_topic_overlap": 0.0,
    },
}


@dataclass(frozen=True, slots=True)
class SampleRow:
    """One line of the document's table."""

    signed_up: int
    attended: int
    seats_empty: int
    average_signed_up: float
    average_attended: float


@cache
def _simulation_profiles() -> dict[int, SimulationProfile]:
    rows = tuple(
        SimulationProfileRow(
            profile_no=p.profile_no,
            display_name=p.display_name,
            major=p.major,
            class_year=p.class_year,
            past_event_keys=p.past_event_keys,
            stated_interests=p.stated_interests,
            career_goal=p.career_goal,
            hidden_true_interests=p.hidden_true_interests,
            hidden_true_career_goal=p.hidden_true_career_goal,
        )
        for p in _dataset().profiles
    )
    profiles = simulation_profiles(rows, non_responding_profile_nos=frozenset())
    return {profile.profile_no: profile for profile in profiles}


@cache
def sample_row(event_key: str, weighting: str) -> SampleRow:
    """The document's numbers for one event and one list."""
    assert EXERCISE_SIMULATION_COEFFICIENTS is not None
    events = _events()
    event = next(e for e in events if e.event_key == event_key)
    rankable = rankable_set(_rows(), events)
    listing = exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=WEIGHTINGS[weighting],
        invite_limit=INVITE_LIMIT,
        year_rank=rankable.year_rank,
        dataset_checksum=_dataset().checksum,
    )
    by_no = _simulation_profiles()
    invited = tuple(by_no[int(entry.profile_id)] for entry in listing.entries)
    rule_event = simulation_event(event)

    def run(seed: int) -> tuple[int, int]:
        result = simulate_results(
            invited,
            rule_event,
            seed=seed,
            coefficients=EXERCISE_SIMULATION_COEFFICIENTS,
            invite_limit=INVITE_LIMIT,
        )
        return len(result.signed_up), len(result.attended)

    signed, attended = run(EXAMPLE_SEED)
    many = [run(seed) for seed in range(1, TEAMS + 1)]
    return SampleRow(
        signed_up=signed,
        attended=attended,
        seats_empty=seats_empty(attended),
        average_signed_up=round(statistics.mean(s for s, _ in many), 1),
        average_attended=round(statistics.mean(a for _, a in many), 1),
    )


#: The pinned table: (event, list) -> (signed up, attended, seats empty,
#: average signed up, average attended). Copied into the document.
PINNED: Mapping[tuple[str, str], tuple[int, int, int, float, float]] = {
    ("E11", "equal weights"): (8, 7, 45, 9.5, 7.1),
    ("E11", "said they are interested"): (12, 10, 42, 6.8, 5.1),
    ("E11", "same major"): (7, 6, 46, 8.1, 6.0),
    ("E12", "equal weights"): (8, 6, 46, 7.5, 5.6),
    ("E12", "said they are interested"): (11, 7, 45, 8.9, 6.7),
    ("E12", "same major"): (7, 7, 45, 7.1, 5.3),
}


@pytest.mark.golden
@pytest.mark.parametrize(("event_key", "weighting"), list(PINNED))
def test_the_sample_result_in_the_document_is_what_the_rule_gives(
    event_key: str, weighting: str
) -> None:
    row = sample_row(event_key, weighting)
    assert (
        row.signed_up,
        row.attended,
        row.seats_empty,
        row.average_signed_up,
        row.average_attended,
    ) == PINNED[(event_key, weighting)]


@pytest.mark.golden
def test_both_events_are_exploratory_in_the_sample() -> None:
    """Ann: "Treat both Northline and Harbor as exploratory"."""
    assert {e.event_key for e in _events() if e.is_exploratory} >= {"E11", "E12"}
