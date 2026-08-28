# Orchestrator handoff

**For:** the next orchestrating session (Opus 5, high effort)
**From:** the session that closed the Wave 0 HIGH defects and built Waves 1–3D
**Date:** 2026-08-28
**Repo (absolute):** `/mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped`
**Branch:** `friday-deliverable-828` — 19 commits ahead of `main`
**Working tree:** clean, everything committed
**Not pushed.** Nothing has reached CI. That is the next action.

> This file supersedes the previous handoff (Wave A/B of the
> `claude/smart-match-v1-migration-sp1t49` migration). That content remains in
> git history.

The approved plan for this session is at
`/home/danny/.claude/plans/given-these-updates-from-eager-kahn.md`.

---

## Standing constraints

Carried forward from the previous handoff. **They referenced a different branch
and contract — confirm with the user that they still bind before relying on
them.**

- `ALLOW_REMOTE_PUSH=false`, `ALLOW_CLOUD_DEPLOY=false`,
  `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false`.
- No production credentials, no live PII, no live provider calls.
- **Never declare production readiness.** Nothing is deployed.
- **Do not open a pull request** unless the user explicitly asks.
- An agent may not approve its own port.

This session did **not** push and did **not** open a PR — the user asked only to
commit and hand off.

---

## Local gate at handoff

`make check` passes in full: format, lint, `mypy --strict`, 4 import contracts,
**880 passed / 1 skipped**, forbidden-behaviour scan clean (331 files),
agent-memory ledger clean (3 records), license policy clean (43 allowed, 4
recorded exceptions), environment isolation clean (4 environments, 40
identifiers, none shared).

`make openapi-check` reports the committed document current.

---

## What landed (8 commits)

| Commit | Wave | Summary |
|---|---|---|
| `c03eb43` | 0 | Worker seam — both HIGH merge blockers |
| `8f24e41` | 1E | `resolved_date()` resolves in the event's own timezone |
| `51c291f` | 1F | Column contract, per-column blank sentinels |
| `6baf40e` | 1A+2B | Metric register (domain) + metrics routes (ADR-0011) |
| `d55fa02` | 1G | Engagement schema, migration `0009` |
| `9edeea3` | 2H | Body-size middleware, authz matcher, `/v1/me` suspension, OpenAPI `oneOf` |
| `dccea8d` | 3D | Web portal calls onto the request seam, `mockData` retired |
| `ad273f2` | — | OpenAPI regenerated once, after both API-surface changes |

### Wave 0 — verified in source, not taken on trust

Both HIGH defects closed. One root cause: the handler owned a session it should
not have.

- `_review_session_factory` and its undisposed second engine are **gone** from
  `handlers.py`. The only remaining `lru_cache` is `get_settings` in
  `config.py`, which is correct.
- `CommandContext.session` carries the executor-owned transaction.
- `execution.py::_finish` — transition applied → `append_event` + one
  `commit()`; not applied → `session.rollback()` (discarding the handler's
  staged review items) then a **fresh** session for the `job.outcome_discarded`
  event. Failure paths roll back before writing the terminal event.
- `_emit` deliberately keeps its own separate session. **Do not "fix" this** —
  progress must be visible mid-run and survive a rollback.

---

## Blockers

### 1. No PostgreSQL locally — integration proof exists only on CI *(environmental)*

No `postgres` user, no package, no systemd unit, no root for `apt-get`, and
Docker Desktop's daemon is not running. `make db-up`, `make migrate-check` and
`make test-integration` **cannot run here**.

This matters: the Wave 0 fix — the reason PR #7 was blocked — is proven by
integration tests, and migration `0009` has ~20 unrun behavioural constraint
tests.

**CI covers it.** `.github/workflows/verify.yml` runs a `postgres:16` service,
`cd db && alembic upgrade head` from empty (line 92), and `pytest tests/` with
**no marker exclusion** (line 95).

To verify locally: start Docker Desktop, then
`make db-up && make migrate && make test-integration`.

### 2. Metrics routes are ungated — a decision, not a bug. **Needs a call.**

`services/api/smartmatch_api/routers/metrics.py::_authorize_unit_read` calls
`assert_allowed` with **no `required_roles`**. The imports router its docstring
claims to mirror "exactly" (`routers/imports.py:232-241`) passes
`required_roles=_IMPORT_ROLES`. That docstring is inaccurate, and **any active
membership at the unit, of any role, can read unit metrics and drill into the
underlying rows.**

Drill-down returns the actual rows behind an aggregate, and ADR-0014 is a
minimum-disclosure decision. This may be right for a metrics surface, or too
open for drill-down specifically — but it should be chosen, not inherited by
accident from a helper copied without its role gate.

Recorded honestly rather than papered over: `tests/authz/test_policy_matrix.py`
gained `INTENTIONALLY_UNGATED_OPERATIONS`, and every universal property scoped
out for these operations has an explicit positive counterpart test asserting the
actual ungated behaviour. **If these should be gated, add `required_roles` in
`metrics.py`; the matrix rows follow from it.**

### 3. `npm ci` cannot complete on the `/mnt/c` mount *(environmental)*

Three attempts failed with `ENOTEMPTY: rmdir node_modules/date-fns/docs` and
`ENOENT: mkdir node_modules/tar` — Windows holds directory handles on DrvFs. The
identical install succeeds in **13 seconds** on the WSL-native filesystem.

