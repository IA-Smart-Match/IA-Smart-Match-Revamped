# B26 T8c — registry `3.0.0` (proposed): band table, hash coverage, Full before the solve, load penalty, `load` block, G-CBA-14…19

**Next action:** once T4 milestones 6 and 8 and T8b milestone 2 are pushed, rebase this branch onto
`feat/b26-t4`, merge `feat/b26-t8b`, and commit milestone 1 (§12).

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` (as corrected on
`feat/b26-t8b`), §5.2 registry items 1–7, §7 row 11, §8 T8c row, §9 Q7, §10 row 3, §11 risks 3–4.
Consumes: T8b plan (`eli.py` 2.0.0), T8a plan (`0040`, `cancelled_at`), T2 as built (`0038`,
`SpeakerAvailabilityRepository`), T4 plan (run payload, `excluded` stored, UTC `as_of`, Stage A placement).

**Plan gate: APPROVE (orchestrator, 2026-09-23).** OQ1–OQ5 accepted as recommended; departures C1 and
C2 accepted. Findings 1–7 applied (§15).

## 0. Guardrail

Registry `3.0.0` ships **declared, with status `proposed`, and not current.**

| Stays exactly as it is | Evidence it stays |
|---|---|
| `REGISTRY_VERSION == "2.0.0-approved-oq-cba-004"` and `CBA_REGISTRY` is what new runs score under | `test_factor_registry.py:262-271` unedited; new test 3 (§11) asserts `current_cba_registry() is CBA_REGISTRY` |
| `SUPERSEDED_REGISTRY_VERSION == "1.1.1-approved-g1-m6j"` (a `str`) | Same test, unedited |
| `registry_hash` of every 1.1.1 and 2.0.0 run, byte for byte | New test 8 pins the literals measured on `origin/main` `1909278f` (§3.5) |
| `inputs_hash`, `weights`, every `MatchRunPins` field of a 2.0.0 run | New worker test W1/W2 (§11) |
| 2.0.0 explanation payload bytes (no `load` key is written) | G-CBA-18 (§10) |
| Query count of a 2.0.0 run create (T4's count) | Contract test C1 (§11) |
| `SCORING_MODE_VERSION == "1.0.0"`, both mode names, `ck_match_run_scoring_mode` | No edit |

**The one line that later makes 3.0.0 current (not done in T8c)** — in `factor_registry.py`:

```python
CURRENT_CBA_REGISTRY: Final[FactorRegistry] = CBA_REGISTRY_3  # was: = CBA_REGISTRY
```

It needs approval first (§13). Flipped without approval, it fails closed: the create route's gate
reads the current registry's status, so a proposed current registry answers `503 registry_not_ready`
(contract test C3).

## 1. Branch, dependencies, migration

**Stacking.** T4 is stacked on T8a → T6b-1 → T2 → T1 (T4 plan header). T8c needs all of them plus T8b:

1. `git rebase --onto origin/feat/b26-t4 origin/main feat/b26-t8c` (only this plan commit moves).
2. `git merge origin/feat/b26-t8b` (T8b branches from `main`; pure domain). Expected conflict: the parent
   plan only (T8b edited lines 413–425, 511, 535, 543–546; T4 adds §3.5 and its §8 row). Keep both sides.
3. Rebase onto `main` as each lower track lands. PR against `main`, draft until T4 and T8b merge.

| Needs | From | What T8c uses |
|---|---|---|
| `pipeline_record.cancelled_at` | T8a `0040` | the load read's `cancelled_at IS NULL` |
| `LoadBand`, `LoadBandTable`, `Q7_LOAD_BAND_TABLE`, `Engagement.from_event_time`, `LoadInputs`, `LoadAssessment`, `compute_eli`, `ELI_FORMULA_VERSION` | T8b | ELI 2.0.0; T8c never edits `eli.py` or its types |
| `speaker_availability.declared_capacity_hours_per_90_days`, `SpeakerAvailabilityRepository.get_many` | T2 (`0038`) | capacity (`statement.declared_capacity_hours_per_90_days`, `Decimal \| None`) |
| `as_of_utc`, `event_time_from_columns` (`availability_verdict.py`); `current_verdicts` (`availability_reads.py`); payload `excluded` stored and read; `EXCLUSION_FILED_THIS_REQUEST` placement in `assemble_cba_pool`; golden runner `owner_decisions` + case `as_of` | T4 | one `as_of` per run; Full sits beside Q8 at Stage A |

**No migration.** Every column the read needs exists after `0040`; every index it needs exists today:

| Access | Index that serves it |
|---|---|
| `pipeline_record WHERE tenant_id = ? AND subject_id = ANY(?)` | `uq_pipeline_record_subject_opportunity (tenant_id, subject_id, opportunity_event_id)` — leading two columns |
| `event` joined on `(tenant_id, id)` | `uq_event_tenant_id (tenant_id, id)`, `event_pkey (id)` |
| `speaker_availability` by `(tenant_id, professional_id)` | its primary key (T2) |

`match_run` has no CHECK on `registry_version` (`schema.py:1501-1612`: blankness only), the mode CHECK is
unchanged, and explanations live in `job.payload` (JSONB). So nothing new is stored in a column. If a
reviewer proves an index is needed, it is `0042` after T4's `0041` — flagged, not planned.

## 2. Files

| # | Path | Change |
|---|---|---|
| 1 | `python/smartmatch_domain/smartmatch_domain/load_bands.py` | **New.** §3.1: `ENGAGEMENT_LOAD_FACTOR_KEY`, `LoadBandOwnership`, `RegisteredLoadBands`, `Q7_REGISTERED_LOAD_BANDS`, `AssessedLoad`, `canonical_load_bands`, `assess_pool_loads`, `stage_a_load_excluded`. Imports `eli` only (no cycle: `eli` imports `events` only). |
| 2 | `python/smartmatch_domain/smartmatch_domain/factor_registry.py` | `FactorRegistry` gains `load_bands` (§3.2); `ENGAGEMENT_LOAD_SPEC`, `REGISTRY_3_VERSION`, `PROPOSED_FACTORS_3`, `APPROVED_SCORING_KEYS_3`, `CBA_3_PHYSICAL_MODEL`, `CBA_3_VIRTUAL_MODEL`, `CBA_REGISTRY_3`; bound in `_REGISTRIES_BY_VERSION` (`:689`); `CURRENT_CBA_REGISTRY`, `current_cba_registry()`, lineage, `superseded_registry_versions()`, `proposed_registry_versions()`, `SUPERSEDED_REGISTRY_VERSIONS` (§3.4); impostor guard widened (§3.6); `_unregister_for_tests` (`:725`) refuses the 3.0.0 pin. Docstrings: module "Status" (`:7-11`), `REGISTRY_VERSION` (`:146-154`), `ScoringModel.is_current` (`:450-452`), `UnknownRegistryVersionError` (`:890-911`). |
| 3 | `python/smartmatch_domain/smartmatch_domain/match_run.py` | `registry_fingerprint(weights, *, load_bands)` (§3.5); `MatchRunPins.registry_hash` docstring (`:213`). `weights_fingerprint` and `inputs_fingerprint` unchanged. |
| 4 | `python/smartmatch_domain/smartmatch_domain/scoring.py` | `CbaCandidateEvidence.load` (`:417`); `StageBScore.load`, `.composite_before_load` (`:151`); `registry` keyword on `score_cba_candidate` (`:463`), `_cba_factor_scores` (`:521`), `_compose_cba` (`:562`), `rank_cba_candidates` (`:649`); `CBA_LOAD_STAGE_B_FORMULA_VERSION`; the multiplier (§6). |
| 5 | `python/smartmatch_domain/smartmatch_domain/explanation.py` | `LoadExplanation`; `CandidateExplanation.load` (`:287`); `explain_candidate` builds it (`:462`); `explanation_to_payload` (`:535`) and `explanation_from_payload` (`:653`) (§7). |
| 6 | `python/smartmatch_domain/smartmatch_domain/weight_settings.py` | `applied_weights` (`:247`) gains `registry: FactorRegistry = CBA_REGISTRY`, passed to `normalize_weights`. Default keeps every caller. |
| 7 | `python/smartmatch_persistence/smartmatch_persistence/engagement_load.py` | **New.** `EngagementLoadRepository.engagements_for` (§4). Never commits. |
| 8 | `services/api/smartmatch_api/match_run_evidence.py` | `EXCLUSION_LOAD_FULL = "load_full"` (+ `__all__`); `ExcludedCandidate.load: AssessedLoad \| None = None` (`:206`); `assemble_cba_pool(..., loads=None)` (`:353`) (§5). |
| 9 | `services/api/smartmatch_api/availability_reads.py` (T4's) | `current_verdicts(..., statements=None)`: reuse a map already read; `None` keeps T4's own `get_many`. |
| 10 | `services/api/smartmatch_api/routers/match_runs.py` | Create (`:795`): current registry, one `as_of`, load read, `loads` into the pool, `registry=` into ranking, payload `registry_version` and `excluded[].load` (§8). `_assert_scoring_permitted` (`:622`) takes a registry: create passes the current one; **read passes the run's own pin** (`registry_for_version(run.registry_version)`, or `CBA_REGISTRY` when the pin is unknown), never the current registry. `ExcludedCandidateView` (`:316`): `reason` description (`:327`) lists `load_full`; new optional `load: LoadBlockView \| None`, mapped from the stored `excluded[].load` block by `_to_view`, **without `unknown_hours_refs`** (§8 Read). |
| 11 | `services/worker/smartmatch_worker/handlers.py` | `MatchRunCommand.registry_version` (`:930`); `_read_match_run_command` (`:1025`); gate, weights and `registry_hash` from the payload's registry (`:1184`, `:1198`, `:1225`, `:1254`) (§8). |
| 12 | `services/api/smartmatch_api/routers/matching_weights.py:346` | `registry_version=current_cba_registry().version` (same value today). |
| 13 | `contracts/openapi/smartmatch.json` | `make openapi` (`ExcludedCandidateView`: `reason` description and the optional `LoadBlockView`, which has no `unknown_hours_refs` field). |
| 14 | `docs/architecture/decisions/ADR-0027-registry-3-engagement-load.md` + `README.md` index row | **New, status Proposed.** Records Q7 = A, the multiplier, `registry_hash` for 3.x (amends ADR-0016's "`registry_hash` is `weights_fingerprint`", line 336, for 3.x only), and the flip procedure (§13). |
| 15 | `docs/architecture/registry-supersession-record.md` | Dated section "3.0.0 declared proposed (B26 T8c), not current". |
| 16 | Parent plan | §5.2 items 3–4 re-worded to §3.4 (plural derived set, `CURRENT_CBA_REGISTRY`); §8 T8c "Depends on" → "T4 (stack), T8b; approval before current". |
| 17 | Tests and fixtures | §11: `tests/unit/test_factor_registry.py` (appended section), `tests/unit/test_load_bands.py` (new), `tests/unit/test_match_run_pins.py`, `tests/unit/test_scoring_load.py` (new), `tests/unit/test_explanation.py`, `tests/unit/registry_evaluation.py` (new helper, not collected), `tests/unit/test_cba_matching_golden.py`, `tests/golden/matching/cba/G-CBA-14…19-*.json`, `cba_case.schema.json`, `tests/integration/test_engagement_load_read.py` (new), `tests/integration/test_match_run_command_path.py`, `tests/contract/test_match_runs_api.py`. |

Not touched: `eli.py` and its types, `schema.py`, any migration, `optimizer.py`, the frontend (band words
are T8d), `explanation.py`'s factor rows, `SCORING_MODE_VERSION`.

`factor_registry.py` is 1,120 lines today, over the 800-line rule; T8c adds about 130. A split is a
follow-up card (OQ5), not T8c.

## 3. Contracts

### 3.1 `load_bands.py` — the registry-side wrapper around T8b's table

```python
ENGAGEMENT_LOAD_FACTOR_KEY: Final[str] = "engagement_load"


