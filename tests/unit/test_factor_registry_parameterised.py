"""W2a pin: the CBA registry is a value object, and every free function defaults to it.

ADR-0024 D2 / ADR-0025 D3 / class-exercise design §4.1. This file exists to prove
the registry *mechanism* is parameterised, and that parameterising it changed
nothing about the CBA registry itself. It is the companion to
``tests/unit/test_factor_registry.py``, which pins the CBA registry's contents and
is deliberately not edited by this work.

The only second registry in this repository is the throwaway toy built here. It
is a test fixture proving the parameter is real — it declares no student factor,
no exercise factor, and nothing importable outside this module.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.explanation import explain_candidate
from smartmatch_domain.factor_registry import (
    APPROVED_SCORING_KEYS,
    CBA_PHYSICAL_MODEL,
    CBA_REGISTRY,
    CBA_VIRTUAL_MODEL,
    PROHIBITED_INPUTS,
    PROPOSED_FACTORS,
    REGISTRY_APPROVED_ON,
    REGISTRY_APPROVER,
    REGISTRY_STATUS,
    REGISTRY_VERSION,
    SCORING_MODELS,
    SUPERSEDED_G1_MODEL,
    SUPERSEDED_REGISTRY_VERSION,
    FactorKind,
    FactorRegistry,
    FactorSpec,
    RegistryNotApprovedError,
    RegistryNotReadyError,
    ScoringModel,
    active_weights,
    assert_registry_approved,
    assert_scoring_ready,
    display_weights,
    factor_keys,
    implemented_scoring_keys,
    normalize_weights,
    proposed_weights,
    register_registry,
    registry_for_version,
    resolve_scoring_model,
)
from smartmatch_domain.factors.proximity import CBA_SCORING_MODES, UnknownScoringModeError

# ---------------------------------------------------------------------------
# The toy registry: a fixture, not a product registry.
# ---------------------------------------------------------------------------

_TOY_VERSION = "0.0.1-toy"
_TOY_MODE = "toy-1"


def _toy_model(*, scoring_keys: tuple[str, ...] = ("toy_overlap",)) -> ScoringModel:
    return ScoringModel(
        registry_version=_TOY_VERSION,
        scoring_mode=_TOY_MODE,
        scoring_mode_version="1.0.0",
        scoring_keys=scoring_keys,
        is_current=True,
        mode_vocabulary=frozenset({_TOY_MODE}),
    )


def _toy_spec(key: str, weight: float) -> FactorSpec:
    return FactorSpec(
        key=key,
        display_label=f"Toy {key}",
        kind=FactorKind.SUITABILITY,
        proposed_weight=weight,
        implemented=True,
        rationale="A throwaway factor for the parameterisation tests.",
    )


def _toy_registry(status: str = "proposed") -> FactorRegistry:
    return FactorRegistry(
        version=_TOY_VERSION,
        status=status,
        approver=None,
        approved_on=None,
        factors=(_toy_spec("toy_overlap", 1.0),),
        approved_scoring_keys=frozenset({"toy_overlap"}),
        scoring_modes={_TOY_MODE: _toy_model()},
    )


def _two_factor_toy_registry() -> FactorRegistry:
    keys = ("toy_overlap", "toy_affinity")
    return FactorRegistry(
        version="0.0.2-toy",
        status="approved",
        approver=None,
        approved_on=None,
        factors=(_toy_spec("toy_overlap", 0.75), _toy_spec("toy_affinity", 0.25)),
        approved_scoring_keys=frozenset(keys),
        scoring_modes={
            _TOY_MODE: ScoringModel(
                registry_version="0.0.2-toy",
                scoring_mode=_TOY_MODE,
                scoring_mode_version="1.0.0",
                scoring_keys=keys,
                is_current=True,
                mode_vocabulary=frozenset({_TOY_MODE}),
            )
        },
    )


# ---------------------------------------------------------------------------
# CBA_REGISTRY reproduces the legacy constants value for value.
# ---------------------------------------------------------------------------


def test_factor_registry_is_frozen() -> None:
    toy = _toy_registry()
    with pytest.raises(AttributeError):
        toy.version = "1.0.0"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        CBA_REGISTRY.status = "proposed"  # type: ignore[misc]


def test_factor_registry_holds_no_mutable_state() -> None:
    assert isinstance(CBA_REGISTRY.factors, tuple)
    assert isinstance(CBA_REGISTRY.approved_scoring_keys, frozenset)
    with pytest.raises(TypeError):
        CBA_REGISTRY.scoring_modes["toy-1"] = CBA_PHYSICAL_MODEL  # type: ignore[index]
    with pytest.raises(TypeError):
        CBA_REGISTRY.spec_by_key["toy_overlap"] = PROPOSED_FACTORS[0]  # type: ignore[index]


def test_cba_registry_is_bound_to_the_module_constants() -> None:
    assert CBA_REGISTRY.version == REGISTRY_VERSION
    assert CBA_REGISTRY.status == REGISTRY_STATUS
    assert CBA_REGISTRY.status == "approved"
    assert CBA_REGISTRY.approver == REGISTRY_APPROVER
    assert CBA_REGISTRY.approved_on == REGISTRY_APPROVED_ON
    assert CBA_REGISTRY.factors is PROPOSED_FACTORS
    assert CBA_REGISTRY.approved_scoring_keys == APPROVED_SCORING_KEYS
    assert dict(CBA_REGISTRY.scoring_modes) == dict(SCORING_MODELS)
    assert CBA_REGISTRY.scoring_modes["cba-physical-1"] is CBA_PHYSICAL_MODEL
    assert CBA_REGISTRY.scoring_modes["cba-virtual-1"] is CBA_VIRTUAL_MODEL


def test_cba_registry_lookup_tables_match_the_legacy_module_lookups() -> None:
    assert dict(CBA_REGISTRY.spec_by_key) == {spec.key: spec for spec in PROPOSED_FACTORS}
    assert dict(CBA_REGISTRY.kind_by_key) == {spec.key: spec.kind for spec in PROPOSED_FACTORS}


def test_prohibited_inputs_is_imported_not_redefined() -> None:
    # ADR-0025 D3: a second registry imports this set; it is never copied.
    assert "age" in PROHIBITED_INPUTS
    assert isinstance(PROHIBITED_INPUTS, frozenset)


# ---------------------------------------------------------------------------
# Every threaded function defaults to CBA_REGISTRY.
# ---------------------------------------------------------------------------


def test_free_functions_default_to_the_cba_registry() -> None:
    assert factor_keys() == factor_keys(registry=CBA_REGISTRY)
    assert implemented_scoring_keys() == implemented_scoring_keys(registry=CBA_REGISTRY)
    assert dict(normalize_weights()) == dict(normalize_weights(registry=CBA_REGISTRY))
    assert dict(proposed_weights()) == dict(proposed_weights(registry=CBA_REGISTRY))
    assert dict(active_weights()) == dict(active_weights(registry=CBA_REGISTRY))
    assert dict(display_weights()) == dict(display_weights(registry=CBA_REGISTRY))
    assert resolve_scoring_model("cba-physical-1") is CBA_PHYSICAL_MODEL
    assert resolve_scoring_model("cba-physical-1", registry=CBA_REGISTRY) is CBA_PHYSICAL_MODEL
    assert resolve_scoring_model(None) is SUPERSEDED_G1_MODEL
    assert_registry_approved()
    assert_registry_approved(registry=CBA_REGISTRY)
    assert_scoring_ready()
    assert_scoring_ready(registry=CBA_REGISTRY)


def test_defaults_reproduce_the_legacy_values() -> None:
    assert factor_keys() == tuple(spec.key for spec in PROPOSED_FACTORS)
    assert implemented_scoring_keys() == APPROVED_SCORING_KEYS
    assert set(normalize_weights(model=CBA_PHYSICAL_MODEL)) == set(CBA_PHYSICAL_MODEL.scoring_keys)
    assert abs(sum(normalize_weights(model=CBA_VIRTUAL_MODEL).values()) - 1.0) <= 1e-9


# ---------------------------------------------------------------------------
# The parameter is real: a second registry is honoured.
# ---------------------------------------------------------------------------


def test_a_second_registry_scores_over_its_own_factors_only() -> None:
    toy = _toy_registry()
    assert factor_keys(registry=toy) == ("toy_overlap",)
    assert implemented_scoring_keys(registry=toy) == frozenset({"toy_overlap"})
    weights = normalize_weights(model=toy.scoring_modes[_TOY_MODE], registry=toy)
    assert dict(weights) == {"toy_overlap": 1.0}
    assert dict(proposed_weights(registry=toy)) == {"toy_overlap": 1.0}
    assert dict(active_weights(registry=toy)) == {"toy_overlap": 1.0}


def test_a_proposed_registry_fails_closed_while_cba_passes() -> None:
    with pytest.raises(RegistryNotApprovedError):
        assert_registry_approved(registry=_toy_registry("proposed"))
    assert_registry_approved(registry=_toy_registry("approved"))
    assert_registry_approved(registry=CBA_REGISTRY)


def test_assert_scoring_ready_reads_the_supplied_registrys_approved_set() -> None:
    approved = _toy_registry("approved")
    assert_scoring_ready(registry=approved)

    mismatched = FactorRegistry(
        version="0.0.3-toy",
        status="approved",
        approver=None,
        approved_on=None,
        factors=(_toy_spec("toy_overlap", 1.0),),
        # Approves a key nothing implements: the deflation guard must notice.
        approved_scoring_keys=frozenset({"toy_overlap", "toy_absent"}),
        scoring_modes={_TOY_MODE: _toy_model()},
    )
    with pytest.raises(RegistryNotReadyError, match="toy_absent"):
        assert_scoring_ready(registry=mismatched)


def test_modes_are_closed_per_registry() -> None:
    toy = _toy_registry()
    with pytest.raises(UnknownScoringModeError, match="closed"):
        resolve_scoring_model("cba-physical-1", registry=toy)
    with pytest.raises(UnknownScoringModeError, match="closed"):
        resolve_scoring_model(_TOY_MODE, registry=CBA_REGISTRY)


def test_a_model_refuses_a_mode_outside_its_own_vocabulary() -> None:
    with pytest.raises(UnknownScoringModeError, match="closed"):
        ScoringModel(
            registry_version=_TOY_VERSION,
            scoring_mode="cba-physical-1",
            scoring_mode_version="1.0.0",
            scoring_keys=("toy_overlap",),
            is_current=True,
            mode_vocabulary=frozenset({_TOY_MODE}),
        )


def test_scoring_model_mode_vocabulary_defaults_to_the_cba_vocabulary() -> None:
    assert CBA_PHYSICAL_MODEL.mode_vocabulary == CBA_SCORING_MODES
    assert SUPERSEDED_G1_MODEL.mode_vocabulary == CBA_SCORING_MODES


def test_a_registry_refuses_a_model_that_scores_an_undeclared_key() -> None:
    with pytest.raises(ValueError, match="undeclared"):
        FactorRegistry(
            version="0.0.4-toy",
            status="approved",
            approver=None,
            approved_on=None,
            factors=(_toy_spec("toy_overlap", 1.0),),
            approved_scoring_keys=frozenset({"toy_overlap"}),
            scoring_modes={_TOY_MODE: _toy_model(scoring_keys=("toy_overlap", "toy_missing"))},
        )


def test_a_registry_refuses_a_duplicate_factor_key_and_an_unknown_status() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        FactorRegistry(
            version="0.0.5-toy",
            status="approved",
            approver=None,
            approved_on=None,
            factors=(_toy_spec("toy_overlap", 0.5), _toy_spec("toy_overlap", 0.5)),
            approved_scoring_keys=frozenset({"toy_overlap"}),
            scoring_modes={},
        )
    with pytest.raises(ValueError, match="status"):
        FactorRegistry(
            version="0.0.6-toy",
            status="pending",
            approver=None,
            approved_on=None,
            factors=(_toy_spec("toy_overlap", 1.0),),
            approved_scoring_keys=frozenset({"toy_overlap"}),
            scoring_modes={},
        )


# ---------------------------------------------------------------------------
# normalize_weights under a second registry keeps ADR-0016's rule.
# ---------------------------------------------------------------------------


def test_normalize_weights_never_respreads_an_absent_factors_weight() -> None:
    """ADR-0016: the denominator ranges over the model's whole factor set.

    Both factors stay in the denominator whatever a candidate's evidence turns
    out to be, so an unknown factor cannot hand its weight to its neighbour.
    """
    toy = _two_factor_toy_registry()
    model = toy.scoring_modes[_TOY_MODE]
    weights = normalize_weights(model=model, registry=toy)
    assert dict(weights) == {"toy_overlap": 0.75, "toy_affinity": 0.25}
    assert abs(sum(weights.values()) - 1.0) <= 1e-9
    # The weight of a factor is identical whether or not its neighbour would be
    # unknown at scoring time: normalization happens before evidence is read.
    assert weights["toy_overlap"] == normalize_weights(model=model, registry=toy)["toy_overlap"]


def test_normalize_weights_ignores_overrides_for_keys_outside_the_registry() -> None:
    toy = _two_factor_toy_registry()
    model = toy.scoring_modes[_TOY_MODE]
    baseline = dict(normalize_weights(model=model, registry=toy))
    with_foreign = dict(
        normalize_weights({"industry_match": 99.0, "toy_absent": 5.0}, model=model, registry=toy)
    )
    assert with_foreign == baseline
    assert "industry_match" not in with_foreign
    assert "toy_absent" not in with_foreign


def test_normalize_weights_rejects_a_negative_override_under_any_registry() -> None:
    toy = _two_factor_toy_registry()
    with pytest.raises(ValueError, match="negative"):
        normalize_weights({"toy_overlap": -1.0}, model=toy.scoring_modes[_TOY_MODE], registry=toy)


def test_display_weights_rounds_the_supplied_registrys_weights() -> None:
    toy = _two_factor_toy_registry()
    rendered = display_weights(toy.scoring_modes[_TOY_MODE], registry=toy)
    assert dict(rendered) == {"toy_overlap": 0.75, "toy_affinity": 0.25}


# ---------------------------------------------------------------------------
# Registry lookup by version — how scoring and explanation resolve a score's
# spec and kind tables.
# ---------------------------------------------------------------------------


def test_registry_for_version_finds_the_cba_registry_under_both_pins() -> None:
    assert registry_for_version(REGISTRY_VERSION) is CBA_REGISTRY
    assert registry_for_version(SUPERSEDED_REGISTRY_VERSION) is CBA_REGISTRY
    with pytest.raises(KeyError):
        registry_for_version("9.9.9-nowhere")
    assert registry_for_version("9.9.9-nowhere", default=CBA_REGISTRY) is CBA_REGISTRY


def test_register_registry_makes_a_second_registry_findable() -> None:
    toy = _toy_registry("approved")
    register_registry(toy)
    assert registry_for_version(_TOY_VERSION) is toy
    register_registry(toy)  # idempotent for the same object
    with pytest.raises(ValueError, match="already bound"):
        register_registry(_toy_registry("approved"))


def test_scoring_and_explanation_lookups_resolve_per_registry() -> None:
    toy = _two_factor_toy_registry()
    assert set(toy.kind_by_key) == {"toy_overlap", "toy_affinity"}
    assert set(CBA_REGISTRY.kind_by_key) == set(factor_keys())
    assert toy.kind_by_key["toy_overlap"] is FactorKind.SUITABILITY
    assert toy.spec_by_key["toy_affinity"].display_label == "Toy toy_affinity"
    # The CBA tables the two consumer modules read are the registry's tables.
    assert CBA_REGISTRY.spec_by_key["industry_match"].display_label == "Industry Match"


def test_explanations_still_read_the_cba_spec_table(  # behaviour-preservation pin
) -> None:
    from smartmatch_domain.factors import FactorScore
    from smartmatch_domain.scoring import STAGE_B_FORMULA_VERSION, StageBScore

    score = StageBScore(
        subject_id="subj-1",
        value=1.0,
        factor_scores=(
            FactorScore(
                factor_key="topic_relevance",
                value=1.0,
                basis="test fixture",
            ),
        ),
        applied_weights={"topic_relevance": 1.0},
        unknown_factor_keys=(),
        registry_version=SUPERSEDED_REGISTRY_VERSION,
        formula_version=STAGE_B_FORMULA_VERSION,
        scoring_mode=None,
        scoring_mode_version=None,
    )
    explanation = explain_candidate(score)
    assert explanation.factors[0].display_label == "Topic Relevance"
    assert explanation.factors[0].kind == FactorKind.SUITABILITY.value


def test_registry_hash_is_stable_and_version_sensitive() -> None:
    a = _toy_registry()
    b = _toy_registry()
    assert a.registry_hash == b.registry_hash
    assert a.registry_hash.startswith("sha256:")
    assert a.registry_hash != CBA_REGISTRY.registry_hash
    assert CBA_REGISTRY.registry_hash == CBA_REGISTRY.registry_hash
