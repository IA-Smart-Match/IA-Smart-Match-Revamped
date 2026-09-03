"""Tests for the canonical factor registry.

The central test here is :func:`test_implemented_scoring_weights_sum_to_one`,
which encodes the defect found in the legacy baseline so it cannot recur.
"""

from __future__ import annotations

import math

import pytest
from smartmatch_domain.factor_registry import (
    PROHIBITED_INPUTS,
    PROPOSED_FACTORS,
    REGISTRY_VERSION,
    FactorKind,
    FactorSpec,
    active_weights,
    assert_registry_approved,
    assert_scoring_ready,
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

    Post-M6j, topic_relevance and travel_burden are both implemented, so this
    actually asserts the sum rather than passing vacuously.
    """
    weights = normalize_weights()
    assert sum(weights.values()) == pytest.approx(1.0)


def test_active_weight_is_zero_unless_scoring_and_implemented():
    """The structural half of the same guard.

    A factor may be *proposed* with a nonzero weight before it is built — that
    is what a proposal is for. What it must never do is contribute active
    weight, because active weight is what normalization divides by. The
    invariant is ``not (is_scoring and implemented) => active_weight == 0.0``
    — the same statement :class:`~smartmatch_domain.factor_registry.
    FactorSpec`'s ``implemented`` docstring now makes explicitly.

    A prior version of this test only checked ``not spec.implemented``, which
    was correct while ``availability`` was the registry's one
    ``implemented=False`` entry, but went vacuous the moment every
    ``PROPOSED_FACTORS`` entry became ``implemented=True`` (fix wave, Fix 2):
    the loop body stopped running at all, so the assertion inside it stopped
    proving anything, while still reading as a live regression guard. This
    version checks the real invariant — is_scoring, not implemented, is what
    keeps availability at weight 0 — and asserts the loop body actually ran
    at least once, so it can never again silently pass without checking
    anything.
    """
    checked = 0
    for spec in PROPOSED_FACTORS:
        if not (spec.is_scoring and spec.implemented):
            checked += 1
            assert spec.active_weight == 0.0, (
                f"{spec.key} is not both a scoring factor and implemented, "
                f"but contributes active weight {spec.active_weight} — this "
                "is the legacy deflation defect"
            )
    assert checked > 0, (
        "no PROPOSED_FACTORS entry is outside (is_scoring and implemented) — "
        "this guard would otherwise pass vacuously, as it did before this "
        "fix wave once every factor became implemented=True"
    )


def test_active_weights_are_the_approved_scoring_set_after_m6j():
    """M6j implements topic_relevance and travel_burden; availability stays unscored."""
    active = active_weights()
    assert set(active) == {"topic_relevance", "travel_burden"}
    assert active["topic_relevance"] == pytest.approx(0.70)
    assert active["travel_burden"] == pytest.approx(0.30)

    proposed = proposed_weights()
    assert set(proposed) == {"topic_relevance", "travel_burden", "availability"}
    assert proposed["availability"] == 0.0


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


def test_both_approved_scoring_factors_are_implemented():
    """Post-M6j: both approved Stage B scoring factors are implemented."""
    weights = normalize_weights()
    assert set(weights) == {"topic_relevance", "travel_burden"}
    assert weights["topic_relevance"] == pytest.approx(0.70)
    assert weights["travel_burden"] == pytest.approx(0.30)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_normalize_weights_honours_overrides_and_renormalizes():
    """An override changes the balance but never breaks the sum-to-one invariant."""
    base = normalize_weights()
    key, other = list(base)[:2]
    bumped = normalize_weights({key: base[key] * 10.0})

    assert sum(bumped.values()) == pytest.approx(1.0)
    assert bumped[key] > base[key]
    assert bumped[other] < base[other]


def test_normalize_weights_ignores_unknown_and_unimplemented_keys():
    """Unknown and unimplemented (eligibility) keys cannot inject weight mass."""
    weights = normalize_weights({"not_a_factor": 5.0, "availability": 5.0})
    assert "not_a_factor" not in weights
    assert "availability" not in weights
    assert set(weights) == {"topic_relevance", "travel_burden"}
    assert weights == normalize_weights()


def test_normalize_weights_rejects_negative_weights():
    with pytest.raises(ValueError, match="must not be negative"):
        normalize_weights({"topic_relevance": -0.5})


def test_normalize_weights_all_zero_returns_zeros_not_nan():
    """A zero total must not divide by zero and produce NaN scores."""
    weights = normalize_weights({"topic_relevance": 0.0, "travel_burden": 0.0})
    assert weights == {"topic_relevance": 0.0, "travel_burden": 0.0}
    for value in weights.values():
        assert value == 0.0
        assert not math.isnan(value)


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


def test_assert_scoring_ready_passes():
    """M6j: the implemented scoring set matches the approved set exactly."""
    assert assert_scoring_ready() is None


def test_registry_version_is_pinned():
    """The version bump records that the implemented scoring set changed."""
    assert REGISTRY_VERSION == "1.1.1-approved-g1-m6j"


def test_availability_remains_unscored():
    """availability has a real Stage A implementation but is never a Stage B scorer.

    ``implemented=True`` records that smartmatch_domain.eligibility.
    apply_availability_filter exists; ``is_scoring`` (governed by
    ``FactorKind.ELIGIBILITY``) is what keeps it out of Stage B regardless.
    """
    spec = next(spec for spec in PROPOSED_FACTORS if spec.key == "availability")
    assert spec.implemented is True
    assert spec.is_scoring is False
    assert spec.active_weight == 0.0


def test_no_dropped_factor_reappeared():
    """Factors dropped for this PR must never be wired back into the registry."""
    dropped_factors = {
        "role_fit",
        "engagement_load",
        "repeat_penalty",
        "credential_check",
        "contact_status",
        "declared_cap",
        "historical_conversion",
        "student_interest",
        "match_depth",
    }
    assert not dropped_factors & set(factor_keys())
