#!/usr/bin/env bash
#
# Deploy the synthetic SmartMatch instance on the pilot VM.
#
# This is the only command that changes what the VM is running. GitHub Actions
# invokes it over IAP (see .github/workflows/deploy.yml); an operator can run
# the same command by hand over the same IAP tunnel. There is no other path,
# and in particular there is no path that reaches the VM from the public
# internet.
#
#   sudo -u smartmatch /opt/smartmatch/app/scripts/vm/deploy.sh
#
# ---------------------------------------------------------------------------
# What it guarantees
# ---------------------------------------------------------------------------
#
#   1. One deployment at a time. A flock on $LOCK_FILE; a second invocation
#      waits rather than interleaving two `git pull`s and two migrations.
#   2. The previous SHA is recorded before anything moves, and a timestamped
#      pg_dump is taken before the migration runs.
#   3. A dirty working tree is refused. Tracked files modified on the VM mean
#      the deployed SHA does not describe what is running, and every other
#      guarantee here is written in terms of that SHA.
#   4. Only a fast-forward. `git pull --ff-only` plus an explicit ancestry
#      check, so a force-pushed or rewritten `deploy` branch stops the
#      deployment instead of silently rewriting the VM's history.
#   5. Images are built BEFORE any running service is replaced. A build that
#      fails leaves the previous release serving.
#   6. The migration service runs exactly once, through compose's own
#      dependency ordering, and the API and worker do not start until it has
#      exited 0.
#   7. No volume is ever removed. `docker compose down -v` does not appear in
#      this file, and tests/unit/test_vm_deploy_script.py asserts that it never
#      will: it is the one command that would discard the database.
#   8. The full bounded health suite must pass (scripts/compose_health.sh),
#      including that /api/health reports the SHA just deployed.
#   9. On failure the APPLICATION rolls back to the previous SHA, rebuilds,
#      and re-runs health — and the script still exits nonzero, so the GitHub
#      job fails even though the VM recovered.
#
# ---------------------------------------------------------------------------
# What it will never do: undo a migration
# ---------------------------------------------------------------------------
# Database migrations are forward-only. This script never runs `alembic
# downgrade` and never restores the backup it takes. The rollback in step 9 is
# an APPLICATION rollback: the previous code, against the already-migrated
# schema. That is safe precisely because the migration policy requires each
# revision to be compatible with the release before it — see
# docs/operations/deploy-runbook.md, which is the authority on this and on what
# to do when a revision fails part-way.
#
# The rule that rollback depends on: a release only ADDS to the schema
# (expand). Dropping or renaming a table or column (contract) ships in a LATER
# release, once the release that stopped using the object is promoted and
# stable. A drop shipped together with the code that stops reading the column
# breaks step 9: the previous code still selects and inserts it.
# tools/migration_expand_contract_check.py (`make expand-contract`, and the
# `isolation` job in CI) fails a migration whose upgrade() drops or renames,
# unless the file is marked as a contract revision:
#
#     # unused since: <the release that stopped using the object>
#     CONTRACT_PHASE = True
#
# What step 9 does about the migration step. The compose `migrate` service runs
# the CHECKOUT's db/ tree, and after the rollback checkout that is the previous
# release's tree. If the failed release already applied a revision, the
# database is at a revision that tree does not contain, so the previous
# release's migrate exits non-zero ("Can't locate revision identified by ...")
# and compose will not start the API or the worker behind it. The rollback
# therefore tries the ordinary `up` first and, ONLY when migrate failed for
# exactly that reason AND the named revision is one the failed release's tree
# defines and the previous release's tree does not, brings the stack up again
# with migrate replaced by a no-op (an override file written to $STATE_DIR —
# see schema_ahead_revision and rollback below). Nothing is downgraded; the
# schema stays where the failed release left it, which is what expand/contract
# makes safe for the previous code. Health then tolerates one check only: the
# previous release's `migrations-at-head`, and only when it reports that same
# revision. Any other migrate failure, and any other failing check, still ends
# in "The VM needs a human". A forward deployment never takes this path.
#
# One consequence of step 4: `git pull` replaces this file on disk, but the
# copy already executing is the PREVIOUS release's. A change to the rollback
# logic therefore takes effect from the deployment AFTER the one that ships it.
#
# The backup exists so a human has something to work from when a migration
# does real damage. Restoring it is a deliberate, manual, logged decision, not
# something an automated deployment gets to make at 3am.
#
# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
# Nothing here reads a secret. The Cloudflare tunnel token lives in
# cloudflared's own credentials file, installed out-of-band; this script never
# touches it. Everything written to the log passes through redact(), which
# blanks anything shaped like a token, key, secret, or password so that a
# future step which does handle one cannot leak it into a deployment log.
#
# Exit codes:
#   0  deployed and healthy
#   1  deployment failed (the log and metadata say where; the application was
#      rolled back to the previous SHA if one existed)
#   2  refused before changing anything (dirty tree, non-fast-forward, misuse)
#   3  a prerequisite is missing

