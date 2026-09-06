# D6 — rewards budget owner: decision record

**Status:** **CLOSED — 2026-09-02 (pilot scope).** Danny Tran (@dangt) named
institutional budget owner. **$5,000** placeholder ceiling ratified pending
institutional funding confirmation — **not** a ratified figure. IA West
Coordinator remains operational administrator. D7 remains tentative and is
**not** promoted by this record.
**Gate:** P7 — D6/D7 rewards (`docs/plans/prep/blocked-work-register-830.md`
§"P7 — D6/D7 rewards"; `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`
Stop-gate item 1).
**Formal decider:** Danny Tran (@dangt), rewards budget owner — named
2026-09-02.
**Session direction (31 August 2026):** recorded in
`docs/decisions/pilot-decisions.md` §"D6 — session-recorded working direction
(31 August 2026)", closed for pilot scope and formalized below.

This record does not build anything. It formalizes the D6 working direction
already recorded in `docs/decisions/pilot-decisions.md` §D6, and it is the
"formal D6 record" that record and
`docs/decisions/2026-08-31-session-ratification.md` (row "P7 D6/D7") both
point to. Deliverable 2 — schema/append-only verification of the rewards
tables already authorized by migration `0009` — is recorded separately in
`docs/testing/d6-p7-rewards-schema-verification.md`.

---

## 1. Budget ownership

**Decision:** Danny Tran (@dangt) is named the **institutional budget owner**
for the rewards program, effective 2026-09-02.

- Source: `docs/decisions/pilot-decisions.md` §D6 — "**Ratification status:**
  **CLOSED — 2026-09-02 (pilot scope).** Danny Tran (@dangt) named as
  institutional budget owner."
- Confirmed by `docs/decisions/2026-08-31-session-ratification.md`, matrix row
  "P7 D6/D7": "Danny Tran (@dangt), budget owner — D6 closed 2026-09-02" /
  "Institutional budget owner: Danny Tran; operational control with IA West
  Coordinator."
- Confirmed by `docs/plans/prep/blocked-work-register-830.md` §0 row 5:
  "**Rewards budget owner (D6)** … **Named 2026-09-02** — Danny Tran (@dangt);
  $5k placeholder. D6 **closed** for pilot scope."

## 2. Operational administration

**Decision:** The **IA West Coordinator** remains the **operational
administrator** of the rewards program. Naming a budget owner does not move
day-to-day administration off the Coordinator role.

- Source: `docs/decisions/pilot-decisions.md` D1–D9 table, row D6: "IA West
  Coordinator operational administrator."
- Source: `docs/decisions/pilot-decisions.md` §D6: "IA West Coordinator
  remains operational administrator."
- Source: `docs/decisions/2026-08-31-session-ratification.md` row "P7 D6/D7":
  "operational control with IA West Coordinator."

## 3. The $5,000 placeholder ceiling

**Decision:** A **$5,000** placeholder ceiling is recorded, **ratified
pending institutional funding confirmation**.

**This is explicitly not a ratified figure.** Two things are true at once and
neither cancels the other: the ceiling is written down so work can proceed
against something concrete, and it carries no institutional funding behind
it yet.

- Source: `docs/decisions/pilot-decisions.md` D1–D9 table, row D6: "**$5,000**
  placeholder ceiling (pending institutional funding confirmation)."
- Source: `docs/decisions/pilot-decisions.md` §D6: "$5,000 placeholder
  ceiling ratified pending institutional funding confirmation."
- Source: `docs/decisions/pilot-decisions.md` §D6 permitted implementation
  boundary: "The $5,000 placeholder and the tentative D7 values below are
  **not promoted to ratified figures**."
- Source: `docs/plans/prep/blocked-work-register-830.md` §2 "P7":
  "$5,000 placeholder ceiling ratified pending institutional funding
  confirmation."
- Consistent with the file-wide status line every entry in
  `pilot-decisions.md` carries: "**Status: TENTATIVE. None of the decisions
  below is organizationally ratified.**" — D6's closure is a *pilot-scope
  development decision*, not an institutional ratification, and this record
  makes no claim otherwise.

## 4. D7 — remains tentative, not promoted

**Decision:** D7 (points-economy calibration: earning rate, reward bands,
calibration N) **remains tentative**. Closing D6 does **not** promote D7.

- Source: `docs/decisions/pilot-decisions.md` §D6: "D7 remains tentative."
- Source: `docs/decisions/pilot-decisions.md` D1–D9 table, row D7: "Decided
  tentatively, in full, below. … Still required from IA West: Review of the
  earn rate, the bands, and N."
- Source: `docs/decisions/pilot-decisions.md` §D6 permitted implementation
  boundary: "the tentative D7 values below are not promoted to ratified
  figures."
- Source: `docs/decisions/2026-08-31-session-ratification.md` row "P7 D6/D7":
  "D7 remains tentative."
