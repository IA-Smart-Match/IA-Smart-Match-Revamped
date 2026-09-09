#!/usr/bin/env bash
#
# Rebuild the synthetic pilot dataset from an empty database, on this machine.
#
# WHY A CLEAN REBUILD RATHER THAN A RE-RUN
# ----------------------------------------
# tools/generate_pilot_dataset.py is re-runnable against the database it last
# wrote, but it is NOT re-runnable against a database some *other* run half
# filled. Re-running the generator over a tenant that already carries its
# Phase B rows collides on `uq_professional_unit_relationship` and on the
# ADR-0012 event identity key, because Phase B's writers resolve an existing
# row where Phase A's importers would create a second one. The only honest way
# back to a known state is an empty database, so that is what this script
# builds: drop, recreate, migrate, seed, run, verify.
#
# THE FAILURE THIS SCRIPT EXISTS TO MAKE IMPOSSIBLE
# -------------------------------------------------
# The pilot tenant was found holding 250 professional_unit_relationship rows,
# 60 event rows, 180 pipeline_record rows and 258 attendance_record rows beside
# ZERO job, import_batch, review_item, speaker_profile, match_run,
# cba_invitation and student_speaker_feedback rows. Every full table is written
# by the generator's Phase B, which goes through repositories. Every empty one
# is written by Phase A, which goes through the HTTP API. Phase A needs three
# processes, not one:
#
#   * the API           — accepts POST /v1/units/{id}/imports and answers 202;
#   * the worker        — executes the command the queue delivers;
#   * something driving dispatch — because nothing moves a queued job to the
#     worker on its own. Under `docker compose` that is the `scheduler`
#     sidecar, which POSTs the worker's own /operations/dispatch on a timer.
#     Its target is a hard-coded compose service name
#     (smartmatch_worker.local_scheduler.DISPATCH_URL), so it cannot be pointed
#     at a host-run worker, and this script drives that endpoint itself instead.
#
# A run missing the third process submits imports that sit queued forever, and
# the generator's own report — which describes what the tool believed it did —
# reads almost the same as a healthy one. So this script gates on the database:
# if Phase A produced zero `job` rows, it FAILS LOUDLY. A silent zero is exactly
# how the database reached the state described above.
#
# WHAT IT WILL NOT DO
# -------------------
# It seeds no reward catalog values of its own. Every reward_item field — name,
# points cost, fulfilment cost, budget owner, funded — is owner-supplied by
# design (docs/pilot-data/rewards-catalog-worksheet.md: engineering "must not
# invent owners, funding, or point costs"), so `make seed-pilot-rewards` runs
# only when the operator has put a worksheet row into SEED_PILOT_REWARD_ARGS,
# and the script says plainly when it has not. An empty catalog is a true state.
#
# It also invents no consent. Composing speaker invitations skips a recipient
# who holds no approved, unsuppressed contact channel, and this script seeds no
# such channel: consent origin is exactly the kind of evidence ADR-0011 and the
# G4 consent-origin gate forbid a generator from manufacturing.
#
# USAGE
#   scripts/reset_pilot_dataset.sh
#
# Every knob is an environment variable with a stated default; none is a
# credential of consequence and none reaches a live provider.
#
#   VENV                       path to the virtualenv (default: ./.venv). A git
#                              worktree has none of its own; point this at the
#                              parent checkout's .venv.
#   SEED                       generator seed (default: 42)
#   DATABASE                   database to drop and recreate (default: smartmatch)
#   PGHOST/PGPORT/PGUSER/PGPASSWORD  libpq settings for the drop and recreate
#                              (defaults: localhost/5432/smartmatch/smartmatch)
#   API_PORT / WORKER_PORT     host ports (defaults: 8000 / 8001)
#   COORDINATOR_SUBJECT/EMAIL/TOKEN  the seeded coordinator and its dev bearer
#                              token (defaults: local-pilot-coordinator,
#                              coordinator@example.test, local-dev)
#   SEED_PILOT_REWARD_ARGS     owner-supplied reward worksheet row; unset means
#                              the catalog is left empty on purpose
#   KEEP_RUNNING=1             leave the API and worker up after the run
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="${VENV:-$ROOT/.venv}"
PY="$VENV/bin/python"
SEED="${SEED:-42}"
DATABASE="${DATABASE:-smartmatch}"

export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-smartmatch}"
export PGPASSWORD="${PGPASSWORD:-smartmatch}"

API_PORT="${API_PORT:-8000}"
WORKER_PORT="${WORKER_PORT:-8001}"
API_BASE="http://127.0.0.1:${API_PORT}"
WORKER_BASE="http://127.0.0.1:${WORKER_PORT}"