set -uo pipefail

# --- configuration ----------------------------------------------------------
#
# Every path is overridable so the mocked deployment tests can run this script
# against a scratch directory with stub `git`, `docker`, and `pg_dump` on PATH.
# The defaults are what scripts/vm/bootstrap_vm.sh creates.

STATE_DIR="${SMARTMATCH_STATE_DIR:-/opt/smartmatch}"
APP_DIR="${SMARTMATCH_APP_DIR:-${STATE_DIR}/app}"
BACKUP_DIR="${SMARTMATCH_BACKUP_DIR:-${STATE_DIR}/backups}"
LOG_DIR="${SMARTMATCH_LOG_DIR:-${STATE_DIR}/logs}"
META_DIR="${SMARTMATCH_META_DIR:-${STATE_DIR}/deployments}"
# SHARED LOCK: scripts/vm/smartmatch.service's ExecStart also takes this same
# flock (hardcoded there as /opt/smartmatch/deploy.lock, since a systemd unit
# cannot expand this shell variable) before it runs `docker compose up -d` on
# boot. That is what stops a boot from racing an in-flight deployment. If this
# default ever changes, update the unit file to match.
LOCK_FILE="${SMARTMATCH_LOCK_FILE:-${STATE_DIR}/deploy.lock}"
SSH_KEY="${SMARTMATCH_SSH_KEY:-${STATE_DIR}/.ssh/id_ed25519}"
DEPLOY_BRANCH="${SMARTMATCH_DEPLOY_BRANCH:-deploy}"
LOCK_WAIT_SECONDS="${SMARTMATCH_LOCK_WAIT_SECONDS:-1800}"
HEALTH_TIMEOUT="${SMARTMATCH_HEALTH_TIMEOUT:-900}"
BACKUP_RETAIN="${SMARTMATCH_BACKUP_RETAIN:-14}"
# How long to wait for the seed-logins one-shot to finish. Nothing in the
# compose graph depends on it, so `up -d` returns while it is still running and
# its exit code has to be waited for rather than read. Seconds, not minutes:
# it hashes four passwords against a local database.
SEED_LOGINS_TIMEOUT="${SMARTMATCH_SEED_LOGINS_TIMEOUT:-120}"
# How many 2-second polls to give a stopped database container to report
# healthy before the deployment refuses for want of a backup.
DB_START_ATTEMPTS="${SMARTMATCH_DB_START_ATTEMPTS:-60}"

# The CBA stack. resolve_compose_scope (below) appends the class-exercise
# overlay to this when the checkout is configured for it.
BASE_COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.vm.yml)
COMPOSE_FILES=("${BASE_COMPOSE_FILES[@]}")
EXERCISE_COMPOSE_FILE="docker-compose.exercise.yml"
# The .env key whose presence means "this VM hosts the class exercise".
EXERCISE_ENV_KEY="SMARTMATCH_EXERCISE_WORKSPACE_SECRET"
DB_URL="postgresql://smartmatch:smartmatch@localhost:5432/smartmatch"
# Written by rollback() when the previous release has to start against a schema
# that is ahead of it, and named on the compose command line only then. It
# lives outside the checkout so it never makes the working tree dirty.
SKIP_MIGRATE_FILE="${STATE_DIR}/rollback-skip-migrate.compose.yml"
SKIP_MIGRATE=0
MIGRATIONS_DIR="db/migrations/versions"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

EXIT_OK=0
EXIT_FAILED=1
EXIT_REFUSED=2
EXIT_PREREQ=3

# --- logging ----------------------------------------------------------------

