"""Tests for the canonical factor registry.

The central test here is :func:`test_implemented_scoring_weights_sum_to_one`,
which encodes the defect found in the legacy baseline so it cannot recur.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.factor_registry import (
    PROHIBITED_INPUTS,
    PROPOSED_FACTORS,
    FactorKind,
    FactorSpec,
    RegistryNotApprovedError,
    active_weights,
    assert_registry_approved,
    factor_keys,
    normalize_weights,
    proposed_weights,
)


def test_factor_keys_are_unique():
    """A duplicated key would silently shadow a factor in the weight mapping."""
    keys = factor_keys()
    assert len(keys) == len(set(keys))


def test_implemented_scoring_weights_sum_to_one():
    """Regression guard for the legacy score-deflation defect.

    Legacy evidence: ``config.FACTOR_REGISTRY`` declared 9 factors summing to
    1.00 while ``engine.compute_match_score`` computed only 7 of them, capping
    every attainable score at 0.90. Here the normalized weights range over
    exactly the implemented scoring factors, so the sum is 1.0 by construction.
    """
    weights = normalize_weights()
    assert weights, "no implemented scoring factors — normalization is vacuous"
    assert sum(weights.values()) == pytest.approx(1.0)


def test_unimplemented_factors_contribute_no_active_weight():
    """The structural half of the same guard.

    A factor may be *proposed* with a nonzero weight before it is built — that
    is what a proposal is for. What it must never do is contribute active weight,
    because active weight is what normalization divides by.
    """
    for spec in PROPOSED_FACTORS:
        if not spec.implemented:
            assert spec.active_weight == 0.0, (
                f"{spec.key} is unimplemented but contributes active weight "
                f"{spec.active_weight} — this is the legacy deflation defect"
            )


def test_active_weights_exclude_proposed_but_unbuilt_factors():
    """The proposed set is strictly larger than the active set today."""
    proposed = proposed_weights()
    active = active_weights()

    assert set(active) < set(proposed)
    assert "engagement_load" in active
    # Proposed but not yet built, so it must not appear in the active mapping.
    assert "topic_relevance" in proposed
    assert "topic_relevance" not in active


def test_proposed_scoring_weights_sum_to_one():
    """The registry proposal is internally consistent as a proposal."""
    total = sum(spec.proposed_weight for spec in PROPOSED_FACTORS if spec.is_scoring)
    assert total == pytest.approx(1.0)


def test_eligibility_factors_carry_no_stage_b_weight():
    """Stage A filters are not scored; giving them weight conflates the stages."""
    with pytest.raises(ValueError, match="Stage A"):
        FactorSpec(
            key="bad_eligibility",
            display_label="Bad",
            kind=FactorKind.ELIGIBILITY,
            proposed_weight=0.10,
            implemented=True,
            rationale="eligibility factors must not be scored",
        )


def test_eligibility_factors_are_never_scoring():
    for spec in PROPOSED_FACTORS:
        if spec.kind is FactorKind.ELIGIBILITY:
            assert not spec.is_scoring
            assert spec.active_weight == 0.0


def test_weight_out_of_range_is_rejected():
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        FactorSpec(
            key="oversized",
            display_label="Oversized",
            kind=FactorKind.SUITABILITY,
            proposed_weight=1.5,
            implemented=True,
            rationale="out of range",
        )


def test_only_one_scoring_factor_is_implemented_today():
    """Documents the current Foundation state, and guards the test below.

    Only ``engagement_load`` is built. Normalization is therefore degenerate —
    it returns 1.0 for that single factor — and the rebalancing test below is
    skipped until a second scoring factor lands. When one does, this test fails
    and forces both to be revisited together, which is the point.
    """
    assert set(normalize_weights()) == {"engagement_load"}


def test_normalize_weights_honours_overrides_and_renormalizes():
    """An override changes the balance but never breaks the sum-to-one invariant."""
    base = normalize_weights()
    if len(base) < 2:
        pytest.skip("needs two implemented scoring factors to observe rebalancing")

    key, other = list(base)[:2]
    bumped = normalize_weights({key: base[key] * 10.0})

    assert sum(bumped.values()) == pytest.approx(1.0)
    assert bumped[key] > base[key]
    assert bumped[other] < base[other]


def test_normalize_weights_ignores_unknown_and_unimplemented_keys():
    """Unknown keys cannot inject weight mass into the mapping."""
    weights = normalize_weights({"not_a_factor": 5.0, "topic_relevance": 5.0})
    assert "not_a_factor" not in weights
    # topic_relevance is declared but unimplemented, so it is not a scoring key.
    assert "topic_relevance" not in weights
    assert sum(weights.values()) == pytest.approx(1.0)


def test_normalize_weights_rejects_negative_weights():
    with pytest.raises(ValueError, match="must not be negative"):
        normalize_weights({"engagement_load": -0.5})


def test_normalize_weights_all_zero_returns_zeros_not_nan():
    """A zero total must not divide by zero and produce NaN scores."""
    weights = normalize_weights(dict.fromkeys(normalize_weights(), 0.0))
    assert set(weights.values()) == {0.0}


def test_weight_mappings_are_immutable():
    """Weights are configuration, not mutable global state."""
    for weights in (proposed_weights(), active_weights(), normalize_weights()):
        with pytest.raises(TypeError):
            weights["engagement_load"] = 0.99  # type: ignore[index]


def test_registry_is_not_yet_approved():
    """Gate G1 is open, and scoring must fail closed while it is.

    When the program owner approves the registry, this test is the one that
    changes — deliberately, so approval is a visible, reviewed commit.
    """
    with pytest.raises(RegistryNotApprovedError, match="gate G1"):
        assert_registry_approved()


def test_prohibited_inputs_are_declared():
    """The v1.1 §1.3 prohibited-input list is present and non-empty."""
    assert "age" in PROHIBITED_INPUTS
    assert "health_inference" in PROHIBITED_INPUTS
    assert "protected_characteristic" in PROHIBITED_INPUTS


def test_no_factor_key_collides_with_a_prohibited_input():
    """A factor must never be named for something it is forbidden to consider."""
    assert not set(factor_keys()) & PROHIBITED_INPUTS