`apps/web/legacy-frontend/node_modules` is currently a **symlink** to
`/home/danny/lf-nodemodules/node_modules`. Because `.gitignore` matches
directories, the symlink appeared as untracked and is excluded via
`.git/info/exclude` (local only — tracked `.gitignore` untouched).

To rebuild web deps:

```bash
mkdir -p ~/lf-nodemodules && cd ~/lf-nodemodules
cp /mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/apps/web/legacy-frontend/package.json .
cp /mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/apps/web/legacy-frontend/package-lock.json .
npm ci
ln -sfn ~/lf-nodemodules/node_modules \
  /mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/apps/web/legacy-frontend/node_modules
```

### 4. Wave 3D verified by typecheck only, never `vite build`

`tsc --noEmit` passes clean against the migrated `api.ts` (run natively) — the
gate that catches a caller depending on a changed error shape. `vite build` was
not run locally. **The web app has no test runner and zero test files**; CI's web
job is `install → typecheck → build → audit`, so bundling is verified there and
nowhere else. Standing up Vitest remains the obvious follow-up.

### 5. Orphaned Codex sandbox, PID `509944`

Still alive with **write access to the repo** after its job
(`task-mtd3d4on-ahus64`) ended `failed`. `codex-companion cancel` reports no such
job, so it cannot be cancelled cleanly. It is idle; left alone rather than
killing a user process. It left a stale `.git/index.lock` that blocked
committing until cleared. **If commits fail with `index.lock` again, this is
why.**

---

## Remaining work, in order

### Immediate — push and confirm CI

```bash
cd /mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped
git push -u origin friday-deliverable-828
gh pr checks 7 --watch
```

CI is where the Wave 0 fix and migration `0009` actually get proven. **Do not
merge before those are green** — local `make check` deliberately excludes
integration tests. Confirm the user wants a push first (see standing
constraints).

### Wave 3C — provenance wiring (last planned wave, not started)

Fence: `apps/web/legacy-frontend/src/app/pages/**` only.

The ADR-0011 primitives at `src/app/components/provenance/` are complete,
exported, type-safe, and **imported by nothing**. Wire `AccountableValue`,
`MetricValueDisplay`, `MetricDrilldownTrigger` and `SyntheticDataBanner` into the
metric-bearing pages — `Pipeline.tsx` first, since ADR-0011 names it.

Every number gets a definition, a provenance badge, and a drill-down. Unknown
renders as *unknown*, never 0. The synthetic-data banner goes site-wide, which is
what keeps this consistent with `docs/decisions/pilot-decisions.md` §D-0,
recording the copied frontend as development-only and not the product.

The typed metrics client was deliberately **not** added to `lib/api.ts` this
session because the route shape was unsettled. It is settled now (`ad273f2`); add
it as part of 3C.

### Backlog surfaced this session

- **`attendance_record.event_id` has no foreign key** — no `event` table exists
  yet, gated behind ADR-0012's tag vocabulary. Whoever builds `event` must add
  the FK back. Documented at length in migration `0009`.
- **`tests/integration/test_check_constraints.py` is a shared registry** with a
  completeness meta-test over all CHECK constraints. Any future schema wave
  adding constraints must register there — concurrent waves will collide on it.
- **Pipeline funnel metrics resolve to unknown** because S12's persistence is not
  started. That is intended and *is* the ADR-0011 demonstration. Do not "fix" it
  by fabricating a data source.

---

## What Dr. Wang can and cannot be shown

**Can:** a server-assigned identity; a live import that quarantines dirty rows
into a durable review queue; a column contract with fixtures that each provoke a
named finding; a metrics surface that admits when it does not know a number *and
says why*, with a definition and drill-down behind the one number it does know;
and a rewards schema that refuses to hold an unowned reward.

**Cannot:** matching or scoring — `assert_registry_approved()` fails closed at
`factor_registry.py:256` until gate G1 is approved, which is a stakeholder
workshop, not code. Nor the crawler-fed event pipeline (S4/S5), behind gate G3's
threat model. Nor a shippable rewards catalog, which needs D6's named budget
owner.

None of those three is limited by engineering capacity.

---

## Process notes worth carrying forward

- **Drive Codex from Bash directly**, not through the `codex:codex-rescue`
  wrapper:
  `node /home/danny/.claude/plugins/cache/openai-codex/codex/1.0.4/scripts/codex-companion.mjs task --background --write "<prompt>"`,
  then `status <id>` / `result <id>`. Costs the orchestrator no context.
- **Leave `--model` unset.** The account's configured model is `gpt-5.6-sol`;
  passing plain `gpt-5.6` (what `/codex 5.6` sends) is rejected by this
  ChatGPT-account plan.
- **A route's policy-matrix row must travel with the route.** Fencing Codex out
  of `test_policy_matrix.py` to avoid a collision meant it could not add its own
  row, and the completeness control failed. Give whoever writes a route the
  matrix file, or hand the row off explicitly.
- **Anchor status-poll greps to the status column.** Matching bare
  `completed|failed` against full output matches text echoed inside the job's own
  summary and fires early.
- Codex stopping to ask rather than implementing was correct twice this session
  (the ADR-0011 data-source blocker; the suite that appeared hung at 17%). Read
  its result before assuming a run failed.
