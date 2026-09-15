# Student→Event Recommender V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the content-based student→event recommender (ADR-0018 D1–D3, D7, D8) behind a closed gate, with the Stage B interface and the V2 feature registry shaped so a learned ranker replaces one component later without touching the HTTP contract.

**Architecture:** Three stages behind protocols — `EligibilityFilter` → `StudentRanker` → `FeedPolicy` — composed by one `recommend()` function. Stage B V1 is a `ContentRanker` over a separate `STUDENT_REGISTRY` (Jaccard over the shared G3 vocabulary), built by parameterising the existing CBA `factor_registry` mechanism into a `FactorRegistry` value object. The registry ships `proposed` and fails closed; the route returns a worded 409 until OQ-SE-01 closes.

**Tech Stack:** Python 3.12, frozen dataclasses, `smartmatch_domain` (pure), FastAPI + Pydantic v2 in `services/api`, pytest (`make test`, no database), `make openapi` for the exported contract. No new runtime dependency in V1.

**Spec:** `docs/architecture/decisions/ADR-0018-staged-student-event-recommender.md`, `docs/architecture/student-recommender-contracts.md`, `docs/decisions/student-recommender-decision-record.md`.

**Review amendments (2026-09-14):** see `docs/superpowers/plans/2026-09-14-student-recommender-review-fixes.md` — soft diversity preference (owner decision), hour-anchored window, candidate evidence in `inputs_hash`, in-pipeline primary tags, bounded learned factors, and OQ-SC-11 as a training prerequisite.

## Global Constraints

- `tests/unit/test_factor_registry.py` is **not edited by one line** in any task. It is the pin that the CBA path did not move.
- No student module imports `student_speaker_feedback`, `attendance`, `event_registration`, or `feedback` (ADR-0018 D4 condition 2; OQ-CBA-053).
- `PROHIBITED_INPUTS` is imported from `smartmatch_domain.factor_registry`, never redefined.
- No number-typed property named like `score|value|percent|match|fit|rating|confidence` on the student HTTP response. `rank` and `withheld_*` are the only integers on items and the envelope.
- `STUDENT_REGISTRY_STATUS = "proposed"` until an OQ-SE-01 artifact flips it. Tests assert the closed gate as a positive assertion.
- Domain constants live in `smartmatch_domain/student_recommender/student_feed.py`: `STUDENT_FEED_WINDOW_DAYS = 7`, `STUDENT_FEED_MAX_ITEMS = 5`, `STUDENT_FEED_WILDCARD_SLOTS = 1`, `STUDENT_FEED_MAX_PER_PRIMARY_TAG = 3`, `STUDENT_FEED_POLICY_VERSION = "feed-1.0.0"`.
- Vocabulary: `smartmatch_domain.event_vocabulary.VOCABULARY_VERSION` (`"g3-2026-08-29"`), referenced, never retyped.
- Every `basis` and `reason` string passes `smartmatch_domain.one_sentence.assert_one_sentence(text, field=...)`.
- Package boundaries (`make imports`, ADR-0002): `smartmatch_domain` imports nothing from `services/` or `smartmatch_persistence`.
- Tasks 1–7 and 9–10 need no database and no profile table. Task 8 (the route) lands only after the W1 profile table exists (OQ-SC-02); until then it is built against the `StudentProfileReader` protocol with an in-memory fake.
- Commit after every task; conventional commit prefixes; no attribution lines beyond what the session reminder requires.

---

### Task 1: `FactorRegistry` value object — parameterise the CBA mechanism (W2a)

**Files:**
- Modify: `python/smartmatch_domain/smartmatch_domain/factor_registry.py`
- Modify: `python/smartmatch_domain/smartmatch_domain/scoring.py:104` (`_FACTOR_KIND`), `:312`, `:606`
- Modify: `python/smartmatch_domain/smartmatch_domain/explanation.py:130` (`_SPECS_BY_KEY`), `:423`, `:444-460`
- Test: `tests/unit/test_factor_registry_parametrised.py`

**Interfaces:**
- Consumes: existing `FactorSpec`, `ScoringModel`, `PROPOSED_FACTORS`, `APPROVED_SCORING_KEYS`, `SCORING_MODELS`, `CBA_SCORING_MODES`.
- Produces: `FactorRegistry` (frozen dataclass), `CBA_REGISTRY: FactorRegistry`, `registry_for_version(version: str) -> FactorRegistry`, `register_registry(registry: FactorRegistry) -> None`, and keyword-only `registry: FactorRegistry = CBA_REGISTRY` on `assert_registry_approved`, `assert_scoring_ready`, `factor_keys`, `implemented_scoring_keys`, `resolve_scoring_model`, `normalize_weights`, `display_weights`, `proposed_weights`, `active_weights`. `ScoringModel` gains `mode_vocabulary: frozenset[str] = CBA_SCORING_MODES` as its last field.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_factor_registry_parametrised.py
"""W2a pin: the CBA registry is a value object, and every free function defaults to it."""
from __future__ import annotations

import pytest
from smartmatch_domain.factor_registry import (
    APPROVED_SCORING_KEYS,
    CBA_PHYSICAL_MODEL,
    CBA_REGISTRY,
    CBA_VIRTUAL_MODEL,
    PROPOSED_FACTORS,
    REGISTRY_APPROVED_ON,
    REGISTRY_APPROVER,
    REGISTRY_STATUS,
    REGISTRY_VERSION,
    FactorKind,
    FactorRegistry,
    FactorSpec,
    RegistryNotApprovedError,
    ScoringModel,
    assert_registry_approved,
    factor_keys,
    implemented_scoring_keys,
    normalize_weights,
    register_registry,
    registry_for_version,
    resolve_scoring_model,
)
from smartmatch_domain.factors.proximity import UnknownScoringModeError


def test_cba_registry_is_bound_to_the_module_constants() -> None:
    assert CBA_REGISTRY.version == REGISTRY_VERSION
    assert CBA_REGISTRY.status == REGISTRY_STATUS
    assert CBA_REGISTRY.approver == REGISTRY_APPROVER
    assert CBA_REGISTRY.approved_on == REGISTRY_APPROVED_ON
    assert CBA_REGISTRY.factors is PROPOSED_FACTORS
    assert CBA_REGISTRY.approved_scoring_keys == APPROVED_SCORING_KEYS
    assert CBA_REGISTRY.scoring_modes["cba-physical-1"] is CBA_PHYSICAL_MODEL
    assert CBA_REGISTRY.scoring_modes["cba-virtual-1"] is CBA_VIRTUAL_MODEL


def test_free_functions_default_to_the_cba_registry() -> None:
    assert factor_keys() == factor_keys(registry=CBA_REGISTRY)
    assert implemented_scoring_keys() == implemented_scoring_keys(registry=CBA_REGISTRY)
    assert dict(normalize_weights()) == dict(normalize_weights(registry=CBA_REGISTRY))
    assert resolve_scoring_model("cba-physical-1", registry=CBA_REGISTRY) is CBA_PHYSICAL_MODEL


def _toy_registry(status: str = "proposed") -> FactorRegistry:
    spec = FactorSpec(
        key="toy_overlap",
        display_label="Toy overlap",
        kind=FactorKind.SUITABILITY,
        proposed_weight=1.0,
        implemented=True,
        rationale="A one-factor registry for the parameterisation tests.",
    )
    model = ScoringModel(
        registry_version="0.0.1-toy",
        scoring_mode="toy-1",
        scoring_mode_version="1.0.0",
        scoring_keys=("toy_overlap",),
        is_current=True,
        mode_vocabulary=frozenset({"toy-1"}),
    )
    return FactorRegistry(
        version="0.0.1-toy",
        status=status,
        approver=None,
        approved_on=None,
        factors=(spec,),
        approved_scoring_keys=frozenset({"toy_overlap"}),
        scoring_modes={"toy-1": model},
    )


def test_a_second_registry_scores_over_its_own_factors_only() -> None:
    toy = _toy_registry()
    assert factor_keys(registry=toy) == ("toy_overlap",)
    assert implemented_scoring_keys(registry=toy) == frozenset({"toy_overlap"})
    weights = normalize_weights(model=toy.scoring_modes["toy-1"], registry=toy)
    assert dict(weights) == {"toy_overlap": 1.0}


def test_a_proposed_registry_fails_closed() -> None:
    with pytest.raises(RegistryNotApprovedError):
        assert_registry_approved(registry=_toy_registry("proposed"))
    assert_registry_approved(registry=_toy_registry("approved"))


def test_modes_are_closed_per_registry() -> None:
    toy = _toy_registry()
    with pytest.raises(UnknownScoringModeError, match="closed"):
        resolve_scoring_model("cba-physical-1", registry=toy)
    with pytest.raises(UnknownScoringModeError, match="closed"):
        resolve_scoring_model("toy-1", registry=CBA_REGISTRY)


def test_a_model_refuses_a_mode_outside_its_own_vocabulary() -> None:
    with pytest.raises(UnknownScoringModeError, match="closed"):
        ScoringModel(
            registry_version="0.0.1-toy",
            scoring_mode="cba-physical-1",
            scoring_mode_version="1.0.0",
            scoring_keys=("toy_overlap",),
            is_current=True,
            mode_vocabulary=frozenset({"toy-1"}),
        )


def test_registry_for_version_finds_registered_registries() -> None:
    assert registry_for_version(REGISTRY_VERSION) is CBA_REGISTRY
    toy = _toy_registry()
    register_registry(toy)
    assert registry_for_version("0.0.1-toy") is toy
    with pytest.raises(KeyError):
        registry_for_version("9.9.9-nowhere")


def test_registry_hash_is_stable_and_version_sensitive() -> None:
    a = _toy_registry()
    b = _toy_registry()
    assert a.registry_hash == b.registry_hash
    assert a.registry_hash.startswith("sha256:")
    assert a.registry_hash != CBA_REGISTRY.registry_hash
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_factor_registry_parametrised.py -q`
Expected: FAIL with `ImportError: cannot import name 'FactorRegistry'`

- [ ] **Step 3: Add `FactorRegistry`, the lookup table, and the `mode_vocabulary` field**

In `factor_registry.py`, after `ScoringModel` (keep every existing constant; add to `__all__`: `"CBA_REGISTRY"`, `"FactorRegistry"`, `"register_registry"`, `"registry_for_version"`):

```python
import hashlib
import json


@dataclass(frozen=True, slots=True)
class ScoringModel:
    registry_version: str
    scoring_mode: str | None
    scoring_mode_version: str | None
    scoring_keys: tuple[str, ...]
    is_current: bool
    #: The closed mode vocabulary this model must belong to. Defaults to the
    #: CBA vocabulary so every existing construction site is unchanged; a
    #: second registry passes its own (ADR-0018 D2).
    mode_vocabulary: frozenset[str] = CBA_SCORING_MODES

    def __post_init__(self) -> None:
        if not self.scoring_keys:
            raise ValueError("scoring_keys: a scoring model must score at least one factor")
        if (self.scoring_mode is None) != (self.scoring_mode_version is None):
            raise ValueError(
                "scoring_mode and scoring_mode_version must be set or unset together; "
                f"got {self.scoring_mode!r} and {self.scoring_mode_version!r}"
            )
        if self.scoring_mode is not None and self.scoring_mode not in self.mode_vocabulary:
            raise UnknownScoringModeError(
                f"scoring_mode: must be one of {sorted(self.mode_vocabulary)} or None, got "
                f"{self.scoring_mode!r}. The mode vocabulary is closed (ADR-0016 Proposal 5)."
            )


@dataclass(frozen=True, slots=True)
class FactorRegistry:
    """One rulebook: its factors, its approval state, and its closed mode set.

    ADR-0018 D2. The CBA registry and the student registry are two values of
    this type sharing one mechanism; nothing here is copied per registry.
    """

    version: str
    status: str
    approver: str | None
    approved_on: str | None
    factors: tuple[FactorSpec, ...]
    approved_scoring_keys: frozenset[str]
    scoring_modes: Mapping[str, ScoringModel]

    def __post_init__(self) -> None:
        if self.status not in {"approved", "proposed"}:
            raise ValueError(f"status: must be 'approved' or 'proposed', got {self.status!r}")
        keys = [spec.key for spec in self.factors]
        if len(set(keys)) != len(keys):
            raise ValueError("factors: duplicate factor key")
        for mode, model in self.scoring_modes.items():
            if model.scoring_mode != mode:
                raise ValueError(f"scoring_modes[{mode!r}] names mode {model.scoring_mode!r}")
            unknown = set(model.scoring_keys) - set(keys)
            if unknown:
                raise ValueError(f"scoring_modes[{mode!r}] scores undeclared keys {sorted(unknown)}")
        object.__setattr__(self, "scoring_modes", MappingProxyType(dict(self.scoring_modes)))

    @property
    def spec_by_key(self) -> Mapping[str, FactorSpec]:
        return MappingProxyType({spec.key: spec for spec in self.factors})

    @property
    def kind_by_key(self) -> Mapping[str, FactorKind]:
        return MappingProxyType({spec.key: spec.kind for spec in self.factors})

    @property
    def registry_hash(self) -> str:
        payload = {
            "version": self.version,
            "factors": [
                [spec.key, spec.kind.value, repr(spec.active_weight), spec.implemented]
                for spec in self.factors
            ],
            "modes": {mode: list(model.scoring_keys) for mode, model in sorted(self.scoring_modes.items())},
        }
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


CBA_REGISTRY: Final[FactorRegistry] = FactorRegistry(
    version=REGISTRY_VERSION,
    status=REGISTRY_STATUS,
    approver=REGISTRY_APPROVER,
    approved_on=REGISTRY_APPROVED_ON,
    factors=PROPOSED_FACTORS,
    approved_scoring_keys=APPROVED_SCORING_KEYS,
    scoring_modes=SCORING_MODELS,
)

_REGISTRIES_BY_VERSION: dict[str, FactorRegistry] = {
    CBA_REGISTRY.version: CBA_REGISTRY,
    SUPERSEDED_REGISTRY_VERSION: CBA_REGISTRY,  # 1.x runs are read under the CBA spec table
}


def register_registry(registry: FactorRegistry) -> None:
    """Make ``registry`` findable by version for stored-score readers."""
    existing = _REGISTRIES_BY_VERSION.get(registry.version)
    if existing is not None and existing is not registry:
        raise ValueError(f"registry version {registry.version!r} is already bound")
    _REGISTRIES_BY_VERSION[registry.version] = registry


def registry_for_version(version: str) -> FactorRegistry:
    """Return the registry a stored score names, or raise ``KeyError``."""
    return _REGISTRIES_BY_VERSION[version]
```

Note `CBA_REGISTRY` must be defined **after** `SCORING_MODELS` (line ~501) and before the gate functions.

- [ ] **Step 4: Thread `registry` through every free function**

Replace the bodies (signatures shown; keep docstrings, add an `Args: registry:` line to each):

```python
def resolve_scoring_model(
    scoring_mode: str | None, *, registry: FactorRegistry = CBA_REGISTRY
) -> ScoringModel:
    if scoring_mode is None:
        if registry is CBA_REGISTRY:
            return SUPERSEDED_G1_MODEL
        raise UnknownScoringModeError(
            f"scoring_mode: registry {registry.version!r} has no pre-mode model; None is refused."
        )
    try:
        return registry.scoring_modes[scoring_mode]
    except KeyError:
        raise UnknownScoringModeError(
            f"scoring_mode: must be one of {sorted(registry.scoring_modes)} or None, got "
            f"{scoring_mode!r}. The mode vocabulary is closed (ADR-0016 Proposal 5); "
            "an unrecognised mode is refused rather than defaulted."
        ) from None


def assert_registry_approved(*, registry: FactorRegistry = CBA_REGISTRY) -> None:
    if registry.status != "approved":
        raise RegistryNotApprovedError(
            f"Factor registry {registry.version} is {registry.status!r}. "
            "Scoring is blocked until the program owner approves the registry contents "
            "and the golden case set."
        )


def factor_keys(*, registry: FactorRegistry = CBA_REGISTRY) -> tuple[str, ...]:
    return tuple(spec.key for spec in registry.factors)


def implemented_scoring_keys(*, registry: FactorRegistry = CBA_REGISTRY) -> frozenset[str]:
    return frozenset(
        spec.key for spec in registry.factors if spec.implemented and spec.is_scoring and not spec.is_retired
    )