class LoadReviewStatus(StrEnum):
    PENDING_IA_WEST_REVIEW = "pending_ia_west_review"  # parent §10 row 3
    REVIEWED = "reviewed"


@dataclass(frozen=True, slots=True)
class LoadBandOwnership:
    decided_by: str  # "Danny Tran, Development Lead / program owner of record"
    decided_on: str  # "2026-09-22"
    decision: str  # "B26 Q7 = A (parent plan §9)"
    review_status: LoadReviewStatus
    # __post_init__: every str non-blank; decided_on is an ISO date.


@dataclass(frozen=True, slots=True)
class RegisteredLoadBands:
    table: LoadBandTable  # T8b's type, used as-is; never subclassed or edited
    eli_formula_version: str  # "2.0.0" == eli.ELI_FORMULA_VERSION at declaration
    ownership: LoadBandOwnership  # not hashed (see 3.5)


Q7_REGISTERED_LOAD_BANDS: Final = RegisteredLoadBands(
    table=Q7_LOAD_BAND_TABLE,
    eli_formula_version=ELI_FORMULA_VERSION,
    ownership=LoadBandOwnership(
        decided_by="Danny Tran, Development Lead / program owner of record",
        decided_on="2026-09-22",
        decision="B26 Q7 = A (parent plan §9)",
        review_status=LoadReviewStatus.PENDING_IA_WEST_REVIEW,
    ),
)


@dataclass(frozen=True, slots=True)
class AssessedLoad:
    as_of: date  # the run's UTC date (T4 C7, T8b R2); one value per run
    assessment: LoadAssessment  # T8b's output, unmodified


def canonical_load_bands(bands: RegisteredLoadBands) -> dict[str, object]: ...


def assess_pool_loads(
    subject_ids: Sequence[uuid.UUID],
    *,
    capacities: Mapping[uuid.UUID, Decimal | None],
    engagements: Mapping[uuid.UUID, tuple[Engagement, ...]],
    as_of: date,
    bands: RegisteredLoadBands,
) -> Mapping[uuid.UUID, AssessedLoad]: ...


