"""Tests for the canonical factor registry.

The central test here is :func:`test_implemented_scoring_weights_sum_to_one`,
which encodes the defect found in the legacy baseline so it cannot recur.
"""

from __future__ import annotations

import dataclasses
import math
import re
import sys
from pathlib import Path

import pytest
from smartmatch_domain import factor_registry as factor_registry_module
from smartmatch_domain.eli import ELI_FORMULA_VERSION
from smartmatch_domain.factor_registry import (
    APPROVED_SCORING_KEYS,
    APPROVED_SCORING_KEYS_3,
    CBA_3_PHYSICAL_MODEL,
    CBA_3_VIRTUAL_MODEL,
    CBA_PHYSICAL_MODEL,
    CBA_REGISTRY,
    CBA_REGISTRY_3,
    CBA_VIRTUAL_MODEL,
    ENGAGEMENT_LOAD_SPEC,
    PROHIBITED_INPUTS,
    PROPOSED_FACTORS,
    PROPOSED_FACTORS_3,
    REGISTRY_3_VERSION,
    REGISTRY_APPROVED_ON,
    REGISTRY_APPROVER,
    REGISTRY_STATUS,
    REGISTRY_VERSION,
    SCORING_MODE_VERSION,
    SUPERSEDED_G1_MODEL,
    SUPERSEDED_REGISTRY_VERSION,
    SUPERSEDED_REGISTRY_VERSIONS,
    SUPERSEDED_SCORING_KEYS,
    FactorKind,
    FactorRegistry,
    FactorSpec,
    RegistryNotApprovedError,
    active_weights,
    assert_registry_approved,
    assert_scoring_ready,
    current_cba_registry,
    display_weights,
    factor_keys,
    implemented_scoring_keys,
    normalize_weights,
    proposed_registry_versions,
    proposed_weights,
    registry_for_version,
    resolve_scoring_model,
    superseded_registry_versions,
)
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_SCORING_MODES,
    CBA_VIRTUAL_SCORING_MODE,
    UnknownScoringModeError,
)
from smartmatch_domain.load_bands import (
    ENGAGEMENT_LOAD_FACTOR_KEY,
    Q7_REGISTERED_LOAD_BANDS,
)
from smartmatch_domain.match_run import registry_fingerprint, weights_fingerprint


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


# ---------------------------------------------------------------------------
# B26 T8c: registry 3.0.0, declared ``proposed`` and NOT current
# ---------------------------------------------------------------------------

#: Measured on origin/main 1909278f and re-measured on the stacked base (T8c
#: plan §3.5). A 1.1.1 or 2.0.0 run's registry_hash must reproduce byte for byte.
PINNED_2_0_0_PHYSICAL_HASH = (
    "sha256:f870192c2b1d9977aaf4be3368f51f67accbbbba9955e4346a4445b0be4be4e5"
)
#: cba-virtual-1 divides 0.3 / 0.25 / 0.15 by their float ``sum()``. Python 3.11
#: adds left to right (0.7000000000000001); 3.12's ``sum()`` is compensated
#: (0.7). The last digit of every weight, and so the digest, depends on the
#: interpreter. Production (Dockerfile.api / Dockerfile.worker,
#: ``python:3.11-slim-bookworm``) and CI run 3.11: that digest is what stored
#: virtual runs carry. ``pyproject.toml`` also allows 3.12 (local dev).
PINNED_2_0_0_VIRTUAL_HASH_PY311 = (
    "sha256:62524878457dee467d747e3b9040a61cf6915e7a5398a08a8d9af4e83792b74c"
)
PINNED_2_0_0_VIRTUAL_HASH_PY312 = (
    "sha256:0b27df1f198b501da27f3a58d0128625f1351a1ba77fa4189807c31865c85ce4"
)
PINNED_2_0_0_VIRTUAL_HASH = (
    PINNED_2_0_0_VIRTUAL_HASH_PY311
    if sys.version_info < (3, 12)
    else PINNED_2_0_0_VIRTUAL_HASH_PY312
)
PINNED_1_1_1_G1_HASH = "sha256:9da5f1b1ccb6b0627759c77a472fb47d8b77ce634c21fffe9bf53a5b04e79de1"