def assert_scoring_ready(*, registry: FactorRegistry = CBA_REGISTRY) -> None:
    implemented = implemented_scoring_keys(registry=registry)
    approved = registry.approved_scoring_keys
    if implemented != approved:
        missing = approved - implemented
        extra = implemented - approved
        raise RegistryNotReadyError(
            "Implemented Stage B scoring set does not match the approved set "
            f"{sorted(approved)}. Missing: {sorted(missing) or 'none'}. Extra: {sorted(extra) or 'none'}."
        )
    for model in registry.scoring_modes.values():
        if not model.is_current:
            continue
        weight_total = sum(normalize_weights(model=model, registry=registry).values())
        if abs(weight_total - 1.0) > 1e-9:
            raise RegistryNotReadyError(
                f"Normalized Stage B weights for {model.scoring_mode!r} sum to {weight_total!r}, not 1.0."
            )


def proposed_weights(*, registry: FactorRegistry = CBA_REGISTRY) -> Mapping[str, float]:
    return MappingProxyType({spec.key: spec.proposed_weight for spec in registry.factors})


def active_weights(*, registry: FactorRegistry = CBA_REGISTRY) -> Mapping[str, float]:
    return MappingProxyType(
        {spec.key: spec.active_weight for spec in registry.factors if spec.active_weight > 0.0}
    )


def normalize_weights(
    weights: Mapping[str, float] | None = None,
    *,
    model: ScoringModel = CBA_PHYSICAL_MODEL,
    registry: FactorRegistry = CBA_REGISTRY,
) -> Mapping[str, float]:
    by_key = registry.spec_by_key
    scoring = {
        key: by_key[key].proposed_weight
        for key in model.scoring_keys
        if key in by_key and by_key[key].implemented and by_key[key].is_scoring
    }
    if weights is not None:
        for key, value in weights.items():
            if value < 0.0:
                raise ValueError(f"{key}: weight must not be negative (got {value})")
            if key in scoring:
                scoring[key] = float(value)
    total = sum(scoring.values())
    if total <= 0.0:
        return MappingProxyType(dict.fromkeys(scoring, 0.0))
    return MappingProxyType({key: value / total for key, value in scoring.items()})


def display_weights(
    model: ScoringModel = CBA_PHYSICAL_MODEL, *, registry: FactorRegistry = CBA_REGISTRY
) -> Mapping[str, float]:
    return MappingProxyType(
        {key: round(value, _WEIGHT_DISPLAY_PRECISION) for key, value in normalize_weights(model=model, registry=registry).items()}
    )
```

`assert_scoring_ready`'s original loop over `(CBA_PHYSICAL_MODEL, CBA_VIRTUAL_MODEL)` becomes the `is_current` loop above; `SUPERSEDED_G1_MODEL` is `is_current=False` and is skipped exactly as before.

- [ ] **Step 5: Make `scoring.py` and `explanation.py` look kinds and specs up by the score's registry**

`scoring.py`: delete the module-level `_FACTOR_KIND` (line 104). At both use sites (lines ~312 and ~606) replace `kind = _FACTOR_KIND[score.factor_key]` with:

```python
kind = registry_for_version(registry_version).kind_by_key[score.factor_key]
```

where `registry_version` is the value the surrounding function already places on the `StageBScore` it builds (`SUPERSEDED_G1_MODEL.registry_version` in `score_candidate`, `model.registry_version` in `_compose_cba`). Import `registry_for_version` from `factor_registry`.

`explanation.py`: delete `_SPECS_BY_KEY` (line 130). Change `_explain_factor(score, weight)` to `_explain_factor(score, weight, *, spec_by_key: Mapping[str, FactorSpec])` and use `spec_by_key.get(score.factor_key)`. In `explain_candidate`, replace `assert_registry_approved()` with:

```python
registry = registry_for_version(score.registry_version)
assert_registry_approved(registry=registry)
spec_by_key = registry.spec_by_key
```

and pass `spec_by_key=spec_by_key` to every `_explain_factor` call. This is also the fix the file's own comment asks for: the spec table now follows the score, like the weights already do.

- [ ] **Step 6: Run the new test and the untouched pins**

Run: `.venv/bin/python -m pytest tests/unit/test_factor_registry_parametrised.py tests/unit/test_factor_registry.py tests/unit/test_scoring.py tests/unit/test_cba_scoring_decision_artifact.py tests/unit/test_cba_matching_golden.py tests/unit/test_matching_approved_golden.py -q`
Expected: all PASS. Then `git diff --stat tests/unit/test_factor_registry.py` prints nothing.

- [ ] **Step 7: Lint, types, imports**

Run: `make lint typecheck imports`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add python/smartmatch_domain/smartmatch_domain/factor_registry.py python/smartmatch_domain/smartmatch_domain/scoring.py python/smartmatch_domain/smartmatch_domain/explanation.py tests/unit/test_factor_registry_parametrised.py
git commit -m "refactor: parameterise factor_registry into a FactorRegistry value object (ADR-0018 D2, W2a)"
```

---

### Task 2: `student_interest_overlap` — evidence dataclasses and the Jaccard factor

**Files:**
- Create: `python/smartmatch_domain/smartmatch_domain/factors/student_interest_overlap.py`
- Test: `tests/unit/test_student_interest_overlap.py`

**Interfaces:**
- Consumes: `FactorScore`, `FACTOR_SCORE_PRECISION` from `smartmatch_domain.factors`; `VOCABULARY_VERSION` from `smartmatch_domain.event_vocabulary`; `assert_one_sentence` from `smartmatch_domain.one_sentence`.
- Produces: `STUDENT_INTEREST_OVERLAP_FACTOR_KEY = "student_interest_overlap"`, `STUDENT_INTEREST_VOCABULARY_VERSION`, `StudentInterestState`, `EventTagState`, `StudentInterestEvidence`, `EventTagEvidence`, `score_student_interest_overlap(interests, tags) -> FactorScore`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_student_interest_overlap.py
from __future__ import annotations

import pytest
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION
from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorState, ZeroClassification
from smartmatch_domain.factors.student_interest_overlap import (
    STUDENT_INTEREST_OVERLAP_FACTOR_KEY,
    EventTagEvidence,
    EventTagState,
    StudentInterestEvidence,
    StudentInterestState,
    score_student_interest_overlap,
)
from smartmatch_domain.one_sentence import assert_one_sentence

V = VOCABULARY_VERSION


def _declared(*terms: str) -> StudentInterestEvidence:
    return StudentInterestEvidence(StudentInterestState.DECLARED, frozenset(terms), V)


def _tagged(*terms: str, quarantined: int = 0) -> EventTagEvidence:
    return EventTagEvidence(EventTagState.TAGGED, frozenset(terms), quarantined, V)


def _assert_unknown(score, needle: str) -> None:
    assert score.factor_key == STUDENT_INTEREST_OVERLAP_FACTOR_KEY
    assert score.value is None
    assert score.state is FactorState.UNKNOWN
    assert score.zero_classification is ZeroClassification.UNKNOWN
    assert needle in score.basis
    assert_one_sentence(score.basis, field="basis")


def test_no_profile_is_unknown() -> None:
    interests = StudentInterestEvidence(StudentInterestState.NO_PROFILE, frozenset(), V)
    _assert_unknown(score_student_interest_overlap(interests, _tagged("finance")), "No interest profile")


def test_declared_but_empty_is_unknown() -> None:
    _assert_unknown(score_student_interest_overlap(_declared(), _tagged("finance")), "lists no interests")


def test_no_tag_records_is_unknown() -> None:
    tags = EventTagEvidence(EventTagState.NO_TAG_RECORDS, frozenset(), 0, V)
    _assert_unknown(score_student_interest_overlap(_declared("finance"), tags), "no vocabulary tags")


def test_tagged_but_none_mapped_is_unknown() -> None:
    _assert_unknown(
        score_student_interest_overlap(_declared("finance"), _tagged(quarantined=2)), "None of this event's tags"
    )


def test_disjoint_sets_are_a_measured_zero() -> None:
    score = score_student_interest_overlap(_declared("finance"), _tagged("hackathon", "workshop"))
    assert score.value == 0.0
    assert score.state is FactorState.MEASURED
    assert score.zero_classification is ZeroClassification.MEASURED_ZERO
    assert "2 tags" in score.basis
    assert_one_sentence(score.basis, field="basis")


def test_overlap_is_jaccard_rounded() -> None:
    score = score_student_interest_overlap(_declared("finance", "hackathon"), _tagged("hackathon", "workshop", "finance"))
    assert score.value == round(2 / 3, FACTOR_SCORE_PRECISION)
    assert score.state is FactorState.MEASURED
    assert score.zero_classification is None
    assert "finance and hackathon" in score.basis
    assert "two of this event's three tags" in score.basis
    assert_one_sentence(score.basis, field="basis")


def test_declaring_everything_scores_worse_than_declaring_accurately() -> None:
    twelve = _declared(*[f"t{i}" for i in range(10)], "finance", "hackathon")
    two = _declared("finance", "hackathon")
    event = _tagged("finance", "hackathon")
    assert score_student_interest_overlap(two, event).value == 1.0
    assert score_student_interest_overlap(twelve, event).value == round(2 / 12, FACTOR_SCORE_PRECISION)


def test_vocabulary_mismatch_raises_at_construction() -> None:
    with pytest.raises(ValueError, match="vocabulary_version"):
        StudentInterestEvidence(StudentInterestState.DECLARED, frozenset({"finance"}), "g3-1999-01-01")
    with pytest.raises(ValueError, match="vocabulary_version"):
        EventTagEvidence(EventTagState.TAGGED, frozenset({"finance"}), 0, "g3-1999-01-01")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_student_interest_overlap.py -q`
Expected: FAIL with `ModuleNotFoundError: smartmatch_domain.factors.student_interest_overlap`

- [ ] **Step 3: Implement the factor**

```python
# python/smartmatch_domain/smartmatch_domain/factors/student_interest_overlap.py
"""Set overlap between a student's declared interests and an event's mapped tags.

ADR-0018 D3. Lexical and deterministic over the closed G3 vocabulary; no
provider, no neutral. A set that was read and does not overlap is a measured
zero; a set that could not be established is unknown (ADR-0011).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION
from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorScore
from smartmatch_domain.one_sentence import assert_one_sentence

__all__ = [
    "STUDENT_INTEREST_OVERLAP_FACTOR_KEY",
    "STUDENT_INTEREST_VOCABULARY_VERSION",
    "EventTagEvidence",
    "EventTagState",
    "StudentInterestEvidence",
    "StudentInterestState",
    "score_student_interest_overlap",
]

STUDENT_INTEREST_OVERLAP_FACTOR_KEY: Final[str] = "student_interest_overlap"
#: Referenced, never retyped (W1 §2): interests and tags share one vocabulary.
STUDENT_INTEREST_VOCABULARY_VERSION: Final[str] = VOCABULARY_VERSION


class StudentInterestState(StrEnum):
    DECLARED = "declared"
    NO_PROFILE = "no_profile"


class EventTagState(StrEnum):
    TAGGED = "tagged"
    NO_TAG_RECORDS = "no_tag_records"


def _check_version(version: str) -> None:
    if version != STUDENT_INTEREST_VOCABULARY_VERSION:
        raise ValueError(
            f"vocabulary_version: expected {STUDENT_INTEREST_VOCABULARY_VERSION!r}, got {version!r}; "
            "interests and tags must be read at the same vocabulary version (caller bug)"
        )


@dataclass(frozen=True, slots=True)
class StudentInterestEvidence:
    """The student's declared interests, as the caller resolved them."""

    state: StudentInterestState
    terms: frozenset[str]
    vocabulary_version: str

    def __post_init__(self) -> None:
        _check_version(self.vocabulary_version)
        if self.state is StudentInterestState.NO_PROFILE and self.terms:
            raise ValueError("terms: NO_PROFILE evidence cannot carry terms")


@dataclass(frozen=True, slots=True)
class EventTagEvidence:
    """The event's mapped vocabulary tags, as the caller resolved them."""

    state: EventTagState
    mapped_terms: frozenset[str]
    quarantined_count: int
    vocabulary_version: str

    def __post_init__(self) -> None:
        _check_version(self.vocabulary_version)
        if self.quarantined_count < 0:
            raise ValueError("quarantined_count: must not be negative")
        if self.state is EventTagState.NO_TAG_RECORDS and (self.mapped_terms or self.quarantined_count):
            raise ValueError("NO_TAG_RECORDS evidence cannot carry tags")


def _unknown(text: str) -> FactorScore:
    return FactorScore(
        factor_key=STUDENT_INTEREST_OVERLAP_FACTOR_KEY,
        value=None,
        basis=assert_one_sentence(text, field="basis"),
    )


def _words(terms: frozenset[str]) -> str:
    ordered = sorted(terms)
    if len(ordered) == 1:
        return ordered[0]
    return ", ".join(ordered[:-1]) + " and " + ordered[-1]


_COUNT_WORDS: Final[dict[int, str]] = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _count(n: int) -> str:
    return _COUNT_WORDS.get(n, str(n))


def score_student_interest_overlap(
    interests: StudentInterestEvidence, tags: EventTagEvidence
) -> FactorScore:
    """Jaccard ``|I ∩ T| / |I ∪ T|`` over the closed vocabulary, or an explicit absence."""
    version = STUDENT_INTEREST_VOCABULARY_VERSION
    if interests.state is StudentInterestState.NO_PROFILE:
        return _unknown(f"No interest profile on file for this student ({version}).")
    if not interests.terms:
        return _unknown(f"The interest profile lists no interests ({version}).")
    if tags.state is EventTagState.NO_TAG_RECORDS:
        return _unknown(f"This event carries no vocabulary tags and is not evaluable ({version}).")
    if not tags.mapped_terms:
        return _unknown(f"None of this event's tags resolved to the vocabulary ({version}).")

    shared = interests.terms & tags.mapped_terms
    if not shared:
        text = (
            f"None of your interests appear among this event's {len(tags.mapped_terms)} tags ({version})."
        )
        return FactorScore(
            factor_key=STUDENT_INTEREST_OVERLAP_FACTOR_KEY,
            value=0.0,
            basis=assert_one_sentence(text, field="basis"),
        )

    jaccard = len(shared) / len(interests.terms | tags.mapped_terms)
    text = (
        f"Your interests {_words(shared)} match {_count(len(shared))} of this event's "
        f"{_count(len(tags.mapped_terms))} tags ({version})."
    )
    return FactorScore(
        factor_key=STUDENT_INTEREST_OVERLAP_FACTOR_KEY,
        value=round(jaccard, FACTOR_SCORE_PRECISION),
        basis=assert_one_sentence(text, field="basis"),
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/test_student_interest_overlap.py -q`
Expected: 8 PASS. If `assert_one_sentence` rejects the version token, check that `(g3-2026-08-29).` keeps the dots followed by `)` — W2 §4 says this survives the sentence regex; adjust the phrasing, not the validator.

- [ ] **Step 5: Commit**

```bash
git add python/smartmatch_domain/smartmatch_domain/factors/student_interest_overlap.py tests/unit/test_student_interest_overlap.py
git commit -m "feat: student_interest_overlap factor with six evidence rows (ADR-0018 D3)"
```

---

### Task 3: `STUDENT_REGISTRY`, shipped with the gate shut (W2b)

**Files:**
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/__init__.py` (empty docstring module)
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/registry.py`
- Test: `tests/unit/test_student_factor_registry.py`, `tests/unit/test_scoring_registry_isolation.py`, `tests/unit/test_student_scoring_inputs_wiring.py`

**Interfaces:**
- Consumes: Task 1's `FactorRegistry`, `ScoringModel`, `FactorSpec`, `FactorKind`, `register_registry`, `PROHIBITED_INPUTS`; Task 2's factor key.
- Produces: `STUDENT_REGISTRY_VERSION = "0.1.0-proposed-oq-se-01"`, `STUDENT_REGISTRY_STATUS = "proposed"`, `STUDENT_SCORING_MODE = "student-event-1"`, `STUDENT_SCORING_MODE_VERSION = "1.0.0"`, `STUDENT_STAGE_B_FORMULA_VERSION = "1.0.0"`, `STUDENT_SCORING_MODES: frozenset[str]`, `APPROVED_STUDENT_SCORING_KEYS`, `STUDENT_FACTORS`, `STUDENT_EVENT_MODEL: ScoringModel`, `STUDENT_REGISTRY: FactorRegistry`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_student_factor_registry.py
from __future__ import annotations

import pytest
from smartmatch_domain.factor_registry import (
    FactorKind,
    RegistryNotApprovedError,
    assert_registry_approved,
    implemented_scoring_keys,
    normalize_weights,
    registry_for_version,
)
from smartmatch_domain.student_recommender.registry import (
    APPROVED_STUDENT_SCORING_KEYS,
    STUDENT_EVENT_MODEL,
    STUDENT_FACTORS,
    STUDENT_REGISTRY,
    STUDENT_REGISTRY_VERSION,
)


def test_weights_sum_to_one() -> None:
    total = sum(normalize_weights(model=STUDENT_EVENT_MODEL, registry=STUDENT_REGISTRY).values())
    assert abs(total - 1.0) < 1e-9


def test_implemented_scoring_keys_are_exactly_the_approved_set() -> None:
    assert implemented_scoring_keys(registry=STUDENT_REGISTRY) == APPROVED_STUDENT_SCORING_KEYS
    assert APPROVED_STUDENT_SCORING_KEYS == frozenset({"student_interest_overlap"})


def test_eligibility_factor_carries_no_stage_b_weight() -> None:
    spec = STUDENT_REGISTRY.spec_by_key["student_modality_eligibility"]
    assert spec.kind is FactorKind.ELIGIBILITY
    assert spec.active_weight == 0.0
    assert "student_modality_eligibility" not in STUDENT_EVENT_MODEL.scoring_keys


def test_unbuilt_factors_touch_neither_numerator_nor_denominator() -> None:
    for key in ("student_availability_fit", "student_program_affinity"):
        spec = STUDENT_REGISTRY.spec_by_key[key]
        assert spec.implemented is False
        assert spec.proposed_weight == 0.0
        assert key not in normalize_weights(model=STUDENT_EVENT_MODEL, registry=STUDENT_REGISTRY)


def test_the_gate_is_shut() -> None:
    assert STUDENT_REGISTRY.status == "proposed"
    with pytest.raises(RegistryNotApprovedError):
        assert_registry_approved(registry=STUDENT_REGISTRY)


def test_registry_is_findable_by_version() -> None:
    assert registry_for_version(STUDENT_REGISTRY_VERSION) is STUDENT_REGISTRY
    assert len(STUDENT_FACTORS) == 4
```