def stage_a_load_excluded(load: AssessedLoad | None) -> bool: ...
```

- `assess_pool_loads`: one `compute_eli(LoadInputs(as_of=..., engagements=..., declared_capacity_hours=...), bands.table)`
  per subject. Absent capacity key or `None` → `None` capacity (Unknown, `capacity_not_stated`); never a
  default (Q6). Absent engagements key → `()`. Returns a `MappingProxyType`.
- `stage_a_load_excluded(load)` is `load is not None and load.assessment.band is LoadBand.FULL`.

### 3.2 Registry entries

`FactorRegistry` (`factor_registry.py:546`) gains one field, placed after `mode_vocabulary`:

```python
load_bands: RegisteredLoadBands | None = None  # compared and hashed; None for 1.x/2.x/exercise
```

`__post_init__` adds, fail-closed:

1. `load_bands is None` ⇔ `ENGAGEMENT_LOAD_FACTOR_KEY` is not a declared key.
2. When declared, that spec is `kind=PENALTY`, `proposed_weight=0.0`, `implemented=True`, not retired,
   and in **no** model's `scoring_keys` (so `normalize_weights`, `applied_weights` and the deflation
   guard in `_compose_cba` never see it).
3. `load_bands.eli_formula_version == eli.ELI_FORMULA_VERSION`.

`CBA_REGISTRY`, `EXERCISE_REGISTRY` and every toy registry leave `load_bands` at `None`, so their
equality, hash, and every value they produce are unchanged (`test_factor_registry_parameterised.py`
green unedited).

The 3.0.0 declaration:

| Name | Value |
|---|---|
| `REGISTRY_3_VERSION` | `"3.0.0-approved-b26-eli"` (parent §5.2 item 3; OQ1) |
| `ENGAGEMENT_LOAD_SPEC` | `FactorSpec(key="engagement_load", display_label="Engagement load", kind=PENALTY, proposed_weight=0.0, implemented=True, rationale="B26 Q1/D2 + Q7 = A: multiplier on the composite (Light 1.00, Moderate 0.90, Heavy 0.70); Full removed at Stage A; weight 0 in the weighted sum so utilities stay in [0, 1].")` |
| `PROPOSED_FACTORS_3` | the **same objects** as `PROPOSED_FACTORS[0:4]` (industry, role, topic, proximity), then `ENGAGEMENT_LOAD_SPEC`, then the same `availability` spec (`PROPOSED_FACTORS[6]`). The retired G1 pair stays in `CBA_REGISTRY` only: 1.1.1 runs resolve there. |
| `APPROVED_SCORING_KEYS_3` | `APPROVED_SCORING_KEYS \| {"engagement_load"}` — required, because `implemented_scoring_keys(registry=R3)` includes every implemented non-eligibility spec and `assert_scoring_ready` demands equality. `CONFIGURABLE_FACTOR_KEYS` (the CBA constant) is unchanged, so the penalty is never a configurable weight. |
| `CBA_3_PHYSICAL_MODEL` / `CBA_3_VIRTUAL_MODEL` | `ScoringModel(registry_version=REGISTRY_3_VERSION, scoring_mode=cba-physical-1 / cba-virtual-1, scoring_mode_version=SCORING_MODE_VERSION, scoring_keys=` the same four / three keys `, is_current=True, mode_vocabulary=CBA_SCORING_MODES)`. `is_current` keeps its only use (`assert_scoring_ready`'s sum check, `:992`) and its docstring becomes "selectable in its own rulebook". |
| `CBA_REGISTRY_3` | `FactorRegistry(version=REGISTRY_3_VERSION, status="proposed", approver=None, approved_on=None, factors=PROPOSED_FACTORS_3, approved_scoring_keys=APPROVED_SCORING_KEYS_3, scoring_modes={...both models...}, mode_vocabulary=CBA_SCORING_MODES, load_bands=Q7_REGISTERED_LOAD_BANDS)` |

Because the four weighted specs are the same objects, `normalize_weights(model=CBA_3_PHYSICAL_MODEL, registry=CBA_REGISTRY_3)`
equals `normalize_weights(model=CBA_PHYSICAL_MODEL)` value for value (G-CBA-19). `resolve_scoring_model(None, registry=CBA_REGISTRY_3)`
raises `UnknownScoringModeError` (`:800-805`): 3.0.0 has no pre-mode model.

### 3.3 Band table with ownership

| Band | Utilization `u` | Stage A | Multiplier | Edge owner |
|---|---|---|---|---|
| Light | `u < 0.50` | pass | `Decimal("1.00")` | `eli.py` code (`>=`/`>`), T8b §4 |
| Moderate | `0.50 ≤ u < 0.80` | pass | `Decimal("0.90")` | same |
| Heavy | `0.80 ≤ u ≤ 1.00` | pass | `Decimal("0.70")` | same |
| Full | `u > 1.00` | removed before the solve, in `excluded` as `load_full` | none (never scored) | same |
| Unknown | capacity not stated, or unknown in-window hours without known hours `> 100%` | pass | `Decimal("1.00")` | same |

Cut points and multipliers: T8b's `Q7_LOAD_BAND_TABLE`. Ownership (who decided, when, which decision,
IA West review state): `LoadBandOwnership` above. Approval of the whole rulebook: `CBA_REGISTRY_3.status`.

### 3.4 Current, superseded, proposed

```python
_CBA_LINEAGE: Final[tuple[tuple[str, FactorRegistry], ...]] = (
    (SUPERSEDED_REGISTRY_VERSION, CBA_REGISTRY),  # 1.1.1
    (REGISTRY_VERSION, CBA_REGISTRY),  # 2.0.0
    (REGISTRY_3_VERSION, CBA_REGISTRY_3),  # 3.0.0
)
CURRENT_CBA_REGISTRY: Final[FactorRegistry] = CBA_REGISTRY  # the flip line (section 0)


def current_cba_registry() -> FactorRegistry: ...  # returns the module global, read per call


def superseded_registry_versions(
    current: FactorRegistry | None = None,
) -> frozenset[str]: ...  # lineage versions strictly older than current.version


def proposed_registry_versions(
    current: FactorRegistry | None = None,
) -> frozenset[str]: ...  # lineage versions strictly newer than current.version


SUPERSEDED_REGISTRY_VERSIONS: Final[frozenset[str]] = superseded_registry_versions()
```

| | T8c ships | After the flip |
|---|---|---|
| `current_cba_registry().version` | `2.0.0-approved-oq-cba-004` | `3.0.0-approved-b26-eli` |
| `SUPERSEDED_REGISTRY_VERSIONS` | `{1.1.1-approved-g1-m6j}` | `{1.1.1-approved-g1-m6j, 2.0.0-approved-oq-cba-004}` = parent §5.2 item 4 |
| `proposed_registry_versions()` | `{3.0.0-approved-b26-eli}` | `{}` |
| `registry_for_version(v)` | resolves all three | unchanged |

`SUPERSEDED_REGISTRY_VERSION` (singular, `str`) stays: it names the G1 pin, `SUPERSEDED_G1_MODEL` is
pinned to it, and 43 lines across `python/`, `services/` and `tests/` read it as a string (C1, §14). `REGISTRY_VERSION` stays the 2.0.0
rulebook's identity — it is `CBA_REGISTRY.version`, the G1 pair's `retired_in_version` (`:363`, `:378`),
and a member of `_CBA_REGISTRY_VERSIONS` (`:696`). Retargeting it would re-label every stored 2.0.0 run,
so the flip moves `CURRENT_CBA_REGISTRY`, never `REGISTRY_VERSION` (C2).

Only the **create route** reads `current_cba_registry()`. The worker reads the payload's pin (§8);
every domain default stays `CBA_REGISTRY`, so goldens G-CBA-01…13 score 2.0.0 before and after the flip.

### 3.5 Hash coverage per version

```python
def registry_fingerprint(
    weights: Mapping[str, float], *, load_bands: RegisteredLoadBands | None
) -> str: ...
```

| Registry | `load_bands` | `registry_hash` | Bytes hashed |
|---|---|---|---|
| `1.1.1-approved-g1-m6j` | `None` | `weights_fingerprint(weights)` — the same call as today | `{"topic_relevance":"0.7","travel_burden":"0.3"}` |
| `2.0.0-approved-oq-cba-004` | `None` | `weights_fingerprint(weights)` — the same call as today | `{"cba_semantic_topic":"0.15",…}` (unchanged) |
| `3.0.0-approved-b26-eli` | set | `_digest({"weights": _rendered_weights(weights), "load_bands": canonical_load_bands(bands)})` | see below |

The rule keys on `load_bands is None`, never on parsing the version string. `inputs_fingerprint` is
unchanged; under 3.x it folds the post-penalty utilities, which is how the load enters it (parent item 5).

`canonical_load_bands(Q7_REGISTERED_LOAD_BANDS)` — every `Decimal` rendered `format(d.normalize(), "f")`,
so `0.5` and `0.50` (equal under `LoadBandTable.__eq__`) hash equal:

```json
{"eli_formula_version": "2.0.0", "full_above": "1", "heavy_from": "0.8", "moderate_from": "0.5",
 "multipliers": {"heavy": "0.7", "light": "1", "moderate": "0.9", "unknown": "1"}}
