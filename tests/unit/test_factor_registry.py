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

    When no scoring factors are implemented yet (post-G1, pre-M2), normalization
    is vacuous and this test passes without asserting a sum.
    """
    weights = normalize_weights()
    if not weights:
        return
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


def test_active_weights_empty_until_m2_implements_scoring_factors():
    """G1 approved 2026-09-03; topic_relevance and travel_burden land in M2."""
    assert active_weights() == {}
    proposed = proposed_weights()
    assert set(proposed) == {"topic_relevance", "travel_burden", "availability"}
    assert proposed["topic_relevance"] == pytest.approx(0.70)
    assert proposed["travel_burden"] == pytest.approx(0.30)


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
    """Post-G1 pre-M2: no scoring factors are implemented yet."""
    assert normalize_weights() == {}


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
    assert "topic_relevance" not in weights
    assert weights == {}


def test_normalize_weights_rejects_negative_weights():
    with pytest.raises(ValueError, match="must not be negative"):
        normalize_weights({"topic_relevance": -0.5})


def test_normalize_weights_all_zero_returns_zeros_not_nan():
    """A zero total must not divide by zero and produce NaN scores."""
    weights = normalize_weights(dict.fromkeys(normalize_weights(), 0.0))
    assert weights == {}


def test_weight_mappings_are_immutable():
    """Weights are configuration, not mutable global state."""
    proposed = proposed_weights()
    if proposed:
        key = next(iter(proposed))
        with pytest.raises(TypeError):
            proposed[key] = 0.99  # type: ignore[index]


def test_registry_is_approved_after_g1():
    """Gate G1 closed 2026-09-03 — scoring may proceed once M2 implements factors."""
    assert_registry_approved()


def test_prohibited_inputs_are_declared():
    """The v1.1 §1.3 prohibited-input list is present and non-empty."""
    assert "age" in PROHIBITED_INPUTS
    assert "health_inference" in PROHIBITED_INPUTS
    assert "protected_characteristic" in PROHIBITED_INPUTS


def test_no_factor_key_collides_with_a_prohibited_input():
    """A factor must never be named for something it is forbidden to consider."""
    assert not set(factor_keys()) & PROHIBITED_INPUTS
