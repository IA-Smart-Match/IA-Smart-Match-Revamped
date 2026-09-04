#!/usr/bin/env bash
#
# SmartMatch launcher — Ubuntu 24.04, WSL, and anywhere else with bash.
#
# This is the everyday entry point to the compose appliance
# (docker-compose.yml). `smartmatch.ps1` is the same command set for Windows
# PowerShell; the two are kept in step by tests/unit/test_launcher_parity.py.
#
# It is a launcher, not a deployment tool. Everything it does happens on this
# machine, against the same local-only stack docker-compose.yml describes:
# ALLOW_CLOUD_DEPLOY=false is untouched, no image is published, no cloud
# resource is provisioned, and nothing here reaches outside the compose
# network. Deploying the synthetic instance to the pilot VM is a separate
# script with a separate name — scripts/vm/deploy.sh — precisely so that
# "start the appliance" and "release to the VM" can never be the same keystroke.
#
# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
#   install [--developer]  Validate, build, start, wait for health, print URLs.
#                          --developer additionally installs the Python and
#                          Node toolchains and runs the local gates.
#   start                  Bring the stack up (build if images are missing).
#   stop                   Stop the stack, KEEPING the data volumes.
#   restart                stop then start.
#   status [--json]        Per-service state and health.
#   health [--wait]        The bounded health suite. Non-mutating.
#   verify [--full]        health, plus (--full) the end-to-end smoke path.
#   logs [service] [-f]    Container logs.
#
# ---------------------------------------------------------------------------
# Exit codes — stable, and tested
# ---------------------------------------------------------------------------
#   0  success
#   1  the stack is unhealthy, or a verification failed
#   2  usage error (unknown command, unknown flag, unknown service)
#   3  a prerequisite is missing (docker, or compose v2)
#   4  a published port is already held by something that is not this stack
#   5  timed out waiting for the stack to become healthy
#
# `stop` never removes a volume, and neither does anything else here. Discarding
# the database is `docker compose down -v`, spelled out by hand, on purpose.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT" || exit 2

EXIT_OK=0
EXIT_UNHEALTHY=1
EXIT_USAGE=2
EXIT_PREREQ=3
EXIT_PORT=4
EXIT_TIMEOUT=5

READY_TIMEOUT="${SMARTMATCH_READY_TIMEOUT:-900}"

# The ports docker-compose.yml publishes, all on 127.0.0.1. Kept as
# "port=service" pairs so a collision message can name what wanted the port.
PUBLISHED_PORTS=(
  "5432=postgres"
  "8080=api"
  "8081=worker"
  "5173=web"
)

COMPOSE_SERVICES=(db migrate seed seed-logins api worker scheduler seed-review web)

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { local code="$1"; shift; printf '%s\n' "$*" >&2; exit "$code"; }

# --- prerequisites ----------------------------------------------------------

require_docker() {
  command -v docker >/dev/null 2>&1 \
    || die "$EXIT_PREREQ" "docker is not installed or not on PATH. Run ./setup.sh (Ubuntu/WSL) or setup.ps1 (Windows) first."
  docker compose version >/dev/null 2>&1 \
    || die "$EXIT_PREREQ" "docker compose v2 is unavailable. The legacy 'docker-compose' binary is not a substitute; run ./setup.sh to install the compose plugin."
  docker info >/dev/null 2>&1 \
    || die "$EXIT_PREREQ" "the Docker daemon is not reachable. Start Docker Desktop, or 'sudo systemctl start docker', then retry."
}

