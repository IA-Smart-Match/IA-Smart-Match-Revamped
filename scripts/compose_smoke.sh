#!/usr/bin/env bash
#
# End-to-end smoke path for the docker compose appliance (docker-compose.yml).
#
# It proves ONE sentence, in order, against the running stack:
#
#   import -> scheduler dispatch -> pending_review_items 0->1 -> accept -> 1->0
#   -> events import -> accept -> pipeline_matched 0->1, opportunities 0->1,
#   provenance stored
#
# ...with no manual dispatch step anywhere in it. The compose `scheduler`
# sidecar is what drives the queued import to completion; if it does not, this
# script fails rather than papering over it with a longer wait.
#
# The second half (stages 9-15) is P8's own acceptance criterion (plan
# `docs/plans/2026-09-03-pipeline-synthetic-caller-plan.md`, Decision 8): a
# `pipeline_funnel_rows_v1` metric that has been a permanent measured zero
# since `pipeline_record` was added, because nothing in production ever
# called `PipelineRepository`, actually becomes `1` — from inside the running
# compose appliance, through the same review-accept route stages 1-8 already
# exercised, not from an in-process test. §1.10 governs stage 13 in
# particular: a `2xx` from the accept in stage 12 is not itself evidence —
# the positive count polled afterward is.
#
# This is the same sequence INSTALL.md documents command by command. It is not
# a deployment, publishes no image, pushes to no registry, and reaches nothing
# outside this compose network — see docker-compose.yml's header.
#
# All HTTP calls below go to `api`/`worker` on their published loopback ports
# (`docker-compose.yml` publishes both — only `db`'s port collides with a
# native PostgreSQL on this kind of host), and every direct database read
# uses `psql_scalar`, which runs `psql` **inside** the `db` container via
# `docker compose exec` rather than against any host-published port — `db`
# publishes none that a native PostgreSQL on 5432 has not already claimed.
# Stages 9-15 hold to that exactly as stages 1-8 already did.
#
# Usage:
#
#   docker compose up --build -d
#   scripts/compose_smoke.sh
#   docker compose down -v        # teardown is the caller's, not this script's
#
# This script deliberately does NOT bring the stack up or tear it down. CI owns
# `up` and an always-run `down -v` so logs survive a failure, and a developer
# running it by hand wants the stack still standing to look at.
#
# Exit codes: 0 = the whole path held. 1 = a stage failed; the failing stage is
# named on stderr and the relevant `docker compose logs` are dumped.
#
# Rules this file holds itself to:
#   * No `|| true`, and no swallowed exit code on any assertion. The only
#     tolerated failure anywhere is a connection refusal *inside a readiness
#     poll*, which is the condition being polled for, and every such loop still
#     ends in a hard check that exits 1.
#   * No bare `sleep` standing in for readiness. Every wait is a bounded poll
#     of the actual condition, and reports what it saw on each attempt.

set -Eeuo pipefail

# --- Local-only identities, matching docker-compose.yml exactly ---------------
# These are the compose file's own literals (its x-compose-dev-identity
# anchors). They authenticate nothing outside that network and are not secrets;
# see docker-compose.yml's header note on why they are short, plain strings.
API_BASE="${API_BASE:-http://127.0.0.1:8080}"
WORKER_BASE="${WORKER_BASE:-http://127.0.0.1:8081}"
API_BEARER="${API_BEARER:-compose-api}"
UNIT_PATH="${UNIT_PATH:-pilot}"
DB_URL="postgresql://smartmatch:smartmatch@localhost:5432/smartmatch"

# Bounded poll budgets, in attempts. Each attempt prints what it observed.
READY_ATTEMPTS="${READY_ATTEMPTS:-60}"     # x2s — image start + migrate + seed
SCHEDULER_ATTEMPTS="${SCHEDULER_ATTEMPTS:-15}"  # x2s — one accepted pass
METRIC_ATTEMPTS="${METRIC_ATTEMPTS:-30}"   # x1s — the scheduler's 2s loop

log() { printf '%s\n' "$*"; }

fail() {
  # Named stage, then the logs that explain it. `::error::` is a GitHub Actions
  # annotation and is harmless noise in a local terminal.
  printf '::error::compose smoke failed: %s\n' "$*" >&2
  docker compose ps || true
  docker compose logs --no-color --tail=200 api worker scheduler seed migrate || true
  exit 1
}

