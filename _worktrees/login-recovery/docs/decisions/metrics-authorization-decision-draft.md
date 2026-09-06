# Metrics authorization decision — draft

**Status:** **CLOSED — 2026-09-02.** Product owner and security/privacy owner
named and signed (same person, both roles). Engineering may implement per §5.
**Classification:** human-decision-required (`remaining-engineering-implementation-plan.md` §5.4).  
**Prior behaviour:** intentionally ungated — documented and tested until implementation lands.

## 0. Session-recorded direction (31 August 2026)

**Session approver:** Danny Tran (@dangt) — see
`docs/decisions/2026-08-31-session-ratification.md`.

The session approved an **aggregate-visibility hierarchy** as direction:

| Actor | Recorded aggregate direction |
|---|---|
| Student | Their own class or unit summary. |
| School coordinator | Their school summary. |
| IA West Coordinator | Cross-unit portfolio metrics. |

Raw rows stay restricted; this hierarchy is about aggregate access only.

## 1. Closed decisions (2 September 2026)

**Product owner:** Danny Tran (@dangt) — program owner, same person.  
**Security/privacy owner:** Danny Tran (@dangt) — privacy owner (P9 Gate B).  
**Development Lead:** Danny Tran (@dangt)

| Question | Decision |
|---|---|
| Student aggregate scope | **Subtree** (unit + descendants) |
| School coordinator aggregate scope | **Subtree** (school + descendants) |
| `admin` treatment | **Unrestricted within tenant** |
| Bare `resource_grant` reads aggregates? | **No** — role required |
| Row drill-down policy | **Option B — split:** any active membership reads aggregates; `admin` and `coordinator` only for `metrics.drill_down` |
| Metric-specific exceptions | **None** |

**Contact-field coupling (P9 Gate B):** collect direction closed 2026-09-02.
Option B limits `row_data` (including contact fields) to `admin` and
`coordinator` roles for drill-down. Aggregate visibility remains broader per
table above.

## 2. Prior state (superseded on implementation)

`services/api/smartmatch_api/routers/metrics.py::_authorize_unit_read` called
`assert_allowed` with **no `required_roles`**. Pinned in
`tests/authz/test_policy_matrix.py` — `INTENTIONALLY_UNGATED_OPERATIONS`.
Implementation must retire this exception in the same change set that enforces
§1.

## 3. Drill-down field sensitivity inventory

| Metric | Owning query | Row fields today | Sensitivity |
|---|---|---|---|
| `pending_review_items` | `pending_review_item_rows_v1` | `id`, `import_batch_id`, `row_index`, `status`, **`row_data`** | **High** — full imported row payload; may contain PII and contact fields |
| `pipeline_*` (5 metrics) | `pipeline_funnel_rows_v1` | *(none — honest unknown)* | N/A until S12 |
| Future `opportunities` | TBD (S12) | TBD | Per P8 definition |

## 4. Authorized policy (Option B, refined)

| Operation | Roles permitted |
|---|---|
| `metrics.read` (aggregates) | Any **active unit membership** with a role (bare `resource_grant` **denied**) |
| `metrics.drill_down` | `admin`, `coordinator` only |

Scope rules:

- **Student:** subtree of their unit
- **School coordinator:** subtree of their school unit
- **`admin`:** unrestricted within tenant for aggregates; drill-down per row above

## 5. Expected code deltas (authorized)

| File | Change |
|---|---|
| `routers/metrics.py` | separate aggregate vs drill-down authorizers; scope/subtree logic |
| `tests/authz/test_policy_matrix.py` | remove `metrics.*` from `INTENTIONALLY_UNGATED_OPERATIONS`; matrix cells; negative tests |
| `tests/contract/test_metrics.py` | wrong-role refusal tests; preserve equality for authorized callers |
| `contracts/openapi/smartmatch.json` | regenerate only if response docs change |

## 6. Acceptance (post-implementation)

- [x] Committed decision record names roles separately for aggregate and rows.
- [ ] Wrong-role, sibling-unit, suspended, cross-tenant, expired-membership,
      explicit-deny cases tested.
- [ ] No path becomes "any authenticated user" without unit membership.
- [ ] Authorized drill-down count still equals aggregate.
- [ ] Raw-row refusal uses standard error envelope (not empty row list).

## 7. Signatures

```
Product owner:        Danny Tran (@dangt), program/product owner
Security/privacy:     Danny Tran (@dangt), privacy owner (P9 Gate B)
Development Lead:     Danny Tran (@dangt)
Date:                 2026-09-02
```

## References

- `docs/architecture/decisions/ADR-0014-disclosure-consent.md`
- `docs/plans/orchestrator-handoff.md` §Blocker 2
- `docs/plans/workshops/p1-metrics-authorization-workshop-packet.md`
- `services/api/smartmatch_api/routers/metrics.py`
- `tests/authz/test_policy_matrix.py`