```python
# tests/unit/test_scoring_registry_isolation.py
from __future__ import annotations

import pytest
from smartmatch_domain import factor_registry
from smartmatch_domain.factor_registry import (
    APPROVED_SCORING_KEYS,
    CBA_PHYSICAL_MODEL,
    CBA_REGISTRY,
    CBA_VIRTUAL_MODEL,
    PROHIBITED_INPUTS,
    resolve_scoring_model,
)
from smartmatch_domain.factors.proximity import UnknownScoringModeError
from smartmatch_domain.student_recommender import registry as student_registry
from smartmatch_domain.student_recommender.registry import (
    APPROVED_STUDENT_SCORING_KEYS,
    STUDENT_REGISTRY,
    STUDENT_SCORING_MODE,
)


def test_key_sets_are_disjoint() -> None:
    assert not (APPROVED_SCORING_KEYS & APPROVED_STUDENT_SCORING_KEYS)
    for model in (CBA_PHYSICAL_MODEL, CBA_VIRTUAL_MODEL):
        assert not (set(model.scoring_keys) & APPROVED_STUDENT_SCORING_KEYS)


def test_student_mode_is_unknown_to_the_cba_registry_and_vice_versa() -> None:
    with pytest.raises(UnknownScoringModeError):
        resolve_scoring_model(STUDENT_SCORING_MODE, registry=CBA_REGISTRY)
    with pytest.raises(UnknownScoringModeError):
        resolve_scoring_model("cba-physical-1", registry=STUDENT_REGISTRY)


def test_prohibited_inputs_is_one_shared_object() -> None:
    assert student_registry.PROHIBITED_INPUTS is factor_registry.PROHIBITED_INPUTS
    assert "unrelated_student_feedback" in PROHIBITED_INPUTS
    assert "llm_generated_assumption" in PROHIBITED_INPUTS
```

```python
# tests/unit/test_student_scoring_inputs_wiring.py
"""OQ-CBA-053 as an executable control: no student scoring path can reach outcome data."""
from __future__ import annotations

import subprocess
import sys

import pytest

_FORBIDDEN = ("student_speaker_feedback", "attendance", "event_registration", "feedback")
_MODULES = (
    "smartmatch_domain.factors.student_interest_overlap",
    "smartmatch_domain.student_recommender.registry",
    "smartmatch_domain.student_recommender.eligibility",
    "smartmatch_domain.student_recommender.ranker",
    "smartmatch_domain.student_recommender.policy",
    "smartmatch_domain.student_recommender.recommend",
)


@pytest.mark.parametrize("module", _MODULES)
def test_student_module_imports_no_outcome_source(module: str) -> None:
    code = (
        "import importlib, sys\n"
        f"importlib.import_module({module!r})\n"
        "print('\\n'.join(sorted(sys.modules)))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    if result.returncode != 0 and "No module named" in result.stderr:
        pytest.skip(f"{module} not built yet")
    assert result.returncode == 0, result.stderr
    loaded = set(result.stdout.split())
    offenders = {m for m in loaded if any(m.endswith(f".{f}") or f".{f}." in m for f in _FORBIDDEN)}
    assert not offenders, f"{module} reaches outcome data: {sorted(offenders)}"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_student_factor_registry.py tests/unit/test_scoring_registry_isolation.py -q`
Expected: FAIL with `ModuleNotFoundError: smartmatch_domain.student_recommender`

- [ ] **Step 3: Implement the registry**

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/__init__.py
"""Student→event recommender (ADR-0018). Three stages behind fixed interfaces."""
```

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/registry.py
"""The student rulebook. Its own FactorRegistry; the CBA mechanism, not a copy of it."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from smartmatch_domain.factor_registry import (
    PROHIBITED_INPUTS,
    FactorKind,
    FactorRegistry,
    FactorSpec,
    ScoringModel,
    register_registry,
)
from smartmatch_domain.factors.student_interest_overlap import STUDENT_INTEREST_OVERLAP_FACTOR_KEY

__all__ = [
    "APPROVED_STUDENT_SCORING_KEYS",
    "PROHIBITED_INPUTS",
    "STUDENT_EVENT_MODEL",
    "STUDENT_FACTORS",
    "STUDENT_MODALITY_ELIGIBILITY_FACTOR_KEY",
    "STUDENT_REGISTRY",
    "STUDENT_REGISTRY_STATUS",
    "STUDENT_REGISTRY_VERSION",
    "STUDENT_SCORING_MODE",
    "STUDENT_SCORING_MODES",
    "STUDENT_SCORING_MODE_VERSION",
    "STUDENT_STAGE_B_FORMULA_VERSION",
]

STUDENT_REGISTRY_VERSION: Final[str] = "0.1.0-proposed-oq-se-01"
#: The gate. Flipped to "approved" only by an OQ-SE-01 artifact, with approver and date.
STUDENT_REGISTRY_STATUS: Final[str] = "proposed"
STUDENT_REGISTRY_APPROVER: Final[str | None] = None
STUDENT_REGISTRY_APPROVED_ON: Final[str | None] = None
STUDENT_SCORING_MODE: Final[str] = "student-event-1"
STUDENT_SCORING_MODE_VERSION: Final[str] = "1.0.0"
STUDENT_STAGE_B_FORMULA_VERSION: Final[str] = "1.0.0"
STUDENT_SCORING_MODES: Final[frozenset[str]] = frozenset({STUDENT_SCORING_MODE})
STUDENT_MODALITY_ELIGIBILITY_FACTOR_KEY: Final[str] = "student_modality_eligibility"

APPROVED_STUDENT_SCORING_KEYS: Final[frozenset[str]] = frozenset({STUDENT_INTEREST_OVERLAP_FACTOR_KEY})

STUDENT_FACTORS: Final[tuple[FactorSpec, ...]] = (
    FactorSpec(
        key=STUDENT_INTEREST_OVERLAP_FACTOR_KEY,
        display_label="Interest overlap",
        kind=FactorKind.SUITABILITY,
        proposed_weight=1.00,
        implemented=True,
        rationale=(
            "Jaccard between declared interests and mapped event tags at one vocabulary "
            "version; symmetric and gaming-resistant (W2 §4)."
        ),
    ),
    FactorSpec(
        key=STUDENT_MODALITY_ELIGIBILITY_FACTOR_KEY,
        display_label="Modality",
        kind=FactorKind.ELIGIBILITY,
        proposed_weight=0.0,
        implemented=True,
        rationale=(
            "Stage A filter: in_person excludes virtual events, virtual the converse, "
            "no_preference excludes nothing; excluded events are counted, never dropped."
        ),
    ),
    FactorSpec(
        key="student_availability_fit",
        display_label="Availability",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.0,
        implemented=False,
        rationale="OQ-SC-02: no availability datum may be stored and no event field compares to one.",
    ),
    FactorSpec(
        key="student_program_affinity",
        display_label="Program affinity",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.0,
        implemented=False,
        rationale="OQ-SC-02, and event_manual_detail.audience is unvalidated free text; both sides missing.",
    ),
)

STUDENT_EVENT_MODEL: Final[ScoringModel] = ScoringModel(
    registry_version=STUDENT_REGISTRY_VERSION,
    scoring_mode=STUDENT_SCORING_MODE,
    scoring_mode_version=STUDENT_SCORING_MODE_VERSION,
    scoring_keys=(STUDENT_INTEREST_OVERLAP_FACTOR_KEY,),
    is_current=True,
    mode_vocabulary=STUDENT_SCORING_MODES,
)

STUDENT_REGISTRY: Final[FactorRegistry] = FactorRegistry(
    version=STUDENT_REGISTRY_VERSION,
    status=STUDENT_REGISTRY_STATUS,
    approver=STUDENT_REGISTRY_APPROVER,
    approved_on=STUDENT_REGISTRY_APPROVED_ON,
    factors=STUDENT_FACTORS,
    approved_scoring_keys=APPROVED_STUDENT_SCORING_KEYS,
    scoring_modes=MappingProxyType({STUDENT_SCORING_MODE: STUDENT_EVENT_MODEL}),
)

register_registry(STUDENT_REGISTRY)
```

- [ ] **Step 4: Run the three tests**

Run: `.venv/bin/python -m pytest tests/unit/test_student_factor_registry.py tests/unit/test_scoring_registry_isolation.py tests/unit/test_student_scoring_inputs_wiring.py -q`
Expected: registry and isolation PASS; wiring PASSes for the two built modules and SKIPs the four not yet built.

- [ ] **Step 5: Commit**

```bash
git add python/smartmatch_domain/smartmatch_domain/student_recommender tests/unit/test_student_factor_registry.py tests/unit/test_scoring_registry_isolation.py tests/unit/test_student_scoring_inputs_wiring.py
git commit -m "feat: STUDENT_REGISTRY 0.1.0 shipped proposed and failing closed (ADR-0018 D2, W2b)"
```

---

### Task 4: Stage A — run, candidate, eligibility filter, and the feed constants

**Files:**
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/student_feed.py`
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/run.py`
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/eligibility.py`
- Test: `tests/unit/test_student_eligibility.py`, `tests/unit/test_student_feed_window.py`

**Interfaces:**
- Consumes: Task 2's `StudentInterestEvidence`, `EventTagEvidence`.
- Produces: constants above; `feed_window_for(now)` (contracts §1.1, hour-anchored); `StudentRankingRun`, `StudentEventCandidate` (contracts §2); `ELIGIBILITY_REASONS`, `EligibilityResult`, `EligibilityFilter` (Protocol), `DefaultEligibilityFilter` with `version = "eligibility-1.0.0"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_student_eligibility.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION
from smartmatch_domain.factors.student_interest_overlap import (
    EventTagEvidence,
    EventTagState,
    StudentInterestEvidence,
    StudentInterestState,
)
from smartmatch_domain.student_recommender.eligibility import (
    ELIGIBILITY_REASONS,
    DefaultEligibilityFilter,
)
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
WINDOW = (T0, T0 + timedelta(days=7))
TAGS = EventTagEvidence(EventTagState.TAGGED, frozenset({"finance"}), 0, VOCABULARY_VERSION)


def _run(modality: str = "no_preference", exclude: frozenset[str] = frozenset()) -> StudentRankingRun:
    return StudentRankingRun(
        unit_id="unit-1",
        subject_id="stu-1",
        interests=StudentInterestEvidence(StudentInterestState.DECLARED, frozenset({"finance"}), VOCABULARY_VERSION),
        modality_preference=modality,
        feed_window=WINDOW,
        exclude_event_ids=exclude,
        profile_version=1,
    )


def _event(event_id: str, **overrides) -> StudentEventCandidate:
    base = dict(
        event_id=event_id,
        is_virtual=False,
        starts_at=T0 + timedelta(days=1),
        time_precision="exact",
        publication_status="published",
        already_registered=False,
        tags=TAGS,
    )
    base.update(overrides)
    return StudentEventCandidate(**base)


def test_each_reason_is_produced_exactly_once_and_counts_reconcile() -> None:
    catalog = (
        _event("ok"),
        _event("unpub", publication_status="unpublished"),
        _event("late", starts_at=T0 + timedelta(days=9)),
        _event("undated", starts_at=None, time_precision="unresolved"),
        _event("virtual", is_virtual=True),
        _event("mine", already_registered=True),
        _event("skipped"),
    )
    result = DefaultEligibilityFilter().apply(_run("in_person", frozenset({"skipped"})), catalog)
    assert [c.event_id for c in result.eligible] == ["ok"]
    assert result.excluded == {
        "not_published": 1, "outside_window": 1, "unresolved_date": 1,
        "modality_mismatch": 1, "already_registered": 1, "session_excluded": 1,
    }
    assert set(result.excluded) == ELIGIBILITY_REASONS
    assert sum(result.excluded.values()) == len(catalog) - len(result.eligible)


def test_no_preference_excludes_nothing_on_modality() -> None:
    result = DefaultEligibilityFilter().apply(_run(), (_event("v", is_virtual=True), _event("p")))
    assert result.excluded["modality_mismatch"] == 0
    assert len(result.eligible) == 2


def test_virtual_preference_excludes_in_person() -> None:
    result = DefaultEligibilityFilter().apply(_run("virtual"), (_event("v", is_virtual=True), _event("p")))
    assert [c.event_id for c in result.eligible] == ["v"]


def test_window_is_closed_open() -> None:
    start = _event("at-start", starts_at=WINDOW[0])
    end = _event("at-end", starts_at=WINDOW[1])
    result = DefaultEligibilityFilter().apply(_run(), (start, end))
    assert [c.event_id for c in result.eligible] == ["at-start"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_student_eligibility.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement constants, run, and the filter**

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/student_feed.py
"""Feed bounds. Domain constants, never router literals (ADR-0018 D7)."""

from datetime import UTC, datetime, timedelta
from typing import Final

STUDENT_FEED_WINDOW_DAYS: Final[int] = 7
STUDENT_FEED_MAX_ITEMS: Final[int] = 5
STUDENT_FEED_WILDCARD_SLOTS: Final[int] = 1
STUDENT_FEED_MAX_PER_PRIMARY_TAG: Final[int] = 3
STUDENT_FEED_POLICY_VERSION: Final[str] = "feed-1.0.0"
STUDENT_FEED_MAX_SESSION_EXCLUSIONS: Final[int] = 50
STUDENT_FEED_WINDOW_ANCHOR: Final[str] = "hour"   # documented in contracts §1.1


def feed_window_for(now: datetime) -> tuple[datetime, datetime]:
    """Anchor the window to the top of the UTC hour so refreshes within an hour share an inputs_hash."""
    if now.tzinfo is None:
        raise ValueError("feed_window_for: now must be tz-aware")
    start = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=STUDENT_FEED_WINDOW_DAYS)
```

```python
# tests/unit/test_student_feed_window.py
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.student_recommender.student_feed import STUDENT_FEED_WINDOW_DAYS, feed_window_for


def test_requests_in_the_same_hour_share_a_window() -> None:
    a = feed_window_for(datetime(2026, 10, 5, 14, 3, 7, 123456, tzinfo=UTC))
    b = feed_window_for(datetime(2026, 10, 5, 14, 59, 59, 999999, tzinfo=UTC))
    assert a == b == (datetime(2026, 10, 5, 14, tzinfo=UTC), datetime(2026, 10, 5, 14, tzinfo=UTC) + timedelta(days=STUDENT_FEED_WINDOW_DAYS))


def test_crossing_the_hour_moves_the_window() -> None:
    assert feed_window_for(datetime(2026, 10, 5, 14, 59, tzinfo=UTC)) != feed_window_for(datetime(2026, 10, 5, 15, 0, tzinfo=UTC))


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError):
        feed_window_for(datetime(2026, 10, 5, 14))
