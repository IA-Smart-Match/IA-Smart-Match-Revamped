# P1 metrics-authorization workshop packet

**Status:** **CLOSED — 2026-09-02.** Decision recorded in
`docs/decisions/metrics-authorization-decision-draft.md`. V4 implementation
authorized.

**Prepared:** 2 September 2026 · **Plan id:** P1 (V4 in the ratification
report's continuation order).

**Binding sources (read these, not this packet, where they disagree):**
`docs/decisions/metrics-authorization-decision-draft.md` (the recorded
direction and the four questions), `docs/plans/2026-08-28-metrics-authz-plan.md`,
`docs/architecture/decisions/ADR-0014-disclosure-consent.md`.

## Purpose

Convert the aggregate-visibility direction recorded on 31 August 2026 into a
signed policy that engineering may implement. The direction narrowed the
problem; it answered none of the four questions below, and
`metrics-authorization-decision-draft.md` §0 says so explicitly.

## 1. Who must be in the room

| Role | Why required | Named? |
|---|---|---|
| Product owner | Owns whether imported row payloads are visible to all unit roles | **Danny Tran (@dangt)** — named 2026-09-02 |
| Security/privacy owner | ADR-0014 minimum disclosure applies to `row_data` | **Danny Tran (@dangt)** — privacy owner (P9 Gate B) |
| Development Lead | Records the decision and the resulting engineering sequence | Danny Tran |

`metrics-authorization-decision-draft.md` §0 requires product **and** security
**together**. A meeting missing either does not close the gate; it produces
another recorded direction. **Naming these two people is a prerequisite to
scheduling, not an agenda item.**

## 2. Current behaviour the workshop is deciding about (do not change in prep)

`services/api/smartmatch_api/routers/metrics.py::_authorize_unit_read` calls
`assert_allowed` with **no `required_roles`**. Any active unit membership may
read both aggregates and drill-down rows. This is intentional and pinned:

- `tests/authz/test_policy_matrix.py` — `INTENTIONALLY_UNGATED_OPERATIONS`
- `tests/contract/test_metrics.py` — aggregate count equals drill-down rows

It is an explicit unresolved exception, **not** an approved policy and **not**
a pattern new work may copy.

## 3. Recorded direction — the starting point, not the answer

| Actor | Recorded aggregate direction |
|---|---|
| Student | Their own class or unit summary |
| School coordinator | Their school summary |
| IA West Coordinator | Cross-unit portfolio metrics |

Raw rows stay restricted. This is about **aggregate** access only.

## 4. Agenda — four bounded questions, 60 minutes

Each item is decided or explicitly deferred with a named blocker. Nothing
carries over as "we sort of agreed".

### Item 1 (10 min) — Scope shape

The direction says "their unit" and "their school" without saying whether
either means an **exact unit** or a **subtree**, and does not say how `admin`
is treated.

- Student scope: ☐ exact unit ☑ subtree
- School coordinator scope: ☐ exact unit ☑ subtree
- `admin`: ☐ same as coordinator ☑ unrestricted within tenant ☐ other: ______

### Item 2 (10 min) — May a bare `resource_grant` (no role) read aggregates?

Security finding S-007: today, yes, for ungated operations.

- ☐ Yes, a bare grant reads aggregates ☑ No, a role is required

### Item 3 (25 min) — Which roles may read underlying rows?

This is the item with real disclosure consequence. `pending_review_items`
drill-down returns `review_item.row_data` — the **full imported row payload**,
which may carry names, companies, and (if P9 Gate B collects them) published
contacts. ADR-0014 minimum disclosure applies: aggregate access does not
automatically authorize row payloads.

| Option | `metrics.read` | `metrics.drill_down` | Matrix change |
|---|---|---|---|
| A — status quo | any active membership | any active membership | none |
| B — split | any active membership | `admin`, `coordinator` only | remove `metrics.drill_down` from `INTENTIONALLY_UNGATED_OPERATIONS`; add `_METRICS_DRILL_DOWN_ROLES` |
| C — gate both | `admin`, `coordinator` | `admin`, `coordinator` | remove both from the ungated set |

**Option A requires an explicit, signed statement that imported row data is
visible to every unit role.** It is available, but it is a decision, not a
default.

- Chosen: ☐ A ☑ B ☐ C ☐ other: ______

### Item 4 (10 min) — Metric-specific exceptions

Must any specific metric carry a stricter drill-down policy than the answer to
Item 3?

- ☑ No exceptions ☐ Yes — list metric and rule: ______

### Item 5 (5 min) — Record and close

Sign §6. Anything unanswered is written down as unanswered, with the person
who owes the answer named.

## 5. What signing unblocks

- V4 in the ratification report's continuation order moves from "record the
  hierarchy" to "implement".
- `routers/metrics.py` may separate aggregate and drill-down authorizers.
- The ungated-operations exception can be retired from
  `tests/authz/test_policy_matrix.py` rather than re-explained each review.
- Raw-row refusal moves to the standard error envelope instead of an empty
  row list.

Acceptance conditions engineering must then meet (from the draft, unchanged):
the decision record names roles **separately** for aggregate and rows;
wrong-role, sibling-unit, suspended, cross-tenant, expired-membership, and
explicit-deny cases are tested; no path becomes "any authenticated user"
without unit membership; authorized drill-down count still equals aggregate.

## 6. Decision record — TO BE COMPLETED BY THE NAMED HUMANS

```
Product owner (name, role):        Danny Tran (@dangt), program/product owner
Security/privacy owner (name, role): Danny Tran (@dangt), privacy owner
Development Lead:                  Danny Tran (@dangt)
Date:                              2026-09-02

Item 1  student scope:             subtree
Item 1  school-coordinator scope:  subtree
Item 1  admin treatment:           unrestricted within tenant
Item 2  bare resource_grant:       no — role required
Item 3  option chosen (A/B/C):     B
Item 4  metric exceptions:         none

Signatures:
  Product owner:                   Danny Tran (@dangt)
  Security/privacy owner:          Danny Tran (@dangt)
```

P1 is **CLOSED**. Implementation authorized per
`docs/decisions/metrics-authorization-decision-draft.md` §5.

## 7. References

- `docs/decisions/metrics-authorization-decision-draft.md`
- `docs/plans/2026-08-28-metrics-authz-plan.md`
- `docs/architecture/decisions/ADR-0014-disclosure-consent.md`
- `docs/plans/2026-08-31-ratification-and-implementation-report.md` §4 (V4)
- `services/api/smartmatch_api/routers/metrics.py`
- `tests/authz/test_policy_matrix.py`, `tests/contract/test_metrics.py`
