"""Golden for #336: the ordering of round-two lift across asking choices.

Pins the ORDERING only (reward and required both lift more than promise), never
a count. The driver is ``asking_choice_lift``; it re-implements nothing, and
this file changes no coefficient. N = 20 fixed seeds, so the result is exact
and repeatable. What it does not say: that the spread is big enough for Ann's
lesson to show. At N = 100 the gap is 0.2 to 0.4 attendees of 30 against a
per-team sd near 3. That call is Chau's and Ann's (see
``docs/plans/sweep-drafts/336-asking-choice-lift.md``).
"""

from __future__ import annotations

import statistics

import pytest
from smartmatch_domain.exercise.asking import AskingChoice

from tests.golden.exercise.asking_choice_lift import measure

pytestmark = pytest.mark.golden

SEEDS = 20


@pytest.fixture(scope="module")
def mean_lift() -> dict[AskingChoice, float]:
    return {x.choice: statistics.fmean(x.lifts) for x in measure(SEEDS)}


def test_small_reward_lifts_more_than_promise(mean_lift: dict[AskingChoice, float]) -> None:
    assert mean_lift[AskingChoice.SMALL_REWARD] > mean_lift[AskingChoice.BETTER_RECOMMENDATIONS]


def test_required_lifts_more_than_promise(mean_lift: dict[AskingChoice, float]) -> None:
    assert mean_lift[AskingChoice.REQUIRED] > mean_lift[AskingChoice.BETTER_RECOMMENDATIONS]