COORDINATOR_SUBJECT="${COORDINATOR_SUBJECT:-local-pilot-coordinator}"
COORDINATOR_EMAIL="${COORDINATOR_EMAIL:-coordinator@example.test}"
COORDINATOR_TOKEN="${COORDINATOR_TOKEN:-local-dev}"

# The worker's two dev tokens. They MUST differ: smartmatch_worker.config
# refuses to boot when the task-scoped and dispatch-scoped credentials collapse
# into one string, because Cloud Tasks and Cloud Scheduler keep distinct
# audiences and allowlists and a local fixture that blurred them would stop
# emulating the boundary it exists to emulate.
WORKER_TASK_TOKEN="${WORKER_TASK_TOKEN:-local-task}"
WORKER_SCHEDULER_TOKEN="${WORKER_SCHEDULER_TOKEN:-local-sched}"

LOG_DIR="${LOG_DIR:-$ROOT/.pilot-reset-logs}"
DOMAIN_PATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence"
DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${DATABASE}"

API_PID=""
WORKER_PID=""
DISPATCH_PID=""

say() { printf '\n=== %s\n' "$*"; }
die() { printf '\nreset-pilot-dataset: FATAL: %s\n' "$*" >&2; exit 1; }

cleanup() {
  local status=$?
  if [[ "${KEEP_RUNNING:-0}" == "1" && $status -eq 0 ]]; then
    printf '\nreset-pilot-dataset: KEEP_RUNNING=1 — api pid %s, worker pid %s, dispatch pid %s left up.\n' \
      "$API_PID" "$WORKER_PID" "$DISPATCH_PID"
    return
  fi
  for pid in "$DISPATCH_PID" "$WORKER_PID" "$API_PID"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 0. Preflight. Every check here is one this script would otherwise fail on
#    later, further from its cause.
# ---------------------------------------------------------------------------
say "0. preflight"
[[ -x "$PY" ]] || die "no interpreter at $PY. Run 'make setup', or set VENV to a checkout that has one."
command -v psql >/dev/null || die "psql is not on PATH; the drop/recreate below needs it."
pg_isready -q || die "PostgreSQL is not accepting connections at ${PGHOST}:${PGPORT}."
mkdir -p "$LOG_DIR"
echo "interpreter   $PY"
echo "database      $DATABASE_URL"
echo "seed          $SEED"
echo "logs          $LOG_DIR"

# The dev-principal map the API will boot with: the coordinator the generator
# authenticates as, plus one student per member of the feedback cohort. It is
# computed here, before anything starts, because Settings reads the environment
# once at process start — a token added after the API is up authenticates as
# nobody and answers 401.
say "0b. dev principal map"
DEV_PRINCIPALS="$(
  PYTHONPATH="$DOMAIN_PATH:tools" "$PY" - "$COORDINATOR_TOKEN" "$COORDINATOR_SUBJECT" <<'PYEOF'
import json
import sys

from pilot_dataset_plan import feedback_dev_principals

token, subject = sys.argv[1], sys.argv[2]
principals = {token: subject}
principals.update(feedback_dev_principals())
print(json.dumps(principals, sort_keys=True))
PYEOF
)"
echo "$DEV_PRINCIPALS"

# ---------------------------------------------------------------------------
# 1. Drop and recreate. THIS DESTROYS EVERY TENANT IN THIS DATABASE, not only
#    the pilot one — say so before doing it rather than after.
# ---------------------------------------------------------------------------
say "1. drop and recreate database '$DATABASE' (DESTRUCTIVE — every tenant in it)"
psql -d postgres -v ON_ERROR_STOP=1 -qc \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE datname = '$DATABASE' AND pid <> pg_backend_pid();" >/dev/null
psql -d postgres -v ON_ERROR_STOP=1 -qc "DROP DATABASE IF EXISTS \"$DATABASE\";"
psql -d postgres -v ON_ERROR_STOP=1 -qc "CREATE DATABASE \"$DATABASE\" OWNER \"$PGUSER\";"
echo "recreated."

export SMARTMATCH_DATABASE_URL="$DATABASE_URL"
export SMARTMATCH_EDITION=dev
export SMARTMATCH_USE_FIXTURE_PROVIDERS=true

# ---------------------------------------------------------------------------
# 2-5. Migrate and seed, through the Makefile targets that already exist. Each
#      one is reused rather than reimplemented: `seed-pilot-principals` in
#      particular takes no identity arguments on purpose, because its subjects
#      must match a fixed table, and restating them here is exactly the drift
#      that target's own comment refuses.
# ---------------------------------------------------------------------------
say "2. make migrate"
make VENV="$VENV" migrate

say "3. make seed-pilot"
make VENV="$VENV" seed-pilot \
  SEED_PILOT_ARGS="--subject $COORDINATOR_SUBJECT --email $COORDINATOR_EMAIL --role coordinator"

