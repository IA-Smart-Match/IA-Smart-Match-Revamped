#!/usr/bin/env bash
#
# Bootstrap the synthetic SmartMatch pilot VM (Ubuntu 24.04).
#
# The baseline this is written for is the one the operations notes already
# recommend: instance `smartmatch-pilot`, machine type `e2-medium`, 30 GB disk,
# zone `us-west1-a`. Nothing here creates that instance — a bootstrap script
# that could also provision a VM is a script that provisions a VM by accident.
# Create it with gcloud (the command is in docs/operations/vm-deploy.md), then
# run this on it.
#
#   sudo ./bootstrap_vm.sh                     # prepare the machine
#   sudo ./bootstrap_vm.sh --show-deploy-key   # print the public key again
#   sudo ./bootstrap_vm.sh --check             # validate, install nothing
#
# It is idempotent. A second run installs nothing, regenerates no key, and
# reclones nothing; it reports what is already correct and stops.
#
# ---------------------------------------------------------------------------
# What it installs and creates
# ---------------------------------------------------------------------------
#   * Git, Docker Engine, the Compose v2 plugin, the PostgreSQL 16 client
#     tools, and cloudflared.
#   * A dedicated unprivileged `smartmatch` user in the `docker` group. The
#     appliance and every deployment run as that user; nothing runs as root
#     after this script finishes.
#   * /opt/smartmatch with app/, backups/, logs/, and deployments/.
#   * A read-only GitHub deploy key at /opt/smartmatch/.ssh/id_ed25519. The
#     PRIVATE key never leaves the VM and is never printed. The public half is
#     printed once, for a human to add to the repository as a deploy key
#     WITHOUT write access — read-only is the point: a VM that can push is a
#     VM that can rewrite the branch it deploys from.
#   * A clone that tracks ONLY the protected `deploy` branch.
#   * The smartmatch.service systemd unit, enabled, so the stack comes back
#     after a reboot.
#
# ---------------------------------------------------------------------------
# What it deliberately does NOT do
# ---------------------------------------------------------------------------
#   * It does not write the Cloudflare tunnel token. cloudflared is installed
#     and left unconfigured; the token is supplied out-of-band by an operator
#     (`cloudflared service install <token>`), never committed, never passed
#     through GitHub Actions, and never written to a log. See
#     docs/operations/vm-deploy.md.
#   * It does not open a firewall port and does not enable public SSH. Access
#     is IAP + OS Login for administration and the Cloudflare Tunnel, behind
#     Cloudflare Access, for the application. The compose files publish every
#     port on 127.0.0.1 only.
#   * It does not deploy. The first deployment is scripts/vm/deploy.sh, run
#     the same way every later one is.
#   * It provisions no GCP resource and changes ALLOW_CLOUD_DEPLOY not at all.
#     The instance stays synthetic: SMARTMATCH_EDITION=dev, fixture providers,
#     seeded data, no real user, no live provider credential.

set -uo pipefail

REPO_URL="${SMARTMATCH_REPO_URL:-git@github.com:IA-Smart-Match/IA-Smart-Match-Revamped.git}"
DEPLOY_BRANCH="${SMARTMATCH_DEPLOY_BRANCH:-deploy}"
RUNTIME_USER="${SMARTMATCH_RUNTIME_USER:-smartmatch}"
STATE_DIR="${SMARTMATCH_STATE_DIR:-/opt/smartmatch}"
APP_DIR="${SMARTMATCH_APP_DIR:-${STATE_DIR}/app}"
SSH_DIR="${STATE_DIR}/.ssh"
DEPLOY_KEY="${SSH_DIR}/id_ed25519"
UNIT_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/smartmatch.service"

CHECK_ONLY=0
SHOW_KEY_ONLY=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --show-deploy-key) SHOW_KEY_ONLY=1 ;;
    -h|--help) sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { warn "$*"; exit 1; }