port_in_use() {
  # True when something is listening on 127.0.0.1:$1. ss, then lsof, then a
  # bash /dev/tcp probe — one of the three exists on every machine this runs on.
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :${port}" 2>/dev/null | grep -q ":${port}" && return 0
    return 1
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${port}" -sTCP:LISTEN -n -P >/dev/null 2>&1 && return 0
    return 1
  fi
  (exec 3<>"/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1 && { exec 3>&- 3<&-; return 0; }
  return 1
}

stack_has_containers() {
  [ -n "$(docker compose ps -aq 2>/dev/null)" ]
}

check_ports_free() {
  # Only meaningful before this stack owns them. Once it is up the ports are
  # legitimately busy, and a collision check that cannot tell the difference
  # would make `restart` fail on a healthy machine.
  stack_has_containers && return 0
  local entry port owner busy=()
  for entry in "${PUBLISHED_PORTS[@]}"; do
    port="${entry%%=*}"
    owner="${entry##*=}"
    port_in_use "$port" && busy+=("${port} (wanted by ${owner})")
  done
  if [ "${#busy[@]}" -gt 0 ]; then
    warn "These published ports are already held by something else:"
    printf '  %s\n' "${busy[@]}" >&2
    warn ""
    warn "The most common cause is a native PostgreSQL on 5432 — docker-compose.yml's"
    warn "header says it outright: pick one database. Stop the other service"
    warn "('sudo service postgresql stop'), or change the published port in"
    warn "docker-compose.yml and set SMARTMATCH_DATABASE_URL to match."
    exit "$EXIT_PORT"
  fi
}

validate_configuration() {
  # `docker compose config -q` parses the file, resolves every ${VAR}, and
  # fails on an anchor that no longer resolves — which is the failure mode the
  # compose file's YAML-anchor identity design is most exposed to.
  docker compose config -q 2>/tmp/smartmatch-config-err.txt \
    || { warn "docker-compose.yml is not valid:"; cat /tmp/smartmatch-config-err.txt >&2; exit "$EXIT_USAGE"; }
  say "configuration: docker-compose.yml parses and every reference resolves"

  if [ ! -f "${REPO_ROOT}/.env" ]; then
    say "configuration: no .env — the appliance runs on docker-compose.yml's own defaults."
    say "               Copy .env.example to .env only if you need the pilot logins."
  else
    say "configuration: .env present (left exactly as it is; nothing here writes to it)"
  fi
}

# --- commands ---------------------------------------------------------------

cmd_start() {
  require_docker
  check_ports_free
  say "starting the appliance (building images that are missing or stale)..."
  docker compose up --build -d || die "$EXIT_UNHEALTHY" "docker compose up failed; 'smartmatch.sh logs' has the reason"
  wait_for_health
}

cmd_stop() {
  require_docker
  say "stopping the appliance (data volumes are kept)..."
  docker compose stop || die "$EXIT_UNHEALTHY" "docker compose stop failed"
  say "stopped. 'smartmatch.sh start' brings it back with the same database."
}

cmd_restart() {
  cmd_stop
  cmd_start
}

wait_for_health() {
  say "waiting for the stack to become healthy (up to ${READY_TIMEOUT}s)..."
  say "first run is slow: the images build and the web service runs npm ci."
  if scripts/compose_health.sh --wait --timeout "$READY_TIMEOUT"; then
    print_urls
    return "$EXIT_OK"
  fi
  warn ""
  warn "The stack did not become healthy within ${READY_TIMEOUT}s."
  warn "'./smartmatch.sh status' shows which service is stuck and"
  warn "'./smartmatch.sh logs <service>' shows why."
  exit "$EXIT_TIMEOUT"
}

print_urls() {
  say ""
  say "SmartMatch is up:"
  say "  frontend   http://127.0.0.1:5173/           <- open this"
  say "  portal     http://127.0.0.1:5173/coordinator-portal"
  say "  api        http://127.0.0.1:8080/api/health"
  say "  worker     http://127.0.0.1:8081/health"
  say "  database   postgresql://smartmatch:smartmatch@127.0.0.1:5432/smartmatch"
  say ""
  say "The frontend authenticates with the compose-only fixture bearer token."
  say "There is no login and no identity provider — see docker-compose.yml's header."
}

cmd_install() {
  local developer=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --developer) developer=1 ;;
      *) die "$EXIT_USAGE" "install: unknown flag '$1' (only --developer is accepted)" ;;
    esac
    shift
  done

  require_docker
  validate_configuration
  check_ports_free

  say ""
  say "building images..."
  docker compose build || die "$EXIT_UNHEALTHY" "the image build failed"

  say "starting services..."
  docker compose up -d || die "$EXIT_UNHEALTHY" "docker compose up failed; 'smartmatch.sh logs' has the reason"

  wait_for_health || exit "$?"

  if [ "$developer" -eq 1 ]; then
    install_developer_toolchain
  fi

  say "install complete."
}

