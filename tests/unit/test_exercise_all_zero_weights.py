"""All four weights at zero is refused in a sentence a class can read.

M2 B5: the refusal reached the screen as "…the resulting weights sum to zero;
every profile would score the same and the list would be the tie-break alone.
Refused rather than normalized into something plausible." That is a note for
an engineer. A team sees: "At least one number must be above 0."

The domain keeps its precise wording for logs and tests; the route chooses the
team's sentence by the refusal's type, not by matching its text.
"""

from __future__ import annotations

import pytest
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_matching_weights import validated
from smartmatch_domain.exercise.registry import (
    AllZeroExerciseWeightsError,
    InvalidExerciseWeightError,
    validate_exercise_weight_overrides,
)

_ALL_ZERO = {
    "same_major": 0.0,
    "stated_interest_overlap": 0.0,
    "career_goal_fit": 0.0,
    "past_event_topic_overlap": 0.0,
}

_TEAM_SENTENCE = "At least one number must be above 0."


def test_the_domain_names_the_all_zero_case_by_type() -> None:
    with pytest.raises(AllZeroExerciseWeightsError) as caught:
        validate_exercise_weight_overrides(_ALL_ZERO)
    assert isinstance(caught.value, InvalidExerciseWeightError)


def test_a_team_reads_one_plain_sentence() -> None:
    with pytest.raises(ExerciseError) as caught:
        validated(_ALL_ZERO)
    error = caught.value
    assert (error.status_code, error.code) == (422, "exercise_weights_invalid")
    assert error.message == _TEAM_SENTENCE


@pytest.mark.parametrize("word", ["sum to zero", "normalized", "tie-break", "Refused"])
def test_no_engineering_words_reach_the_team(word: str) -> None:
    with pytest.raises(ExerciseError) as caught:
        validated(_ALL_ZERO)
    assert word not in caught.value.message


def test_other_refusals_keep_their_own_detail() -> None:
    """Only the all-zero case changes; a negative weight still says which one."""
    with pytest.raises(ExerciseError) as caught:
        validated({**_ALL_ZERO, "same_major": -1.0})
    assert caught.value.message != _TEAM_SENTENCE
    assert "same_major" in caught.value.message
