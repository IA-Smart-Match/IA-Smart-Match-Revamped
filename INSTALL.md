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
migration step, two one-shot dev-only seed steps, the API, the worker, a
dev-only scheduler sidecar, and the legacy Vite frontend. Bringing it up is not
a deployment — see the file's own header for what it deliberately does not
claim.

```bash
docker compose up --build -d
```

---

## The stakeholder click-through

One command, one browser tab, and one thing to click. This is the section to
follow if the goal is to *show* the pilot rather than to develop against it;
everything below it is the same path expressed as curl, plus the developer
detail.

**1. Start the appliance.**

```bash
docker compose up --build -d
```

The first run builds two images and installs the frontend's dependencies, so
give it several minutes. It is finished when `docker compose ps` shows this:

| Service | Expected state | Published on |
|---|---|---|
| `db` | `running (healthy)` | `127.0.0.1:5432` — see the port-collision note below |
| `migrate` | `exited (0)` | — |
| `seed` | `exited (0)` | — |
| `api` | `running (healthy)` | `127.0.0.1:8080` |
| `worker` | `running (healthy)` | `127.0.0.1:8081` |
| `scheduler` | `running` | — (outbound only) |
| `seed-review` | `exited (0)` | — |
| `web` | `running (healthy)` | `127.0.0.1:5173` |

`web` stays `starting` while `npm ci` runs on a first start — that is the long
step, and `docker compose logs -f web` shows it happening. A `seed-review` that
is `exited (1)` rather than `exited (0)` means the demo import never reached
review; `docker compose logs seed-review` names the stage it stopped at, and
that is a real failure of the import path, not a cosmetic one.

**2. Open the coordinator portal.**

<http://127.0.0.1:5173/coordinator-portal>

There is **no login screen and no sign-in step**, and this is deliberate:
institutional sign-in (A1b) is not connected, and nothing here pretends
otherwise. The `web` container is built with the same local-only fixture
bearer token the curl steps below send, so the browser presents a credential
and the *server* decides who that is. The shell calls `GET /v1/me` before it
renders and shows what the server answered — the seeded email
`compose-pilot-coordinator@example.invalid` and the server-assigned
`coordinator` role on the `pilot` unit. Nothing on that screen is chosen in
the browser.

**3. Find the review queue.** The `seed-review` one-shot has already put two
synthetic professionals — *Grace Hopper* and *Katherine Johnson*, both
`metro_region: Portland` — into the queue. It did not write them into the
database directly: it submitted an ordinary import through the API and waited
for the worker and scheduler to turn it into review items, which is why their
presence is evidence that the import path works rather than decoration.

**4. Accept one, and watch a metric move.** The metric is the point; a decision
that changes no count has not been recorded anywhere that matters. Read it
before and after:

```bash
UNIT_ID=$(docker compose exec -T db psql \
  "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" \
  -tAc "select id from org_unit where path = 'pilot'")

curl -s "http://127.0.0.1:8080/v1/units/$UNIT_ID/metrics" \
  -H "Authorization: Bearer compose-api" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(m["value"] for m in d["metrics"] if m["name"]=="pending_review_items"))'
```

`2` before the decision, `1` after it. Step 6 of the smoke path below is the
same decision as a curl, if the portal's own control is not reachable.

**Two things this walkthrough does not show, stated rather than glossed:**

- **Portal page content.** The pages fetch `/api/portals/*`, a legacy backend
  this repository does not contain and this stack does not run, so each page
  renders its own load-failure state under the signed-in chrome. Identity, the
  route guard, and the sign-out path are what the browser exercises here; the
  data path's proof is the curl sequence below and
  `scripts/compose_smoke.sh`.
- **Sign-in.** There is none. See step 2.

**A port collision worth knowing about.** This stack publishes `5432`, and so
does a native `apt install postgresql-16`. If `docker compose ps db` shows
`5432/tcp` with **no** `127.0.0.1:5432->` prefix, a native PostgreSQL already
holds the port and host-side `psql` reaches *that* database, not this one. Use
`docker compose exec -T db psql` — as every command in this file does — or
stop the native service first.

Tear down when finished; `-v` discards both the database volume and the
frontend's installed dependencies, so the next start really is clean:

```bash
docker compose down -v
```

---

### Smoke-testing the full import path

This is the complete path from a freshly started stack through a
coordinator's review decision and back out to the metric that decision moved.
"Freshly started" is not "empty": `seed-review` has already queued two rows,
so the counts below start at `2` and this path's own row makes `3`.

    import  ->  scheduler dispatch  ->  pending_review_items == 3
            ->  review decision     ->  pending_review_items == 2

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