```

In: cut points, multipliers, ELI formula version (same numbers under another formula are another rule).
Out: ownership and review status (approval must not move a hash), the registry version string (as in
2.x). `FactorRegistry` gains no `registry_hash` attribute (`test_the_registry_declares_no_registry_hash_of_its_own`).

**Byte-for-byte literals**, measured on `origin/main` `1909278f` with default weights; re-measured at
milestone 1 on the stacked base and must be equal (T4 touches no weight):

| Model | `registry_hash` |
|---|---|
| 2.0.0 `cba-physical-1` | `sha256:f870192c2b1d9977aaf4be3368f51f67accbbbba9955e4346a4445b0be4be4e5` |
| 2.0.0 `cba-virtual-1` | `sha256:0b27df1f198b501da27f3a58d0128625f1351a1ba77fa4189807c31865c85ce4` |
| 1.1.1 G1 | `sha256:9da5f1b1ccb6b0627759c77a472fb47d8b77ce634c21fffe9bf53a5b04e79de1` |

### 3.6 Gates

| Call | 2.0.0 (current) | 3.0.0 (proposed) |
|---|---|---|
| `assert_registry_approved(registry=…)` | passes (reads `REGISTRY_STATUS`, `:875`) | raises `RegistryNotApprovedError` (reads `CBA_REGISTRY_3.status`) |
| `assert_scoring_ready(registry=…)` | passes | passes (5 implemented = 5 approved; both models sum to 1) |
| `explain_candidate(score)` | passes | raises (gate on the score's registry, `:485-486`) |
| worker gate | passes | `failed_policy`, reason `registry_not_ready` |

Impostor guard: `_reads_as_the_cba_registry` (`:821`) stays as is. A new `_DECLARED_BY_VERSION`
(from `_CBA_LINEAGE`) makes `assert_registry_approved` and `assert_scoring_ready` refuse any registry
that claims `3.0.0-approved-b26-eli` without being `== CBA_REGISTRY_3` (an "approved" copy cannot
borrow the pin). `register_registry` already refuses rebinding the version (`:716-722`).
`_unregister_for_tests` refuses all three lineage pins.

`score_cba_candidate` keeps calling `assert_registry_approved()` / `assert_scoring_ready()` with **no
arguments** when `registry == CBA_REGISTRY` (the seam `test_scoring.py:64-65` patches with zero-argument
fakes), and with `registry=registry` otherwise — the pattern `assert_scoring_ready` already uses (`:967-977`).

## 4. The load read (DB → ELI at run time)

`EngagementLoadRepository.engagements_for(session, *, tenant_id, professional_ids, as_of) -> Mapping[uuid.UUID, tuple[Engagement, ...]]`
— one statement, empty input issues none, never commits:

```sql
SELECT r.id, r.subject_id, r.attended_at,
       e.id AS event_id, e.time_precision, e.starts_at, e.ends_at, e.on_date, e.time_zone
FROM pipeline_record AS r
LEFT JOIN event AS e
  ON e.tenant_id = r.tenant_id AND e.id = r.opportunity_event_id
WHERE r.tenant_id = :tenant_id
  AND r.subject_id = ANY(:professional_ids)
  AND r.confirmed_at IS NOT NULL
  AND r.cancelled_at IS NULL
  AND (e.id IS NULL
       OR e.resolved_date IS NULL
       OR e.resolved_date BETWEEN :window_start AND :window_end)
ORDER BY r.subject_id, r.id
```

`window_start = as_of - timedelta(days=COMPLETED_WINDOW_DAYS)` and
`window_end = as_of + timedelta(days=CONFIRMED_WINDOW_DAYS - 1)` are computed in Python from T8b's
constants and bound as two `date` parameters. No date arithmetic in SQL, no `now()`.

| Rule | Source |
|---|---|
| Completed / confirmed windows `[as_of − 45, as_of)` + `[as_of, as_of + 44]`; attended-on-`as_of` counts as confirmed | T8b R1, R2 — decided in `compute_eli`, not SQL |
| `as_of` = the run's UTC date, `as_of_utc(utc_now())`, computed **once** in `create_match_run` and passed to the read, to `assess_pool_loads`, and to T4's `current_verdicts` | T4 C7, T8b R2 |
| Cancelled excluded: `cancelled_at IS NULL` (any cancellation time; "drops out immediately") | parent §5.2, T8a `0040` |
| `subject_id` is the professional id | `pipeline.py:1057` joins `profile.professional_id == record.subject_id` |
| Scope: **tenant-wide**, every unit's bookings of that person | OQ2 |
| Each row → `Engagement.from_event_time(ref=str(r.id), event_time, confirmed=True, attended=r.attended_at is not None, cancelled=False)`; `event_time` from T4's `event_time_from_columns` | T8b hand-off |
| No event row (`opportunity_event_id` has no FK, `pipeline.py:742-750`) → `UnresolvedTime()` → unknown hours if in play (R4) | OQ3 |
| Date prefilter on `event.resolved_date`: written by `events.resolved_date(event_time)` on every write that sets an event's time (insert and upsert `smartmatch_persistence/events.py:358`, `:404`; edit `routers/manual_events.py:446`), the same function T8b uses for `Engagement.event_date`. `NULL` (unresolved) and missing events always pass. Python stays authoritative. | test L3 |
| Index: none new (§1). One query for ≤ 200 subjects (`MAX_CANDIDATES`). | test L9 |

Capacity: T2's `get_many` over **all named** `subject_ids`, read once, then handed to T4's
`current_verdicts(statements=...)`, so a 3.x create costs T4's queries + 1 (the engagements).

## 5. Full removed before the solve, reported in `excluded`

`assemble_cba_pool(..., loads: Mapping[uuid.UUID, AssessedLoad] | None = None)`. Per subject, in order:

1. no profile → `speaker_profile_not_found` (unchanged);
2. Q8 → `filed_this_request` (T4);
3. **`stage_a_load_excluded(loads[subject])` → `ExcludedCandidate(subject, "load_full", load=...)`** (OQ4);
4. `match_ineligibility_reason` → its token (unchanged);
5. `_candidate_evidence` exclusions (unchanged); otherwise evidence with `load=loads[subject]`.

- `loads is None` (2.x current): steps 3 and the `load=` stay out; output identical to T4's.
- `loads` given but a kept subject has no entry → `KeyError` raised as a defect (never a default band).
- The Full subject is never scored, never explained, and gets no T4 `availability` entry (T4 §2:
  pool-excluded subjects get none).
- Payload: `excluded` entries are T4's `{"subject_id", "reason"}`; a `load_full` entry adds
  `"load": <load assessment block, §7>` so the numbers that removed someone are on record. T4's reader
  ignores the extra key.
- `rank_cba_candidates(registry=R3)` given a Full evidence raises `ValueError` (§6): Full cannot reach Stage B.
- UI word ("Full (no override available)", parent §11 risk 3) is T8d. No override is built (parent item 7).

## 6. Where the multiplier is applied

In `_compose_cba` (`scoring.py:562`), after the weighted sum, before rounding:

```text
bands = registry.load_bands
bands is None:     evidence.load must be None (else ValueError)       -> value = round(total, 6)          # 2.x, unchanged line
bands is not None: evidence.load required (else ValueError: never a default band)
                   band FULL -> ValueError ("removed at Stage A")
                   assessment.formula_version != bands.eli_formula_version -> ValueError
                   m = bands.table.multipliers[band]                  -> value = round(total * float(m), 6)
