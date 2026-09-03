# Plan — P1/V4 metrics authorization (Option B) + P8/V5 card O1 (`opportunities` register entry)

**Date:** 2026-09-02 · **Branch:** `friday-deliverable-828`
**Spec authority (binding):**
- `docs/decisions/metrics-authorization-decision-draft.md` (P1 — CLOSED 2026-09-02)
- `docs/decisions/p8-opportunities-decision-draft.md` (P8 — CLOSED 2026-09-02)
- `docs/plans/2026-08-28-opportunities-s12-plan.md` §Card O1

## Global Constraints

1. **Deny-by-default.** No change may turn a denial into a permit that the
   closed decision does not name. No path becomes "any authenticated user".
2. **Unknown stays unknown** (ADR-0011). A metric with no evidence source
   returns `value: null` with a non-empty `unknown_reason` and an empty
   drill-down. An empty drill-down is never a measured zero.
3. **One canonical name ↔ one owning query ↔ drill-down count equals aggregate.**
4. **Definition text is copied from the ratified decision record**, not
   paraphrased.
5. **No push, no PR, no production-readiness claims.** Local commits only.
6. **Fence discipline:** each task commits ONLY the files listed in its own
   fence, with explicit `git add <path>` — never `git add -A`/`.`/`-a`. The
   working tree carries unrelated in-flight edits from other work.
7. Baseline (recorded before this plan): `pytest tests/ -m "not integration"`
   has 4 pre-existing failures unrelated to metrics —
   `tests/unit/test_agent_memory_check.py` (3) and
   `tests/unit/test_gate_decision_artifacts.py::test_g1_packet_remains_unapproved_prep`.
   These must not grow. Do not fix them in this plan.
8. `tests/contract/test_metrics.py` is `pytest.mark.integration` and requires a
   migrated PostgreSQL. There is no database in this environment. Integration
   tests are written but NOT run here; report that honestly rather than
   claiming end-to-end validation.

## Shared interface contract (both tasks depend on it — verbatim)

Task 2 registers the metric; Task 1 supplies its API-layer adapter. They must
agree exactly on these three literals:

- `canonical_name = "opportunities"`
- `owning_query = "opportunities_rows_v1"`
- The adapter key in `routers/metrics.py::_OWNING_QUERIES` is
  `"opportunities_rows_v1"`, bound to a function that returns
  `_MetricEvidence(rows=(), unknown_reason=metric.unknown_reason)` — the exact
  shape `_pipeline_funnel_rows_v1` already uses for an absent evidence source.

## Task 1 — P1/V4 metrics authorization (Option B)

**Fence (exclusive ownership):**
- `python/smartmatch_authz/smartmatch_authz/policy.py`
- `python/smartmatch_authz/smartmatch_authz/__init__.py`
- `services/api/smartmatch_api/routers/metrics.py`
- `tests/authz/test_policy_matrix.py`
- `tests/contract/test_metrics.py`
- `tests/unit/` — only new/edited policy tests it adds

**Authorized policy (from the closed decision §4, verbatim):**

| Operation | Roles permitted |
|---|---|
| `metrics.read` (aggregates) | Any **active unit membership** with a role (bare `resource_grant` **denied**) |
| `metrics.drill_down` | `admin`, `coordinator` only |

Scope: student → subtree of their unit; school coordinator → subtree of their
school unit; `admin` → unrestricted within tenant for aggregates.

**Controller ruling carried into this task (R1):** "any active membership with
a role, bare `resource_grant` denied" cannot be expressed with
`required_roles`, because `membership.role` is free text (`schema.py` —
`sa.Column("role", sa.Text)`), so there is no finite role set to enumerate and
inventing one would be a policy invention. It is also not expressible as
`required_roles=frozenset()`, because `evaluate`'s Path 2 permits a bare grant
in exactly that case. Express it as a first-class policy concept: add a
keyword-only `require_membership: bool = False` to `evaluate` and
`assert_allowed`, meaning *an explicit resource grant alone does not satisfy
this operation; an active membership must cover the owning unit path*.
Existing call sites are unaffected by the default. Cost if wrong: a new policy
keyword to remove, and one call site to rewrite.

**Work:**
1. `policy.py`: add `require_membership` to `evaluate` and `assert_allowed`.
   When it is set and no active membership covered the path, Path 2 must deny
   with a distinct, stable reason code (e.g. `resource_grant_lacks_membership`)
   rather than allowing. Suspension, tenant mismatch, and explicit deny keep
   their current precedence — they are checked before either grant path.
   Document the rule in the module docstring alongside the existing four.
2. `routers/metrics.py`: split `_authorize_unit_read` into two authorizers —
   an aggregate authorizer (`require_membership=True`, no `required_roles`) and
   a drill-down authorizer (`required_roles=_DRILL_DOWN_ROLES` where
   `_DRILL_DOWN_ROLES: Final[frozenset[str]] = frozenset({"admin",
   "coordinator"})`, plus `require_membership=True`). `list_metrics` calls the
   aggregate one; `metric_drill_down` calls the drill-down one. Authorization
   still runs before any conditional-request handling and before the
   metric-not-found check — a 404 or a 304 must never be reachable by an
   unauthorized caller. Update the docstrings that currently describe the
   ungated behaviour.
