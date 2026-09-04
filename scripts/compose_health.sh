#!/usr/bin/env bash
#
# Bounded health suite for the docker compose appliance (docker-compose.yml).
#
# It answers one question — "is this stack actually serving?" — and it answers
# it with a nonzero exit when the answer is no. Nothing here mutates the
# appliance: every check is a read (`docker compose ps`, a `select` through
# `psql`, an HTTP GET). The mutating end-to-end path is
# `scripts/compose_smoke.sh`, which `smartmatch.sh verify --full` runs; this
# script is what `smartmatch.sh health` runs, and what the VM deployment script
# runs before and after a release.
#
# ---------------------------------------------------------------------------
# The eleven checks, and why each one is here
# ---------------------------------------------------------------------------
#
#   db-healthy             PostgreSQL's own healthcheck passes. Everything
#                          below is meaningless if it does not.
#   migrations-at-head     alembic_version equals the head computed from
#                          db/migrations/versions/. A stack serving an
#                          out-of-date schema answers 200 and is still wrong,
#                          and after a deployment this is the check that says
#                          the migration step actually ran.
#   migrate-exited-ok      The one-shot migration service exited 0. Distinct
#                          from the check above: at-head with a failed migrate
#                          means someone migrated by hand.
#   seed-exited-ok         The one-shot pilot principal seed exited 0. Without
#                          it the API has no principal to authenticate.
#   seed-review-exited-ok  The one-shot demo review queue seed exited 0. It
#                          drives a real import through dispatch, so its exit
#                          code is a statement about the pipeline, not the data.
#   api-health             GET /api/health is 200, status=ok, and the release
#                          is the one this checkout expects. The release match
#                          is what makes "the deploy landed" observable.
#   worker-health          GET /health on the worker is 200 and status=ok.
#   scheduler-heartbeat    The worker reports a completed dispatch pass, recent
#                          enough to mean the scheduler sidecar is still
#                          driving it. A worker that is up but never dispatched
#                          is a queue that silently never drains.
#   frontend-root          GET / on the Vite dev server is 200.
#   frontend-spa-route     GET /coordinator-portal is 200 — the deep-route
#                          fallback, which is what a stakeholder's bookmark
#                          hits and what a plain / check cannot see.
#   frontend-api-proxy     GET /v1/me through the frontend is 2xx and names
#                          the seeded principal. This is the only check that
#                          exercises browser -> frontend -> API as one path.
#
# ---------------------------------------------------------------------------
# `smartmatch.ps1` implements this same list natively
# ---------------------------------------------------------------------------
# Windows without WSL has Docker Desktop and PowerShell but no bash, so the
# PowerShell launcher cannot delegate here and reimplements each check. The
# two are held together by `tests/unit/test_launcher_parity.py`, which parses
# the check identifiers out of both files and fails if the sets differ — so a
# check added to one and forgotten in the other is a red build, not a
# platform-specific blind spot.
#
# Usage:
#   scripts/compose_health.sh                 one bounded pass, human output
#   scripts/compose_health.sh --wait          retry until the timeout expires
#   scripts/compose_health.sh --json          machine-readable result
#   scripts/compose_health.sh --timeout 900   change the --wait budget
#
# Exit codes: 0 every check passed, 1 at least one failed, 2 usage error.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

API_BASE="${SMARTMATCH_API_BASE:-http://127.0.0.1:8080}"
WORKER_BASE="${SMARTMATCH_WORKER_BASE:-http://127.0.0.1:8081}"
WEB_BASE="${SMARTMATCH_WEB_BASE:-http://127.0.0.1:5173}"

# The compose file's own x-compose-dev-identity literal, the same one
# scripts/compose_smoke.sh and tests/e2e/conftest.py carry. It authenticates
# nothing outside the compose network.
API_BEARER="${SMARTMATCH_API_BEARER:-compose-api}"
PILOT_EMAIL="${SMARTMATCH_PILOT_SUBJECT_EMAIL:-compose-pilot-coordinator@example.invalid}"

