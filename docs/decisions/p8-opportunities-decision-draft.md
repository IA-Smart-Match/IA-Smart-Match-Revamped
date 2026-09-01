# P8 — opportunities definition: decision record

**Status:** **RECORDED — GATE INCOMPLETE.** A session direction exists; the
formal stop-gate is not closed. This document does not ratify the canonical
"opportunities" metric and does not authorize card O1 of
`docs/plans/2026-08-28-opportunities-s12-plan.md`.
**Gate:** P8 stop-gate (`docs/plans/2026-08-28-opportunities-s12-plan.md`
§Stop-gate) — a written canonical definition of "opportunities", ratified by
the product owner.
**Formal decider:** the product owner — **no such role is named anywhere in
this repository.** No artifact previously existed under `docs/decisions/` for
this gate; this file is the first.
**Session approver of the recorded direction:** Danny Tran
(`dt110202@gmail.com`), 31 August 2026 — see
`docs/decisions/2026-08-31-session-ratification.md`.
**Prepared from:** `docs/plans/prep/human-decisions-handoff-831.md` §7 and
`docs/plans/opportunities-metric-inventory.md`.
**Changes no code.**

---

## 1. What the stop-gate requires

A committed artifact containing, non-blank:

1. the definition — which of: events eligible for publication, events in a
   match pool, events with a candidate above a score floor, or another
   precisely stated rule;
2. which variants deserve distinct registered names versus UI filters;
3. the owning evidence source for each registered name.

None of the three is answered by this record.

## 2. Recorded session direction (31 August 2026)

The opportunities model is a list of **programmatic engagement
opportunities**, recorded as an inclusive, non-exhaustive set of examples:

- hackathon
- datathon
- competition
- guest lecturer event
- school event

These are opportunities the coordinator can send connections or volunteers to
represent the institution. The later session direction intends **out-of-list
raw examples** to go to the IA West Coordinator for review — "out-of-list"
does not mean invalid or unknown; the list is explicitly non-exhaustive
unless a later product-owner artifact says it is exhaustive.

## 3. Unresolved fields

- Whether the examples above are exhaustive (recorded direction: they are
  not, unless a future artifact says otherwise).
- The canonical eligibility/count definition required by stop-gate item 1
  (publication-eligible vs. match-pool vs. score-floor vs. another rule).
- The owning evidence source for each registered name (stop-gate item 3).
- T-28 identity/tenant/unit authorization, required before any durable
  assignment or review action.
- P6 persistence, required before any event-backed evidence exists to query.
- The formal product-owner signature closing this gate.

## 4. Permitted implementation boundary

**Committed category-shape fixtures only**, proving an **in-list** category
shape and an **out-of-list raw example** shape, without waiting for P1 or P9.
Specifically not authorized by this record:

- No durable assignment of an opportunity to a reviewer or queue.
- No approve/reject action.
- No registered metric, aggregate, or drill-down (waits on P1's completed
  authorization rule, a canonical eligibility definition, and P6 owning
  persistence).
- No score floor is assumed; P8 does not inherit P5's fail-closed matching
  gate unless a later decision adds a score-floor branch.
- The legacy CSV/crawler merge and its fabricated fields
  (`docs/plans/opportunities-metric-inventory.md`) are **not** presented as
  the completed replacement.

## 5. References

- `docs/plans/2026-08-28-opportunities-s12-plan.md` — the stop-gate this
  record partially answers
- `docs/plans/opportunities-metric-inventory.md` — evidence on the current
  (fabricated-field) surface
- `docs/plans/prep/human-decisions-handoff-831.md` §7
- `docs/decisions/2026-08-31-session-ratification.md`