# 1
def test_registry_3_is_declared_proposed():
    assert REGISTRY_3_VERSION == "3.0.0-approved-b26-eli"
    assert CBA_REGISTRY_3.version == REGISTRY_3_VERSION
    assert CBA_REGISTRY_3.status == "proposed"
    assert CBA_REGISTRY_3.approver is None
    assert CBA_REGISTRY_3.approved_on is None
    assert CBA_REGISTRY_3.load_bands is Q7_REGISTERED_LOAD_BANDS
    assert CBA_REGISTRY_3.mode_vocabulary == CBA_SCORING_MODES
    assert registry_for_version(REGISTRY_3_VERSION) is CBA_REGISTRY_3


# 2
def test_registry_3_declares_engagement_load_as_weight_zero_penalty_in_no_model():
    spec = CBA_REGISTRY_3.spec_by_key[ENGAGEMENT_LOAD_FACTOR_KEY]
    assert spec is ENGAGEMENT_LOAD_SPEC
    assert spec.kind is FactorKind.PENALTY
    assert spec.proposed_weight == 0.0
    assert spec.implemented is True
    assert spec.is_retired is False
    for model in CBA_REGISTRY_3.scoring_modes.values():
        assert ENGAGEMENT_LOAD_FACTOR_KEY not in model.scoring_keys
    assert CBA_3_PHYSICAL_MODEL.scoring_keys == CBA_PHYSICAL_MODEL.scoring_keys
    assert CBA_3_VIRTUAL_MODEL.scoring_keys == CBA_VIRTUAL_MODEL.scoring_keys
    # The four weighted specs and availability are the same objects as 2.0.0's;
    # the retired G1 pair stays in CBA_REGISTRY only.
    assert PROPOSED_FACTORS_3[:4] == PROPOSED_FACTORS[:4]
    assert all(a is b for a, b in zip(PROPOSED_FACTORS_3[:4], PROPOSED_FACTORS[:4], strict=True))
    assert PROPOSED_FACTORS_3[4] is ENGAGEMENT_LOAD_SPEC
    assert PROPOSED_FACTORS_3[5] is PROPOSED_FACTORS[6]
    assert len(PROPOSED_FACTORS_3) == 6
    assert APPROVED_SCORING_KEYS | {ENGAGEMENT_LOAD_FACTOR_KEY} == APPROVED_SCORING_KEYS_3
    for mode in (CBA_PHYSICAL_SCORING_MODE, CBA_VIRTUAL_SCORING_MODE):
        model = resolve_scoring_model(mode, registry=CBA_REGISTRY_3)
        assert model.registry_version == REGISTRY_3_VERSION
        assert model.scoring_mode_version == SCORING_MODE_VERSION
        assert dict(normalize_weights(model=model, registry=CBA_REGISTRY_3)) == dict(
            normalize_weights(model=resolve_scoring_model(mode))
        )
    with pytest.raises(UnknownScoringModeError):
        resolve_scoring_model(None, registry=CBA_REGISTRY_3)


# 3
def test_current_registry_is_2_0_0():
    assert current_cba_registry() is CBA_REGISTRY
    assert factor_registry_module.CURRENT_CBA_REGISTRY is CBA_REGISTRY
    assert REGISTRY_VERSION == "2.0.0-approved-oq-cba-004"
    assert current_cba_registry().version == REGISTRY_VERSION
    assert SUPERSEDED_REGISTRY_VERSION == "1.1.1-approved-g1-m6j"
    assert isinstance(SUPERSEDED_REGISTRY_VERSION, str)


def test_current_registry_is_read_per_call(monkeypatch):
    monkeypatch.setattr(factor_registry_module, "CURRENT_CBA_REGISTRY", CBA_REGISTRY_3)
    assert current_cba_registry() is CBA_REGISTRY_3


# 4
def test_superseded_and_proposed_sets_derive_from_current():
    assert frozenset({SUPERSEDED_REGISTRY_VERSION}) == SUPERSEDED_REGISTRY_VERSIONS
    assert superseded_registry_versions() == frozenset({"1.1.1-approved-g1-m6j"})
    assert proposed_registry_versions() == frozenset({"3.0.0-approved-b26-eli"})
    assert superseded_registry_versions(CBA_REGISTRY_3) == frozenset(
        {"1.1.1-approved-g1-m6j", "2.0.0-approved-oq-cba-004"}
    )
    assert proposed_registry_versions(CBA_REGISTRY_3) == frozenset()


def test_the_derived_sets_refuse_a_registry_outside_the_lineage():
    stranger = dataclasses.replace(CBA_REGISTRY_3, version="9.9.9-nobody", scoring_modes={})
    with pytest.raises(ValueError, match="lineage"):
        superseded_registry_versions(stranger)
    with pytest.raises(ValueError, match="lineage"):
        proposed_registry_versions(stranger)


