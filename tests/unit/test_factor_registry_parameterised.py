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

import dataclasses
import re
import threading
from collections.abc import Iterator

import pytest
from smartmatch_domain import factor_registry as factor_registry_module
from smartmatch_domain.explanation import ScoreState, explain_candidate
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
    UnknownRegistryVersionError,
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
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.factors.proximity import CBA_SCORING_MODES, UnknownScoringModeError
from smartmatch_domain.scoring import STAGE_B_FORMULA_VERSION, StageBScore

# ---------------------------------------------------------------------------
# The toy registry: a fixture, not a product registry.
# ---------------------------------------------------------------------------

_TOY_VERSION = "0.0.1-toy"
_TOY_MODE = "toy-1"
_TOY_VOCABULARY = frozenset({_TOY_MODE})


def _toy_model(
    *,
    scoring_keys: tuple[str, ...] = ("toy_overlap",),
    registry_version: str = _TOY_VERSION,
) -> ScoringModel:
    return ScoringModel(
        registry_version=registry_version,
        scoring_mode=_TOY_MODE,
        scoring_mode_version="1.0.0",
        scoring_keys=scoring_keys,
        is_current=True,
        mode_vocabulary=_TOY_VOCABULARY,
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


def _toy_registry(status: str = "proposed", *, version: str = _TOY_VERSION) -> FactorRegistry:
    return FactorRegistry(
        version=version,
        status=status,
        approver=None,
        approved_on=None,
        factors=(_toy_spec("toy_overlap", 1.0),),
        approved_scoring_keys=frozenset({"toy_overlap"}),
        scoring_modes={_TOY_MODE: _toy_model(registry_version=version)},
        mode_vocabulary=_TOY_VOCABULARY,
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
                mode_vocabulary=_TOY_VOCABULARY,
            )
        },
        mode_vocabulary=_TOY_VOCABULARY,
    )


@pytest.fixture
def registered_toy() -> Iterator[FactorRegistry]:
    """Register a toy registry for one test and take it back out again.

    The version map is module-global process state. A test that registered a
    toy rulebook and left it there would change what every *later* test in the
    session resolves a version to, so the binding is undone in teardown through
    the module's private test hook rather than by a public unregister nobody
    should have.
    """
    toy = _toy_registry("proposed")
    register_registry(toy)
    try:
        yield toy
    finally:
        factor_registry_module._unregister_for_tests(toy.version)


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
    """Literals, not derivations.

    Restating the derivation the runtime uses would pass however the runtime's
    numbers moved, which is exactly what a behaviour-preservation pin must not
    do. These are the values ``main`` produces, written out.
    """
    assert factor_keys() == (
        "industry_match",
        "role_match",
        "cba_semantic_topic",
        "proximity",
        "topic_relevance",
        "travel_burden",
        "availability",
    )
    assert implemented_scoring_keys() == frozenset(
        {"industry_match", "role_match", "cba_semantic_topic", "proximity"}
    )
    assert dict(display_weights(CBA_PHYSICAL_MODEL)) == {
        "industry_match": 0.3,
        "role_match": 0.25,
        "cba_semantic_topic": 0.15,
        "proximity": 0.3,
    }
    # Customer §11's approved renderings for a virtual event.
    assert dict(display_weights(CBA_VIRTUAL_MODEL)) == {
        "industry_match": 0.428571,
        "role_match": 0.357143,
        "cba_semantic_topic": 0.214286,
    }
    assert dict(normalize_weights(model=SUPERSEDED_G1_MODEL)) == {
        "topic_relevance": 0.7,
        "travel_burden": 0.3,
    }
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
        scoring_modes={_TOY_MODE: _toy_model(registry_version="0.0.3-toy")},
        mode_vocabulary=_TOY_VOCABULARY,
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
            scoring_modes={
                _TOY_MODE: _toy_model(
                    scoring_keys=("toy_overlap", "toy_missing"), registry_version="0.0.4-toy"
                )
            },
            mode_vocabulary=_TOY_VOCABULARY,
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