unknown factor:    value = None (unchanged); load still recorded on the score
```

- Multiplies the **unrounded** composite, then rounds once. `total * 1.0 == total` exactly, so Light and
  Unknown give the 2.x number bit for bit (G-CBA-17). `m ∈ (0, 1]` keeps utilities in `[0, 1]`.
- Worked: composite `0.97` → Moderate `0.873`, Heavy `round(0.6789999999999999, 6) = 0.679` (measured).
- `StageBScore` gains `load: AssessedLoad | None = None` and `composite_before_load: float | None = None`
  (the unrounded `total`, `None` when unknown).
- `formula_version`: `CBA_LOAD_STAGE_B_FORMULA_VERSION = "3.0.0-cba-load"` when `bands` is set, else
  `CBA_STAGE_B_FORMULA_VERSION` (`2.0.0-cba`). The composition changed, so its version does (`:86-90`).
- `normalize_weights(..., model=model, registry=registry)` and `factor_keys(registry=registry)` replace the
  default-registry calls at `:571` and `:586`.

## 7. Explanation `load` block and back-compat

```python
@dataclass(frozen=True, slots=True)
class LoadExplanation:
    band: LoadBand
    reason: LoadReason
    measurable: bool
    completed_hours: Decimal
    confirmed_hours: Decimal
    capacity_hours: Decimal | None
    utilization: Decimal | None  # unrounded; a lower bound when not measurable
    unknown_hours_refs: tuple[str, ...]
    multiplier: Decimal  # from the registry's table for this band
    composite_before_load: float | None  # unrounded; None iff heuristic_score is None
    as_of: date
    eli_formula_version: str
```

Payload (`explanation_to_payload`), decimals as strings so nothing rounds on the way to JSON:

```json
"load": {"band": "moderate", "reason": "measured", "measurable": true,
         "completed_hours": "50", "confirmed_hours": "0", "capacity_hours": "100.0",
         "utilization": "0.5", "unknown_hours_refs": [], "multiplier": "0.9",
         "composite_before_load": 0.97, "as_of": "2026-10-06", "eli_formula_version": "2.0.0"}
