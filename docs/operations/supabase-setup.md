# Setting up Supabase as managed PostgreSQL

**Status: staging/dev only, synthetic data only. `ALLOW_CLOUD_DEPLOY` stays
`false` and stays unchanged by anything in this document.** D8 (real student
data handling) is not met, so **no real student data goes into a Supabase
project set up from this guide, ever**, until D8 closes and someone
explicitly re-authorizes this document for a production database. This
closes the "managed DB backups" pilot-readiness row by giving an operator a
managed Postgres with real backups to point a staging deployment at — it does
not authorize a production cutover.

This is a **documentation-only** implementation of the plan recorded in
[`docs/plans/2026-09-14-supabase-migration-ticket.md`](../plans/2026-09-14-supabase-migration-ticket.md);
read that file for the full rationale. No Supabase project has been created
and no command in this document has actually been run against one — nothing
here should be read as "executed." The ticket lists six acceptance criteria;
three are documentation and are met by this change, three require an
operator to actually stand up a project and are unverified:

**Met (documentation, this change):**

> `docs/operations/supabase-setup.md` and `supabase-maintenance.md` committed.
> `.env.example` documents the Supabase URL shape and pool settings.
> No Supabase keys, Data API, or RLS in the app path;
> `SMARTMATCH_DATABASE_URL` is the only integration point.

**Unverified — pending an operator standing up a project and running these:**

> `alembic upgrade head` runs clean on the Supabase project.
> `test_schema_matches_migration.py` passes against Supabase.
> `make test-integration` passes against Supabase.

Until someone runs those three against a real project, treat every command
in this document as reviewed-but-unexecuted, not as a verified working
procedure.

Supabase is used as **managed Postgres only** — no PostgREST Data API, no
GoTrue auth, no Row Level Security. Authorization stays in
`smartmatch_authz`; the app connects as a direct Postgres client through
`SMARTMATCH_DATABASE_URL`, exactly as it does against the local Docker
`db` service.

## 1. Create the project

1. In the Supabase dashboard, create a new project.
2. **Name it as staging, not production** — e.g. `smartmatch-staging` — so
   nobody mistakes it for a production database later.
3. **Region** — pick the region closest to wherever the app process runs
   (the pilot VM's `us-west1-a`/`us-west2-c`, or your own machine for local
   testing). Record the choice; it cannot be changed without recreating the
   project.