# 5
def test_registry_3_fails_the_approval_gate_and_passes_readiness():
    with pytest.raises(RegistryNotApprovedError, match="proposed"):
        assert_registry_approved(registry=CBA_REGISTRY_3)
    assert_scoring_ready(registry=CBA_REGISTRY_3)
    assert implemented_scoring_keys(registry=CBA_REGISTRY_3) == APPROVED_SCORING_KEYS_3
    # And the 2.0.0 gate is untouched.
    assert_registry_approved()
    assert_scoring_ready()


# 6
def test_an_approved_copy_cannot_borrow_the_3_0_0_pin():
    impostor = dataclasses.replace(
        CBA_REGISTRY_3,
        status="approved",
        approver="Somebody Else",
        approved_on="2026-09-23",
    )
    assert impostor.version == REGISTRY_3_VERSION
    with pytest.raises(RegistryNotApprovedError):
        assert_registry_approved(registry=impostor)
    with pytest.raises(RegistryNotApprovedError):
        assert_scoring_ready(registry=impostor)
    with pytest.raises(ValueError, match="already bound"):
        factor_registry_module.register_registry(impostor)


def test_the_3_0_0_pin_is_never_unregistered():
    with pytest.raises(ValueError, match="CBA"):
        factor_registry_module._unregister_for_tests(REGISTRY_3_VERSION)
    assert registry_for_version(REGISTRY_3_VERSION) is CBA_REGISTRY_3


