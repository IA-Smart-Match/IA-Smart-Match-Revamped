# Critical path: job authorization (grant deny + owning unit)

**IDs:** CP-GRANT, CP-A5
**Parent:** [critical-path-plans.md](critical-path-plans.md)

Two defects in the same files (`services/api/smartmatch_api/routers/jobs.py`,
and the re-drive router). Do them as two commits, GRANT first, so the A4
matrix is rewritten once.

Planning only.

---

## 1. CP-GRANT — Job reads ignore `resource_grant`

### (a) What / where

Policy rule 3: an explicit deny beats inheritance. Re-drive and abandon apply
it. Job **reads** do not: `_authorize_job_read` never consults `resource_grant`.
An administrator who carved one job out of a broad grant with an explicit DENY
is refused on `POST /v1/jobs/{id}/redrive` and `/abandon` and **allowed** on
`GET /v1/jobs/{id}` and `GET /v1/jobs/{id}/events`.

Documented in `docs/plans/pr1-blockers-handoff.md` §3.1 (PR1 branch only),
discovered by A4 (`tests/authz/test_policy_matrix.py`). Adjacent to S-006 in
`docs/security/scaffold-security-review.md` but it is not the same hole:
S-006 is missing *unit* data; this is a missing *rule* on a path that already
authorizes.

### (b) Status

Open. Exists only after A4. Two matrix cells currently pin the wrong
behaviour so the fix will fail them on purpose.

### (c) Execution plan

**Files:**

- `services/api/smartmatch_api/routers/jobs.py` — `_authorize_job_read`
- `tests/authz/test_policy_matrix.py` — the two cells
- Possibly `python/smartmatch_authz/` only if the router was hand-rolling
  policy (re-drive already does that for the same reason: no owning unit).
  Prefer calling the same helper re-drive uses rather than a third copy.

**Tasks, in order:**

1. On the PR1 tree, read `_authorize_job_read` and `_authorize_redrive`. Diff
   the grant step. Do not guess from this plan's prose.
2. Add an explicit DENY `resource_grant` for a job the principal could otherwise
   read (admin or oversight role). Assert GET status and SSE return the same
   denial class as re-drive (stable error envelope, no existence leak —
   security review "Denials do not leak existence").
3. Implement: after suspension, tenant, and actor-or-role checks, evaluate
   grants. Explicit deny must win even for the job's actor if that is what
   policy says — **read `policy.evaluate` before deciding**; do not invent a
   special case that re-drive does not have.
4. Update the two matrix cells. Completeness tests must still require every
   `job.*` operation × principal shape.
5. Confirm a bare ALLOW grant still cannot satisfy a role-gated job read
   (S-007). This path must not re-open it.

Do **not** add `owning_unit_id` in this commit.

### (d) Dependencies

Blocked by CP-PR1 (A4 matrix). Blocks nothing except a cleaner A5 diff.
Unrelated to G1.

### (e) Acceptance

- [ ] Principal with oversight role + explicit DENY on job J: GET `/v1/jobs/J`
      and GET `/v1/jobs/J/events` denied; same code family as re-drive deny.
