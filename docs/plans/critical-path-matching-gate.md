# Critical path: matching gate G1 and R1 matching work

**IDs:** CP-G1, CP-MATCH
**Parent:** [critical-path-plans.md](critical-path-plans.md)

Matching is the product. Everything in this file waits on a person who is not
engineering, then becomes a long engineering sequence that must not start
against the legacy's broken scores.

Planning only.

---

## 1. CP-G1 — Approve the registry (D1 / F-001 / MM-002)

### (a) What / where

At legacy `bdce024`, `FACTOR_REGISTRY` declares **9** factors (weights sum to
1.00) and `compute_match_score` computes **7**. Normalization divides by nine;
the two missing factors' weight mass is discarded. Maximum attainable
`total_score` is **0.90**. Relative ranking is not even uniformly deflated
unless the missing factors would have scored identically for every candidate.

Contract v1.1 already gates R1 on registry approval (G1). The contract review
quantified the defect that gate exists to catch.

Sources:

- `docs/architecture/review/contract-findings.md` F-001 (**BLOCKER** for the
  matching slice only; Foundation scaffold still PASSed)
- `docs/plans/remaining-foundation-r1-work.md` D1, M1–M10
- `docs/migration/migration-manifest.yaml` MM-002 `blocked_contract`
- `docs/architecture/review/stakeholder-test-log-audit.md` kickoff Q1
- `docs/plans/stakeholder-audit-integration.md` §9 Q6
- `python/smartmatch_domain/smartmatch_domain/factor_registry.py`
  (`REGISTRY_STATUS = "proposed"`, `assert_registry_approved()`)

The seven factors the stakeholder was shown must be mapped onto the nine
proposed. MM-002 amendment (25 Aug 2026):

- `calendar_fit` → `availability` (Stage A)
- `historical_conversion` and `student_interest` — **no target, no decision**
- Required golden cases: exact 43% tie; "Topic Relevance 0%" on an AI event;
  "Match Depth 0"
- Per ADR-0011, each of those zeroes is either a measured zero or unknown
  wearing a zero; the golden case must pin which

### (b) Status

Registry proposal is committed. Scoring fails closed. Characterization against
legacy outputs is **forbidden** — pinning them would enshrine the 10%
deflation. MM-002 `reviewer: pending`, `blocking_owner: program owner`.

Open decision 2 (ELI parameters) is **not** this gate. D2 blocks R1 *tuning*,
not R1 *delivery* (`remaining-foundation-r1-work.md`). F-9 on PR1 made
"completed only" explicit; whether committed future load counts is D2, not G1.

Open decision 6 (route-matrix terms) blocks **M4** only, not G1.

### (c) Execution plan

**Not engineering until step 5.**

1. Name the G1 owner if "program owner" is not a specific person. D1 cannot
   start as a Slack rumour.
2. Workshop contents: which of the nine proposed survive; fate of
   `historical_conversion` and `student_interest` (return, drop, or rename into
   an existing factor). Record either way — silence is the current defect (Q6).
3. Agree the golden case set **before any scoring code**. Include the three
   stakeholder symptoms with an explicit unknown-vs-zero call per ADR-0011.
4. Agree weight-set governance: who may change weights, shadow-mode (MM-005 /
   F-25 application semantics belong here as a consumer decision).
5. Engineering: M1 — flip `REGISTRY_STATUS` to `approved` in a reviewed
   commit; land golden cases; invert `test_registry_is_not_yet_approved`
   deliberately (`remaining-foundation-r1-work.md` M1).
6. Move MM-002 off `blocked_contract` only after M1. Port scoring against the
   **new** golden set, not the legacy engine.

### (d) Dependencies

Blocked on a named program owner. Blocks M1–M10, W5 (control center), F-25
settlement, S12 funnel (matched stage). Does not block CP-PR1, A5, F9
re-review.

### (e) Acceptance

- [ ] Written approval (commit, ADR amendment, or signed note in
      `docs/architecture/`) of factor list + weights + golden cases.
- [ ] Q6 answered in MM-002 notes.
- [ ] `REGISTRY_STATUS == "approved"`; `assert_registry_approved()` no-ops.
- [ ] Golden cases in CI; at least the three stakeholder symptoms.
- [ ] `test_only_one_scoring_factor_is_implemented_today` / skip on
      `test_normalize_weights_honours_overrides_and_renormalizes` revisited as
      soon as a second scoring factor lands (the skip is a tripwire).
