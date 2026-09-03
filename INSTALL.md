# Installation

From a fresh clone to a green test run, including the **database lane** — the
one most people skip, and the one that proves the most.

For contributor workflow, the gate-by-gate CI mapping, and error-keyed
troubleshooting, see [`CONTRIBUTING.md`](CONTRIBUTING.md). This file is only
about getting the thing installed and verified.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.11 or 3.12** | `pyproject.toml` requires `>=3.11,<3.13` — **3.13 does not work**. CI runs 3.11, and both container images are `python:3.11-slim-bookworm`, so 3.11 is the version everything is actually verified against. |
| **PostgreSQL 16** | Needed for the integration lane and for running the app. Not needed for `make check`. |
| `python3-venv` | A separate package on Debian/Ubuntu. Without it `make setup` fails on its first line with exit code 1. |

```bash
sudo apt install -y python3-venv postgresql-16    # Debian / Ubuntu
```

---

## 1. Dependencies

```bash
make setup
```

Creates `.venv` and installs hash-verified pinned dependencies, then installs
the four workspace packages editable.

**It is slow — do not interrupt it.** Minutes on a native Linux filesystem, and
it can exceed fifteen on a Windows-mounted path under WSL (`/mnt/c/...`). A run
that looks hung is usually still working.

---

## 2. Database

These are the three commands that turn an installed-but-empty PostgreSQL into
one this repository's tests can actually use:

```bash
sudo make db-up          # start PostgreSQL; create the smartmatch role + database
make migrate             # apply migrations to head — creates the schema
make test-integration    # pytest tests/ -m integration — proves the schema works
```

`make db-up` **requires root**: it runs `service postgresql start` and
`su postgres`. It is written for a Debian-style PostgreSQL service, so it fails
on WSL without systemd, on macOS, and anywhere you cannot become `postgres`.
That failure is not fatal — provide the database yourself and skip straight to
`make migrate`:

```sql
CREATE USER smartmatch WITH PASSWORD 'smartmatch' SUPERUSER;
CREATE DATABASE smartmatch OWNER smartmatch;
```

Both the Makefile and the tests default to:

```
postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch
```

Override with `SMARTMATCH_DATABASE_URL` if yours differs.

### Verifying you actually have a database

**The integration tests skip themselves when no database is reachable, and a
skipped test is green.** So "the suite passed" proves nothing about the
integration lane unless you confirm the lane ran. Check the schema directly:

```bash
pg_isready
psql "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" \
  -tAc "select count(*) from information_schema.tables where table_schema='public'"
psql "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" \
  -tAc "select version_num from alembic_version"
```

A migrated database reports a non-zero table count and an `alembic_version`
matching the newest file in `db/migrations/versions/`. If `alembic_version` is
behind that, run `make migrate` again.

Then confirm the lane ran rather than skipped — the summary line must say
`passed`, not `skipped`:

```bash
.venv/bin/pytest tests/ -m integration -q
```

---

## 3. Verify

```bash
make check               # the nine gates that need no infrastructure
make test-integration    # the database lane
```

`make check` runs formatting, lint, strict typing, architecture import
boundaries, the no-database test lane, the forbidden-behavior scan, the
agent-memory ledger check, the dependency-license policy, and the Terraform
environment-isolation check.

**A green `make check` is not a green CI.** `make test` is
`pytest tests/ -m "not integration"` — the no-database lane only. CI also runs
the migration from an empty database, the full suite including integration, the
OpenAPI drift check, dependency-lock recompilation, `pip-audit --strict`,
gitleaks over full history, the tracked-artifact checks, and the container image
build. `make test-all` and `make migrate-check` close part of that gap locally;
the rest needs CI. [`CONTRIBUTING.md`](CONTRIBUTING.md) maps each CI step to its
local counterpart.

---

## 4. Run it

```bash
make run-api        # http://localhost:8000  (fixtures only)
make run-worker     # http://localhost:8001
```

The API runs against fixture providers by default and **cannot** be configured
into a live provider without credentials that do not exist in this repository.