Wait for it to settle (`docker compose ps` — `api`, `worker`, `scheduler`, and
`web` should all be `running`/`healthy`; `migrate`, `seed`, and `seed-review`
should be `exited (0)`). The state table in "The stakeholder click-through"
above lists every service and its published port.

Note that a settled stack is **not** an empty one: `seed-review` has already
put two pending review items on the `pilot` unit, so `pending_review_items`
reads `2` before step 3 imports anything. The counts in steps 4, 7, 9 and 12
below are stated as that baseline plus or minus this path's own row, which is
exactly how `scripts/compose_smoke.sh` asserts them.

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
for `pending_review_items` to reach `3` — the two rows `seed-review` already
queued, plus this one:

```bash
for i in $(seq 1 30); do
  value=$(curl -s "http://127.0.0.1:8080/v1/units/$UNIT_ID/metrics" \
    -H "Authorization: Bearer compose-api" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((m["value"] for m in d["metrics"] if m["name"]=="pending_review_items"), "null"))')
  echo "attempt $i: pending_review_items.value = $value"
  [ "$value" = "3" ] && break
  sleep 1
done
[ "$value" = "3" ] || { echo "FAILED: expected pending_review_items.value == 3, got $value"; exit 1; }
echo "OK: one more row queued through the dev-only scheduler, no manual dispatch"
```

If this never reaches `3`, check the `scheduler` sidecar **before** blaming the
poll budget — it exits rather than retrying when the worker answers `401`,
`403`, or `501`, so a stopped sidecar is a misconfiguration, not a slow start:

```bash
docker compose ps -a scheduler                      # 'exited' means misconfigured
docker compose logs scheduler | tail -5
```

**5. Recover the pending review item's UUID.** The API exposes no list route
for review items — `POST /v1/review-items/{id}/decision` is the only route in
`smartmatch_api/routers/review.py` — so read the id from the database the same
way step 2 read the unit id. The query is narrowed to this path's own row by
name, because the queue also holds the two rows `seed-review` put there and
accepting one of those instead would move the same metric for a different
reason:

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
     and ib.dataset = 'professionals'
     and ri.row_data->>'name' = 'Ada Lovelace'
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
  [ "$value" = "2" ] && break
  sleep 1
done
[ "$value" = "2" ] || { echo "FAILED: expected pending_review_items.value == 2, got $value"; exit 1; }
echo "OK: import -> scheduler dispatch -> review -> decision -> metric"
```

**8. Submit one inline `events` row.** `pending_review_items` is not the only
metric a coordinator's accept can move. This row uses the columns
`docs/pilot-data/columns.yaml` ratifies for `events` (`Event / Program` and
`Category` required) with an in-list category, so it queues the same way the
professionals row in step 3 did.

```bash
curl -s -X POST "http://127.0.0.1:8080/v1/units/$UNIT_ID/imports" \
  -H "Authorization: Bearer compose-api" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: smoke-events-$(date +%s)" \
  -d '{
        "dataset": "events",
        "dry_run": false,
        "rows": [
          {"Event / Program": "Portland Hackathon", "Category": "hackathon"}
        ]
      }'
```

**9. Poll for `pending_review_items` to reach `3` again**, exactly as step 4
did.

**10. Recover the new review item's UUID**, narrowing step 5's query to the
`events` batch. Note the key: the import pipeline normalizes the ratified
header `Event / Program` into `event_program` before it stores the row, so
that — not the header — is what `row_data` is keyed by:

```bash
EVENTS_REVIEW_ITEM_ID=$(docker compose exec -T db psql \
  "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" -tAc "
  select ri.id
    from review_item ri
    join import_batch ib
      on ib.tenant_id = ri.tenant_id and ib.id = ri.import_batch_id
    join org_unit ou
      on ou.tenant_id = ib.tenant_id and ou.id = ib.owning_unit_id
   where ou.path = 'pilot' and ri.status = 'pending' and ib.dataset = 'events'
     and ri.row_data->>'event_program' = 'Portland Hackathon'
   order by ri.row_index
   limit 1")
echo "$EVENTS_REVIEW_ITEM_ID"
```

**11. Accept it**, exactly as step 6 did:

```bash
curl -sf -X POST "http://127.0.0.1:8080/v1/review-items/$EVENTS_REVIEW_ITEM_ID/decision" \
  -H "Authorization: Bearer compose-api" \
  -H "Content-Type: application/json" \
  -d '{"decision": "accepted"}'
```

**12. Confirm `pipeline_matched` moved from `0` to `1`.** This is the smoke
path's other half, and the reason this branch exists: `pipeline_record` has
never had a production caller before this branch, so `pipeline_matched` has
been a permanent measured zero for every unit this appliance has ever seeded.
A `2xx` from step 11 is not evidence of that on its own (§1.10 of the plan
this branch implements) — the positive count polled below is.

```bash
for i in $(seq 1 30); do
  value=$(curl -s "http://127.0.0.1:8080/v1/units/$UNIT_ID/metrics" \
    -H "Authorization: Bearer compose-api" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((m["value"] for m in d["metrics"] if m["name"]=="pipeline_matched"), "null"))')
  echo "attempt $i: pipeline_matched.value = $value"
  [ "$value" = "1" ] && break
  sleep 1
done
[ "$value" = "1" ] || { echo "FAILED: expected pipeline_matched.value == 1, got $value"; exit 1; }
echo "OK: pipeline_matched moved 0 -> 1"
```

**13. Confirm `opportunities` also moved, from the same metrics route:**

```bash
curl -s "http://127.0.0.1:8080/v1/units/$UNIT_ID/metrics" \
  -H "Authorization: Bearer compose-api" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(m["value"] for m in d["metrics"] if m["name"]=="opportunities"))'
