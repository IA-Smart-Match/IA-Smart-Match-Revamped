# Maintaining a Supabase-hosted database

Prerequisite: [supabase-setup.md](supabase-setup.md) — this document assumes
a project already exists, migrated to head, with `SMARTMATCH_DATABASE_URL`
pointed at it. **Staging/synthetic data only** — the same scope constraint
as the setup guide: `ALLOW_CLOUD_DEPLOY` stays `false`, and D8 is not met, so
this project never holds real student data.

## Backup schedule and retention

**Verify the actual schedule and retention window in the dashboard**
(Project Settings → Database → Backups) before relying on any number below —
Supabase's plan-tier backup behavior changes, and asserting a specific
retention period here would go stale silently.

- What the Supabase plan gives you (verify in dashboard, do not assume):
  most paid tiers include automatic daily backups with a retention window
  tied to the plan; Point-in-Time Recovery (PITR) is typically a separate
  add-on with its own retention. Free-tier projects may pause when idle and
  have no automatic backup guarantee at all — confirm the current project's
  tier before treating its backups as a safety net.
- **Regardless of tier, keep a scheduled logical `pg_dump` fallback outside
  Supabase**, mirroring the pattern already used on the pilot VM
  (`scripts/vm/deploy.sh`, the `pg_dump --clean --if-exists | gzip` step run
  before every migration):

  ```bash
  PGPASSWORD='<PASSWORD>' pg_dump \
    --host=aws-0-<REGION>.pooler.supabase.com \
    --port=5432 \
    --username=postgres.<PROJECT_REF> \
    --dbname=postgres \
    --clean --if-exists \
    | gzip > "smartmatch-supabase-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
  ```

  Store this dump off-Supabase (e.g. a GCS bucket, matching the pilot VM's
  local `backups/` convention but off the same infrastructure the primary
  copy lives on). This dump is a **disaster-recovery artifact**, not a
  convenience copy for pulling data to a dev machine — synthetic pilot data
  can be regenerated from `make seed-pilot`; the dump exists in case both
  the live project and its own automatic backups are unavailable.
- Retention for this fallback dump: keep the most recent 14, mirroring
  `scripts/vm/deploy.sh`'s bounded retention for the same reason — an
  unbounded dump directory fills a disk and takes the next deployment down
  with it. Prune older ones as part of whatever runs the scheduled dump
  (cron, GitHub Actions schedule, etc.).

## Restore drill

Run this against a **separate scratch Supabase project or a local Docker
Postgres** — never restore over the live staging project as a drill.

1. **Take a fresh dump of the source** (or use the most recent scheduled
   fallback dump from above):

   ```bash
   PGPASSWORD='<PASSWORD>' pg_dump \
     --host=aws-0-<REGION>.pooler.supabase.com \
     --port=5432 \
     --username=postgres.<PROJECT_REF> \
     --dbname=postgres \
     --clean --if-exists \
     | gzip > restore-drill.sql.gz
   ```

2. **Stand up a scratch target** — either a local Docker Postgres
   (`docker compose up -d db` against a scratch `docker-compose.yml`
   project name) or a throwaway Supabase project. Do not point this at the
   staging project created in `supabase-setup.md`.

3. **Restore:**

   ```bash
   gunzip -c restore-drill.sql.gz | \
     PGPASSWORD='<SCRATCH_PASSWORD>' psql \
       --host=<SCRATCH_HOST> \
       --port=<SCRATCH_PORT> \
       --username=<SCRATCH_USER> \
       --dbname=postgres \
       -v ON_ERROR_STOP=1
   ```

   `-v ON_ERROR_STOP=1` matters here for the same reason `db/migrations/env.py`
   calls it out for applying a generated migration script: without it,
   `psql` rolls back a failed statement and silently continues to the next
   one, which can leave the target schema ahead of what actually succeeded
   with no error reported.

4. **Pass/fail check** — run against the restored scratch database:

   ```bash
   SMARTMATCH_DATABASE_URL="postgresql+psycopg://<SCRATCH_USER>:<SCRATCH_PASSWORD>@<SCRATCH_HOST>:<SCRATCH_PORT>/postgres" \
     pytest tests/integration/test_schema_matches_migration.py -m integration
   ```

   **Pass:** the drift test passes, `SELECT count(*) FROM alembic_version;`
   returns exactly one row at the expected head revision (`0042_exercise_ann_dataset`
   or later, whatever `db/migrations/versions/` currently ends at), and spot
   row counts on a handful of core tables (e.g. `org_unit`, `membership`)
   are non-zero and plausible against what the source held.

   **Fail:** any of the above disagrees, or `psql` reported an error during
   restore. Treat a failed drill as a finding, not a shrug — it means the
   dump format, the restore command, or the target's Postgres version has
   drifted from what this document assumes, and the *next* real disaster
   recovery would fail the same way.

5. **Tear down the scratch target.** It is not a long-lived environment.

Run this drill on a recurring cadence (recommended: before any migration
touching a large table, and at minimum quarterly) so a failure is caught
before an actual incident needs it.

## Migration procedure

