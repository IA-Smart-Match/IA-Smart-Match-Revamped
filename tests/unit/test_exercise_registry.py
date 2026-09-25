"""``EXERCISE_REGISTRY`` is a second rulebook, and it changes nothing about the first.

Design spec §4.3. The claim PR #173 made is that the registry mechanism is
parameterised; this file is the first *product* registry to sit beside
:data:`~smartmatch_domain.factor_registry.CBA_REGISTRY` and prove it, and it
pins the three things that keep the two apart: an unmistakable version, its own
closed mode vocabulary, and equal defaults that Ann confirmed (OQ-CE-02,
closed 2026-09-25).
"""

from __future__ import annotations

import pytest
from smartmatch_domain.exercise.registry import (
    CAREER_GOAL_FIT_DEFAULT_WEIGHT,
    EXERCISE_APPROVED_ON,
    EXERCISE_APPROVED_SCORING_KEYS,
    EXERCISE_APPROVER,
    EXERCISE_DEFAULT_WEIGHTS,
    EXERCISE_FACTOR_LABELS,
    EXERCISE_MODE_VOCABULARY,
    EXERCISE_REGISTRY,
    EXERCISE_REGISTRY_VERSION,
    EXERCISE_SCORING_MODE,
    EXERCISE_STATUS,
    PAST_EVENT_TOPIC_OVERLAP_DEFAULT_WEIGHT,
    SAME_MAJOR_DEFAULT_WEIGHT,
    STATED_INTEREST_OVERLAP_DEFAULT_WEIGHT,
    InvalidExerciseWeightError,
    exercise_applied_weights,
    validate_exercise_weight_overrides,
)
from smartmatch_domain.factor_registry import (
    CBA_REGISTRY,
    REGISTRY_VERSION,
    SUPERSEDED_REGISTRY_VERSION,
    UnknownScoringModeError,
    assert_registry_approved,
    assert_scoring_ready,
    factor_keys,
    implemented_scoring_keys,
    normalize_weights,
    registry_for_version,
    resolve_scoring_model,
)
from smartmatch_domain.factors.proximity import CBA_SCORING_MODES
from smartmatch_domain.student_factors import STUDENT_FACTOR_KEYS

# ---------------------------------------------------------------------------
# Contents
# ---------------------------------------------------------------------------


def test_the_registry_declares_the_four_shared_factors() -> None:
    assert factor_keys(registry=EXERCISE_REGISTRY) == STUDENT_FACTOR_KEYS
    assert frozenset(STUDENT_FACTOR_KEYS) == EXERCISE_APPROVED_SCORING_KEYS
    assert all(spec.implemented for spec in EXERCISE_REGISTRY.factors)
    assert not any(spec.is_retired for spec in EXERCISE_REGISTRY.factors)


def test_the_registry_is_approved_on_anns_authority() -> None:
    assert EXERCISE_STATUS == "approved"
    assert EXERCISE_APPROVER == "Ann Wang, class-exercise requirements 2026-09-15"
    assert EXERCISE_APPROVED_ON == "2026-09-15"
    assert EXERCISE_REGISTRY.approver == EXERCISE_APPROVER
    assert_registry_approved(registry=EXERCISE_REGISTRY)


def test_the_factors_are_labelled_in_anns_plain_words() -> None:
    """Requirements "Matching", verbatim. A class participant reads these."""
    assert dict(EXERCISE_FACTOR_LABELS) == {
        "same_major": "same major",
        "stated_interest_overlap": "said they are interested in this topic",
        "career_goal_fit": "career goal fits this event",
        "past_event_topic_overlap": "went to similar events before",
    }
    for spec in EXERCISE_REGISTRY.factors:
        assert spec.display_label == EXERCISE_FACTOR_LABELS[spec.key]


def test_default_weights_are_the_oq_ce_02_equal_set() -> None:
    """OQ-CE-02 closed 2026-09-25: equal, named, and teams decide the rest."""
    assert SAME_MAJOR_DEFAULT_WEIGHT == 0.25
    assert STATED_INTEREST_OVERLAP_DEFAULT_WEIGHT == 0.25
    assert CAREER_GOAL_FIT_DEFAULT_WEIGHT == 0.25
    assert PAST_EVENT_TOPIC_OVERLAP_DEFAULT_WEIGHT == 0.25
    assert set(EXERCISE_DEFAULT_WEIGHTS.values()) == {0.25}


def test_the_default_weights_are_no_longer_marked_placeholders() -> None:
    """Ann confirmed equal weights; a marker left behind would be untrue."""
    from pathlib import Path

    from smartmatch_domain.exercise import registry

    source = Path(registry.__file__).read_text(encoding="utf-8")
    assert "PLACEHOLDER (OQ-CE-02" not in source
    assert "OQ-CE-02 closed 2026-09-25" in source