def test_an_unknown_factors_weight_is_not_redistributed_to_the_others() -> None:
    """The unknown case ADR-0016 Proposal 6 refuses to re-spread, exercised.

    A weight table alone cannot show this: the re-spreading defect would show
    up on a score whose evidence *is* unknown. So this composes a CBA score
    with one factor unknown and reads the explanation back. The unknown factor
    keeps its own weight, its neighbours keep theirs unchanged, and the
    composite is unknown rather than a total computed over the known subset.
    """
    weights = dict(normalize_weights(model=CBA_PHYSICAL_MODEL))
    unknown_key = "proximity"
    assert unknown_key in weights

    score = StageBScore(
        subject_id="subj-unknown",
        value=None,
        factor_scores=tuple(
            FactorScore(
                factor_key=key,
                value=None if key == unknown_key else 1.0,
                basis="test fixture",
            )
            for key in CBA_PHYSICAL_MODEL.scoring_keys
        ),
        applied_weights=weights,
        unknown_factor_keys=(unknown_key,),
        registry_version=REGISTRY_VERSION,
        formula_version=STAGE_B_FORMULA_VERSION,
        scoring_mode="cba-physical-1",
        scoring_mode_version="1.0.0",
    )
    explanation = explain_candidate(score)

    assert explanation.state is ScoreState.UNKNOWN
    assert explanation.heuristic_score is None
    by_key = {factor.factor_key: factor for factor in explanation.factors}
    # The unknown factor still carries its full weight...
    assert by_key[unknown_key].weight == weights[unknown_key]
    # ...and none of it reached the other three.
    for key, weight in weights.items():
        assert by_key[key].weight == weight
    assert abs(sum(factor.weight for factor in explanation.factors) - 1.0) <= 1e-9


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


def test_registry_for_version_refuses_an_unknown_pin_rather_than_defaulting() -> None:
    """No fail-open resolution (review HIGH-1).

    ``registry_version`` on a stored score is free-form data. Resolving an
    unrecognised one to the CBA rulebook would hand it the CBA rulebook's
    *approval*, so a gate that must refuse would pass. The lookup refuses
    instead, and it refuses with the module's registry error type so the API
    and worker handlers that already catch ``RegistryNotReadyError`` keep
    turning it into a refusal rather than an unhandled ``KeyError``.
    """
    with pytest.raises(UnknownRegistryVersionError, match=re.escape("9.9.9-nowhere")):
        registry_for_version("9.9.9-nowhere")
    assert issubclass(UnknownRegistryVersionError, RegistryNotReadyError)


def test_register_registry_makes_a_second_registry_findable(
    registered_toy: FactorRegistry,
) -> None:
    assert registry_for_version(_TOY_VERSION) is registered_toy
    register_registry(registered_toy)  # idempotent for the same object
    assert registry_for_version(_TOY_VERSION) is registered_toy
    with pytest.raises(ValueError, match="already bound"):
        register_registry(_toy_registry("approved"))


def test_register_registry_is_taken_back_out_after_the_fixture() -> None:
    """The fixture's teardown is the point: no test leaks a binding."""
    with pytest.raises(UnknownRegistryVersionError):
        registry_for_version(_TOY_VERSION)


