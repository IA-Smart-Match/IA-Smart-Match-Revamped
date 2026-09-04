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
LOCK_FILE="${SMARTMATCH_LOCK_FILE:-${STATE_DIR}/deploy.lock}"
DEPLOY_BRANCH="${SMARTMATCH_DEPLOY_BRANCH:-deploy}"
LOCK_WAIT_SECONDS="${SMARTMATCH_LOCK_WAIT_SECONDS:-1800}"
HEALTH_TIMEOUT="${SMARTMATCH_HEALTH_TIMEOUT:-900}"
BACKUP_RETAIN="${SMARTMATCH_BACKUP_RETAIN:-14}"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.vm.yml)
DB_URL="postgresql://smartmatch:smartmatch@localhost:5432/smartmatch"

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

log "=== SmartMatch VM deployment ${STAMP} ==="
log "app dir:  ${APP_DIR}"
log "branch:   ${DEPLOY_BRANCH}"
log "log file: ${LOG_FILE}"

# --- metadata ---------------------------------------------------------------

PREVIOUS_SHA=""
DEPLOYED_SHA=""
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

record_running_release() {
  # The systemd unit reads this file, so a reboot brings the stack back
  # reporting the SHA it is actually running rather than the `vm-unknown`
  # default. Written on success and after a rollback, because after a rollback
  # the running release is the previous SHA and the file must say so.
  printf 'SMARTMATCH_RELEASE=%s\n' "$1" > "${STATE_DIR}/release.env" 2>/dev/null \
    || log "warning: could not write ${STATE_DIR}/release.env"
}

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

if compose ps -a --format '{{.State}}' db 2>/dev/null | grep -q .; then
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
else
  log "no database container yet — this is the first deployment, so there is nothing to back up"
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
  log "building images for $(git rev-parse HEAD)"
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
    return 1
  fi
  return 0
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
  if ! deploy_current_checkout; then
    fail_out "the previous release could not be rebuilt. The VM needs a human."
    FAILURE_STAGE="$stage"
    return
  fi

  if SMARTMATCH_RELEASE="$PREVIOUS_SHA" \
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
if SMARTMATCH_RELEASE="$DEPLOYED_SHA" \
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