show_deploy_key() {
  [ -f "${DEPLOY_KEY}.pub" ] || die "no deploy key at ${DEPLOY_KEY}.pub — run this script without --show-deploy-key first."
  say ""
  say "Add this PUBLIC key to the repository as a deploy key with READ-ONLY access"
  say "(GitHub -> Settings -> Deploy keys -> Add deploy key; leave 'Allow write access' UNCHECKED):"
  say ""
  cat "${DEPLOY_KEY}.pub"
  say ""
}

if [ "$SHOW_KEY_ONLY" -eq 1 ]; then
  show_deploy_key
  exit 0
fi

[ "$(id -u)" -eq 0 ] || die "this script must run as root (sudo ./bootstrap_vm.sh). Everything it creates then runs as the unprivileged '${RUNTIME_USER}' user."

MISSING=()
NOTES=()
note() { NOTES+=("$1"); }

apt_updated=0
apt_update_once() {
  [ "$apt_updated" -eq 1 ] && return 0
  apt-get update -qq && apt_updated=1
}
apt_install() {
  apt_update_once || return 1
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
}

# --- packages ---------------------------------------------------------------

ensure_base_packages() {
  local wanted=(git curl ca-certificates gnupg jq)
  local absent=()
  local package
  for package in "${wanted[@]}"; do
    dpkg -s "$package" >/dev/null 2>&1 || absent+=("$package")
  done
  if [ "${#absent[@]}" -eq 0 ]; then
    say "base packages: present"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("${absent[*]}"); return 1; fi
  say "installing: ${absent[*]}"
  apt_install "${absent[@]}" || MISSING+=("${absent[*]}")
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    say "docker: $(docker --version), compose $(docker compose version --short)"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("docker engine + compose v2"); return 1; fi

  say "installing Docker Engine and the Compose v2 plugin"
  install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.asc ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
      || { MISSING+=("docker"); return 1; }
    chmod a+r /etc/apt/keyrings/docker.asc
  fi
  local codename line
  codename="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  line="deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable"
  if ! grep -qsF "$line" /etc/apt/sources.list.d/docker.list 2>/dev/null; then
    printf '%s\n' "$line" > /etc/apt/sources.list.d/docker.list
    apt_updated=0
  fi
  apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
    || { MISSING+=("docker"); return 1; }
  systemctl enable --now docker >/dev/null 2>&1 || note "could not enable docker.service; check 'systemctl status docker'"
  say "docker: $(docker --version)"
}

ensure_postgres_client() {
  if command -v psql >/dev/null 2>&1; then
    say "postgres client: $(psql --version)"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("postgresql-client-16"); return 1; fi
  say "installing the PostgreSQL client tools"
  # Used for hand inspection on the VM. Deployment backups run pg_dump INSIDE
  # the db container (see scripts/vm/deploy.sh), so the dump is always taken by
  # a client whose version matches the server.
  apt_install postgresql-client-16 || apt_install postgresql-client || MISSING+=("postgresql-client")
}

ensure_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    say "cloudflared: $(cloudflared --version 2>&1 | head -n1)"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("cloudflared"); return 1; fi

  say "installing cloudflared from Cloudflare's apt repository"
  install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/cloudflare-main.gpg ]; then
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
      -o /etc/apt/keyrings/cloudflare-main.gpg || { MISSING+=("cloudflared"); return 1; }
    chmod a+r /etc/apt/keyrings/cloudflare-main.gpg
  fi
  local line="deb [signed-by=/etc/apt/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main"
  if ! grep -qsF "$line" /etc/apt/sources.list.d/cloudflared.list 2>/dev/null; then
    printf '%s\n' "$line" > /etc/apt/sources.list.d/cloudflared.list
    apt_updated=0
  fi
  apt_install cloudflared || { MISSING+=("cloudflared"); return 1; }

  note "cloudflared is installed but NOT configured. Supply the named tunnel's token out-of-band and run 'sudo cloudflared service install <token>' on this VM. The token must never be committed, never passed through GitHub Actions, and never echoed into a log. Point the tunnel at http://127.0.0.1:5173 and require Cloudflare Access in front of it — the appliance has no login of its own."
}