```

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/run.py
"""What a run may see. One StudentRankingRun per request; never per candidate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from smartmatch_domain.factors.student_interest_overlap import EventTagEvidence, StudentInterestEvidence

ModalityPreference = Literal["in_person", "virtual", "no_preference"]
TimePrecision = Literal["exact", "date_only", "unresolved"]


@dataclass(frozen=True, slots=True)
class StudentRankingRun:
    unit_id: str
    subject_id: str
    interests: StudentInterestEvidence
    modality_preference: ModalityPreference
    feed_window: tuple[datetime, datetime]
    exclude_event_ids: frozenset[str]
    profile_version: int

    def __post_init__(self) -> None:
        start, end = self.feed_window
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("feed_window: both bounds must be tz-aware")
        if not start < end:
            raise ValueError("feed_window: start must precede end")
        if self.profile_version < 1:
            raise ValueError("profile_version: must be >= 1")


@dataclass(frozen=True, slots=True)
class StudentEventCandidate:
    event_id: str
    is_virtual: bool
    starts_at: datetime | None
    time_precision: TimePrecision
    publication_status: str
    already_registered: bool
    tags: EventTagEvidence

    def __post_init__(self) -> None:
        if self.time_precision == "unresolved" and self.starts_at is not None:
            raise ValueError("starts_at: an unresolved event carries no instant (ADR-0010)")
```

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/eligibility.py
"""Stage A. Hard constraints; excluded events are counted, never silently dropped."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

ELIGIBILITY_REASONS: Final[frozenset[str]] = frozenset(
    {
        "not_published",
        "outside_window",
        "unresolved_date",
        "modality_mismatch",
        "already_registered",
        "session_excluded",
    }
)

#: Evaluation order. The first failing reason is the one counted, so one event
#: is counted exactly once and the counts reconcile to the catalog size.
_ORDER: Final[tuple[str, ...]] = (
    "not_published",
    "unresolved_date",
    "outside_window",
    "modality_mismatch",
    "already_registered",
    "session_excluded",
)


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    eligible: tuple[StudentEventCandidate, ...]
    excluded: Mapping[str, int]


class EligibilityFilter(Protocol):
    version: str

    def apply(
        self, run: StudentRankingRun, candidates: Sequence[StudentEventCandidate]
    ) -> EligibilityResult: ...


def _failing_reason(run: StudentRankingRun, c: StudentEventCandidate) -> str | None:
    start, end = run.feed_window
    checks = {
        "not_published": c.publication_status != "published",
        "unresolved_date": c.time_precision == "unresolved" or c.starts_at is None,
        "outside_window": c.starts_at is not None and not (start <= c.starts_at < end),
        "modality_mismatch": (
            (run.modality_preference == "in_person" and c.is_virtual)
            or (run.modality_preference == "virtual" and not c.is_virtual)
        ),
        "already_registered": c.already_registered,
        "session_excluded": c.event_id in run.exclude_event_ids,
    }
    for reason in _ORDER:
        if checks[reason]:
            return reason
    return None


class DefaultEligibilityFilter:
    version: str = "eligibility-1.0.0"

    def apply(
        self, run: StudentRankingRun, candidates: Sequence[StudentEventCandidate]
    ) -> EligibilityResult:
        counts = dict.fromkeys(_ORDER, 0)
        eligible: list[StudentEventCandidate] = []
        for candidate in candidates:
            reason = _failing_reason(run, candidate)
            if reason is None:
                eligible.append(candidate)
            else:
                counts[reason] += 1
        return EligibilityResult(eligible=tuple(eligible), excluded=MappingProxyType(counts))
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest tests/unit/test_student_eligibility.py -q`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add python/smartmatch_domain/smartmatch_domain/student_recommender tests/unit/test_student_eligibility.py
git commit -m "feat: student recommender Stage A eligibility filter and feed constants (ADR-0018 D1, D7)"
```

---

### Task 5: Stage B — `StudentRanker` protocol, `ContentRanker`, and `recommend()` composition

**Files:**
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/ranker.py`
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/fingerprint.py`
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/recommend.py`
- Modify: `python/smartmatch_domain/smartmatch_domain/match_run.py` — export `canonical_digest = _digest` and add it to `__all__`
- Test: `tests/unit/test_student_scoring.py`, `tests/unit/test_student_recommend.py`

**Interfaces:**
- Consumes: `StageBScore`, `_ranked` (import as `from smartmatch_domain.scoring import _ranked` — it is the shared tie-break; if the team prefers, promote it to `ranked_by_policy` in `scoring.py` with `_ranked = ranked_by_policy` kept), `normalize_weights`, `assert_registry_approved`, `assert_scoring_ready`, Task 3 registry, Task 4 types.
- Produces: `StudentRanker` (Protocol with `ranker_id`, `registry`, `scoring_mode`, `formula_version`, `model_artifact_hash`, `rank(run, candidates)`), `ContentRanker`, `student_inputs_hash(...) -> str`, `recommend(run, catalog, *, eligibility, ranker, policy) -> RecommendationOutcome`. Task 6 supplies `FeedPolicy`; until then `recommend` is tested with a `PassThroughPolicy` defined in the test.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_student_scoring.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION as V
from smartmatch_domain.factor_registry import RegistryNotReadyError
from smartmatch_domain.factors.student_interest_overlap import (
    EventTagEvidence,
    EventTagState,
    StudentInterestEvidence,
    StudentInterestState,
)
from smartmatch_domain.student_recommender.ranker import ContentRanker
from smartmatch_domain.student_recommender.registry import (
    STUDENT_REGISTRY_VERSION,
    STUDENT_SCORING_MODE,
    STUDENT_STAGE_B_FORMULA_VERSION,
)
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def _run(*terms: str) -> StudentRankingRun:
    return StudentRankingRun(
        "unit-1", "stu-1",
        StudentInterestEvidence(StudentInterestState.DECLARED, frozenset(terms), V),
        "no_preference", (T0, T0 + timedelta(days=7)), frozenset(), 1,
    )


def _event(event_id: str, *tags: str, state: EventTagState = EventTagState.TAGGED) -> StudentEventCandidate:
    return StudentEventCandidate(
        event_id, False, T0 + timedelta(days=1), "exact", "published", False,
        EventTagEvidence(state, frozenset(tags), 0, V),
    )


def test_scores_carry_the_student_pins_and_event_id_as_subject() -> None:
    (score,) = ContentRanker().rank(_run("finance"), (_event("e1", "finance"),))
    assert score.subject_id == "e1"
    assert score.value == 1.0
    assert score.registry_version == STUDENT_REGISTRY_VERSION
    assert score.scoring_mode == STUDENT_SCORING_MODE
    assert score.formula_version == STUDENT_STAGE_B_FORMULA_VERSION
    assert dict(score.applied_weights) == {"student_interest_overlap": 1.0}
    assert score.unknown_factor_keys == ()


def test_unknown_dominates_and_sorts_last() -> None:
    scores = ContentRanker().rank(
        _run("finance"),
        (_event("untagged", state=EventTagState.NO_TAG_RECORDS), _event("zero", "hackathon"), _event("hit", "finance")),
    )
    assert [s.subject_id for s in scores] == ["hit", "zero", "untagged"]
    assert scores[-1].value is None
    assert scores[-1].unknown_factor_keys == ("student_interest_overlap",)
    assert scores[1].value == 0.0


def test_ties_break_by_event_id_ascending() -> None:
    scores = ContentRanker().rank(_run("finance"), (_event("b", "finance"), _event("a", "finance")))
    assert [s.subject_id for s in scores] == ["a", "b"]


def test_identical_inputs_give_identical_order() -> None:
    catalog = tuple(_event(f"e{i}", "finance" if i % 2 else "hackathon") for i in range(10))
    first = ContentRanker().rank(_run("finance"), catalog)
    second = ContentRanker().rank(_run("finance"), tuple(reversed(catalog)))
    assert [s.subject_id for s in first] == [s.subject_id for s in second]


def test_duplicate_event_ids_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        ContentRanker().rank(_run("finance"), (_event("e", "finance"), _event("e", "finance")))


def test_deflation_guard_fires_when_scored_keys_diverge(monkeypatch: pytest.MonkeyPatch) -> None:
    from smartmatch_domain.student_recommender import ranker as module

    monkeypatch.setattr(module, "_factor_scores", lambda run, c: ())
    with pytest.raises(RegistryNotReadyError, match="deflate"):
        ContentRanker().rank(_run("finance"), (_event("e1", "finance"),))
```

```python
# tests/unit/test_student_recommend.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION as V
from smartmatch_domain.factor_registry import RegistryNotApprovedError
from smartmatch_domain.factors.student_interest_overlap import (
    EventTagEvidence,
    EventTagState,
    StudentInterestEvidence,
    StudentInterestState,
)
from smartmatch_domain.student_recommender import registry as registry_module
from smartmatch_domain.student_recommender.eligibility import DefaultEligibilityFilter
from smartmatch_domain.student_recommender.ranker import ContentRanker
from smartmatch_domain.student_recommender.recommend import recommend, student_inputs_hash
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


class PassThroughPolicy:
    policy_version = "test-passthrough"

    def select(self, run, ranked, inputs_hash, *, primary_tag_by_event={}):
        from smartmatch_domain.student_recommender.policy import StudentFeed

        return StudentFeed(
            items=ranked, wildcard=None, wildcard_pool_size=0, wildcard_seed="",
            withheld_unscorable=sum(1 for s in ranked if s.value is None),
            withheld_untagged=0, truncated=False, policy_version=self.policy_version,
        )


def _run(exclude: frozenset[str] = frozenset()) -> StudentRankingRun:
    return StudentRankingRun(
        "unit-1", "stu-1",
        StudentInterestEvidence(StudentInterestState.DECLARED, frozenset({"finance"}), V),
        "no_preference", (T0, T0 + timedelta(days=7)), exclude, 1,
    )


def _event(event_id: str, *tags: str) -> StudentEventCandidate:
    return StudentEventCandidate(
        event_id, False, T0 + timedelta(days=1), "exact", "published", False,
        EventTagEvidence(EventTagState.TAGGED, frozenset(tags), 0, V),
    )


RUN = _run()


def _catalog(*, tags: Mapping[str, set[str]]) -> tuple[StudentEventCandidate, ...]:
    """One candidate per entry, insertion order preserved; the value is the event's mapped terms."""
    return tuple(_event(event_id, *sorted(terms)) for event_id, terms in tags.items())


def _approved_ranker() -> ContentRanker:
    """A ranker over an approved copy of the registry; the shipped constant stays 'proposed'."""
    return ContentRanker(
        registry=replace(registry_module.STUDENT_REGISTRY, status="approved",
                         approver="test", approved_on="2026-10-05"),
    )


@pytest.fixture
def approved_registry(monkeypatch: pytest.MonkeyPatch):
    """Flip the gate for a test only; the shipped constant stays 'proposed'."""
    from dataclasses import replace

    approved = replace(registry_module.STUDENT_REGISTRY, status="approved", approver="test", approved_on="2026-10-05")
    monkeypatch.setattr(registry_module, "STUDENT_REGISTRY", approved)
    return approved


def test_proposed_registry_refuses_before_reading_evidence() -> None:
    with pytest.raises(RegistryNotApprovedError):
        recommend(_run(), (_event("e1", "finance"),), eligibility=DefaultEligibilityFilter(),
                  ranker=ContentRanker(), policy=PassThroughPolicy())


def test_same_inputs_same_hash_and_order(approved_registry) -> None:
    ranker = ContentRanker(registry=approved_registry)
    catalog = (_event("b", "finance"), _event("a", "finance"), _event("c", "hackathon"))
    one = recommend(_run(), catalog, eligibility=DefaultEligibilityFilter(), ranker=ranker, policy=PassThroughPolicy())
    two = recommend(_run(), tuple(reversed(catalog)), eligibility=DefaultEligibilityFilter(), ranker=ranker, policy=PassThroughPolicy())
    assert one.inputs_hash == two.inputs_hash
    assert one.inputs_hash.startswith("sha256:")
    assert [s.subject_id for s in one.feed.items] == [s.subject_id for s in two.feed.items] == ["a", "b", "c"]


def test_session_exclusions_change_the_hash_and_are_counted(approved_registry) -> None:
    ranker = ContentRanker(registry=approved_registry)
    catalog = (_event("a", "finance"), _event("b", "finance"))
    plain = recommend(_run(), catalog, eligibility=DefaultEligibilityFilter(), ranker=ranker, policy=PassThroughPolicy())
    skipped = recommend(_run(frozenset({"a"})), catalog, eligibility=DefaultEligibilityFilter(), ranker=ranker, policy=PassThroughPolicy())
    assert plain.inputs_hash != skipped.inputs_hash
    assert skipped.eligibility.excluded["session_excluded"] == 1
    assert [s.subject_id for s in skipped.feed.items] == ["b"]


def test_inputs_hash_covers_the_documented_tuple() -> None:
    h = student_inputs_hash(
        unit_id="u", subject_id="s", profile_version=1, interest_terms=frozenset({"b", "a"}),
        modality_preference="no_preference", vocabulary_version=V,
        window=(T0, T0 + timedelta(days=7)), eligible=(_event("y", "finance"), _event("x", "finance")),
        exclude_event_ids=frozenset(), registry_version="r", registry_hash="sha256:0",
        scoring_mode="m", scoring_mode_version="1", formula_version="f",
        model_artifact_hash=None, policy_version="p",
    )
    same_different_order = student_inputs_hash(
        unit_id="u", subject_id="s", profile_version=1, interest_terms=frozenset({"a", "b"}),
        modality_preference="no_preference", vocabulary_version=V,
        window=(T0, T0 + timedelta(days=7)), eligible=(_event("x", "finance"), _event("y", "finance")),
        exclude_event_ids=frozenset(), registry_version="r", registry_hash="sha256:0",
        scoring_mode="m", scoring_mode_version="1", formula_version="f",
        model_artifact_hash=None, policy_version="p",
    )
    assert h == same_different_order


def test_changing_an_eligible_events_tags_changes_the_hash() -> None:
    catalog = _catalog(tags={"e1": {"finance"}, "e2": {"hackathon"}})
    edited = _catalog(tags={"e1": {"finance", "hackathon"}, "e2": {"hackathon"}})
    a = recommend(RUN, catalog, eligibility=DefaultEligibilityFilter(), ranker=_approved_ranker(), policy=PassThroughPolicy())
    b = recommend(RUN, edited, eligibility=DefaultEligibilityFilter(), ranker=_approved_ranker(), policy=PassThroughPolicy())
    assert a.inputs_hash != b.inputs_hash


def test_candidate_evidence_covers_every_candidate_field() -> None:
    from dataclasses import fields

    from smartmatch_domain.student_recommender.recommend import candidate_evidence
    from smartmatch_domain.student_recommender.run import StudentEventCandidate
    names = {f.name for f in fields(StudentEventCandidate)}
    assert names == {"event_id", "is_virtual", "starts_at", "time_precision", "publication_status", "already_registered", "tags"}
    assert len(candidate_evidence(_catalog(tags={"e1": {"finance"}})[0])) == 10
