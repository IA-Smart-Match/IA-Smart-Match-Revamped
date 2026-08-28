# Metrics authorization decision — draft

**Status:** draft for product/security workshop — **does not change code**.  
**Classification:** human-decision-required (`remaining-engineering-implementation-plan.md` §5.4).  
**Current behaviour:** intentionally ungated — documented and tested.

## Current state (intentional)

`services/api/smartmatch_api/routers/metrics.py::_authorize_unit_read` calls
`assert_allowed` with **no `required_roles`**. Any **active unit membership**
may read aggregates and drill-down rows.

Pinned in:

- `tests/authz/test_policy_matrix.py` — `INTENTIONALLY_UNGATED_OPERATIONS`
- `tests/contract/test_metrics.py` — aggregate count equals drill-down rows

This is not a bug to paper over without an explicit decision.

## Questions the workshop must answer

1. May any active unit membership read **aggregates**?
2. May a bare `resource_grant` (no role) read aggregates? (S-007: currently yes
   for ungated ops.)
3. Which roles may read **underlying rows** (e.g. `review_item.row_data`)?
4. Must specific metrics have stricter drill-down policy than others?

## Drill-down field sensitivity inventory

| Metric | Owning query | Row fields today | Sensitivity |
|---|---|---|---|
| `pending_review_items` | `pending_review_item_rows_v1` | `id`, `import_batch_id`, `row_index`, `status`, **`row_data`** | **High** — full imported row payload; may contain PII from pilot CSV |
| `pipeline_*` (5 metrics) | `pipeline_funnel_rows_v1` | *(none — honest unknown)* | N/A until S12 |
| Future `opportunities` | TBD (S12) | TBD | Depends on metric definition |

**`row_data` note:** Imported professional/event fields may include names,
companies, and (if collected) published contacts. ADR-0014 minimum disclosure
applies — aggregate access does not automatically authorize row payloads.

## Policy options (comparison)

| Option | `metrics.read` | `metrics.drill_down` | Matrix change |
|---|---|---|---|
| A — status quo | any active membership | any active membership | none |
| B — split | any active membership | `admin`, `coordinator` only | remove `metrics.drill_down` from `INTENTIONALLY_UNGATED_OPERATIONS`; add `_METRICS_DRILL_DOWN_ROLES` |
| C — gate both | `admin`, `coordinator` | `admin`, `coordinator` | remove both from ungated set |

**Recommendation (not authorization):** if row payloads stay in drill-down, Option B
or C merits serious consideration under ADR-0014. Option A requires explicit
approval that imported row data is visible to all unit roles.

## Expected code deltas (after decision only)

| File | Change |
|---|---|
| `routers/metrics.py` | separate aggregate vs drill-down authorizers if policies differ |
| `tests/authz/test_policy_matrix.py` | update `INTENTIONALLY_UNGATED_OPERATIONS`, matrix cells, negative tests |
| `tests/contract/test_metrics.py` | wrong-role refusal tests; preserve equality for authorized callers |
| `contracts/openapi/smartmatch.json` | regenerate only if response docs change |

## Acceptance (post-decision)

- [ ] Committed decision record names roles separately for aggregate and rows.
- [ ] Wrong-role, sibling-unit, suspended, cross-tenant, expired-membership,
      explicit-deny cases tested.
- [ ] No path becomes "any authenticated user" without unit membership.
- [ ] Authorized drill-down count still equals aggregate.

## References

- `docs/architecture/decisions/ADR-0014-disclosure-consent.md`
- `docs/plans/orchestrator-handoff.md` §Blocker 2
- `services/api/smartmatch_api/routers/metrics.py`
- `tests/authz/test_policy_matrix.py`