```

The `excluded[].load` block (§5) is the same shape without `multiplier` and `composite_before_load`.

| Payload's registry | `load` key | Reader (`explanation_from_payload`) |
|---|---|---|
| `load_bands is None` (1.1.1, 2.0.0) | **absent** — the writer omits it, so 2.x payload bytes are unchanged | absent → `load=None`; present (even `null`) → `ValueError` |
| `load_bands` set (3.0.0) | always present | absent or `null` → `ValueError`; otherwise strict parse |
| unknown version | — | `UnknownRegistryVersionError` re-raised as `ValueError("registry_version: …")`, so `_read_stored_explanations` (`match_runs.py:1137-1140`) reports it unreadable with no route change |

Strict parse (report, never repair): band and reason must be enum values; `measurable == (reason == "measured")`;
decimals must be JSON strings (a JSON number is refused); `Decimal(multiplier) == registry.load_bands.table.multipliers[band]`;
`heuristic_score == round(composite_before_load * float(multiplier), 6)` when both are set, and both `None`
together. Omitting the key for 2.x is not "unknown collapsed into absent": presence is decided by the
pinned registry, never guessed. The gate at `:670` stays `assert_registry_approved()`.

`explain_candidate` builds `LoadExplanation` from `score.load` and the registry's table, and refuses a
3.x score without a load or a 2.x score with one.

## 8. Run payload and worker

**Create** (`match_runs.py:795`), in order:

1. `registry = current_cba_registry()`; `_assert_scoring_permitted(registry)` → 503 while proposed.
2. `as_of = as_of_utc(utc_now())`, once.
3. If `registry.load_bands`: `statements = get_many(all named ids)`, `engagements = engagements_for(...)`,
   `loads = assess_pool_loads(...)`. Else `statements = loads = None` (2.x: zero new queries).
4. `assemble_cba_pool(..., loads=loads)`; `rank_cba_candidates(..., registry=registry)`.
5. T4's `current_verdicts(..., as_of=as_of, statements=statements)`.
6. Payload gains `"registry_version": registry.version` (always written; the worker's pin). Explanations
   carry `load` under 3.x. `excluded[]` carries `load` for `load_full`.

**Read** (`match_runs.py:1148`): `_assert_scoring_permitted(registry_for_version(run.registry_version))`,
falling back to `CBA_REGISTRY` when the pin names no registry (the explanations then report unreadable,
§7). It never reads `current_cba_registry()`: flipping current to a proposed 3.0.0 must not 503 the
reads of stored 1.1.1 / 2.0.0 runs (contract test C8). The read renders `excluded[].load` through
`ExcludedCandidateView.load` (absent → `null`).

**`LoadBlockView` keeps `unknown_hours_refs` off the wire** (orchestrator ruling, T8d gate, unit
privacy). The load read is tenant-wide (OQ2), so the refs can be other units' `pipeline_record` ids.

| Field | Stored payload (`excluded[].load`, explanation `load`) | `LoadBlockView` (run read / `202` response) |
|---|---|---|
| `band`, `reason`, `measurable`, `completed_hours`, `confirmed_hours`, `capacity_hours`, `utilization`, `as_of`, `eli_formula_version` | kept | kept (decimals as strings) |
| `unknown_hours_refs` | **kept** (the run's evidence) | **no such field**; `_to_view` drops it; the response model declares no field that could carry it |

Only `_to_view` builds a `LoadBlockView`; there is no pass-through of the stored dict. T8d, which renders
explanation `load` blocks on the wire, reuses `LoadBlockView` and the same rule.

**Worker** (`handlers.py`):

| Payload | Registry | Model |
|---|---|---|
| no `registry_version`, no `scoring_mode` | `CBA_REGISTRY` | `SUPERSEDED_G1_MODEL` (1.1.1) — as today |
| no `registry_version`, a mode | `CBA_REGISTRY` | the 2.0.0 model — as today; **never** "current" |
| `registry_version` given | `registry_for_version(v)`; unknown → problem → `invalid_command_payload` | `resolve_scoring_model(mode, registry=…)`; mode `None` under 3.0.0 → problem |

**Pin check.** When the payload names a `registry_version`, the resolved `model.registry_version` must
equal it, else a problem → `invalid_command_payload`. Example: pin `2.0.0-approved-oq-cba-004` with
`scoring_mode` null resolves through `CBA_REGISTRY` to `SUPERSEDED_G1_MODEL` (pin 1.1.1); that is
refused, never silently recorded as a 1.1.1 run (test W7).

Then `assert_registry_approved(registry=…)`, `assert_scoring_ready(registry=…)` (proposed → `failed_policy`
`registry_not_ready`), `weights = applied_weights(overrides, model=model, registry=registry)`,
`registry_hash = registry_fingerprint(weights, load_bands=registry.load_bands)`. The worker never reads
`load`, `explanations`, `availability` or `excluded`.

## 9. How 3.0.0 is exercised in tests without becoming the default

1. **Pure functions, no gate:** `compute_eli` with `CBA_REGISTRY_3.load_bands.table`, `assess_pool_loads`,
   `canonical_load_bands`, `registry_fingerprint`, `normalize_weights(registry=CBA_REGISTRY_3)`.
2. **Explicit selection, gate evaluated:** `tests/unit/registry_evaluation.py` (not collected) provides
   `evaluate_registry_3(monkeypatch, modules=(...))`. It wraps the `assert_registry_approved` name only
   in the modules the caller names, and only if each is already in `sys.modules`; it never imports one.
   Golden and domain unit tests name `smartmatch_domain.scoring` and `smartmatch_domain.explanation`
   only, so they never import the API or the worker. Contract and worker tests add
   `smartmatch_api.routers.match_runs` / `smartmatch_worker.handlers`, which they have already imported.
   A named module missing from `sys.modules` raises `LookupError` (a silent no-op would hide an unpatched
   gate). Only `registry is CBA_REGISTRY_3` passes; every other call goes to the real gate. Precedent: `test_scoring.py:64-65` patches the same names. Callers then pass
   `registry=CBA_REGISTRY_3` explicitly, or patch `factor_registry.CURRENT_CBA_REGISTRY` for API tests.
3. **Refusal proven without the helper:** tests 5, C3, W3 run 3.0.0 with the real gate and expect refusal.
4. **Containment:** test 7 source-scans `python/`, `services/`, `tools/` for `registry_evaluation` and
   `CURRENT_CBA_REGISTRY =` assignments outside `factor_registry.py`; both must be absent.

## 10. Golden cases G-CBA-14…19

Fixtures in `tests/golden/matching/cba/`, `registry_version` `3.0.0-approved-b26-eli` except G-CBA-18,
`owner_decisions` (T4 C9 field) naming `B26 Q1/D2`, `B26 Q7 = A`, `B26 unknown load`. Every candidate
uses G-CBA-09's evidence (sector `52`, role `finance`, topic text "corporate treasury and financial
planning" scored `0.8`, Pomona `91768`, `10.0` mi, physical), whose 2.x composite is `0.97`
(0.30 + 0.25 + 0.15 × 0.8 + 0.30; measured `repr(total) == "0.97"`). Case `as_of` `"2026-10-06"`.

Schema (`cba_case.schema.json`) gains candidate `load`: `{"capacity_hours": "<decimal string>" | null,
"engagements": [{"ref", "offset_days", "hours": "<decimal string>" | null, "confirmed", "attended",
"cancelled"}]}` and expected `load_band`, `load_reason`, `load_multiplier`, `utilization`,
`unknown_hours_refs`, and case-level expected `excluded: [{subject_id, reason}]`. The runner converts hours
with T8b's exact-microsecond helper (asserts integral µs). Utilization compared as `Decimal` values.
`REQUIRED_CASE_IDS` → `range(1, 20)`. `test_every_case_pins_the_registry_it_was_approved_under` accepts
`{REGISTRY_VERSION, REGISTRY_3_VERSION}` for scored cases, and 3.0.0 only with `owner_decisions`.
3.0.0 cases run under `evaluate_registry_3` (§9).

**G-CBA-14 — band boundaries.** Capacity `"100.0"` each; one attended engagement at `offset_days −10`.

| Subject | Hours | `u` | Band | × | `heuristic_score` |
|---|---|---|---|---|---|
| `SYNTH-CBA-14-A-U4999` | 49.99 | 0.4999 | light | 1.00 | 0.97 |
| `SYNTH-CBA-14-B-U5000` | 50.00 | 0.5 | moderate | 0.90 | 0.873 |
| `SYNTH-CBA-14-C-U7999` | 79.99 | 0.7999 | moderate | 0.90 | 0.873 |
| `SYNTH-CBA-14-D-U8000` | 80.00 | 0.8 | heavy | 0.70 | 0.679 |
| `SYNTH-CBA-14-E-U10000` | 100.00 | 1 | heavy | 0.70 | 0.679 |
| `SYNTH-CBA-14-F-U10001` | 100.01 | 1.0001 | full | — | excluded `load_full` |

Ranking `[A, B, C, D, E]`; every reason `measured`; every `registry_version` 3.0.0; formula `3.0.0-cba-load`.

**G-CBA-15 — Full removed before the solve.**

| Subject | Load | Expected |
|---|---|---|
| `SYNTH-CBA-15-FULL` | capacity 10.0; attended 12 h at −3 | full, `measured`, excluded `load_full` |
| `SYNTH-CBA-15-FULL-LOWER-BOUND` | capacity 10.0; attended 10.5 h at −3; confirmed `hours null` at +2 (`ref G15-DATE-ONLY`) | full, `full_by_known_hours`, excluded `load_full` |
| `SYNTH-CBA-15-LIGHT-1`, `-LIGHT-2` | capacity 100.0; no engagements | light, `measured`, `u 0`, 0.97 |

Ranking `[LIGHT-1, LIGHT-2]`; `excluded` = both Full in named order. Dedicated asserts:
`rank_cba_candidates(registry=CBA_REGISTRY_3)` on the Full evidence raises `ValueError` matching
`Stage A`; `inputs_fingerprint` of the kept pool equals the fingerprint of a pool that never named the
Full two (T4 test 22e's discipline).

**G-CBA-16 — a cancelled booking drops out.** Capacity 10.0.

| Subject | Engagements | Band | Score |
|---|---|---|---|
| `SYNTH-CBA-16-CANCELLED` | confirmed 4 h at +5; confirmed 6 h at +6 **cancelled** | light (`u 0.4`) | 0.97 |
| `SYNTH-CBA-16-KEPT` | same two, none cancelled | heavy (`u 1`) | 0.679 |

Ranking `[CANCELLED, KEPT]`. (The SQL half — the read never returns the cancelled row — is test L1.)

**G-CBA-17 — unknown scores neutral and is labelled.**

| Subject | Load | Band / reason | `u` | Refs | Score |
|---|---|---|---|---|---|
| `SYNTH-CBA-17-NO-CAPACITY` | capacity null; attended 30 h at −5 | unknown / `capacity_not_stated`, `measurable false` | null | `[]` | 0.97 |
| `SYNTH-CBA-17-HOURS-UNKNOWN` | capacity 100.0; attended 20 h at −5; confirmed `hours null` at +3 (`ref G17-DATE-ONLY`) | unknown / `hours_unknown`, `measurable false` | 0.2 (lower bound) | `["G17-DATE-ONLY"]` | 0.97 |

Ranking `[HOURS-UNKNOWN, NO-CAPACITY]` (tie, subject ascending). Both `multiplier "1"` in the load
block, and each score `==` the 2.0.0 score of the same evidence (float equality, not approx).

**G-CBA-18 — a 2.0.0 run stays readable and keeps its hash** (dedicated test, like G-CBA-12; fixture
pins `registry_version` 2.0.0 and `expected.registry_hash` = the three §3.5 literals).

1. `registry_fingerprint(normalize_weights(model=M), load_bands=None)` equals the literal for physical,
   virtual and G1, and equals `weights_fingerprint(...)`.
2. G-CBA-09 scored under 2.0.0 → payload has **no** `load` key; its key set equals the pre-T8c literal
   set; round trip → `load is None`, `== explanation`.
3. That payload plus `"load": null` → `ValueError`.
4. A G-CBA-14 3.0.0 payload with `load` deleted → `ValueError`.
5. `registry_for_version` resolves 1.1.1 and 2.0.0 to `CBA_REGISTRY` and 3.0.0 to `CBA_REGISTRY_3`.

**G-CBA-19 — same weights, 2.x vs 3.x → different `registry_hash`.**

1. `dict(normalize_weights(model=CBA_3_PHYSICAL_MODEL, registry=CBA_REGISTRY_3)) == dict(normalize_weights(model=CBA_PHYSICAL_MODEL))`; same for virtual.
2. `h2 = registry_fingerprint(w, load_bands=None)` = `sha256:f870192c…e4e5`; `h3 = registry_fingerprint(w, load_bands=CBA_REGISTRY_3.load_bands)`; `h3 != h2`.
3. `h3 == "sha256:73d5b67c898424c58984db49fa9542163e31438c23bed9742ecaebc50d9075f2"` (pinned) and
   `h3 == "sha256:" + sha256(LITERAL).hexdigest()` where `LITERAL` is the hand-written byte string
   `{"load_bands":{"eli_formula_version":"2.0.0","full_above":"1","heavy_from":"0.8","moderate_from":"0.5","multipliers":{"heavy":"0.7","light":"1","moderate":"0.9","unknown":"1"}},"weights":{"cba_semantic_topic":"0.15","industry_match":"0.3","proximity":"0.3","role_match":"0.25"}}`.
4. Virtual 3.x hash `!=` virtual 2.x hash and `!=` physical 3.x hash.
5. Heavy multiplier `0.70 → 0.71` moves `h3`; changing `ownership.review_status` does not; `Decimal("0.5")` vs `Decimal("0.50")` cut points hash equal.
6. Same `scoring_mode`, different `registry_version`.

## 11. TDD list

Run one file at a time: `PYTHONPATH=… $VENV/bin/pytest <file> -q`. DB tests use a private database
`smartmatch_b26_t8c`, dropped afterwards. CI proves the suite.

**Unit — `tests/unit/test_factor_registry.py` (appended section; existing tests unedited)**

1. `test_registry_3_is_declared_proposed` (version, `status "proposed"`, approver/date `None`).
2. `test_registry_3_declares_engagement_load_as_weight_zero_penalty_in_no_model`.
3. `test_current_registry_is_2_0_0` (`current_cba_registry() is CBA_REGISTRY`; `REGISTRY_VERSION` literal).
4. `test_superseded_and_proposed_sets_derive_from_current` (T8c: `{1.1.1}` / `{3.0.0}`; with `current=CBA_REGISTRY_3`: `{1.1.1, 2.0.0}` / `{}`).
5. `test_registry_3_fails_the_approval_gate_and_passes_readiness`.
6. `test_an_approved_copy_cannot_borrow_the_3_0_0_pin` (replace-copy with `status "approved"` → both gates refuse); `test_the_3_0_0_pin_is_never_unregistered`.
7. `test_no_production_module_imports_the_evaluation_helper_or_reassigns_current` (source scan).
8. `test_registry_fingerprint_without_bands_is_weights_fingerprint` (the three §3.5 literals).
9. `test_registry_invariants` (parametrized: spec without bands; bands without spec; spec in a model; weight ≠ 0; ELI version mismatch → `ValueError`).
10. `test_toy_exercise_and_cba_registries_are_unchanged_by_the_new_field`: `load_bands is None`; each registry `==` a `dataclasses.replace` copy of itself and the two copies hash equal. No fixed `hash()` value is asserted (string hashing is salted per process).

**Unit — `tests/unit/test_load_bands.py` (new)**

11. `test_ownership_rejects_blank_fields_and_bad_date`.
12. `test_canonical_load_bands_normalizes_decimals` (hand-written dict equality).
13. `test_assess_pool_loads_reads_no_default_capacity` (absent key and `None` → `capacity_not_stated`).
14. `test_assess_pool_loads_uses_one_as_of_for_every_subject`.
15. `test_stage_a_load_excluded_is_full_only` (each band; `None`).

**Unit — `tests/unit/test_match_run_pins.py`**

16. `test_registry_fingerprint_requires_the_keyword` (`TypeError` without `load_bands`).
17. `test_registry_fingerprint_with_bands_differs_and_is_order_independent`.

**Unit — `tests/unit/test_scoring_load.py` (new)**

18. `test_2_x_scoring_refuses_a_load`; `test_3_x_scoring_requires_a_load`.
19. `test_full_cannot_reach_stage_b`.
20. `test_multiplier_applies_to_the_unrounded_composite` (Moderate `0.873`, Heavy `0.679`).
21. `test_light_and_unknown_equal_the_2_x_value_bit_for_bit`.
22. `test_unknown_factor_keeps_none_and_still_records_the_load`.
23. `test_formula_version_moves_only_under_3_x`.
24. `test_eli_formula_mismatch_is_refused`.
25. `test_score_cba_candidate_calls_zero_argument_gates_on_the_cba_path` (the `test_scoring.py` seam holds).

**Unit — `tests/unit/test_explanation.py`**

26. `test_2_x_payload_has_no_load_key_and_reads_back_none`.
27. `test_3_x_load_block_round_trips_exactly` (Decimals as strings).
28. `test_load_block_is_refused_not_repaired` (parametrized: number instead of string; bad band; `measurable` mismatch; multiplier ≠ table; heuristic ≠ `round(composite × m, 6)`; `load` on 2.x; missing on 3.x; unknown version → `ValueError`).

**Golden — `tests/unit/test_cba_matching_golden.py`**

29. `test_g_cba_14_band_boundaries` … `test_g_cba_19_same_weights_different_registry_hash` (§10), plus the parametrized runner over the new fixtures.

**Integration — `tests/integration/test_engagement_load_read.py` (new, Postgres, private DB)**

- L1 `test_a_cancelled_booking_is_never_returned` (cancel through T8a's `cancel_booking`).
- L2 `test_unconfirmed_journeys_are_not_returned`.
- L3 `test_prefilter_matches_the_domain_window` (events at −46, −45, −1, 0, +44, +45 via the events repository; the prefilter returns exactly −45 … +44, and `compute_eli` agrees).
- L4 `test_event_time_maps_to_duration` (exact with end → exact `timedelta`; exact without end, `date_only` → `None`).
- L5 `test_a_journey_naming_no_event_is_unresolved`.
- L6 `test_unresolved_events_are_always_returned`.
- L7 `test_another_tenants_rows_are_invisible`.
- L8 `test_another_units_booking_counts` (OQ2).
- L9 `test_one_query_for_two_hundred_subjects` (`before_cursor_execute` count; empty input → 0).

**Integration — `tests/integration/test_match_run_command_path.py`**

- W1 `test_a_payload_without_registry_version_pins_2_0_0_and_the_literal_hash`.
- W2 `test_an_explicit_2_0_0_pin_writes_the_identical_row` (every pin, `weights`, `inputs_hash`).
- W3 `test_a_3_0_0_pin_fails_policy_while_proposed` (`registry_not_ready`, no row).
- W4 `test_an_unknown_pin_is_an_invalid_payload`; W5 `test_3_0_0_with_no_mode_is_an_invalid_payload`.
- W6 `test_under_evaluation_3_0_0_fingerprints_the_band_table` (helper §9).
- W7 `test_a_pin_its_mode_does_not_resolve_to_is_an_invalid_payload` (pin 2.0.0 + mode null → `invalid_command_payload`, no row; never a 1.1.1 run).

**Contract — `tests/contract/test_match_runs_api.py`**

- C1 `test_create_scores_under_2_0_0_and_reads_no_engagements` (payload pin, no `load` keys, T4's query count).
- C2 `test_under_evaluation_create_removes_full_and_stores_load_blocks` (Full in `excluded` with `load`; Moderate utility `0.873`; payload pin 3.0.0; worker row `registry_hash == registry_fingerprint(weights, bands)`; then `GET` the run and assert `excluded` renders the Full subject with reason `load_full` and its `load` object present **with no `unknown_hours_refs` key**, while the stored `job.payload` `excluded[].load` still carries `unknown_hours_refs` — use the G-CBA-15 lower-bound subject so the stored list is non-empty, `["<its pipeline_record id>"]`).
- C3 `test_a_proposed_current_registry_fails_closed` (patch current only → 503 `registry_not_ready`, no job).
- C4 `test_3_0_0_create_costs_one_more_query_than_2_0_0`.
- C5 `test_cancelling_a_booking_lowers_the_band_on_the_next_run`.
- C6 `test_a_stored_2_0_0_run_reads_unchanged_after_current_is_switched` (same `registry_hash`, explanations, no `load`).
- C7 `test_the_availability_and_load_as_of_are_the_same_date`.
- C9 `test_the_run_read_never_carries_unknown_hours_refs` (under the helper: a run whose stored payload has non-empty `unknown_hours_refs` in both an explanation and an `excluded` entry; walk the whole `GET` JSON and the `202` JSON recursively and assert no key named `unknown_hours_refs` appears anywhere).
- C8 `test_a_flipped_unapproved_current_registry_does_not_block_stored_run_reads` (store a 2.0.0 run; patch current to the proposed 3.0.0 **without** the helper; `GET` → 200, same `registry_hash`, explanations readable; `POST` → 503).

## 12. Commit milestones (red → green)

Each milestone is two commits: tests red, then code green. Red for new modules is a collection
`ImportError`; the commit body quotes the error line. `ruff check` + `ruff format` on every touched file.

| # | Red commit | Green commit | Tests green |
|---|---|---|---|
| 1 | — | `docs: T8c ADR-0027 (proposed), supersession record, parent-plan sync` (re-measure §3.5 literals first) | — |
| 2 | `test: registry 3.0.0 declaration and hash coverage (red)` | `feat: registry 3.0.0 declared proposed with band table and hash coverage` (files 1–3) | 1–17; `test_factor_registry.py`, `_parameterised.py`, `test_exercise_registry*.py` unedited and green |
| 3 | `test: load multiplier and explanation load block (red)` | `feat: load multiplier in CBA scoring and explanation load block` (files 4–6) | 18–28; `test_scoring.py`, `test_explanation.py`, G-CBA-01…13 green |
| 4 | `test: golden G-CBA-14..19 (red)` | `feat: golden runner evaluates registry 3.0.0 explicitly` (runner, schema, helper) | 29 |
| 5 | `test: engagement load read (red)` | `feat: engagement load read from pipeline_record and event` (file 7) | L1–L9 |
| 6 | `test: worker pins the registry from the payload (red)` | `feat: worker resolves the payload registry and fingerprints its band table` (file 11) | W1–W7 |
| 7 | `test: create under the current registry and 3.0.0 evaluation (red)` | `feat: create reads load, removes Full before the solve, stores load blocks` (files 8–10, 12, 13) | C1–C9; T4's contract tests unedited and green |
| 8 | — | push; PR `feat: B26 T8c registry 3.0.0 (proposed)` against `main`, draft until T4 and T8b merge | — |

## 13. The flip (after approval; not T8c)

| Step | Change | Who |
|---|---|---|
| A. Approve | `CBA_REGISTRY_3`: `status="approved"`, `approver=…`, `approved_on=…`; `ownership.review_status=REVIEWED` once IA West reviews (§10 row 3); ADR-0027 → Accepted | owner + IA West |
| B. Make current | the one line in §0 | owner-approved PR |
| C. Same PR as B | update: `tests/unit/test_factor_registry.py` tests 3 (`current_cba_registry() is CBA_REGISTRY_3`) and 4 (superseded `{1.1.1, 2.0.0}`, proposed `{}`); tests that assert a **new** run carries `REGISTRY_VERSION` (`tests/contract/test_match_runs_api.py`, `tests/integration/test_match_run_command_path.py` create-path rows); C3 becomes a post-approval create test. G-CBA-01…19 need no edit (domain defaults stay 2.0.0) | implementer |

B without A answers `503 registry_not_ready` on create (C3). After B: new runs pin 3.0.0; 1.1.1 and
2.0.0 runs read at their own pins, unchanged; `SUPERSEDED_REGISTRY_VERSIONS` becomes the parent's set.

## 14. Contradictions and open questions

**Resolved by the guardrail**

| # | Parent says | T8c does | Why |
|---|---|---|---|
| C1 | §5.2 item 4: `SUPERSEDED_REGISTRY_VERSION` becomes a set of 1.1.1 and 2.0.0 | Keeps the `str`; adds derived `SUPERSEDED_REGISTRY_VERSIONS` = `{1.1.1}` now, the parent's set after the flip | 2.0.0 is still current; the `str` pins `SUPERSEDED_G1_MODEL` and 43 references |
| C2 | §5.2 item 3: `REGISTRY_VERSION` → 3.0.0 once approved | `REGISTRY_VERSION` stays 2.0.0's identity; `CURRENT_CBA_REGISTRY` is what moves | Retargeting it re-labels every stored 2.0.0 run (§3.4) |
| C3 | §7 row 11 names only `test_factor_registry.py` | Adds scoring, explanation, read, worker and contract tests | The penalty, block and read are T8c's too (§8 T8c row) |

**Decided (orchestrator, 2026-09-23: all five as recommended)**

| # | Question | Ruling |
|---|---|---|
| OQ1 | Version string while proposed: parent's `3.0.0-approved-b26-eli`, or `3.0.0-proposed-b26-eli` renamed at approval? | **Keep the parent's string.** The gate refuses it until `status` flips, so no stored run can carry it early; renaming at approval would move every 3.0.0 fixture. |
| OQ2 | Load read scope: tenant-wide, or only the run's unit? | **Tenant-wide.** Load is the person's, not the unit's. Numbers stay in the stored payload; screens show a band word only (OQ-CBA-005, T8d). |
| OQ3 | A confirmed journey whose `opportunity_event_id` names no event row. | **Unresolved → unknown hours** (R4's rule). Never dropped, never 0 (ADR-0011). Legacy-only: new journeys are checked (`UnknownOpportunityEventError`). |
| OQ4 | Order of `load_full` among Stage A reasons. | **After `filed_this_request`, before classification checks.** Full decides the outcome whatever the record says; a Connector should not fix a classification for someone who cannot be invited. |
| OQ5 | `factor_registry.py` is 1,120 lines; T8c adds ~130. | **Ship T8c as planned**; open a follow-up card to split the lineage and 3.0.0 declaration into their own module once the flip lands. |

## 15. Plan-gate findings applied (2026-09-23)

| # | Sev | Finding | Where |
|---|---|---|---|
| 1 | MED | Read route gates on the run's own pin, never the current registry | §2 row 10, §8 Read, test C8 |
| 2 | MED | Worker refuses a pin its resolved model does not carry | §8 Pin check, test W7 |
| 3 | LOW | Evaluation helper patches only named modules already in `sys.modules` | §9 item 2 |
| 4 | LOW | Flip list names `test_factor_registry.py` tests 3 and 4 | §13 row C |
| 5 | LOW | C2 reads the run back via `GET`; `excluded` renders `load` | §2 rows 10 and 13, §8 Read, test C2 |
| 6 | LOW | Window bounds computed in Python, bound as two dates | §4 |
| 7 | LOW | Test 10 asserts equality and equal-copies-hash-equal; G-CBA-19 digest pinned | §11 test 10, §10 G-CBA-19 step 3 |
| 8 | Ruling | `unknown_hours_refs` stay in the stored payload, never on the API wire: `LoadBlockView` has no refs field; `_to_view` drops them | §2 rows 10 and 13, §8 Read, tests C2 and C9 |

**Follow-up card (OQ5):** `B26-FU-REGISTRY-SPLIT` — after the flip lands, move the CBA lineage,
`CURRENT_CBA_REGISTRY` and the 3.0.0 declaration out of `factor_registry.py` (1,120 lines + ~130) into
their own module, behaviour-preserving, with `test_factor_registry*.py` green unedited. Not T8c.

---

**Next action (under two minutes):** run `git log --oneline origin/main..origin/feat/b26-t4` and check that T4 milestone 6 is pushed.