- Source: `docs/plans/prep/blocked-work-register-830.md` §2 "P7": "**Waiting
  on:** D7 calibration review; cards L1–L4+ remain gated per plan."

D7's tentative numbers (100 points per verified attendance; 300/600/1,000
point bands; calibration N = 3) stand as the values implemented-against-if-anything,
exactly as `pilot-decisions.md` §D7 records them — this record repeats none
of that arithmetic as if it were newly decided, and changes none of it.

## 5. Fields this direction does not resolve

Per `docs/decisions/pilot-decisions.md` §D6, the following remain **blocked
pending a formal design** and are not touched by this record:

- Currency
- Institutional budget ownership (as distinct from the interim named owner
  above — i.e., which institutional entity ultimately backs the budget)
- Funded balance
- Budget lifecycle and effective versions
- Concurrency
- Release/refund semantics
- Overlap rules
- Item names, costs, and content
- Earn policy and calibration N
- Fulfilment commitments
- Read/redemption roles

None of these is decided, implied, or narrowed by this record. Each remains
exactly as open as `pilot-decisions.md` §D6 already states.

## 6. Permitted implementation boundary

Quoted faithfully from `docs/decisions/pilot-decisions.md` §D6:

> **Permitted implementation boundary:** the formal D6 record above, and
> verification of already-authorized existing-schema/append-only guarantees
> (e.g. `budget_owner_id NOT NULL`,
> `test_reward_item_rejects_a_null_budget_owner`) only. If a database
> append-only guard is found absent, that gap is reported rather than added
> under this session. **No new budget envelope, commitment, reservation,
> redemption, earning, catalog, route, or UI behavior is authorized by this
> record.** The $5,000 placeholder and the tentative D7 values below are not
> promoted to ratified figures.

This document — the "formal D6 record" the boundary text refers to — and the
schema verification performed under it are exactly what this slice (V6)
delivers. Nothing else was built. In particular, and consistent with
`docs/decisions/2026-08-31-session-ratification.md`'s "Superseded plans"
table (row for `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`, P7): cards
L1–L4, C1, R3, and U1 of that plan (ledger fold, catalog listing, redemption,
frontend retirement) **remain gated** on D6/D7/role artifacts and do not
start early under this record.

## 7. Schema / append-only verification (Deliverable 2 — summary)

Verify-only, add-nothing verification of the existing-schema and append-only
guarantees the permitted implementation boundary refers to was performed
against `python/smartmatch_persistence/smartmatch_persistence/schema.py`,
`db/migrations/versions/0009_engagement_schema.py`,
`tests/unit/test_engagement_schema.py`, and
`tests/integration/test_engagement_schema_constraints.py`. Full evidence,
file:line citations, and command output are in
`docs/testing/d6-p7-rewards-schema-verification.md`. Summary:

| # | Check | Verdict |
|---|---|---|
| 1 | `reward_item.budget_owner_id` is `NOT NULL`, no server default; `test_reward_item_rejects_a_null_budget_owner` exists and asserts it | **CONFIRMED** |
| 2 | `point_ledger_entry` is append-only at the database level | **GAP FOUND — enforced only by convention (absent mutable columns) and by an application/test contract, not by any database trigger or rule.** No `UPDATE`/`DELETE` guard exists on the live table. **Reported here, not added.** |
| 3 | `amount <> 0` check constraint and the composite foreign key on `point_ledger_entry` | **CONFIRMED, both present and correct** |
| 4 | A balance is computed as a fold over the ledger rather than stored as a mutable column | **CONFIRMED — no balance column exists anywhere in the schema; no fold implementation exists yet either (out of scope)** |

The verification record also notes that "the redemption table" referenced in
this task's read list **does not exist** — `redemption` is one of the three
tables (`event`, `redemption`, `disclosure_consent`) that migration `0009`
explicitly defers past this gate (`0009_engagement_schema.py:8-13`).

No database trigger, rule, migration, or test was added in the course of this
verification. The append-only gap identified in check 2 is exactly the kind
of finding the permitted implementation boundary directs be reported rather
than closed under this session; closing it is scoped to plan card **L2**,
which remains gated.

## 8. Signature

```
Rewards budget owner:  Danny Tran (@dangt)
Date:                  2026-09-02
```

## 9. References

- `docs/decisions/pilot-decisions.md` §D6 and §D7
- `docs/decisions/2026-08-31-session-ratification.md` — matrix row "P7 D6/D7";
  "Superseded plans" table row for
  `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`
- `docs/plans/prep/blocked-work-register-830.md` §0 row 5, §2 "P7 — D6/D7
  rewards"
- `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md` (context only; cards
  L1–L4, C1, R3, U1 remain gated)
- `docs/architecture/decisions/ADR-0011-accountable-numbers.md`
- `docs/testing/d6-p7-rewards-schema-verification.md` (Deliverable 2, full
  evidence)
- `python/smartmatch_persistence/smartmatch_persistence/schema.py`
- `db/migrations/versions/0009_engagement_schema.py`
