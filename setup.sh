#!/usr/bin/env bash
#
# First-time prerequisite setup for Ubuntu 24.04 and WSL.
#
# Run this once on a new machine, then use ./smartmatch.sh for everything else.
# It installs only what the appliance needs and validates whatever is already
# there; it is safe to re-run, and a second run should install nothing.
#
#   ./setup.sh                 Git, Docker Engine, Compose v2, curl
#   ./setup.sh --developer     ...plus Python 3.11 + venv, Node 22, Make
#   ./setup.sh --check         Validate only. Installs nothing, exits nonzero
#                              if a prerequisite is missing.
#
# ---------------------------------------------------------------------------
# What it deliberately does not do
# ---------------------------------------------------------------------------
#   * It never writes .env. If one exists it is left untouched; if none exists
#     it stays absent, because docker-compose.yml runs on its own defaults and
#     an .env is only needed for the optional pilot logins. A setup script that
#     overwrote an .env would destroy exactly the file that is never in version
#     control and never recoverable.
#   * It installs no application dependency. Docker Compose is the runtime
#     dependency installer for this project — PostgreSQL 16, the Python service
#     dependencies, the migrations, the seed data, the scheduler, and the
#     frontend's `npm ci` all happen inside containers. The --developer half
#     exists for running the gates on the host, not for running the app.
#   * It provisions nothing outside this machine.
#
# Adding your user to the `docker` group takes effect on the next login. That
# is reported loudly at the end rather than papered over, because the failure
# it causes — "permission denied while trying to connect to the Docker daemon
# socket" immediately after a successful setup — otherwise looks like a broken
# install.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DEVELOPER=0
CHECK_ONLY=0

NODE_MAJOR=22        # .nvmrc
PYTHON_SERIES=3.11   # .python-version, and both container images

while [ "$#" -gt 0 ]; do
  case "$1" in
    --developer) DEVELOPER=1 ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }

MISSING=()
NOTES=()

note() { NOTES+=("$1"); }

is_wsl() { grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; }

need_sudo() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    warn "this step needs root and sudo is not available: $*"
    return 1
  fi
}

apt_updated=0
apt_update_once() {
  [ "$apt_updated" -eq 1 ] && return 0
  need_sudo apt-get update -qq || return 1
  apt_updated=1
}

apt_install() {
  apt_update_once || return 1
  need_sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
}

# --- validators -------------------------------------------------------------
#
# Each `ensure_*` reports what is present, installs it when it is not and we
# are not in --check mode, and records the gap in MISSING when it cannot.

ensure_git() {
  if command -v git >/dev/null 2>&1; then
    say "git: $(git --version)"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("git"); return 1; fi
  say "installing git..."
  apt_install git && say "git: $(git --version)" || MISSING+=("git")
}

ensure_curl() {
  if command -v curl >/dev/null 2>&1; then
    say "curl: present"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("curl"); return 1; fi
  say "installing curl and ca-certificates..."
  apt_install curl ca-certificates || MISSING+=("curl")
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    say "docker: $(docker --version)"
    say "compose: $(docker compose version --short 2>/dev/null || echo 'v2 plugin present')"
    ensure_docker_usable
    return 0
  fi

  if [ "$CHECK_ONLY" -eq 1 ]; then
    command -v docker >/dev/null 2>&1 || MISSING+=("docker")
    docker compose version >/dev/null 2>&1 || MISSING+=("docker compose v2 plugin")
    return 1
  fi

  if is_wsl && ! command -v docker >/dev/null 2>&1; then
    note "This looks like WSL. If you use Docker Desktop on Windows, do NOT install Docker Engine here — enable WSL integration in Docker Desktop's settings instead, and re-run this script. Continuing will install Docker Engine inside this distro, which is the correct choice only if you are not using Docker Desktop."
  fi

  say "installing Docker Engine and the Compose v2 plugin from Docker's own apt repository..."
  ensure_curl
  need_sudo install -m 0755 -d /etc/apt/keyrings || { MISSING+=("docker"); return 1; }
  if [ ! -f /etc/apt/keyrings/docker.asc ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | need_sudo tee /etc/apt/keyrings/docker.asc >/dev/null \
      || { MISSING+=("docker"); return 1; }
    need_sudo chmod a+r /etc/apt/keyrings/docker.asc
  fi

  local codename
  codename="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  local line="deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable"
  if ! grep -qsF "$line" /etc/apt/sources.list.d/docker.list 2>/dev/null; then
    printf '%s\n' "$line" | need_sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    apt_updated=0   # the new source has to be read before the install below
  fi

  apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
    || { MISSING+=("docker"); return 1; }

  say "docker: $(docker --version)"
  ensure_docker_usable
}

ensure_docker_usable() {
  # Being in the `docker` group is what makes `docker` work without sudo, and
  # the membership only takes effect at the next login. Reporting that is the
  # whole point: the error it produces looks like a failed install.
  if docker info >/dev/null 2>&1; then
    say "docker daemon: reachable"
    return 0
  fi

  if [ "$(id -u)" -eq 0 ]; then
    note "The Docker daemon is not answering. On a systemd host: 'systemctl start docker'. On WSL without systemd: 'sudo service docker start', or enable Docker Desktop's WSL integration."
    return 1
  fi

  if ! id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
    if [ "$CHECK_ONLY" -eq 0 ]; then
      say "adding ${USER} to the 'docker' group..."
      need_sudo usermod -aG docker "$USER" || true
    fi
    note "RE-LOGIN REQUIRED: ${USER} was added to the 'docker' group, which takes effect on your next login. Log out and back in (WSL: run 'wsl --shutdown' from Windows), or use 'newgrp docker' in this shell. Until then 'docker' fails with a permission-denied on /var/run/docker.sock, which is not a broken install."
  else
    note "You are in the 'docker' group but the daemon is not answering. Start it: 'sudo systemctl start docker', or on WSL without systemd 'sudo service docker start'."
  fi
  return 1
}

ensure_python() {
  local found=""
  if command -v "python${PYTHON_SERIES}" >/dev/null 2>&1; then
    found="python${PYTHON_SERIES}"
  elif command -v python3 >/dev/null 2>&1; then
    local series
    series="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
    case "$series" in
      3.11|3.12) found=python3 ;;
      *) note "python3 is ${series:-unreadable}; pyproject.toml requires >=3.11,<3.13, so 3.13 does not work. Installing python${PYTHON_SERIES} alongside it." ;;
    esac
  fi

  if [ -n "$found" ] && "$found" -c 'import venv' >/dev/null 2>&1; then
    say "python: $("$found" --version) with venv"
    return 0
  fi

  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("python${PYTHON_SERIES} and python3-venv"); return 1; fi

  say "installing python${PYTHON_SERIES}, its venv module, and pip..."
  # python3-venv is a separate package on Debian/Ubuntu, and its absence is the
  # single most common first-run failure in this repository.
  apt_install "python${PYTHON_SERIES}" "python${PYTHON_SERIES}-venv" python3-pip \
    || apt_install python3 python3-venv python3-pip \
    || { MISSING+=("python${PYTHON_SERIES}"); return 1; }
  say "python: $(python3 --version)"
}