```

Expect `1`.

**14. Confirm the stored row says it is synthetic**, read directly from the
table rather than through any route — this is the database-level half of the
same claim step 12 makes at the metrics layer:

```bash
docker compose exec -T db psql \
  "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" -tAc \
  "select matched_provenance from pipeline_record"
```

Expect exactly one row, reading `synthetic / coordinator-accepted`.

**What `pipeline_matched` becoming `1` proves, and what it does not.** It
proves that a coordinator accepted a synthetic, in-list `events` row for a
synthetic professional inside this compose appliance, through the same
authenticated route a real coordinator uses, and that the row it produced
records itself in the database as synthetic rather than merely claiming so
in a log line. It proves nothing about matching quality: there is no score,
confidence, or ranking anywhere in this path (plan §1.3), and it says
nothing about the separate matching engine landing on `pilot/match-engine-m2-m7`
(`PR #12`), which this branch does not import from, depend on, or reference.

For a demo that wants funnel *depth* — a coordinator's accept only ever opens
a journey at Matched — `tools/seed_demo_pipeline.py` is the optional
follow-on: a dev-only operator tool that walks already-open journeys toward
Contacted, Confirmed, Attended, and Member Inquiry. It is **not** part of
either shipped container image (its own module docstring says so), so it is
invoked from the host, against the compose stack's published database port,
the same way `tools/seed_pilot.py` already is. It exits non-zero if it finds
nothing to advance, so a demo run that silently did nothing is never
mistaken for one that worked:

```bash
SMARTMATCH_EDITION=dev \
SMARTMATCH_USE_FIXTURE_PROVIDERS=true \
SMARTMATCH_DATABASE_URL="postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch" \
.venv/bin/python tools/seed_demo_pipeline.py \
  --tenant-slug pilot --unit-path pilot --through attended --limit 2
```

`localhost:5432` above is the same port a native PostgreSQL install (§2)
would also bind — on a host running both, the native instance can silently
shadow the compose appliance's `db` with no error to say so, and the command
above would then seed the wrong database. Check `docker compose ps db`
first: a `5432/tcp` entry with **no** `127.0.0.1:5432->` prefix means the
port is shadowed, and you cannot reach the appliance from the host at all —
use the same `docker compose exec -T db psql` this file's steps 10/14 and
`scripts/compose_smoke.sh`'s own `psql_scalar` helper already use instead of
the host-side invocation above.

Tear down when finished:

```bash
docker compose down -v
```

### The same path, non-interactively

`scripts/compose_smoke.sh` runs steps 2 through 14 above as one command, with
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

### Clicking through the portals as the compose principal

The stack now runs the legacy frontend itself, as the `web` service, published
on <http://127.0.0.1:5173>. Nothing needs to be installed or started on the
host — `docker compose up --build -d` is the whole command, and the two
environment variables that used to be typed by hand are set in
`docker-compose.yml`:

- `SMARTMATCH_API_PROXY_TARGET=http://api:8080` forwards the dev server's
  `/api` and `/v1` to the compose API by service name. It is read at config
  time and is never bundled.