install_developer_toolchain() {
  say ""
  say "== developer install =="

  command -v python3 >/dev/null 2>&1 \
    || die "$EXIT_PREREQ" "python3 is not installed. ./setup.sh --developer installs Python 3.11 and python3-venv."
  local pyversion
  pyversion="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
  case "$pyversion" in
    3.11|3.12) say "python: ${pyversion}" ;;
    *) die "$EXIT_PREREQ" "python3 is ${pyversion:-unknown}; pyproject.toml requires >=3.11,<3.13 and everything is verified against 3.11." ;;
  esac

  say "creating .venv and installing hash-verified dependencies (slow; do not interrupt)..."
  python3 -m venv .venv \
    || die "$EXIT_PREREQ" "python3 -m venv failed. On Debian/Ubuntu install python3-venv — it is a separate package."
  .venv/bin/pip install -q --upgrade pip || die "$EXIT_UNHEALTHY" "pip upgrade failed"
  .venv/bin/pip install -q --require-hashes -r requirements/dev.txt \
    || die "$EXIT_UNHEALTHY" "the hash-verified dependency install failed"
  .venv/bin/pip install -q --no-deps \
    -e python/smartmatch_domain -e python/smartmatch_authz \
    -e python/smartmatch_providers -e python/smartmatch_persistence \
    || die "$EXIT_UNHEALTHY" "the editable workspace install failed"

  command -v node >/dev/null 2>&1 \
    || die "$EXIT_PREREQ" "node is not installed. ./setup.sh --developer installs Node 22 (the version in .nvmrc)."
  local major
  major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null)"
  [ "${major:-0}" -ge 20 ] \
    || die "$EXIT_PREREQ" "node is v${major:-unknown}; the frontend needs >=20 and .nvmrc pins 22."
  say "node: v$(node -p 'process.versions.node')"

  say "installing frontend dependencies from the lockfile..."
  ( cd apps/web/legacy-frontend && npm ci --no-audit --no-fund ) \
    || die "$EXIT_UNHEALTHY" "npm ci failed in apps/web/legacy-frontend"

  say ""
  say "running the local gates ('make check')..."
  make check || die "$EXIT_UNHEALTHY" "'make check' failed — the toolchain installed, but the tree does not pass its own gates."
  say "developer install complete."
}

cmd_status() {
  local json=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --json) json=1 ;;
      *) die "$EXIT_USAGE" "status: unknown flag '$1' (only --json is accepted)" ;;
    esac
    shift
  done
  require_docker

  local service state health exit_code first=1 unhealthy=0

  if [ "$json" -eq 1 ]; then
    printf '{"services":['
  fi

  for service in "${COMPOSE_SERVICES[@]}"; do
    state="$(docker compose ps -a --format '{{.State}}' "$service" 2>/dev/null | head -n1 | tr -d '\r')"
    health="$(docker compose ps -a --format '{{.Health}}' "$service" 2>/dev/null | head -n1 | tr -d '\r')"
    exit_code="$(docker compose ps -a --format '{{.ExitCode}}' "$service" 2>/dev/null | head -n1 | tr -d '\r')"
    [ -n "$state" ] || state="absent"

    # A one-shot that exited 0 is correct, not down. Conflating the two is how
    # a status display teaches people to ignore it.
    case "$service" in
      migrate|seed|seed-logins|seed-review)
        if [ "$state" != "exited" ] || [ "${exit_code:-1}" != "0" ]; then unhealthy=1; fi
        ;;
      *)
        if [ "$state" != "running" ]; then unhealthy=1; fi
        ;;
    esac

    if [ "$json" -eq 1 ]; then
      [ "$first" -eq 1 ] || printf ','
      first=0
      printf '{"service":"%s","state":"%s","health":"%s","exit_code":%s}' \
        "$service" "$state" "${health:-none}" "${exit_code:-null}"
    else
      printf '  %-12s state=%-10s health=%-10s exit=%s\n' \
        "$service" "$state" "${health:-none}" "${exit_code:-—}"
    fi
  done

  if [ "$json" -eq 1 ]; then
    printf '],"ok":%s}\n' "$([ "$unhealthy" -eq 0 ] && echo true || echo false)"
  elif [ "$unhealthy" -eq 0 ]; then
    say "all services are in their expected state."
  else
    say "at least one service is not in its expected state."
  fi

  [ "$unhealthy" -eq 0 ] || exit "$EXIT_UNHEALTHY"
}

