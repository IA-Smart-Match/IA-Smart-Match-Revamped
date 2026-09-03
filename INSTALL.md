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

This is the complete path from an empty stack through a coordinator's review
decision and back out to the metric that decision moved:

    import  ->  scheduler dispatch  ->  pending_review_items == 1
            ->  review decision     ->  pending_review_items == 0

with **no manual dispatch step** anywhere in it — the `scheduler` sidecar
drives the import to completion on its own, the same way Cloud Scheduler would
drive the real deployed worker (see `docs/operations/containers.md`). The last
two steps are the ones worth insisting on: an import that reaches review only
proves ingestion, and a decision is only real once the count it is supposed to
change actually changes.

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
[ "$value" = "1" ] || { echo "FAILED: expected pending_review_items.value == 1, got $value"; exit 1; }
echo "OK: one row queued through the dev-only scheduler, no manual dispatch"
```

If this never reaches `1`, check the `scheduler` sidecar **before** blaming the
poll budget — it exits rather than retrying when the worker answers `401`,
`403`, or `501`, so a stopped sidecar is a misconfiguration, not a slow start:

```bash
docker compose ps -a scheduler                      # 'exited' means misconfigured
docker compose logs scheduler | tail -5
```

**5. Recover the pending review item's UUID.** The API exposes no list route
for review items — `POST /v1/review-items/{id}/decision` is the only route in
`smartmatch_api/routers/review.py` — so read the id from the database the same
way step 2 read the unit id:

```bash
REVIEW_ITEM_ID=$(docker compose exec -T db psql \
  "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" -tAc "
  select ri.id
    from review_item ri
    join import_batch ib
      on ib.tenant_id = ri.tenant_id and ib.id = ri.import_batch_id
    join org_unit ou
      on ou.tenant_id = ib.tenant_id and ou.id = ib.owning_unit_id
   where ou.path = 'pilot' and ri.status = 'pending'
   order by ri.row_index
   limit 1")
echo "$REVIEW_ITEM_ID"
```

**6. Accept the row.** `200`, not `202`: a decision starts nothing durable —
it is one conditional `UPDATE` that either lands in this request or does not
(see `routers/review.py`). The response deliberately carries no count; the
count has an owning route, and step 7 reads it from there.

```bash
curl -sf -X POST "http://127.0.0.1:8080/v1/review-items/$REVIEW_ITEM_ID/decision" \
  -H "Authorization: Bearer compose-api" \
  -H "Content-Type: application/json" \
  -d '{"decision": "accepted"}'
```

Expect `{"id":"...","status":"accepted","decided_at":"..."}`. Repeating the
same call answers `409 review_item_already_decided` — a decision may not be
recorded twice.

**7. Confirm the metric moved.** This is the half the smoke path exists for:
a decision that does not change `pending_review_items` has not been recorded
anywhere that matters.

```bash
for i in $(seq 1 30); do
  value=$(curl -s "http://127.0.0.1:8080/v1/units/$UNIT_ID/metrics" \
    -H "Authorization: Bearer compose-api" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((m["value"] for m in d["metrics"] if m["name"]=="pending_review_items"), "null"))')
  echo "attempt $i: pending_review_items.value = $value"
  [ "$value" = "0" ] && break
  sleep 1
done
[ "$value" = "0" ] || { echo "FAILED: expected pending_review_items.value == 0, got $value"; exit 1; }
echo "OK: import -> scheduler dispatch -> review -> decision -> metric"
```

Tear down when finished:

```bash
docker compose down -v
```

### The same path, non-interactively

`scripts/compose_smoke.sh` runs steps 2 through 7 above as one command, with
every assertion made explicit and the relevant `docker compose logs` dumped on
the first failure. It is what the `compose smoke` CI job
(`.github/workflows/build.yml`) runs, so the documented path and the enforced
path are one sequence rather than two that can drift:

```bash
docker compose up --build -d
scripts/compose_smoke.sh
docker compose down -v
```

It deliberately does not bring the stack up or tear it down — CI wants the
containers alive after a failure so it can read their logs, and so does anyone
debugging by hand.

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
| Smoke path never reaches `pending_review_items == 1` | Check `docker compose ps -a scheduler` first. `exited` means the sidecar was refused (`401`/`403`/`501`) and stopped rather than looping — a bearer-token or dispatch misconfiguration, not a slow start. `docker compose logs scheduler` names the status. |
| `409 review_item_already_decided` | That item was already accepted or rejected. Submit a fresh import, or `docker compose down -v` and start clean. |

Error-keyed troubleshooting beyond this table is in
[`CONTRIBUTING.md`](CONTRIBUTING.md#troubleshooting).