# The release the API must report. Resolved exactly the way compose itself
# resolves ${SMARTMATCH_RELEASE} — the shell environment first, then ./.env,
# then docker-compose.yml's own `compose-dev` default — because any other order
# makes this check disagree with the value compose actually passed to the
# container and turns a correct stack red. The VM deployment exports the
# deployed git SHA, which is what makes a half-applied deployment (new
# checkout, old containers still running) a failure rather than a green stack.
resolve_expected_release() {
  if [ -n "${SMARTMATCH_RELEASE:-}" ]; then
    printf '%s' "$SMARTMATCH_RELEASE"
    return
  fi
  if [ -f "${REPO_ROOT}/.env" ]; then
    local from_env_file
    from_env_file="$(sed -nE 's/^[[:space:]]*SMARTMATCH_RELEASE[[:space:]]*=[[:space:]]*"?([^"#]*)"?.*/\1/p' \
      "${REPO_ROOT}/.env" | tail -n1 | sed -E 's/[[:space:]]+$//')"
    if [ -n "$from_env_file" ]; then
      printf '%s' "$from_env_file"
      return
    fi
  fi
  printf '%s' 'compose-dev'
}
EXPECTED_RELEASE="$(resolve_expected_release)"

# How stale a completed dispatch pass may be before the scheduler counts as
# stopped. The compose scheduler loops every 2s; 300s is generous enough that a
# slow machine never trips it and tight enough that a dead sidecar always does.
HEARTBEAT_MAX_AGE_SECONDS="${SMARTMATCH_HEARTBEAT_MAX_AGE_SECONDS:-300}"

CURL_TIMEOUT="${SMARTMATCH_CURL_TIMEOUT:-10}"

WAIT=0
JSON=0
TIMEOUT="${SMARTMATCH_HEALTH_TIMEOUT:-600}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --wait) WAIT=1 ;;
    --json) JSON=1 ;;
    --timeout)
      shift
      [ "$#" -gt 0 ] || { echo "--timeout needs a value" >&2; exit 2; }
      TIMEOUT="$1"
      ;;
    --timeout=*) TIMEOUT="${1#--timeout=}" ;;
    -h|--help) sed -n '1,60p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$TIMEOUT" in
  ''|*[!0-9]*) echo "--timeout must be a whole number of seconds" >&2; exit 2 ;;
esac

cd "$REPO_ROOT" || exit 2

# --- check plumbing ---------------------------------------------------------
#
# CHECK_IDS is the contract. tests/unit/test_launcher_parity.py reads this array
# and the PowerShell launcher's own list and requires them to match, so this is
# the one place a check is named.

CHECK_IDS=(
  db-healthy
  migrations-at-head
  migrate-exited-ok
  seed-exited-ok
  seed-review-exited-ok
  api-health
  worker-health
  scheduler-heartbeat
  frontend-root
  frontend-spa-route
  frontend-api-proxy
)

declare -A CHECK_STATUS=()
declare -A CHECK_DETAIL=()

pass() { CHECK_STATUS["$1"]=pass; CHECK_DETAIL["$1"]="$2"; }
fail() { CHECK_STATUS["$1"]=fail; CHECK_DETAIL["$1"]="$2"; }

compose_field() {
  # $1 service, $2 Go template field. Empty when the service was never created.
  docker compose ps -a --format "{{.$2}}" "$1" 2>/dev/null | head -n1 | tr -d '\r'
}

psql_scalar() {
  docker compose exec -T db \
    psql "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" \
    -tAc "$1" 2>/dev/null | tr -d '[:space:]'
}

http_status() {
  curl -s -o /dev/null -m "$CURL_TIMEOUT" -w '%{http_code}' "$@" 2>/dev/null || echo 000
}