# `docker compose logs` in the failure path is best-effort diagnostics only —
# it runs after the verdict is already "failed" and cannot change it. Every
# assertion above uses no such tolerance.

require_json_number() {
  # Reads stdin, prints the named metric's value, or the literal string `null`
  # when the metric is absent or its value is unknown. Never invents a 0:
  # unknown is not zero (see smartmatch_api/routers/metrics.py).
  python3 -c '
import json, sys
name = sys.argv[1]
doc = json.load(sys.stdin)
print(next((m["value"] for m in doc["metrics"] if m["name"] == name), "null"))
' "$1"
}

metric_value() {
  # $1 = unit id, $2 = metric name. A transport failure here is a real failure:
  # the API is already known-healthy by the time this is called.
  curl -sf "${API_BASE}/v1/units/${1}/metrics" \
    -H "Authorization: Bearer ${API_BEARER}" | require_json_number "$2"
}

psql_scalar() {
  docker compose exec -T db psql "$DB_URL" -tAc "$1" | tr -d '[:space:]'
}

# =============================================================================
# Stage 1 — readiness. A real poll of both health endpoints, not a sleep.
# =============================================================================
log "== stage 1: api + worker readiness =="
api_code=000
worker_code=000
for attempt in $(seq 1 "$READY_ATTEMPTS"); do
  # A connection refusal is the condition being polled for, so a non-zero curl
  # here is data, not an error — hence the explicit default rather than a
  # blanket `|| true`. The hard check after the loop is what decides.
  if ! api_code="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE}/api/health")"; then
    api_code=000
  fi
  if ! worker_code="$(curl -s -o /dev/null -w '%{http_code}' "${WORKER_BASE}/health")"; then
    worker_code=000
  fi
  log "  attempt ${attempt}: api=${api_code} worker=${worker_code}"
  if [ "$api_code" = "200" ] && [ "$worker_code" = "200" ]; then
    break
  fi
  sleep 2
done
[ "$api_code" = "200" ] && [ "$worker_code" = "200" ] \
  || fail "api or worker never reported healthy (api=${api_code} worker=${worker_code})"

# =============================================================================
# Stage 2 — scheduler misconfiguration guard. THIS IS THE LOUD ONE.
#
# The sidecar exits 1 on 401/403/501 from POST /operations/dispatch — a token
# that drifted from the worker's SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN, or a
# worker with no dispatch configured (smartmatch_worker/local_scheduler.py's
# _FATAL_STATUSES). Without this stage that failure would surface later as a
# timeout on stage 5, which reads like "slow" rather than "misconfigured".
#
# Two independent assertions: the container is still running, AND it logged at
# least one accepted pass. Either alone can pass while the path is broken —
# a sidecar that has not yet been refused is still "running", and a stale log
# line could outlive a container that has since exited.
# =============================================================================
log "== stage 2: scheduler sidecar is running and dispatching =="
accepted=""
scheduler_state=""
for attempt in $(seq 1 "$SCHEDULER_ATTEMPTS"); do
  # `-a`: a container that has already exited is absent from a bare
  # `compose ps`, and "absent" is exactly the state this stage must name out
  # loud rather than report as an empty string.
  scheduler_state="$(docker compose ps -a --format '{{.State}}' scheduler)"
  [ -n "$scheduler_state" ] || scheduler_state="absent"
  if [ "$scheduler_state" != "running" ]; then
    fail "scheduler sidecar is '${scheduler_state}', not running. It exits rather \
than looping against a worker that will never accept it (401/403/501), so this \
is a scheduler/worker bearer-token or dispatch misconfiguration — check that \
SMARTMATCH_LOCAL_SCHEDULER_BEARER_TOKEN and the worker's \
SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN still resolve to the same compose anchor, \
and that the worker's SMARTMATCH_EDITION is dev. This is not a slow start."
  fi
  # awk, not `grep -c`, because grep exits 1 on zero matches and zero matches is
  # the expected state on the first attempt — this counts, it does not assert.
  accepted="$(docker compose logs --no-color scheduler \
    | awk '/dispatch pass accepted/ {n++} END {print n+0}')"
  log "  attempt ${attempt}: state=${scheduler_state} accepted_passes=${accepted}"
  if [ "${accepted:-0}" -ge 1 ]; then
    break
  fi
  sleep 2
done
[ "${accepted:-0}" -ge 1 ] \
  || fail "scheduler sidecar never logged an accepted dispatch pass; the worker \
is not answering POST /operations/dispatch 2xx for it"

