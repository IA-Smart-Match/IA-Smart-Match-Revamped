# P9 Gate A — `board_role` shape: decision record

**Status:** **RECORDED — GATE INCOMPLETE.** A session direction exists; the
formal gate is not closed. This document does not ratify a schema change and
does not authorize a migration.
**Gate:** P9 Gate A (`docs/plans/2026-08-28-pilot-columns-plan.md` §Stop-gates
§Gate A).
**Formal decider:** Dr. Wang (program owner), per the plan's own text. Not
superseded by this record.
**Session approver of the recorded direction:** Danny Tran
(`dt110202@gmail.com`), 31 August 2026 — see
`docs/decisions/2026-08-31-session-ratification.md`.
**Prepared from:** `docs/pilot-data/board-role-decision-prep.md` and
`docs/plans/prep/human-decisions-handoff-831.md` §7.
**Changes no code and no schema.**

---

## 1. The two questions Gate A asks

1. Is `board_role` intrinsic to a professional, or scoped to that person's
   relationship with one unit/chapter?
2. If relationship-scoped: multiplicity (multiple simultaneous roles?),
   effective dates, and source semantics.

## 2. Recorded session direction (31 August 2026)

`board_role` is **relationship-scoped, contextual, and time-dependent**
rather than a single intrinsic attribute. A person can serve on a board for
one program while appearing only as a guest speaker in another; the system
should treat `board_role` as varying by context and by relationship, not as
one universal label attached to the person.

This answers question 1 in direction only. It does **not** answer:

- **Multiplicity** — whether one person may hold more than one `board_role`
  concurrently across different relationships, and whether that must be
  representable at the same instant.
- **Effective dates** — whether a `board_role` carries a start/end and how a
  correction to a past-dated role is represented.
- **Source semantics** — who or what asserts a `board_role` value, and how a
  disagreement between sources is resolved.
- **Correction semantics** — how a wrongly recorded `board_role` is corrected
  without silently rewriting history.
- **The formal gate record** — Dr. Wang has not signed a Gate A artifact.
  This document is a session-recorded direction, not that signature.

## 3. Permitted implementation boundary

**Documentation and schema-shape analysis only.** Specifically prohibited
until the formal gate closes:

- No flat rejection of the current `columns.yaml` single-column
  representation as a discarded interpretation.
- No enforcement of a new column shape.
- No relationship-schema behavior (new table, new FK, new migration) that
  encodes multiplicity or effective dates.

`columns.yaml`'s current single-column representation **remains the holding
position** — documented as such, not as the approved final model — exactly as
`docs/plans/prep/blocked-work-register-830.md` §2 already states. This record
does not select a migration.

## 4. What this unlocks

Nothing past documentation. Gate A and Gate B (contact fields) pass
**independently**; Gate B's status is recorded separately in
`docs/decisions/p9-gate-b-contact-fields-worksheet.md`. Neither gate's
resolution depends on the other.

## 5. References

- `docs/plans/2026-08-28-pilot-columns-plan.md` — Gate A text
- `docs/pilot-data/board-role-decision-prep.md` — prep material
- `docs/pilot-data/columns.yaml` — current holding position
- `docs/plans/prep/human-decisions-handoff-831.md` §7
- `docs/decisions/2026-08-31-session-ratification.md`