# One request, both facts. Sets HTTP_CODE and HTTP_BODY, because two separate
# curls against a starting service can disagree with each other and produce a
# check that reports a status code from one response and a body from another.
HTTP_CODE=000
HTTP_BODY=""
http_get() {
  local raw
  raw="$(curl -s -m "$CURL_TIMEOUT" -w $'\n%{http_code}' "$@" 2>/dev/null)" || raw=$'\n000'
  HTTP_CODE="${raw##*$'\n'}"
  HTTP_BODY="${raw%$'\n'*}"
  [ -n "$HTTP_CODE" ] || HTTP_CODE=000
}

expected_migration_head() {
  # The revision no other revision names as its down_revision. The migration
  # files declare both at column zero, which is what makes this greppable
  # without importing alembic — this script must work on a machine that has
  # Docker and nothing else.
  local dir="${REPO_ROOT}/db/migrations/versions"
  [ -d "$dir" ] || return 1
  local revisions downs
  revisions="$(grep -hE '^revision = "' "$dir"/*.py 2>/dev/null | sed -E 's/^revision = "([^"]+)".*/\1/' | sort)"
  downs="$(grep -hE '^down_revision = "' "$dir"/*.py 2>/dev/null | sed -E 's/^down_revision = "([^"]+)".*/\1/' | sort)"
  [ -n "$revisions" ] || return 1
  comm -23 <(printf '%s\n' "$revisions") <(printf '%s\n' "$downs")
}

json_field() {
  # $1 JSON document, $2 dotted path. Uses python3 when present (every Ubuntu
  # image here has it) and a deliberately narrow grep otherwise, so a machine
  # without python3 degrades to a weaker check rather than a false pass.
  local doc="$1" path="$2"
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$doc" | python3 -c '
import json, sys
doc = json.load(sys.stdin)
for part in sys.argv[1].split("."):
    if doc is None:
        break
    doc = doc.get(part) if isinstance(doc, dict) else None
print("" if doc is None else doc)
' "$path" 2>/dev/null
    return
  fi
  printf '%s' "$doc" | sed -E 's/.*"'"${path##*.}"'"[[:space:]]*:[[:space:]]*"?([^",}]*)"?.*/\1/'
}

# --- the checks -------------------------------------------------------------

check_db_healthy() {
  local health state
  health="$(compose_field db Health)"
  state="$(compose_field db State)"
  if [ "$health" = "healthy" ]; then
    pass db-healthy "postgres container reports healthy"
  else
    fail db-healthy "postgres container state='${state:-absent}' health='${health:-none}'"
  fi
}

check_migrations_at_head() {
  local head actual
  head="$(expected_migration_head)"
  if [ -z "$head" ] || [ "$(printf '%s\n' "$head" | wc -l)" -ne 1 ]; then
    fail migrations-at-head "could not resolve a single migration head from db/migrations/versions/"
    return
  fi
  actual="$(psql_scalar 'select version_num from alembic_version')"
  if [ "$actual" = "$head" ]; then
    pass migrations-at-head "alembic_version=${actual}"
  else
    fail migrations-at-head "alembic_version='${actual:-unreadable}' but head is '${head}'"
  fi
}

check_one_shot_exited_ok() {
  # $1 check id, $2 compose service name.
  local id="$1" service="$2" state code
  state="$(compose_field "$service" State)"
  code="$(compose_field "$service" ExitCode)"
  if [ "$state" = "exited" ] && [ "$code" = "0" ]; then
    pass "$id" "${service} exited 0"
  else
    fail "$id" "${service} state='${state:-absent}' exit=${code:-unknown} (\`docker compose logs ${service}\` names the stage)"
  fi
}

check_api_health() {
  local body status release
  http_get "${API_BASE}/api/health"
  body="$HTTP_BODY"
  if [ "$HTTP_CODE" != "200" ]; then
    fail api-health "GET ${API_BASE}/api/health -> ${HTTP_CODE}"
    return
  fi
  status="$(json_field "$body" status)"
  release="$(json_field "$body" release)"
  if [ "$status" != "ok" ]; then
    fail api-health "api reported status='${status}' (body: ${body})"
  elif [ "$release" != "$EXPECTED_RELEASE" ]; then
    fail api-health "api reports release='${release}' but this checkout expects '${EXPECTED_RELEASE}' — the containers are older than the code"
  else
    pass api-health "200 status=ok release=${release}"
  fi
}