- [ ] MM-002 status no longer `blocked_contract`.

### (f) Priority

Start the conversation **in parallel with CP-PR1**. It is the longest pole
(`remaining-foundation-r1-work.md` D1; PR1 handoff §5 item 4). Do not wait for
A5.

---

## 2. CP-MATCH — M1–M10 after the gate

### (a) What / where

`remaining-foundation-r1-work.md` "R1 — Matching foundation". v1.1 §1.2–1.3,
§5.3. LLM never solves the schedule (M7).

OpenAPI today has no matching routes. Adding them is part of M8/M9, with
`tools/export_openapi.py --check` in CI.

### (b) Status

Not started, except ELI (MM-003) and the registry proposal. ELI still
`ported_unverified` until CP-REREVIEW; it can be *used* as a library before
the manifest is `verified`, but do not treat that as G1.

### (c) Execution plan (dependency order)

| # | Item | Files / notes |
|---|---|---|
| M1 | Flip registry + golden set | `factor_registry.py`, `tests/unit/test_factor_registry.py` |
| M2 | `topic_relevance` | Embeddings only as feature inputs with provenance + golden/shadow tests. No unlabeled model output (DESIGN.md §1.1). |
| M3 | `role_fit` | Legacy alias/fuzzy is a starting point, **not a port**. Needs goldens. |
| M4 | `travel_burden` | Needs D3 (route-matrix terms + per-run budget). Interim: straight-line, labelled "estimate quality: coarse". Never fabricate mileage (v1.1 §3.6 N1). Fixture adapter already exists in `smartmatch_providers`. |
| M5 | `repeat_penalty` | Feeds V6 (repeatedly selected vs underutilized). |
| M6 | Stage A eligibility | Four eligibility factors declared, unimplemented. Must apply ELI hard cap separately from Stage B penalty (v1.1 §1.3; M9 will explain both). |
| M7 | Stage B CP-SAT | OR-Tools. Not an LLM. |
| M8 | Immutable `match_run` | Snapshot: inputs, eligibility policy, registry, weight set, optimizer version, route-estimate timestamp. F-25 application semantics must be decided before weights are applied. |
| M9 | Explanations | Per-factor and per-penalty; hard cap vs soft penalty shown separately. |
| M10 | Scenario comparison | Six objectives, v1.1 §5.3. |

Also needed when M8 exists: persist via the durable command path (J2 pattern),
not in request memory (F-005 / MM-A02 already archived that habit).

**Do not** port `src/matching/engine.py`. Characterization is impossible
(MM-002 `characterization_tests`).

### (d) Dependencies

```
D1 (G1) ──► M1 ──► M2, M3, M4, M5, M6 ──► M7 ──► M8 ──► M9, M10
                M4 also needs D3
W5 needs M8 + D-0 + W2 + W4
```

CP-A1B needed before match runs execute on a real worker, not before domain
tests.

### (e) Acceptance

- [ ] Every implemented scoring factor has golden cases; unimplemented factors
      have weight 0 or are absent from the approved registry — never silently
      dropped during normalize (the F-001 shape).
- [ ] `normalize_weights` ranges over exactly the implemented scoring factors
      (`test_implemented_scoring_weights_sum_to_one` stays true).
- [ ] Stage A cap cannot be moved by display rounding (F-6 discipline).
- [ ] `match_run` rows are immutable; version pins recorded.
- [ ] OpenAPI documents the new command routes; TS client still generated
      (W2), never hand-written.
- [ ] No demo-mode fallback scores (scanner `fabricated-score`).

### (f) Priority

After G1. Do not start M7 against a `proposed` registry.

---

## 3. Adjacent decisions that look like matching but are not G1

| ID | What | When |
|---|---|---|
| D2 | ELI half-life, window, caps; committed vs completed (F-9) | Tuning; can ship M6 with proposed defaults labelled proposed (`eli.py` already does). |
| D3 | Route-matrix provider | M4 only. |
| F-25 | Proposal vs applied weights | Before M8 applies a `WeightProposal`. |
| ADR-0011 | Accountable numbers | Golden cases for 0% / 0 depth; later S1 register. |
| MM-003 re-review | ELI manifest | Parallel; not a G1 prerequisite. |