def test_register_registry_is_serialised_across_threads() -> None:
    """Check-then-set on a module global, done under a lock.

    Every thread registers the *same* object, so the only way a thread can see
    a failure is if one of them observed the map mid-update and rebound it.
    """
    toy = _toy_registry("approved", version="0.0.9-toy-threads")
    start = threading.Barrier(8)
    failures: list[BaseException] = []

    def _register() -> None:
        start.wait()
        try:
            register_registry(toy)
        except BaseException as exc:  # recorded, then asserted on below
            failures.append(exc)

    threads = [threading.Thread(target=_register) for _ in range(8)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert failures == []
        assert registry_for_version(toy.version) is toy
    finally:
        factor_registry_module._unregister_for_tests(toy.version)


def test_the_cba_pins_can_never_be_unregistered() -> None:
    """The test hook is private *and* refuses the pins every stored score uses."""
    with pytest.raises(ValueError, match="CBA"):
        factor_registry_module._unregister_for_tests(REGISTRY_VERSION)
    with pytest.raises(ValueError, match="CBA"):
        factor_registry_module._unregister_for_tests(SUPERSEDED_REGISTRY_VERSION)
    assert registry_for_version(REGISTRY_VERSION) is CBA_REGISTRY


def test_scoring_and_explanation_lookups_resolve_per_registry() -> None:
    toy = _two_factor_toy_registry()
    assert set(toy.kind_by_key) == {"toy_overlap", "toy_affinity"}
    assert set(CBA_REGISTRY.kind_by_key) == set(factor_keys())
    assert toy.kind_by_key["toy_overlap"] is FactorKind.SUITABILITY
    assert toy.spec_by_key["toy_affinity"].display_label == "Toy toy_affinity"
    # The CBA tables the two consumer modules read are the registry's tables.
    assert CBA_REGISTRY.spec_by_key["industry_match"].display_label == "Industry Match"


def test_the_registry_declares_no_registry_hash_of_its_own() -> None:
    """``registry_hash`` is already taken (review HIGH-2).

    The name is a shipped, persisted field — a schema column and an OpenAPI
    field, defined by ADR-0016 as the fingerprint of a run's *applied weights*.
    A second, differently-computed payload under the same name and the same
    ``sha256:`` prefix would be indistinguishable from it in a log or a row, so
    this refactor does not introduce one.
    """
    assert not hasattr(CBA_REGISTRY, "registry_hash")
    assert not hasattr(_toy_registry(), "registry_hash")


# ---------------------------------------------------------------------------
# A registry's identity: hashable, comparable, and copy-safe.
# ---------------------------------------------------------------------------


def test_a_registry_is_hashable() -> None:
    """Frozen values that cannot be hashed are frozen in name only."""
    assert isinstance(hash(CBA_REGISTRY), int)
    assert hash(CBA_REGISTRY) == hash(CBA_REGISTRY)
    assert len({CBA_REGISTRY, _toy_registry(), _two_factor_toy_registry()}) == 3


def test_structurally_different_registries_are_unequal() -> None:
    assert _toy_registry() == _toy_registry()
    assert _toy_registry() != _toy_registry("approved")
    assert _toy_registry() != _two_factor_toy_registry()
    assert _toy_registry() != CBA_REGISTRY


def test_a_replace_copy_of_the_cba_registry_behaves_like_the_cba_registry() -> None:
    """The CBA seams key on the version, not on object identity (review LOW).

    ``resolve_scoring_model(None, ...)`` and the two gate helpers have to know
    they are looking at *the CBA rulebook* — that is where the pre-mode model
    and the module-level status constants live. Keying that on ``is`` would
    make a ``dataclasses.replace`` copy, an unpickled copy or a copy from a
    reloaded module a different rulebook with the same contents, and
    ``resolve_scoring_model(None)`` would raise where it used to return the
    superseded model. Keying it on the version keeps the seam honest.
    """
    copy = dataclasses.replace(CBA_REGISTRY)
    assert copy is not CBA_REGISTRY
    assert copy == CBA_REGISTRY
    assert copy.version == CBA_REGISTRY.version

    assert resolve_scoring_model(None, registry=copy) is SUPERSEDED_G1_MODEL
    assert resolve_scoring_model("cba-physical-1", registry=copy) is CBA_PHYSICAL_MODEL
    assert_registry_approved(registry=copy)
    assert_scoring_ready(registry=copy)
    assert factor_keys(registry=copy) == factor_keys()
    assert dict(normalize_weights(registry=copy)) == dict(normalize_weights())


def test_the_cba_gate_reads_the_module_constants_not_the_registrys_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documented in ``assert_registry_approved``: one source of truth.

    On the CBA path the gate is read from ``REGISTRY_STATUS`` itself rather
    than from the snapshot ``CBA_REGISTRY`` took at import, so there is exactly
    one place the CBA status is declared. ``tests/unit/test_scoring.py`` relies
    on this, patching the constant to prove scoring fails closed.
    """
    monkeypatch.setattr(factor_registry_module, "REGISTRY_STATUS", "proposed")
    with pytest.raises(RegistryNotApprovedError):
        assert_registry_approved()
    with pytest.raises(RegistryNotApprovedError):
        assert_registry_approved(registry=dataclasses.replace(CBA_REGISTRY))


# ---------------------------------------------------------------------------
# A registry's models must belong to it.
# ---------------------------------------------------------------------------


def test_lookup_tables_are_built_once_not_per_access() -> None:
    """Scoring reads these per factor per candidate; they are not rebuilt."""
    assert CBA_REGISTRY.spec_by_key is CBA_REGISTRY.spec_by_key
    assert CBA_REGISTRY.kind_by_key is CBA_REGISTRY.kind_by_key


def test_a_registry_refuses_a_model_pinned_to_another_registry() -> None:
    with pytest.raises(ValueError, match="registry_version"):
        FactorRegistry(
            version="0.0.7-toy",
            status="approved",
            approver=None,
            approved_on=None,
            factors=(_toy_spec("toy_overlap", 1.0),),
            approved_scoring_keys=frozenset({"toy_overlap"}),
            # Pinned to _TOY_VERSION, filed under 0.0.7-toy.
            scoring_modes={_TOY_MODE: _toy_model()},
            mode_vocabulary=_TOY_VOCABULARY,
        )


def test_a_registry_refuses_a_model_carrying_another_registrys_vocabulary() -> None:
    """A second rulebook must not silently inherit the CBA vocabulary.

    ``ScoringModel.mode_vocabulary`` defaults to the CBA one so every existing
    construction site keeps the check it had. That default must not become a
    way for a second registry to declare ``cba-physical-1`` as one of its own
    modes.
    """
    with pytest.raises(ValueError, match="mode_vocabulary"):
        FactorRegistry(
            version=REGISTRY_VERSION,
            status="approved",
            approver=None,
            approved_on=None,
            factors=PROPOSED_FACTORS,
            approved_scoring_keys=APPROVED_SCORING_KEYS,
            scoring_modes=dict(SCORING_MODELS),
            # The registry claims a toy vocabulary while its models carry the
            # CBA one.
            mode_vocabulary=_TOY_VOCABULARY,
        )


def test_the_cba_registry_declares_the_cba_vocabulary() -> None:
    assert CBA_REGISTRY.mode_vocabulary == CBA_SCORING_MODES
    assert set(CBA_REGISTRY.scoring_modes) <= CBA_REGISTRY.mode_vocabulary


# ---------------------------------------------------------------------------
# The gate is the gate of the registry the score names (review HIGH-1).
# ---------------------------------------------------------------------------


def _cba_score(registry_version: str) -> StageBScore:
    return StageBScore(
        subject_id="subj-1",
        value=1.0,
        factor_scores=(FactorScore(factor_key="topic_relevance", value=1.0, basis="test fixture"),),
        applied_weights={"topic_relevance": 1.0},
        unknown_factor_keys=(),
        registry_version=registry_version,
        formula_version=STAGE_B_FORMULA_VERSION,
        scoring_mode=None,
        scoring_mode_version=None,
    )


def test_explaining_a_score_with_an_unknown_registry_version_is_refused() -> None:
    """The fail-open hole: an unrecognised pin must not borrow CBA's approval."""
    with pytest.raises(UnknownRegistryVersionError, match=re.escape("9.9.9-nowhere")):
        explain_candidate(_cba_score("9.9.9-nowhere"))


def test_explaining_a_score_pinned_to_a_proposed_registry_is_refused(
    registered_toy: FactorRegistry,
) -> None:
    """A registered but unapproved rulebook fails the G1 gate, not passes it."""
    assert registered_toy.status == "proposed"
    with pytest.raises(RegistryNotApprovedError):
        explain_candidate(_cba_score(registered_toy.version))


@pytest.mark.parametrize("pin", [REGISTRY_VERSION, SUPERSEDED_REGISTRY_VERSION])
def test_explaining_a_score_under_either_cba_pin_is_unchanged(pin: str) -> None:
    """Behaviour-preservation pin: both CBA pins read the CBA spec table."""
    explanation = explain_candidate(_cba_score(pin))
    assert explanation.registry_version == pin
    assert explanation.factors[0].display_label == "Topic Relevance"
    assert explanation.factors[0].kind == FactorKind.SUITABILITY.value


def test_the_scoring_kind_table_refuses_an_unknown_registry_version() -> None:
    """The scoring-side twin of the explanation gate."""
    from smartmatch_domain import scoring

    assert scoring._kind_table(REGISTRY_VERSION) == dict(CBA_REGISTRY.kind_by_key)
    assert scoring._kind_table(SUPERSEDED_REGISTRY_VERSION) == dict(CBA_REGISTRY.kind_by_key)
    with pytest.raises(UnknownRegistryVersionError, match=re.escape("9.9.9-nowhere")):
        scoring._kind_table("9.9.9-nowhere")