check_worker_health() {
  local body status
  http_get "${WORKER_BASE}/health"
  body="$HTTP_BODY"
  if [ "$HTTP_CODE" != "200" ]; then
    fail worker-health "GET ${WORKER_BASE}/health -> ${HTTP_CODE}"
    return
  fi
  status="$(json_field "$body" status)"
  if [ "$status" = "ok" ]; then
    pass worker-health "200 status=ok"
  else
    fail worker-health "worker reported status='${status}' (body: ${body})"
  fi
}

check_scheduler_heartbeat() {
  # GET /operations/dispatch is the worker's own heartbeat: what THIS process
  # last completed. In compose the sidecar drives that same process, so a
  # populated, recent last_completed is exactly "the scheduler is still
  # dispatching". It is not the production absence alert — see
  # docs/operations/deploy-runbook.md §J8, which is evaluated on the log line.
  local body configured finished age
  http_get "${WORKER_BASE}/operations/dispatch"
  body="$HTTP_BODY"
  if [ "$HTTP_CODE" != "200" ]; then
    fail scheduler-heartbeat "GET ${WORKER_BASE}/operations/dispatch -> ${HTTP_CODE}"
    return
  fi
  configured="$(json_field "$body" configured)"
  if [ "$configured" != "True" ] && [ "$configured" != "true" ]; then
    fail scheduler-heartbeat "the worker reports configured=${configured:-unknown}: it cannot dispatch at all"
    return
  fi
  finished="$(json_field "$body" last_completed.finished_at)"
  if [ -z "$finished" ]; then
    fail scheduler-heartbeat "the worker has completed no dispatch pass; the scheduler sidecar is not driving it"
    return
  fi
  age="$(heartbeat_age_seconds "$finished")"
  if [ -z "$age" ]; then
    # Unparseable timestamp is reported, not silently treated as fresh.
    fail scheduler-heartbeat "could not read the heartbeat timestamp '${finished}'"
  elif [ "$age" -le "$HEARTBEAT_MAX_AGE_SECONDS" ]; then
    pass scheduler-heartbeat "last completed pass ${age}s ago"
  else
    fail scheduler-heartbeat "the last completed dispatch pass was ${age}s ago (limit ${HEARTBEAT_MAX_AGE_SECONDS}s); the scheduler has stopped"
  fi
}

heartbeat_age_seconds() {
  # Whole seconds between $1 (an ISO-8601 instant) and now, or empty when it
  # cannot be read. python3 first because `date -d` rejects some fractional
  # offsets that FastAPI emits.
  local stamp="$1"
  if command -v python3 >/dev/null 2>&1; then
    python3 -c '
import sys
from datetime import datetime, timezone
raw = sys.argv[1].replace("Z", "+00:00")
try:
    moment = datetime.fromisoformat(raw)
except ValueError:
    sys.exit(1)
if moment.tzinfo is None:
    moment = moment.replace(tzinfo=timezone.utc)
print(int((datetime.now(timezone.utc) - moment).total_seconds()))
' "$stamp" 2>/dev/null
    return
  fi
  local epoch now
  epoch="$(date -u -d "$stamp" +%s 2>/dev/null)" || return 0
  now="$(date -u +%s)"
  [ -n "$epoch" ] && echo "$((now - epoch))"
}

check_frontend_root() {
  local code
  code="$(http_status "${WEB_BASE}/")"
  if [ "$code" = "200" ]; then
    pass frontend-root "GET / -> 200"
  else
    fail frontend-root "GET ${WEB_BASE}/ -> ${code} (\`docker compose logs web\` shows whether npm ci or vite failed)"
  fi
}

