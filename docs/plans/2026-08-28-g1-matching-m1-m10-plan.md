# Implementation plan — G1 matching, M1–M10

**Date:** 2026-08-28 · **Plan id:** P5 · **Worktree branch:** `plan/g1-matching`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.

## Standing constraints (restated; permanent)

- **Never port or characterize the legacy scoring engine.** Its maximum
  attainable score is 0.90 (nine declared factors, seven computed); any
  characterization enshrines the defect.
- ADR-0011: unknown and zero are distinct everywhere, including golden cases.
- No user-visible score, rank, match run, or matching UI reaches any surface
  before this plan's stop-gate passes; every scoring path calls
  `assert_registry_approved()`.
- No push, no PR, no production-readiness claims.

## Stop-gate (verify before card M1)

Required artifact: a committed D1/G1 decision document (expected under
`docs/decisions/`), ratified or signed by a **named IA West program owner**
(the repository's self-assigned interim owner does not qualify). It must
contain, non-blank:

1. the named program owner;
2. the approved factor list and weights, including the explicit fate of
   `historical_conversion` and `student_interest` (Q6);
3. approved golden cases with expected outputs, classifying the three
   stakeholder symptoms — the 43% tie, "Topic Relevance 0%", "Match Depth 0" —
   each zero labeled measured-zero or unknown per ADR-0011;
4. weight governance: who may change approved weights, and how changes are
   recorded.

`docs/plans/workshops/g1-factor-registry-workshop-packet.md` is preparation,
not approval. `docs/decisions/pilot-decisions.md` explicitly says D1 is
tentative. `tests/unit/test_gate_decision_artifacts.py` checks packet
completeness — passing it does not signify approval. If any field is missing
or tentative: **stop and report "G1 artifact missing or incomplete."**

## Current state (verifiable)

- `python/smartmatch_domain/smartmatch_domain/factor_registry.py`:
  `REGISTRY_STATUS = "proposed"` (~line 59); `assert_registry_approved()`
  raises `RegistryNotApprovedError` (~lines 256–272). Only `engagement_load`
  is marked implemented.
- Guard tests that must flip **deliberately, in the approval-landing commit**:
  `tests/unit/test_factor_registry.py::test_registry_is_not_yet_approved`,
  the proposed-status assertions in `tests/unit/test_matching_fail_closed.py`,
  and its OpenAPI scan rejecting match/score/rank routes (that scan changes
  only in card M8b when routes actually land).
- No match/score/rank operation exists in `contracts/openapi/smartmatch.json`.
- Legacy UI surfaces are gated at `69611b2`; they stay gated until M9.

## Task cards

### Card M1 — approval landing (sequential; nothing runs before it)

- **Fence:** `factor_registry.py`, `tests/unit/test_factor_registry.py`,
  `tests/unit/test_matching_fail_closed.py` (status assertions only), MM-002
  reference doc, new golden fixtures directory
  `tests/golden/matching/` (or the repo's existing golden layout).
- **Work:** copy the approved factors/weights exactly from the artifact — no
  interpretation; set the approved registry version; land approved golden
  cases as fixtures; cite the decision artifact path in the module header.
  **Two-stage status — scoring stays fail-closed until M6j:** M1 sets
  `REGISTRY_STATUS = "approved_pending_implementation"` (new value), and
  `assert_registry_approved()` continues to raise for it. Only card M6j —
  after proving every approved scoring factor is implemented and weights
  normalize over the complete approved set — flips the status to
  `"approved"` and inverts `test_registry_is_not_yet_approved` into
  `test_registry_is_approved_at_version_X`, in that same M6j commit. M1
  instead updates the guard test to assert the intermediate status still
  refuses scoring. This prevents the window where an "approved" registry
  could score using only a subset of the approved factors.
- **Hard rule:** weights must normalize to 1.0 over exactly the approved
  *implemented* factor set at every stage of M2–M6 (re-normalization is
  computed, never hand-tuned); a factor without an implementation carries no
  silent weight.

### Cards M2–M6 — factor implementations (parallel lanes after M1)

One lane per approved factor (or small factor cluster sharing inputs). Every
lane has the same shape:

- **Fence:** one new module
  `python/smartmatch_domain/smartmatch_domain/factors/<factor>.py` plus its
  test file; a shared join card owns the registry wiring table so lanes never
  edit `factor_registry.py` concurrently.
- **Work:** pure function from typed evidence inputs to a score component;
  missing evidence returns unknown (`None`), never 0; each factor's approved
  golden rows pass.
- **D3 caveat:** if `travel_burden` is approved but D3 route-matrix terms are
  not, implement it returning unknown with a documented reason — never
  fabricate mileage.
- **Join card M6j:** wire implemented factors into the registry table, flip
  each factor's `implemented` flag, add a readiness assertion that the
  implemented set equals the approved scoring-factor set exactly, then — and
  only then — set `REGISTRY_STATUS = "approved"`, perform the deliberate
  guard-test inversion (see M1), assert normalization over the complete
  approved set, and run the full golden suite.

### Card M7 — portfolio optimization (after M6j)

- **Fence:** new `python/smartmatch_domain/smartmatch_domain/optimizer.py` +
  tests; add the CP-SAT dependency through the repo's pinned dependency
  process (lock refresh is part of this card).
- **Work:** CP-SAT model for portfolio assignment — **never an LLM**.
  Deterministic given identical inputs and seed; solver version recorded in
  the result object.

### Card M8 — match_run persistence (after M7; serial migration resource)

- **M8a fence:** new migration under `db/migrations/versions/` (number
  assigned by the portfolio index's migration owner),
  `python/smartmatch_persistence/smartmatch_persistence/schema.py`, unit +
  integration tests.
  Immutable `match_run` snapshot rows: inputs hash, registry version, weights,
  optimizer + route-estimate version pins, tenant/unit scoping, created-at.
  Executed through the existing durable-command path (transactional outbox per
  ADR-0005); progress emission keeps `_emit`'s separate session untouched.
- **M8b fence:** `services/api/smartmatch_api/routers/` new match-run routes,
  `tests/authz/test_policy_matrix.py` rows for every new operation,
  `tests/contract/` route tests, OpenAPI regeneration (`make openapi-check`).
  Update the fail-closed OpenAPI scan in the same commit the routes land —
  that is its deliberate flip. Roles per the decision artifact; if it names
  none, stop and request the roles rather than guessing.

### Cards M9/M10 — explanations and UI (after M8)

- **M9 fence:** domain explanation assembly + API response fields; every
  displayed score carries registry version and the provenance label
  "heuristic score" per the artifact's wording.
- **M10 fence:** `apps/web/legacy-frontend` matching surfaces — replace the
  G1-gate explanations with real data honestly labeled; scenario comparison
  reads two persisted `match_run` snapshots. The Fix #7A/A1b rules hold: no
  browser-asserted identity; if plan P2 has not landed, matching UI stays
  behind whatever identity mechanism exists without weakening it.

## Evidence ladder

1. Per-card focused pytest; golden suite green from M1 onward
2. `make check`; `make openapi-check` after M8b
3. Web typecheck/build after M10
4. **CI-only proof:** migration + integration tests on PostgreSQL (M8a),
   full contract suite, web build. Local Windows runs do not prove these.

## Done means

- Every approved golden case passes; unknown/zero distinction is testable.
- `match_run` snapshots are immutable and version-pinned.
- Policy matrix covers every new operation; OpenAPI matches committed contract.
- No surface shows a score without registry version + heuristic provenance.
- The decision artifact is cited from code, tests, and this plan's closing note.