```

The Stage-C pipeline test (`DefaultFeedPolicy` through `recommend`) belongs to
Task 6 and is written there; this task's block never imports `DefaultFeedPolicy`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_student_scoring.py tests/unit/test_student_recommend.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Export the digest and implement the ranker, fingerprint, and composition**

`match_run.py`: after `_digest`, add `canonical_digest = _digest` and `"canonical_digest"` to `__all__`.

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/fingerprint.py
"""The run's inputs hash: same format and digest as match_run.inputs_fingerprint."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from smartmatch_domain.match_run import canonical_digest
from smartmatch_domain.student_recommender.run import StudentEventCandidate


def candidate_evidence(c: StudentEventCandidate) -> tuple:
    """Every candidate field a ranker or policy may read; folded into inputs_hash (contracts §1.4)."""
    return (
        c.event_id, c.is_virtual,
        None if c.starts_at is None else c.starts_at.isoformat(),
        c.time_precision, c.publication_status, c.already_registered,
        c.tags.state.value, sorted(c.tags.mapped_terms),
        c.tags.quarantined_count, c.tags.vocabulary_version,
    )


def student_inputs_hash(
    *,
    unit_id: str,
    subject_id: str,
    profile_version: int,
    interest_terms: Iterable[str],
    modality_preference: str,
    vocabulary_version: str,
    window: tuple[datetime, datetime],
    eligible: Iterable[StudentEventCandidate],
    exclude_event_ids: Iterable[str],
    registry_version: str,
    registry_hash: str,
    scoring_mode: str,
    scoring_mode_version: str,
    formula_version: str,
    model_artifact_hash: str | None,
    policy_version: str,
) -> str:
    payload = {
        "unit_id": unit_id,
        "subject_id": subject_id,
        "profile_version": profile_version,
        "interest_terms": sorted(interest_terms),
        "modality_preference": modality_preference,
        "vocabulary_version": vocabulary_version,
        "window": [window[0].isoformat(), window[1].isoformat()],
        "eligible_evidence": sorted(candidate_evidence(c) for c in eligible),
        "exclude_event_ids": sorted(exclude_event_ids),
        "registry_version": registry_version,
        "registry_hash": registry_hash,
        "scoring_mode": scoring_mode,
        "scoring_mode_version": scoring_mode_version,
        "formula_version": formula_version,
        "model_artifact_hash": model_artifact_hash,
        "policy_version": policy_version,
    }
    return canonical_digest(payload)
```

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/ranker.py
"""Stage B. V1: content-based, one factor, the CBA composition invariants reused."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from smartmatch_domain.factor_registry import (
    FactorKind,
    FactorRegistry,
    RegistryNotReadyError,
    assert_scoring_ready,
    normalize_weights,
    resolve_scoring_model,
)
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.factors.student_interest_overlap import score_student_interest_overlap
from smartmatch_domain.scoring import StageBScore, _ranked
from smartmatch_domain.student_recommender import registry as registry_module
from smartmatch_domain.student_recommender.registry import (
    STUDENT_SCORING_MODE,
    STUDENT_STAGE_B_FORMULA_VERSION,
)
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

RankerId = Literal["content-1", "ltr-1"]


class StudentRanker(Protocol):
    ranker_id: RankerId
    registry: FactorRegistry
    scoring_mode: str
    formula_version: str
    model_artifact_hash: str | None

    def rank(
        self, run: StudentRankingRun, candidates: Sequence[StudentEventCandidate]
    ) -> tuple[StageBScore, ...]: ...


def _factor_scores(run: StudentRankingRun, candidate: StudentEventCandidate) -> tuple[FactorScore, ...]:
    """Every scoring factor the student model admits, in registry order."""
    return (score_student_interest_overlap(run.interests, candidate.tags),)


def _compose(
    subject_id: str,
    factor_scores: tuple[FactorScore, ...],
    applied_weights: Mapping[str, float],
    *,
    registry: FactorRegistry,
    scoring_mode: str,
    scoring_mode_version: str,
    formula_version: str,
) -> StageBScore:
    scored = {s.factor_key for s in factor_scores}
    weighted = set(applied_weights)
    if scored != weighted:
        raise RegistryNotReadyError(
            "Stage B composite would silently deflate: factor_scores covers "
            f"{sorted(scored)} but applied_weights covers {sorted(weighted)}."
        )
    if abs(sum(applied_weights.values()) - 1.0) > 1e-9:
        raise ValueError("applied_weights: must sum to 1.0")
    unknown = tuple(s.factor_key for s in factor_scores if s.is_unknown)
    value: float | None
    if unknown:
        value = None
    else:
        kinds = registry.kind_by_key
        total = 0.0
        for s in factor_scores:
            assert s.value is not None
            contribution = s.value if kinds[s.factor_key] is FactorKind.SUITABILITY else 1.0 - s.value
            total += applied_weights[s.factor_key] * contribution
        value = round(total, 6)
    return StageBScore(
        subject_id=subject_id,
        value=value,
        factor_scores=factor_scores,
        applied_weights=applied_weights,
        unknown_factor_keys=unknown,
        registry_version=registry.version,
        formula_version=formula_version,
        scoring_mode=scoring_mode,
        scoring_mode_version=scoring_mode_version,
    )


@dataclass(frozen=True, slots=True)
class ContentRanker:
    """ADR-0018 D3. Jaccard over the closed vocabulary; deterministic; no provider."""

    ranker_id: RankerId = "content-1"
    registry: FactorRegistry = field(default_factory=lambda: registry_module.STUDENT_REGISTRY)
    scoring_mode: str = STUDENT_SCORING_MODE
    formula_version: str = STUDENT_STAGE_B_FORMULA_VERSION
    model_artifact_hash: str | None = None

    def rank(
        self, run: StudentRankingRun, candidates: Sequence[StudentEventCandidate]
    ) -> tuple[StageBScore, ...]:
        ids = [c.event_id for c in candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("event_id: duplicate candidate event_id in ContentRanker.rank")
        assert_scoring_ready(registry=self.registry)
        model = resolve_scoring_model(self.scoring_mode, registry=self.registry)
        weights = normalize_weights(model=model, registry=self.registry)
        assert model.scoring_mode_version is not None
        scores = tuple(
            _compose(
                c.event_id,
                _factor_scores(run, c),
                weights,
                registry=self.registry,
                scoring_mode=self.scoring_mode,
                scoring_mode_version=model.scoring_mode_version,
                formula_version=self.formula_version,
            )
            for c in candidates
        )
        return _ranked(scores)
```

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/recommend.py
"""The one composition every test targets: A → B → C, gate first."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from smartmatch_domain.factor_registry import assert_registry_approved
from smartmatch_domain.student_recommender.eligibility import EligibilityFilter, EligibilityResult
from smartmatch_domain.student_recommender.fingerprint import candidate_evidence, student_inputs_hash
from smartmatch_domain.student_recommender.policy import FeedPolicy, StudentFeed, primary_tag
from smartmatch_domain.student_recommender.ranker import StudentRanker
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

__all__ = ["RecommendationOutcome", "candidate_evidence", "recommend", "student_inputs_hash"]


@dataclass(frozen=True, slots=True)
class RecommendationOutcome:
    feed: StudentFeed
    eligibility: EligibilityResult
    inputs_hash: str


def recommend(
    run: StudentRankingRun,
    catalog: Sequence[StudentEventCandidate],
    *,
    eligibility: EligibilityFilter,
    ranker: StudentRanker,
    policy: FeedPolicy,
) -> RecommendationOutcome:
    assert_registry_approved(registry=ranker.registry)
    stage_a = eligibility.apply(run, catalog)
    ranked = ranker.rank(run, stage_a.eligible)
    model = ranker.registry.scoring_modes[ranker.scoring_mode]
    assert model.scoring_mode_version is not None
    inputs_hash = student_inputs_hash(
        unit_id=run.unit_id,
        subject_id=run.subject_id,
        profile_version=run.profile_version,
        interest_terms=run.interests.terms,
        modality_preference=run.modality_preference,
        vocabulary_version=run.interests.vocabulary_version,
        window=run.feed_window,
        eligible=stage_a.eligible,
        exclude_event_ids=run.exclude_event_ids,
        registry_version=ranker.registry.version,
        registry_hash=ranker.registry.registry_hash,
        scoring_mode=ranker.scoring_mode,
        scoring_mode_version=model.scoring_mode_version,
        formula_version=ranker.formula_version,
        model_artifact_hash=ranker.model_artifact_hash,
        policy_version=policy.policy_version,
    )
    primary_tag_by_event = {c.event_id: primary_tag(run.interests, c.tags) for c in stage_a.eligible}
    feed = policy.select(run, ranked, inputs_hash, primary_tag_by_event=primary_tag_by_event)
    return RecommendationOutcome(feed=feed, eligibility=stage_a, inputs_hash=inputs_hash)
```

`recommend.py` imports `policy.py`, which Task 6 creates. For this task create `policy.py` with the `StudentFeed` dataclass, the `FeedPolicy` Protocol from contracts §2, and `primary_tag` (no `DefaultFeedPolicy` yet); Task 6 adds the implementation.

```python
def primary_tag(interests: StudentInterestEvidence, tags: EventTagEvidence) -> str | None:
    if not interests.terms or tags.state.value != "tagged":
        return None
    matched = sorted(interests.terms & tags.mapped_terms)
    return matched[0] if matched else None
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/test_student_scoring.py tests/unit/test_student_recommend.py tests/unit/test_student_scoring_inputs_wiring.py -q`
Expected: all PASS; the wiring test now imports `ranker` and `recommend` and finds no outcome module.

- [ ] **Step 5: Commit**

```bash
git add python/smartmatch_domain/smartmatch_domain/match_run.py python/smartmatch_domain/smartmatch_domain/student_recommender tests/unit/test_student_scoring.py tests/unit/test_student_recommend.py
git commit -m "feat: ContentRanker, inputs hash, and recommend() composition (ADR-0018 D1, D3)"
```

---

### Task 6: Stage C — `DefaultFeedPolicy`: bound, diversity cap, declared wildcard

**Files:**
- Modify: `python/smartmatch_domain/smartmatch_domain/student_recommender/policy.py`
- Test: `tests/unit/test_student_feed_policy.py`

**Interfaces:**
- Consumes: Task 4 constants, `StageBScore`, Task 5's `RecommendationOutcome` unchanged.
- Produces: `DefaultFeedPolicy(policy_version=STUDENT_FEED_POLICY_VERSION)`, `primary_tag(score) -> str | None` (the alphabetically first matched interest, from `FactorScore.basis`-free evidence: policy reads `score.factor_scores[0]` value only for scorability; the primary tag comes from `primary_tag(run.interests, candidate.tags)` computed inside `recommend()` (Task 5); no router involvement). To keep Stage C pure, `select` gains a keyword argument `primary_tag_by_event: Mapping[str, str | None] = {}` — recorded in the contracts doc §2 as an amendment.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_student_feed_policy.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION as V
from smartmatch_domain.factors.student_interest_overlap import StudentInterestEvidence, StudentInterestState
from smartmatch_domain.scoring import StageBScore
from smartmatch_domain.student_recommender.policy import DefaultFeedPolicy
from smartmatch_domain.student_recommender.run import StudentRankingRun
from smartmatch_domain.student_recommender.student_feed import (
    STUDENT_FEED_MAX_ITEMS,
    STUDENT_FEED_MAX_PER_PRIMARY_TAG,
    STUDENT_FEED_POLICY_VERSION,
)

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
RUN = StudentRankingRun(
    "u", "s", StudentInterestEvidence(StudentInterestState.DECLARED, frozenset({"finance"}), V),
    "no_preference", (T0, T0 + timedelta(days=7)), frozenset(), 1,
)
HASH = "sha256:" + "ab" * 32


def _score(event_id: str, value: float | None) -> StageBScore:
    return StageBScore(
        subject_id=event_id, value=value, factor_scores=(), applied_weights={},
        unknown_factor_keys=("student_interest_overlap",) if value is None else (),
        registry_version="r", formula_version="f", scoring_mode="student-event-1", scoring_mode_version="1.0.0",
    )


def _ranked(*pairs: tuple[str, float | None]) -> tuple[StageBScore, ...]:
    return tuple(_score(e, v) for e, v in pairs)


def test_bound_and_truncation() -> None:
    ranked = _ranked(*[(f"e{i}", 1.0 - i / 100) for i in range(8)])
    feed = DefaultFeedPolicy().select(RUN, ranked, HASH)
    assert len(feed.items) == STUDENT_FEED_MAX_ITEMS
    assert feed.truncated is True
    assert feed.policy_version == STUDENT_FEED_POLICY_VERSION
    assert feed.wildcard is not None
    assert feed.wildcard.subject_id not in {s.subject_id for s in feed.items}
    assert feed.wildcard_pool_size == 3


def test_wildcard_is_null_when_no_scorable_event_is_left_outside() -> None:
    feed = DefaultFeedPolicy().select(RUN, _ranked(("a", 1.0), ("b", None)), HASH)
    assert [s.subject_id for s in feed.items] == ["a"]
    assert feed.wildcard is None
    assert feed.wildcard_pool_size == 0
    assert feed.withheld_unscorable == 1


def test_wildcard_is_never_unscorable_and_is_hash_deterministic() -> None:
    ranked = _ranked(*[(f"e{i}", 0.9 - i / 100) for i in range(6)], ("u1", None), ("u2", None))
    one = DefaultFeedPolicy().select(RUN, ranked, HASH)
    two = DefaultFeedPolicy().select(RUN, ranked, HASH)
    assert one.wildcard is not None and one.wildcard.value is not None
    assert one.wildcard.subject_id == two.wildcard.subject_id
    assert one.wildcard_seed == two.wildcard_seed
    assert one.withheld_unscorable == 2


def test_diversity_preference_defers_same_tag_items_but_still_fills_the_feed() -> None:
    ranked = _ranked(("f1", 0.9), ("f2", 0.8), ("f3", 0.7), ("f4", 0.6), ("h1", 0.5), ("f5", 0.4), ("u", None))
    tags = {"f1": "finance", "f2": "finance", "f3": "finance", "f4": "finance", "h1": "hackathon", "f5": "finance", "u": None}
    feed = DefaultFeedPolicy().select(RUN, ranked, HASH, primary_tag_by_event=tags)
    assert [s.subject_id for s in feed.items] == ["f1", "f2", "f3", "h1", "f4"]
    assert feed.wildcard is not None and feed.wildcard.subject_id == "f5"
    assert feed.wildcard_pool_size == 1
    assert "u" not in [s.subject_id for s in feed.items]
    assert feed.withheld_unscorable == 1


def test_diversity_preference_never_shortens_the_feed() -> None:
    ranked = _ranked(("f1", 0.9), ("f2", 0.8), ("f3", 0.7), ("f4", 0.6), ("f5", 0.5))
    tags = {k: "finance" for k in ("f1", "f2", "f3", "f4", "f5")}
    feed = DefaultFeedPolicy().select(RUN, ranked, HASH, primary_tag_by_event=tags)
    assert [s.subject_id for s in feed.items] == ["f1", "f2", "f3", "f4", "f5"]
    assert feed.wildcard is None and feed.truncated is False


def test_empty_ranked_gives_empty_feed() -> None:
    feed = DefaultFeedPolicy().select(RUN, (), HASH)
    assert feed.items == () and feed.wildcard is None and feed.truncated is False
```

Stage C is also exercised through the whole pipeline. Append this case to Task 5's
`tests/unit/test_student_recommend.py` — it is new in this task, and Step 4 below
re-runs that file:

```python
# tests/unit/test_student_recommend.py  (append; new in this task)
# Add to that file's imports:
#     from smartmatch_domain.student_recommender.policy import DefaultFeedPolicy
#     from smartmatch_domain.student_recommender.student_feed import (
#         STUDENT_FEED_MAX_ITEMS,
#         STUDENT_FEED_MAX_PER_PRIMARY_TAG,
#     )
# `replace`, `V`, `RUN`, `_catalog` and `_approved_ranker` already exist in the file
# from Task 5.


def test_diversity_preference_applies_through_recommend_without_caller_tags() -> None:
    catalog = _catalog(tags={f"f{i}": {"finance"} for i in range(1, 6)} | {"h1": {"hackathon"}})
    run = replace(RUN, interests=StudentInterestEvidence(StudentInterestState.DECLARED, frozenset({"finance", "hackathon"}), V))
    out = recommend(run, catalog, eligibility=DefaultEligibilityFilter(), ranker=_approved_ranker(), policy=DefaultFeedPolicy())
    ids = [s.subject_id for s in out.feed.items]
    # All six tie at Jaccard 1/2 and break by event id, so the finance run is f1..f5;
    # the soft preference defers f4 and f5 behind h1 and the feed still fills.
    assert ids[STUDENT_FEED_MAX_PER_PRIMARY_TAG] == "h1"
    assert len(ids) == STUDENT_FEED_MAX_ITEMS
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_student_feed_policy.py -q`
Expected: FAIL with `ImportError: cannot import name 'DefaultFeedPolicy'`