1. Write the new revision in `db/migrations/versions/` **and** mirror the
   change in `python/smartmatch_persistence/smartmatch_persistence/schema.py` in the same change — the
   drift test (`tests/integration/test_schema_matches_migration.py`) fails
   the build if only one side moves.
2. Take a fresh `pg_dump` (see [Backup schedule](#backup-schedule-and-retention))
   immediately before running the migration against Supabase.
3. Apply:

   ```bash
   cd db && SMARTMATCH_DATABASE_URL="<supabase-url>" alembic upgrade head
   ```

4. **Never downgrade, never autogenerate.** Migrations are forward-only by
   policy (ADR-0009); see
   [deploy-runbook.md](deploy-runbook.md#when-a-revision-fails-part-way) —
   the authority on migration policy and on what to do when a revision fails
   part-way — for the general procedure. It applies identically against
   Supabase.
5. Re-run the drift test against the Supabase URL to confirm parity before
   calling the migration done.

## Credential rotation

1. In the Supabase dashboard: Project Settings → Database → **Reset
   database password**. This immediately invalidates the old password on
   every connection path (pooler and direct).
2. Update the value in wherever it actually lives — the gitignored `.env`
   locally, or the secret manager entry in a deployed environment. Never a
   file in this repository.
3. Restart every process holding a `SMARTMATCH_DATABASE_URL` connection pool
   (api, worker, scheduler, or any local `make run-api` process) — an open
   SQLAlchemy pool does not notice a password rotation on its own for
   connections it already holds, only on new connection attempts once they
   start failing.
4. No code change is required; the credential lives only in the connection
   string.
5. If rotation follows a suspected leak rather than routine hygiene, also
   check CI's secret-scan history and this repository's commit patches for
   the old value, and treat any hit as a confirmed compromise requiring
   immediate rotation regardless of whether the scan already caught it.

## Monitoring

- **Pooler connection count vs. plan limit** — check in the dashboard
  (Project Settings → Database → Connection pooling, or the project's
  usage/reports page) against the `SMARTMATCH_DB_POOL_SIZE` /
  `SMARTMATCH_DB_MAX_OVERFLOW` values in use (see
  [supabase-setup.md §6](supabase-setup.md#6-tune-the-connection-pool-down)).
  `pool_pre_ping=True` (default in `python/smartmatch_persistence/smartmatch_persistence/engine.py`)
  covers idle-connection drops but does **not** cover pool exhaustion —
  that surfaces as application-level `TimeoutError`s or SQLSTATE `53300`.
- **Alerts** — verify what alerting the current Supabase plan tier offers
  (dashboard → Reports/Alerts) rather than assuming a specific integration;
  this repository has no built-in Supabase alert wiring today. Until an
  alert is configured, the pilot dataset rebuild guide and periodic manual
  `SELECT count(*)` spot checks are the only signal an operator has.
- **Project pause** — free-tier Supabase projects pause when idle; a paused
  project surfaces to the app as `OperationalError` (connection
  refused/timeout), identical to a wrong host or port. If connectivity
  fails and the host/port/password all check out, check the dashboard for a
  paused project first.

## Incident steps

Read top-down; each entry is location → cause → fix, matching the debugging
table already in
[the setup ticket](../plans/2026-09-14-supabase-migration-ticket.md#debugging-guide--error-codes-and-where-to-look).

| Symptom | Location | Likely cause | Fix |
|---|---|---|---|
| `OperationalError` (connection refused/timeout) | psycopg/SQLAlchemy, in api/worker logs | Wrong host/port, IPv6-only direct host on an IPv4 network, or a paused Supabase project | Switch to the session pooler (§3 of setup); check dashboard for pause state |
| `TimeoutError` from the pool | Same | Pool exhausted against the plan's connection cap | Lower `SMARTMATCH_DB_POOL_SIZE`/`_MAX_OVERFLOW`, or raise the plan's connection limit |
| SQLSTATE `53300` (too many connections) | Postgres, surfaced through psycopg | Hit the Supavisor/direct connection cap | Same fix as pool exhaustion above |
| SQLSTATE `42P01` (undefined table) | Postgres | Migrations not run against this database | Check `alembic_version`; run `alembic upgrade head` (§7 of setup) |
| SQLSTATE `28P01` (auth failed) | Postgres | Wrong password, or using bare `postgres` instead of `postgres.<PROJECT_REF>` on the pooler | Correct the username; rotate password if leaked (see above) |
| "prepared statement ... already exists" | psycopg | Connected through the transaction-mode pooler (port `6543`) | Switch to the session pooler (port `5432`) — see §3 of setup |
| Alembic failure mid-run | `alembic upgrade head` output | A revision failed partway; earlier revisions already committed (`transaction_per_migration=True`, ADR-0009) | Fix the failing revision and re-run; see `deploy-runbook.md` |
| Drift test failure | `test_schema_matches_migration.py` output | `schema.py` and the migrated DB disagree | The test output names the table/constraint; fix whichever side is wrong — never edit both to force agreement |

For anything not in this table, service logs are the next step — the API's
error envelope (`services/api/smartmatch_api/errors.py`) deliberately never
leaks DB detail to clients, so DB-layer debugging always happens in logs,
not in API responses.
