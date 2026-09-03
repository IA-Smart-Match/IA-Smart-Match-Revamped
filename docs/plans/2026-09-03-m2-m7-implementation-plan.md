# Implementation plan — G1 matching M2, M4, M6, M6j, M7

**Plan id:** P5-M2M7
**Date:** 2026-09-03
**Branch:** `pilot/match-engine-m2-m7` (worktree
`/mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-match-engine`)
**Parent plan:** `docs/plans/2026-08-28-g1-matching-m1-m10-plan.md` (cards M2, M4, M6, M6j, M7)
**Binding authority:** `docs/plans/workshops/g1-workshop-output-worksheet.md` (RATIFIED 2026-09-03)
**Supporting authority:** `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`
(§3 D3 deferred, §5 F-25 normalize-on-apply)

**Execution model:** subagent-driven. One fresh implementer subagent per task card.
Each subagent sees **only** its own card plus the Global Constraints and the
Cross-card interface contract sections below. No card refers to the worksheet,
the decision record, or another card for a value — every binding value is inlined.

---

## 0. Global Constraints — binding on every implementer and every reviewer

### 0.1 Environment

- All work happens in the worktree
  `/mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-match-engine`. Use absolute
  paths. Do not touch the sibling main checkout.
- **The worktree `.venv` is currently bare (pip only).** Before the first card runs,
  someone must run `make setup` from the worktree root. Verify with
  `.venv/bin/python -c "import pytest, mypy"`. If `make setup` has not been run,
  run it before anything else; it installs `requirements/dev.txt` with
  `--require-hashes` and editable-installs the four workspace packages.
- Python is 3.12 in that venv. Tests run as
  `.venv/bin/python -m pytest <paths> -q` from the worktree root.
- **No network at runtime and no network in any test.** No route-matrix provider,
  no HTTP client, no socket. `make lock` (Task 5 only) is the single exception and
  it is a build-time operation, not a runtime one.

### 0.2 Ratified matching values (copy verbatim; never re-derive)

| Key | Kind | Weight | Notes |
|---|---|---|---|
| `topic_relevance` | `FactorKind.SUITABILITY` | **0.70** | Stage B |
| `travel_burden` | `FactorKind.PENALTY` | **0.30** | Stage B, straight-line coarse estimate |
| `availability` | `FactorKind.ELIGIBILITY` | **0** | Stage A, applied **after** the Stage B shortlist |

Stage B weights sum to **1.0**. Weights are **normalized on apply** (F-25) — computed
at scoring time by `normalize_weights()`, **never hand-tuned**.

Approved `zero_classification` per golden case:

| Case | Classification |
|---|---|
| `G1-GC-002` (topic relevance zero, topics recorded, disjoint) | `measured_zero` |
| `G1-GC-003` (match depth zero, history recorded, empty) | `measured_zero` |
| `G1-GC-005` (topics absent) | `unknown` |
| `G1-GC-006` (topics recorded, disjoint) | `measured_zero` |
| `G1-GC-007` (history absent) | `unknown` |
| `G1-GC-008` (history recorded, empty) | `measured_zero` |

**Tie-break rule:** lexicographic **ascending** by `subject_id`.
`G1-GC-004` supplies the reproducing inputs (`SYNTH-PRO-0001`, `SYNTH-PRO-0002`);
`G1-GC-001` is the symptom it reproduces.

### 0.3 Hard rules

1. **Unknown is not zero (ADR-0011).** Missing evidence returns `None`. Never
   coerce an absent record to `0.0`. A recorded-but-empty / recorded-but-disjoint
   record is a genuine `0.0` (`measured_zero`). These two must be distinguishable
   in every return type and asserted as a pair in every factor's tests.
2. **Never assert, reproduce, or reference the legacy 43% value** or any other
   legacy engine output. Characterizing the legacy scoring engine is forbidden
   (its maximum attainable score is 0.90 — the defect the registry exists to kill).
3. **Every scoring path calls `assert_registry_approved()` first**, before reading
   any evidence.
4. **Never fabricate mileage, travel time, or any distance.** No live route-matrix
   provider. D3 is deferred; straight-line only, explicitly labelled coarse.
5. **Never implement, wire, or reference these factors:** `role_fit`,
   `engagement_load`, `repeat_penalty`, `credential_check`, `contact_status`,
   `declared_cap`, `historical_conversion`, `student_interest`. They are dropped
   forever for this PR. `eli.py` already exists and stays **untouched** —
   `engagement_load` must NOT be wired into the registry.
6. **`match_depth` is a derived display quantity, not a registry factor.** It must
   never appear in `PROPOSED_FACTORS` and never carry weight.
7. **CP-SAT, never an LLM**, for portfolio assignment. Returning 2–3 speakers is a
   *presentation* rule owned by M10; the optimizer takes portfolio size as a
   parameter and must not hardcode 2 or 3.
8. Out of scope entirely: `match_run` table/persistence (M8), HTTP API/routes
   (M8b), UI (M10), pipeline writers, crawler, explanations (M9).

### 0.4 Do-not-touch file list (any card, no exceptions)

- Anything under `services/api/` or `apps/`.
- `tests/unit/test_matching_fail_closed.py` — in particular
  `test_openapi_exposes_no_gated_product_surface_routes` must NOT be inverted,
  weakened, or edited. No HTTP routes land in this PR.
- `tests/unit/test_matching_golden_case_schema.py` — untouched.
- `tests/golden/matching/symptoms/**` and `tests/golden/matching/golden_case.schema.json`
  — untouched. Those fixtures are drafts, `zero_classification` is deliberately
  absent, and their schema forbids `expected`. Approved cases land in a **new**
  directory instead (Task 4).
- `python/smartmatch_domain/smartmatch_domain/eli.py` and `tests/unit/test_eli.py`.
- `contracts/openapi/smartmatch.json`.
- `db/migrations/**`, `python/smartmatch_persistence/**`.

### 0.5 House style (mirror `smartmatch_domain/eli.py` and `factor_registry.py`)

- Module docstring that cites the architecture section and, where relevant, the
  migration manifest / decision artifact path, and states what the module refuses
  to do and why.
- `from __future__ import annotations` first.
- Frozen, slotted dataclasses: `@dataclass(frozen=True, slots=True)`.
- `StrEnum` for closed vocabularies.
- `Final[...]` for version and parameter constants, each with a `#:` comment
  explaining the value.
- Explicit `__all__`, sorted.
- Google-style `Args:` / `Returns:` / `Raises:` docstrings on public functions.
- Validate in `__post_init__` and raise `ValueError` with the offending key in
  the message.
