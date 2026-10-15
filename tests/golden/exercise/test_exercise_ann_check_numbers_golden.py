"""Ann Wang's check numbers, pinned so the rule cannot drift from her ruling.

What Ann asked (Ann Wang, email 2026-10-10, Q2): "a suggested list of 30 should
add about 6 sign-ups at Northline and about 4 to 5 at Harbor over the mass
email alone."

The ruled rule: the mass email reaches all 300 and 20 in 100 notice it; the
team's 30 also get the CBACH email and 60 in 100 notice it; a profile that
noticed signs up by Step B (5 in 100 to start, +35 true interest, +15 true
goal, +5 per past event up to +15, +5 same major); 65 in 100
of those show up; no extra luck; one seed per team.

On her Oct 2 file, with the app's suggested 30 at weights 3/3/2/2, this gives
(mean of 5,000 seeds, after the 2026-10-15 rule) K = 6.3 at Northline and 5.2 at Harbor. N is the
mass-email-alone sign-ups, K the sign-ups the list adds, M = N + K.

If this test fails, the rule drifted from Ann's ruling - do not re-pin without
her written OK. Rule docs: docs/decisions/class-exercise-results-rule-2026-10-10.md
and docs/decisions/class-exercise-current-rule.md.
"""

from __future__ import annotations

import statistics
from functools import cache

import pytest
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_api.routers.exercise_results_models import simulation_event
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.simulation import (
    EXERCISE_SIMULATION_COEFFICIENTS,
    run_email_everyone,
    simulate_results,
)

from tests.golden.exercise.test_exercise_ann_dataset_golden import _dataset, _events, _rows
from tests.golden.exercise.test_exercise_results_rule_sample_golden import (
    INVITE_LIMIT,
    _simulation_profiles,
)

#: Ann's default weights 3/3/2/2 (the app's own default when weights is None).
#: Seeds averaged in CI; the 5,000-seed means (6.3 / 5.2) are in the docs.
MEAN_SEEDS = 200

#: Exact (N, K, M) per seed 1-5, from the real code path.
PINNED_SEEDS = {
    "E11": {1: (10, 5, 15), 2: (5, 9, 14), 3: (11, 10, 21), 4: (7, 8, 15), 5: (14, 6, 20)},
    "E12": {1: (15, 2, 17), 2: (12, 6, 18), 3: (13, 2, 15), 4: (10, 4, 14), 5: (5, 4, 9)},
}


@cache
def _setup(event_key: str):
    events = _events()
    event = next(e for e in events if e.event_key == event_key)
    rankable = rankable_set(_rows(), events)
    listing = exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=None,
        invite_limit=INVITE_LIMIT,
        year_rank=rankable.year_rank,
        dataset_checksum=_dataset().checksum,
    )
    by_no = _simulation_profiles()
    invited = tuple(by_no[int(e.profile_id)] for e in listing.entries)
    return tuple(by_no.values()), invited, simulation_event(event)


def nkm(event_key: str, seed: int) -> tuple[int, int, int]:
    """(N, K, M) for one team seed through the production path."""
    assert EXERCISE_SIMULATION_COEFFICIENTS is not None
    everyone, invited, event = _setup(event_key)
    mass = run_email_everyone(
        everyone, event, seed=seed, coefficients=EXERCISE_SIMULATION_COEFFICIENTS
    )
    team = simulate_results(
        invited,
        event,
        seed=seed,
        coefficients=EXERCISE_SIMULATION_COEFFICIENTS,
        invite_limit=INVITE_LIMIT,
    )
    n = len(mass.signed_up)
    m = len(set(mass.signed_up) | set(team.signed_up))
    return n, m - n, m


@pytest.mark.golden
@pytest.mark.parametrize(
    ("event_key", "seed"), [(e, s) for e, d in PINNED_SEEDS.items() for s in d]
)
def test_per_seed_n_k_m_are_pinned(event_key: str, seed: int) -> None:
    assert nkm(event_key, seed) == PINNED_SEEDS[event_key][seed]


@pytest.mark.golden
@pytest.mark.parametrize(
    ("event_key", "mean_k", "low", "high"),
    [("E11", 6.4, 5.5, 8.0), ("E12", 5.1, 4.0, 5.5)],
)
def test_mean_lift_matches_anns_check(
    event_key: str, mean_k: float, low: float, high: float
) -> None:
    mean = statistics.mean(nkm(event_key, s)[1] for s in range(1, MEAN_SEEDS + 1))
    assert abs(mean - mean_k) <= 0.6, mean
    assert low <= mean <= high, mean
