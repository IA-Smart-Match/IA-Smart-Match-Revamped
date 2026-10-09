"""Mocked tests for ``scripts/vm/deploy.sh`` rolling back past a newer schema.

Same approach as ``test_vm_deploy_script.py``: the real script, a scratch git
repository, a stub ``docker`` and a stub health suite. Nothing here touches a
real VM or a real Docker daemon.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.vm_deploy_harness import Deployment, make_deployment, up_calls

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("flock") is None,
    reason="the deployment script needs git and flock, which this platform lacks",
)


@pytest.fixture
def vm(tmp_path: Path) -> Deployment:
    return make_deployment(tmp_path)


# --- rollback past a newer schema --------------------------------------------
#
# The compose `migrate` service runs the CHECKOUT's db/ tree. After a rollback
# that tree is the previous release's, and if the failed release had already
# applied a revision, the database names a revision the old tree does not
# contain: the migration tool exits non-zero ("Can't locate revision identified
# by ..."), and compose never starts the API or the worker, which wait on
# migrate. The previous release's own health suite also fails its
# `migrations-at-head` check for the same reason. Both are the expected state
# of a forward-only schema under an application rollback, and deploy.sh must
# tolerate exactly that state — and nothing that merely resembles it.

AHEAD_REVISION = "0002_shipped_by_the_failed_release"
SKIP_MIGRATE_FILE = "rollback-skip-migrate.compose.yml"


def _cannot_locate(revision: str) -> str:
    return (
        "migrate-1  | ERROR [alembic.util.messaging] Can't locate revision identified by "
        f"'{revision}'\n"
        f"migrate-1  | FAILED: Can't locate revision identified by '{revision}'"
    )


def _ship_migration(vm: Deployment, revision: str = AHEAD_REVISION) -> None:
    """Make the release being deployed add one migration revision."""
    versions = vm.seed / "db" / "migrations" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    (versions / f"{revision}.py").write_text(
        f'revision = "{revision}"\ndown_revision = "0001_base"\n', encoding="utf-8"
    )
    vm.target_sha = vm.push_commit("ship a migration", "v3")  # type: ignore[attr-defined]


def _schema_ahead(vm: Deployment, **overrides: str) -> dict[str, str]:
    """The new release migrated, then failed health; the old tree cannot migrate."""
    return {
        "HEALTH_STUB_FAIL_FOR": vm.target_sha,  # type: ignore[attr-defined]
        "DOCKER_STUB_MIGRATE_FAIL_FOR": vm.previous_sha,  # type: ignore[attr-defined]
        "DOCKER_STUB_MIGRATE_LOG": _cannot_locate(AHEAD_REVISION),
        "HEALTH_STUB_JSON_FAILING": "migrations-at-head",
        "HEALTH_STUB_DB_REVISION": AHEAD_REVISION,
        **overrides,
    }


def _skip_migrate_calls(vm: Deployment) -> list[str]:
    return [call for call in vm.docker_calls if SKIP_MIGRATE_FILE in call]


def _needs_a_human(vm: Deployment, result: subprocess.CompletedProcess[str]) -> None:
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "needs a human" in output
    assert "and it is healthy" not in output
    assert not (vm.state / "release.env").exists(), "an unrecovered VM recorded a release"


def test_rollback_past_a_newer_schema_starts_the_previous_release(vm: Deployment) -> None:
    _ship_migration(vm)

    result = vm.run(**_schema_ahead(vm))
    output = result.stdout + result.stderr

    assert result.returncode == 1, output
    assert vm.head() == vm.previous_sha  # type: ignore[attr-defined]
    assert vm.metadata()["rolled_back"] is True
    assert f"rolled back to {vm.previous_sha} and it is healthy" in output  # type: ignore[attr-defined]
    assert AHEAD_REVISION in output, "the log must name the revision the schema stays at"
    recorded = (vm.state / "release.env").read_text(encoding="utf-8")
    assert recorded.strip() == f"SMARTMATCH_RELEASE={vm.previous_sha}"  # type: ignore[attr-defined]

    # The whole stack is brought up again through compose's own ordering — a
    # full `up`, not a hand-picked service list — with migrate made a no-op.
    ups = up_calls(vm)
    assert len(ups) == 3, ups
    assert SKIP_MIGRATE_FILE not in ups[0] and SKIP_MIGRATE_FILE not in ups[1], ups
    assert SKIP_MIGRATE_FILE in ups[2], ups
    assert ups[2].endswith("up -d --remove-orphans"), ups[2]


def test_the_skip_migrate_override_only_replaces_the_migrate_command(vm: Deployment) -> None:
    _ship_migration(vm)
    vm.run(**_schema_ahead(vm))

    override = (vm.state / SKIP_MIGRATE_FILE).read_text(encoding="utf-8")
    body = [line for line in override.splitlines() if line and not line.startswith("#")]
    assert body[:2] == ["services:", "  migrate:"], override
    assert len(body) == 3 and body[2].startswith("    command: "), override
    assert "alembic" not in "\n".join(body)
    # Outside the checkout, so the next deployment's dirty-tree check passes.
    assert vm.git("status", "--porcelain", "--untracked-files=no", cwd=vm.app) == ""


def test_rollback_past_a_newer_schema_stays_forward_only(vm: Deployment) -> None:
    _ship_migration(vm)
    vm.run(**_schema_ahead(vm))

    joined = "\n".join(vm.docker_calls)
    assert "downgrade" not in joined
    assert "psql" not in joined
    assert "pg_restore" not in joined
    assert not any(" run " in call for call in vm.docker_calls)
    for call in vm.docker_calls:
        assert " down" not in call, f"the rollback ran a `down`: {call}"
        assert "volume rm" not in call
    assert len(vm.backups) == 1


def test_the_next_deployment_after_such_a_rollback_migrates_normally(vm: Deployment) -> None:
    _ship_migration(vm)
    vm.run(**_schema_ahead(vm))
    vm.docker_log.unlink()

    second = vm.run()

    assert second.returncode == 0, second.stdout + second.stderr
    assert vm.head() == vm.target_sha  # type: ignore[attr-defined]
    assert _skip_migrate_calls(vm) == [], "a forward deployment skipped its migration"


@pytest.mark.parametrize(
    "migrate_log",
    [
        'migrate-1  | sqlalchemy.exc.OperationalError: connection to server at "db" failed',
        "migrate-1  | FAILED: Multiple head revisions are present for given argument 'head'",
        # A revision the failed release does not define either: not "schema
        # ahead by what we just deployed", so not something to wave through.
        _cannot_locate("9999_unknown_to_both_releases"),
        # An older "can't locate" line followed by a different, later failure.
        _cannot_locate(AHEAD_REVISION)
        + "\nmigrate-1  | FAILED: Target database is not up to date.",
        "",
    ],
    ids=["db-unreachable", "multiple-heads", "foreign-revision", "stale-line", "no-output"],
)
def test_any_other_migrate_failure_on_rollback_still_needs_a_human(
    vm: Deployment, migrate_log: str
) -> None:
    _ship_migration(vm)

    result = vm.run(**_schema_ahead(vm, DOCKER_STUB_MIGRATE_LOG=migrate_log))

    _needs_a_human(vm, result)
    assert _skip_migrate_calls(vm) == [], "an unexplained migrate failure was skipped past"
    # Health never ran against a release that was not started.
    assert vm.health_calls == [vm.target_sha]  # type: ignore[attr-defined]


def test_a_forward_deployment_never_skips_its_migration(vm: Deployment) -> None:
    """The same error text on the way FORWARD is a failed deployment."""
    _ship_migration(vm)

    result = vm.run(**_schema_ahead(vm, DOCKER_STUB_MIGRATE_FAIL_FOR=vm.target_sha))  # type: ignore[attr-defined]

    assert result.returncode == 1, result.stdout + result.stderr
    assert _skip_migrate_calls(vm) == [], "a forward deployment skipped its migration"
    assert vm.metadata()["failure_stage"] == "build-and-up"
    # The rollback's own migrate then succeeds the ordinary way.
    assert vm.metadata()["rolled_back"] is True
    assert vm.health_calls == [vm.previous_sha]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("failing", "db_revision"),
    [
        ("migrations-at-head api-health", AHEAD_REVISION),
        ("api-health", AHEAD_REVISION),
        ("migrations-at-head", "9999_some_other_revision"),
        ("migrations-at-head", ""),
    ],
    ids=["api-also-down", "only-api-down", "database-at-another-revision", "unreadable"],
)
def test_health_still_gates_a_rollback_past_a_newer_schema(
    vm: Deployment, failing: str, db_revision: str
) -> None:
    """Only `migrations-at-head`, naming the expected revision, is tolerated."""
    _ship_migration(vm)

    result = vm.run(
        **_schema_ahead(
            vm,
            HEALTH_STUB_JSON_FAILING=failing,
            HEALTH_STUB_DB_REVISION=db_revision,
            SMARTMATCH_HEALTH_TIMEOUT="0",
        )
    )

    _needs_a_human(vm, result)
    assert "NOT healthy" in result.stdout + result.stderr


def test_an_ordinary_rollback_runs_the_previous_migrate_and_the_full_suite(
    vm: Deployment,
) -> None:
    """No new revision: the rollback path is exactly what it was."""
    result = vm.run(HEALTH_STUB_FAIL_FOR=vm.target_sha)  # type: ignore[attr-defined]

    assert result.returncode == 1, result.stdout + result.stderr
    assert _skip_migrate_calls(vm) == []
    assert not (vm.state / SKIP_MIGRATE_FILE).exists()
    assert len(up_calls(vm)) == 2
    assert vm.health_calls == [vm.target_sha, vm.previous_sha]  # type: ignore[attr-defined]
