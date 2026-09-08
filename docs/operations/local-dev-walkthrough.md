# Local development walkthrough — CBA pilot appliance

**Audience:** a contributor bringing the CBA pilot up on their own machine for
the first time, to make a change and see it work end to end.

**Posture:** this is the *developer* companion to
[`hosted-synthetic-pilot-guide.md`](hosted-synthetic-pilot-guide.md), which is
written for an operator standing up a demo for a stakeholder over a tunnel.
The two overlap — same appliance, same fixtures — but that guide's path runs
mostly through `docker compose` and fixture bearer tokens; this one runs the
API and worker as host processes (`make run-api` / `make run-worker`) and
signs in through the real `/login` form, because that is the loop a
contributor actually iterates in. Where the two disagree on a detail (a port,
an env var), trust whichever one you are actually following — do not mix
compose ports into a host-run session or vice versa; the [Vite proxy
trap](#7-the-frontend) section below explains why that specifically breaks.

**What this guide has and has not been executed against.** Every command
below is traceable to a line in the `Makefile`, an `argparse` block under
`tools/`, `docker-compose.yml`, `services/api/smartmatch_api/config.py`, or an
existing doc, as of `main` at the time this was written — sources are named
inline. None of it has been *run* on the machine that wrote it: there is no
PostgreSQL here, and WSL itself was not available to execute the sequence
end to end. Treat the shape and the flag names as verified; treat exact
runtime output (row counts aside — see step 6, which is sourced from a
committed ADR, not guessed) as unconfirmed until your own run produces it. If
a step disagrees with what you see, the repository is the tiebreaker, not
this file.

---

## 0. Prerequisites

Run this in **WSL**, not Windows PowerShell. Two independent reasons:

- The `.venv` `make setup` builds is POSIX-layout (`.venv/bin/python`, not
  `.venv\Scripts\python.exe`), and every `Makefile` target invokes it by that
  path.
- `requirements/dev.txt` and `requirements/runtime.txt` both pin
  `uvloop==0.22.1`, which has no Windows wheel and does not build there.

Install Python **3.11** — the version `.python-version` and
`pyproject.toml` (`requires-python = ">=3.11,<3.13"`) pin, and the same major
version both `Dockerfile.api` and `Dockerfile.worker` build on
(`python:3.11-slim-bookworm`). On a machine that also has a newer interpreter
on `PATH`, make sure `python3` resolves to 3.11 before running `make setup` —
WSL/Ubuntu commonly ships `python3` as 3.12+ once updated, and `python`/`py`
on the Windows side is a different interpreter entirely and irrelevant here
regardless of version.

**The trap worth naming up front:** regenerating `contracts/openapi/smartmatch.json`
(`make openapi`) under a 3.13 interpreter rewrites on the order of a hundred
HTTP reason-phrase lines in the committed document (Python's `http.client`
changed how it renders them between 3.11 and 3.13), and `make openapi-check`
— one of the CI gates — then fails on the diff. You should not need to run
`make openapi` in the course of this walkthrough at all; it is called out
here only so that if you ever do, it stays on the pinned interpreter your
`.venv` was built with.

---

## 1. `.env`

```bash
cp .env.example .env
```

`.env.example` documents itself inline; the fields this walkthrough actually
needs filled in are:

- **`SMARTMATCH_EDITION=dev`** — already the default. `SMARTMATCH_USE_FIXTURE_PROVIDERS=true`
  is also already the default; both are asserted at boot (`config.py`), and a
  non-`dev` edition or a `false` here makes the seed tools and the dev
  bearer-token map refuse to run.
- **The four `SMARTMATCH_PILOT_*_EMAIL` / `_PASSWORD` pairs** —
  `COORDINATOR`, `STUDENT`, `ADMIN`, `VOLUNTEER`. These are the real
  `/login` credentials `make seed-pilot-logins` (step 4) creates, and they
  are what you actually sign into the frontend with in this walkthrough —
  not the compose fixture bearer tokens the operator guide uses. Pick
  passwords of at least 12 characters; leaving a pair blank is fine and just
  means that role's login is not created (the seed says so by name). Role
  labels in the UI differ from these env-var names: `VOLUNTEER` is the
  stored role behind the **Event Host** persona, and `COORDINATOR` is the
  stored role behind **Speaker Connector** — see
  `python/smartmatch_domain/smartmatch_domain/role_presentation.py`, the
  single source for that mapping.
- **`SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED`** — the exact field is
  `cba_topic_local_embedding_enabled` in `config.py`, so with the settings
  class's `SMARTMATCH_` prefix the env var is
  `SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED` (no internal space, despite
  how the flag name reads out loud). **This flag is not yet present in
  `.env.example` on `main` as of this writing** — it ships in a separate,
  concurrently-open PR that adds it there alongside the hosted-pilot guide
  update. Add the line yourself if your checkout predates that merge; this
  walkthrough assumes it exists. Off by default (`False`), which keeps
  customer §9's Topic comparison on `FixtureSemanticTopicProvider` — a
  deterministic playback fixture with no recording for most speaker
  expertise text, so most candidates score `cba_semantic_topic: unknown` and
  are reported unscorable. On, it reaches ADR-0017's offline, in-process
  embedding model (averaged GloVe vectors, vendored, no network call, no
  vendor, no credential) — never a live or external provider either way.
  See `docs/architecture/decisions/ADR-0017-offline-embedding-topic-semantics.md`.

`SMARTMATCH_DEV_PRINCIPALS` also lives in `.env.example`, defaulting to `{}`.
You will need to set it later, in step 6, only if you run
`tools/generate_pilot_dataset.py` — it needs a bearer token mapped to the
coordinator subject you seed in step 4, and that map is this variable, not
the login pairs above.

---

## 2. `make setup`

```bash
make setup
```

Creates `.venv`, upgrades `pip`, and installs `requirements/dev.txt` with
`--require-hashes` — a compromised or newly-broken upstream release cannot be
picked up silently. Then installs the four workspace packages
(`python/smartmatch_domain`, `smartmatch_authz`, `smartmatch_providers`,
`smartmatch_persistence`) editable, so local edits to any of them take effect
without a reinstall. Run `make check` afterward if you want confirmation the
toolchain is sound before touching anything — see step 8.

---

## 3. Database

```bash
make db-up
make migrate
```

`db-up` starts a native PostgreSQL service (`service postgresql start`) and,
idempotently, creates the `smartmatch` superuser role and the `smartmatch`
database if they do not already exist — this is the native-Postgres path,
not `docker compose up -d db`; pick one, they both want port 5432. `migrate`
runs `alembic upgrade head` against `SMARTMATCH_DATABASE_URL` (defaulted in
the `Makefile` to `postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch`,
matching `.env.example`'s default), bringing the schema to the tip of
`db/`'s migration chain. Nothing in this walkthrough seeds data until the
next step — an empty, migrated database is the expected state to hand to
`make seed-pilot`.

---

## 4. Seeding: three tools, three jobs

```bash
make seed-pilot SEED_PILOT_ARGS="--subject local-pilot-coordinator --email coordinator@example.test --role coordinator"
make seed-pilot-principals
make seed-pilot-logins
```

They are not interchangeable, and the order above matters:

- **`seed-pilot`** (`tools/seed_pilot.py`) creates *one* synthetic principal
  from arguments you supply — `--subject`, `--email`, and `--role` are all
  `required=True`; `--tenant-slug` (default `pilot`), `--unit-path` (default
  `pilot`), `--unit-type`, and `--unit-name` have defaults. This is also what
  creates the `pilot` tenant and org unit the other two tools, and the
  frontend, resolve by that same default path — run it first.
- **`seed-pilot-principals`** (`tools/seed_pilot_principals.py`) seeds the
  student, Event Host, and admin principals — deliberately taking **no
  identity arguments**. The `Makefile` target's own comment explains why:
  the subjects it writes must match `docker-compose.yml`'s
  `SMARTMATCH_DEV_PRINCIPALS` map exactly (`compose-pilot-student`,
  `compose-pilot-volunteer`, `compose-pilot-admin`), so they live as literals
  in the script rather than as a variable a caller could point somewhere the
  API would then 401. This target is for exactly the situation you are in
  here — a database migrated by hand rather than by the compose `seed`
  one-shot, which runs this same script.
- **`seed-pilot-logins`** (`tools/seed_pilot_logins.py`) is the one that
  reads the `SMARTMATCH_PILOT_*_EMAIL`/`_PASSWORD` pairs from step 1 and
  creates the actual `/login` credentials, one per role that has both halves
  of its pair filled in. A pair left blank is skipped and named on stderr,
  never defaulted. These are what you sign into the Vite frontend with in
  step 7 — a separate mechanism from both `seed-pilot`'s synthetic account
  and the compose bearer-token map.

All three are safe to re-run: `seed-pilot` and the two seed tools built on it
share the pattern of ignoring an already-existing row for a subject that
already matches.

---

## 5. Run the appliance

Two shells:

```bash
make run-api      # PYTHONPATH-wired uvicorn, smartmatch_api.main:app --reload, port 8000
make run-worker   # same, smartmatch_worker.main:app --reload, port 8001
```

Both run "against fixtures, never a live provider" by the `Makefile`'s own
section header — the `--reload` flag means an edit to `services/api` or
`services/worker` (or the workspace packages under `python/`) restarts the
process without you doing it by hand.

---

## 6. `tools/generate_pilot_dataset.py` — a dataset deep enough to measure

```bash
python3 tools/generate_pilot_dataset.py \
  --api-base http://127.0.0.1:8000 \
  --bearer-token <token mapped to local-pilot-coordinator in SMARTMATCH_DEV_PRINCIPALS>
```

`--api-base` and `--bearer-token` are the two `required=True` arguments
(`tools/generate_pilot_dataset.py`'s `parse_args`); everything else —
`--tenant-slug`/`--unit-path` (default `pilot`, matching step 4),
`--seed` (default a fixed literal so runs are reproducible), `--professionals`
(250), `--events` (60), `--students` (120), `--journeys` (180), and the two
readiness/poll-attempt counts — has a default and rarely needs overriding.

The `--bearer-token` is **not** one of the `SMARTMATCH_PILOT_*` login
passwords from step 1 — it is a dev-fixture bearer token the API's
`SMARTMATCH_DEV_PRINCIPALS` JSON map resolves to the coordinator subject you
named in step 4's `seed-pilot` call. If you have not set one, add e.g.
`SMARTMATCH_DEV_PRINCIPALS={"local-dataset-token":"local-pilot-coordinator"}`
to `.env` and restart `make run-api` (it reads `.env` at process start, so a
running instance will not pick up the change).

The tool imports professionals and events through the real `/v1` API, walks
customer §19's classification review on most of them, files a real Speaker
Request, and submits a real match run — then **prints a shortlist report**
rather than a green checkmark, because a successful submission over an empty
shortlist is not a working demo and the tool's whole point is not hiding that.

**The fixture-path baseline**, sourced directly from
`docs/architecture/decisions/ADR-0017-offline-embedding-topic-semantics.md`
(recorded from this same generator, PR #112): of the 100 professionals it
submits as match-run candidates, **5 were scorable, 3 shortlisted, 56 dropped
as `cba_semantic_topic: unknown`, and 39 excluded with an honest §19 reason.**
The 56 unknowns are not missing data — they are professionals *with* real
topic text on file that the fixture playback provider holds no recording for,
which is the exact asymmetry ADR-0017 exists to fix. `tools/generate_pilot_dataset.py`'s
own module docstring explains the arithmetic: with the deliberate unreviewed
fifth and the deliberate unclassified share taken out of a hundred-row pool,
only the professionals carrying *no* expertise text can be scored on the
fixture path, and a hundred yields five.

Running this once with `SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED=false`
(the default) and once with it `true` on the **API process** — restart
`make run-api` with the flag flipped between runs, then re-run the generator
— is a real before/after: the response payload from `POST
/v1/units/{unit_id}/match-runs` carries a `scoring_mode`, and the generator's
own report prints `scored`/`unscorable`/`excluded` counts each time, so the
difference is directly visible rather than asserted. This walkthrough has not
executed that comparison; the off-path numbers above are the only ones
independently confirmed against a committed source.

---

## 7. The frontend

```bash
cd apps/web/legacy-frontend
npm install
npm run dev
```

Create `apps/web/legacy-frontend/.env.local` (gitignored) with:

```
VITE_SMARTMATCH_BEARER_TOKEN=<a dev bearer token, if you want the build-time-configured unit's metrics pages>
VITE_SMARTMATCH_UNIT_ID=<uuid of the pilot org_unit>
```

Get the unit id the same way the operator guide does, against your own
host-run database instead of compose's container:

```bash
psql "$SMARTMATCH_DATABASE_URL" -tAc "select id from org_unit where path = 'pilot'"
```

**Vite bakes every `VITE_*` variable in at process start**, not per-request —
changing `.env.local` requires restarting `npm run dev`, not just reloading
the browser tab.

**The proxy trap:** `vite.config.ts` reads `SMARTMATCH_API_PROXY_TARGET` from
`process.env` at config time and falls back to `http://127.0.0.1:8000` when
it is unset — i.e. `make run-api`, the host-run path this walkthrough uses,
**not** compose's published `:8080`. That means the plain `npm run dev` from
above "just works" against the appliance this guide built. If you instead
bring the backend up with `docker compose up`, you must set
`SMARTMATCH_API_PROXY_TARGET=http://127.0.0.1:8080` before starting Vite (or
edit `vite.config.ts`'s fallback) — the hosted-pilot guide documents that
path and the login story that goes with it (compose's baked fixture bearer
tokens rather than the `/login` credentials from step 1).

Once running, sign in at `http://localhost:5173` with one of the
`SMARTMATCH_PILOT_*_EMAIL`/`_PASSWORD` pairs you filled in and seeded in
steps 1 and 4.

---

## 8. The click-through

With an Event Host login and a Speaker Connector login (two browser
sessions, or two browsers) against the same seeded unit:

1. **Host files a speaker request** — the Event Host portal's request form,
   `POST /v1/units/{unit_id}/speaker-requests`.
2. **Host reads it back on the My Requests page** — `GET
   /v1/units/{unit_id}/host/speaker-requests`, scoped to that host's own
   filings only; a second Event Host account sees a different list.
3. **Connector runs the match** against the filed request — `POST
   /v1/units/{unit_id}/match-runs`, following the job to completion — and
   sees the **shortlist** the run produced.
4. **Connector composes invitations** to shortlisted speakers and
   **dispatches** them.
5. **Host sees the confirmed speaker** once a speaker accepts.
6. **Attendance is recorded** for the event.
7. **The student's balance is credited** from that verified attendance.
8. **A reward is requested and decided** — a student opens a redemption
   against the catalog, a Connector/admin decides it — which only works once
   `make seed-pilot-rewards` (step 9) has put at least one funded item in the
   catalog; it is empty by default.
9. **Connector sees the unit feedback aggregate on the dashboard** —
   `CoordinatorHome.tsx`'s statistics panel, drawn from `GET
   /v1/units/{unit_id}/metrics?surface=cba` and the feedback read, both
   scoped to whatever unit `GET /v1/me/portals` actually granted that
   account — not the frontend's build-time `VITE_SMARTMATCH_UNIT_ID`.

This sequence is verified at the router level — `speaker_requests.py`,
`match_runs.py`, `cba_invitations.py`, `attendance.py`, `rewards.py`, and
`student_speaker_feedback.py` all exist under
`services/api/smartmatch_api/routers/` and the frontend pages named above
exist under `apps/web/legacy-frontend/src/app/pages/` — but this walkthrough
has not clicked through it end to end. If a screen 404s, the legacy frontend
has drifted from the `/v1` contract; OpenAPI wins, per the operator guide.

---

## 9. Rewards: a required, unfillable-by-us catalog

```bash
make seed-pilot-rewards SEED_PILOT_REWARD_ARGS='--name "..." --points-cost 300 \
  --fulfilment-cost 10.00 --budget-owner-subject local-pilot-coordinator --funded'
```

Every one of `--name`, `--points-cost`, `--fulfilment-cost`,
`--budget-owner-subject`, and the mutually-exclusive `--funded`/`--unfunded`
pair is `required=True` in `tools/seed_pilot_rewards.py` — there is no
default for any of them, by design: `docs/pilot-data/rewards-catalog-worksheet.md`
says engineering "must not invent owners, funding, or point costs," so this
tool invents nothing and every value must come from a worksheet row a human
has actually filled in. `--budget-owner-subject` is a
`user_account.external_subject` that already has a seeded login — one of the
subjects from step 4, not a display name.

It is idempotent for an identical repeat (reported as a no-op, not an error)
and refuses a second call for the same `--name` with any different value
rather than silently changing a catalog row.

---

## 10. Running the tests

What you actually reach for day to day — see `CONTRIBUTING.md`'s "The gates"
section for the full gate-by-gate CI mapping; the short version:

```bash
make check            # every target `make check` runs: format-check, lint, typecheck,
                       # imports, test, scan, memory, licenses, infra-check
make test              # pytest tests/ -m "not integration and not e2e" — no database needed
make test-integration  # pytest tests/ -m integration — requires PostgreSQL
make test-all          # pytest tests/ -m "not e2e" — everything that needs no running appliance
```

`make check` is a **subset** of CI, not the whole of it — CI additionally
checks that migrations apply from empty, runs the full test suite with
coverage, verifies the committed OpenAPI document is current, recompiles the
dependency locks and diffs them, and runs a secret scan and a dependency
audit, none of which have a one-line local equivalent. CI is the authority
here: it runs the full matrix on every pull request, and a slow local
`test-all`/`test-integration` run against a laptop database is not a
substitute for it and is usually the wrong thing to reach for when you just
want to know whether your change is green — push and let CI answer that.

---

## See also

- [`hosted-synthetic-pilot-guide.md`](hosted-synthetic-pilot-guide.md) — the
  operator's compose-and-tunnel path, the `.env` inventory against what the
  code actually reads, and the pre-loaded compose principal table.
- [`../../INSTALL.md`](../../INSTALL.md) — the launcher-script path
  (`./smartmatch.sh install` / `.\smartmatch.ps1 install`), which does not
  require this walkthrough's manual toolchain at all.
- [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) — the full CI gate mapping
  and the testing conventions referenced in step 10.