- **ruff line-length 100**; ruff lint select `E,F,I,UP,B,SIM,RUF`.
- **mypy strict** over `python/` and `services/`. Every function annotated.
- Pure domain code: no `os`, `pathlib`, `socket`, `subprocess`, `requests`,
  `httpx`, `google`, `boto3`, no framework, no storage, no provider imports.
  (Task 5's `ortools` import is the single, explicitly analysed exception.)

### 0.6 Repo gates that will bite you

- `make scan` (`tools/scan_forbidden.py`) rule **`fabricated-score`** matches the
  regex `(score|confidence|match_score)\s*=\s*(0\.\d+|[1-9]\d*)\s*(#.*)?$` in any
  `.py` file. A line like `expected_score = 0.3` or `score = 0.7` **fails the
  build**, in tests too. Write assertions as
  `assert result.value == pytest.approx(0.3)` and name locals so they do not end
  in `score = <number>` at end of line. JSON fixtures are not scanned.
- Rule **`demo-mode-fallback`** matches `load_fixture(`. Name golden helpers
  `_load_case(` / `_case_paths(`, never `load_fixture(`.
- Rule **`module-level-mutable-state`** matches module-level
  `NAME_(QUEUE|STATE|CACHE|REGISTRY|STORE|BUS|RESULT[S])= {}` / `= []`. Use
  frozen tuples / `frozenset` for module constants.
- `make licenses` (`tools/supply_chain.py`) fails on any dependency whose declared
  license is outside `ALLOWED_LICENSES`. **Do not widen that table to make a build
  green.** If a new transitive dependency reports an unknown license, STOP and report.

### 0.7 Fence discipline

Each card lists the exact files it may create or modify. **Touching any other file
is a card failure**, even a trivially correct fix. Fences do not overlap, with one
stated exception:

> **Task 4 is the sole owner of
> `python/smartmatch_domain/smartmatch_domain/factor_registry.py` and of
> `tests/unit/test_factor_registry.py`.** Tasks 1, 2, 3 and 5 may *import from*
> the registry but must not edit either file. Tasks 1–3 must not change any
> `implemented` flag; that is Task 4's job alone.

### 0.8 Ordering

- Tasks 1, 2, 3 are independent and may run in parallel.
- Task 4 requires Tasks 1, 2, 3 complete.
- Task 5 requires Task 4 complete (it consumes Stage B utilities).

---

## Cross-card interface contract

These are the exact shared names Tasks 1–3 produce and Task 4 consumes.
**Task 1 is the sole author of `factors/__init__.py`.** Tasks 2 and 3 import from
it and must not edit it. Field names, types and order are binding.

File: `python/smartmatch_domain/smartmatch_domain/factors/__init__.py` (Task 1)

```python
__all__ = [
    "FACTOR_SCORE_PRECISION",
    "EvidenceState",
    "FactorScore",
    "ZeroClassification",
]

#: Decimal places every factor value is rounded to before it leaves a factor.
FACTOR_SCORE_PRECISION: Final[int] = 4


class ZeroClassification(StrEnum):
    """ADR-0011: an unknown and a measured zero are different facts."""

    MEASURED_ZERO = "measured_zero"
    UNKNOWN = "unknown"


class EvidenceState(StrEnum):
    """Whether the underlying record exists at all."""

    ABSENT = "absent"  # no record -> unknown
    RECORDED = "recorded"  # record exists, possibly empty -> measurable


@dataclass(frozen=True, slots=True)
class FactorScore:
    """One factor's contribution, or its explicit absence.

    Attributes:
        factor_key: Registry key. Must match a key in ``factor_keys()``.
        value: Score in ``[0.0, 1.0]``, or ``None`` when the evidence is absent.
            ``None`` is unknown and is never coerced to ``0.0``.
        basis: Human-readable provenance for the number, non-empty.
        estimate_label: Set when the value is an explicitly coarse estimate,
            otherwise ``None``.
    """

    factor_key: str
    value: float | None
    basis: str
    estimate_label: str | None = None

    def __post_init__(self) -> None: ...  # value in [0,1] or None; basis non-empty

    @property
    def is_unknown(self) -> bool:
        return self.value is None

    @property
    def zero_classification(self) -> ZeroClassification | None:
        """``UNKNOWN`` for ``None``, ``MEASURED_ZERO`` for ``0.0``, else ``None``."""
```

File: `factors/topic_relevance.py` (Task 1)

```python
TOPIC_RELEVANCE_FORMULA_VERSION: Final[str] = "1.0.0"
REQUIRED_TOPIC_SUBWEIGHT: Final[float] = 0.75
PREFERRED_TOPIC_SUBWEIGHT: Final[float] = 0.25


@dataclass(frozen=True, slots=True)
class TopicRelevanceInputs:
    expertise_topics: tuple[str, ...] | None  # None == no record == unknown
    required_topics: tuple[str, ...]
    preferred_topics: tuple[str, ...] = ()


def score_topic_relevance(inputs: TopicRelevanceInputs) -> FactorScore: ...
```

File: `factors/travel_burden.py` (Task 2)

```python
TRAVEL_BURDEN_FORMULA_VERSION: Final[str] = "1.0.0-straight-line"
TRAVEL_ESTIMATE_LABEL: Final[str] = "coarse straight-line estimate; D3 route matrix deferred"
FREE_RADIUS_KM: Final[float] = 16.0
MAX_BURDEN_KM: Final[float] = 160.0
EARTH_RADIUS_KM: Final[float] = 6371.0088


@dataclass(frozen=True, slots=True)
class GeoPoint:
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class TravelInputs:
    origin: GeoPoint | None  # professional's synthetic coordinates
    destination: GeoPoint | None  # event_need's synthetic coordinates


def haversine_km(origin: GeoPoint, destination: GeoPoint) -> float: ...
def score_travel_burden(inputs: TravelInputs) -> FactorScore: ...
```

File: `eligibility.py` (Task 3)

```python
class AvailabilityState(StrEnum):
    AVAILABLE = "available"
    BLACKED_OUT = "blacked_out"
    UNKNOWN = "unknown"


class EligibilityOutcome(StrEnum):
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class AvailabilityEvidence:
    subject_id: str
    state: AvailabilityState


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    subject_id: str
    outcome: EligibilityOutcome
    reason: str


def apply_availability_filter(
    shortlist: tuple[str, ...],
    evidence: Mapping[str, AvailabilityEvidence],
) -> tuple[EligibilityDecision, ...]: ...
```

File: `match_depth.py` (Task 3)

```python
@dataclass(frozen=True, slots=True)
class EngagementHistoryEvidence:
    subject_id: str
    unit_id: str
    engagement_ids: tuple[str, ...] | None  # None == absent record == unknown


@dataclass(frozen=True, slots=True)
class MatchDepth:
    subject_id: str
    unit_id: str
    count: int | None  # None == unknown
    basis: str

    @property
    def zero_classification(self) -> ZeroClassification | None: ...


def derive_match_depth(evidence: EngagementHistoryEvidence) -> MatchDepth: ...
```

Task 4 consumes exactly these names and adds
`python/smartmatch_domain/smartmatch_domain/scoring.py` on top of them.
Task 5 consumes `scoring.StageBScore.value` only.

---

## Task 1 (M2) — `topic_relevance` factor + shared factor types

### Fence

May create/modify **only**:

- `python/smartmatch_domain/smartmatch_domain/factors/__init__.py` (new)
- `python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py` (new)
- `tests/unit/test_topic_relevance.py` (new)

Must NOT touch `factor_registry.py`, `tests/unit/test_factor_registry.py`, any
other factor module, `eli.py`, `services/`, `apps/`, or anything under
`tests/golden/`.

### Work

Create the shared `factors` package exactly as pinned in the Cross-card interface
contract above: `FACTOR_SCORE_PRECISION = 4`, `ZeroClassification`,
`EvidenceState`, `FactorScore` with fields
`factor_key: str`, `value: float | None`, `basis: str`,
`estimate_label: str | None = None`, and the two properties `is_unknown` and
`zero_classification`. `__post_init__` raises `ValueError` when `value` is not
`None` and not in `[0.0, 1.0]`, and when `basis` is empty or whitespace.

Create `factors/topic_relevance.py`:

Constants (each with a `#:` comment):
- `TOPIC_RELEVANCE_FORMULA_VERSION: Final[str] = "1.0.0"`
- `REQUIRED_TOPIC_SUBWEIGHT: Final[float] = 0.75`
- `PREFERRED_TOPIC_SUBWEIGHT: Final[float] = 0.25`

`TopicRelevanceInputs` dataclass with fields, in order:
`expertise_topics: tuple[str, ...] | None`, `required_topics: tuple[str, ...]`,
`preferred_topics: tuple[str, ...] = ()`.
`__post_init__` raises `ValueError` if any topic string is empty/whitespace.

Topic canonicalization (private helper `_canonical(topic: str) -> str`):
`topic.strip().lower()`. Comparison is over `frozenset` of canonical forms, so
duplicates and case differences cannot change the answer.

`score_topic_relevance(inputs: TopicRelevanceInputs) -> FactorScore`, in this
exact decision order:

1. `inputs.expertise_topics is None` → return `FactorScore("topic_relevance",
   None, basis="no expertise record for this professional")`. **Unknown, not 0.0.**
2. `inputs.required_topics == () and inputs.preferred_topics == ()` → return
   `FactorScore("topic_relevance", None, basis="event_need declares no topics")`.
   Nothing to measure against is unknown, not zero.
3. Otherwise, with `E`, `R`, `P` the canonical frozensets:
   - `required_coverage = len(E & R) / len(R)` when `R` is non-empty, else `None`
   - `preferred_coverage = len(E & P) / len(P)` when `P` is non-empty, else `None`
   - both defined → `value = 0.75 * required_coverage + 0.25 * preferred_coverage`
   - only `required_coverage` defined → `value = required_coverage`
   - only `preferred_coverage` defined → `value = preferred_coverage`
   - `value = round(value, FACTOR_SCORE_PRECISION)`
   - basis: `f"{len(E & R)}/{len(R)} required, {len(E & P)}/{len(P)} preferred topics matched"`
     (omit the half that does not apply).
   - `estimate_label` stays `None` — this is a measured quantity, not an estimate.

An empty recorded expertise tuple `()` is `RECORDED`, therefore falls to branch 3
and yields `0.0` (`measured_zero`) — a professional with a topic record and no
overlap is verifiably irrelevant, which is different from having no record.

**Justification for 0.75 / 0.25** (put this in the module docstring): the
`event_need` distinguishes required from preferred topics, so the factor must
too, or a candidate covering only nice-to-haves would score as well as one
covering the must-haves. 3:1 makes full required coverage dominate any amount of
preferred coverage (0.75 > 0.25) while still separating two candidates that both
cover the requirements. These are **intra-factor sub-weights and are not registry
weights** — F-25 normalize-on-apply governs the Stage B weights (0.70 / 0.30)
only, and this factor never sees them.

### Tests — `tests/unit/test_topic_relevance.py`

House style of `tests/unit/test_eli.py`: module docstring, `from __future__ import
annotations`, small builder helper, one behaviour per test.

Required behaviours:

1. `test_absent_expertise_record_is_unknown_not_zero` — `expertise_topics=None`,
   `required_topics=("artificial_intelligence",)` → `result.value is None`,
   `result.is_unknown is True`,
   `result.zero_classification is ZeroClassification.UNKNOWN`.
2. `test_recorded_disjoint_topics_are_measured_zero` —
   `expertise_topics=("municipal_finance", "public_procurement")`,
   `required_topics=("artificial_intelligence",)`,
   `preferred_topics=("machine_learning",)` →
   `result.value == pytest.approx(0.0)`,
   `result.zero_classification is ZeroClassification.MEASURED_ZERO`.
   (1 and 2 together are the mandatory unknown-vs-zero pair.)
3. `test_recorded_empty_expertise_is_measured_zero` — `expertise_topics=()` →
   value `0.0`, `MEASURED_ZERO`.
4. `test_full_required_and_preferred_coverage_scores_one` —
   `("artificial_intelligence", "machine_learning")` against
   required `("artificial_intelligence",)` / preferred `("machine_learning",)`
   → `pytest.approx(1.0)`.
5. `test_required_only_coverage_scores_the_required_subweight` — expertise covers
   required but not preferred → `pytest.approx(0.75)`.
6. `test_preferred_only_coverage_scores_the_preferred_subweight` — expertise
   covers preferred but not required → `pytest.approx(0.25)`.
7. `test_partial_required_coverage_is_proportional` — required
   `("a", "b")`, expertise `("a",)`, no preferred → `pytest.approx(0.5)`.
8. `test_event_with_no_topics_is_unknown` — required `()` and preferred `()`,
   expertise recorded → `value is None`, `UNKNOWN`.
9. `test_no_required_topics_falls_back_to_preferred_only` — required `()`,
   preferred `("machine_learning",)`, expertise `("machine_learning",)` →
   `pytest.approx(1.0)`.
10. `test_topic_matching_is_case_and_whitespace_insensitive` —
    `("  Artificial_Intelligence ",)` vs `("artificial_intelligence",)` →
    `pytest.approx(1.0)`.
11. `test_duplicate_topics_do_not_change_the_score` — duplicated entries produce
    the same value as the deduplicated inputs.
12. `test_subweights_sum_to_one` —
    `REQUIRED_TOPIC_SUBWEIGHT + PREFERRED_TOPIC_SUBWEIGHT == pytest.approx(1.0)`.
13. `test_value_is_always_within_bounds` — a spread of inputs, every result is
    `None` or within `[0.0, 1.0]`.
14. `test_blank_topic_string_is_rejected` — `pytest.raises(ValueError)`.
15. `test_factor_key_is_declared_in_the_registry` —
    `"topic_relevance" in factor_keys()` (import from
    `smartmatch_domain.factor_registry`; read only).
16. `test_factor_score_rejects_out_of_range_value` and
    `test_factor_score_rejects_empty_basis` — `pytest.raises(ValueError)`.
17. `test_factor_score_zero_classification_is_none_for_a_positive_value`.

Do **not** write any line matching `score = <number>` at end of line (see §0.6).

### Verification commands

```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-match-engine
.venv/bin/python -m pytest tests/unit/test_topic_relevance.py -q
.venv/bin/ruff format --check python/smartmatch_domain/smartmatch_domain/factors tests/unit/test_topic_relevance.py
.venv/bin/ruff check python/smartmatch_domain/smartmatch_domain/factors tests/unit/test_topic_relevance.py
.venv/bin/mypy python/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
```

### Done when

- [ ] Exactly three files created; `git status --porcelain` shows no others.
- [ ] All 17 tests pass; `.venv/bin/python -m pytest tests/unit -q` is green.
- [ ] `ruff format --check`, `ruff check`, `mypy python/`, `lint-imports`, and
      `tools/scan_forbidden.py` all exit 0.
- [ ] `factors/__init__.py` exports exactly `FACTOR_SCORE_PRECISION`,
      `EvidenceState`, `FactorScore`, `ZeroClassification`.
- [ ] `score_topic_relevance` returns `None` for absent expertise and `0.0` for
      recorded-disjoint expertise, proven by tests 1 and 2.
- [ ] `factor_registry.py` and `tests/unit/test_factor_registry.py` are unmodified.

---

## Task 2 (M4) — `travel_burden` factor

### Fence

May create/modify **only**:

- `python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py` (new)
- `tests/unit/test_travel_burden.py` (new)

Must NOT touch `factors/__init__.py` (Task 1 owns it — import from it),
`factor_registry.py`, `tests/unit/test_factor_registry.py`, `eli.py`, `services/`,
`apps/`, or anything under `tests/golden/`.

### Work

Module docstring must state, explicitly: the value is a **coarse straight-line
estimate**; the D3 route-matrix provider is **deferred pending procurement**
(`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` §3);
this module **never** calls a network, a provider, or a route-matrix API, and
**never fabricates mileage** — absent coordinates yield unknown, not a guess.
Coordinates are synthetic pilot data.

Constants (each with a `#:` comment):

- `TRAVEL_BURDEN_FORMULA_VERSION: Final[str] = "1.0.0-straight-line"`
- `TRAVEL_ESTIMATE_LABEL: Final[str] = "coarse straight-line estimate; D3 route matrix deferred"`
- `EARTH_RADIUS_KM: Final[float] = 6371.0088`  (IUGG mean Earth radius)
- `FREE_RADIUS_KM: Final[float] = 16.0`  (≈10 miles — local travel, no burden)
- `MAX_BURDEN_KM: Final[float] = 160.0`  (≈100 miles — burden saturates at 1.0)

`GeoPoint(latitude: float, longitude: float)` — `__post_init__` raises
`ValueError` when latitude is outside `[-90.0, 90.0]` or longitude outside
`[-180.0, 180.0]`.

`TravelInputs(origin: GeoPoint | None, destination: GeoPoint | None)`.

`haversine_km(origin: GeoPoint, destination: GeoPoint) -> float` — standard
haversine using `math.radians`, `math.sin`, `math.cos`, `math.asin`, `math.sqrt`
and `EARTH_RADIUS_KM`. Pure `math` only; no third-party library.

`score_travel_burden(inputs: TravelInputs) -> FactorScore` — the returned `value`
is the **burden magnitude**, where `0.0` means no burden and `1.0` means maximum
burden. (`travel_burden` is registered as `FactorKind.PENALTY`; Stage B subtracts
it — see Task 4 for the exact composition.)

Decision order:

1. `inputs.origin is None or inputs.destination is None` → return
   `FactorScore("travel_burden", None,
   basis="professional or event_need coordinates are absent",
   estimate_label=TRAVEL_ESTIMATE_LABEL)`. **Unknown, never 0.0, never a guessed
   distance.**
2. Otherwise `distance = haversine_km(origin, destination)` and:
   - `distance <= FREE_RADIUS_KM` → `burden = 0.0`
   - `distance >= MAX_BURDEN_KM` → `burden = 1.0` (clamped; long distance is a
     penalty, **not** a Stage A exclusion)
   - otherwise `burden = (distance - FREE_RADIUS_KM) / (MAX_BURDEN_KM - FREE_RADIUS_KM)`
   - `value = round(burden, FACTOR_SCORE_PRECISION)` (4 dp)
   - `basis = f"{distance:.1f} km straight-line between synthetic coordinates"`
   - `estimate_label = TRAVEL_ESTIMATE_LABEL` **always** when a value is produced.

Bound: `value ∈ [0.0, 1.0]`, monotonically non-decreasing in distance.

Mapping in words, for the card's reviewer: 0 km through 16 km → 0.0; 16 km
through 160 km → linear 0.0 → 1.0 (so 88 km → 0.5); 160 km and beyond → 1.0.

### Tests — `tests/unit/test_travel_burden.py`

1. `test_absent_origin_is_unknown_not_zero` — `origin=None`, destination set →
   `value is None`, `zero_classification is ZeroClassification.UNKNOWN`.
2. `test_absent_destination_is_unknown_not_zero` — mirror of 1.
3. `test_identical_coordinates_are_measured_zero_burden` — origin ==
   destination == `GeoPoint(34.0522, -118.2437)` →
   `value == pytest.approx(0.0)`,
   `zero_classification is ZeroClassification.MEASURED_ZERO`.
   (1/2 and 3 are the mandatory unknown-vs-zero pair.)
4. `test_inside_the_free_radius_is_zero_burden` — 0.1° of latitude apart
   (≈11.1 km) → `pytest.approx(0.0)`.
5. `test_haversine_matches_a_known_separation` — one degree of latitude at the
   same longitude is ≈111.19 km:
   `haversine_km(GeoPoint(0.0, 0.0), GeoPoint(1.0, 0.0)) == pytest.approx(111.19, abs=0.05)`.
6. `test_haversine_is_symmetric` — `haversine_km(a, b) == pytest.approx(haversine_km(b, a))`.
7. `test_haversine_of_a_point_with_itself_is_zero`.
8. `test_burden_saturates_at_one_beyond_the_maximum` — points > 160 km apart →
   `pytest.approx(1.0)`; a far-further pair returns the same `1.0`.
9. `test_burden_is_monotonic_in_distance` — a strictly increasing sequence of
   separations yields a non-decreasing sequence of values.
10. `test_midpoint_of_the_band_is_half_burden` — construct a pair at ≈88 km
    (0.7912° of latitude) and assert `pytest.approx(0.5, abs=0.01)`.
11. `test_value_is_always_within_bounds` — over a spread of inputs, every result
    is `None` or within `[0.0, 1.0]`.
12. `test_every_produced_value_carries_the_coarse_estimate_label` —
    `result.estimate_label == TRAVEL_ESTIMATE_LABEL` for both the known and the
    unknown branch.
13. `test_out_of_range_latitude_is_rejected` and
    `test_out_of_range_longitude_is_rejected` — `pytest.raises(ValueError)`.
14. `test_module_imports_no_network_or_io` — parse the module source with `ast`
    and assert the set of top-level imported module roots is a subset of
    `{"__future__", "math", "dataclasses", "typing", "smartmatch_domain"}`.
    This is the executable form of the no-network rule.
15. `test_factor_key_is_declared_in_the_registry` — `"travel_burden" in factor_keys()`.
16. `test_formula_version_is_pinned` —
    `TRAVEL_BURDEN_FORMULA_VERSION == "1.0.0-straight-line"`.

Do **not** write any line matching `score = <number>` at end of line (see §0.6).

### Verification commands

```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-match-engine
.venv/bin/python -m pytest tests/unit/test_travel_burden.py -q
.venv/bin/ruff format --check python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py tests/unit/test_travel_burden.py
.venv/bin/ruff check python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py tests/unit/test_travel_burden.py
.venv/bin/mypy python/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
```

### Done when

- [ ] Exactly two files created; `git status --porcelain` shows no others.
- [ ] All 16 tests pass; `.venv/bin/python -m pytest tests/unit -q` is green.
- [ ] `ruff format --check`, `ruff check`, `mypy python/`, `lint-imports`, and
      `tools/scan_forbidden.py` all exit 0.
- [ ] Absent coordinates return `None`; identical coordinates return `0.0`.
- [ ] Every produced `FactorScore` carries `TRAVEL_ESTIMATE_LABEL`.
- [ ] No network, provider, or route-matrix import anywhere in the module, proven
      by test 14.
- [ ] `factors/__init__.py`, `factor_registry.py` and
      `tests/unit/test_factor_registry.py` are unmodified.

---

## Task 3 (M6) — Stage A `availability` filter + derived `match_depth`

### Fence

May create/modify **only**:

- `python/smartmatch_domain/smartmatch_domain/eligibility.py` (new)
- `python/smartmatch_domain/smartmatch_domain/match_depth.py` (new)
- `tests/unit/test_eligibility.py` (new)
- `tests/unit/test_match_depth.py` (new)

Must NOT touch `factors/__init__.py` (Task 1 owns it — import `ZeroClassification`
from it), `factor_registry.py`, `tests/unit/test_factor_registry.py`, `eli.py`,
`services/`, `apps/`, or anything under `tests/golden/`.

These are two separate modules on purpose: eligibility is a Stage A gate, and
match depth is a coordinator-facing display quantity. Putting them in one file
would suggest depth participates in filtering. It does not.

### Work — `eligibility.py`

Module docstring must state: `availability` is a **Stage A eligibility** factor
with **weight 0**; per ratified program direction it is applied **after** the
Stage B shortlist (match first, then availability; the coordinator batch-invites),
and it **never enters the Stage B score**. Also: an unknown availability record
is neither an exclusion nor a pass — it is `UNDETERMINED`, because silently
excluding an unknown discards a candidate on missing evidence and silently
including one asserts a fact the data does not carry (ADR-0011).

- `AvailabilityState(StrEnum)`: `AVAILABLE = "available"`,
  `BLACKED_OUT = "blacked_out"`, `UNKNOWN = "unknown"`.
- `EligibilityOutcome(StrEnum)`: `ELIGIBLE = "eligible"`,
  `EXCLUDED = "excluded"`, `UNDETERMINED = "undetermined"`.
- `AvailabilityEvidence(subject_id: str, state: AvailabilityState)` — frozen,
  slotted; `__post_init__` rejects a blank `subject_id`.
- `EligibilityDecision(subject_id: str, outcome: EligibilityOutcome, reason: str)`
  — frozen, slotted; `__post_init__` rejects a blank `reason`.
- `apply_availability_filter(shortlist: tuple[str, ...],
  evidence: Mapping[str, AvailabilityEvidence]) -> tuple[EligibilityDecision, ...]`

  Mapping is keyed by `subject_id`. Rules:
  - state `AVAILABLE` → `ELIGIBLE`, reason `"availability recorded as available"`
  - state `BLACKED_OUT` → `EXCLUDED`, reason `"availability recorded as blacked out"`
  - state `UNKNOWN` → `UNDETERMINED`, reason `"availability record is unknown"`
  - `subject_id` absent from `evidence` → `UNDETERMINED`, reason
    `"no availability record for this subject"`
  - **Shortlist order is preserved exactly** — the filter never reorders, because
    the Stage B ranking (including the `subject_id` tie-break) already fixed it.
  - A `subject_id` appearing twice in the shortlist raises `ValueError`.
  - Evidence keys not present in the shortlist are ignored silently — Stage A runs
    only over the shortlist.
- Add a module-level `AVAILABILITY_STAGE_B_WEIGHT: Final[float] = 0.0` with a `#:`
  comment recording that this is fixed by the ratified registry and is not a
  tunable.

### Work — `match_depth.py`

Module docstring must state, in these words or closer: **`match_depth` is a
derived display quantity computed from engagement history. It is NOT a registry
factor, carries no weight, and must never be added to `PROPOSED_FACTORS`.** Cite
that `G1-GC-003`, `G1-GC-007` and `G1-GC-008` exercise it as a derived quantity,
not as a scorer.

- `EngagementHistoryEvidence(subject_id: str, unit_id: str,
  engagement_ids: tuple[str, ...] | None)` — frozen, slotted;
  `__post_init__` rejects blank `subject_id` / `unit_id`.
- `MatchDepth(subject_id: str, unit_id: str, count: int | None, basis: str)` —
  frozen, slotted, with:
  - `zero_classification` property → `ZeroClassification.UNKNOWN` when
    `count is None`, `ZeroClassification.MEASURED_ZERO` when `count == 0`,
    otherwise `None`.
  - `is_unknown` property → `count is None`.
  - `__post_init__` rejects a negative `count` and a blank `basis`.
- `derive_match_depth(evidence: EngagementHistoryEvidence) -> MatchDepth`:
  - `engagement_ids is None` → `count=None`,
    `basis="no engagement history record for this subject and unit"` → **unknown**
  - `engagement_ids == ()` → `count=0`,
    `basis="engagement history recorded and empty for this unit"` → **measured zero**
  - otherwise `count=len(engagement_ids)` with duplicates rejected
    (`ValueError` on a repeated engagement id), `basis=f"{count} recorded engagements with this unit"`.

### Tests — `tests/unit/test_eligibility.py`

1. `test_available_subject_is_eligible`
2. `test_blacked_out_subject_is_excluded`
3. `test_unknown_availability_is_undetermined_not_excluded` — the ADR-0011 pair
   partner: an unknown record must not silently drop the candidate.
4. `test_missing_availability_record_is_undetermined_not_excluded`
5. `test_recorded_blackout_and_missing_record_are_distinguishable` — the explicit
   unknown-vs-measured pair: `BLACKED_OUT` → `EXCLUDED`, absent → `UNDETERMINED`,
   and the two `reason` strings differ.
6. `test_shortlist_order_is_preserved` — decisions come back in shortlist order
   regardless of evidence-mapping order.
7. `test_evidence_for_subjects_outside_the_shortlist_is_ignored`
8. `test_duplicate_subject_in_shortlist_is_rejected` — `pytest.raises(ValueError)`
9. `test_empty_shortlist_returns_empty_tuple`
10. `test_availability_carries_no_stage_b_weight` —
    `AVAILABILITY_STAGE_B_WEIGHT == 0.0`, and the registry spec for
    `"availability"` has `kind is FactorKind.ELIGIBILITY`, `is_scoring is False`,
    `active_weight == 0.0` (import read-only from
    `smartmatch_domain.factor_registry`).
11. `test_availability_is_not_in_the_normalized_stage_b_weights` —
    `"availability" not in normalize_weights()`.
12. `test_blank_subject_id_is_rejected` and `test_blank_reason_is_rejected`.

### Tests — `tests/unit/test_match_depth.py`

1. `test_absent_history_is_unknown_not_zero` — `engagement_ids=None` →
   `count is None`, `zero_classification is ZeroClassification.UNKNOWN`.
   (This is `G1-GC-007`.)
2. `test_recorded_empty_history_is_measured_zero` — `engagement_ids=()` →
   `count == 0`, `zero_classification is ZeroClassification.MEASURED_ZERO`.
   (This is `G1-GC-008`, and with 1 it is the mandatory unknown-vs-zero pair.)
3. `test_recorded_history_counts_engagements` — three ids → `count == 3`,
   `zero_classification is None`.
4. `test_duplicate_engagement_id_is_rejected` — `pytest.raises(ValueError)`.
5. `test_negative_count_is_rejected` — constructing `MatchDepth` with `count=-1`
   raises `ValueError`.
6. `test_match_depth_is_not_a_registry_factor` —
   `"match_depth" not in factor_keys()` and
   `"match_depth" not in proposed_weights()` (import read-only from
   `smartmatch_domain.factor_registry`).
7. `test_absent_and_empty_history_have_different_bases` — the two `basis` strings
   differ, so a coordinator-facing explanation can tell them apart.
8. `test_blank_subject_or_unit_id_is_rejected`.

### Verification commands

```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-match-engine
.venv/bin/python -m pytest tests/unit/test_eligibility.py tests/unit/test_match_depth.py -q
.venv/bin/ruff format --check python/smartmatch_domain/smartmatch_domain/eligibility.py python/smartmatch_domain/smartmatch_domain/match_depth.py tests/unit/test_eligibility.py tests/unit/test_match_depth.py
.venv/bin/ruff check python/smartmatch_domain/smartmatch_domain/eligibility.py python/smartmatch_domain/smartmatch_domain/match_depth.py tests/unit/test_eligibility.py tests/unit/test_match_depth.py
.venv/bin/mypy python/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
```

### Done when

- [ ] Exactly four files created; `git status --porcelain` shows no others.
- [ ] All 20 tests pass; `.venv/bin/python -m pytest tests/unit -q` is green.
- [ ] `ruff format --check`, `ruff check`, `mypy python/`, `lint-imports`, and
      `tools/scan_forbidden.py` all exit 0.
- [ ] Absent availability is `UNDETERMINED`, not `EXCLUDED`; absent history is
      `count=None`, not `0`.
- [ ] `match_depth` appears nowhere in `factor_registry.py`, proven by test 6.
- [ ] `factors/__init__.py`, `factor_registry.py` and
      `tests/unit/test_factor_registry.py` are unmodified.

---

## Task 4 (M6j) — registry wiring, Stage B scoring entry point, approved golden cases

**Prerequisite:** Tasks 1, 2 and 3 are complete and green.

### Fence

May create/modify **only**:

- `python/smartmatch_domain/smartmatch_domain/factor_registry.py` (modify — **sole owner**)
- `tests/unit/test_factor_registry.py` (modify — **sole owner**)
- `python/smartmatch_domain/smartmatch_domain/scoring.py` (new)
- `tests/unit/test_scoring.py` (new)
- `tests/golden/matching/approved/approved_case.schema.json` (new)
- `tests/golden/matching/approved/G1-GC-002-topic-relevance-measured-zero.json` (new)
- `tests/golden/matching/approved/G1-GC-003-match-depth-measured-zero.json` (new)
- `tests/golden/matching/approved/G1-GC-004-tie-break-subject-id.json` (new)
- `tests/golden/matching/approved/G1-GC-005-topic-relevance-unknown-absent-topics.json` (new)
- `tests/golden/matching/approved/G1-GC-006-topic-relevance-measured-zero-disjoint.json` (new)
- `tests/golden/matching/approved/G1-GC-007-match-depth-unknown-absent-history.json` (new)
- `tests/golden/matching/approved/G1-GC-008-match-depth-measured-zero-empty-history.json` (new)
- `tests/unit/test_matching_approved_golden.py` (new)
- `docs/decisions/pilot-decisions.md` (modify — **one line only**, the
  `REGISTRY_VERSION` cell in the D1 table around line 108)

Must NOT touch: `tests/golden/matching/symptoms/**`,
`tests/golden/matching/golden_case.schema.json`,
`tests/unit/test_matching_golden_case_schema.py`,
`tests/unit/test_matching_fail_closed.py`, `eli.py`, `services/`, `apps/`, the
factor modules from Tasks 1–3, or `contracts/openapi/smartmatch.json`.

### Work — 4a. `factor_registry.py`

1. Flip `implemented=False` → `implemented=True` on the `topic_relevance` and
   `travel_burden` `FactorSpec` entries. **`availability` stays
   `implemented=False`** — it is `ELIGIBILITY`, weight 0, and never scored.
2. **Do not change `REGISTRY_STATUS`.** It is already `"approved"` on main and
   `assert_registry_approved()` already passes. Leave both alone.
3. Bump `REGISTRY_VERSION` from `"1.1.0-approved-g1"` to
   `"1.1.1-approved-g1-m6j"`, with a `#:` comment recording that the implemented
   scoring set changed and therefore stored `match_run` version pins must
   distinguish the two. Update the one matching cell in
   `docs/decisions/pilot-decisions.md` in the same commit so the doc and the code
   do not drift.
4. Add, exported through `__all__` (keep `__all__` sorted):

```python
#: The Stage B scoring factors gate G1 approved on 2026-09-03. The readiness
#: assertion below requires the implemented set to equal this set exactly —
#: neither a missing implementation nor an extra one is acceptable.
APPROVED_SCORING_KEYS: Final[frozenset[str]] = frozenset({"topic_relevance", "travel_burden"})


class RegistryNotReadyError(RuntimeError):
    """Raised when the implemented scoring set is not the approved scoring set."""


def implemented_scoring_keys() -> frozenset[str]:
    """Return the keys of every implemented Stage B scoring factor."""


def assert_scoring_ready() -> None:
    """Fail closed unless the implemented scoring set is exactly the approved set.

    ``assert_registry_approved`` proves the program owner signed off. This proves
    the code actually built what was signed off — the window this closes is an
    "approved" registry scoring with only a subset of the approved factors, which
    is the legacy deflation defect in a new costume.

    Raises:
        RegistryNotReadyError: when the implemented scoring set differs from
            ``APPROVED_SCORING_KEYS``, or when the normalized weights do not sum
            to 1.0 within 1e-9.
    """
```

`assert_scoring_ready` must (a) compare `implemented_scoring_keys()` against
`APPROVED_SCORING_KEYS` and name the missing and the extra keys in the message,
and (b) assert `abs(sum(normalize_weights().values()) - 1.0) <= 1e-9`.

### Work — 4b. Deliberate guard-test updates in `tests/unit/test_factor_registry.py`

These five tests encode the pre-M6j state and **must be updated deliberately in
this card's commit**. Do not delete them; convert them.

1. `test_active_weights_empty_until_m2_implements_scoring_factors` →
   rename to `test_active_weights_are_the_approved_scoring_set_after_m6j`.
   New body: `active_weights()` has exactly the keys
   `{"topic_relevance", "travel_burden"}` with values `pytest.approx(0.70)` and
   `pytest.approx(0.30)`; `proposed_weights()` still has all three keys and
   `proposed_weights()["availability"] == 0.0`.
2. `test_only_one_scoring_factor_is_implemented_today` →
   rename to `test_both_approved_scoring_factors_are_implemented`.
   New body: `set(normalize_weights()) == {"topic_relevance", "travel_burden"}`;
   values `pytest.approx(0.70)` / `pytest.approx(0.30)`; sum
   `pytest.approx(1.0)`.
3. `test_normalize_weights_ignores_unknown_and_unimplemented_keys` — keep the
   name. New body: `normalize_weights({"not_a_factor": 5.0, "availability": 5.0})`
   → `"not_a_factor" not in weights`, `"availability" not in weights`,
   `set(weights) == {"topic_relevance", "travel_burden"}`, and the result equals
   `normalize_weights()` (an unknown override injects no mass).
4. `test_normalize_weights_all_zero_returns_zeros_not_nan` — keep the name.
   New body: `normalize_weights({"topic_relevance": 0.0, "travel_burden": 0.0})`
   → `{"topic_relevance": 0.0, "travel_burden": 0.0}`; assert every value is
   `0.0` and that no value is NaN (`value == value`).
5. `test_normalize_weights_honours_overrides_and_renormalizes` — **remove the
   `pytest.skip`**; it now runs with two implemented factors. Add
   `assert sum(bumped.values()) == pytest.approx(1.0)`.

Also in the same file:

6. `test_implemented_scoring_weights_sum_to_one` — **delete the
   `if not weights: return` early-out** so the test actually asserts the sum.
7. Add `test_assert_scoring_ready_passes` — `assert_scoring_ready()` returns
   without raising.
8. Add `test_registry_version_is_pinned` —
   `REGISTRY_VERSION == "1.1.1-approved-g1-m6j"`.
9. Add `test_availability_remains_unimplemented_and_unscored` — the
   `"availability"` spec has `implemented is False`, `is_scoring is False`,
   `active_weight == 0.0`.
10. Add `test_no_dropped_factor_reappeared` — none of
    `{"role_fit", "engagement_load", "repeat_penalty", "credential_check",
    "contact_status", "declared_cap", "historical_conversion",
    "student_interest", "match_depth"}` is in `factor_keys()`.

Leave every other test in the file unchanged, including
`test_registry_is_approved_after_g1`.

### Work — 4c. `scoring.py` — the Stage B entry point

Module docstring cites architecture v1.1 §1.2 Stage B, F-25 normalize-on-apply
(`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` §5), and
ADR-0011. It must state that the legacy engine is never characterized and no
legacy score value is asserted anywhere.

```python
STAGE_B_FORMULA_VERSION: Final[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    subject_id: str
    topic: TopicRelevanceInputs
    travel: TravelInputs


@dataclass(frozen=True, slots=True)
class StageBScore:
    subject_id: str
    value: float | None
    factor_scores: tuple[FactorScore, ...]
    applied_weights: Mapping[str, float]
    unknown_factor_keys: tuple[str, ...]
    registry_version: str
    formula_version: str


def score_candidate(
    evidence: CandidateEvidence,
    *,
    weight_overrides: Mapping[str, float] | None = None,
) -> StageBScore: ...


def rank_candidates(
    candidates: Sequence[CandidateEvidence],
    *,
    weight_overrides: Mapping[str, float] | None = None,
) -> tuple[StageBScore, ...]: ...
```

`score_candidate` behaviour, in this exact order:

1. Call `assert_registry_approved()`. Then call `assert_scoring_ready()`. Both
   before touching any evidence.
2. `applied_weights = normalize_weights(weight_overrides)` — **normalize on
   apply**, computed, never hand-tuned. With no overrides this is
   `{"topic_relevance": 0.70, "travel_burden": 0.30}`.
3. Compute `score_topic_relevance(evidence.topic)` and
   `score_travel_burden(evidence.travel)`. Store both in `factor_scores` in
   registry order (`factor_keys()` order), **including the unknown ones** —
   the explanation layer needs to see that a factor was unknown.
4. `unknown_factor_keys` = the keys whose `FactorScore.value is None`, in registry
   order.
5. **If `unknown_factor_keys` is non-empty, `value` is `None`.** An unknown
   factor makes the composite score unknown; it is never dropped, never
   substituted with `0.0`, and the weights are never re-spread over the known
   subset. Re-spreading would let a candidate with no evidence outrank one with
   real evidence, which is the ADR-0011 defect in aggregate form. Presentation of
   partial evidence is M9/M10's problem, not this function's.
6. Otherwise compose:

```
contribution(key, v) = v          when the registry kind is FactorKind.SUITABILITY
                       (1.0 - v)  when the registry kind is FactorKind.PENALTY
value = round(sum(applied_weights[key] * contribution(key, v) for each factor), 6)
```

   Document why the penalty enters as its complement: subtracting the penalty
   directly would put the composite in `[-0.30, 0.70]`, which is not a score. The
   complement form is an affine reparameterization — it adds the constant
   `sum(weights over penalty factors)` and preserves the ranking of every pair of
   candidates exactly — and keeps the composite in `[0.0, 1.0]` with weights that
   sum to 1.0. Assert the bound in tests.

7. `registry_version = REGISTRY_VERSION`, `formula_version = STAGE_B_FORMULA_VERSION`.

`rank_candidates`:

- Scores every candidate, then orders with the **ratified tie-break**:
  `sorted(scores, key=lambda s: (s.value is None, -(s.value or 0.0), s.subject_id))`.
  That is: known scores first (unknowns last, never treated as `0.0`), then
  descending `value`, then **lexicographic ascending `subject_id`**.
- Raises `ValueError` on a duplicate `subject_id`.
- Returns a tuple; never mutates the input.

### Work — 4d. Approved golden cases

Create `tests/golden/matching/approved/approved_case.schema.json`, a **new**
schema, independent of `golden_case.schema.json`:

- `$id`: `https://smartmatch.local/schemas/g1-approved-golden-case-v1.json`
- `title`: `"G1 approved golden case (with expected outputs)"`
- `type: "object"`, `additionalProperties: false`
- `required`: `["id", "symptom_class", "description", "inputs", "expected"]`
- `properties.id`: string, `pattern` `^G1-GC-[0-9]{3}$`
- `properties.symptom_class`: enum `["tie", "zero_or_unknown", "depth_zero"]`
- `properties.description`: string, `minLength` 1
- `properties.registry_version`: string
- `properties.stakeholder_reference`: string
- `properties.zero_classification`: enum `["measured_zero", "unknown"]`
- `properties.inputs`: object
- `properties.expected`: object — **required, and NOT forbidden** (this schema has
  no `"not": {}`; that is precisely why it is a separate file)
- Two `allOf` conditionals: when `symptom_class` is `zero_or_unknown` **or**
  `depth_zero`, `zero_classification` is `required`.

Fixture shape (all seven files). Coordinates are synthetic. Event coordinates are
`34.0522 / -118.2437` throughout.

```json
{
  "id": "G1-GC-00X",
  "symptom_class": "...",
  "description": "...",
  "registry_version": "1.1.1-approved-g1-m6j",
  "stakeholder_reference": "docs/plans/workshops/g1-workshop-output-worksheet.md agenda item 3 (RATIFIED 2026-09-03)",
  "zero_classification": "...",
  "inputs": { "...": "..." },
  "expected": { "...": "..." }
}
```

Every `description` must state that the fixture is **synthetic** and that **no
legacy engine output is asserted**.

**`G1-GC-002-topic-relevance-measured-zero.json`** — `symptom_class`
`"zero_or_unknown"`, `zero_classification` `"measured_zero"`.
inputs: `candidate.subject_id` `"SYNTH-PRO-0002A"`;
`expertise_topics` `["municipal_finance"]`;
`event_need.required_topics` `["artificial_intelligence"]`,
`preferred_topics` `[]`;
`professional.coordinates` `{"latitude": 34.0522, "longitude": -118.2437}`;
`event_need.coordinates` `{"latitude": 34.0522, "longitude": -118.2437}`.
expected:
```json
{
  "factor_scores": {
    "topic_relevance": {"value": 0.0, "zero_classification": "measured_zero"},
    "travel_burden": {"value": 0.0, "zero_classification": "measured_zero"}
  },
  "unknown_factor_keys": [],
  "stage_b_score": 0.3
}
```
(0.70 × 0.0 + 0.30 × (1.0 − 0.0) = 0.30.)

**`G1-GC-006-topic-relevance-measured-zero-disjoint.json`** — `"zero_or_unknown"`,
`"measured_zero"`. `subject_id` `"SYNTH-PRO-0006"`;
`expertise_topics` `["municipal_finance", "public_procurement"]`;
`required_topics` `["artificial_intelligence"]`,
`preferred_topics` `["machine_learning"]`; both coordinates
`34.0522 / -118.2437`. Same expected block as `G1-GC-002`
(`stage_b_score` `0.3`).

**`G1-GC-005-topic-relevance-unknown-absent-topics.json`** — `"zero_or_unknown"`,
`"unknown"`. `subject_id` `"SYNTH-PRO-0005"`; `expertise_topics` `null`;
`required_topics` `["artificial_intelligence"]`, `preferred_topics` `[]`;
both coordinates `34.0522 / -118.2437`.
expected:
```json
{
  "factor_scores": {
    "topic_relevance": {"value": null, "zero_classification": "unknown"},
    "travel_burden": {"value": 0.0, "zero_classification": "measured_zero"}
  },
  "unknown_factor_keys": ["topic_relevance"],
  "stage_b_score": null
}
```

**`G1-GC-004-tie-break-subject-id.json`** — `symptom_class` `"tie"`, **no**
`zero_classification`. Two candidates, `"SYNTH-PRO-0001"` and
`"SYNTH-PRO-0002"`, listed in the fixture in the **reverse** order
(`SYNTH-PRO-0002` first) so the test proves the tie-break sorts rather than
preserving input order. Both have `expertise_topics`
`["artificial_intelligence", "machine_learning"]` and coordinates
`{"latitude": 34.1522, "longitude": -118.2437}`.
`event_need`: `required_topics` `["artificial_intelligence"]`,
`preferred_topics` `["machine_learning"]`, coordinates
`{"latitude": 34.0522, "longitude": -118.2437}`
(0.1° of latitude ≈ 11.1 km, inside the 16 km free radius → burden exactly 0.0).
`description` must record: this reproduces the `G1-GC-001` exact-tie symptom by
**symmetry of inputs**; the legacy 43% value is deliberately **not** asserted.
expected:
```json
{
  "factor_scores": {
    "topic_relevance": {"value": 1.0, "zero_classification": null},
    "travel_burden": {"value": 0.0, "zero_classification": "measured_zero"}
  },
  "unknown_factor_keys": [],
  "stage_b_score": 1.0,
  "scores_are_equal": true,
  "ranking": ["SYNTH-PRO-0001", "SYNTH-PRO-0002"]
}
```

**`G1-GC-003-match-depth-measured-zero.json`** — `symptom_class` `"depth_zero"`,
`zero_classification` `"measured_zero"`. inputs: `subject_id`
`"SYNTH-PRO-0003"`, `unit_id` `"SYNTH-UNIT-0001"`, `engagement_ids` `[]`.
expected: `{"match_depth": {"count": 0, "zero_classification": "measured_zero"},
"match_depth_is_a_registry_factor": false}`.

**`G1-GC-007-match-depth-unknown-absent-history.json`** — `"depth_zero"`,
`"unknown"`. `subject_id` `"SYNTH-PRO-0007"`, `unit_id` `"SYNTH-UNIT-0001"`,
`engagement_ids` `null`.
expected: `{"match_depth": {"count": null, "zero_classification": "unknown"},
"match_depth_is_a_registry_factor": false}`.

**`G1-GC-008-match-depth-measured-zero-empty-history.json`** — `"depth_zero"`,
`"measured_zero"`. `subject_id` `"SYNTH-PRO-0008"`, `unit_id`
`"SYNTH-UNIT-0001"`, `engagement_ids` `[]`,
plus `"engagement_history_verified_through": "2026-09-01"`.
expected: same shape as `G1-GC-003`.

### Tests — `tests/unit/test_scoring.py`

1. `test_score_candidate_calls_the_registry_guards_first` — monkeypatch
   `smartmatch_domain.scoring.assert_registry_approved` and
   `assert_scoring_ready` with recorders; assert both were called and that they
   were called before any factor function.
2. `test_applied_weights_are_the_normalized_registry_weights` — with no
   overrides, `applied_weights == {"topic_relevance": pytest.approx(0.70),
   "travel_burden": pytest.approx(0.30)}` and the values sum to
   `pytest.approx(1.0)`.
3. `test_weights_are_normalized_on_apply_not_hardcoded` — passing
   `weight_overrides={"topic_relevance": 7.0, "travel_burden": 3.0}` yields the
   same normalized `{0.70, 0.30}`, proving normalization is computed.
4. `test_perfect_candidate_scores_one` — full topic coverage, identical
   coordinates → `pytest.approx(1.0)`.
5. `test_disjoint_topics_and_zero_distance_scores_the_penalty_weight` — →
   `pytest.approx(0.3)`.
6. `test_unknown_topic_relevance_makes_the_composite_unknown` —
   `expertise_topics=None` → `result.value is None`,
   `result.unknown_factor_keys == ("topic_relevance",)`.
7. `test_unknown_travel_makes_the_composite_unknown` — coordinates `None` →
   `value is None`, `unknown_factor_keys == ("travel_burden",)`.
8. `test_measured_zero_and_unknown_produce_different_composites` — the mandatory
   pair: recorded-disjoint topics give `pytest.approx(0.3)`; absent topics give
   `None`. They must not be equal.
9. `test_unknown_factors_are_still_reported_in_factor_scores` — `factor_scores`
   always has two entries, in `factor_keys()` order, even when one is unknown.
10. `test_composite_is_always_within_bounds` — over a spread of inputs, every
    non-`None` value is within `[0.0, 1.0]`.
11. `test_penalty_enters_as_its_complement` — two candidates identical except
    travel distance; the further one scores strictly lower.
12. `test_ranking_breaks_ties_lexicographically_by_subject_id` — two symmetric
    candidates supplied as `("SYNTH-PRO-0002", "SYNTH-PRO-0001")` rank as
    `("SYNTH-PRO-0001", "SYNTH-PRO-0002")`.
13. `test_ranking_orders_by_descending_value_before_the_tie_break`.
14. `test_unknown_candidates_rank_last_and_are_not_treated_as_zero` — a candidate
    with `value is None` sorts after one with `value == 0.0`.
15. `test_duplicate_subject_id_is_rejected` — `pytest.raises(ValueError)`.
16. `test_result_records_registry_and_formula_versions` —
    `registry_version == "1.1.1-approved-g1-m6j"`,
    `formula_version == STAGE_B_FORMULA_VERSION`.
17. `test_scoring_raises_when_the_registry_is_not_approved` — monkeypatch
    `REGISTRY_STATUS` (or the guard) so `assert_registry_approved` raises, and
    assert `score_candidate` propagates `RegistryNotApprovedError`.
18. `test_scoring_raises_when_an_approved_factor_is_unimplemented` — monkeypatch
    `implemented_scoring_keys` to return `frozenset({"topic_relevance"})` and
    assert `RegistryNotReadyError`.

### Tests — `tests/unit/test_matching_approved_golden.py`

Mark every test `@pytest.mark.golden`. Helper names must not be
`load_fixture(` — use `_load_case(` and `_case_paths()`.

1. `test_approved_schema_file_exists`.
2. `test_approved_schema_permits_expected_outputs` — the schema's
   `properties.expected` has **no** `"not"` key and `"expected"` is in
   `required`. (This is the structural proof that the approved directory is a
   different contract from the symptoms directory.)
3. `test_every_ratified_case_id_has_a_fixture` — the ids present are exactly
   `{"G1-GC-002", "G1-GC-003", "G1-GC-004", "G1-GC-005", "G1-GC-006",
   "G1-GC-007", "G1-GC-008"}`.
4. `test_approved_cases_have_required_shape` — parametrized over every file:
   `id` matches `^G1-GC-[0-9]{3}$`, `symptom_class` is in the enum,
   `description` non-empty, `inputs` and `expected` present, and for
   `zero_or_unknown` / `depth_zero` the `zero_classification` is present and in
   `{"measured_zero", "unknown"}`.
5. `test_zero_classifications_match_the_ratified_table` — assert exactly:
   `G1-GC-002` → `measured_zero`, `G1-GC-003` → `measured_zero`,
   `G1-GC-005` → `unknown`, `G1-GC-006` → `measured_zero`,
   `G1-GC-007` → `unknown`, `G1-GC-008` → `measured_zero`.
6. `test_stage_b_cases_reproduce_expected_scores` — parametrized over
   `G1-GC-002`, `G1-GC-005`, `G1-GC-006`: build `CandidateEvidence` from
   `inputs`, call `score_candidate`, compare `value` (`pytest.approx` with
   `abs=1e-6`, or `is None`), `unknown_factor_keys`, and each factor's `value`
   and `zero_classification` against `expected`.
7. `test_tie_case_reproduces_the_ratified_tie_break` — for `G1-GC-004`, feed the
   candidates in the fixture's (reversed) order to `rank_candidates`; assert the
   two composite values are equal, and that the returned order is
   `("SYNTH-PRO-0001", "SYNTH-PRO-0002")`.
8. `test_match_depth_cases_reproduce_expected_depth` — parametrized over
   `G1-GC-003`, `G1-GC-007`, `G1-GC-008`: call `derive_match_depth`, compare
   `count` and `zero_classification`.
9. `test_no_approved_fixture_asserts_a_legacy_score` — every file's serialized
   text contains neither `"43"` as a percentage nor the substring `"legacy"`
   inside `expected`; the search is over the `expected` subtree only.
10. `test_symptom_fixtures_are_untouched` — every file under
    `tests/golden/matching/symptoms/` still has `"expected" not in payload`, and
    `tests/golden/matching/golden_case.schema.json` still has `"not"` in
    `properties.expected`. This test is the executable proof that Task 4 left the
    draft directory alone.

### Verification commands

```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-match-engine
.venv/bin/python -m pytest tests/unit/test_factor_registry.py tests/unit/test_scoring.py tests/unit/test_matching_approved_golden.py -q
.venv/bin/python -m pytest tests/unit/test_matching_golden_case_schema.py tests/unit/test_matching_fail_closed.py -q
.venv/bin/python -m pytest tests/ -m "not integration" -q
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy python/ services/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
git status --porcelain
git diff --stat -- tests/golden/matching/symptoms tests/unit/test_matching_golden_case_schema.py tests/unit/test_matching_fail_closed.py
```

The last command must print **nothing**.

### Done when

- [ ] `topic_relevance` and `travel_burden` have `implemented=True`;
      `availability` still has `implemented=False`.
- [ ] `REGISTRY_STATUS` is still the literal `"approved"` and was not edited.
- [ ] `REGISTRY_VERSION == "1.1.1-approved-g1-m6j"` in code **and** in
      `docs/decisions/pilot-decisions.md`.
- [ ] `assert_scoring_ready()` passes, and fails with a named-key message when an
      approved factor is unimplemented (test 18 in `test_scoring.py`).
- [ ] `normalize_weights()` returns `{"topic_relevance": 0.70,
      "travel_burden": 0.30}` summing to 1.0.
- [ ] All five named guard tests were converted (not deleted) and the whole
      `tests/unit/test_factor_registry.py` file is green with no skips.
- [ ] Seven approved fixtures plus the new schema exist under
      `tests/golden/matching/approved/`; all ten golden-runner tests pass.
- [ ] `git diff` over `tests/golden/matching/symptoms`,
      `tests/unit/test_matching_golden_case_schema.py` and
      `tests/unit/test_matching_fail_closed.py` is empty.
- [ ] `make check`-equivalent gates (`format-check`, `lint`, `typecheck`,
      `imports`, `test`, `scan`) all exit 0.

---

## Task 5 (M7) — CP-SAT portfolio optimizer + dependency lock refresh

**Prerequisite:** Task 4 is complete and green.

### Fence

May create/modify **only**:

- `python/smartmatch_domain/smartmatch_domain/optimizer.py` (new)
- `tests/unit/test_optimizer.py` (new)
- `requirements/runtime.in` (modify — add one line)
- `requirements/runtime.txt` (regenerated by `make lock`)
- `requirements/dev.txt` (regenerated by `make lock`)
- `python/smartmatch_domain/pyproject.toml` (modify — `dependencies` only)
- `pyproject.toml` (modify — **add one mypy override block only**; do not touch
  `[tool.importlinter]`, `[tool.ruff]`, `[tool.pytest.ini_options]`, or any
  existing contract)
- `python/smartmatch_domain/smartmatch_domain/__init__.py` (modify — **docstring
  only**, one sentence)

Must NOT touch `factor_registry.py`, `scoring.py`, any factor module,
`Makefile`, `tools/supply_chain.py`, or anything under `tests/golden/`.

### Import-linter resolution — decided, do not re-open

**Approach: keep `optimizer.py` inside `smartmatch_domain` and import OR-Tools at
module level. No new package, no lazy import, no import-linter contract
exception.**

Evidence this is safe, gathered on this worktree at plan time:

> import-linter builds its graph with `grimp`, and with
> `include_external_packages = true` grimp records external packages as
> **squashed leaf nodes with no outbound edges**. Probing this repository's own
> graph confirms it: building the graph for `smartmatch_persistence` yields
> external nodes `['__future__', 'collections', 'dataclasses', 'datetime',
> 'decimal', 'enum', 'hashlib', 'json', 'sqlalchemy', 'types', 'typing', 'uuid']`
> and `find_modules_directly_imported_by("sqlalchemy")` returns `[]`. Submodule
> imports also squash to the top-level name — `from collections.abc import
> Mapping` is recorded as `collections`.

Therefore `from ortools.sat.python import cp_model` inside
`smartmatch_domain.optimizer` is recorded in the graph as the single edge
`smartmatch_domain.optimizer -> ortools`. `google` / `google.protobuf` — which
OR-Tools imports transitively — **never enter the graph at all**, so the
`forbidden_modules = [..., "google", ...]` entry of the
"Domain is pure — no frameworks, storage, providers, IO, or env" contract is not
violated. A function-local import would gain nothing (grimp sees function-local
imports too) and would cost a per-call import and a typing hole.

The remaining objection is honesty, not tooling: `smartmatch_domain/__init__.py`
currently says "This package has **no dependencies**." That must be corrected in
this card, to something like:

> This package depends on no framework, storage layer, provider SDK, filesystem,
> network, or environment variable. Its one third-party dependency is
> `ortools`, a deterministic in-process constraint solver used by
> :mod:`smartmatch_domain.optimizer`; it performs no IO and reaches nothing
> outside the process. That is enforced in CI by the import-linter contracts in
> the root ``pyproject.toml``, not by convention.

If `make imports` nonetheless reports a violation naming `google`, **stop and
report** — do not add a contract exception and do not weaken the forbidden list.

### Work — dependencies

1. `requirements/runtime.in`: append `ortools>=9.14,<10` with a comment naming
   this card and the reason (CP-SAT portfolio assignment, v1.1 §1.2 Stage B).
2. `python/smartmatch_domain/pyproject.toml`: change
   `dependencies = []` to `dependencies = ["ortools>=9.14,<10"]`.
3. Root `pyproject.toml`: add, after the existing `tests.*` override:

```toml
# OR-Tools ships partial type information; its generated protobuf modules are
# not typed. Narrow to the one package rather than relaxing strict mode.
[[tool.mypy.overrides]]
module = ["ortools.*"]
ignore_missing_imports = true
```

4. Run `make lock` from the worktree root. This installs `pip-tools==7.6.1` and
   regenerates `requirements/runtime.txt` and `requirements/dev.txt` with hashes.
   **It needs network access.** Then reinstall:
   `.venv/bin/pip install -q --require-hashes -r requirements/dev.txt`.
5. Run `.venv/bin/python tools/supply_chain.py licenses`. OR-Tools is Apache-2.0
   (allowed). Its transitive dependencies (`protobuf`, `absl-py`, `numpy`,
   `pandas`, `immutabledict`, and pandas' own chain) must all resolve to an
   allowed license. **If any reports an unknown or disallowed license, STOP and
   report it — do not add an entry to `ALLOWED_LICENSES` or `LICENSE_EXCEPTIONS`.**

### Work — `optimizer.py`

Module docstring: architecture v1.1 §1.2 Stage B global optimization; **CP-SAT,
never an LLM**; deterministic for identical inputs and seed; the solver version
is recorded on every result so a stored `match_run` (M8) can be reproduced.
State explicitly: **`portfolio_size` is a caller parameter. Returning 2–3
speakers is a presentation rule owned by M10 and must never be hardcoded here.**

```python
OPTIMIZER_MODEL_VERSION: Final[str] = "1.0.0-cpsat"
SOLVER_NAME: Final[str] = "ortools-cpsat"

#: Utilities are floats in [0, 1]; CP-SAT is an integer solver, so utilities are
#: scaled to integers. 1e6 keeps six decimal places, which is the precision
#: StageBScore.value is rounded to.
UTILITY_SCALE: Final[int] = 1_000_000

#: Wall-clock ceiling. A deterministic model this small never approaches it; the
#: bound exists so a pathological input cannot hang a worker.
SOLVE_TIME_LIMIT_SECONDS: Final[float] = 10.0


class PortfolioStatus(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"


@dataclass(frozen=True, slots=True)
class PortfolioCandidate:
    subject_id: str
    utility: float  # a known StageBScore.value; must be in [0.0, 1.0]


@dataclass(frozen=True, slots=True)
class PortfolioRequest:
    event_need_id: str
    candidates: tuple[PortfolioCandidate, ...]
    portfolio_size: int  # required; no default
    random_seed: int = 0


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    event_need_id: str
    selected_subject_ids: tuple[str, ...]
    objective_value: int
    status: PortfolioStatus
    solver_name: str
    solver_version: str
    model_version: str
    random_seed: int
    portfolio_size: int


def solve_portfolio(request: PortfolioRequest) -> PortfolioResult: ...
```

Validation (`__post_init__` / at entry):

- `PortfolioCandidate.utility` outside `[0.0, 1.0]` → `ValueError`. A candidate
  whose Stage B value is `None` is **rejected with `ValueError`, never coerced to
  `0.0`** — the caller decides how to present an unknown (ADR-0011).
- `portfolio_size < 1` → `ValueError`.
- Duplicate `subject_id` → `ValueError`.
- Blank `event_need_id` or `subject_id` → `ValueError`.

Model:

1. `ordered = sorted(request.candidates, key=lambda c: (-c.utility, c.subject_id))`
   — the ratified tie-break applied to the model's variable order.
2. One `model.NewBoolVar(f"select_{i}")` per ordered candidate.
3. `target = min(request.portfolio_size, len(ordered))`;
   `model.Add(sum(x) == target)`. With no candidates, return immediately with
   `selected_subject_ids=()`, `objective_value=0`,
   `status=PortfolioStatus.OPTIMAL`.
4. Objective coefficient for index `i` over `n = len(ordered)`:

```
coefficient[i] = round(ordered[i].utility * UTILITY_SCALE) * (n + 1) + (n - i)
```

   The `(n - i)` term is a strict lexicographic tie-break that makes the optimum
   **unique**: it lies in `[1, n]`, always strictly less than the `(n + 1)`
   multiplier, so it can never outweigh a utility difference of one scale unit.
   It ranks equal-utility candidates by ascending `subject_id`, matching the
   ratified rule. Without it CP-SAT may return either of two equally good
   portfolios and the "deterministic given identical inputs and seed" requirement
   would rest on solver internals.
5. `model.Maximize(sum(coefficient[i] * x[i]))`.
6. Solver parameters, all three required for determinism:
   `solver.parameters.num_workers = 1`,
   `solver.parameters.random_seed = request.random_seed`,
   `solver.parameters.max_time_in_seconds = SOLVE_TIME_LIMIT_SECONDS`.
7. Map `cp_model.OPTIMAL` → `PortfolioStatus.OPTIMAL`,
   `cp_model.FEASIBLE` → `FEASIBLE`, anything else → `INFEASIBLE` with
   `selected_subject_ids=()`.
8. `selected_subject_ids` = the selected ids **sorted lexicographically
   ascending**.
9. `solver_version` = `ortools.__version__` (import the package and read the
   attribute; do not hardcode a version string).
10. `objective_value = int(solver.ObjectiveValue())`.

### Tests — `tests/unit/test_optimizer.py`

1. `test_selects_the_highest_utility_candidates` — five candidates,
   `portfolio_size=3` → the three highest utilities, ids returned sorted.
2. `test_portfolio_size_is_a_parameter_not_a_constant` — the same candidate set
   solved at sizes 1, 2, 3, 4 returns 1, 2, 3, 4 ids respectively.
3. `test_no_two_or_three_is_hardcoded` — read `optimizer.py` source and assert
   neither the integer literal `2` nor `3` appears as a portfolio-size default;
   assert `PortfolioRequest` has no default for `portfolio_size`
   (`dataclasses.fields` → the field's `default` and `default_factory` are both
   `MISSING`).
4. `test_portfolio_size_larger_than_the_candidate_pool_returns_everyone`.
5. `test_empty_candidate_pool_returns_an_empty_portfolio` — status `OPTIMAL`,
   no exception.
6. `test_result_is_deterministic_across_repeated_solves` — solve the same request
   twenty times; every `selected_subject_ids` and `objective_value` is identical.
7. `test_result_is_deterministic_regardless_of_input_order` — shuffle the
   candidate tuple; the result is unchanged.
8. `test_ties_are_broken_lexicographically_by_subject_id` — three candidates with
   identical utility, `portfolio_size=2`, supplied in reverse id order → the two
   lexicographically smallest ids.
9. `test_result_records_the_solver_version` — `solver_name == "ortools-cpsat"`,
   `solver_version` equals `ortools.__version__` and is non-empty,
   `model_version == OPTIMIZER_MODEL_VERSION`, `random_seed` is echoed back.
10. `test_unknown_utility_is_rejected_never_coerced_to_zero` — constructing
    `PortfolioCandidate(subject_id="x", utility=None)` (typed `float`, passed at
    runtime) raises, and a `float("nan")` utility raises `ValueError`.
11. `test_utility_out_of_range_is_rejected` — `-0.1` and `1.1` raise `ValueError`.
12. `test_duplicate_subject_id_is_rejected` — `pytest.raises(ValueError)`.
13. `test_portfolio_size_below_one_is_rejected` — `0` and `-1` raise `ValueError`.
14. `test_no_llm_or_network_import` — parse `optimizer.py` with `ast`; the set of
    imported module roots is a subset of
    `{"__future__", "dataclasses", "enum", "typing", "ortools", "smartmatch_domain"}`.
    Explicitly assert none of `{"openai", "anthropic", "google.generativeai",
    "httpx", "requests", "socket", "subprocess", "os"}` appears.
15. `test_integrates_with_stage_b_scores` — build two `CandidateEvidence` values,
    run `rank_candidates`, feed the non-`None` values into
    `PortfolioCandidate(subject_id=..., utility=...)`, solve at size 1, and assert
    the top-ranked subject is selected.

### Verification commands

```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-match-engine
make lock
.venv/bin/pip install -q --require-hashes -r requirements/dev.txt
.venv/bin/python -c "import ortools; print(ortools.__version__)"
.venv/bin/python -m pytest tests/unit/test_optimizer.py -q
.venv/bin/python -m pytest tests/ -m "not integration" -q
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy python/ services/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
.venv/bin/python tools/supply_chain.py licenses
git status --porcelain
```

`lint-imports` must report the "Domain is pure" contract as **KEPT**. Paste its
output into the card's completion report.

### Done when

- [ ] Exactly the seven fenced files changed; `git status --porcelain` shows no
      others.
- [ ] `ortools>=9.14,<10` is in `requirements/runtime.in` and in
      `python/smartmatch_domain/pyproject.toml`; `requirements/runtime.txt` and
      `requirements/dev.txt` are regenerated with hashes.
- [ ] `lint-imports` passes and the "Domain is pure" contract is KEPT — output
      pasted in the report.
- [ ] `tools/supply_chain.py licenses` exits 0 with no widened allowlist.
- [ ] All 15 optimizer tests pass; `.venv/bin/python -m pytest tests/ -m "not
      integration" -q` is green.
- [ ] `ruff format --check .`, `ruff check .`, `mypy python/ services/`, and
      `tools/scan_forbidden.py` all exit 0.
- [ ] Twenty repeated solves of the same request return identical results.
- [ ] `portfolio_size` has no default and the literals 2 and 3 are not used as a
      portfolio size anywhere in `optimizer.py`.
- [ ] `smartmatch_domain/__init__.py` no longer claims the package has no
      dependencies.

---

## Evidence ladder for the whole plan

1. Per-card focused pytest (commands above).
2. `make check` from the worktree root after Task 5 — this runs `format-check`,
   `lint`, `typecheck`, `imports`, `test`, `scan`, `memory`, `licenses`,
   `infra-check`.
3. `git diff --stat` over the do-not-touch list (§0.4) must be empty.
4. `make openapi-check` must still pass and the committed OpenAPI document must be
   byte-identical — no routes land in this PR.

## Explicitly not done by this plan

`match_run` persistence and its migration (M8a), HTTP routes and the policy
matrix (M8b), explanations (M9), UI (M10), and the D3 route-matrix provider. No
push, no PR, no production-readiness claim.
