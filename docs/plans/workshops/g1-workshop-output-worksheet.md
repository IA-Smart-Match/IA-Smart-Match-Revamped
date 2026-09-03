# G1 workshop output worksheet — RATIFIED

**Status: RATIFIED — 2026-09-03.** Gate G1 / D1 closed. M1 complete in code.

Prepared from:

- Dr. Wang design decisions (2026-09-03 session direction)
- `g1-factor-registry-workshop-packet.md`
- Program owner: **Danny Tran (@dangt)**

**Ratified by:** Danny Tran (@dangt)  
**Date:** 2026-09-03  

---

## Sign-off block

- [x] Surviving factor keys and final weights recorded; Stage B sum = 1.0.
- [x] Q6 answered for `historical_conversion` and `student_interest`.
- [x] `zero_classification` recorded for every symptom zero above.
- [x] Tie-break rule recorded.
- [x] Named program owner for ongoing weight governance recorded.

**Ratified by:** Danny Tran (@dangt)  
**Date:** 2026-09-03  
**Commit recording ratification:** (this commit) — out of G1 scope (tracked separately)

| Directive | Owner / gate | Notes |
|---|---|---|
| Single standard login; roles in backend | P2 A1b + legacy frontend | No "choose your portal" |
| Dashboard discovery feed (R/Y/G) | Legacy frontend O4 / W3 | Purple theme on hold |
| Student feedback/ratings for admins | Post-G1 product (Chau matrix) | Not a matching factor; separate feature |
| Month calendar bottom of events page | Legacy events UI | Presentation |
| Reimbursements ~3 weeks; Sept OK | Ops / Dr. Wang invoices | Not in registry |

---

## Agenda item 1 — factor list and final weights

**Program direction:** Simple fixed weights — **topic relevance (heavier) + proximity**. Match **before** availability; coordinator batch-invites; return **2–3 speakers**, no ranked percentage (presentation rule — M10/explanation).

| Key | Stage | Proposed | Implemented | Survives? | Final weight | Notes |
|---|---|---|---|---|---|---|
| `topic_relevance` | B suitability | 0.30 | no | **Y** | **0.70** | Heavier per Wang |
| `role_fit` | B suitability | 0.25 | no | **N** | — | Dropped for pilot simplicity |
| `travel_burden` | B penalty | 0.20 | no | **Y** | **0.30** | Proximity proxy (straight-line until D3) |
| `engagement_load` | B penalty | 0.15 | yes | **N** | — | Deferred post-pilot; Wang two-factor model |
| `repeat_penalty` | B penalty | 0.10 | no | **N** | — | Dropped for pilot |
| `availability` | A eligibility | 0 | no | **Y** | 0 (fixed) | Applied **after** shortlist, not in Stage B score |
| `credential_check` | A eligibility | 0 | no | **N** | — | Deferred |
| `contact_status` | A eligibility | 0 | no | **N** | — | Deferred |
| `declared_cap` | A eligibility | 0 | no | **N** | — | Deferred |

**Stage B sum (surviving scoring factors):** 0.70 + 0.30 = **1.0** ✓

**M2 implementation order:** `topic_relevance`, then `travel_burden` (proximity). Until M2 lands, registry approval does not produce user-visible scores.

**Presentation (not a factor):** Return top **2–3** candidates; **no percentage** display to coordinators.

---

## Agenda item 2 — Q6

| Legacy factor | Decision | Rationale |
|---|---|---|
| `historical_conversion` | **DROP** | Not in Wang simple model |
| `student_interest` | **DROP** | Captured as separate admin feedback feature per Wang |

---

## Agenda item 3 — golden cases and ADR-0011 classification

| Fixture | Symptom | `zero_classification` | Presentation when unknown |
|---|---|---|---|
| `G1-GC-002` | Topic Relevance 0% | **measured_zero** | Show 0% with source |
| `G1-GC-005` | Topics absent | **unknown** | "Unknown" — not 0% |
| `G1-GC-006` | Topics disjoint | **measured_zero** | Show 0% with source |
| `G1-GC-003` | Match Depth 0 | **measured_zero** | Show 0% with source |
| `G1-GC-007` | History absent | **unknown** | "Unknown" — not 0% |
| `G1-GC-008` | History empty | **measured_zero** | Show 0% with source |

**Tie case `G1-GC-001` / `G1-GC-004`:**

- Reproducing inputs: **accept `G1-GC-004` draft**
- **Tie-break rule:** lexicographic ascending by `subject_id` (stable, deterministic)

**`match_depth`:** Derived display quantity from engagement history — **not** a separate registry factor.

---

## Agenda item 4 — weight governance

1. **Who may change weights after G1:** Danny Tran (@dangt), program owner (or IA West designee after ratification).
2. **Shadow-mode (MM-005) gates weight changes:** **Yes** — no weight change ships without shadow evaluation pass.
3. **Registry version pinning for `match_run` (M8):** **Yes** — every run records registry version hash.

---

## Dr. Wang directives