cmd_health() {
  local args=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --wait) args+=(--wait) ;;
      --json) args+=(--json) ;;
      --timeout) shift; [ "$#" -gt 0 ] || die "$EXIT_USAGE" "health: --timeout needs a value"; args+=(--timeout "$1") ;;
      *) die "$EXIT_USAGE" "health: unknown flag '$1'" ;;
    esac
    shift
  done
  require_docker
  scripts/compose_health.sh "${args[@]+"${args[@]}"}" || exit "$EXIT_UNHEALTHY"
}

cmd_verify() {
  local full=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --full) full=1 ;;
      *) die "$EXIT_USAGE" "verify: unknown flag '$1' (only --full is accepted)" ;;
    esac
    shift
  done
  require_docker

  validate_configuration
  say ""
  say "== health =="
  scripts/compose_health.sh || die "$EXIT_UNHEALTHY" "the health suite failed; the stack is not serving correctly."

  if [ "$full" -eq 1 ]; then
    say ""
    say "== full smoke path (this WRITES to the appliance's database) =="
    scripts/compose_smoke.sh || die "$EXIT_UNHEALTHY" "the end-to-end smoke path failed."
  else
    say ""
    say "verify passed. 'verify --full' additionally runs scripts/compose_smoke.sh,"
    say "which imports, dispatches, reviews, and asserts the metrics move — and"
    say "which writes to the appliance's database, unlike everything above."
  fi
}

cmd_logs() {
  local service="" follow=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -f|--follow) follow=(--follow) ;;
      -*) die "$EXIT_USAGE" "logs: unknown flag '$1'" ;;
      *)
        [ -z "$service" ] || die "$EXIT_USAGE" "logs: name at most one service"
        service="$1"
        ;;
    esac
    shift
  done

  if [ -n "$service" ]; then
    local known=0 candidate
    for candidate in "${COMPOSE_SERVICES[@]}"; do
      [ "$candidate" = "$service" ] && known=1
    done
    [ "$known" -eq 1 ] || die "$EXIT_USAGE" "logs: '${service}' is not a service in this stack. Known: ${COMPOSE_SERVICES[*]}"
    require_docker
    docker compose logs --no-color --tail 200 "${follow[@]+"${follow[@]}"}" "$service"
  else
    require_docker
    docker compose logs --no-color --tail 200 "${follow[@]+"${follow[@]}"}"
  fi
}

usage() {
  sed -n '2,45p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# --- dispatch ---------------------------------------------------------------

[ "$#" -gt 0 ] || { usage; exit "$EXIT_USAGE"; }

command="$1"
shift

case "$command" in
  install) cmd_install "$@" ;;
  start)   cmd_start "$@" ;;
  stop)    cmd_stop "$@" ;;
  restart) cmd_restart "$@" ;;
  status)  cmd_status "$@" ;;
  health)  cmd_health "$@" ;;
  verify)  cmd_verify "$@" ;;
  logs)    cmd_logs "$@" ;;
  -h|--help|help) usage ;;
  *)
    warn "unknown command: ${command}"
    warn ""
    usage
    exit "$EXIT_USAGE"
    ;;
esac