- [ ] **Step 3: Implement the policy**

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/policy.py
"""Stage C. A constrained re-rank, always on (ADR-0018 D7)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from smartmatch_domain.factors.student_interest_overlap import (
    EventTagEvidence,
    StudentInterestEvidence,
)
from smartmatch_domain.scoring import StageBScore
from smartmatch_domain.student_recommender.run import StudentRankingRun
from smartmatch_domain.student_recommender.student_feed import (
    STUDENT_FEED_MAX_ITEMS,
    STUDENT_FEED_MAX_PER_PRIMARY_TAG,
    STUDENT_FEED_POLICY_VERSION,
    STUDENT_FEED_WILDCARD_SLOTS,
)


@dataclass(frozen=True, slots=True)
class StudentFeed:
    items: tuple[StageBScore, ...]
    wildcard: StageBScore | None
    wildcard_pool_size: int
    wildcard_seed: str
    withheld_unscorable: int
    withheld_untagged: int
    truncated: bool
    policy_version: str


class FeedPolicy(Protocol):
    policy_version: str

    def select(
        self,
        run: StudentRankingRun,
        ranked: tuple[StageBScore, ...],
        inputs_hash: str,
        *,
        primary_tag_by_event: Mapping[str, str | None] = ...,
    ) -> StudentFeed: ...


def primary_tag(interests: StudentInterestEvidence, tags: EventTagEvidence) -> str | None:
    if not interests.terms or tags.state.value != "tagged":
        return None
    matched = sorted(interests.terms & tags.mapped_terms)
    return matched[0] if matched else None


def _apply_diversity_cap(
    scorable: list[StageBScore], primary_tag_by_event: Mapping[str, str | None], cap: int
) -> list[StageBScore]:
    """Soft preference (ADR-0018 D7): an item past the per-tag count is deferred behind every other scorable item, never dropped; the feed still fills."""
    taken: dict[str, int] = {}
    kept: list[StageBScore] = []
    deferred: list[StageBScore] = []
    for score in scorable:
        tag = primary_tag_by_event.get(score.subject_id)
        if tag is None or taken.get(tag, 0) < cap:
            kept.append(score)
            if tag is not None:
                taken[tag] = taken.get(tag, 0) + 1
        else:
            deferred.append(score)
    return kept + deferred


def _is_untagged(score: StageBScore) -> bool:
    return any("no vocabulary tags" in f.basis or "tags resolved" in f.basis for f in score.factor_scores if f.is_unknown)


@dataclass(frozen=True, slots=True)
class DefaultFeedPolicy:
    policy_version: str = STUDENT_FEED_POLICY_VERSION

    def select(
        self,
        run: StudentRankingRun,
        ranked: tuple[StageBScore, ...],
        inputs_hash: str,
        *,
        primary_tag_by_event: Mapping[str, str | None] = {},
    ) -> StudentFeed:
        scorable = [s for s in ranked if s.value is not None]
        unscorable = [s for s in ranked if s.value is None]
        ordered = _apply_diversity_cap(scorable, primary_tag_by_event, STUDENT_FEED_MAX_PER_PRIMARY_TAG)
        items = tuple(ordered[:STUDENT_FEED_MAX_ITEMS])
        pool = ordered[STUDENT_FEED_MAX_ITEMS:]
        seed = inputs_hash.removeprefix("sha256:")[:16]
        wildcard: StageBScore | None = None
        if pool and STUDENT_FEED_WILDCARD_SLOTS:
            index = int(seed, 16) % len(pool)
            wildcard = pool[index]
        return StudentFeed(
            items=items,
            wildcard=wildcard,
            wildcard_pool_size=len(pool),
            wildcard_seed=seed,
            withheld_unscorable=len(unscorable),
            withheld_untagged=sum(1 for s in unscorable if _is_untagged(s)),
            truncated=len(ordered) > STUDENT_FEED_MAX_ITEMS,
            policy_version=self.policy_version,
        )
```

This file supersedes the Task 5 stub; `StudentFeed`, `FeedPolicy` and `primary_tag` are carried over unchanged.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/test_student_feed_policy.py tests/unit/test_student_recommend.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add python/smartmatch_domain/smartmatch_domain/student_recommender/policy.py tests/unit/test_student_feed_policy.py
git commit -m "feat: DefaultFeedPolicy with bound, diversity cap, and declared wildcard (ADR-0018 D7)"
```

---

### Task 7: Golden cases — the artifact the owner reviews to close OQ-SE-01

**Files:**
- Create: `tests/golden/student/golden_case.schema.json`
- Create: `tests/golden/student/proposed/SE-GC-001..010.json` (ten cases listed below)
- Test: `tests/unit/test_student_golden.py`, `tests/unit/test_student_golden_case_schema.py`

**Interfaces:**
- Consumes: Tasks 4–6.
- Produces: the schema in contracts §5.1 and a runner that flips the gate in-test only.

- [ ] **Step 1: Write the schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://smartmatch.local/schemas/student-golden-case-v1.json",
  "title": "Student→event golden case",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "symptom_class", "description", "inputs", "expected"],
  "properties": {
    "id": {"type": "string", "pattern": "^SE-GC-[0-9]{3}$"},
    "symptom_class": {"type": "string", "enum": ["tie", "zero_or_unknown", "untagged", "wildcard", "diversity", "refusal", "anti_gaming", "eligibility"]},
    "description": {"type": "string", "minLength": 1},
    "inputs": {
      "type": "object", "additionalProperties": false, "required": ["run", "catalog"],
      "properties": {
        "run": {
          "type": "object", "additionalProperties": false,
          "required": ["interest_state", "interests", "modality_preference", "window_start", "window_end", "exclude_event_ids", "profile_version"],
          "properties": {
            "interest_state": {"enum": ["declared", "no_profile"]},
            "interests": {"type": "array", "items": {"type": "string"}},
            "modality_preference": {"enum": ["in_person", "virtual", "no_preference"]},
            "window_start": {"type": "string", "format": "date-time"},
            "window_end": {"type": "string", "format": "date-time"},
            "exclude_event_ids": {"type": "array", "items": {"type": "string"}},
            "profile_version": {"type": "integer", "minimum": 1}
          }
        },
        "catalog": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["event_id", "is_virtual", "starts_at", "time_precision", "publication_status", "already_registered", "tag_state", "tags", "quarantined_count"],
            "properties": {
              "event_id": {"type": "string"},
              "is_virtual": {"type": "boolean"},
              "starts_at": {"type": ["string", "null"], "format": "date-time"},
              "time_precision": {"enum": ["exact", "date_only", "unresolved"]},
              "publication_status": {"type": "string"},
              "already_registered": {"type": "boolean"},
              "tag_state": {"enum": ["tagged", "no_tag_records"]},
              "tags": {"type": "array", "items": {"type": "string"}},
              "quarantined_count": {"type": "integer", "minimum": 0}
            }
          }
        }
      }
    },
    "expected": {
      "type": "object", "additionalProperties": false,
      "required": ["refused", "order", "wildcard", "withheld_unscorable", "withheld_untagged", "excluded", "factor_states"],
      "properties": {
        "refused": {"type": "boolean"},
        "order": {"type": "array", "items": {"type": "string"}},
        "wildcard": {"type": ["string", "null"]},
        "withheld_unscorable": {"type": "integer"},
        "withheld_untagged": {"type": "integer"},
        "excluded": {"type": "object", "additionalProperties": {"type": "integer"}},
        "factor_states": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": {"enum": ["measured", "unknown"]}}}
      }
    }
  }
}
```

- [ ] **Step 2: Author the ten cases**

One file each, `tests/golden/student/proposed/SE-GC-00N.json`. All use `window_start = "2026-10-05T09:00:00+00:00"`, `window_end = "2026-10-12T09:00:00+00:00"`, events at `"2026-10-06T18:00:00+00:00"` unless stated, `publication_status = "published"`, `quarantined_count = 0`, `profile_version = 1`:

| id | symptom_class | inputs | expected |
|---|---|---|---|
| 001 | refusal | any valid run and catalog | `refused: true`, everything else empty/zero (this case runs against the shipped `proposed` registry; all others flip the gate in-test) |
| 002 | zero_or_unknown | `no_profile`; one tagged event | `order: []`, `withheld_unscorable: 1`, `factor_states.e1.student_interest_overlap = "unknown"` |
| 003 | untagged | interests `[finance]`; `e1` tags `[finance]`, `e2` `tag_state = no_tag_records`, `e3` tagged with `tags: []`, `quarantined_count: 2` | `order: [e1]`, `withheld_unscorable: 2`, `withheld_untagged: 2` |
| 004 | zero_or_unknown | interests `[finance]`; `e1` `[hackathon]`, `e2` `[finance]` | `order: [e2, e1]`, `factor_states.e1 = measured`, `withheld_unscorable: 0` |
| 005 | tie | interests `[finance]`; `b` `[finance]`, `a` `[finance]` | `order: [a, b]` |
| 006 | anti_gaming | interests = all twelve vocabulary terms; `e1` `[finance, hackathon]`; second run with `[finance, hackathon]` encoded as a second case 007 | 006: `order: [e1]` and the runner asserts `value == round(2/12, 4)`; 007: `value == 1.0` |
| 008 | diversity | interests `[finance, hackathon]`; `f1..f4` `[finance]` with descending scores, `h1` `[hackathon]` scoring below `f4` | `order: [f1, f2, f3, h1, f4]`, `wildcard: null`, `withheld_unscorable: 0`, `withheld_untagged: 0` |
| 009 | wildcard | interests `[finance]`; `e1..e8` `[finance]` | `order: [e1..e5]`, `wildcard` = the id the runner computes from the hash (author it by running once and pinning), `withheld_unscorable: 0` |
| 010 | eligibility | `in_person`; `exclude_event_ids: [skip]`; catalog of `ok`, `virtual`, `late (2026-10-20)`, `undated (unresolved, starts_at null)`, `mine (already_registered)`, `skip`, `unpub` | `order: [ok]`, `excluded: {not_published:1, unresolved_date:1, outside_window:1, modality_mismatch:1, already_registered:1, session_excluded:1}` |

- [ ] **Step 3: Write the runner and the schema test**

```python
# tests/unit/test_student_golden_case_schema.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1] / "golden" / "student"
_CASES = sorted((_ROOT / "proposed").glob("SE-GC-*.json"))


def _validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((_ROOT / "golden_case.schema.json").read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


@pytest.mark.parametrize("path", _CASES, ids=[p.stem for p in _CASES])
def test_case_matches_schema(path: Path) -> None:
    errors = sorted(_validator().iter_errors(json.loads(path.read_text(encoding="utf-8"))), key=str)
    assert not errors, "\n".join(str(e.message) for e in errors)


def test_ids_are_contiguous() -> None:
    numbers = sorted(int(p.stem.split("-")[-1]) for p in _CASES)
    assert numbers == list(range(1, len(numbers) + 1))
```

If `jsonschema` is not in `requirements/dev.in`, mirror whatever `tests/unit/test_matching_golden_case_schema.py` does instead of importing it.

```python
# tests/unit/test_student_golden.py
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION as V
from smartmatch_domain.factor_registry import RegistryNotApprovedError
from smartmatch_domain.factors.student_interest_overlap import (
    EventTagEvidence,
    EventTagState,
    StudentInterestEvidence,
    StudentInterestState,
)
from smartmatch_domain.student_recommender import registry as registry_module
from smartmatch_domain.student_recommender.eligibility import DefaultEligibilityFilter
from smartmatch_domain.student_recommender.policy import DefaultFeedPolicy
from smartmatch_domain.student_recommender.ranker import ContentRanker
from smartmatch_domain.student_recommender.recommend import recommend
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

_CASES = sorted((Path(__file__).resolve().parents[1] / "golden" / "student" / "proposed").glob("SE-GC-*.json"))


def _run(raw: dict) -> StudentRankingRun:
    state = StudentInterestState(raw["interest_state"])
    return StudentRankingRun(
        "unit-golden", "student-golden",
        StudentInterestEvidence(state, frozenset(raw["interests"]), V),
        raw["modality_preference"],
        (datetime.fromisoformat(raw["window_start"]), datetime.fromisoformat(raw["window_end"])),
        frozenset(raw["exclude_event_ids"]), raw["profile_version"],
    )


def _candidate(raw: dict) -> StudentEventCandidate:
    return StudentEventCandidate(
        raw["event_id"], raw["is_virtual"],
        None if raw["starts_at"] is None else datetime.fromisoformat(raw["starts_at"]),
        raw["time_precision"], raw["publication_status"], raw["already_registered"],
        EventTagEvidence(EventTagState(raw["tag_state"]), frozenset(raw["tags"]), raw["quarantined_count"], V),
    )


@pytest.mark.golden
@pytest.mark.parametrize("path", _CASES, ids=[p.stem for p in _CASES])
def test_golden_case(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    run = _run(case["inputs"]["run"])
    catalog = tuple(_candidate(c) for c in case["inputs"]["catalog"])
    expected = case["expected"]

    if expected["refused"]:
        with pytest.raises(RegistryNotApprovedError):
            recommend(run, catalog, eligibility=DefaultEligibilityFilter(), ranker=ContentRanker(), policy=DefaultFeedPolicy())
        return

    approved = replace(registry_module.STUDENT_REGISTRY, status="approved", approver="golden", approved_on="2026-10-05")
    monkeypatch.setattr(registry_module, "STUDENT_REGISTRY", approved)
    ranker = ContentRanker(registry=approved)

    outcome = recommend(run, catalog, eligibility=DefaultEligibilityFilter(), ranker=ranker, policy=DefaultFeedPolicy())
    assert [s.subject_id for s in outcome.feed.items] == expected["order"]
    assert (outcome.feed.wildcard.subject_id if outcome.feed.wildcard else None) == expected["wildcard"]
    assert outcome.feed.withheld_unscorable == expected["withheld_unscorable"]
    assert outcome.feed.withheld_untagged == expected["withheld_untagged"]
    for reason, count in expected["excluded"].items():
        assert outcome.eligibility.excluded[reason] == count
    by_id = {s.subject_id: s for s in (*outcome.feed.items, *(outcome.feed.wildcard,) if outcome.feed.wildcard else ())}
    for event_id, states in expected["factor_states"].items():
        score = by_id.get(event_id)
        if score is None:
            continue
        for key, state in states.items():
            actual = next(f for f in score.factor_scores if f.factor_key == key)
            assert actual.state.value == state
```

- [ ] **Step 4: Run and pin the wildcard id for SE-GC-009**

Run: `.venv/bin/python -m pytest tests/unit/test_student_golden_case_schema.py tests/unit/test_student_golden.py -q`
Expected: 009 fails once with the computed wildcard id in the assertion message; write that id into the case, rerun, all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/golden/student tests/unit/test_student_golden.py tests/unit/test_student_golden_case_schema.py
git commit -m "test: ten proposed student golden cases for OQ-SE-01 review"
```

---

### Task 8: The route — `GET /v1/units/{unit_id}/student/recommendations`

**Files:**
- Create: `services/api/smartmatch_api/routers/student_recommendations.py`
- Create: `services/api/smartmatch_api/student_profile_reader.py` (`StudentProfileReader` Protocol + `AbsentProfileReader`; the persistence-backed reader lands with W1 after OQ-SC-02)
- Modify: `services/api/smartmatch_api/main.py` (include router, same pattern as `student_events`)
- Modify: `tests/unit/test_matching_fail_closed.py:133-150` (widen `_G1_FORBIDDEN_SEGMENTS` with `"recommendation"`, `"recommendations"`, `"suggest"`; add the exact path to the existing allowlist beside `match-runs`)
- Modify: `tests/authz/test_policy_matrix.py` (new row: route → `{student}`)
- Test: `tests/contract/test_student_recommendations_api.py`
- Regenerate: `contracts/openapi/smartmatch.json` via `make openapi`

**Interfaces:**
- Consumes: Tasks 4–6; `StudentEventSummary` and the catalog query from `routers/student_events.py` (reuse the `browse_student_events` query by extracting `_load_published_events(session, unit_id, subject_id)` into a shared function in that module — same rows, same `on_my_agenda` logic).
- Produces: the Pydantic models in contracts §1.2, exactly; error code `student_registry_not_approved` (409).

- [ ] **Step 1: Write the failing contract test**

```python
# tests/contract/test_student_recommendations_api.py
"""ADR-0018 D8 and contracts §1: shape, refusals, determinism."""
from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app

_NUMERIC_NAME = re.compile(r"score|value|percent|match|fit|rating|confidence", re.IGNORECASE)


def _walk(schema: dict, components: dict, path: str = "", seen: set[str] | None = None):
    seen = seen or set()
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in seen:
            return
        seen.add(name)
        yield from _walk(components[name], components, path, seen)
        return
    for prop, sub in schema.get("properties", {}).items():
        here = f"{path}.{prop}"
        if sub.get("type") in {"number", "integer"} and _NUMERIC_NAME.search(prop) and prop != "rank":
            yield here
        yield from _walk(sub, components, here, seen)
        if sub.get("type") == "array":
            yield from _walk(sub.get("items", {}), components, here + "[]", seen)
        if "additionalProperties" in sub and isinstance(sub["additionalProperties"], dict):
            if here.endswith(".applied_weights"):
                continue
            yield from _walk(sub["additionalProperties"], components, here + "{}", seen)


def test_no_numeric_score_anywhere_in_the_response_schema() -> None:
    spec = app.openapi()
    components = spec["components"]["schemas"]
    offenders = list(_walk(components["StudentRecommendationsResponse"], components))
    assert offenders == [], offenders


def test_route_is_student_only_in_the_policy_matrix() -> None:
    from tests.authz.test_policy_matrix import ROUTE_ROLES  # the matrix the authz suite already asserts

    assert ROUTE_ROLES["GET /v1/units/{unit_id}/student/recommendations"] == {"student"}


@pytest.mark.usefixtures("student_client")
def test_proposed_registry_is_a_409_not_an_empty_200(student_client: TestClient, unit_id: str) -> None:
    response = student_client.get(f"/v1/units/{unit_id}/student/recommendations")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "student_registry_not_approved"


@pytest.mark.usefixtures("student_client")
def test_more_than_fifty_exclusions_is_a_422(student_client: TestClient, unit_id: str) -> None:
    params = [("exclude_event_ids", f"00000000-0000-0000-0000-{i:012d}") for i in range(51)]
    response = student_client.get(f"/v1/units/{unit_id}/student/recommendations", params=params)
    assert response.status_code == 422


def test_two_requests_in_the_same_hour_share_inputs_hash_and_wildcard(
    student_client: TestClient, unit_id: str, approved_registry, seeded_catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    import smartmatch_api.routers.student_recommendations as mod

    url = f"/v1/units/{unit_id}/student/recommendations"
    clock = iter([datetime(2026, 10, 5, 14, 3, tzinfo=UTC), datetime(2026, 10, 5, 14, 41, tzinfo=UTC)])
    monkeypatch.setattr(mod, "_now", lambda: next(clock))
    first = student_client.get(url).json()
    second = student_client.get(url).json()
    assert first["provenance"]["inputs_hash"] == second["provenance"]["inputs_hash"]
    assert first["wildcard"] == second["wildcard"]
    assert first["feed_window"] == second["feed_window"]
```

Use whatever `student_client` / `unit_id` fixtures `tests/contract/test_student_events_api.py` already uses; if it has none, copy its client construction verbatim into this file. `approved_registry` flips the gate the way Task 5's fixture does; `seeded_catalog` gives the unit enough published events for a wildcard.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/contract/test_student_recommendations_api.py -q`
Expected: FAIL — `KeyError: 'StudentRecommendationsResponse'` and 404s.

- [ ] **Step 3: Implement the reader protocol and the router**

```python
# services/api/smartmatch_api/student_profile_reader.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from smartmatch_domain.factors.student_interest_overlap import StudentInterestEvidence, StudentInterestState
from smartmatch_domain.factors.student_interest_overlap import STUDENT_INTEREST_VOCABULARY_VERSION


@dataclass(frozen=True, slots=True)
class StudentProfileView:
    interests: StudentInterestEvidence
    modality_preference: Literal["in_person", "virtual", "no_preference"]
    profile_version: int


class StudentProfileReader(Protocol):
    def read(self, *, unit_id: str, subject_id: str) -> StudentProfileView | None: ...


class AbsentProfileReader:
    """Until W1 lands (OQ-SC-02) there is no profile table; every read is absent."""

    def read(self, *, unit_id: str, subject_id: str) -> StudentProfileView | None:
        return None


def absent_evidence() -> StudentInterestEvidence:
    return StudentInterestEvidence(StudentInterestState.NO_PROFILE, frozenset(), STUDENT_INTEREST_VOCABULARY_VERSION)
```

```python
# services/api/smartmatch_api/routers/student_recommendations.py
"""ADR-0018 delivery: a synchronous read, pinned in the response, never stored."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from smartmatch_domain.factor_registry import RegistryNotApprovedError
from smartmatch_domain.factors.student_interest_overlap import (
    STUDENT_INTEREST_VOCABULARY_VERSION,
    EventTagEvidence,
    EventTagState,
)
from smartmatch_domain.one_sentence import assert_one_sentence
from smartmatch_domain.student_recommender.eligibility import DefaultEligibilityFilter
from smartmatch_domain.student_recommender.policy import DefaultFeedPolicy
from smartmatch_domain.student_recommender.ranker import ContentRanker
from smartmatch_domain.student_recommender.recommend import recommend
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun
from smartmatch_domain.student_recommender.student_feed import (
    STUDENT_FEED_MAX_SESSION_EXCLUSIONS,
    feed_window_for,
)

