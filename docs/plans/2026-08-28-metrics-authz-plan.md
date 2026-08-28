# Implementation plan — metrics authorization decision application

**Date:** 2026-08-28 · **Plan id:** P1 · **Worktree branch:** `plan/metrics-authz`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. This plan is self-contained; no chat history is required.

## Standing constraints (restated; do not override)

- No push, no pull request, no merge without explicit human request.
- No live providers, live data, production credentials, or production-readiness
  claims. Nothing is deployed.
- Authorization may stay the same or become **narrower** only. Never replace
  unit-scoped authorization with authentication alone; never bypass tenant
  isolation, active-membership windows, suspension, or explicit deny.
- ADR-0014 minimum disclosure: aggregate access does not automatically
  authorize row-level payload access.

## Stop-gate (verify before selecting any branch)

The decision artifact is `docs/decisions/metrics-authorization-decision-draft.md`
(or a successor file it names). Before running any branch, the executor MUST
verify **all** of the following in the committed artifact:

1. It is no longer marked draft/unapproved; it records a ratified decision.
2. It answers all four questions from
   `docs/plans/remaining-engineering-implementation-plan.md` §5.4:
   (a) may any active unit membership read aggregates; (b) may a bare unit
   resource grant read aggregates; (c) which roles may read underlying rows
   such as `review_item.row_data`; (d) do particular metrics need stricter
   drill-down policy.
3. It names the deciding product/security owner.

If any check fails: **stop, report "workshop artifact missing or incomplete",
and do not modify code.** Do not infer approval from the draft's
recommendation. A decision that leaves alternatives open selects no branch.

## Current state (facts an executor can verify)

- `services/api/smartmatch_api/routers/metrics.py::_authorize_unit_read` calls
  `assert_allowed` with **no `required_roles`** — any active unit membership
  reads aggregates and drills into underlying rows. This is intentional and
  documented (docstring cites `INTENTIONALLY_UNGATED_OPERATIONS`).
- `tests/authz/test_policy_matrix.py` declares
  `INTENTIONALLY_UNGATED_OPERATIONS = frozenset({"metrics.read", "metrics.drill_down"})`
  with completeness meta-tests: an undeclared ungated operation fails CI.
- `services/api/smartmatch_api/routers/imports.py` shows the gated pattern:
  `required_roles=_IMPORT_ROLES` (`frozenset({"admin", "coordinator"})`).
- `tests/contract/test_metrics.py` (integration) proves drill-down count equals
  aggregate for `pending_review_items`.

## Branch selection

| Committed decision | Branch |
|---|---|
| Both operations stay ungated (explicitly approved) | `BRANCH-UNGATED-CONFIRMED` |
| Both operations gated to named roles | `BRANCH-GATED-BOTH` |
| Aggregates open to any active membership; drill-down gated | `BRANCH-SPLIT` |

### BRANCH-UNGATED-CONFIRMED

Task card U1 (single card, no parallelism needed):

- **Fence:** `docs/decisions/metrics-authorization-decision-draft.md` (rename to
  a ratified filename if the artifact says so), `metrics.py` docstring,
  `tests/authz/test_policy_matrix.py` comments only.
- **Work:** record the ratified decision reference next to
  `INTENTIONALLY_UNGATED_OPERATIONS` and in the `metrics.py` docstring so the
  ungated state is documented as chosen, not inherited. No behavioral change.
- **Tests:** `python -m pytest tests/authz/test_policy_matrix.py -q`; full
  `make check` if available.

### BRANCH-GATED-BOTH

Lane A — API (card G1a):

- **Fence:** `services/api/smartmatch_api/routers/metrics.py`.
- **Work:** add a module-level role constant named per the decision (pattern:
  `_METRICS_ROLES = frozenset({...})` mirroring `_IMPORT_ROLES`), pass
  `required_roles` in `_authorize_unit_read`. Continue loading the unit and
  calling `assert_allowed` — do not weaken unit scoping.

Lane B — policy matrix (card G1b, parallel with A):

- **Fence:** `tests/authz/test_policy_matrix.py`.
- **Work:** remove `metrics.read` and `metrics.drill_down` from
  `INTENTIONALLY_UNGATED_OPERATIONS`; add matrix rows for every role × both
  operations; add negative tests: wrong role, sibling unit, suspended user,
  cross-tenant, expired membership, explicit deny.

Join card G1c (after A and B):

- **Fence:** `tests/contract/test_metrics.py`.
- **Work:** add endpoint-level refusal tests (wrong-role caller receives the
  standard error envelope) while preserving the aggregate = drill-down-count
  equality for authorized callers.
- **OpenAPI:** regenerate and run `make openapi-check` **only if** response
  documentation changes (403 documentation). One card owns regeneration.

### BRANCH-SPLIT

Same lanes as BRANCH-GATED-BOTH, with these differences:

- Card S1a: two constants and two authorizer paths in `metrics.py` —
  aggregate path keeps `required_roles=None` (or the decision's aggregate
  roles), drill-down path uses the decision's row-level roles. Register the
  two operations separately.
- Card S1b: `metrics.read` may remain in `INTENTIONALLY_UNGATED_OPERATIONS`
  only if the artifact explicitly approves that; `metrics.drill_down` moves to
  the gated matrix with full negative tests.
- Card S1c: contract tests must prove an aggregate-authorized,
  drill-down-refused caller sees the aggregate value and receives a refusal
  envelope (not an empty rows array) on drill-down.

## Hard rules for every branch

- No option may become "any authenticated user"; unit scope always remains.
- Policy-matrix rows travel with the route change in the same commit.
- If per-metric stricter policies are decided (question d), encode them as
  data on the metric register entry, not as if/else chains in the router; add
  one matrix row per (metric, operation) pair the decision distinguishes.

## Evidence ladder

1. `python -m pytest tests/authz/test_policy_matrix.py tests/contract/test_metrics.py -q`
2. `make check` (no-database; does not prove integration behavior)
3. `make openapi-check` if contracts changed
4. **CI-only proof:** PostgreSQL-backed contract tests
   (`tests/contract/test_metrics.py` full run). Do not claim integration green
   from a local Windows run; the pinned venv/Postgres may be unavailable
   (see `docs/plans/orchestrator-handoff.md` §CI / environment).

## Done means

- The committed policy names roles separately for aggregate and rows (or
  documents the explicit choice to keep both open).
- Every negative case listed above has a test.
- Authorized drill-down count still equals the aggregate.
- The decision artifact, code, matrix, and OpenAPI agree.