3. `routers/metrics.py`: add the `"opportunities_rows_v1"` adapter per the
   shared interface contract above.
4. `tests/authz/test_policy_matrix.py`: retire
   `INTENTIONALLY_UNGATED_OPERATIONS` for `metrics.read` and
   `metrics.drill_down`. `metrics.drill_down` becomes an ordinary role-gated
   row naming `_DRILL_DOWN_ROLES`. `metrics.read` has no role constant, so it
   needs its own honest category — a `MEMBERSHIP_ONLY_OPERATIONS` set with the
   same rigour the ungated set had: both directions of membership checked, and
   a test that a bare `resource_grant` is now DENIED for `metrics.read` (the
   inverse of the test that pinned the old behaviour). If
   `INTENTIONALLY_UNGATED_OPERATIONS` ends up empty, keep the constant and its
   machinery — an empty set with its S-007 rationale is the record, matching
   how `GAPS` is kept after being emptied. Update the module docstring's S-007
   section so it describes the code as it now is.
5. Negative coverage required by the decision record §6: wrong-role,
   sibling-unit, suspended, cross-tenant, expired-membership, and
   explicit-deny cases, for both operations.
6. `tests/contract/test_metrics.py`: a `student`-role principal reads
   aggregates but is refused drill-down; a bare `resource_grant` principal is
   refused aggregates; an `admin`/`coordinator` principal keeps today's
   behaviour and the authorized drill-down count still equals the aggregate.
   Refusal must use the standard error envelope, not an empty row list.
7. Regenerate `contracts/openapi/smartmatch.json` only if response docs change.

**Verification:** `.venv/bin/pytest tests/ -m "not integration" -q`,
`.venv/bin/ruff format --check .`, `.venv/bin/ruff check .`, and the project's
typecheck. Integration tests are written but cannot run (Constraint 8).

## Task 2 — P8/V5 card O1: register `opportunities`

**Fence (exclusive ownership):**
- `python/smartmatch_domain/smartmatch_domain/metrics.py`
- `tests/unit/test_metrics_register.py`
- new fixture file(s) under `tests/fixtures/` if needed

**Explicitly out of fence:** `services/api/smartmatch_api/routers/metrics.py`
(Task 1 owns it and supplies the adapter), anything under `apps/web`, any
migration, any persistence change. Cards O2–O4 are blocked and are not in
scope.

**Work:**
1. Add one `MetricDefinition` to `METRIC_REGISTER`:
   - `canonical_name="opportunities"`, `display_name="Opportunities"`
   - `definition` — the counting rule copied from the ratified decision §1: an
     event row counts when its category is one of the in-list programmatic
     engagement types (hackathon, datathon, competition, guest lecturer event,
     school event); out-of-list rows do not count until the IA West
     Coordinator reviews and either assigns an in-list category or explicitly
     approves inclusion. The in-list set is non-exhaustive; out-of-list is not
     invalid.
   - `owning_query="opportunities_rows_v1"` (shared interface contract)
   - `drill_down` — the constituent rows the same query returns.
   - `unknown_reason=OPPORTUNITIES_UNKNOWN_REASON`, a new module constant
     naming the real blockers honestly: S12 pipeline persistence is not
     started, so no evidence source exists yet (card O3 binds storage).
2. Export the in-list category set as a module-level constant
   (e.g. `OPPORTUNITY_IN_LIST_CATEGORIES`) so the category shape is data, not
   prose buried in a string, and a later card cannot silently disagree with the
   decision record. Normalize comparison case-insensitively.
3. Add a category-shape helper for the in-list vs out-of-list distinction that
   returns three states, never a boolean: in-list (counts), out-of-list
   (pending coordinator review — NOT invalid, NOT counted), and — if the
   category is absent — pending review as well. Out-of-list must never be
   reported as an error.
4. `tests/unit/test_metrics_register.py`: `opportunities` is registered, is
   unknown with a reason naming S12, and its definition text carries the
   ratified counting rule. Category-shape fixtures for in-list and
   out-of-list examples (in-list: each of the five; out-of-list: at least one
   raw/unmapped label) asserting the three-state outcome. Assert the
   registered `owning_query` is exactly `"opportunities_rows_v1"`.
5. Do NOT flip
   `tests/contract/test_metrics.py::test_pipeline_unknown_is_null_with_an_empty_drill_down`
   — that flip belongs to card O3 and only for stages with real evidence.

**Verification:** `.venv/bin/pytest tests/unit tests/authz tests/golden -q`,
`.venv/bin/ruff format --check .`, `.venv/bin/ruff check .`.
