# P9 Gate A — `board_role` shape: decision record

**Status:** **CLOSED — 2026-09-02 (pilot scope).** Relationship-scoped model
ratified; multiplicity and pilot date semantics decided. Schema migration
remains a separate engineering card after `columns.yaml` update.
**Gate:** P9 Gate A (`docs/plans/2026-08-28-pilot-columns-plan.md` §Stop-gates
§Gate A).
**Formal decider:** Danny Tran (@dangt), program owner — named 2026-09-02.
(Supersedes prior "Dr. Wang" placeholder in plan text where program owner was
unnamed.)
**Session direction (31 August 2026):** relationship-scoped, contextual,
time-dependent — incorporated below.

---

## 1. Question 1 — intrinsic vs relationship-scoped

**Decision:** **Relationship-scoped.** `board_role` varies by
`(professional, unit)` relationship, not as a single intrinsic attribute on
the person.

## 2. Question 2 — multiplicity, dates, source (pilot scope)

| Sub-question | Decision |
|---|---|
| **Multiplicity** | **Multiple concurrent** `board_role` values per person across different unit relationships **must be representable** at the same instant |
| **Effective dates (pilot)** | **None required** — pilot treats `board_role` as **current-state only** on each relationship; no `effective_from` / `effective_to` columns for pilot |
| **Source semantics** | Human import per `columns.yaml`; coordinator correction via audited import/review (aligns with Gate B contact governance) |
| **Correction semantics** | Corrections update the current relationship record; historical effective dating deferred post-pilot |

## 3. Schema direction (authorized for planning — not yet migrated)

**Target shape (post-pilot dates optional):**

- Remove `board_role` from `professionals.optional` in `columns.yaml` when
  migration is authorized.
- New relationship table e.g. `professional_unit_relationship` with composite
  `(tenant_id, professional_id, unit_id)` + `board_role` (+ effective dates
  when added post-pilot).

**Holding position until migration card runs:** `columns.yaml` single-column
representation remains importable; worker wiring documents relationship intent.

## 4. Permitted implementation boundary

- Update `columns.yaml`, fixtures, and decision prep to reflect closed gate.
- Schema-shape analysis and migration **planning** authorized.
- **Authorized 2026-09-02 (program owner, this slice — P9 pilot columns V2):**
  the program owner has authorized the schema change this section previously
  called "not yet authorized." That covers authoring the relationship
  table's source — `professional_unit_relationship` in
  `python/smartmatch_persistence/smartmatch_persistence/schema.py` and the
  corresponding version file
  `db/migrations/versions/0012_professional_unit_relationship.py` — and
  updating `columns.yaml`, the worker's `column_contract`/`handlers` import
  path, and fixtures so `board_role` is removed from
  `professionals.optional` and enforced only in its relationship-scoped
  shape. This authorizes writing and reviewing that source; it does not
  itself apply the migration or verify it against a live database — no
  database exists in the authoring environment, and running `alembic
  upgrade` against a real pilot database is a separate, later operator
  action.

## 5. Signature

```
Program owner / Gate A decider:  Danny Tran (@dangt)
Date:                            2026-09-02
```

## 6. References

- `docs/plans/2026-08-28-pilot-columns-plan.md` — Gate A text
- `docs/pilot-data/board-role-decision-prep.md`
- `docs/pilot-data/columns.yaml`
- `docs/decisions/2026-08-31-session-ratification.md`