check_frontend_spa_route() {
  local code
  code="$(http_status "${WEB_BASE}/coordinator-portal")"
  if [ "$code" = "200" ]; then
    pass frontend-spa-route "GET /coordinator-portal -> 200"
  else
    fail frontend-spa-route "GET ${WEB_BASE}/coordinator-portal -> ${code}: the dev server is not serving deep routes"
  fi
}

check_frontend_api_proxy() {
  local body email
  http_get -H "Authorization: Bearer ${API_BEARER}" "${WEB_BASE}/v1/me"
  body="$HTTP_BODY"
  if [ "$HTTP_CODE" != "200" ]; then
    fail frontend-api-proxy "GET ${WEB_BASE}/v1/me -> ${HTTP_CODE}: the dev server's /v1 proxy is not reaching the API"
    return
  fi
  email="$(json_field "$body" email)"
  if [ "$email" = "$PILOT_EMAIL" ]; then
    pass frontend-api-proxy "proxied /v1/me authenticated as ${email}"
  else
    fail frontend-api-proxy "proxied /v1/me authenticated as '${email:-nobody}', not the seeded principal"
  fi
}

run_all_checks() {
  local id
  for id in "${CHECK_IDS[@]}"; do
    CHECK_STATUS["$id"]=fail
    CHECK_DETAIL["$id"]="not evaluated"
  done

  check_db_healthy
  check_migrations_at_head
  check_one_shot_exited_ok migrate-exited-ok migrate
  check_one_shot_exited_ok seed-exited-ok seed
  check_one_shot_exited_ok seed-review-exited-ok seed-review
  check_api_health
  check_worker_health
  check_scheduler_heartbeat
  check_frontend_root
  check_frontend_spa_route
  check_frontend_api_proxy

  for id in "${CHECK_IDS[@]}"; do
    [ "${CHECK_STATUS[$id]}" = "pass" ] || return 1
  done
  return 0
}

json_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\n\r\t'
}

emit_json() {
  local overall="$1" id first=1
  printf '{"healthy":%s,"release_expected":"%s","checks":[' \
    "$([ "$overall" -eq 0 ] && echo true || echo false)" "$(json_escape "$EXPECTED_RELEASE")"
  for id in "${CHECK_IDS[@]}"; do
    [ "$first" -eq 1 ] || printf ','
    first=0
    printf '{"id":"%s","status":"%s","detail":"%s"}' \
      "$id" "${CHECK_STATUS[$id]}" "$(json_escape "${CHECK_DETAIL[$id]}")"
  done
  printf ']}\n'
}

emit_human() {
  local overall="$1" id mark
  for id in "${CHECK_IDS[@]}"; do
    if [ "${CHECK_STATUS[$id]}" = "pass" ]; then mark="PASS"; else mark="FAIL"; fi
    printf '  %-4s %-22s %s\n' "$mark" "$id" "${CHECK_DETAIL[$id]}"
  done
  if [ "$overall" -eq 0 ]; then
    printf 'health: all %d checks passed\n' "${#CHECK_IDS[@]}"
  else
    printf 'health: FAILED\n'
  fi
}

# --- the bounded loop -------------------------------------------------------

deadline=$(( $(date +%s) + TIMEOUT ))
overall=1
attempt=0

while :; do
  attempt=$((attempt + 1))
  if run_all_checks; then
    overall=0
    break
  fi
  overall=1
  [ "$WAIT" -eq 1 ] || break
  if [ "$(date +%s)" -ge "$deadline" ]; then
    [ "$JSON" -eq 1 ] || printf 'health: gave up after %ds (%d attempts)\n' "$TIMEOUT" "$attempt" >&2
    break
  fi
  [ "$JSON" -eq 1 ] || printf 'health: attempt %d incomplete, retrying...\n' "$attempt" >&2
  sleep 5
done

if [ "$JSON" -eq 1 ]; then
  emit_json "$overall"
else
  emit_human "$overall"
fi

exit "$overall"