ensure_node() {
  if command -v node >/dev/null 2>&1; then
    local major
    major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null)"
    if [ "${major:-0}" -ge 20 ]; then
      say "node: v$(node -p 'process.versions.node')"
      command -v npm >/dev/null 2>&1 && { say "npm: $(npm --version)"; return 0; }
    else
      note "node is v${major}; .nvmrc pins ${NODE_MAJOR} and the frontend needs >=20. Installing Node ${NODE_MAJOR}."
    fi
  fi

  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("node >= 20 (.nvmrc pins ${NODE_MAJOR})"); return 1; fi

  say "installing Node ${NODE_MAJOR} from NodeSource..."
  ensure_curl
  # No `-E`: need_sudo runs its arguments directly when already root, and
  # `-E` is only meaningful to sudo — as a command it is "not found", which
  # would surface as a missing Node rather than as a broken install line. The
  # NodeSource script needs nothing from the caller's environment.
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | need_sudo bash - \
    || { MISSING+=("node"); return 1; }
  apt_updated=0
  apt_install nodejs || { MISSING+=("node"); return 1; }
  say "node: v$(node -p 'process.versions.node')"
}

ensure_make() {
  if command -v make >/dev/null 2>&1; then
    say "make: $(make --version | head -n1)"
    return 0
  fi
  if [ "$CHECK_ONLY" -eq 1 ]; then MISSING+=("make"); return 1; fi
  say "installing make..."
  apt_install make || MISSING+=("make")
}

# --- the .env rule ----------------------------------------------------------

report_env_file() {
  if [ -f "${REPO_ROOT}/.env" ]; then
    say ".env: present — left exactly as it is. Nothing in this script writes to it."
  else
    say ".env: absent, which is fine. docker-compose.yml runs on its own defaults."
    say "      Copy .env.example to .env only if you want the optional pilot logins."
  fi
}

# --- run --------------------------------------------------------------------

say "SmartMatch prerequisite setup"
say "repository: ${REPO_ROOT}"
if [ "$CHECK_ONLY" -eq 1 ]; then
  say "mode: --check (validating only; nothing will be installed)"
elif [ "$DEVELOPER" -eq 1 ]; then
  say "mode: --developer (appliance prerequisites plus the host toolchain)"
else
  say "mode: appliance prerequisites only"
fi
is_wsl && say "environment: WSL"
say ""

if ! command -v apt-get >/dev/null 2>&1 && [ "$CHECK_ONLY" -eq 0 ]; then
  warn "This script installs packages with apt-get and so is written for Ubuntu 24.04"
  warn "and Debian-family WSL distributions. On anything else, run './setup.sh --check'"
  warn "to see what is missing and install those packages your own way."
  exit 2
fi

ensure_git
ensure_curl
ensure_docker

if [ "$DEVELOPER" -eq 1 ]; then
  say ""
  say "-- developer toolchain --"
  ensure_python
  ensure_node
  ensure_make
fi

say ""
report_env_file

if [ "${#NOTES[@]}" -gt 0 ]; then
  say ""
  say "== read these =="
  for entry in "${NOTES[@]}"; do
    printf '  * %s\n' "$entry"
  done
fi

if [ "${#MISSING[@]}" -gt 0 ]; then
  say ""
  warn "missing prerequisites:"
  for entry in "${MISSING[@]}"; do
    printf '  - %s\n' "$entry" >&2
  done
  exit 1
fi

say ""
if [ "$CHECK_ONLY" -eq 1 ]; then
  say "every prerequisite is present."
else
  say "setup complete. Next:"
  say "  ./smartmatch.sh install              start the appliance"
  say "  ./smartmatch.sh install --developer  ...and install the host toolchain"
fi