redact() {
  # Blank anything shaped like a credential before it reaches a log file that
  # a CI job will later print. Deliberately broad: a redacted value that did
  # not need redacting costs nothing, and the reverse is unrecoverable.
  sed -E \
    -e 's/((token|secret|password|passwd|api[-_]?key|key|credential)[^[:alnum:]]{0,3})[[:alnum:]_\-\.\/\+=]{8,}/\1[REDACTED]/Ig' \
    -e 's#(https?://)[^:/@[:space:]]+:[^@[:space:]]+@#\1[REDACTED]@#g' \
    -e 's/(Bearer )[[:alnum:]_\-\.]{8,}/\1[REDACTED]/Ig'
}

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail_out() { printf '%s ERROR %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }

# --- prerequisites ----------------------------------------------------------

for tool in git docker flock; do
  command -v "$tool" >/dev/null 2>&1 || {
    fail_out "required tool '${tool}' is not installed on this VM"
    exit "$EXIT_PREREQ"
  }
done

[ -d "$APP_DIR/.git" ] || {
  fail_out "${APP_DIR} is not a git checkout; run scripts/vm/bootstrap_vm.sh first"
  exit "$EXIT_PREREQ"
}

# --- the lock ---------------------------------------------------------------
#
# Acquired BEFORE the log file is opened, so a waiting invocation does not
# create a second, near-empty deployment log while it blocks. Re-exec under
# flock rather than backgrounding one: the lock is then held by this process
# for its whole life, including the rollback, and is released by the kernel
# even if the VM kills us.

if [ "${SMARTMATCH_DEPLOY_LOCK_HELD:-0}" != "1" ]; then
  export SMARTMATCH_DEPLOY_LOCK_HELD=1
  log "waiting for the deployment lock (${LOCK_FILE}, up to ${LOCK_WAIT_SECONDS}s)"
  mkdir -p "$(dirname "$LOCK_FILE")" 2>/dev/null || true
  exec flock --wait "$LOCK_WAIT_SECONDS" "$LOCK_FILE" "$0" "$@"
  # `exec` only returns if flock could not start; a timeout exits 1 from flock.
  fail_out "could not acquire the deployment lock within ${LOCK_WAIT_SECONDS}s"
  exit "$EXIT_FAILED"
fi

mkdir -p "$BACKUP_DIR" "$LOG_DIR" "$META_DIR" || {
  fail_out "cannot create the state directories under ${STATE_DIR}"
  exit "$EXIT_PREREQ"
}

LOG_FILE="${LOG_DIR}/deploy-${STAMP}.log"
META_FILE="${META_DIR}/deploy-${STAMP}.json"

# Everything from here is logged, redacted, and echoed to the caller — which
# for an automated deployment is the GitHub Actions job output.
exec > >(redact | tee -a "$LOG_FILE") 2>&1

cd "$APP_DIR" || { fail_out "cannot enter ${APP_DIR}"; exit "$EXIT_PREREQ"; }

# The read-only deploy key. `bootstrap_vm.sh` also writes this into the clone's
# own `core.sshCommand`, so a hand-run `git fetch` in that directory works too;
# this export is what makes the value independent of a config a later
# `git config --unset` or a fresh clone could lose. Without it git offers no
# identity at all and every fetch fails with "Permission denied (publickey)" —
# which reads like a broken key rather than a missing one.
if [ -f "${SSH_KEY}" ]; then
  export GIT_SSH_COMMAND="ssh -i ${SSH_KEY} -o IdentitiesOnly=yes -o UserKnownHostsFile=${STATE_DIR}/.ssh/known_hosts -o StrictHostKeyChecking=yes"
fi

log "=== SmartMatch VM deployment ${STAMP} ==="
log "app dir:  ${APP_DIR}"
log "branch:   ${DEPLOY_BRANCH}"
log "log file: ${LOG_FILE}"

# --- metadata ---------------------------------------------------------------

PREVIOUS_SHA=""
DEPLOYED_SHA=""
# Where the last deploy_current_checkout stopped: build, up, migrate,
# seed-logins, or empty when it succeeded.
BRING_UP_FAILED_AT=""
BACKUP_FILE=""
OUTCOME="failed"
FAILURE_STAGE="startup"
ROLLED_BACK="false"

json_string() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\n\r\t'
}

write_metadata() {
  cat > "$META_FILE" <<META
{
  "stamp": "${STAMP}",
  "branch": "$(json_string "$DEPLOY_BRANCH")",
  "previous_sha": "$(json_string "$PREVIOUS_SHA")",
  "deployed_sha": "$(json_string "$DEPLOYED_SHA")",
  "backup_file": "$(json_string "$BACKUP_FILE")",
  "outcome": "$(json_string "$OUTCOME")",
  "failure_stage": "$(json_string "$FAILURE_STAGE")",
  "rolled_back": ${ROLLED_BACK},
  "log_file": "$(json_string "$LOG_FILE")"
}
META
  log "metadata: ${META_FILE}"
}

trap 'write_metadata' EXIT

compose() { docker compose "${COMPOSE_FILES[@]}" "$@"; }