from smartmatch_api.errors import ApiError  # the standard envelope helper the other routers raise
from smartmatch_api.routers.student_events import StudentEventSummary, load_published_events
from smartmatch_api.student_profile_reader import StudentProfileReader, absent_evidence

router = APIRouter(tags=["student"])


def _now() -> datetime:                    # the test seam; the only clock read in this router
    return datetime.now(tz=UTC)


class StudentRecommendationItem(BaseModel):
    rank: int = Field(ge=1)
    event: StudentEventSummary
    matched_interests: list[str]
    reason: str


class StudentRecommendationWildcard(BaseModel):
    event: StudentEventSummary
    selection_basis: Literal["deterministic_index_from_inputs_hash"]
    pool_size: int = Field(ge=1)
    seed: str
    reason: str


class StudentFeedWindow(BaseModel):
    starts_at: datetime
    ends_at: datetime
    time_zone: str


class StudentRecommendationProvenance(BaseModel):
    ranker: Literal["content-1", "ltr-1"]
    fallback_from: Literal["ltr-1"] | None = None
    registry_version: str
    registry_hash: str
    registry_status: Literal["approved"]
    scoring_mode: str
    scoring_mode_version: str
    formula_version: str
    model_artifact_hash: str | None = None
    applied_weights: dict[str, float]
    interest_vocabulary_version: str
    profile_version: int
    inputs_hash: str
    policy_version: str


class StudentRecommendationsResponse(BaseModel):
    unit_id: uuid.UUID
    profile_state: Literal["present", "absent"]
    feed_window: StudentFeedWindow
    items: list[StudentRecommendationItem]
    wildcard: StudentRecommendationWildcard | None
    withheld_unscorable: int
    withheld_untagged: int
    withheld_unresolved_date: int
    withheld_ineligible: dict[str, int]
    truncated: bool
    caption: str
    provenance: StudentRecommendationProvenance


def _candidate(summary: StudentEventSummary, starts_at: datetime | None, precision: str, status: str) -> StudentEventCandidate:
    state = EventTagState.TAGGED if summary.tags or precision else EventTagState.NO_TAG_RECORDS
    return StudentEventCandidate(
        event_id=str(summary.id),
        is_virtual=summary.is_virtual,
        starts_at=starts_at,
        time_precision=precision,  # type: ignore[arg-type]
        publication_status=status,
        already_registered=summary.registration is not None and summary.registration.status == "registered",
        tags=EventTagEvidence(state, frozenset(summary.tags), 0, STUDENT_INTEREST_VOCABULARY_VERSION),
    )


def _reason(matched: list[str], total_tags: int) -> str:
    words = " and ".join(matched) if len(matched) <= 2 else ", ".join(matched[:-1]) + " and " + matched[-1]
    return assert_one_sentence(f"Recommended because your interests {words} match {len(matched)} of this event's {total_tags} tags.", field="reason")


@router.get("/v1/units/{unit_id}/student/recommendations", response_model=StudentRecommendationsResponse)
def get_student_recommendations(
    unit_id: uuid.UUID,
    exclude_event_ids: list[uuid.UUID] = Query(default=[], max_length=STUDENT_FEED_MAX_SESSION_EXCLUSIONS),
    ctx=Depends(require_student_in_unit),          # the same dependency student_events.py uses
    session=Depends(get_session),
    profiles: StudentProfileReader = Depends(get_student_profile_reader),
) -> StudentRecommendationsResponse:
    window = feed_window_for(_now())
    profile = profiles.read(unit_id=str(unit_id), subject_id=str(ctx.subject_id))
    interests = profile.interests if profile else absent_evidence()
    run = StudentRankingRun(
        unit_id=str(unit_id), subject_id=str(ctx.subject_id), interests=interests,
        modality_preference=profile.modality_preference if profile else "no_preference",
        feed_window=window, exclude_event_ids=frozenset(str(e) for e in exclude_event_ids),
        profile_version=profile.profile_version if profile else 1,
    )
    rows = load_published_events(session, unit_id=unit_id, subject_id=ctx.subject_id)   # (summary, starts_at, precision, status)
    by_id = {str(s.id): s for s, *_ in rows}
    catalog = tuple(_candidate(s, starts, precision, status) for s, starts, precision, status in rows)
    ranker = ContentRanker()
    policy = DefaultFeedPolicy()
    try:
        outcome = recommend(run, catalog, eligibility=DefaultEligibilityFilter(), ranker=ranker, policy=policy)
    except RegistryNotApprovedError as exc:
        raise ApiError(status_code=409, code="student_registry_not_approved", message=str(exc)) from exc

    def item(rank: int, score) -> StudentRecommendationItem:
        summary = by_id[score.subject_id]
        matched = sorted(set(summary.tags) & interests.terms)
        return StudentRecommendationItem(rank=rank, event=summary, matched_interests=matched, reason=_reason(matched, len(summary.tags)))

    feed = outcome.feed
    wildcard = None
    if feed.wildcard is not None:
        summary = by_id[feed.wildcard.subject_id]
        wildcard = StudentRecommendationWildcard(
            event=summary, selection_basis="deterministic_index_from_inputs_hash",
            pool_size=feed.wildcard_pool_size, seed=feed.wildcard_seed,
            reason=assert_one_sentence("This is a wildcard drawn from events that matched your interests but did not rank in the top five.", field="reason"),
        )
    model = ranker.registry.scoring_modes[ranker.scoring_mode]
    profile_state = "present" if profile else "absent"
    caption = (
        "No interest profile is on file, so there is nothing to rank yet."
        if profile is None
        else f"Ranked {len(feed.items)} of {len(outcome.eligibility.eligible)} eligible events this week; {feed.withheld_unscorable} could not be scored."
    )
    return StudentRecommendationsResponse(
        unit_id=unit_id,
        profile_state=profile_state,
        feed_window=StudentFeedWindow(starts_at=window[0], ends_at=window[1], time_zone="UTC"),
        items=[item(i + 1, s) for i, s in enumerate(feed.items)],
        wildcard=wildcard,
        withheld_unscorable=feed.withheld_unscorable,
        withheld_untagged=feed.withheld_untagged,
        withheld_unresolved_date=outcome.eligibility.excluded["unresolved_date"],
        withheld_ineligible=dict(outcome.eligibility.excluded),
        truncated=feed.truncated,
        caption=assert_one_sentence(caption, field="caption"),
        provenance=StudentRecommendationProvenance(
            ranker=ranker.ranker_id, registry_version=ranker.registry.version,
            registry_hash=ranker.registry.registry_hash, registry_status="approved",
            scoring_mode=ranker.scoring_mode, scoring_mode_version=model.scoring_mode_version or "",
            formula_version=ranker.formula_version, model_artifact_hash=ranker.model_artifact_hash,
            applied_weights=dict(feed.items[0].applied_weights) if feed.items else {},
            interest_vocabulary_version=STUDENT_INTEREST_VOCABULARY_VERSION,
            profile_version=run.profile_version, inputs_hash=outcome.inputs_hash,
            policy_version=policy.policy_version,
        ),
    )
```

Replace `require_student_in_unit`, `get_session`, `get_student_profile_reader`, `ApiError`, and `load_published_events` with the real names in `routers/student_events.py` and `smartmatch_api` — read that file first; the names above are the roles, the file has the spellings. The unit's IANA zone for `feed_window.time_zone` comes from wherever `student_events.py` gets the event's zone; use that, not `"UTC"`, if it is available.

- [ ] **Step 4: Widen the fail-closed scan and the policy matrix**

In `tests/unit/test_matching_fail_closed.py` add `"recommendation"`, `"recommendations"`, `"suggest"` to `_G1_FORBIDDEN_SEGMENTS` and add the literal `"/v1/units/{unit_id}/student/recommendations"` to the allowlist that admits `match-runs`. In `tests/authz/test_policy_matrix.py` add the route with `{"student"}`.

- [ ] **Step 5: Run everything and regenerate the contract**

Run: `make openapi && .venv/bin/python -m pytest tests/contract/test_student_recommendations_api.py tests/unit/test_matching_fail_closed.py tests/authz -q && make openapi-check`
Expected: PASS; `contracts/openapi/smartmatch.json` gains the route and models.

- [ ] **Step 6: Commit**

```bash
git add services/api/smartmatch_api/routers/student_recommendations.py services/api/smartmatch_api/student_profile_reader.py services/api/smartmatch_api/main.py services/api/smartmatch_api/routers/student_events.py tests/contract/test_student_recommendations_api.py tests/unit/test_matching_fail_closed.py tests/authz/test_policy_matrix.py contracts/openapi/smartmatch.json
git commit -m "feat: GET /student/recommendations behind the proposed-registry gate (ADR-0018 D8)"
```

---

### Task 9: V2 shape — `FeatureSpec`, `STUDENT_FEATURE_REGISTRY`, `FeatureVector`

**Files:**
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/features.py`
- Test: `tests/unit/test_feature_spec.py`

**Interfaces:**
- Consumes: `PROHIBITED_INPUTS`, Tasks 4–5 types.
- Produces: `FeatureSource`, `FeatureSpec`, `STUDENT_FEATURE_REGISTRY_VERSION = "0.1.0-proposed-oq-se-19"`, `STUDENT_FEATURES`, `FeatureVector`, `build_feature_vector(run, candidate) -> FeatureVector`.
- Deletion: no table is created in this plan. When OQ-SE-19 + OQ-SC-11 close, the `training_example` migration carries a `student_profile_id` FK with `ON DELETE CASCADE` and the three purge tests in contracts §5.4; the account-level FK alone is insufficient because the W1 profile DELETE leaves `user_account` intact.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_feature_spec.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION as V
from smartmatch_domain.factors.student_interest_overlap import (
    EventTagEvidence,
    EventTagState,
    StudentInterestEvidence,
    StudentInterestState,
)
from smartmatch_domain.student_recommender.features import (
    STUDENT_FEATURES,
    FeatureSource,
    FeatureSpec,
    build_feature_vector,
)
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def test_a_prohibited_source_or_key_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="PROHIBITED_INPUTS"):
        FeatureSpec("unrelated_student_feedback", FeatureSource.DERIVED, True, "OQ-SE-01", "x")
    with pytest.raises(ValueError, match="label"):
        FeatureSpec("registered_before", FeatureSource.OUTCOME, False, "OQ-SE-19", "x")


def test_registered_features_never_name_an_outcome_source() -> None:
    assert all(f.source is not FeatureSource.OUTCOME for f in STUDENT_FEATURES)
    assert {f.key for f in STUDENT_FEATURES} >= {"student_interest_overlap", "modality_match", "days_until_event"}


def test_required_unknown_is_reported_not_imputed() -> None:
    run = StudentRankingRun(
        "u", "s", StudentInterestEvidence(StudentInterestState.NO_PROFILE, frozenset(), V),
        "no_preference", (T0, T0 + timedelta(days=7)), frozenset(), 1,
    )
    candidate = StudentEventCandidate("e", False, T0 + timedelta(days=2), "exact", "published", False,
                                      EventTagEvidence(EventTagState.TAGGED, frozenset({"finance"}), 0, V))
    vector = build_feature_vector(run, candidate)
    assert vector.values["student_interest_overlap"] is None
    assert "student_interest_overlap" in vector.unknown_required_keys
    assert vector.values["days_until_event"] == 2.0


def test_unbounded_feature_without_transform_is_rejected() -> None:
    with pytest.raises(ValueError, match="factor_transform"):
        FeatureSpec("raw_count", FeatureSource.EVENT, True, "OQ-SE-01", "x")


@pytest.mark.parametrize("key,raw,expected", [("interest_count", 2.0, 2 / 12), ("event_tag_count", 12.0, 1.0), ("event_tag_count", 30.0, 1.0), ("days_until_event", 3.5, 0.5)])
def test_as_factor_is_bounded(key: str, raw: float, expected: float) -> None:
    spec = next(f for f in STUDENT_FEATURES if f.key == key)
    assert spec.as_factor(raw) == pytest.approx(expected)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_feature_spec.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/features.py