say "4. make seed-pilot-principals"
make VENV="$VENV" seed-pilot-principals

# The four /login credentials come from SMARTMATCH_PILOT_*_EMAIL/_PASSWORD and
# nowhere else. A pair left blank creates nothing and is named on stderr; no
# default password is invented here or there. That is not a failure of this
# rebuild — the dataset does not depend on a browser login — so a non-zero exit
# is reported and stepped over rather than aborting a run that is otherwise fine.
say "5. make seed-pilot-logins"
if ! make VENV="$VENV" seed-pilot-logins; then
  echo "reset-pilot-dataset: NOTE: seed-pilot-logins did not create every login." >&2
  echo "  The SMARTMATCH_PILOT_*_EMAIL/_PASSWORD pairs are owner-supplied; nothing was" >&2
  echo "  defaulted. The dataset below is unaffected — only the browser sign-in is." >&2
fi

# ---------------------------------------------------------------------------
# 6. The three processes Phase A needs.
#
#    uvicorn is invoked directly rather than through `make run-api` /
#    `make run-worker`: those two carry --reload, which is right for a developer
#    editing code and wrong for a script — a reload mid-import restarts the
#    process holding the in-flight request. The PYTHONPATH wiring is copied from
#    those targets so the two cannot disagree about what is importable.
# ---------------------------------------------------------------------------
say "6. start api, worker, and the dispatch driver"

SMARTMATCH_DEV_PRINCIPALS="$DEV_PRINCIPALS" \
PYTHONPATH="$DOMAIN_PATH:services/api" \
  "$VENV/bin/uvicorn" smartmatch_api.main:app --host 127.0.0.1 --port "$API_PORT" \
  >"$LOG_DIR/api.log" 2>&1 &
API_PID=$!

# The worker's loopback task queue (LocalPostgresHttpTaskQueue): the dispatcher
# records a job as durably dispatched in PostgreSQL and this same process then
# POSTs it back to its own /tasks/execute. The target must be loopback, plain
# http, this process's own port and exactly that path — the worker's config
# validator enforces all four and refuses to boot otherwise.
SMARTMATCH_DEV_TASK_BEARER_TOKEN="$WORKER_TASK_TOKEN" \
SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN="$WORKER_SCHEDULER_TOKEN" \
SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED=true \
SMARTMATCH_LOCAL_TASK_TARGET_URL="http://127.0.0.1:${WORKER_PORT}/tasks/execute" \
PYTHONPATH="$DOMAIN_PATH:services/worker" \
  "$VENV/bin/uvicorn" smartmatch_worker.main:app --host 127.0.0.1 --port "$WORKER_PORT" \
  >"$LOG_DIR/worker.log" 2>&1 &
WORKER_PID=$!

wait_healthy() {
  local name="$1" url="$2" pid="$3" attempt
  for attempt in $(seq 1 60); do
    if ! kill -0 "$pid" 2>/dev/null; then
      die "$name exited during startup. Its log is ${LOG_DIR}/${name}.log"
    fi
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      echo "$name healthy on attempt $attempt"
      return 0
    fi
    sleep 2
  done
  die "$name never became healthy at $url. Its log is ${LOG_DIR}/${name}.log"
}

wait_healthy api "${API_BASE}/api/health" "$API_PID"
wait_healthy worker "${WORKER_BASE}/health" "$WORKER_PID"

# The third process. This is what `docker compose`'s `scheduler` sidecar does —
# POST the worker's own /operations/dispatch on a timer — reproduced here
# because that sidecar's destination is a hard-coded compose service name and
# cannot be repointed at a host-run worker. It is emphatically NOT Cloud
# Scheduler and proves nothing about the deployed dispatch path (F5/S-001).
(
  while sleep 2; do
    curl -fsS --max-time 30 -X POST \
      -H "Authorization: Bearer ${WORKER_SCHEDULER_TOKEN}" \
      "${WORKER_BASE}/operations/dispatch" >>"$LOG_DIR/dispatch.log" 2>&1 || true
  done
) &
DISPATCH_PID=$!

# One pass before the generator submits anything, so a dispatch path that is
# misconfigured fails here — where the message is about dispatch — rather than
# ninety seconds later as "the queued import never reached review".
sleep 2
if ! curl -fsS --max-time 30 -X POST \
      -H "Authorization: Bearer ${WORKER_SCHEDULER_TOKEN}" \
      "${WORKER_BASE}/operations/dispatch" >/dev/null 2>&1; then
  die "POST ${WORKER_BASE}/operations/dispatch was refused. 401/403 means the scheduler
token disagrees with the worker's SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN; 501 means the
worker has no task queue configured. Neither is fixed by asking again, and without this
endpoint every import this run submits sits queued forever. Worker log: ${LOG_DIR}/worker.log"
fi
echo "dispatch driver running (pid $DISPATCH_PID)"

