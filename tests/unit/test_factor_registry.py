"""Tests for the canonical factor registry.

The central test here is :func:`test_implemented_scoring_weights_sum_to_one`,
which encodes the defect found in the legacy baseline so it cannot recur.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from smartmatch_domain.factor_registry import (
    APPROVED_SCORING_KEYS,
    CBA_PHYSICAL_MODEL,
    CBA_VIRTUAL_MODEL,
    PROHIBITED_INPUTS,
    PROPOSED_FACTORS,
    REGISTRY_APPROVED_ON,
    REGISTRY_APPROVER,
    REGISTRY_STATUS,
    REGISTRY_VERSION,
    SCORING_MODE_VERSION,
    SUPERSEDED_G1_MODEL,
    SUPERSEDED_REGISTRY_VERSION,
    SUPERSEDED_SCORING_KEYS,
    FactorKind,
    FactorSpec,
    active_weights,
    assert_registry_approved,
    assert_scoring_ready,
    display_weights,
    factor_keys,
    implemented_scoring_keys,
    normalize_weights,
    proposed_weights,
    resolve_scoring_model,
)
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_VIRTUAL_SCORING_MODE,
    UnknownScoringModeError,
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


def test_active_weights_are_the_approved_cba_scoring_set():
    """2.0.0 implements the CBA four; the superseded two carry no active weight."""
    active = active_weights()
    assert set(active) == set(APPROVED_SCORING_KEYS)
    assert active["industry_match"] == pytest.approx(0.30)
    assert active["role_match"] == pytest.approx(0.25)
    assert active["cba_semantic_topic"] == pytest.approx(0.15)
    assert active["proximity"] == pytest.approx(0.30)

    proposed = proposed_weights()
    assert set(proposed) == set(factor_keys())
    assert proposed["availability"] == 0.0
    # Retained at the weights they were approved with, so a stored 1.x run can
    # be reproduced rather than re-derived (OQ-CBA-025: coexist).
    assert proposed["topic_relevance"] == pytest.approx(0.70)
    assert proposed["travel_burden"] == pytest.approx(0.30)


def test_current_model_scoring_weights_sum_to_one():
    """The registry's current proposal is internally consistent as a proposal.

    Ranged over the *current* model's factors rather than every scoring factor
    declared: the retired pair still carries the 0.70/0.30 it was approved
    with, so summing across both generations would total 2.0 and prove nothing.
    """
    by_key = {spec.key: spec for spec in PROPOSED_FACTORS}
    total = sum(by_key[key].proposed_weight for key in CBA_PHYSICAL_MODEL.scoring_keys)
    assert total == pytest.approx(1.0)


def test_superseded_model_scoring_weights_sum_to_one():
    """The G1 rulebook stays internally consistent, so a 1.x run reproduces."""
    by_key = {spec.key: spec for spec in PROPOSED_FACTORS}
    total = sum(by_key[key].proposed_weight for key in SUPERSEDED_G1_MODEL.scoring_keys)
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


def test_all_four_approved_scoring_factors_are_implemented():
    """ADR-0016 §5: Industry 30, Role 25, Topic 15, Proximity 30 — and nothing else.

    The single most load-bearing assertion in this file. These four numbers are
    the accepted policy, and this is the one place they are checked against the
    registry rather than against another copy of themselves.
    """
    weights = normalize_weights()
    assert set(weights) == {"industry_match", "role_match", "cba_semantic_topic", "proximity"}
    assert weights["industry_match"] == pytest.approx(0.30)
    assert weights["role_match"] == pytest.approx(0.25)
    assert weights["cba_semantic_topic"] == pytest.approx(0.15)
    assert weights["proximity"] == pytest.approx(0.30)
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
    assert set(weights) == set(APPROVED_SCORING_KEYS)
    assert weights == normalize_weights()


def test_normalize_weights_ignores_retired_keys():
    """A retired factor cannot inject weight mass back into the current model.

    The mirror of the deflation guard: OQ-CBA-025 keeps ``travel_burden``
    declared and implemented, so the only thing standing between it and the
    2.0.0 denominator is ``retired_in_version``. An override naming it must be
    ignored exactly as an unknown key is.
    """
    weights = normalize_weights({"travel_burden": 5.0, "topic_relevance": 5.0})
    assert set(weights) == set(APPROVED_SCORING_KEYS)
    assert weights == normalize_weights()


def test_normalize_weights_rejects_negative_weights():
    with pytest.raises(ValueError, match="must not be negative"):
        normalize_weights({"industry_match": -0.5})


def test_normalize_weights_all_zero_returns_zeros_not_nan():
    """A zero total must not divide by zero and produce NaN scores."""
    weights = normalize_weights(dict.fromkeys(APPROVED_SCORING_KEYS, 0.0))
    assert weights == dict.fromkeys(APPROVED_SCORING_KEYS, 0.0)
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
    """ADR-0016 Proposal 9's version string, exactly as approved.

    A major bump, because the CBA four-factor set replaces the G1 two-factor
    set rather than extending it: a 1.x score and a 2.x score are not
    comparable, and this string is the only thing that keeps them apart.
    """
    assert REGISTRY_VERSION == "2.0.0-approved-oq-cba-004"
    assert SUPERSEDED_REGISTRY_VERSION == "1.1.1-approved-g1-m6j"
    assert REGISTRY_VERSION != SUPERSEDED_REGISTRY_VERSION


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


# ---------------------------------------------------------------------------
# ADR-0016 (accepted 2026-09-05): the CBA four-factor registry
# ---------------------------------------------------------------------------


def test_registry_records_who_approved_it_and_when():
    """An "approved" flag with no approver is a checkbox, not an approval."""
    assert REGISTRY_STATUS == "approved"
    assert REGISTRY_APPROVER == "Danny Tran, Development Lead / program owner of record"
    assert REGISTRY_APPROVED_ON == "2026-09-05"


def test_exactly_four_factors_are_approved_for_scoring():
    """Four implemented keys exactly — no fifth, and none of them missing."""
    approved = {"industry_match", "role_match", "cba_semantic_topic", "proximity"}
    assert set(APPROVED_SCORING_KEYS) == approved
    assert implemented_scoring_keys() == APPROVED_SCORING_KEYS


def test_topic_slot_binds_to_the_cba_semantic_factor_not_topic_relevance():
    """OQ-CBA-027, decided: the Topic slot is ``cba_semantic_topic``.

    Customer §9 asks for a semantic comparison against the request description
    and for a policy-neutral third state for an observed absence.
    ``topic_relevance`` is a lexical set-overlap factor with two states and
    implements neither, so binding the slot to it would have satisfied the
    weight table while failing the requirement the weight exists for.
    """
    assert "cba_semantic_topic" in APPROVED_SCORING_KEYS
    assert "topic_relevance" not in APPROVED_SCORING_KEYS
    assert "topic_relevance" in factor_keys()


def test_superseded_factors_are_retained_not_deleted():
    """OQ-CBA-025, decided: coexist. A stored 1.x run must stay reproducible."""
    by_key = {spec.key: spec for spec in PROPOSED_FACTORS}
    for key in SUPERSEDED_SCORING_KEYS:
        spec = by_key[key]
        assert spec.implemented is True, f"{key} must stay implemented (OQ-CBA-025)"
        assert spec.is_retired is True
        assert spec.retired_in_version == REGISTRY_VERSION
        assert spec.active_weight == 0.0, (
            f"{key} is retired but still contributes active weight — this is the "
            "legacy deflation defect pointed the other way"
        )


def test_superseded_model_reproduces_the_g1_weights_exactly():
    """A run pinned to 1.1.1 scores the numbers it was produced with, forever."""
    weights = normalize_weights(model=SUPERSEDED_G1_MODEL)
    assert set(weights) == set(SUPERSEDED_SCORING_KEYS)
    assert weights["topic_relevance"] == pytest.approx(0.70)
    assert weights["travel_burden"] == pytest.approx(0.30)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_superseded_model_is_pinned_to_its_own_registry_version():
    """Old runs stay distinguishable: a 1.x model never claims the 2.x pin."""
    assert SUPERSEDED_G1_MODEL.registry_version == SUPERSEDED_REGISTRY_VERSION
    assert SUPERSEDED_G1_MODEL.is_current is False
    assert CBA_PHYSICAL_MODEL.registry_version == REGISTRY_VERSION
    assert CBA_VIRTUAL_MODEL.registry_version == REGISTRY_VERSION


def test_scoring_mode_is_a_separate_pin_from_registry_version():
    """ADR-0016 Proposal 9: a mode is never a version and a version never a mode."""
    assert CBA_PHYSICAL_MODEL.scoring_mode == CBA_PHYSICAL_SCORING_MODE
    assert CBA_VIRTUAL_MODEL.scoring_mode == CBA_VIRTUAL_SCORING_MODE
    assert CBA_PHYSICAL_MODEL.scoring_mode != CBA_VIRTUAL_MODEL.scoring_mode
    # Same rulebook, different model.
    assert CBA_PHYSICAL_MODEL.registry_version == CBA_VIRTUAL_MODEL.registry_version
    assert CBA_PHYSICAL_MODEL.scoring_mode_version == SCORING_MODE_VERSION
    assert CBA_VIRTUAL_MODEL.scoring_mode_version == SCORING_MODE_VERSION
    # And a mode is never mistakable for a version.
    assert REGISTRY_VERSION not in {CBA_PHYSICAL_SCORING_MODE, CBA_VIRTUAL_SCORING_MODE}


def test_virtual_mode_excludes_proximity_and_nothing_else():
    """Customer §11: ignore proximity entirely; do not touch the other three."""
    assert set(CBA_VIRTUAL_MODEL.scoring_keys) == set(CBA_PHYSICAL_MODEL.scoring_keys) - {
        "proximity"
    }
    assert "proximity" not in CBA_VIRTUAL_MODEL.scoring_keys


def test_virtual_redistribution_is_the_approved_proportional_table():
    """ADR-0016 Proposal 6, option 6a — the exact approved six-place values.

    These three numbers are the whole of the §11 decision, and this is the only
    place in the repository they are written down as literals. They are asserted
    against ``display_weights``, which *computes* them from the physical
    weights: a runtime that typed them would have a second source of truth that
    could drift from the division it claims to be.
    """
    rendered = display_weights(CBA_VIRTUAL_MODEL)
    assert rendered == {
        "industry_match": 0.428571,
        "role_match": 0.357143,
        "cba_semantic_topic": 0.214286,
    }
    # Summed on the unrounded weights, which are what actually score.
    assert sum(normalize_weights(model=CBA_VIRTUAL_MODEL).values()) == pytest.approx(1.0)


def test_virtual_weights_are_the_physical_weights_over_the_survivors():
    """Proportional renormalization, checked as a ratio rather than as a table."""
    physical = normalize_weights(model=CBA_PHYSICAL_MODEL)
    virtual = normalize_weights(model=CBA_VIRTUAL_MODEL)
    surviving_mass = sum(physical[key] for key in virtual)
    for key, value in virtual.items():
        assert value == pytest.approx(physical[key] / surviving_mass)


def test_physical_and_virtual_weight_maps_differ():
    """G-CBA-09's premise: two modes of one rulebook must fingerprint apart."""
    assert dict(normalize_weights(model=CBA_PHYSICAL_MODEL)) != dict(
        normalize_weights(model=CBA_VIRTUAL_MODEL)
    )