"""V2 feature registry (ADR-0018 D4 condition 2). Shape only; no model here."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from smartmatch_domain.factor_registry import PROHIBITED_INPUTS
from smartmatch_domain.factors.student_interest_overlap import score_student_interest_overlap
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun
from smartmatch_domain.student_recommender.student_feed import STUDENT_FEED_WINDOW_DAYS


class FeatureSource(StrEnum):
    STUDENT_PROFILE = "student_profile"
    EVENT = "event"
    DERIVED = "derived"
    OUTCOME = "outcome"
    INTERACTION = "interaction"


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    key: str
    source: FeatureSource
    required: bool
    admitted_by: str
    rationale: str
    factor_transform: Callable[[float], float] | None = None
    raw_bounded: bool = False          # True when raw values are already in [0, 1]

    def as_factor(self, raw: float) -> float:
        value = raw if self.factor_transform is None else self.factor_transform(raw)
        return min(1.0, max(0.0, value))

    def __post_init__(self) -> None:
        if self.key in PROHIBITED_INPUTS or self.source.value in PROHIBITED_INPUTS:
            raise ValueError(f"{self.key}: names a PROHIBITED_INPUTS entry")
        if self.source is FeatureSource.OUTCOME:
            raise ValueError(f"{self.key}: an outcome is a label, never a feature (OQ-SE-19)")
        if not self.admitted_by.startswith("OQ-"):
            raise ValueError("admitted_by: must name a register row")
        if self.factor_transform is None and not self.raw_bounded:
            raise ValueError(f"{self.key}: unbounded raw feature needs a factor_transform")


STUDENT_FEATURE_REGISTRY_VERSION: Final[str] = "0.1.0-proposed-oq-se-19"

STUDENT_INTEREST_VOCABULARY_SIZE: Final[int] = 12     # W1: the twelve G3 terms
STUDENT_MAX_TAGS_PER_EVENT: Final[int] = 12          # same vocabulary

STUDENT_FEATURES: Final[tuple[FeatureSpec, ...]] = (
    FeatureSpec("student_interest_overlap", FeatureSource.DERIVED, True, "OQ-SE-01", "Jaccard, the V1 factor.", raw_bounded=True),
    FeatureSpec("interest_count", FeatureSource.STUDENT_PROFILE, True, "OQ-SE-01", "How many interests were declared.", factor_transform=lambda n: n / STUDENT_INTEREST_VOCABULARY_SIZE),
    FeatureSpec("event_tag_count", FeatureSource.EVENT, True, "OQ-SE-01", "How many mapped tags the event carries.", factor_transform=lambda n: n / STUDENT_MAX_TAGS_PER_EVENT),
    FeatureSpec("modality_match", FeatureSource.DERIVED, True, "OQ-SE-01", "1.0 when modality is compatible, else 0.0.", raw_bounded=True),
    FeatureSpec("days_until_event", FeatureSource.EVENT, False, "OQ-SE-01", "Days from window start; missing when unresolved.", factor_transform=lambda d: d / STUDENT_FEED_WINDOW_DAYS),
)


@dataclass(frozen=True, slots=True)
class FeatureVector:
    feature_registry_version: str
    values: Mapping[str, float | None]
    unknown_required_keys: tuple[str, ...]


def build_feature_vector(run: StudentRankingRun, candidate: StudentEventCandidate) -> FeatureVector:
    overlap = score_student_interest_overlap(run.interests, candidate.tags)
    compatible = (
        run.modality_preference == "no_preference"
        or (run.modality_preference == "virtual") == candidate.is_virtual
    )
    days = None if candidate.starts_at is None else (candidate.starts_at - run.feed_window[0]).total_seconds() / 86400.0
    values: dict[str, float | None] = {
        "student_interest_overlap": overlap.value,
        "interest_count": None if not run.interests.terms else float(len(run.interests.terms)),
        "event_tag_count": None if candidate.tags.state.value != "tagged" else float(len(candidate.tags.mapped_terms)),
        "modality_match": 1.0 if compatible else 0.0,
        "days_until_event": days,
    }
    unknown_required = tuple(f.key for f in STUDENT_FEATURES if f.required and values[f.key] is None)
    return FeatureVector(STUDENT_FEATURE_REGISTRY_VERSION, MappingProxyType(values), unknown_required)
```

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/unit/test_feature_spec.py tests/unit/test_student_scoring_inputs_wiring.py -q`
Expected: PASS (add `smartmatch_domain.student_recommender.features` to the wiring test's `_MODULES`).

- [ ] **Step 5: Commit**

```bash
git add python/smartmatch_domain/smartmatch_domain/student_recommender/features.py tests/unit/test_feature_spec.py tests/unit/test_student_scoring_inputs_wiring.py
git commit -m "feat: V2 feature registry shape with prohibited-source refusal (ADR-0018 D4)"
```

---

### Task 10: `LearnedRanker` skeleton, fallback builder, and the gold-set evaluator (shadow only, no dependency)

**Files:**
- Create: `python/smartmatch_domain/smartmatch_domain/student_recommender/learned.py`
- Create: `tools/evaluate_student_ranker.py`
- Create: `tests/golden/student/gold/README.md` (how to author a graded triple; no rows yet)
- Test: `tests/unit/test_learned_ranker_fallback.py`, `tests/unit/test_student_ranker_evaluator.py`

**Interfaces:**
- Consumes: Task 5 `StudentRanker`, Task 9 `build_feature_vector`.
- Produces: `Predictor` Protocol (`predict(rows: Sequence[Mapping[str, float | None]]) -> Sequence[float]`), `LearnedRanker(predictor, artifact_hash, registry)`, `ArtifactUnavailable`, `build_student_ranker(*, learned_artifact: Callable[[], Predictor] | None) -> tuple[StudentRanker, str | None]`, `ndcg_at_k(order, graded, k=5)`, `agreement_at_k(a, b, k=5)`. `xgboost` is **not** imported anywhere; a real predictor arrives with OQ-SE-20 as `requirements/ml.in`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_learned_ranker_fallback.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION as VOCAB
from smartmatch_domain.factors.student_interest_overlap import (
    EventTagEvidence,
    EventTagState,
    StudentInterestEvidence,
    StudentInterestState,
)
from smartmatch_domain.student_recommender.learned import (
    ArtifactUnavailable,
    LearnedRanker,
    build_student_ranker,
)
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
RUN = StudentRankingRun(
    "unit-1", "stu-1",
    StudentInterestEvidence(StudentInterestState.DECLARED, frozenset({"finance"}), VOCAB),
    "no_preference", (T0, T0 + timedelta(days=7)), frozenset(), 1,
)


def _catalog(*, tags: Mapping[str, set[str]]) -> tuple[StudentEventCandidate, ...]:
    """Same helper Task 5's tests define; one candidate per entry, insertion order preserved."""
    return tuple(
        StudentEventCandidate(
            event_id, False, T0 + timedelta(days=1), "exact", "published", False,
            EventTagEvidence(EventTagState.TAGGED, frozenset(terms), 0, VOCAB),
        )
        for event_id, terms in tags.items()
    )


def _broken():
    raise ArtifactUnavailable("no artifact configured")


class _Constant:
    def predict(self, rows):
        return [0.5 for _ in rows]


def test_missing_artifact_falls_back_to_content_and_names_it() -> None:
    ranker, fallback_from = build_student_ranker(learned_artifact=_broken)
    assert ranker.ranker_id == "content-1"
    assert fallback_from == "ltr-1"


def test_no_learned_config_is_plain_content() -> None:
    ranker, fallback_from = build_student_ranker(learned_artifact=None)
    assert ranker.ranker_id == "content-1" and fallback_from is None


def test_a_loaded_artifact_yields_the_learned_ranker() -> None:
    ranker, fallback_from = build_student_ranker(learned_artifact=lambda: _Constant())
    assert ranker.ranker_id == "ltr-1" and fallback_from is None
    assert ranker.formula_version.startswith("ltr-")


def test_learned_ranker_ranks_multi_interest_multi_tag_candidates() -> None:
    run = replace(RUN, interests=StudentInterestEvidence(StudentInterestState.DECLARED, frozenset({"finance", "hackathon"}), VOCAB))
    candidates = _catalog(tags={"e1": {"finance", "hackathon"}, "e2": {"finance"}, "e3": set()})
    ranker = LearnedRanker(predictor=_Constant(), model_artifact_hash=None)
    ranked = ranker.rank(run, candidates)
    assert [s.subject_id for s in ranked][:2] == ["e1", "e2"]            # constant margin ⇒ event-id tie-break
    e1 = next(s for s in ranked if s.subject_id == "e1")
    assert e1.value is not None
    assert all(0.0 <= f.value <= 1.0 for f in e1.factor_scores if f.value is not None)
    assert next(f for f in e1.factor_scores if f.factor_key == "interest_count").value == pytest.approx(2 / 12)
    assert next(s for s in ranked if s.subject_id == "e3").value is None   # untagged ⇒ unscorable, not raised
```

```python
# tests/unit/test_student_ranker_evaluator.py
from __future__ import annotations

from smartmatch_domain.student_recommender.learned import agreement_at_k, ndcg_at_k


def test_ndcg_is_one_for_a_perfect_order_and_less_otherwise() -> None:
    graded = {"a": 2, "b": 1, "c": 0}
    assert ndcg_at_k(["a", "b", "c"], graded, k=5) == 1.0
    assert ndcg_at_k(["c", "b", "a"], graded, k=5) < 1.0
    assert ndcg_at_k([], graded, k=5) == 0.0


def test_agreement_is_set_overlap_of_the_top_k() -> None:
    assert agreement_at_k(["a", "b", "c"], ["c", "b", "a"], k=3) == 1.0
    assert agreement_at_k(["a", "b"], ["c", "d"], k=2) == 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_learned_ranker_fallback.py tests/unit/test_student_ranker_evaluator.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# python/smartmatch_domain/smartmatch_domain/student_recommender/learned.py
"""V2 Stage B skeleton (ADR-0018 D4). Shadow-only until OQ-SE-19/20; no model library here."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from smartmatch_domain.factor_registry import FactorRegistry
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.scoring import StageBScore, _ranked
from smartmatch_domain.student_recommender import registry as registry_module
from smartmatch_domain.student_recommender.features import STUDENT_FEATURES, build_feature_vector
from smartmatch_domain.student_recommender.ranker import ContentRanker, StudentRanker
from smartmatch_domain.student_recommender.run import StudentEventCandidate, StudentRankingRun

LEARNED_SCORING_MODE = "student-event-ltr-1"
LEARNED_FORMULA_VERSION = "ltr-0.1.0-shadow"


class ArtifactUnavailable(RuntimeError):
    """The configured model artifact could not be loaded; the caller falls back."""


class Predictor(Protocol):
    def predict(self, rows: Sequence[Mapping[str, float | None]]) -> Sequence[float]: ...


@dataclass(frozen=True, slots=True)
class LearnedRanker:
    predictor: Predictor
    model_artifact_hash: str | None
    ranker_id: str = "ltr-1"
    registry: FactorRegistry = field(default_factory=lambda: registry_module.STUDENT_REGISTRY)
    scoring_mode: str = LEARNED_SCORING_MODE
    formula_version: str = LEARNED_FORMULA_VERSION

    def rank(self, run: StudentRankingRun, candidates: Sequence[StudentEventCandidate]) -> tuple[StageBScore, ...]:
        vectors = [build_feature_vector(run, c) for c in candidates]
        scorable = [(c, v) for c, v in zip(candidates, vectors, strict=True) if not v.unknown_required_keys]
        margins = list(self.predictor.predict([v.values for _, v in scorable])) if scorable else []
        lo, hi = (min(margins), max(margins)) if margins else (0.0, 0.0)
        rescale = (lambda m: 0.5) if hi == lo else (lambda m: (m - lo) / (hi - lo))
        by_id: dict[str, StageBScore] = {}
        for (c, v), m in zip(scorable, margins, strict=True):
            by_id[c.event_id] = self._score(c.event_id, v, rescale(m))
        for c, v in zip(candidates, vectors, strict=True):
            if c.event_id not in by_id:
                by_id[c.event_id] = self._score(c.event_id, v, None)
        return _ranked(tuple(by_id[c.event_id] for c in candidates))

    def _score(self, event_id: str, vector, value: float | None) -> StageBScore:
        required = tuple(f.key for f in STUDENT_FEATURES if f.required)
        specs = {f.key: f for f in STUDENT_FEATURES}
        factor_scores = tuple(
            FactorScore(
                factor_key=k,
                value=None if vector.values[k] is None else specs[k].as_factor(vector.values[k]),
                basis=f"Feature {k} (raw {vector.values[k]}) from registry {vector.feature_registry_version}.",
            )
            for k in required
        )
        return StageBScore(
            subject_id=event_id, value=None if value is None else round(value, 6),
            factor_scores=factor_scores, applied_weights={k: 1.0 / len(required) for k in required},
            unknown_factor_keys=vector.unknown_required_keys, registry_version=self.registry.version,
            formula_version=self.formula_version, scoring_mode=self.scoring_mode, scoring_mode_version="1.0.0",
        )


def build_student_ranker(*, learned_artifact: Callable[[], Predictor] | None) -> tuple[StudentRanker, str | None]:
    """D4's fallback rule: a learned artifact that fails to load yields content-1, named."""
    if learned_artifact is None:
        return ContentRanker(), None
    try:
        predictor = learned_artifact()
    except ArtifactUnavailable:
        return ContentRanker(), "ltr-1"
    return LearnedRanker(predictor=predictor, model_artifact_hash=None), None


def ndcg_at_k(order: Sequence[str], graded: Mapping[str, int], *, k: int = 5) -> float:
    def dcg(ids: Sequence[str]) -> float:
        return sum((2 ** graded.get(e, 0) - 1) / math.log2(i + 2) for i, e in enumerate(ids[:k]))

    ideal = dcg(sorted(graded, key=lambda e: -graded[e]))
    return 0.0 if ideal == 0.0 or not order else round(dcg(order) / ideal, 6)


def agreement_at_k(a: Sequence[str], b: Sequence[str], *, k: int = 5) -> float:
    top_a, top_b = set(a[:k]), set(b[:k])
    return 0.0 if not top_a and not top_b else round(len(top_a & top_b) / max(len(top_a), len(top_b)), 6)
```

`tools/evaluate_student_ranker.py` loads every `tests/golden/student/gold/*.json` (same `inputs` shape as §5.1 plus `graded_relevance`), runs `ContentRanker` and, if `--artifact PATH` is given, a `LearnedRanker` over a predictor the tool constructs (`ArtifactUnavailable` when the path is missing), and prints a table of NDCG@5 and agreement@5 per case and in aggregate. It is a CLI over the two functions above; write it with `argparse` and no third-party import.

Note for `LearnedRanker.scoring_mode`: `"student-event-ltr-1"` is **not** in `STUDENT_SCORING_MODES` yet. Do not widen it in this task: `LearnedRanker` is never handed to `recommend()` in V1 (that composition resolves the mode through the registry and would refuse it, which is correct while OQ-SE-20 is open). The evaluator calls `rank()` directly. Widening the vocabulary and adding `STUDENT_EVENT_LTR_MODEL` is the first line of the OQ-SE-20 promotion PR.

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/unit/test_learned_ranker_fallback.py tests/unit/test_student_ranker_evaluator.py tests/unit/test_student_scoring_inputs_wiring.py -q && .venv/bin/python tools/evaluate_student_ranker.py --help`
Expected: PASS; help text prints. Add `smartmatch_domain.student_recommender.learned` to the wiring test's `_MODULES`.

- [ ] **Step 5: Full check and commit**

Run: `make check`
Expected: the three known local `.env`-related failures at most (see memory); nothing new.

```bash
git add python/smartmatch_domain/smartmatch_domain/student_recommender/learned.py tools/evaluate_student_ranker.py tests/golden/student/gold/README.md tests/unit/test_learned_ranker_fallback.py tests/unit/test_student_ranker_evaluator.py tests/unit/test_student_scoring_inputs_wiring.py
git commit -m "feat: LearnedRanker shadow skeleton, fallback builder, and gold-set evaluator (ADR-0018 D4)"
```

---

## Sequencing and gates

| Task | Depends on | Merge gate |
|---|---|---|
| 1 | — | none: no behaviour change; `test_factor_registry.py` untouched |
| 2, 3, 4, 9 | 1 | none: pure domain, gate shut |
| 5, 6, 7 | 2–4 | none; Task 7's cases are the OQ-SE-01 review artifact |
| 8 | 5–7, W1 profile table (OQ-SC-02) for a non-absent profile | route merges with the 409 live; a `200` needs OQ-SE-01 |
| 10 | 5, 9 | none; adding `xgboost` and widening `STUDENT_SCORING_MODES` wait on OQ-SE-20 |

Estimated engineering time, executor-facing: Task 1 about a day (three hot modules, type-check churn); Tasks 2–7 about two days together; Task 8 one day plus whatever W1 needs; Tasks 9–10 one day. Roughly one engineer-week for V1 with the gate shut, excluding decision wait time.