4. Set a strong database password when prompted. **Do not write it into any
   file in this repository.** It goes in a gitignored `.env` or a secret
   manager only (see [Secrets handling](#5-secrets-handling)).
5. Record the **project ref** (the `<PROJECT_REF>` used throughout this
   document — the short id in the project's dashboard URL,
   `https://supabase.com/dashboard/project/<PROJECT_REF>`).

## 2. Verify the Postgres major version

The project must provision **Postgres 16** to match `postgres:16-bookworm`
in `docker-compose.yml` and in CI. Check in the dashboard under
Project Settings → Database. If Supabase provisions a different major
version, **stop** — a version bump is its own ticket, not something to paper
over here.

```sql
SELECT version();
```

## 3. Choose the connection string — pooler vs. direct

Supabase exposes two connection paths. **Which one Alembic (and everything
else) needs is the session pooler, or a direct IPv4-capable connection — never
the transaction-mode pooler.**

| Path | Host shape | Port | Use it? |
|---|---|---|---|
| Session pooler | `aws-0-<region>.pooler.supabase.com` | `5432` | **Yes — default choice** |
| Direct connection | `db.<PROJECT_REF>.supabase.co` | `5432` | Only if you've confirmed IPv4 reachability |
| Transaction pooler | `aws-0-<region>.pooler.supabase.com` | `6543` | **Never** — breaks migrations and seeds |

Why the transaction-mode pooler (port `6543`) is excluded: `seed_pilot.py`
takes a PostgreSQL advisory lock (`pg_advisory_xact_lock`), and psycopg's
prepared statements are per-connection state. Transaction pooling breaks
both — you will see "prepared statement ... already exists" errors mid-run.

Direct connections on newer Supabase projects are **IPv6-only**. If the host
running the app is IPv4-only (most VMs and most laptops without IPv6
transit), use the session pooler — this is the single most common "it won't
connect" cause reported against Supabase.

## 4. Set `SMARTMATCH_DATABASE_URL`

```
postgresql+psycopg://postgres.<PROJECT_REF>:<PASSWORD>@aws-0-<REGION>.pooler.supabase.com:5432/postgres
```

Notes:

- The pooler username is `postgres.<PROJECT_REF>`, not bare `postgres` — a
  bare `postgres` user against the pooler host raises SQLSTATE `28P01`
  (auth failed).
- `sslmode` — Supabase's pooler and direct endpoints both require TLS and
  accept connections without an explicit `sslmode` query parameter (they
  negotiate TLS by default); if your client library refuses to connect
  without one, append `?sslmode=require`. Do not use `sslmode=disable`
  against a Supabase host.
- This value is a secret (it embeds the DB password) and follows the same
  rule as every other credential in this repository: it goes in the
  gitignored `.env` or in Secret Manager, never in a committed file. See
  [.env.example](#5-secrets-handling) below for the placeholder entry.

## 5. Secrets handling

- **Env vars / secret manager only.** No Supabase project ref, host, or
  password is committed to this repository, in this doc or anywhere else.
  Every example above uses `<PROJECT_REF>`, `<REGION>`, and `<PASSWORD>`
  placeholders — replace them locally, never here.
- `.env.example` (see the entries added by this change) documents the URL
  **shape** with a placeholder, exactly like every other credential in that
  file — it is not a real host and must never become one.
- In deployed environments the value comes from Secret Manager, following
  the same convention `SMARTMATCH_EMAIL_API_KEY` and
  `SMARTMATCH_ROUTES_API_KEY` already use in `.env.example`.
- CI's secret scan reads commit patches across every ref — a leaked
  Supabase password cannot be undone by a later commit. If one is ever
  committed by mistake, rotate it in the Supabase dashboard immediately
  (Project Settings → Database → Reset database password) and treat the old
  value as permanently compromised.

## 6. Tune the connection pool down

Supabase plans cap concurrent direct/pooler connections well below the
`postgres:16` compose default of `max_connections=100`. The engine's own
defaults (`SMARTMATCH_DB_POOL_SIZE=20`, `SMARTMATCH_DB_MAX_OVERFLOW=10` per
process, api + worker = 60 connections) assume a dedicated local Postgres —
**verify your plan's connection limit in the dashboard** (Project Settings →
Database → Connection pooling) and size these down to fit under it:

```
SMARTMATCH_DB_POOL_SIZE=<fits under the plan limit>
SMARTMATCH_DB_MAX_OVERFLOW=<fits under the plan limit>
```

`pool_pre_ping=True` is already on by default in
`python/smartmatch_persistence/smartmatch_persistence/engine.py` and covers idle-connection drops, but not
pool exhaustion — an undersized plan limit against the default pool sizing
surfaces as `TimeoutError` from the pool, or SQLSTATE `53300` ("too many
connections") from Postgres itself. See
[supabase-maintenance.md](supabase-maintenance.md#monitoring) for what to
watch.

## 7. Run migrations to head

```bash
cd db
SMARTMATCH_DATABASE_URL="postgresql+psycopg://postgres.<PROJECT_REF>:<PASSWORD>@aws-0-<REGION>.pooler.supabase.com:5432/postgres" \
  alembic upgrade head
```

This must land at `0040_booking_cancellation`, the current head revision (see
`db/migrations/versions/`). Migrations are forward-only and hand-written,
never autogenerated (ADR-0009) — a failed revision leaves earlier ones
committed; see
[deploy-runbook.md](deploy-runbook.md#when-a-revision-fails-part-way) for
what to do next.

Confirm the `ltree` extension came up (migration `0001` runs
`CREATE EXTENSION IF NOT EXISTS ltree`):

```sql
SELECT * FROM pg_extension WHERE extname = 'ltree';
```

## 8. Verify schema parity

```bash
pytest tests/integration/test_schema_matches_migration.py -m integration
```

with `SMARTMATCH_DATABASE_URL` pointed at the Supabase project. This is the
drift guard between the hand-written `schema.py` mirror and the migrated
database, and it is the acceptance test that Supabase matches the contract
in both directions.

## 9. Role / GRANT model

There are **two different roles in play here, and they are not the same
model.** Do not call the whole-app role below "least privilege" without
reading this reconciliation first — it is broader than the exercise
convention on purpose, and that gap is documented, not accidental.

### 9a. The exercise-scoped role — mirrors the existing convention exactly

[`docs/operations/exercise-hosting.md` §3, "The database role"](exercise-hosting.md#3-the-database-role)
already defines the owner-decided (2026-09-21) convention for anything
touching `exercise_*` tables: a dedicated role with narrow, **per-table,
per-verb** `GRANT`s on `exercise_*` tables only, no `CREATE`, and migrations
run as a separate owner role rather than this one. If the workload connecting
to this Supabase project is (or includes) the class-exercise product scope,
**follow that document's grant statements as written** — they are
reproduced there, not here, so this file cannot drift out of sync with the
owner-decided list of tables and verbs. Do not re-derive or paraphrase that
SQL in this file.

### 9b. The whole-app staging role — broader than 9a, and that is explicit

For a **whole-app staging deployment** (CBA scope, not the exercise scope
alone) the role below grants blanket read/write across every table in
`public`, rather than the exercise convention's per-table, per-verb list.
This is a real difference in security posture, not a rounding error: a role
built this way can read and write tables the application code never
touches, where the exercise-scoped role in 9a cannot. It is used here only
because a whole-app staging role has no equivalent "the code only ever
touches N named tables" boundary the way the exercise scope does — the CBA
schema is ~49 tables and growing, and enumerating every one here would
silently drift out of sync with `python/smartmatch_persistence/smartmatch_persistence/schema.py`, the
same failure mode 9a avoids by linking out instead of duplicating SQL. If
that boundary is ever defined for the CBA scope, this section should be
narrowed to match 9a's shape rather than kept as blanket grants.

1. Run project creation and `alembic upgrade head` (step 7) as the
   Supabase-provisioned `postgres` role — migrations need DDL privileges,
   and `postgres` is the role that owns the schema and every table
   `alembic upgrade head` creates. `ALTER DEFAULT PRIVILEGES` in step 2
   below is scoped to grants made *by* the role that runs it, so running
   migrations consistently as `postgres` is what makes that default-privilege
   grant apply automatically to tables a future migration creates, without
   a repeated manual `GRANT` after every migration.
2. Create a dedicated application role scoped to the `public` schema (adjust
   the table list as the schema evolves; `python/smartmatch_persistence/smartmatch_persistence/schema.py`
   is the source of truth for what exists):

   ```sql
   CREATE ROLE smartmatch_app WITH LOGIN PASSWORD '<APP_ROLE_PASSWORD>';
   GRANT USAGE ON SCHEMA public TO smartmatch_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO smartmatch_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO smartmatch_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public
     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO smartmatch_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public
     GRANT USAGE, SELECT ON SEQUENCES TO smartmatch_app;
   ```

3. Point the running app's `SMARTMATCH_DATABASE_URL` at `smartmatch_app`,
   not at `postgres`. Keep the `postgres`-role connection string available
   separately (in the same secret manager, under a distinct name) for
   running future migrations — migrations need DDL privileges this role
   deliberately does not have.
4. `smartmatch_app` does **not** need `CREATEDB`, `CREATEROLE`, or
   superuser. If a future migration needs a privilege this role lacks,
   grant it explicitly in that migration's own runbook entry rather than
   widening the role's standing privileges.

## 10. Seed and smoke — synthetic data only

Once migrations are at head and parity is verified (step 8), seed the
project with the same synthetic pilot dataset the local Docker appliance
uses — **never real student or participant data**, per the scope statement
at the top of this document:

```bash
make seed-pilot
make seed-pilot-principals
make seed-pilot-logins    # needs SMARTMATCH_PILOT_*_EMAIL/_PASSWORD pairs in .env
make verify-pilot-dataset
```

Then smoke-test against the Supabase database:

```bash
scripts/compose_smoke.sh
# or
make test-integration
```

with `SMARTMATCH_DATABASE_URL` pointed at the Supabase project for whichever
of these you run. `make seed-pilot`, `make seed-pilot-principals`,
`make seed-pilot-logins`, `make verify-pilot-dataset`, and
`make test-integration` are Makefile targets already in this repository, and
`scripts/compose_smoke.sh` already exists — none of this is new tooling.

## 11. SSL mode

Supabase requires TLS on both the pooler and direct hosts; the connection is
encrypted by default without any extra configuration. Do not pass
`sslmode=disable`. If your driver stack requires an explicit mode, use
`sslmode=require` (verify in the dashboard's connection-string example under
Project Settings → Database, since Supabase's own generated string is the
authoritative source for the exact parameters a given project expects).

## 12. Lock down the Supabase surface

- Do not distribute the project's `anon` or `service_role` API keys to the
  app. The app never uses the Supabase client library or the PostgREST Data
  API — it is a plain Postgres client.
- Do not enable Row Level Security policies expecting PostgREST-mediated
  access; RLS is not part of this integration and authorization stays in
  `smartmatch_authz`.
- The database is reached only via `SMARTMATCH_DATABASE_URL`. No other
  Supabase surface (Storage, Edge Functions, Auth/GoTrue, Realtime) is
  wired to this application, and none should be enabled for this project
  without its own ticket.

## What this does NOT authorize

- **`ALLOW_CLOUD_DEPLOY` stays `false`.** Nothing in this document changes
  it, and standing up this Supabase project is not the gate this flag
  represents.
- **No real student or participant data.** D8 (production data-handling
  gate) is not met. This project is for synthetic, seeded, or fixture data
  only — the same kind of data the pilot VM's `SMARTMATCH_EDITION=dev`
  appliance already uses. If D8 closes and a production database is
  actually needed, that is new work built on top of this document, not a
  quiet reuse of the staging project created here.
- **Not a replacement for the pilot VM's database.** Moving the pilot VM
  onto Supabase is explicitly out of scope for this document (see the
  ticket's Scope section) and is its own follow-up ticket.

See [supabase-maintenance.md](supabase-maintenance.md) for backups, the
restore drill, migrations, credential rotation, and incident response once
the project is standing.
