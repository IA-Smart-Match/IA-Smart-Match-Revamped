"""Shared harness for the mocked ``scripts/vm/deploy.sh`` tests.

A scratch "VM" — an origin, a checkout, a state directory — plus a stub
``docker`` and a stub health suite. The real deployment script is executed
against it; see ``test_vm_deploy_script.py`` for why.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "vm" / "deploy.sh"


# --- the stubs --------------------------------------------------------------

#: A value shaped like a real credential: long, mixed-case, alphanumeric. The
#: stub `docker` prints it in container logs so the redaction test has
#: something the filter must actually catch, rather than a short placeholder
#: any regular expression would miss for the wrong reason.
CREDENTIAL_SHAPED_VALUE = "abcdefgh12345678ABCDEFGH"

DOCKER_STUB = r"""#!/usr/bin/env bash
# Stub `docker` for the deployment tests. Records every invocation and answers
# the handful of `docker compose` reads scripts/vm/deploy.sh performs.
printf '%s\n' "$*" >> "$DOCKER_STUB_LOG"
all="$*"

# The migrate one-shot fails for the release named in
# DOCKER_STUB_MIGRATE_FAIL_FOR — the way the real one does when the checkout's
# db/ tree lacks the revision the database is at — unless this invocation
# carries the rollback's skip-migrate override file.
migrate_blocked=0
if [ -n "${DOCKER_STUB_MIGRATE_FAIL_FOR:-}" ] \
   && [ "${SMARTMATCH_RELEASE:-}" = "${DOCKER_STUB_MIGRATE_FAIL_FOR}" ]; then
  case "$all" in
    *rollback-skip-migrate*) : ;;
    *) migrate_blocked=1 ;;
  esac
fi

case "$all" in
  *"exec -T db pg_dump"*)
    if [ "${DOCKER_STUB_PGDUMP_FAIL:-0}" = "1" ]; then
      echo "pg_dump: connection refused" >&2
      exit 1
    fi
    echo "-- synthetic dump"
    exit 0
    ;;
  *"ps -a --format {{.State}} db"*)
    [ "${DOCKER_STUB_DB_EXISTS:-1}" = "1" ] && echo "${DOCKER_STUB_DB_STATE:-running}"
    exit 0
    ;;
  *"ps -a --format {{.Health}} db"*)
    echo "${DOCKER_STUB_DB_HEALTH:-healthy}"
    exit 0
    ;;
  *"ps -a --format {{.State}} migrate"*)
    echo "${DOCKER_STUB_MIGRATE_STATE:-exited}"
    exit 0
    ;;
  *"ps -a --format {{.ExitCode}} migrate"*)
    if [ "$migrate_blocked" = "1" ]; then
      echo 255
      exit 0
    fi
    echo "${DOCKER_STUB_MIGRATE_EXIT:-0}"
    exit 0
    ;;
  *"ps -a --format {{.State}} seed-logins"*)
    echo "${DOCKER_STUB_SEED_LOGINS_STATE:-exited}"
    exit 0
    ;;
  *"ps -a --format {{.ExitCode}} seed-logins"*)
    echo "${DOCKER_STUB_SEED_LOGINS_EXIT:-0}"
    exit 0
    ;;
  *" build"*)
    exit "${DOCKER_STUB_BUILD_EXIT:-0}"
    ;;
  *"up -d db")
    exit "${DOCKER_STUB_UP_EXIT:-0}"
    ;;
  *"up -d"*)
    # Real compose exits non-zero when a service another one waits on with
    # `service_completed_successfully` did not complete successfully.
    [ "$migrate_blocked" = "1" ] && exit 1
    exit "${DOCKER_STUB_UP_EXIT:-0}"
    ;;
  *"logs"*" migrate")
    printf '%s\n' "${DOCKER_STUB_MIGRATE_LOG-migrate-1  | (no output)}"
    echo "migrate-1  | SMARTMATCH_DEV_TASK_TOKEN=__CREDENTIAL_SHAPED_VALUE__"
    exit 0
    ;;
  *"logs"*)
    # Deliberately emits credential-shaped text, so the redaction filter has
    # something real to catch.
    echo "worker | authorization: Bearer __CREDENTIAL_SHAPED_VALUE__"
    echo "worker | SMARTMATCH_DEV_TASK_TOKEN=__CREDENTIAL_SHAPED_VALUE__"
    exit 0
    ;;
  *"ps -a"*)
    echo "NAME STATE"
    exit 0
    ;;
esac
exit 0
"""

HEALTH_STUB = r"""#!/usr/bin/env bash
# Stub health suite. Records the release it was asked to verify and fails for
# any release named in HEALTH_STUB_FAIL_FOR.
printf '%s\n' "${SMARTMATCH_RELEASE:-none}" >> "$HEALTH_STUB_LOG"
case " $* " in
  *" --json "*)
    # One pass in the real suite's `--json` shape (scripts/compose_health.sh,
    # emit_json). HEALTH_STUB_JSON_FAILING names the checks that fail.
    printf '{"healthy":false,"release_expected":"%s","checks":[' "${SMARTMATCH_RELEASE:-}"
    first=1
    for id in db-healthy migrations-at-head migrate-exited-ok api-health; do
      status=pass
      detail=ok
      for bad in ${HEALTH_STUB_JSON_FAILING:-}; do
        [ "$bad" = "$id" ] && status=fail && detail="not ok"
      done
      if [ "$id" = "migrations-at-head" ] && [ "$status" = "fail" ]; then
        detail="alembic_version='${HEALTH_STUB_DB_REVISION:-}' but head is '0001_base'"
      fi
      [ "$first" = "1" ] || printf ','
      first=0
      printf '{"id":"%s","status":"%s","detail":"%s"}' "$id" "$status" "$detail"
    done
    printf ']}\n'
    [ -z "${HEALTH_STUB_JSON_FAILING:-}" ]
    exit
    ;;