There is also a container stack (`docker-compose.yml`) providing PostgreSQL, a
migration step, a one-shot dev-only seed step, the API, the worker, and a
dev-only scheduler sidecar. Bringing it up is not a deployment — see the file's
own header for what it deliberately does not claim.

```bash
docker compose up --build -d
```

### Smoke-testing the full import path

This is the complete path from an empty stack to one pending review item,
with **no manual dispatch step** — the `scheduler` sidecar drives the import
to completion on its own, the same way Cloud Scheduler would drive the real
deployed worker (see `docs/operations/containers.md`).

**1. Bring the stack up.**

```bash
docker compose up --build -d
```

Wait for it to settle (`docker compose ps` — `api`, `worker`, and `scheduler`
should all be `running`/`healthy`; `migrate` and `seed` should be
`exited (0)`).

**2. Recover the seeded unit's UUID.** `seed` created a `pilot` org unit under
a synthetic `pilot` tenant (`tools/seed_pilot.py`'s own defaults); look it up
directly rather than guessing an id:

```bash
UNIT_ID=$(docker compose exec -T db psql \
  "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" \
  -tAc "select id from org_unit where path = 'pilot'")
echo "$UNIT_ID"
```

**3. Submit one valid inline `professionals` row**, with `dry_run: false` so
it actually queues work. The bearer token below (`compose-api`) is
the local-only dev principal `docker-compose.yml` maps to the seeded
`coordinator` membership — see that file's `SMARTMATCH_DEV_PRINCIPALS`. The
row uses only columns `docs/pilot-data/columns.yaml` ratifies for
`professionals` (`name` and `metro_region` required; the rest optional), so it
validates cleanly rather than producing findings. `Idempotency-Key` must be
unique per attempt — reusing one replays the first response instead of
submitting again.

```bash
curl -s -X POST "http://127.0.0.1:8080/v1/units/$UNIT_ID/imports" \
  -H "Authorization: Bearer compose-api" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: smoke-$(date +%s)" \
  -d '{
        "dataset": "professionals",
        "dry_run": false,
        "rows": [
          {"name": "Ada Lovelace", "metro_region": "Portland"}
        ]
      }'
```

A `202` here means the command was accepted and queued — not that anything
has been imported yet. The `scheduler` sidecar is what moves it the rest of
the way, on its own two-second loop.

**4. Poll `GET /v1/units/$UNIT_ID/metrics` for at most 30 seconds**, watching
for `pending_review_items` to reach `1`:

```bash
for i in $(seq 1 30); do
  value=$(curl -s "http://127.0.0.1:8080/v1/units/$UNIT_ID/metrics" \
    -H "Authorization: Bearer compose-api" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((m["value"] for m in d["metrics"] if m["name"]=="pending_review_items"), "null"))')
  echo "attempt $i: pending_review_items.value = $value"
  [ "$value" = "1" ] && break
  sleep 1
done
```

**5. Assert the result.**

```bash
[ "$value" = "1" ] || { echo "FAILED: expected pending_review_items.value == 1, got $value"; exit 1; }
echo "OK: one row queued through the dev-only scheduler, no manual dispatch"
```

Tear down when finished:

```bash
docker compose down -v
```

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `make setup` fails immediately, exit 1 | `python3-venv` missing. `sudo apt install -y python3-venv`. |
| `make setup` appears hung | Expected on `/mnt/c/...` under WSL. Wait. |
| `su: Authentication failure` / `service: command not found` from `make db-up` | No systemd or no `postgres` account. Create the role and database manually (above), then `make migrate`. |
| Integration tests report `skipped` | No reachable database. Verify with the `psql` checks above. |
| `ModuleNotFoundError: No module named 'sqlalchemy'` | You used the system `python3`. Use `.venv/bin/python` and `.venv/bin/pytest`. |
| `alembic_version` behind the newest migration file | `make migrate`. |

Error-keyed troubleshooting beyond this table is in
[`CONTRIBUTING.md`](CONTRIBUTING.md#troubleshooting).