resolve_compose_scope() {
  # Decides, for the checkout currently in $APP_DIR, whether the class-exercise
  # overlay (api-exercise, web-exercise) is part of the stack this script
  # manages. Without it, `up -d --remove-orphans` deletes those containers as
  # orphans of the `smartmatch` project on every deployment.
  #
  # It must stay CONDITIONAL. docker-compose.exercise.yml uses required
  # `${VAR:?}` interpolation, which compose evaluates at parse time for the
  # whole file; naming it on a VM without the exercise secrets breaks every
  # compose command here, not only the exercise services. So the overlay is
  # loaded only when .env gives SMARTMATCH_EXERCISE_WORKSPACE_SECRET a
  # non-empty value AND the checkout has the file. The second check matters
  # after a rollback to a release that predates it.
  #
  # Re-run before each build-and-up, because the pull and the rollback both
  # change which checkout that is. `--profile exercise` goes in the same array
  # as the files: it is a global `docker compose` flag, and one array keeps the
  # expansion safe under `set -u`.
  COMPOSE_FILES=("${BASE_COMPOSE_FILES[@]}")
  if [ -f .env ] \
     && grep -Eq "^[[:space:]]*(export[[:space:]]+)?${EXERCISE_ENV_KEY}=[\"']?[^\"'[:space:]]" .env \
     && [ -f "$EXERCISE_COMPOSE_FILE" ]; then
    COMPOSE_FILES+=(-f "$EXERCISE_COMPOSE_FILE" --profile exercise)
    log "compose scope: CBA + class exercise (${EXERCISE_COMPOSE_FILE}, --profile exercise)"
  else
    log "compose scope: CBA only (no ${EXERCISE_ENV_KEY} in .env, or no ${EXERCISE_COMPOSE_FILE})"
  fi
  if [ "$SKIP_MIGRATE" = "1" ]; then
    COMPOSE_FILES+=(-f "$SKIP_MIGRATE_FILE")
    log "compose scope: migrate is a no-op for this rollback (${SKIP_MIGRATE_FILE})"
  fi
}

record_running_release() {
  # The systemd unit reads this file, so a reboot brings the stack back
  # reporting the SHA it is actually running rather than the `vm-unknown`
  # default. Written on success and after a rollback, because after a rollback
  # the running release is the previous SHA and the file must say so.
  printf 'SMARTMATCH_RELEASE=%s\n' "$1" > "${STATE_DIR}/release.env" 2>/dev/null \
    || log "warning: could not write ${STATE_DIR}/release.env"
}

resolve_compose_scope

# --- 1. refuse before changing anything -------------------------------------

FAILURE_STAGE="preflight"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  fail_out "tracked files are modified in ${APP_DIR}:"
  git status --short --untracked-files=no
  fail_out "Refusing to deploy. The deployed SHA would not describe what is running."
  fail_out "Resolve it on the VM ('git -C ${APP_DIR} checkout -- .' discards local edits) and retry."
  OUTCOME="refused"
  exit "$EXIT_REFUSED"
fi

PREVIOUS_SHA="$(git rev-parse HEAD)"
log "previous SHA: ${PREVIOUS_SHA}"

log "fetching origin/${DEPLOY_BRANCH}"
git fetch --quiet origin "$DEPLOY_BRANCH" || {
  fail_out "git fetch failed; the deploy key or network is broken. Nothing changed."
  OUTCOME="refused"
  exit "$EXIT_REFUSED"
}

TARGET_SHA="$(git rev-parse "origin/${DEPLOY_BRANCH}")"
log "origin/${DEPLOY_BRANCH}: ${TARGET_SHA}"

if [ "$TARGET_SHA" = "$PREVIOUS_SHA" ]; then
  log "already at origin/${DEPLOY_BRANCH}; this deployment is a no-op re-verification"
fi

# The explicit ancestry check. `git pull --ff-only` would also refuse, but it
# refuses with a message about diverged branches; this one names the actual
# situation — someone rewrote the protected branch — which is the fact worth
# waking up to.
if ! git merge-base --is-ancestor "$PREVIOUS_SHA" "$TARGET_SHA"; then
  fail_out "origin/${DEPLOY_BRANCH} (${TARGET_SHA}) is not a descendant of the deployed"
  fail_out "SHA (${PREVIOUS_SHA}). The protected branch was force-pushed or rewritten."
  fail_out "Refusing to deploy: a non-fast-forward update would make the VM's history"
  fail_out "disagree with the branch it claims to track. Nothing changed."
  OUTCOME="refused"
  exit "$EXIT_REFUSED"
fi

# --- 2. back up before anything migrates ------------------------------------

FAILURE_STAGE="backup"

DB_STATE="$(compose ps -a --format '{{.State}}' db 2>/dev/null | head -n1)"

if [ -z "$DB_STATE" ]; then
  log "no database container yet — this is the first deployment, so there is nothing to back up"