# =============================================================================
# Stage 3 — the seeded unit. Looked up, never guessed.
# =============================================================================
log "== stage 3: recover the seeded '${UNIT_PATH}' unit =="
unit_id="$(psql_scalar "select id from org_unit where path = '${UNIT_PATH}'")"
[ -n "$unit_id" ] || fail "seed did not produce a '${UNIT_PATH}' org unit"
log "  unit_id=${unit_id}"

# Baseline, so stage 5's "== 1" is a measured change and not an accident of a
# stack that was already carrying a pending item from an earlier run.
baseline="$(metric_value "$unit_id" pending_review_items)"
log "  baseline pending_review_items=${baseline}"
[ "$baseline" = "0" ] \
  || fail "expected a clean stack (pending_review_items == 0), got ${baseline}; \
run 'docker compose down -v' first"

# Baseline for stage 13 too. Without this, a stack that already held one
# pipeline_record row from an earlier interrupted run would satisfy stage
# 13's "== 1" on attempt 1 even if stage 12's accept provisioned nothing —
# a silent zero reported as a pass, exactly the failure class §1.10 forbids.
# This makes stage 13 a measured *change* (0 -> 1), not merely a state check.
pipeline_matched_baseline="$(metric_value "$unit_id" pipeline_matched)"
log "  baseline pipeline_matched=${pipeline_matched_baseline}"
[ "$pipeline_matched_baseline" = "0" ] \
  || fail "expected a clean stack (pipeline_matched == 0), got ${pipeline_matched_baseline}; \
run 'docker compose down -v' first"

# =============================================================================
# Stage 4 — import. One inline professionals row, dry_run:false.
# =============================================================================
log "== stage 4: submit one inline professionals row =="
import_code="$(curl -s -o /dev/null -w '%{http_code}' \
  -X POST "${API_BASE}/v1/units/${unit_id}/imports" \
  -H "Authorization: Bearer ${API_BEARER}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${SMOKE_IDEMPOTENCY_KEY:-smoke-$(date +%s)-$$}" \
  -d '{
        "dataset": "professionals",
        "dry_run": false,
        "rows": [
          {"name": "Ada Lovelace", "metro_region": "Portland"}
        ]
      }')"
log "  POST /imports -> ${import_code}"
[ "$import_code" = "202" ] || fail "import was not accepted (expected 202, got ${import_code})"

# =============================================================================
# Stage 5 — scheduler-driven dispatch lands the row in review.
# There is deliberately no dispatch curl anywhere in this file.
# =============================================================================
log "== stage 5: poll for pending_review_items == 1 (no manual dispatch) =="
value=null
for attempt in $(seq 1 "$METRIC_ATTEMPTS"); do
  value="$(metric_value "$unit_id" pending_review_items)"
  log "  attempt ${attempt}: pending_review_items=${value}"
  [ "$value" = "1" ] && break
  sleep 1
done
[ "$value" = "1" ] \
  || fail "expected pending_review_items == 1 after scheduler-driven dispatch, got ${value}"

# =============================================================================
# Stage 6 — the review item itself. There is no list route for review items
# (services/api/smartmatch_api/routers/review.py exposes only the decision
# endpoint), so the id is read from the database the same way the unit id is.
# =============================================================================
log "== stage 6: recover the pending review item =="
review_item_id="$(psql_scalar "
  select ri.id
    from review_item ri
    join import_batch ib
      on ib.tenant_id = ri.tenant_id and ib.id = ri.import_batch_id
    join org_unit ou
      on ou.tenant_id = ib.tenant_id and ou.id = ib.owning_unit_id
   where ou.path = '${UNIT_PATH}' and ri.status = 'pending'
   order by ri.row_index
   limit 1")"
[ -n "$review_item_id" ] \
  || fail "pending_review_items reported 1 but no pending review_item row joins to unit '${UNIT_PATH}'"
log "  review_item_id=${review_item_id}"

# =============================================================================
# Stage 7 — the decision. 200, not 202: it starts nothing durable.
# =============================================================================
log "== stage 7: accept the review item =="
decision_body="$(curl -sf -X POST "${API_BASE}/v1/review-items/${review_item_id}/decision" \
  -H "Authorization: Bearer ${API_BEARER}" \
  -H "Content-Type: application/json" \
  -d '{"decision": "accepted"}')" \
  || fail "POST /v1/review-items/${review_item_id}/decision did not return 2xx"
