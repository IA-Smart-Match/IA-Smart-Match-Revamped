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

import os
import shutil
import signal
import subprocess
import textwrap
from pathlib import Path

import pytest

from tests.unit.vm_deploy_harness import (
    CREDENTIAL_SHAPED_VALUE,
    DEPLOY_SCRIPT,
    REPO_ROOT,
    Deployment,
    make_deployment,
    up_calls,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("flock") is None,
    reason="the deployment script needs git and flock, which this platform lacks",
)


@pytest.fixture
def vm(tmp_path: Path) -> Deployment:
    """A scratch deployment target with one commit deployed and one to deploy."""
    return make_deployment(tmp_path)


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


def test_a_failed_seed_logins_rolls_back_and_fails_the_deployment(
    vm: Deployment,
) -> None:
    """seed-logins is outside migrate's reach; a non-zero exit must still fail."""
    result = vm.run(DOCKER_STUB_SEED_LOGINS_EXIT="1")
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert "seed-logins" in output
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


def test_down_v_never_appears_in_the_deploy_script_source() -> None:
    """Static guarantee, independent of any run: the discard-the-database
    command must never appear in the script at all, on any path."""
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "down -v" not in code
    assert "compose down" not in code


def test_the_script_asserts_seed_logins_succeeded() -> None:
    """The deploy fails a deployment where seed-logins did not exit 0."""
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "seed-logins" in source
    assert "seed_logins_state" in source and "seed_logins_exit" in source


def test_the_unit_and_the_script_share_the_same_lock_path() -> None:
    """The boot unit's flock and the script's own flock must guard one file."""
    deploy_source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    unit_source = (REPO_ROOT / "scripts" / "vm" / "smartmatch.service").read_text(encoding="utf-8")

    # The script's default: ${SMARTMATCH_STATE_DIR:-/opt/smartmatch}/deploy.lock
    assert 'LOCK_FILE="${SMARTMATCH_LOCK_FILE:-${STATE_DIR}/deploy.lock}"' in deploy_source
    assert 'STATE_DIR="${SMARTMATCH_STATE_DIR:-/opt/smartmatch}"' in deploy_source

    # The unit hardcodes the same resolved default path and wraps its
    # ExecStart in flock over it.
    exec_start = next(line for line in unit_source.splitlines() if line.startswith("ExecStart="))
    assert "/usr/bin/flock" in exec_start
    assert "/opt/smartmatch/deploy.lock" in exec_start


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


# --- the class-exercise compose scope ---------------------------------------
#
# docker-compose.exercise.yml declares api-exercise and web-exercise in the
# same `smartmatch` project. If deploy.sh does not name that file, its
# `up -d --remove-orphans` deletes both containers as orphans. It must name it
# only when the VM is configured for the exercise: the file's `${VAR:?}`
# secrets are interpolated at parse time and would break every compose command
# on a VM that lacks them.

EXERCISE_SCOPE = "-f docker-compose.exercise.yml --profile exercise"
EXERCISE_SECRET_LINE = "SMARTMATCH_EXERCISE_WORKSPACE_SECRET=abcdefgh12345678\n"


def _ship_exercise_overlay(vm: Deployment) -> None:
    """Make the release being deployed carry docker-compose.exercise.yml."""
    (vm.seed / "docker-compose.exercise.yml").write_text("services: {}\n", encoding="utf-8")
    vm.target_sha = vm.push_commit("ship the exercise overlay", "v3")  # type: ignore[attr-defined]


def _write_env(vm: Deployment, text: str) -> None:
    # Untracked on the VM, exactly like the real .env: the dirty-tree check
    # ignores untracked files, so this does not refuse the deployment.
    (vm.app / ".env").write_text(text, encoding="utf-8")


def test_without_exercise_secret_the_scope_is_cba_only(vm: Deployment) -> None:
    _ship_exercise_overlay(vm)
    _write_env(vm, "SMARTMATCH_PILOT_ADMIN_EMAIL=a@example.invalid\n")

    result = vm.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert not any("docker-compose.exercise.yml" in call for call in vm.docker_calls)
    assert not any("--profile" in call for call in vm.docker_calls)
    assert "compose scope: CBA only" in vm.log_text()


def test_with_exercise_secret_the_up_keeps_the_exercise_services(vm: Deployment) -> None:
    _ship_exercise_overlay(vm)
    _write_env(vm, EXERCISE_SECRET_LINE)

    result = vm.run()

    assert result.returncode == 0, result.stdout + result.stderr
    ups = up_calls(vm)
    assert len(ups) == 1, ups
    expected = "compose -f docker-compose.yml -f docker-compose.vm.yml " + EXERCISE_SCOPE
    assert expected in ups[0], ups[0]
    builds = [call for call in vm.docker_calls if call.endswith(" build")]
    assert builds and all(EXERCISE_SCOPE in call for call in builds), builds
    assert "compose scope: CBA + class exercise" in vm.log_text()


@pytest.mark.parametrize(
    "env_text",
    [
        "SMARTMATCH_EXERCISE_WORKSPACE_SECRET=\n",
        'SMARTMATCH_EXERCISE_WORKSPACE_SECRET=""\n',
        "# SMARTMATCH_EXERCISE_WORKSPACE_SECRET=abcdefgh12345678\n",
        "SMARTMATCH_EXERCISE_WORKSPACE_SECRET_OLD=abcdefgh12345678\n",
    ],
    ids=["empty", "empty-quoted", "commented-out", "different-key"],
)
def test_an_unset_exercise_secret_does_not_load_the_overlay(vm: Deployment, env_text: str) -> None:
    # An empty value would fail the file's `${VAR:?}` interpolation, so it must
    # count as "not configured", not as "configured".
    _ship_exercise_overlay(vm)
    _write_env(vm, env_text)

    result = vm.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert not any(EXERCISE_SCOPE in call for call in vm.docker_calls)


def test_an_exported_exercise_secret_loads_the_overlay(vm: Deployment) -> None:
    _ship_exercise_overlay(vm)
    _write_env(vm, "export " + EXERCISE_SECRET_LINE)

    result = vm.run()

    assert result.returncode == 0, result.stdout + result.stderr
    ups = up_calls(vm)
    assert ups and all(EXERCISE_SCOPE in call for call in ups), ups


def test_a_checkout_without_the_overlay_file_stays_cba_only(vm: Deployment) -> None:
    # The secret is set but the release predates docker-compose.exercise.yml:
    # naming a missing file would fail every compose command.
    _write_env(vm, EXERCISE_SECRET_LINE)

    result = vm.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert not any(EXERCISE_SCOPE in call for call in vm.docker_calls)


def test_rollback_re_resolves_the_scope_for_the_previous_checkout(vm: Deployment) -> None:
    # The new release ships the overlay; the previous one does not. The
    # rollback's `up` must drop the file rather than name one that is gone.
    _ship_exercise_overlay(vm)
    _write_env(vm, EXERCISE_SECRET_LINE)

    result = vm.run(HEALTH_STUB_FAIL_FOR=vm.target_sha)  # type: ignore[attr-defined]

    assert result.returncode == 1, result.stdout + result.stderr
    assert vm.metadata()["rolled_back"] is True
    ups = up_calls(vm)
    assert len(ups) == 2, ups
    assert EXERCISE_SCOPE in ups[0], ups[0]
    assert EXERCISE_SCOPE not in ups[1], ups[1]