# ---------------------------------------------------------------------------
# 7. The generator.
# ---------------------------------------------------------------------------
say "7. tools/generate_pilot_dataset.py --seed $SEED"
PYTHONPATH="$DOMAIN_PATH:services/api:tools" "$PY" tools/generate_pilot_dataset.py \
  --api-base "$API_BASE" \
  --bearer-token "$COORDINATOR_TOKEN" \
  --seed "$SEED" \
  2>&1 | tee "$LOG_DIR/generate.log"
GENERATOR_STATUS="${PIPESTATUS[0]}"

# ---------------------------------------------------------------------------
# 8. THE GATE. Phase A either produced jobs or it did not, and the database is
#    the only witness worth asking. A generator that exited 0 having submitted
#    nothing, and a generator that exited 0 having submitted everything, print
#    reports that look alike; `job` = 0 tells them apart.
# ---------------------------------------------------------------------------
say "8. gate: did Phase A reach the queue at all?"
JOB_ROWS="$(psql -d "$DATABASE" -tAc 'SELECT count(*) FROM job;')"
IMPORT_ROWS="$(psql -d "$DATABASE" -tAc 'SELECT count(*) FROM import_batch;')"
REVIEW_ROWS="$(psql -d "$DATABASE" -tAc 'SELECT count(*) FROM review_item;')"
echo "job=$JOB_ROWS import_batch=$IMPORT_ROWS review_item=$REVIEW_ROWS"

if [[ "$JOB_ROWS" -eq 0 ]]; then
  die "Phase A produced ZERO job rows.

The generator's HTTP half did not land. This is the exact state this script was
written to refuse: Phase B's repository writes would still have filled event,
pipeline_record and attendance_record, so the appliance would look populated
while every review, roster, match-run, invitation and feedback surface stayed
empty. Nothing below this point ran.

  api log       ${LOG_DIR}/api.log
  worker log    ${LOG_DIR}/worker.log
  dispatch log  ${LOG_DIR}/dispatch.log
  generator log ${LOG_DIR}/generate.log"
fi

if [[ "$GENERATOR_STATUS" -ne 0 ]]; then
  die "the generator exited $GENERATOR_STATUS. It reached the queue (job=$JOB_ROWS), so this
is a failure partway through rather than a dead dispatch path. See ${LOG_DIR}/generate.log."
fi

# ---------------------------------------------------------------------------
# 9. Rewards — owner-supplied or not at all.
# ---------------------------------------------------------------------------
say "9. rewards catalog"
if [[ -n "${SEED_PILOT_REWARD_ARGS:-}" ]]; then
  make VENV="$VENV" seed-pilot-rewards SEED_PILOT_REWARD_ARGS="$SEED_PILOT_REWARD_ARGS"
else
  cat <<'EOF'
reset-pilot-dataset: reward catalog left EMPTY, on purpose.

Every reward_item value — display name, points cost, fulfilment cost, budget
owner, funded — is owner-supplied. docs/pilot-data/rewards-catalog-worksheet.md
says engineering "must not invent owners, funding, or point costs", and as of
this run that worksheet's item table has no completed row in it. So this script
supplies none, and no redemption is openable in the resulting demo.

To fill it, complete a worksheet row and re-run with, for example:
  SEED_PILOT_REWARD_ARGS="--name '<row>' --points-cost <n> --fulfilment-cost <n> \
    --budget-owner-id <uuid> --funded" scripts/reset_pilot_dataset.sh

The attendance-derived point balances above are real regardless; the catalog is
not missing by accident.
EOF
fi

# ---------------------------------------------------------------------------
# 10. Verify against the database, not against the report.
# ---------------------------------------------------------------------------
say "10. make verify-pilot-dataset"
set +e
make VENV="$VENV" verify-pilot-dataset
VERIFY_STATUS=$?
set -e

if [[ "$VERIFY_STATUS" -ne 0 ]]; then
  REWARD_ROWS="$(psql -d "$DATABASE" -tAc 'SELECT count(*) FROM reward_item;')"
  if [[ "$REWARD_ROWS" -eq 0 && -z "${SEED_PILOT_REWARD_ARGS:-}" ]]; then
    # The verifier is right and this run is still correct: it refuses any empty
    # table, and reward_item is empty because nobody has approved a catalog row.
    # Distinguished here rather than excused in the verifier, which must keep
    # failing on it for an operator who did supply one and got nothing.
    say "verifier reported reward_item empty; see step 9 — that table is owner-supplied"
  fi
fi

say "done"
echo "seed              $SEED"
echo "database          $DATABASE_URL"
echo "coordinator token $COORDINATOR_TOKEN -> $COORDINATOR_SUBJECT"
echo "logs              $LOG_DIR"
exit "$VERIFY_STATUS"
