# G1 factor-registry workshop packet

**Status:** preparation only — does not approve the registry or authorize scoring.  
**Gate:** D1 / G1 (`docs/plans/critical-path-matching-gate.md`, MM-002).  
**Blocking owner:** program owner (name TBD — see `docs/decisions/pilot-decisions.md` D1).

## Purpose

Give the program owner everything needed to close gate G1 in one workshop:
factor list, weights, golden cases, and Q6 (`historical_conversion` /
`student_interest`). Engineering must not flip `REGISTRY_STATUS` or port scoring
until this packet yields a written, reviewable approval.

## Current fail-closed state (do not change in prep)

| Artifact | State |
|---|---|
| `python/smartmatch_domain/smartmatch_domain/factor_registry.py` | `REGISTRY_STATUS = "proposed"` |
| `assert_registry_approved()` | raises `RegistryNotApprovedError` until approved |
| `tests/unit/test_factor_registry.py::test_registry_is_not_yet_approved` | must fail until G1 closes |
| OpenAPI (`contracts/openapi/smartmatch.json`) | no match/score routes |
| Legacy scoring engine | archived — port forbidden (MM-002 `blocked_contract`) |

## Legacy defect the workshop must not reproduce

The legacy baseline declared **9** factors (weights sum 1.00) but computed only
**7**, capping every score at **0.90**. Characterization against legacy outputs
is forbidden — it would enshrine the defect (`migration-manifest.yaml` MM-002).

The proposed registry separates `proposed_weight` from `active_weight` so
unimplemented factors contribute **no** denominator mass
(`tests/unit/test_factor_registry.py::test_implemented_scoring_weights_sum_to_one`).

## Proposed factor inventory (workshop agenda item 1)

Source: `PROPOSED_FACTORS` in `factor_registry.py`.

| Key | Label | Stage | Proposed weight | Implemented today |
|---|---|---|---|---|
| `topic_relevance` | Topic Relevance | B suitability | 0.30 | no |
| `role_fit` | Role Fit | B suitability | 0.25 | no |
| `travel_burden` | Travel Burden | B penalty | 0.20 | no |
| `engagement_load` | Engagement Load Index | B penalty | 0.15 | **yes** (`smartmatch_domain.eli`) |
| `repeat_penalty` | Repeat Selection Penalty | B penalty | 0.10 | no |
| `availability` | Availability / Blackout | A eligibility | 0 | no |
| `credential_check` | Credential and Background Check | A eligibility | 0 | no |
| `contact_status` | Contact Confidence State | A eligibility | 0 | no |
| `declared_cap` | Declared Capacity Cap | A eligibility | 0 | no |

**Recorded mapping (MM-002 amendment 25 Aug 2026):** legacy `calendar_fit` →
`availability` (Stage A). No other legacy→proposed mapping is decided.

## Q6 — factors with no target (workshop agenda item 2)

Stakeholder audit §9 Q6 (`docs/plans/stakeholder-audit-integration.md`):

| Legacy factor | Proposed target | Decision required |
|---|---|---|
| `historical_conversion` | none | return / drop / rename into existing? |
| `student_interest` | none | return / drop / rename into existing? |

Silence is the current defect. The workshop must record **either** answer.

## Golden cases — required before any scoring code (agenda item 3)

Per ADR-0011 and MM-002, three stakeholder symptoms become required golden
cases. Each zero must be classified as **measured zero** or **unknown** — the
legacy did not distinguish them.

| ID | Symptom (stakeholder test log) | Workshop must decide |
|---|---|---|
| `G1-GC-001` | Exact **43% tie** between candidates | tie-break rule; inputs that reproduce the tie |
| `G1-GC-002` | **Topic Relevance 0%** on an event about AI | measured zero vs unknown for the 0% |
| `G1-GC-003` | **Match Depth 0** | measured zero vs unknown for depth |

**Input-only fixtures** (no expected scores) live under
`tests/golden/matching/symptoms/`. Structure is validated by
`tests/golden/matching/golden_case.schema.json` and
`tests/unit/test_matching_golden_case_schema.py`.

## Weight governance (agenda item 4)

Decide and record:

1. Who may change approved weights after G1 closes.
2. Whether shadow-mode evaluation (MM-005) applies before weight changes ship.
3. Registry version pinning for `match_run` snapshots (M8 — post-G1).

## Workshop outputs (required to unblock engineering)

Commit **one** of:

- ADR amendment or signed note under `docs/architecture/decisions/`, **or**
- Updated `docs/decisions/pilot-decisions.md` with named owner + approved list.

Must include:

- [ ] Surviving factor keys and final weights (sum 1.0 over implemented scoring factors).
- [ ] Q6 answered for `historical_conversion` and `student_interest`.
- [ ] Golden case set with unknown-vs-zero classification for each symptom zero.
- [ ] Named program owner for ongoing weight governance.

## Engineering sequence after approval (not this packet)

1. **M1:** flip `REGISTRY_STATUS` to `"approved"`; invert
   `test_registry_is_not_yet_approved` deliberately; land scored golden cases.
2. **M2–M6:** implement approved factors only.
3. **M7:** CP-SAT portfolio optimization (never LLM).
4. **M8–M10:** `match_run` snapshots, explanations, scenario comparison.

See `docs/plans/remaining-foundation-r1-work.md` M1–M10.

## References

- `docs/plans/critical-path-matching-gate.md`
- `docs/migration/migration-manifest.yaml` (MM-002)
- `docs/architecture/review/contract-findings.md` (F-001)
- `docs/architecture/decisions/ADR-0011-accountable-numbers.md`
- `python/smartmatch_domain/smartmatch_domain/factor_registry.py`
- `tests/unit/test_factor_registry.py`