- [ ] Principal with oversight role and no deny: still allowed (today's allow).
- [ ] Job actor without deny: still allowed (do not regress "own job").
- [ ] Matrix cells that documented the hole now document deny-wins; the
      completeness test stays green.
- [ ] No OpenAPI change unless the error `code` string changes — if it does,
      regenerate `contracts/openapi/smartmatch.json`.

### (f) Priority

First engineering item after CP-PR1. The handoff's own suggested order.

---

## 2. CP-A5 — `job.owning_unit_id` (S-006)

### (a) What / where

`job` has no owning org unit. Authorization is actor-or-oversight-role within
the tenant. A coordinator in department A can read, re-drive, and abandon
department B's jobs.

Sources:

- `docs/plans/defect-remediation.md` §8 (sequence, FK shape, NULL fallback)
- `docs/plans/remaining-foundation-r1-work.md` A5; J4 note
- `docs/architecture/command-path.md` §3 ("What this command does not guard")
- `docs/security/scaffold-security-review.md` S-006
- `docs/plans/orchestrator-handoff.md` trap: a unit-scoped job-read test had
  to be removed because the control did not exist — **bring it back here**
- `docs/plans/pr1-blockers-handoff.md` §3.1: A4 pins this as an equality
  across all four `job.*` operations; `payload.unit_id` exists after J10

Target shape already exists: `services/api/smartmatch_api/routers/imports.py`
loads the unit, builds `Resource(..., owning_unit_path=...)`, calls
`assert_allowed`.

### (b) Status

Open on `main` and on PR1. Schema work for J9/J17 is `0004`; J10 payload is
`0005`; A5 is **`0006`**. F7 (widened drift test) is done on `main` — the new
composite FK will be checked. F11 (`transaction_per_migration`) is done —
`0006` will commit in its own transaction.

Nothing is deployed, so backfill is free until first deploy
(`defect-remediation.md` §8.2, §10.5).

### (c) Execution plan

Follow defect-remediation §8.2. Do not invent a second sequence.

**1. Expand — migration `0006`**

- `job.owning_unit_id UUID NULL`
- Composite FK `(tenant_id, owning_unit_id) → org_unit(tenant_id, id)`
- `ON DELETE RESTRICT` (not `SET NULL` — that silently reopens S-006)
- Mirror in `python/smartmatch_persistence/smartmatch_persistence/schema.py`
  **including `ondelete`**
- Drift test should pick this up without a hard-coded table list (F7). If a
  list still exists, add `job`.

**2. Populate**

- `submit_command` / imports router: for `import.create`, the unit is already
  loaded and authorized; write `owning_unit_id` in the same transaction as
  job + outbox + payload (J10).
- Command types with no unit leave NULL. Modelled, not a gap.

**3. Backfill**

- Existing rows: `payload.unit_id` where command type is `import.create`.
- Else NULL.
- No production data today.

**4. Enforce**

- `_authorize_job_read` (and re-drive/abandon, which share the gap): keep
  "actor may read their own job" first (coordinator who changed units must
  not lose their job).
- Then `Resource(resource_type="job", resource_id=..., tenant_id=...,
  owning_unit_path=...)` + `assert_allowed` with oversight roles.
- Path lookup: `org_unit` join or follow `principals.py` `sa.cast(..., sa.Text)`
  ltree pattern.
- **NULL branch:** today's actor-or-oversight rule, labelled in code, own
  reason code `unscoped_job` so audit shows remaining exposure.
- Restore the unit-scoped negative test removed during Wave C.

**5. Contract phase (not this PR)**

- When every row is populated and the release fully promoted: `NOT NULL`,
  delete the fallback. The fallback must not become permanent.

**6. Decide while the file is open (defect-remediation §8.3, §11 Q6)**

- Resolve owning unit path **at read time** (recommended) vs snapshot on the
  job. Record the choice in the migration docstring.
- SSE authorizes once at stream open. Mid-stream membership expiry is out of
  A5's *mechanism* but in scope for a written decision: re-check, short
  stream TTL, or accept and document.

**Files:**

- `db/migrations/versions/0006_job_owning_unit.py` (new)
- `python/smartmatch_persistence/smartmatch_persistence/schema.py`
- `python/smartmatch_persistence/smartmatch_persistence/jobs.py`
- `services/api/smartmatch_api/commands.py`
- `services/api/smartmatch_api/routers/{jobs,redrive,imports}.py`
- `tests/authz/test_policy_matrix.py` (cells will break — that is the signal)
- `tests/integration/test_command_path.py` / new `test_job_owning_unit.py`
- ADR-0004 amendment only if the drift-test story needs it (probably not)

### (d) Dependencies

| This needs | Why |
|---|---|
| CP-PR1 | J10 payload for backfill; A4 matrix as the oracle |
| CP-GRANT | Avoid rewriting matrix cells twice |
| F7, F11 | Done on `main` |
| Not Wave C | Done (`0003`) |

Wave C and A5 both touch migrations + `schema.py`; they are no longer
concurrent. Do not run a second schema change in the same commit.

**Blocks:** truthful unit-scoped job tests; A4 cells for `job.*` after this
will describe the new rule.

### (e) Acceptance

- [ ] Migration `0006` apply from empty; drift test green both directions.
- [ ] Composite FK present; `tenant_id` positional with parent (F7).
- [ ] Coordinator in unit A: allow own unit's job; deny unit B's job on GET,
      events, redrive, abandon.
- [ ] Job actor who moved units: still reads own job (actor-first rule).
- [ ] `owning_unit_id IS NULL`: fallback fires; audit/deny reason
      `unscoped_job`; test exists.
- [ ] Oversight role still reads within policy (not a silent global allow).
- [ ] Explicit DENY from CP-GRANT still wins after unit scoping.
- [ ] Matrix completeness still holds; previously-equal "any coordinator in
      tenant" cells now split by unit.
- [ ] Read-time vs snapshot decision recorded.
- [ ] SSE mid-stream decision recorded.
- [ ] No `NOT NULL` in `0006`.

### (f) Priority

Immediately after CP-GRANT. Strongest scheduling argument remains: backfill
is free until first deploy (`defect-remediation.md` §8.2).

---

## Interaction with S-007 (grant vs role)

A5 must not make a bare `resource_grant` ALLOW satisfy a role-gated job
operation. Grants convey resource access, not a role (`scaffold-security-review.md`
S-007). Which roles a grant *should* convey remains policy-matrix work; fail
closed until that decision exists (`remaining-foundation-r1-work.md` A4 notes).
A4 on PR1 executed the matrix against current fail-closed behaviour — keep it.

---

## Suggested commits

1. `fix(authz): job reads honour resource_grant deny` (CP-GRANT)
2. `feat(jobs): owning_unit_id expand-phase, populate, enforce with unscoped fallback` (CP-A5)

High `code-review` on each staged diff (`orchestrator-handoff.md` process).
Verify findings against the code before acting.