- `VITE_SMARTMATCH_BEARER_TOKEN=compose-api` is the local-only dev token
  `docker-compose.yml` maps to the seeded subject `compose-pilot-coordinator`
  — the same `Authorization: Bearer compose-api` the curl steps above use. It
  is a credential, not an identity: the browser sends it and the server
  decides who that is. Being a build-time variable, it *is* in the bundle the
  browser runs, which is exactly why it is a short compose-only string that
  authenticates nothing outside this network.

`npm ci` used to fail here on a Windows-mounted path under WSL (DrvFs), which
is why this was a host step for so long. The `web-node-modules` volume is what
resolves it: npm writes into a Docker volume on the VM's own filesystem rather
than onto `/mnt/c`. The first start therefore takes minutes and every later
start does not.

Then open <http://127.0.0.1:5173/coordinator-portal>. The shell calls
`GET /v1/me` before it renders anything and shows what the server answered —
the seeded email `compose-pilot-coordinator@example.invalid` and the
server-assigned `coordinator` membership on the `pilot` unit. Nothing on that
screen is chosen in the browser.

To run the dev server on the host instead — for frontend work, where the
container's install cycle is in the way — the old sequence still works and is
unchanged:

```bash
cd apps/web/legacy-frontend
npm ci
SMARTMATCH_API_PROXY_TARGET=http://127.0.0.1:8080 \
VITE_SMARTMATCH_BEARER_TOKEN=compose-api \
npm run dev
```

Stop the `web` container first (`docker compose stop web`), or the host dev
server cannot bind 5173.

Two things are worth checking deliberately, because they are what Fix #7
closed:

1. **Start the dev server without `VITE_SMARTMATCH_BEARER_TOKEN`.** Every
   portal URL — `/student-portal`, `/coordinator-portal`,
   `/volunteer-portal`, `/dashboard` — redirects to `/login`, which states
   that institutional sign-in is not connected yet (A1b). There is no
   fallback identity to fall into, because there is no longer one to fall
   back to. Against the container, that means removing the variable from the
   `web` service and running `docker compose up -d --force-recreate web`; the
   host sequence above is the quicker way to see it.
2. **Sign out from the portal.** It clears the browser-held token and
   re-asks `GET /v1/me`. A bundle started with `VITE_SMARTMATCH_BEARER_TOKEN`
   carries its token in the bundle, so the server answers again and the
   portal stays open — sign-out cannot revoke a build-time fixture, and the
   UI does not pretend it can. Stop the dev server to end that session.

What compose does **not** demonstrate is portal *content*: the pages fetch
`/api/portals/*`, a legacy backend this repository does not contain and the
stack does not run, so each page shows its own load-failure state under the
signed-in chrome. Identity, the route guard, and the sign-out path are what
this walkthrough exercises; `scripts/compose_smoke.sh` above is the proof for
the data path. Its stage 16 asserts exactly the three things the browser can
be held to here — the dev server serves, the documented portal route answers
`200` rather than `404`, and `GET /v1/me` through the proxy resolves to the
seeded coordinator — and asserts nothing about page content, for the same
reason.

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
| Smoke path never reaches the expected `pending_review_items` count | Check `docker compose ps -a scheduler` first. `exited` means the sidecar was refused (`401`/`403`/`501`) and stopped rather than looping — a bearer-token or dispatch misconfiguration, not a slow start. `docker compose logs scheduler` names the status. |
| `409 review_item_already_decided` | That item was already accepted or rejected. Submit a fresh import, or `docker compose down -v` and start clean. |
| `docker compose ps -a seed-review` shows `exited (1)` | The demo import never reached review. `docker compose logs seed-review` names the stage it stopped at — most often the `scheduler` sidecar was refused, so check that next. The review queue really is empty; nothing back-filled it to hide the failure. |
| `web` stays `starting` for minutes on a first `up` | Expected: `npm ci` is installing into the empty `web-node-modules` volume. `docker compose logs -f web` shows progress. Later starts reuse the volume and are fast. |
| `web` is `unhealthy`, or 5173 refuses connections | Read `docker compose logs web`. An `npm ci` that failed on a registry error is the common cause — `docker compose up -d --force-recreate web` retries it. A host process already on 5173 (an earlier `npm run dev`) is the other. |
| Portal pages render an error panel under signed-in chrome | Expected, and not a compose fault: they fetch `/api/portals/*`, a legacy backend this repository does not contain. Identity and routing work; page content has no server here. |
| The portal shows no login screen | Also expected. Institutional sign-in (A1b) is not connected; the browser carries a build-time fixture bearer token and the server decides the identity. Nothing here is a sign-in. |

Error-keyed troubleshooting beyond this table is in
[`CONTRIBUTING.md`](CONTRIBUTING.md#troubleshooting).