# --- user, directories, key -------------------------------------------------

ensure_runtime_user() {
  if id "$RUNTIME_USER" >/dev/null 2>&1; then
    say "user: ${RUNTIME_USER} exists"
  else
    if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("user ${RUNTIME_USER}"); return 1; fi
    say "creating the ${RUNTIME_USER} system user"
    useradd --system --create-home --home-dir "/home/${RUNTIME_USER}" \
            --shell /usr/sbin/nologin "$RUNTIME_USER" \
      || { MISSING+=("user ${RUNTIME_USER}"); return 1; }
  fi

  if id -nG "$RUNTIME_USER" | tr ' ' '\n' | grep -qx docker; then
    say "user: ${RUNTIME_USER} is in the docker group"
  elif [ "$CHECK_ONLY" -eq 0 ]; then
    usermod -aG docker "$RUNTIME_USER" && say "added ${RUNTIME_USER} to the docker group"
  else
    MISSING+=("${RUNTIME_USER} in the docker group")
  fi
}

ensure_directories() {
  local directory
  for directory in "$STATE_DIR" "$STATE_DIR/backups" "$STATE_DIR/logs" "$STATE_DIR/deployments" "$SSH_DIR"; do
    if [ -d "$directory" ]; then
      say "directory: ${directory}"
    elif [ "$CHECK_ONLY" -eq 1 ]; then
      MISSING+=("$directory")
      continue
    else
      install -d -o "$RUNTIME_USER" -g "$RUNTIME_USER" -m 0750 "$directory" \
        && say "created ${directory}" || MISSING+=("$directory")
    fi
  done
  [ "$CHECK_ONLY" -eq 1 ] || chmod 0700 "$SSH_DIR" 2>/dev/null || true
}

ensure_deploy_key() {
  if [ -f "$DEPLOY_KEY" ]; then
    say "deploy key: present (not regenerated — regenerating would silently break the clone)"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("deploy key at ${DEPLOY_KEY}"); return 1; fi

  say "generating a read-only GitHub deploy key"
  sudo -u "$RUNTIME_USER" ssh-keygen -t ed25519 -N '' -C "smartmatch-pilot-vm" -f "$DEPLOY_KEY" >/dev/null \
    || { MISSING+=("deploy key"); return 1; }
  chmod 0600 "$DEPLOY_KEY"

  sudo -u "$RUNTIME_USER" bash -c "ssh-keyscan -t ed25519 github.com >> '${SSH_DIR}/known_hosts' 2>/dev/null" || true
  chown "$RUNTIME_USER:$RUNTIME_USER" "${SSH_DIR}/known_hosts" 2>/dev/null || true

  note "The deploy key was just generated. Nothing can clone until its PUBLIC half is added to the repository as a READ-ONLY deploy key. Run 'sudo ./bootstrap_vm.sh --show-deploy-key' to print it again."
  show_deploy_key
}

# --- clone ------------------------------------------------------------------

git_as_runtime() {
  sudo -u "$RUNTIME_USER" \
    env GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o UserKnownHostsFile=${SSH_DIR}/known_hosts" \
    git "$@"
}