# 7
def test_no_production_module_imports_the_evaluation_helper_or_reassigns_current():
    root = Path(__file__).resolve().parents[2]
    assignment = re.compile(r"(?:^\s*|\.)CURRENT_CBA_REGISTRY\s*(?::[^=\n]*)?=(?!=)", re.MULTILINE)
    offenders: list[str] = []
    for top in ("python", "services", "tools"):
        for path in sorted((root / top).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(root).as_posix()
            if "registry_evaluation" in text:
                offenders.append(f"{relative}: imports registry_evaluation")
            if path.name != "factor_registry.py" and assignment.search(text):
                offenders.append(f"{relative}: assigns CURRENT_CBA_REGISTRY")
            if (
                path.name != "factor_registry.py"
                and "setattr" in text
                and "CURRENT_CBA_REGISTRY" in text
            ):
                offenders.append(f"{relative}: patches CURRENT_CBA_REGISTRY")
            if path.name != "factor_registry.py":
                offenders.extend(
                    f"{relative}: names {name}"
                    for name in ("CBA_REGISTRY_3", "REGISTRY_3_VERSION")
                    if re.search(rf"\b{name}\b", text)
                )
    assert not offenders, offenders
    source = (
        root / "python" / "smartmatch_domain" / "smartmatch_domain" / "factor_registry.py"
    ).read_text(encoding="utf-8")
    bindings = assignment.findall(source)
    assert len(bindings) == 1, bindings
    assert re.search(
        r"^CURRENT_CBA_REGISTRY: Final\[FactorRegistry\] = CBA_REGISTRY\b",
        source,
        re.MULTILINE,
    )


# 8
def test_registry_fingerprint_without_bands_is_weights_fingerprint():
    for model, pinned in (
        (CBA_PHYSICAL_MODEL, PINNED_2_0_0_PHYSICAL_HASH),
        (CBA_VIRTUAL_MODEL, PINNED_2_0_0_VIRTUAL_HASH),
        (SUPERSEDED_G1_MODEL, PINNED_1_1_1_G1_HASH),
    ):
        weights = normalize_weights(model=model)
        assert registry_fingerprint(weights, load_bands=None) == pinned
        assert weights_fingerprint(weights) == pinned
    assert CBA_REGISTRY.load_bands is None


def test_the_cba_lineage_versions_are_the_three_cba_pins():
    from smartmatch_domain.factor_registry import CBA_LINEAGE_VERSIONS, REGISTRY_3_VERSION

    assert {
        SUPERSEDED_REGISTRY_VERSION,
        REGISTRY_VERSION,
        REGISTRY_3_VERSION,
    } == CBA_LINEAGE_VERSIONS


# 8b
def test_both_virtual_literals_are_the_two_float_sums_of_the_same_weights():
    """Each literal is checked on every interpreter, not only the one running.

    Left-to-right addition is 3.11's ``sum()``; ``math.fsum`` is what 3.12's
    compensated ``sum()`` returns for these three values.
    """
    raw = {
        key: CBA_REGISTRY.spec_by_key[key].proposed_weight
        for key in normalize_weights(model=CBA_VIRTUAL_MODEL)
    }
    left_to_right = 0.0
    for value in raw.values():
        left_to_right += value
    compensated = math.fsum(raw.values())
    assert left_to_right != compensated
    assert (
        weights_fingerprint({key: value / left_to_right for key, value in raw.items()})
        == PINNED_2_0_0_VIRTUAL_HASH_PY311
    )
    assert (
        weights_fingerprint({key: value / compensated for key, value in raw.items()})
        == PINNED_2_0_0_VIRTUAL_HASH_PY312
    )


# 9
def _registry_3_with(**changes):
    return dataclasses.replace(CBA_REGISTRY_3, **changes)


def _load_spec(**changes):
    return dataclasses.replace(ENGAGEMENT_LOAD_SPEC, **changes)


def _factors_with(spec):
    return tuple(spec if s.key == ENGAGEMENT_LOAD_FACTOR_KEY else s for s in PROPOSED_FACTORS_3)


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: _registry_3_with(load_bands=None), id="spec-without-bands"),
        pytest.param(
            lambda: dataclasses.replace(CBA_REGISTRY, load_bands=Q7_REGISTERED_LOAD_BANDS),
            id="bands-without-spec",
        ),
        pytest.param(
            lambda: _registry_3_with(
                scoring_modes={
                    CBA_PHYSICAL_SCORING_MODE: dataclasses.replace(
                        CBA_3_PHYSICAL_MODEL,
                        scoring_keys=(
                            *CBA_3_PHYSICAL_MODEL.scoring_keys,
                            ENGAGEMENT_LOAD_FACTOR_KEY,
                        ),
                    ),
                    CBA_VIRTUAL_SCORING_MODE: CBA_3_VIRTUAL_MODEL,
                }
            ),
            id="spec-in-a-model",
        ),
        pytest.param(
            lambda: _registry_3_with(factors=_factors_with(_load_spec(proposed_weight=0.1))),
            id="weight-not-zero",
        ),
        pytest.param(
            lambda: _registry_3_with(
                factors=_factors_with(_load_spec(kind=FactorKind.SUITABILITY))
            ),
            id="not-a-penalty",
        ),
        pytest.param(
            lambda: _registry_3_with(factors=_factors_with(_load_spec(implemented=False))),
            id="not-implemented",
        ),
        pytest.param(
            lambda: _registry_3_with(factors=_factors_with(_load_spec(retired_in_version="4.0.0"))),
            id="retired",
        ),
        pytest.param(
            lambda: _registry_3_with(
                load_bands=dataclasses.replace(
                    Q7_REGISTERED_LOAD_BANDS, eli_formula_version="1.0.0"
                )
            ),
            id="eli-version-mismatch",
        ),
    ],
)
def test_registry_invariants(build):
    with pytest.raises(ValueError):
        build()
    assert Q7_REGISTERED_LOAD_BANDS.eli_formula_version == ELI_FORMULA_VERSION


# 10
def _toy_registry() -> FactorRegistry:
    spec = FactorSpec(
        key="toy_fit",
        display_label="Toy fit",
        kind=FactorKind.SUITABILITY,
        proposed_weight=1.0,
        implemented=True,
        rationale="toy",
    )
    return FactorRegistry(
        version="toy-0.0.1",
        status="proposed",
        approver=None,
        approved_on=None,
        factors=(spec,),
        approved_scoring_keys=frozenset({"toy_fit"}),
        scoring_modes={},
        mode_vocabulary=frozenset(),
    )


def test_toy_exercise_and_cba_registries_are_unchanged_by_the_new_field():
    from smartmatch_domain.exercise.registry import EXERCISE_REGISTRY

    for registry in (_toy_registry(), EXERCISE_REGISTRY, CBA_REGISTRY):
        assert registry.load_bands is None
        first = dataclasses.replace(registry)
        second = dataclasses.replace(registry)
        assert first == registry
        assert first == second
        assert hash(first) == hash(second)
    assert dataclasses.replace(CBA_REGISTRY_3) == CBA_REGISTRY_3
    assert hash(CBA_REGISTRY_3) == hash(dataclasses.replace(CBA_REGISTRY_3))
    assert CBA_REGISTRY_3 != CBA_REGISTRY