def test_resolve_scoring_model_reads_a_missing_mode_as_pre_adr_0016():
    """Proposal 7: no mode means an older run, never ``cba-physical-1``."""
    assert resolve_scoring_model(None) is SUPERSEDED_G1_MODEL
    assert resolve_scoring_model(CBA_PHYSICAL_SCORING_MODE) is CBA_PHYSICAL_MODEL
    assert resolve_scoring_model(CBA_VIRTUAL_SCORING_MODE) is CBA_VIRTUAL_MODEL


def test_resolve_scoring_model_refuses_an_unrecognised_mode():
    """A typo'd mode that defaulted would score a virtual event on proximity."""
    with pytest.raises(UnknownScoringModeError, match="closed"):
        resolve_scoring_model("cba-hybrid-1")


def test_scoring_model_refuses_a_mode_without_its_version():
    """A mode with no version cannot be read back under the definition it used."""
    with pytest.raises(ValueError, match="set or unset together"):
        type(CBA_PHYSICAL_MODEL)(
            registry_version=REGISTRY_VERSION,
            scoring_mode=CBA_PHYSICAL_SCORING_MODE,
            scoring_mode_version=None,
            scoring_keys=("industry_match",),
            is_current=True,
        )


def test_retired_in_version_must_name_a_version():
    """A blank retirement marker would say 'retired in nothing in particular'."""
    with pytest.raises(ValueError, match="retired_in_version"):
        FactorSpec(
            key="blankly_retired",
            display_label="Blankly Retired",
            kind=FactorKind.SUITABILITY,
            proposed_weight=0.10,
            implemented=True,
            rationale="retired without saying when",
            retired_in_version="   ",
        )


def test_no_weight_literal_is_typed_outside_this_registry():
    """One registry source for the defaults — asserted, not trusted.

    Greps the domain package for the approved weight literals. The factor lanes
    were forbidden from writing any weight, and the virtual table is computed
    rather than typed, so the only file that may contain these strings is the
    registry itself (and only as prose in its docstring).
    """
    package_root = Path(__file__).resolve().parents[2] / "python" / "smartmatch_domain"
    forbidden = ("0.428571", "0.357143", "0.214286")
    offenders: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        if path.name == "factor_registry.py":
            continue
        text = path.read_text(encoding="utf-8")
        offenders.extend(f"{path.name}: {token}" for token in forbidden if token in text)
    assert not offenders, (
        "the §11 virtual weights are typed as literals outside the registry: "
        f"{offenders}. They must be computed by normalize_weights()."
    )