else
  # `docker compose exec` needs a RUNNING container, and the container's mere
  # existence does not mean it is running: a rebooted VM whose stack was never
  # brought back, or an operator's `compose stop`, both leave it `exited`.
  # Treating that as "no backup possible" would refuse every deployment,
  # including the one that would fix the machine — so the database is started
  # first, and only a database that will not start stops the deployment.
  if [ "$DB_STATE" != "running" ]; then
    log "the database container is '${DB_STATE}'; starting it so the backup can be taken"
    if ! compose up -d db; then
      fail_out "the database container will not start, so no backup can be taken."
      fail_out "Refusing to deploy. 'docker compose logs db' on the VM says why. Nothing changed."
      OUTCOME="refused"
      exit "$EXIT_REFUSED"
    fi
    db_ready=0
    for _ in $(seq 1 "$DB_START_ATTEMPTS"); do
      if [ "$(compose ps -a --format '{{.Health}}' db 2>/dev/null | head -n1)" = "healthy" ]; then
        db_ready=1
        break
      fi
      sleep 2
    done
    if [ "$db_ready" != "1" ]; then
      fail_out "the database container started but never reported healthy."
      fail_out "Refusing to migrate without a backup. Nothing changed."
      OUTCOME="refused"
      exit "$EXIT_REFUSED"
    fi
    log "the database is healthy"
  fi

  BACKUP_FILE="${BACKUP_DIR}/smartmatch-${STAMP}-${PREVIOUS_SHA:0:12}.sql.gz"
  log "backing up the database to ${BACKUP_FILE}"
  # pg_dump runs inside the db container, so the VM needs no client version
  # matched to the server. A failed backup stops the deployment: migrating
  # without one is the situation this whole file exists to avoid.
  if compose exec -T db pg_dump --clean --if-exists "$DB_URL" | gzip -c > "$BACKUP_FILE"; then
    log "backup complete ($(du -h "$BACKUP_FILE" 2>/dev/null | cut -f1))"
  else
    rm -f "$BACKUP_FILE"
    BACKUP_FILE=""
    fail_out "pg_dump failed. Refusing to migrate without a backup. Nothing changed."
    OUTCOME="refused"
    exit "$EXIT_REFUSED"
  fi
fi

# --- 3. fast-forward --------------------------------------------------------

FAILURE_STAGE="pull"

log "git pull --ff-only origin ${DEPLOY_BRANCH}"
if ! git pull --ff-only origin "$DEPLOY_BRANCH"; then
  fail_out "the fast-forward pull failed. Nothing was rebuilt; the previous release is still serving."
  OUTCOME="refused"
  exit "$EXIT_REFUSED"
fi

# The SHA actually checked out, read back from git rather than assumed from
# what origin reported a moment ago.
DEPLOYED_SHA="$(git rev-parse HEAD)"
log "deployed SHA: ${DEPLOYED_SHA}"
export SMARTMATCH_RELEASE="$DEPLOYED_SHA"

# --- 4-6. build, then replace -----------------------------------------------

