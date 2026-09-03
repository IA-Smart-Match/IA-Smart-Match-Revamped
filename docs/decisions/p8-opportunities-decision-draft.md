# P8 — opportunities definition: decision record

**Status:** **CLOSED — 2026-09-02.** Canonical definition ratified by product
owner Danny Tran (@dangt). Card O1 of
`docs/plans/2026-08-28-opportunities-s12-plan.md` may proceed; O2+ remain
blocked on S12 persistence and P6 crawler persistence where applicable.
**Gate:** P8 stop-gate (`docs/plans/2026-08-28-opportunities-s12-plan.md`
§Stop-gate).
**Product owner:** Danny Tran (@dangt) — named 2026-09-02 (same as program
owner).
**Prepared from:** `docs/plans/prep/human-decisions-handoff-831.md` §7 and
`docs/plans/opportunities-metric-inventory.md`.

---

## 1. Canonical definition (stop-gate item 1)

**Registered name (proposed):** `opportunities` (display: "Opportunities")

**Counting rule — category-list with coordinator review:**

An event row counts toward `opportunities` when its category is one of the
**in-list programmatic engagement types**:

- hackathon
- datathon
- competition
- guest lecturer event
- school event

Rows whose category is **out-of-list** (including raw/unmapped examples) do
**not** count until the **IA West Coordinator** reviews and either assigns an
in-list category or explicitly approves inclusion. "Out-of-list" does not mean
invalid — the in-list set is **non-exhaustive**; coordinators may extend
practice through review without treating unknown labels as errors.

This is **not** a score-floor definition. **Branch:**
`BRANCH-ELIGIBILITY` — does **not** inherit P5/G1 for the count itself.
Matcher actions on opportunities remain G1-gated separately.

## 2. Variants vs UI filters (stop-gate item 2)

| Name | Distinct registered metric? | Notes |
|---|---|---|
| `opportunities` | **Yes** — canonical pilot metric | In-list categories, post-review |
| Per-category filters (e.g. hackathons only) | **UI filters** on the same metric | Not separate registered names for pilot |
| `opportunities_pending_review` | **Optional future name** | Out-of-list rows awaiting coordinator review — defer unless drill-down needs a separate aggregate |

For pilot: **one registered name** (`opportunities`) with UI filters by
category. Pending-review queue may surface as drill-down or a separate metric
in a later pass if coordinators require it.

## 3. Owning evidence source (stop-gate item 3)

| Source | Included? | Notes |
|---|---|---|
| Human/import CSV (`columns.yaml` contract) | **Yes** | Primary pilot path |
| Crawler-fed events (P6) | **Yes** | Inherits P6 persistence gate for crawler rows; no fabricated dates/roles |
| Client-side CSV/crawler merge | **No** | Legacy `Opportunities.tsx` merge is not canonical (Fix #5) |
| Matcher scores | **No** | Not part of this definition |

**P6 inheritance:** crawler-backed rows count only when P6 event persistence
exists and rows pass the same category/review rules. Until then, import-origin
rows may count; crawler-origin rows remain unknown or excluded honestly.

## 4. Recorded session direction (31 August 2026) — incorporated

The 31 August category examples are the in-list set above. Coordinator review
for out-of-list examples is **required**, not advisory.

## 5. Permitted implementation boundary (post-close)

- **Card O1:** register `opportunities` per this definition text.
- **Cards O2–O4:** per plan; authorization consistent with closed P1 (Option B).
- **Not authorized:** fabricated client-side merge; score-floor counting without
  a future gate amendment.

## 6. Signature

```
Product owner:  Danny Tran (@dangt)
Date:           2026-09-02
```

## 7. References

- `docs/plans/2026-08-28-opportunities-s12-plan.md`
- `docs/plans/opportunities-metric-inventory.md`
- `docs/decisions/2026-08-31-session-ratification.md`
- `docs/decisions/metrics-authorization-decision-draft.md` (P1 — closed)