log "  response: ${decision_body}"
decided_status="$(printf '%s' "$decision_body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
[ "$decided_status" = "accepted" ] \
  || fail "decision response reported status '${decided_status}', expected 'accepted'"

# =============================================================================
# Stage 8 — the metric reflects the decision. This is the whole point: the
# count is read back from its owning route (ADR-0011 rule 4), not recomputed.
# =============================================================================
log "== stage 8: poll for pending_review_items == 0 (metrics reflect the decision) =="
value=null
for attempt in $(seq 1 "$METRIC_ATTEMPTS"); do
  value="$(metric_value "$unit_id" pending_review_items)"
  log "  attempt ${attempt}: pending_review_items=${value}"
  [ "$value" = "0" ] && break
  sleep 1
done
[ "$value" = "0" ] \
  || fail "expected pending_review_items == 0 after the accept decision, got ${value}"

# =============================================================================
# Stage 9 — import one inline events row. The professionals row accepted in
# stage 7 is what makes this row's own accept (stage 12) find exactly one
# linked professional and open exactly one journey — see this file's own
# note below stage 15 on why these stages must not be reordered.
# =============================================================================
log "== stage 9: submit one inline events row =="
events_import_code="$(curl -s -o /dev/null -w '%{http_code}' \
  -X POST "${API_BASE}/v1/units/${unit_id}/imports" \
  -H "Authorization: Bearer ${API_BEARER}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${SMOKE_EVENTS_IDEMPOTENCY_KEY:-smoke-events-$(date +%s)-$$}" \
  -d '{
        "dataset": "events",
        "dry_run": false,
        "rows": [
          {"Event / Program": "Portland Hackathon", "Category": "hackathon"}
        ]
      }')"
log "  POST /imports -> ${events_import_code}"
[ "$events_import_code" = "202" ] \
  || fail "events import was not accepted (expected 202, got ${events_import_code})"

# =============================================================================
# Stage 10 — scheduler-driven dispatch lands the events row in review too.
# =============================================================================
log "== stage 10: poll for pending_review_items == 1 (events row, no manual dispatch) =="
value=null
for attempt in $(seq 1 "$METRIC_ATTEMPTS"); do
  value="$(metric_value "$unit_id" pending_review_items)"
  log "  attempt ${attempt}: pending_review_items=${value}"
  [ "$value" = "1" ] && break
  sleep 1
done
[ "$value" = "1" ] \
  || fail "expected pending_review_items == 1 after the events row's scheduler-driven dispatch, got ${value}"

# =============================================================================
# Stage 11 — recover the new pending review item id. Same join stage 6 uses,
# narrowed to the events batch so a stack carrying more than one pending item
# cannot pick up the wrong one.
# =============================================================================
log "== stage 11: recover the pending events review item =="
events_review_item_id="$(psql_scalar "
  select ri.id
    from review_item ri
    join import_batch ib
      on ib.tenant_id = ri.tenant_id and ib.id = ri.import_batch_id
    join org_unit ou
      on ou.tenant_id = ib.tenant_id and ou.id = ib.owning_unit_id
   where ou.path = '${UNIT_PATH}' and ri.status = 'pending' and ib.dataset = 'events'
   order by ri.row_index
   limit 1")"
[ -n "$events_review_item_id" ] \
  || fail "pending_review_items reported 1 but no pending events review_item row joins to unit '${UNIT_PATH}'"
log "  events_review_item_id=${events_review_item_id}"

# Pre-accept baseline for stage 15, in stage 15's own shape: both counts
# must be 0 before this accept, or a pre-existing synthetic (or, worse,
# non-synthetic) pipeline_record row would let stage 15 pass without this
# accept having provisioned anything — the same delta-not-state concern the
# pipeline_matched baseline above addresses at the metrics layer, restated
# here at the database layer stage 15 itself reads from.
provenance_baseline_synthetic="$(psql_scalar \
  "select count(*) from pipeline_record where matched_provenance = 'synthetic / coordinator-accepted'")"
provenance_baseline_non_synthetic="$(psql_scalar \
  "select count(*) from pipeline_record where matched_provenance <> 'synthetic / coordinator-accepted'")"