deploy_current_checkout() {
  # Build first. A build failure must never reach the point of stopping a
  # running service, which is why this is a separate step from `up`.
  resolve_compose_scope
  log "building images for $(git rev-parse HEAD)"
  BRING_UP_FAILED_AT="build"
  compose build || return 1

  # `up -d` runs the one-shot migrate service exactly once and, through the
  # compose file's own `service_completed_successfully` conditions, does not
  # start the API or the worker until it has exited 0. That ordering is the
  # compose file's contract, so it is used rather than reimplemented here with
  # a separate `docker compose run`, which would migrate twice.
  #
  # --remove-orphans cleans up services deleted from the compose file. It
  # removes containers, never volumes. There is no `down`, and no `-v`,
  # anywhere in this script: the database and the web node_modules volume
  # survive every deployment, and that is asserted by a unit test.
  log "recreating changed services (volumes are preserved)"
  BRING_UP_FAILED_AT="up"
  compose up -d --remove-orphans || return 1

  local migrate_state migrate_exit
  migrate_state="$(compose ps -a --format '{{.State}}' migrate | head -n1)"
  migrate_exit="$(compose ps -a --format '{{.ExitCode}}' migrate | head -n1)"
  log "migrate: state=${migrate_state:-absent} exit=${migrate_exit:-unknown}"
  if [ "$migrate_state" != "exited" ] || [ "${migrate_exit:-1}" != "0" ]; then
    fail_out "the migration service did not exit 0. Migrations are forward-only:"
    fail_out "this script will not downgrade and will not restore the backup."
    fail_out "See docs/operations/deploy-runbook.md, 'When a revision fails part-way'."
    compose logs --no-color --tail=200 migrate || true
    BRING_UP_FAILED_AT="migrate"
    return 1
  fi

  # Password login for the pilot stakeholders is outside `migrate`'s reach: it
  # depends on the `seed-logins` one-shot creating one `pilot_credential` row
  # per role from .env's SMARTMATCH_PILOT_*_EMAIL/PASSWORD pairs. A deploy that
  # only checks `migrate` can go fully green with stakeholder login broken —
  # missing or partial .env, or a fresh empty database where fixture-token
  # health still passes. So this mirrors the migrate check above exactly.
  # Unlike `migrate`, this one has to be WAITED for.
  #
  # `api` declares depends_on: migrate/seed/seed-principals with condition
  # service_completed_successfully, so by the time `up -d` returns those have
  # necessarily finished and reading their exit code straight away is sound.
  # NOTHING depends on seed-logins, so `up -d` returns while it is still
  # running. Reading its state immediately is a race, and the first automated
  # deployment to run this check lost it: seed-logins was still `running`, a
  # successful seeding was called a failure, and the release was rolled back.
  # `docker inspect` moments later showed exit=0.
  #
  # So poll until it stops being a running container, then judge it. The budget
  # is small because this is a handful of PBKDF2 hashes against a local
  # database, not a build.
  local seed_logins_state seed_logins_exit waited
  waited=0
  while [ "$waited" -lt "$SEED_LOGINS_TIMEOUT" ]; do
    seed_logins_state="$(compose ps -a --format '{{.State}}' seed-logins | head -n1)"
    case "$seed_logins_state" in
      running|created|restarting|"") : ;;
      *) break ;;
    esac
    sleep 2
    waited=$((waited + 2))
  done
  seed_logins_state="$(compose ps -a --format '{{.State}}' seed-logins | head -n1)"
  seed_logins_exit="$(compose ps -a --format '{{.ExitCode}}' seed-logins | head -n1)"
  log "seed-logins: state=${seed_logins_state:-absent} exit=${seed_logins_exit:-unknown} (waited ${waited}s)"
  if [ "$seed_logins_state" != "exited" ] || [ "${seed_logins_exit:-1}" != "0" ]; then
    fail_out "the seed-logins service did not exit 0. Stakeholder password login is"
    fail_out "not guaranteed to work; treating this as a deployment failure."
    compose logs --no-color --tail=200 seed-logins || true
    BRING_UP_FAILED_AT="seed-logins"
    return 1
  fi
  BRING_UP_FAILED_AT=""
  return 0
}

revision_defined_in() {
  # $1 a commit, $2 a revision id. True when that commit's migration tree has a
  # file declaring `revision = "<id>"` at column zero — the same greppable
  # declaration scripts/compose_health.sh computes the head from.
  git grep -q -E "^revision(: *str)? *= *[\"']${2}[\"']" "$1" -- "$MIGRATIONS_DIR" 2>/dev/null
}

schema_ahead_revision() {
  # Prints the revision the database is at, and returns 0, ONLY when the
  # bring-up that just failed on the rollback checkout failed for the one
  # reason an application rollback is expected to meet: the failed release
  # moved the schema forward, and this (previous) tree does not contain the
  # revision the database now names. All four must hold:
  #
  #   1. the failure was at `up` or at the migrate check — not the build, not
  #      seed-logins;
  #   2. the migrate container exited, non-zero;
  #   3. the LAST failure line it logged is the migration tool's "Can't locate
  #      revision identified by '<id>'" — an unreachable database, multiple
  #      heads, or a revision that is present and fails all say something else;
  #   4. <id> is declared in the failed release's tree ($DEPLOYED_SHA) and is
  #      NOT declared in the tree now checked out. A revision neither release
  #      knows is a database this script does not understand.
  #
  # Anything else returns 1 and the rollback stops with "needs a human".
  local state exit_code last_failure revision
  case "${BRING_UP_FAILED_AT:-}" in
    up|migrate) : ;;
    *) return 1 ;;
  esac
  state="$(compose ps -a --format '{{.State}}' migrate | head -n1)"
  exit_code="$(compose ps -a --format '{{.ExitCode}}' migrate | head -n1)"
  [ "$state" = "exited" ] || return 1
  case "$exit_code" in ''|0|*[!0-9]*) return 1 ;; esac

  last_failure="$(compose logs --no-color --tail=200 migrate 2>/dev/null | grep 'FAILED:' | tail -n1)"
  revision="$(printf '%s\n' "$last_failure" \
    | sed -n -E "s/.*FAILED: Can't locate revision identified by '([A-Za-z0-9_]+)'[[:space:]]*\$/\1/p")"
  [ -n "$revision" ] || return 1
  [ -n "$DEPLOYED_SHA" ] || return 1
  revision_defined_in "$DEPLOYED_SHA" "$revision" || return 1
  revision_defined_in HEAD "$revision" && return 1
  printf '%s' "$revision"
}

