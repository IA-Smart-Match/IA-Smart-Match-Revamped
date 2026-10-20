# Class exercise load test (Plan A, local)

Proves the class exercise keeps updating **correctly** with a full room: 6 teams × ~17 devices
(V1 = 100 students, V3 = 150). Script: `tools/loadtest/classroom_load.py`. Full design and the
Plan B (cloud clone) / Plan C (live VM) follow-ups: the load-test plan (`loadtest-plan/PLAN.md`,
2026-10-16).

**Local only.** The script refuses `*.smartmatch.cloud`. Plan B and C need the
owner's OK first.

## What one run does

It replays the run of show with real think times (6–20 s between slider moves). `--scale 6`
(default, the plan's 10 s class minute) shortens only the phases; the request rate per student
stays real.

| Phase | What the fake students do | Checked after it |
|---|---|---|
| B1 cold load | Lognormal arrivals (median 6 s, p90 20 s). Each student loads the page assets, enters its team, loads events, list and settings. A page with no list after 8 s is reloaded (max 3) | Instructor lists all 6 teams |
| S1 matching (Northline, E11) | Slider moves (list + settings), keyboard bursts, saves under `tN-A/B/C` plus random names (hits the 3-name cap), compare, CSV, full refreshes | Every student and the instructor detail see only their own team's settings |
| B6 CSV | 60 % of students download the Northline CSV within 90 s ("save both top-30 lists") | latency only |
| B2 refresh | Everyone reloads the page | latency only |
| B3 run Northline | Instructor unlocks E11; all students press Run within 10 s, then load the results page | Per team exactly 1 × 201 and the rest 409 `exercise_results_already_run`; every device sees the same run; instructor shows 1 run |
| B4 asking | All students post an asking choice within 10 s | Per team 1 × 200, the rest 409 `exercise_asking_already_chosen` |
| B5 refresh | Teams 1–3 press refresh and race the instructor's refresh-all (sent in the first second); teams 4–6 rely on refresh-all | Each team refreshed exactly once; all devices agree on choice + refreshed |
| S2 + B3 Harbor (E12) | Matching block, then the round-two run burst | Same as S1 and B3 |
| final | — | Instructor: every team has 2 runs, an asking choice and a refresh |

Background the whole time: the instructor projector (teams page every 15 s, a team detail every 60 s),
a canary (1 req/s `GET /workspaces/current`, shows lock waiters starving the app) and a 1 s
sampler (API / web / load-generator CPU and RSS, host load, DB connections by state,
advisory-lock waiters).

## How to run

1. Postgres on `localhost:5432` with the dev `smartmatch` role (`make db-up`). Use a private DB:

   ```bash
   createdb -h localhost -U smartmatch smartmatch_loadtest_1
   cd db && SMARTMATCH_DATABASE_URL=postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch_loadtest_1 ../.venv/bin/alembic upgrade head
   ```

2. An env file outside the repo, `chmod 600`, with fresh values (never the VM's):

   ```bash
   umask 077; cat > ~/loadtest/.env.loadtest <<EOF
   SMARTMATCH_PRODUCT_SCOPE=class_exercise
   SMARTMATCH_EXERCISE_WORKSPACE_SECRET=$(openssl rand -hex 32)
   SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE=$(openssl rand -hex 16)
   SMARTMATCH_EXERCISE_COOKIE_SECURE=false
   SMARTMATCH_DATABASE_URL=postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch_loadtest_1
   SMARTMATCH_RELEASE=loadtest-$(git rev-parse --short HEAD)
   EOF
   ```

   `COOKIE_SECURE=false` is required on plain http: the client drops Secure cookies and every
   call after team entry would be a 401.

3. Seed Ann's fictional 300 and start the API exactly like the container (one process, no
   `--workers`). Add `SMARTMATCH_DB_POOL_SIZE` / `_MAX_OVERFLOW` here to copy the VM's values:

   ```bash
   set -a; . ~/loadtest/.env.loadtest; set +a
   export PYTHONPATH=python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence:services/api
   .venv/bin/python -m smartmatch_api.exercise_seed
   nohup .venv/bin/uvicorn smartmatch_api.main:app --host 127.0.0.1 --port 8191 > ~/loadtest/api.log 2>&1 &
   ```

4. Frontends (from `apps/web/legacy-frontend`, node_modules installed). Both proxy `/v1` to the API:

   ```bash
   export SMARTMATCH_API_PROXY_TARGET=http://127.0.0.1:8191 VITE_SMARTMATCH_BEARER_TOKEN=
   npx vite build --outDir ~/loadtest/dist
   nohup npx vite preview --outDir ~/loadtest/dist --host 127.0.0.1 --port 4174 --strictPort > ~/loadtest/web-built.log 2>&1 &
   nohup npx vite --host 127.0.0.1 --port 5274 --strictPort > ~/loadtest/web-dev.log 2>&1 &
   ```

5. Run (the passcode is read from the environment and never printed):

   ```bash
   export LOADTEST_INSTRUCTOR_PASSCODE=$SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE
   .venv/bin/python tools/loadtest/classroom_load.py --base http://127.0.0.1:4174 \
     --students 100 --out runs/v1-100-built --label v1-100-built \
     --api-pid <uvicorn pid> --web-pid <vite node pid> \
     --pg-dsn postgresql://smartmatch:smartmatch@localhost:5432/smartmatch_loadtest_1
   ```

   - `--base http://127.0.0.1:5274` = Vite dev server (what the VM serves today); `:4174` = built
     bundle; `:8191` = API only (no proxy, no assets).
   - `--students 150` for V3. A run takes about 10 minutes at the default `--scale 6`;
     `--scale 1` is the real-time soak (about 35 minutes).
   - The run resets teams 1–6 and locks E11/E12 at start and end (`--keep-state` to inspect).
     Guards: the host must be `127.0.0.1`/`localhost`, and `/api/health` must report a
     `loadtest-*` release (the env file above sets it), so a typo cannot reset a real class.
   - Exit code 0 = every check and target passed.

## How to read the results

Each run folder has `report.md` (read this), `summary.json`, `requests.csv` (one row per
request) and `samples.csv` (one row per second).

1. **Correctness first.** `report.md` → "Correctness: N/M checks pass". Any FAIL in B3/B4/B5 is a
   class-stopping bug (a team with two runs, a lost asking choice, a double refresh). Stop and file it.
2. **Targets** (plan §4.2, at 100 students): API read p95 ≤ 1.5 s, write p95 ≤ 2 s, any p99 ≤ 4 s,
   page load to first list p95 ≤ 5 s, unexpected errors < 1 %, no 5xx, 0 errors in B3.
3. **Endpoints table**: slowest p95 per phase. Status mix shows expected refusals
   (`409:exercise_results_already_run` etc.); the `unexpected` column counts the rest.
4. **Resource peaks per phase**: `api_cpu` near 100 = the single uvicorn process is the ceiling
   (one GIL); `db_advisory_waiters` > 0 = students queued on a class-wide lock;
   `db_total` near the pool size (default 20 + 10) = pool queueing; `loadgen_cpu` near 100 or
   `host_load1` above the core count = the numbers are inflated by the test box itself, re-run on
   a quiet machine.

Plan A numbers are for **relative** comparisons (dev vs built, 100 vs 150, before vs after a fix).
The January sizing call needs Plan B on e2-medium hardware.

## Re-run after Tracks A–C merge

1. `git fetch && git worktree add ~/worktrees/loadtest-rerun origin/main --detach`.
2. New private DB, `alembic upgrade head`, seed, restart uvicorn and both frontends from that
   tree (steps 1–4). Rebuild the bundle: `npx vite build` again.
3. Run V1 and V3 against built and dev with the same `--seed` (default `20261019`).
4. Compare `summary.json` → `verdicts` and `burst_peaks` with the previous run folder.
5. If an API route or code string changed (for example the results-run refusal codes), update
   the expected codes in `classroom_load.py`; the check prints the code it got.

Checks added for the Oct 23 tree (#419, #423, #425): after B1 every team's list has
`invite_limit` 60 and 60 entries, and a Harbor run press is refused 409
`exercise_round_two_locked`; in B4 (Harbor unlocked, no refresh yet) a Harbor run press is
refused 409 `exercise_ask_first`; after B5 every device reads `asked_without_card` 230.

## Profiling a run (py-spy)

Start the API under py-spy instead of plain uvicorn (no sudo needed: py-spy is the parent):

```bash
python3 -m venv ~/loadtest/pyspy/v && ~/loadtest/pyspy/v/bin/pip install py-spy
date +%s.%N > prof.json.t0
~/loadtest/pyspy/v/bin/py-spy record -r 50 --gil -f chrometrace -o prof.json -- \
  .venv/bin/python -m uvicorn smartmatch_api.main:app --host 127.0.0.1 --port 8191
```

Stop it with `kill -INT <py-spy pid>` after the run so it writes the trace, then cut it by the
script's phase lines (`[  12.3s] phase X` in the run log). The Oct 19 profile and its slicer are
in `sweep-recovery/oct23/perf/profile.md`. For a clean before/after of one route, time
sequential requests against two APIs on one DB rather than comparing two loaded runs: on a
shared box host load swings whole-run p95s by 40 % between identical trees.

**Load-generator check (Oct 19).** httpcore runs `import sniffio` on every request; with the
venv on `/mnt/c` each miss cost ~19 ms of `stat` calls and capped one generator at ~25 req/s,
so run 1's latencies were mostly the generator. The script now pre-empties that import
(1.6 ms per request). Before trusting any run, check: a sequential `GET /api/health` loop
from the generator's Python should take under 5 ms per request.

## Running against the VM (after a deploy; owner-gated)

The VM run belongs to the orchestrator/owner, after the deploy, **outside class time**. It
writes to the live class database: it resets teams 1–6 and locks E11/E12 at start and end,
and in between it saves settings, runs results, asks and refreshes for teams 1–6. Owner OK
first (standing rule: anything that writes on the VM is a gate). Never point it at
`exercise.smartmatch.cloud` — the script refuses it, and a run
through Cloudflare is Plan C, a separate gate.

The VM sets its cookies `Secure`, which httpx will not send over plain http. The tool
handles this for loopback tunnels (`http://127.0.0.1:<port>`, `localhost`, `::1`) only; it
never relaxes other hosts. Use the IAP/SSH tunnel with `--allow-any-release` as documented.

1. **Before.** On the VM (read-only): note the deployed SHA, which dataset is active (must be
   Ann's 300; invite limit 60), and the unlock state of E11/E12 from the instructor page.
   Confirm no team has work you need to keep: the run resets teams 1–6.
2. **Env on the VM**: keep the pool at its default (20 + 10; leave
   `SMARTMATCH_EXERCISE_DB_POOL_*` empty) and **one** uvicorn process. Measured Oct 19 at 150
   students: with #428 the pool never ran out (0 `QueuePool` timeouts; 418 without it, all in
   the Harbor run burst). More workers add nothing on 2 shared vCPUs that Postgres, the CBA
   stack and Node also use, and the instructor-login limiter is per process.
3. **Tunnel from the dev box** (generator off the VM, so it does not steal the server's CPU):

   ```bash
   gcloud compute ssh smartmatch --zone us-west2-c --tunnel-through-iap -- \
     -N -L 15174:127.0.0.1:5174 -L 18090:127.0.0.1:8090
   ```

   `15174` = web-exercise (built bundle + `/v1` proxy), `18090` = api-exercise direct. Check
   the ports in `docker-compose.exercise.yml` on the deployed SHA first. Both are `127.0.0.1`
   locally, which the host guard accepts.
4. **Run** (passcode typed, never echoed; the VM release is not `loadtest-*`):

   ```bash
   read -rs LOADTEST_INSTRUCTOR_PASSCODE; export LOADTEST_INSTRUCTOR_PASSCODE
   .venv/bin/python tools/loadtest/classroom_load.py --base http://127.0.0.1:15174 \
     --students 100 --out runs/vm-v1-100 --label vm-v1-100 --allow-any-release
   ```

   No `--api-pid`/`--web-pid`/`--pg-dsn`: sample the VM in a second IAP SSH session instead
   (`vmstat 5`, `docker stats --no-stream` every 5 s, `free -m`) and save it beside the run.
   Then V3 (`--students 150`). One run at a time.
5. **Read it** as above, with two caveats: the IAP tunnel adds round-trip time and its own
   throughput ceiling, so cold-load numbers are pessimistic; and e2-medium CPU steal shows
   in `vmstat`'s `st` column, not in the run report.
6. **After.** The script resets teams 1–6 and locks E11/E12. Re-open whatever step 1 found
   open, and record SHA, env and results next to the local runs
   (`sweep-recovery/oct23/loadtest-run2/report.md` has the local baseline to compare).

## Next steps that need the owner

- **Plan B** (cloud clone of the VM disk, no internet egress, e2-medium): gates B1–B4 in the plan,
  ≈ $5–8. Needed for absolute numbers.
- **Plan C** (live hostname through Cloudflare, off-hours): gates C1–C7. Only if B leaves a
  Cloudflare question.
- Not covered here: Playwright "felt" timings and the Vite HMR reload storm (plan H11).