def test_the_gates_pass_for_the_exercise_rulebook() -> None:
    assert_scoring_ready(registry=EXERCISE_REGISTRY)
    assert implemented_scoring_keys(registry=EXERCISE_REGISTRY) == EXERCISE_APPROVED_SCORING_KEYS
    applied = exercise_applied_weights()
    assert sum(applied.values()) == pytest.approx(1.0, abs=1e-9)
    assert set(applied) == EXERCISE_APPROVED_SCORING_KEYS


# ---------------------------------------------------------------------------
# It cannot be confused with the CBA rulebook
# ---------------------------------------------------------------------------


def test_the_version_cannot_collide_with_or_resemble_a_cba_pin() -> None:
    assert EXERCISE_REGISTRY_VERSION == "exercise-0.1.0"
    assert EXERCISE_REGISTRY_VERSION not in {REGISTRY_VERSION, SUPERSEDED_REGISTRY_VERSION}
    for pin in (REGISTRY_VERSION, SUPERSEDED_REGISTRY_VERSION):
        assert not EXERCISE_REGISTRY_VERSION.startswith(pin[:3])
        assert "cba" not in EXERCISE_REGISTRY_VERSION


def test_the_mode_vocabulary_is_its_own_and_closed() -> None:
    assert frozenset({"exercise-1"}) == EXERCISE_MODE_VOCABULARY
    assert not EXERCISE_MODE_VOCABULARY & CBA_SCORING_MODES
    with pytest.raises(UnknownScoringModeError):
        resolve_scoring_model("cba-physical-1", registry=EXERCISE_REGISTRY)
    with pytest.raises(UnknownScoringModeError):
        # No pre-mode model: only the CBA rulebook has one.
        resolve_scoring_model(None, registry=EXERCISE_REGISTRY)
    assert (
        resolve_scoring_model(EXERCISE_SCORING_MODE, registry=EXERCISE_REGISTRY).scoring_mode
        == EXERCISE_SCORING_MODE
    )


def test_the_exercise_rulebook_is_findable_only_by_its_own_version() -> None:
    assert registry_for_version(EXERCISE_REGISTRY_VERSION) is EXERCISE_REGISTRY
    assert registry_for_version(REGISTRY_VERSION) is CBA_REGISTRY
    assert registry_for_version(SUPERSEDED_REGISTRY_VERSION) is CBA_REGISTRY


def test_the_cba_defaults_are_untouched_by_the_second_registry() -> None:
    cba = normalize_weights()
    assert sum(cba.values()) == pytest.approx(1.0, abs=1e-9)
    assert set(cba) == CBA_REGISTRY.approved_scoring_keys
    assert not set(cba) & EXERCISE_APPROVED_SCORING_KEYS


# ---------------------------------------------------------------------------
# The exercise weight validator
# ---------------------------------------------------------------------------


def test_an_empty_override_map_is_valid_and_means_use_the_defaults() -> None:
    assert dict(validate_exercise_weight_overrides({})) == {}


def test_a_team_may_set_any_subset_of_the_four() -> None:
    assert dict(validate_exercise_weight_overrides({"same_major": 2.0})) == {"same_major": 2.0}


def test_an_unknown_key_is_refused_not_ignored() -> None:
    with pytest.raises(InvalidExerciseWeightError, match="industry_match"):
        validate_exercise_weight_overrides({"industry_match": 1.0})


def test_a_cba_factor_key_is_not_configurable_here() -> None:
    with pytest.raises(InvalidExerciseWeightError):
        validate_exercise_weight_overrides({"proximity": 1.0})


def test_every_problem_is_named_at_once() -> None:
    with pytest.raises(InvalidExerciseWeightError) as raised:
        validate_exercise_weight_overrides({"nonsense": 1.0, "same_major": -1.0})
    message = str(raised.value)
    assert "nonsense" in message
    assert "same_major" in message


def test_zeroing_every_factor_is_refused_rather_than_normalized() -> None:
    with pytest.raises(InvalidExerciseWeightError, match="sum to zero"):
        validate_exercise_weight_overrides(dict.fromkeys(STUDENT_FACTOR_KEYS, 0.0))


@pytest.mark.parametrize("bad", [True, "0.5", None, float("nan"), float("inf")])
def test_a_weight_that_is_not_a_finite_number_is_refused(bad: object) -> None:
    with pytest.raises(InvalidExerciseWeightError):
        validate_exercise_weight_overrides({"same_major": bad})