ensure_clone() {
  if [ -d "${APP_DIR}/.git" ]; then
    say "clone: ${APP_DIR} exists"
    local branch
    branch="$(git_as_runtime -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null)"
    say "clone: on branch '${branch:-unknown}'"
    [ "$branch" = "$DEPLOY_BRANCH" ] \
      || note "the clone is on '${branch}', not '${DEPLOY_BRANCH}'. scripts/vm/deploy.sh only fast-forwards '${DEPLOY_BRANCH}'."
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("clone at ${APP_DIR}"); return 1; fi

  say "cloning ${REPO_URL} (branch ${DEPLOY_BRANCH} only)"
  # --single-branch is not cosmetic: the VM must be unable to check out `main`
  # or a feature branch by accident. It tracks the one protected branch, and
  # scripts/vm/deploy.sh only ever fast-forwards that branch.
  if ! git_as_runtime clone --branch "$DEPLOY_BRANCH" --single-branch "$REPO_URL" "$APP_DIR"; then
    MISSING+=("clone")
    warn "The clone failed. The usual cause is that the deploy key's public half has"
    warn "not been added to the repository yet. 'sudo ./bootstrap_vm.sh --show-deploy-key'"
    warn "prints it; add it with READ-ONLY access, then re-run this script."
    return 1
  fi
  chown -R "$RUNTIME_USER:$RUNTIME_USER" "$APP_DIR"

  # git does not persist GIT_SSH_COMMAND from the clone, so a later `git fetch`
  # in this directory would offer no identity and fail with "Permission denied
  # (publickey)". Writing it into the clone's own config is what makes a
  # hand-run fetch work the same way the deployment's does.
  git_as_runtime -C "$APP_DIR" config core.sshCommand \
    "ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o UserKnownHostsFile=${SSH_DIR}/known_hosts -o StrictHostKeyChecking=yes"
}

# --- systemd ----------------------------------------------------------------

ensure_systemd_unit() {
  local target=/etc/systemd/system/smartmatch.service
  local source="$UNIT_SOURCE"
  [ -f "$source" ] || source="${APP_DIR}/scripts/vm/smartmatch.service"

  if [ ! -f "$source" ]; then
    [ "$CHECK_ONLY" -eq 1 ] && MISSING+=("smartmatch.service source")
    warn "cannot find smartmatch.service to install (looked in ${UNIT_SOURCE} and ${APP_DIR}/scripts/vm/)"
    return 1
  fi

  if [ -f "$target" ] && cmp -s "$source" "$target"; then
    say "systemd: smartmatch.service already installed and current"
  elif [ "$CHECK_ONLY" -eq 1 ]; then
    MISSING+=("smartmatch.service installed at ${target}")
    return 1
  else
    say "installing ${target}"
    install -m 0644 "$source" "$target" || { MISSING+=("smartmatch.service"); return 1; }
    systemctl daemon-reload
  fi

  if systemctl is-enabled smartmatch.service >/dev/null 2>&1; then
    say "systemd: smartmatch.service is enabled"
  elif [ "$CHECK_ONLY" -eq 0 ]; then
    systemctl enable smartmatch.service >/dev/null 2>&1 \
      && say "systemd: smartmatch.service enabled (starts after docker.service on every boot)" \
      || MISSING+=("smartmatch.service enabled")
  else
    MISSING+=("smartmatch.service enabled")
  fi
}

# --- run --------------------------------------------------------------------

say "SmartMatch pilot VM bootstrap"
say "state dir: ${STATE_DIR}"
say "branch:    ${DEPLOY_BRANCH}"
[ "$CHECK_ONLY" -eq 1 ] && say "mode: --check (validating only; nothing will be installed)"
say ""

ensure_base_packages
ensure_docker
ensure_postgres_client
ensure_cloudflared
ensure_runtime_user
ensure_directories
ensure_deploy_key
ensure_clone
ensure_systemd_unit

if [ "${#NOTES[@]}" -gt 0 ]; then
  say ""
  say "== read these =="
  for entry in "${NOTES[@]}"; do
    printf '  * %s\n' "$entry"
  done
fi

if [ "${#MISSING[@]}" -gt 0 ]; then
  say ""
  warn "not complete:"
  for entry in "${MISSING[@]}"; do
    printf '  - %s\n' "$entry" >&2
  done
  exit 1
fi

say ""
if [ "$CHECK_ONLY" -eq 1 ]; then
  say "the VM is bootstrapped."
else
  say "bootstrap complete. Remaining, both by hand and both deliberate:"
  say "  1. Add the deploy key's public half to the repository, READ-ONLY."
  say "  2. Install the Cloudflare tunnel with its token, out-of-band, and put"
  say "     Cloudflare Access in front of it."
  say ""
  say "Then the first deployment, exactly like every later one:"
  say "  sudo -u ${RUNTIME_USER} ${APP_DIR}/scripts/vm/deploy.sh"
fi