write_skip_migrate_override() {
  # A compose override that changes one thing: what the one-shot `migrate`
  # service runs. Everything else — the image, the database dependency, and
  # every other service's `service_completed_successfully` wait on migrate —
  # is the previous release's own compose file, so the seeds, the API and the
  # worker still start in compose's order. `sh` is what that service's own
  # command already runs under.
  cat > "$SKIP_MIGRATE_FILE" <<OVERRIDE
# Written by scripts/vm/deploy.sh ${STAMP} while rolling back to ${PREVIOUS_SHA}.
# The database is at revision ${1}, which that release's db/ tree does not
# contain, so its migration step cannot run. Nothing was downgraded. This file
# is named only by that rollback; the next deployment does not use it.
services:
  migrate:
    command: ["sh", "-c", "echo 'rollback: the schema is at ${1}, ahead of this release; migration step skipped'"]
OVERRIDE
}

health_tolerating_schema_ahead() {
  # $1 the revision the schema is known to be ahead at. The previous release's
  # own health suite, polled with --json until $HEALTH_TIMEOUT. It passes when
  # every check passes, or when the ONLY failing check is `migrations-at-head`
  # and its detail reports the database at exactly $1 — the difference this
  # rollback already established. That check compares the database to the
  # checkout's head, so against a newer schema it can never pass; every other
  # check (the API reporting this SHA, the worker, the frontend, the one-shots)
  # still has to.
  local revision="$1" deadline report failing
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  while :; do
    report="$(SMARTMATCH_RELEASE="$PREVIOUS_SHA" SMARTMATCH_API_BEARER="" \
      scripts/compose_health.sh --json 2>/dev/null)"
    failing="$(printf '%s' "$report" | grep -o '"id":"[^"]*","status":"[^"]*"' \
      | grep -v '"status":"pass"$' | sed -E 's/^"id":"([^"]*)".*/\1/' | tr '\n' ' ')"
    if printf '%s' "$report" | grep -q '"status":"pass"'; then
      if [ -z "$failing" ]; then
        return 0
      fi
      # The detail reads "<version table>='<revision>' but head is '<head>'".
      # Matched from the `=` on: the test that this script never invokes the
      # migration tool scans its code for that tool's name.
      if [ "$failing" = "migrations-at-head " ] \
         && printf '%s' "$report" | grep -qF "_version='${revision}' but head is '"; then
        log "health: every check passed except migrations-at-head, which reports the schema at ${revision} as expected"
        return 0
      fi
    fi
    [ "$(date +%s)" -ge "$deadline" ] && break
    sleep 5
  done
  fail_out "health: not tolerated — failing checks: ${failing:-the suite printed no result}"
  printf '%s\n' "$report"
  return 1
}

rollback() {
  # An APPLICATION rollback: the previous code, against the schema the
  # migration already moved forward. It never downgrades a migration and never
  # restores the backup — see this file's header and
  # docs/operations/deploy-runbook.md.
  #
  # The local branch is reset to the previous SHA rather than left detached, so
  # the next deployment's `git pull --ff-only origin <branch>` still sees a
  # fast-forward from a commit that is an ancestor of the branch head.
  local stage="$FAILURE_STAGE"
  ROLLED_BACK="true"

  if [ -z "$PREVIOUS_SHA" ]; then
    fail_out "no previous SHA to roll back to — this was the first deployment."
    fail_out "The VM is left as it is; inspect it before retrying."
    ROLLED_BACK="false"
    FAILURE_STAGE="$stage"
    return
  fi

  fail_out "rolling the application back to ${PREVIOUS_SHA}"
  if ! git checkout --force -B "$DEPLOY_BRANCH" "$PREVIOUS_SHA"; then
    fail_out "could not check out ${PREVIOUS_SHA}. The VM needs a human."
    ROLLED_BACK="false"
    FAILURE_STAGE="$stage"
    return
  fi

  export SMARTMATCH_RELEASE="$PREVIOUS_SHA"
  local ahead_revision=""
  if ! deploy_current_checkout; then
    # The one failure that is expected here: the failed release migrated, and
    # this release's migrate cannot run against a revision it does not have.
    # See schema_ahead_revision for exactly what is accepted as that.
    if ! ahead_revision="$(schema_ahead_revision)" || [ -z "$ahead_revision" ]; then
      fail_out "the previous release could not be rebuilt. The VM needs a human."
      FAILURE_STAGE="$stage"
      return
    fi
    fail_out "the database is at revision ${ahead_revision}, which ${DEPLOYED_SHA} added and"
    fail_out "${PREVIOUS_SHA} does not contain, so the previous release's migration step"
    fail_out "cannot run. Starting it WITHOUT that step, against the schema as it is."
    fail_out "Nothing is downgraded and the backup is not restored."
    if ! write_skip_migrate_override "$ahead_revision"; then
      fail_out "could not write ${SKIP_MIGRATE_FILE}. The VM needs a human."
      FAILURE_STAGE="$stage"
      return
    fi
    SKIP_MIGRATE=1
    if ! deploy_current_checkout; then
      fail_out "the previous release could not be started even without its migration step."
      fail_out "The VM needs a human."
      FAILURE_STAGE="$stage"
      return
    fi
  fi

  if [ -n "$ahead_revision" ]; then
    if health_tolerating_schema_ahead "$ahead_revision"; then
      record_running_release "$PREVIOUS_SHA"
      fail_out "rolled back to ${PREVIOUS_SHA} and it is healthy."
      fail_out "The schema is still at ${ahead_revision}: the previous code is running against the"
      fail_out "newer schema. Fix forward — the next deployment migrates normally."
      fail_out "The deployment still FAILED; this job exits nonzero on purpose."
    else
      fail_out "rolled back to ${PREVIOUS_SHA} but it is NOT healthy. The VM needs a human."
    fi
    FAILURE_STAGE="$stage"
    return
  fi

  # Empty here too, and it is correct in BOTH directions. After the rollback
  # checkout this is the PREVIOUS release's own compose_health.sh: an older one
  # reads `${VAR:-default}`, so an empty value falls back to `compose-api` and
  # it still checks the fixture identity that release genuinely shipped; a newer
  # one honours the empty value and runs the unauthenticated check instead.
  # Either way the suite matches the release it is actually testing.
  if SMARTMATCH_RELEASE="$PREVIOUS_SHA" \
     SMARTMATCH_API_BEARER="" \
     scripts/compose_health.sh --wait --timeout "$HEALTH_TIMEOUT"; then
    record_running_release "$PREVIOUS_SHA"
    fail_out "rolled back to ${PREVIOUS_SHA} and it is healthy."
    fail_out "The deployment still FAILED; this job exits nonzero on purpose."
  else
    fail_out "rolled back to ${PREVIOUS_SHA} but it is NOT healthy. The VM needs a human."
  fi
  FAILURE_STAGE="$stage"
}

FAILURE_STAGE="build-and-up"
if ! deploy_current_checkout; then
  fail_out "the new release could not be built or started"
  rollback
  exit "$EXIT_FAILED"
fi

# --- 7. health --------------------------------------------------------------

FAILURE_STAGE="health"
log "running the bounded health suite (up to ${HEALTH_TIMEOUT}s)"
# SMARTMATCH_API_BEARER is passed EXPLICITLY EMPTY. This appliance deploys with
# SMARTMATCH_DEV_PRINCIPALS="{}" (docker-compose.vm.yml), so no fixture bearer
# token authenticates here and the health suite must not try to use one: it
# would get a 401, fail the gate, and roll the deployment back to the release
# that still accepted that token. compose_health.sh reads this with
# `${VAR-default}` rather than `${VAR:-default}` precisely so an explicit empty
# value survives instead of falling back to the compose default.
if SMARTMATCH_RELEASE="$DEPLOYED_SHA" \
   SMARTMATCH_API_BEARER="" \
   scripts/compose_health.sh --wait --timeout "$HEALTH_TIMEOUT"; then
  log "health: every check passed against ${DEPLOYED_SHA}"
else
  fail_out "the deployed release did not become healthy"
  compose ps -a || true
  compose logs --no-color --tail=200 || true
  rollback
  exit "$EXIT_FAILED"
fi

# --- 8. done ----------------------------------------------------------------

FAILURE_STAGE=""
OUTCOME="deployed"
record_running_release "$DEPLOYED_SHA"

prune_backups() {
  # Keep the most recent $BACKUP_RETAIN dumps. A 30 GB disk that fills with
  # backups takes the appliance down, which is a worse outcome than losing the
  # oldest dump — and every dump here is of synthetic data.
  local count
  count="$(find "$BACKUP_DIR" -maxdepth 1 -name 'smartmatch-*.sql.gz' | wc -l)"
  if [ "$count" -gt "$BACKUP_RETAIN" ]; then
    log "pruning $((count - BACKUP_RETAIN)) backup(s) beyond the most recent ${BACKUP_RETAIN}"
    find "$BACKUP_DIR" -maxdepth 1 -name 'smartmatch-*.sql.gz' -printf '%T@ %p\n' \
      | sort -n | head -n "$((count - BACKUP_RETAIN))" | cut -d' ' -f2- \
      | xargs -r rm -f
  fi
}
prune_backups

log "=== deployed ${DEPLOYED_SHA} (was ${PREVIOUS_SHA}) ==="
exit "$EXIT_OK"
