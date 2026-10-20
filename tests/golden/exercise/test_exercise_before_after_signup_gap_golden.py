"""On Ann's 300-row file the before and after rows sign up different numbers.

Balanced (the default 3/3/2/2 weights), Harbor, the same seeds for both rows.
The before row ranks on what students said; the after row ranks once the
team has asked and the card answers (the hidden true interests) are known.
The gap between them is what the Before and After table exists to show.
"""

from __future__ import annotations

import statistics
from dataclasses import replace

import pytest
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_api.routers.exercise_results_models import simulation_event
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.simulation import EXERCISE_SIMULATION_COEFFICIENTS, simulate_results

from tests.golden.exercise.test_exercise_ann_dataset_golden import _dataset, _events, _rows
from tests.golden.exercise.test_exercise_results_rule_sample_golden import (
    INVITE_LIMIT,
    _simulation_profiles,
)

SEEDS = range(1, 201)


def _signed_up_by_seed(rows: tuple, event_key: str) -> list[int]:  # type: ignore[type-arg]
    assert EXERCISE_SIMULATION_COEFFICIENTS is not None
    events = _events()
    event = next(e for e in events if e.event_key == event_key)
    rankable = rankable_set(rows, events)
    listing = exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=None,
        invite_limit=INVITE_LIMIT,
        year_rank=rankable.year_rank,
        dataset_checksum=_dataset().checksum,
    )
    by_no = _simulation_profiles()
    invited = tuple(by_no[int(entry.profile_id)] for entry in listing.entries)
    rule_event = simulation_event(event)
    return [
        len(
            simulate_results(
                invited,
                rule_event,
                seed=seed,
                coefficients=EXERCISE_SIMULATION_COEFFICIENTS,
                invite_limit=INVITE_LIMIT,
            ).signed_up
        )
        for seed in SEEDS
    ]


@pytest.mark.golden
def test_asking_changes_how_many_sign_up_on_anns_file() -> None:
    hidden = {p.profile_no: p for p in _dataset().profiles}
    before = _rows()
    after = tuple(
        replace(
            row,
            overlay_card_interests=hidden[row.profile_no].hidden_true_interests,
            overlay_card_career_goal=hidden[row.profile_no].hidden_true_career_goal,
        )
        for row in before
    )
    gap = statistics.mean(_signed_up_by_seed(after, "E12")) - statistics.mean(
        _signed_up_by_seed(before, "E12")
    )
    assert gap != 0
