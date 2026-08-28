# Implementation plan — D6/D7 rewards: ledger fold, S8 listing, S9 redemption

**Date:** 2026-08-28 · **Plan id:** P7 · **Worktree branch:** `plan/d6-rewards`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.

## Standing constraints (restated; permanent)

- Never list an unowned or unfunded item; never weaken `budget_owner_id`,
  `funded`, tenant FK, point-cost, or fulfilment constraints from migration
  `0009`. A coordinator role is not a budget owner; an arbitrary UUID is not
  ownership.
- The browser never computes or decrements a balance (ADR-0013).
- Do not copy legacy point costs (`studentRewardsCatalog.ts` 2,500–45,000 vs
  25 pts/event is a documented defect, Fix #15); legacy names are discussion
  input only.
- Seed no production catalog data in migrations.
- No push, no PR, no production-readiness claims.

## Stop-gate (verify before any card)

Required committed artifacts:

1. **D6** — the completed successor of
   `docs/pilot-data/rewards-catalog-worksheet.md`: every proposed listable
   item has a **named human budget owner** represented by a real same-tenant
   `user_account`, with written confirmation of funded balance and fulfilment
   commitment. A blank worksheet is the honest pre-workshop state and selects
   nothing.
2. **D7** — program-owner ratification of: points per verified attendance,
   calibration N ("cheapest reward reachable within N events" — ADR-0013's 3
   is a proposal, not approval), item point costs, and catalog content.
3. Reward read and redemption **roles** decided (the prep contract labels
   these TBD). If roles are missing, cards R3+ stop before route work.

Prerequisite engineering (verify, do not assume): **S6** attendance-derived
point evidence and **S7** server-side ledger fold must exist before S8/S9. If
S6/S7 are absent, this plan's cards L1–L2 build them — but only after D6/D7
artifacts exist, because the fold's earn policy comes from D7.

## Current state (verifiable)

- Migration `db/migrations/versions/0009_engagement_schema.py` +
  `smartmatch_persistence/schema.py`: `reward_item.budget_owner_id NOT NULL`
  with composite tenant FK; `funded NOT NULL` (server default false — an
  insert-time default, not a listing permission); positive `points_cost`,
  non-negative `fulfilment_cost` checks.
  `tests/integration/test_engagement_schema_constraints.py` proves the
  refusals.
- `services/api/smartmatch_api/routers/engagement.py` declares no handlers;
  OpenAPI has no rewards/catalog/balance/redemption operation; the fail-closed
  scan in `tests/unit/test_matching_fail_closed.py` rejects reward routes and
  flips deliberately only in card R3.
- `point_ledger_entry` append-only is comment-only (migration `0009`
  non-blocking note) — card L2 hardens it.
- Frontend `studentPoints.ts` / `studentRewardsCatalog.ts` still exist and are
  retired in card U1.

## Task cards

### Card L1 — S6/S7 ledger fold (sequential first; skip if already landed)

- **Fence:** domain fold module in `smartmatch_domain`, persistence adapter,
  unit + integration tests. Migration only if the ledger needs new columns
  (via the portfolio migration owner).
- **Work:** server-side fold from attendance evidence to point balance using
  the D7-ratified earn policy; append-only compensation entries for
  corrections (never destructive updates); balances derived, never stored as
  authoritative mutable state.
- **Tests:** fold determinism; compensation path; integration proof that
  ledger rows are append-only (card L2's trigger enforces it).

### Card L2 — append-only enforcement (parallel with L3 after L1)

- **Fence:** new migration adding a DB-level guard (trigger or rule) making
  `point_ledger_entry` updates/deletes fail; integration tests.

### Card L3 — S8 listing service (parallel with L2)

- **Fence:** repository/service query module + tests; no routes yet.
- **Work:** listing returns only rows with `funded = true` and a valid
  same-tenant owner; server-derived balance and per-item reachability
  (progress only toward reachable items, engagement-model §4).
- **Tests:** unfunded/unowned rows never appear (integration).

### Card L4 — S9 redemption command (after L1)

- **Fence:** durable-command module + tests.
- **Work:** idempotent redemption through the durable command path with
  transitions `requested → approved → fulfilled | denied | expired`; audited;
  concurrent duplicate requests resolve to one redemption; balance check and
  ledger debit are atomic server-side.

### Card C1 — calibration test (after L3; uses D7's N)

- **Fence:** new test asserting the cheapest **listed** reward is reachable
  within N verified attendances under the ratified earn policy, against
  synthetic approved fixtures (fixture values copied from the D6/D7 artifact,
  never invented).

### Card R3 — routes, policy, OpenAPI (after L3/L4; requires decided roles)

- **Fence:** `services/api/smartmatch_api/routers/engagement.py`,
  `tests/authz/test_policy_matrix.py` rows for every new operation,
  `tests/contract/` route tests, OpenAPI regeneration + `make openapi-check`,
  and the deliberate flip of the fail-closed reward-route scan — one commit.
- **Work:** S8 list + balance read routes, S9 redemption command route, gated
  to the decided roles; unit-scoped; standard error envelope on refusal.

### Card U1 — frontend (after R3)

- **Fence:** `apps/web/legacy-frontend` rewards surfaces;
  `studentPoints.ts`, `studentRewardsCatalog.ts` deleted when no caller
  remains.
- **Work:** render server values only; progress bars only toward reachable
  items; redemption UI drives the S9 command and reflects server state; no
  client-side balance math. Unknown values render unknown (plan P3 pattern).

## Evidence ladder

1. Per-card focused pytest; `make check`
2. `make openapi-check` after R3
3. Web typecheck/build after U1
4. **CI-only proof:** migrations from empty PostgreSQL; constraint, fold,
   idempotency integration tests; web build.

## Done means

- Every listed item has a named owner and funded balance (DB + service + test).
- Cheapest listed reward satisfies ratified N; calibration test cites D7.
- Redemption is durable, authorized, auditable, idempotent.
- Browser computes nothing; legacy catalog/point files are gone.
- No tentative D7 number was adopted as approved.
