"""Golden cases for the exercise simulation's per-team determinism.

ADR-0025's verification line asks for golden cases under ``tests/golden/exercise/``
covering "the simulation's per-team determinism". That is the claim Ann and
Dr. Lin are given in plain words — *running the same list twice gives the same
answer* — and it is the one that a plausible implementation gets wrong without
failing anywhere else: design spec §11 writes the chance draw as
``random.Random(workspace.seed ^ hash(event_key))``, and ``hash()`` of a string
is salted per process, so the same team's list gives different results in
tomorrow's process. The subprocess case below is the test that catches it; the
pinned outcome above it is the value that must not drift.

Every coefficient set here is **test-only**. OQ-CE-03 is open and the module
ships none.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest
from smartmatch_domain.exercise.simulation import (
    SimulationCoefficients,
    SimulationEvent,
    SimulationProfile,
    run_email_everyone,
)

GOLDEN_SEED = 20270333
GOLDEN_EVENT_KEY = "northline"

# Test-only. NOT a proposal for OQ-CE-03.
GOLDEN_COEFFICIENTS = SimulationCoefficients(
    base_signup_rate=0.20,
    true_fit_lift=0.50,
    frequent_attender_lift=0.06,
    same_major_lift=0.09,
    chance_spread=0.12,
    attend_given_signup=0.85,
    frequent_attender_events=3,
    true_interest_share_of_fit=0.5,
)

GOLDEN_EVENT = SimulationEvent(
    event_key=GOLDEN_EVENT_KEY,
    topic_tags=frozenset({"analytics", "consumer_insight", "data_career"}),
    target_majors=frozenset({"marketing", "business_analytics"}),
)


def _golden_profiles() -> tuple[SimulationProfile, ...]:
    """Twelve profiles, one per branch of the rule and a few combinations."""
    return (
        # True interests fit, career goal fits, wrong major, no history.
        SimulationProfile(1, "history", frozenset({"analytics"}), "data_career"),
        # True interests fit only.
        SimulationProfile(2, "history", frozenset({"consumer_insight"}), "stage_career"),
        # Career goal fits only.
        SimulationProfile(3, "history", frozenset({"theatre"}), "data_career"),
        # Neither fits.
        SimulationProfile(4, "history", frozenset({"theatre"}), "stage_career"),
        # Same major only.
        SimulationProfile(5, "marketing", frozenset({"theatre"}), "stage_career"),
        # Frequent attender only, at the threshold.
        SimulationProfile(6, "history", frozenset({"theatre"}), "stage_career", 3),
        # Frequent attender, one below the threshold.
        SimulationProfile(7, "history", frozenset({"theatre"}), "stage_career", 2),
        # Everything at once.
        SimulationProfile(8, "marketing", frozenset({"analytics"}), "data_career", 9),
        # Unknown career goal, true interests fit (ADR-0011: no penalty).
        SimulationProfile(9, "business_analytics", frozenset({"analytics"}), None, 1),
        # Nothing on file at all beyond a major.
        SimulationProfile(10, "history"),
        # Non-responding despite a perfect fit (§13, round two).
        SimulationProfile(11, "marketing", frozenset({"analytics"}), "data_career", 9, True),
        # Terms that need trimming and case folding before they match.
        SimulationProfile(12, " MARKETING ", frozenset({" Analytics "}), "DATA_CAREER"),
    )


#: The pinned outcome. If a change to the rule moves these, that is a change to
#: what Ann and Dr. Lin were told, and the docstring in ``simulation.py`` has to
#: move with it.
#:
#: Regenerated once, deliberately, in review: the uniform draw moved from 64
#: bits over ``2 ** 64`` (which rounds the largest digests to exactly ``1.0``,
#: so the documented half-open interval was false) to the top 53 bits over
#: ``2 ** 53``, and the digest's fields became length-prefixed. Both change
#: every draw. The seed moved with them, to one whose run has a sign-up that
#: does not attend, so the golden still exercises that branch. Making the
#: true-fit split a coefficient did **not** move these: at
#: ``true_interest_share_of_fit=0.5`` it reproduces the previous values
#: exactly, which was checked against the old draw before repinning.
GOLDEN_SIGNED_UP = (1, 2, 6, 8, 9, 12)
GOLDEN_ATTENDED = (1, 6, 8, 12)


@pytest.mark.golden
def test_the_pinned_run_does_not_drift():
    result = run_email_everyone(
        _golden_profiles(),
        GOLDEN_EVENT,
        seed=GOLDEN_SEED,
        coefficients=GOLDEN_COEFFICIENTS,
    )
    assert result.invited == tuple(range(1, 13))
    assert result.signed_up == GOLDEN_SIGNED_UP
    assert result.attended == GOLDEN_ATTENDED


@pytest.mark.golden
def test_the_non_responding_profile_is_absent_despite_a_perfect_fit():
    result = run_email_everyone(
        _golden_profiles(),
        GOLDEN_EVENT,
        seed=GOLDEN_SEED,
        coefficients=GOLDEN_COEFFICIENTS,
    )
    assert 11 in result.invited
    assert 11 not in result.signed_up
    # Profile 8 is profile 11 without `non_responding`, and it did sign up, so
    # the absence is the flag and not the fit.
    assert 8 in result.signed_up


_SUBPROCESS_SOURCE = textwrap.dedent(
    """
    import json
    import sys

    sys.path[:] = json.loads(sys.argv[1])

    from smartmatch_domain.exercise.simulation import (
        SimulationCoefficients,
        SimulationEvent,
        SimulationProfile,
        run_email_everyone,
    )

    coefficients = SimulationCoefficients(
        base_signup_rate=0.20,
        true_fit_lift=0.50,
        frequent_attender_lift=0.06,
        same_major_lift=0.09,
        chance_spread=0.12,
        attend_given_signup=0.85,
        frequent_attender_events=3,
        true_interest_share_of_fit=0.5,
    )
    event = SimulationEvent(
        event_key="northline",
        topic_tags=frozenset({"analytics", "consumer_insight", "data_career"}),
        target_majors=frozenset({"marketing", "business_analytics"}),
    )
    profiles = tuple(
        SimulationProfile(
            profile_no=row[0],
            major=row[1],
            true_interests=frozenset(row[2]),
            career_goal=row[3],
            past_event_count=row[4],
            non_responding=row[5],
        )
        for row in json.loads(sys.argv[2])
    )
    result = run_email_everyone(profiles, event, seed=int(sys.argv[3]), coefficients=coefficients)
    print(json.dumps({"signed_up": result.signed_up, "attended": result.attended}))
    """
)


def _run_in_subprocess(hash_seed: str) -> dict[str, list[int]]:
    """Run the golden case in a fresh interpreter under a given hash seed."""
    rows = [
        [
            profile.profile_no,
            profile.major,
            sorted(profile.true_interests),
            profile.career_goal,
            profile.past_event_count,
            profile.non_responding,
        ]
        for profile in _golden_profiles()
    ]
    environment = {**os.environ, "PYTHONHASHSEED": hash_seed}
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _SUBPROCESS_SOURCE,
            json.dumps(sys.path),
            json.dumps(rows),
            str(GOLDEN_SEED),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    parsed: dict[str, list[int]] = json.loads(completed.stdout)
    return parsed


@pytest.mark.golden
@pytest.mark.parametrize("hash_seed", ["0", "1", "12345", "random"])
def test_a_fresh_process_under_a_different_hash_seed_gives_the_same_result(
    hash_seed: str,
):
    """The test that catches ``hash(event_key)``.

    ``PYTHONHASHSEED`` changes ``hash()`` of a string and nothing else that
    this rule touches. A rule seeded on ``hash()`` returns a different answer
    here; a rule seeded on a digest returns the pinned one.
    """
    parsed = _run_in_subprocess(hash_seed)
    assert tuple(parsed["signed_up"]) == GOLDEN_SIGNED_UP
    assert tuple(parsed["attended"]) == GOLDEN_ATTENDED


@pytest.mark.golden
def test_two_teams_on_one_list_get_two_answers_and_neither_moves_the_other():
    """Per-team determinism: the seed is the whole of the per-team state."""
    profiles = _golden_profiles()
    team_a = run_email_everyone(
        profiles, GOLDEN_EVENT, seed=GOLDEN_SEED, coefficients=GOLDEN_COEFFICIENTS
    )
    team_b = run_email_everyone(
        profiles, GOLDEN_EVENT, seed=GOLDEN_SEED + 1, coefficients=GOLDEN_COEFFICIENTS
    )
    team_a_again = run_email_everyone(
        profiles, GOLDEN_EVENT, seed=GOLDEN_SEED, coefficients=GOLDEN_COEFFICIENTS
    )
    assert team_a != team_b
    assert team_a == team_a_again