log "  baseline provenance rows: synthetic=${provenance_baseline_synthetic} non-synthetic=${provenance_baseline_non_synthetic}"
[ "$provenance_baseline_synthetic" = "0" ] && [ "$provenance_baseline_non_synthetic" = "0" ] \
  || fail "expected a clean stack (0 pipeline_record rows of either provenance) before the \
events accept, got synthetic=${provenance_baseline_synthetic} non-synthetic=${provenance_baseline_non_synthetic}; \
run 'docker compose down -v' first"

# =============================================================================
# Stage 12 — accept it. A 2xx here is not the acceptance criterion (§1.10) —
# stage 13's positive count is.
# =============================================================================
log "== stage 12: accept the events review item =="
events_decision_body="$(curl -sf -X POST "${API_BASE}/v1/review-items/${events_review_item_id}/decision" \
  -H "Authorization: Bearer ${API_BEARER}" \
  -H "Content-Type: application/json" \
  -d '{"decision": "accepted"}')" \
  || fail "POST /v1/review-items/${events_review_item_id}/decision did not return 2xx"
log "  response: ${events_decision_body}"
events_decided_status="$(printf '%s' "$events_decision_body" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')" \
  || fail "events decision response was not JSON with a status field: ${events_decision_body}"
[ "$events_decided_status" = "accepted" ] \
  || fail "events decision response reported status '${events_decided_status}', expected 'accepted'"

# =============================================================================
# Stage 13 — poll pipeline_matched to 1. THIS IS THE ACCEPTANCE CRITERION: a
# metric that was a permanent measured zero (nothing in production ever
# called PipelineRepository) is now non-zero, from a path that ran entirely
# inside the compose appliance. §1.10: the 2xx stage 12 already got is not
# sufficient evidence on its own — this positive count is the assertion.
# =============================================================================
log "== stage 13: poll for pipeline_matched == 1 (the acceptance criterion) =="
value=null
for attempt in $(seq 1 "$METRIC_ATTEMPTS"); do
  value="$(metric_value "$unit_id" pipeline_matched)"
  log "  attempt ${attempt}: pipeline_matched=${value}"
  [ "$value" = "1" ] && break
  sleep 1
done
[ "$value" = "1" ] \
  || fail "expected pipeline_matched == 1 after accepting an in-list events row, got ${value}"

# =============================================================================
# Stage 14 — opportunities == 1, from the same metrics route. The funnel and
# the opportunity count both move from the same accept.
# =============================================================================
log "== stage 14: assert opportunities == 1 (same metrics route) =="
opportunities_value="$(metric_value "$unit_id" opportunities)"
log "  opportunities=${opportunities_value}"
[ "$opportunities_value" = "1" ] \
  || fail "expected opportunities == 1 after accepting an in-list events row, got ${opportunities_value}"

# =============================================================================
# Stage 15 — the stored provenance. A row that reached the database without
# saying it is synthetic fails the smoke path — this is the database-level
# half of the same claim stage 13 makes at the metrics layer.
# =============================================================================
log "== stage 15: assert the stored provenance =="
synthetic_provenance_count="$(psql_scalar \
  "select count(*) from pipeline_record where matched_provenance = 'synthetic / coordinator-accepted'")"
non_synthetic_provenance_count="$(psql_scalar \
  "select count(*) from pipeline_record where matched_provenance <> 'synthetic / coordinator-accepted'")"
log "  synthetic provenance rows=${synthetic_provenance_count} non-synthetic provenance rows=${non_synthetic_provenance_count}"
[ "$synthetic_provenance_count" = "1" ] \
  || fail "expected 1 pipeline_record row with matched_provenance = 'synthetic / coordinator-accepted', got ${synthetic_provenance_count}"
[ "$non_synthetic_provenance_count" = "0" ] \
  || fail "expected 0 pipeline_record rows with a non-synthetic matched_provenance, got ${non_synthetic_provenance_count}"

# Note for anyone editing this file: stage 4's professionals import and
# stage 7's accept are what create the user_account and the unit link that
# stage 12's accept finds — reordering stages 9-15 ahead of stages 4-8 is the
# silent-zero case stage 13's own §1.10 warning exists to surface, and this
# script's whole point is exercising the working order, not a reordered one.

log ""
log "OK: import -> scheduler dispatch -> pending_review_items 0->1 -> accept -> 1->0"
log "    -> events import -> accept -> pipeline_matched 0->1, opportunities 0->1,"
log "    provenance stored"
log "    (no manual dispatch step, no registry, nothing outside the compose network)"
