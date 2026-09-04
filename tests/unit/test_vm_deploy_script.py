"""Mocked deployment tests for ``scripts/vm/deploy.sh``.

The real script is executed — not a reimplementation of it — against a scratch
git repository with stub ``docker`` and a stub health suite on ``PATH``. That is
the only way to assert the properties that matter here, because every one of
them is about what the script refuses to do:

* it refuses a dirty working tree and a non-fast-forward update, *before*
  anything is rebuilt;
* it takes a backup before it migrates, and refuses to continue without one;
* it holds a lock, so two deployments cannot interleave;
* it rolls the **application** back on failure and never downgrades a
  migration or restores the backup;
* it never removes a volume;
* it redacts credential-shaped text from the deployment log.

Each test drives the script to one of those decisions and asserts on the log,
the metadata file, and the git state it leaves behind. Nothing here touches a
real VM, a real cloud, or a real Docker daemon.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import textwrap
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "vm" / "deploy.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("flock") is None,
    reason="the deployment script needs git and flock, which this platform lacks",
)


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
    echo "${DOCKER_STUB_MIGRATE_EXIT:-0}"
    exit 0
    ;;
  *" build"*)
    exit "${DOCKER_STUB_BUILD_EXIT:-0}"
    ;;
  *"up -d"*)
    exit "${DOCKER_STUB_UP_EXIT:-0}"
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


@pytest.fixture
def vm(tmp_path: Path) -> Iterator[Deployment]:
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

    yield deployment


# --- the happy path ---------------------------------------------------------


def test_a_successful_deployment_fast_forwards_and_reports_the_deployed_sha(
    vm: Deployment,
) -> None:
    result = vm.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert vm.head() == vm.target_sha  # type: ignore[attr-defined]

    metadata = vm.metadata()
    assert metadata["outcome"] == "deployed"
    assert metadata["previous_sha"] == vm.previous_sha  # type: ignore[attr-defined]
    assert metadata["deployed_sha"] == vm.target_sha  # type: ignore[attr-defined]
    assert metadata["rolled_back"] is False


def test_the_health_suite_verifies_the_sha_that_was_actually_checked_out(
    vm: Deployment,
) -> None:
    """The release passed to health is read back from git, not assumed."""
    vm.run()
    assert vm.health_calls == [vm.target_sha]  # type: ignore[attr-defined]


def test_the_running_release_is_recorded_for_the_systemd_unit(vm: Deployment) -> None:
    vm.run()
    recorded = (vm.state / "release.env").read_text(encoding="utf-8")
    assert recorded.strip() == f"SMARTMATCH_RELEASE={vm.target_sha}"  # type: ignore[attr-defined]


def test_images_are_built_before_any_running_service_is_replaced(vm: Deployment) -> None:
    """A failed build must never have stopped the previous release first."""
    vm.run()
    calls = vm.docker_calls
    build = next(index for index, call in enumerate(calls) if call.endswith(" build"))
    up = next(index for index, call in enumerate(calls) if "up -d" in call)
    assert build < up, f"`up` ran before `build`: {calls}"


def test_the_migration_service_runs_exactly_once(vm: Deployment) -> None:
    """One `up`, which compose runs the one-shot migrate service inside.

    Adding a separate `docker compose run migrate` would migrate twice, which
    is the defect this asserts against.
    """
    vm.run()
    ups = [call for call in vm.docker_calls if "up -d" in call]
    runs = [call for call in vm.docker_calls if " run " in call]
    assert len(ups) == 1, f"expected exactly one `up`: {ups}"
    assert not runs, f"a separate migration run would migrate twice: {runs}"


# --- refusals ---------------------------------------------------------------


def test_a_dirty_working_tree_is_refused_before_anything_changes(vm: Deployment) -> None:
    (vm.app / "docker-compose.yml").write_text("services: {tampered: {}}\n", encoding="utf-8")

    result = vm.run()

    assert result.returncode == 2, result.stdout + result.stderr
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]
    assert vm.metadata()["outcome"] == "refused"
    assert not any("build" in call for call in vm.docker_calls)
    assert vm.health_calls == []


def test_a_non_fast_forward_update_is_refused(vm: Deployment) -> None:
    """A force-pushed `deploy` stops the deployment rather than rewriting the VM."""
    # An orphan commit has no parents, so the branch head cannot be a
    # descendant of what the VM has deployed — exactly the shape a history
    # rewrite of a protected branch produces.
    vm.git("checkout", "--quiet", "--orphan", "rewritten", cwd=vm.seed)
    (vm.seed / "marker.txt").write_text("rewritten history", encoding="utf-8")
    vm.git("add", "-A", cwd=vm.seed)
    vm.git("commit", "-m", "rewritten history", cwd=vm.seed)
    vm.git("push", "--quiet", "--force", "origin", "HEAD:deploy", cwd=vm.seed)

    result = vm.run()

    assert result.returncode == 2, result.stdout + result.stderr
    assert "not a descendant" in result.stdout + result.stderr
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]
    assert vm.metadata()["outcome"] == "refused"
    assert not any("build" in call for call in vm.docker_calls)


def test_a_failed_backup_stops_the_deployment_before_the_pull(vm: Deployment) -> None:
    result = vm.run(DOCKER_STUB_PGDUMP_FAIL="1")

    assert result.returncode == 2, result.stdout + result.stderr
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]
    assert vm.backups == [], "a failed dump must not leave a truncated backup file"
    assert not any("build" in call for call in vm.docker_calls)


def test_a_backup_is_taken_before_the_migration(vm: Deployment) -> None:
    vm.run()

    assert len(vm.backups) == 1
    assert vm.backups[0].stat().st_size > 0
    assert vm.previous_sha[:12] in vm.backups[0].name  # type: ignore[attr-defined]

    calls = vm.docker_calls
    dump = next(index for index, call in enumerate(calls) if "pg_dump" in call)
    up = next(index for index, call in enumerate(calls) if "up -d" in call)
    assert dump < up, "the backup must precede the migration"


def test_the_first_deployment_has_nothing_to_back_up(vm: Deployment) -> None:
    """No database container yet is a fact to state, not a reason to refuse."""
    result = vm.run(DOCKER_STUB_DB_EXISTS="0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert vm.backups == []
    assert "nothing to back up" in result.stdout


# --- rollback ---------------------------------------------------------------


def test_an_unhealthy_release_rolls_the_application_back_and_still_fails(
    vm: Deployment,
) -> None:
    result = vm.run(HEALTH_STUB_FAIL_FOR=vm.target_sha)  # type: ignore[attr-defined]

    # The job must fail even though the VM recovered.
    assert result.returncode == 1, result.stdout + result.stderr
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]

    metadata = vm.metadata()
    assert metadata["outcome"] == "failed"
    assert metadata["rolled_back"] is True
    assert metadata["failure_stage"] == "health"

    # Health ran against the new release, then against the restored one.
    assert vm.health_calls == [vm.target_sha, vm.previous_sha]  # type: ignore[attr-defined]


def test_a_failed_migration_rolls_back_and_names_the_forward_only_policy(
    vm: Deployment,
) -> None:
    result = vm.run(DOCKER_STUB_MIGRATE_EXIT="1")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "forward-only" in output
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]
    assert vm.metadata()["rolled_back"] is True


def test_rollback_leaves_the_branch_fast_forwardable(vm: Deployment) -> None:
    """After a rollback the next deployment must still be a fast-forward.

    A rollback that left a detached HEAD, or a branch that had diverged from
    origin, would make the *next* deployment refuse — turning one failed
    release into a VM that no automated deployment can reach.
    """
    vm.run(HEALTH_STUB_FAIL_FOR=vm.target_sha)  # type: ignore[attr-defined]

    branch = vm.git("rev-parse", "--abbrev-ref", "HEAD", cwd=vm.app)
    assert branch == "deploy", "the rollback left the checkout detached"

    second = vm.run()
    assert second.returncode == 0, second.stdout + second.stderr
    assert vm.head() == vm.target_sha  # type: ignore[attr-defined]


def test_rollback_never_downgrades_a_migration_or_restores_the_backup(
    vm: Deployment,
) -> None:
    """Forward-only, asserted on what the script actually invoked."""
    vm.run(HEALTH_STUB_FAIL_FOR=vm.target_sha)  # type: ignore[attr-defined]

    joined = "\n".join(vm.docker_calls)
    assert "downgrade" not in joined
    assert "psql" not in joined
    assert "pg_restore" not in joined
    # The backup taken at the start is still there, untouched, for a human.
    assert len(vm.backups) == 1


def test_no_deployment_path_removes_a_volume(vm: Deployment) -> None:
    """Neither the successful nor the failing path ever runs a destructive down."""
    vm.run(HEALTH_STUB_FAIL_FOR=vm.target_sha)  # type: ignore[attr-defined]

    for call in vm.docker_calls:
        assert " down" not in call, f"the deployment ran a `down`: {call}"
        assert "volume rm" not in call


# --- the lock ---------------------------------------------------------------


def test_deployments_serialize_on_a_lock(vm: Deployment) -> None:
    """A second deployment waits rather than interleaving with the first."""
    lock_file = vm.state / "deploy.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.touch()

    # Hold the lock for longer than the script is willing to wait.
    #
    # start_new_session puts flock and the `sleep` it execs into their own
    # process group, so killing the group takes both. Terminating only the
    # Popen leaves the `sleep` behind as an orphan for the CI runner to reap,
    # which it reports as a warning at the end of the job.
    holder = subprocess.Popen(
        ["flock", str(lock_file), "sleep", "30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        result = vm.run(SMARTMATCH_LOCK_WAIT_SECONDS="2")
    finally:
        os.killpg(os.getpgid(holder.pid), signal.SIGTERM)
        holder.wait(timeout=10)

    assert result.returncode != 0, "the deployment ran while another held the lock"
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]
    assert vm.health_calls == []
    assert not any("build" in call for call in vm.docker_calls)


# --- redaction --------------------------------------------------------------


def test_credential_shaped_text_is_redacted_from_the_deployment_log(
    vm: Deployment,
) -> None:
    """The log is printed by a CI job, so anything token-shaped must not reach it."""
    result = vm.run(DOCKER_STUB_MIGRATE_EXIT="1")

    assert CREDENTIAL_SHAPED_VALUE not in vm.log_text(), (
        "a credential-shaped value reached the deployment log"
    )
    assert CREDENTIAL_SHAPED_VALUE not in result.stdout + result.stderr
    assert "[REDACTED]" in vm.log_text()


def test_a_database_url_with_a_password_is_redacted(vm: Deployment) -> None:
    """The compose DB URL carries an inline password; it must not be logged raw."""
    vm.run(DOCKER_STUB_PGDUMP_FAIL="1")
    log = vm.log_text()
    assert "smartmatch:smartmatch@" not in log


# --- static properties ------------------------------------------------------


def test_the_script_documents_every_exit_code_it_uses() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    for name in ("EXIT_OK", "EXIT_FAILED", "EXIT_REFUSED", "EXIT_PREREQ"):
        assert f"{name}=" in source
    assert "Exit codes:" in source


def test_the_script_never_calls_alembic_directly() -> None:
    """Migrations run through the compose service, which orders them correctly."""
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "alembic" not in code


def test_the_systemd_unit_stops_rather_than_downs() -> None:
    unit = (REPO_ROOT / "scripts" / "vm" / "smartmatch.service").read_text(encoding="utf-8")
    stop = next(line for line in unit.splitlines() if line.startswith("ExecStop="))
    assert stop.rstrip().endswith(" stop"), textwrap.dedent(
        f"""
        The unit's ExecStop must be `docker compose ... stop`. It is:
            {stop}
        `down` removes the containers a restart policy would bring back, and
        `down -v` would discard the pilot database on a reboot.
        """
    )


def test_a_stopped_database_is_started_so_the_backup_can_be_taken(vm: Deployment) -> None:
    """`docker compose exec` needs a running container, not merely an existing one.

    A rebooted VM whose stack was never brought back leaves `db` in `exited`.
    Treating that as "no backup possible" would refuse every deployment — the
    one that would fix the machine included.
    """
    result = vm.run(DOCKER_STUB_DB_STATE="exited", DOCKER_STUB_DB_HEALTH="healthy")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = vm.docker_calls
    start = next(index for index, call in enumerate(calls) if call.endswith("up -d db"))
    dump = next(index for index, call in enumerate(calls) if "pg_dump" in call)
    assert start < dump, "the database must be started before the dump is attempted"
    assert len(vm.backups) == 1


def test_a_database_that_never_becomes_healthy_refuses_the_deployment(
    vm: Deployment,
) -> None:
    result = vm.run(
        DOCKER_STUB_DB_STATE="exited",
        DOCKER_STUB_DB_HEALTH="starting",
        SMARTMATCH_DB_START_ATTEMPTS="1",
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "never reported healthy" in result.stdout + result.stderr
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]
    assert vm.backups == []
    assert not any("build" in call for call in vm.docker_calls)


def test_git_is_given_the_deploy_key() -> None:
    """The VM's git must present the read-only deploy key, or nothing can fetch.

    `bootstrap_vm.sh` sets `GIT_SSH_COMMAND` for its own clone, and git does not
    persist that. Without both halves of this — the export here and the
    `core.sshCommand` written into the clone — every deployment aborts at "git
    fetch failed", which reads like a revoked key rather than a key that was
    never offered. The mocked tests above run against a `file://` origin and so
    cannot catch it; this is why the property is asserted statically.
    """
    deploy_source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert 'export GIT_SSH_COMMAND="ssh -i ${SSH_KEY}' in deploy_source
    assert "IdentitiesOnly=yes" in deploy_source

    bootstrap = (REPO_ROOT / "scripts" / "vm" / "bootstrap_vm.sh").read_text(encoding="utf-8")
    assert "config core.sshCommand" in bootstrap, (
        "bootstrap_vm.sh must persist the key into the clone's own config"
    )
    assert "StrictHostKeyChecking=yes" in deploy_source and (
        "StrictHostKeyChecking=yes" in bootstrap
    ), "host-key checking must stay on; the VM pins github.com via ssh-keyscan at bootstrap"