esac
for bad in ${HEALTH_STUB_FAIL_FOR:-}; do
  if [ "$bad" = "${SMARTMATCH_RELEASE:-}" ]; then
    echo "health: FAILED"
    exit 1
  fi
done
echo "health: all checks passed"
exit 0
"""


class Deployment:
    """A scratch VM: an origin, a checkout, stub tooling, and a state dir."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.origin = root / "origin.git"
        self.seed = root / "seed"
        self.state = root / "state"
        self.app = self.state / "app"
        self.bin = root / "bin"
        self.docker_log = root / "docker.log"
        self.health_log = root / "health.log"

    # -- git helpers --------------------------------------------------------

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Deployment Test",
                "-c",
                "user.email=deploy-test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=cwd or self.root,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig")},
        )
        return result.stdout.strip()

    def head(self, cwd: Path | None = None) -> str:
        return self.git("rev-parse", "HEAD", cwd=cwd or self.app)

    def push_commit(self, message: str, marker: str) -> str:
        (self.seed / "marker.txt").write_text(marker, encoding="utf-8")
        self.git("add", "-A", cwd=self.seed)
        self.git("commit", "-m", message, cwd=self.seed)
        self.git("push", "--quiet", "origin", "deploy", cwd=self.seed)
        return self.head(cwd=self.seed)

    # -- running ------------------------------------------------------------

    def run(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
            "SMARTMATCH_STATE_DIR": str(self.state),
            "SMARTMATCH_APP_DIR": str(self.app),
            "SMARTMATCH_DEPLOY_BRANCH": "deploy",
            "SMARTMATCH_LOCK_WAIT_SECONDS": "5",
            "SMARTMATCH_HEALTH_TIMEOUT": "5",
            "DOCKER_STUB_LOG": str(self.docker_log),
            "HEALTH_STUB_LOG": str(self.health_log),
        }
        environment.pop("SMARTMATCH_RELEASE", None)
        environment.pop("SMARTMATCH_DEPLOY_LOCK_HELD", None)
        environment.update(overrides)
        return subprocess.run(
            [str(DEPLOY_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            timeout=180,
        )

    # -- reading the result -------------------------------------------------

    @property
    def docker_calls(self) -> list[str]:
        if not self.docker_log.exists():
            return []
        return self.docker_log.read_text(encoding="utf-8").splitlines()

    @property
    def health_calls(self) -> list[str]:
        if not self.health_log.exists():
            return []
        return self.health_log.read_text(encoding="utf-8").splitlines()

    @property
    def backups(self) -> list[Path]:
        directory = self.state / "backups"
        return sorted(directory.glob("smartmatch-*.sql.gz")) if directory.is_dir() else []

    def metadata(self) -> Mapping[str, object]:
        files = sorted((self.state / "deployments").glob("deploy-*.json"))
        assert files, "the deployment wrote no metadata"
        return json.loads(files[-1].read_text(encoding="utf-8"))

    def log_text(self) -> str:
        files = sorted((self.state / "logs").glob("deploy-*.log"))
        assert files, "the deployment wrote no log"
        return files[-1].read_text(encoding="utf-8")


def make_deployment(tmp_path: Path) -> Deployment:
    """A scratch deployment target with one commit deployed and one to deploy."""
    deployment = Deployment(tmp_path)
    deployment.root.mkdir(exist_ok=True)
    deployment.bin.mkdir()

    docker = deployment.bin / "docker"
    docker.write_text(
        DOCKER_STUB.replace("__CREDENTIAL_SHAPED_VALUE__", CREDENTIAL_SHAPED_VALUE),
        encoding="utf-8",
    )
    docker.chmod(0o755)

    # origin, and a working clone to push from
    deployment.git("init", "--bare", "--initial-branch=deploy", str(deployment.origin))
    deployment.git("clone", "--quiet", str(deployment.origin), str(deployment.seed))

    scripts = deployment.seed / "scripts"
    scripts.mkdir()
    health = scripts / "compose_health.sh"
    health.write_text(HEALTH_STUB, encoding="utf-8")
    health.chmod(0o755)
    (deployment.seed / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (deployment.seed / "docker-compose.vm.yml").write_text("services: {}\n", encoding="utf-8")
    deployment.git("add", "-A", cwd=deployment.seed)
    deployment.git("commit", "-m", "base", cwd=deployment.seed)
    deployment.git("push", "--quiet", "-u", "origin", "deploy", cwd=deployment.seed)

    # the VM's checkout, at the commit that is currently "deployed"
    deployment.state.mkdir()
    deployment.git(
        "clone",
        "--quiet",
        "--branch",
        "deploy",
        "--single-branch",
        str(deployment.origin),
        str(deployment.app),
    )
    deployment.previous_sha = deployment.head()  # type: ignore[attr-defined]

    # and the commit this deployment should fast-forward to
    deployment.target_sha = deployment.push_commit("next release", "v2")  # type: ignore[attr-defined]

    return deployment


def up_calls(vm: Deployment) -> list[str]:
    return [call for call in vm.docker_calls if "up -d --remove-orphans" in call]
