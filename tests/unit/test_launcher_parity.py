"""The two launchers, and the operational scripts, are checked statically.

Three properties are asserted here, and each one exists because the failure it
prevents is silent:

1. **Parity.** ``smartmatch.sh`` and ``smartmatch.ps1`` are the same product on
   two operating systems. A command added to one and forgotten in the other,
   or a health check added to ``scripts/compose_health.sh`` and not to the
   PowerShell reimplementation of it, produces a platform where the launcher
   quietly checks less — which is worse than a launcher that is missing,
   because it still reports success.

2. **Syntax.** Every shell script parses. ``bash -n`` is cheap and catches the
   class of defect that only shows up on the machine of whoever ran the script
   first.

3. **No volume deletion.** ``docker compose down -v`` discards the database
   volume. It appears in ``docker-compose.yml``'s header as the documented way
   for a *developer* to throw away local data, and it must never appear in any
   launcher, bootstrap, deployment, or systemd path, where the data being
   discarded is the pilot's.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

BASH_LAUNCHER = REPO_ROOT / "smartmatch.sh"
POWERSHELL_LAUNCHER = REPO_ROOT / "smartmatch.ps1"
HEALTH_SCRIPT = REPO_ROOT / "scripts" / "compose_health.sh"

#: Every shell script this change introduces or relies on, and the ones an
#: operator runs on the VM.
SHELL_SCRIPTS = (
    REPO_ROOT / "smartmatch.sh",
    REPO_ROOT / "setup.sh",
    REPO_ROOT / "scripts" / "compose_health.sh",
    REPO_ROOT / "scripts" / "compose_smoke.sh",
    REPO_ROOT / "scripts" / "vm" / "bootstrap_vm.sh",
    REPO_ROOT / "scripts" / "vm" / "deploy.sh",
)

#: Files that must never destroy a volume.
#:
#: `scripts/compose_smoke.sh` is deliberately absent: it is a developer and CI
#: script whose failure messages tell the reader to run `docker compose down -v`
#: to clear leftover local state, and the compose CI job discards its own throwaway
#: stack that way. Both are correct there and neither runs on the VM. The list
#: below is every path that a pilot deployment or an everyday launcher can reach.
NO_VOLUME_DELETION = (
    REPO_ROOT / "smartmatch.sh",
    REPO_ROOT / "smartmatch.ps1",
    REPO_ROOT / "setup.sh",
    REPO_ROOT / "setup.ps1",
    REPO_ROOT / "scripts" / "compose_health.sh",
    REPO_ROOT / "scripts" / "vm" / "bootstrap_vm.sh",
    REPO_ROOT / "scripts" / "vm" / "deploy.sh",
    REPO_ROOT / "scripts" / "vm" / "smartmatch.service",
    REPO_ROOT / "docker-compose.vm.yml",
    REPO_ROOT / ".github" / "workflows" / "deploy.yml",
)


def _bash_array(source: str, name: str) -> list[str]:
    """Return the elements of a simple ``NAME=( ... )`` bash array."""
    match = re.search(rf"^{re.escape(name)}=\(\s*(.*?)\s*\)\s*$", source, re.MULTILINE | re.DOTALL)
    assert match is not None, f"{name} is not a plain bash array literal any more"
    return [token.strip().strip("\"'") for token in match.group(1).split() if token.strip()]


def _powershell_array(source: str, name: str) -> list[str]:
    """Return the elements of a ``$script:Name = @( 'a', 'b' )`` literal."""
    match = re.search(rf"\${re.escape(name)}\s*=\s*@\(\s*(.*?)\s*\)", source, re.DOTALL)
    assert match is not None, f"{name} is not a plain PowerShell array literal any more"
    return re.findall(r"'([^']+)'", match.group(1))


def test_health_check_identifiers_match_across_platforms() -> None:
    """The bash suite and its PowerShell reimplementation check the same things."""
    bash_ids = _bash_array(HEALTH_SCRIPT.read_text(encoding="utf-8"), "CHECK_IDS")
    powershell_ids = _powershell_array(
        POWERSHELL_LAUNCHER.read_text(encoding="utf-8"), "script:CheckIds"
    )

    assert bash_ids, "scripts/compose_health.sh declares no checks"
    assert set(bash_ids) == set(powershell_ids), (
        "the health checks differ between platforms; a check added to one must be "
        f"added to the other. bash-only={sorted(set(bash_ids) - set(powershell_ids))} "
        f"powershell-only={sorted(set(powershell_ids) - set(bash_ids))}"
    )
    assert bash_ids == powershell_ids, "the checks match but are ordered differently"


def test_the_documented_health_checks_are_all_implemented() -> None:
    """Each declared identifier has a real implementation on both platforms."""
    bash_source = HEALTH_SCRIPT.read_text(encoding="utf-8")
    powershell_source = POWERSHELL_LAUNCHER.read_text(encoding="utf-8")

    for identifier in _bash_array(bash_source, "CHECK_IDS"):
        # An identifier that appears only in the declaration is a check nothing
        # ever reports, which leaves it permanently "not evaluated" — a fail
        # that reads like an oversight rather than a result. Requiring a second
        # occurrence is the cheapest way to catch that without pinning the
        # exact call shape, which differs between the checks written inline and
        # the three that share check_one_shot_exited_ok.
        assert bash_source.count(identifier) >= 2, (
            f"{identifier} is declared but never reported in scripts/compose_health.sh"
        )
        assert powershell_source.count(f"'{identifier}'") >= 2, (
            f"{identifier} is declared but never reported in smartmatch.ps1"
        )


def test_launcher_commands_match_across_platforms() -> None:
    """Both launchers dispatch the same command words."""
    bash_source = BASH_LAUNCHER.read_text(encoding="utf-8")
    powershell_source = POWERSHELL_LAUNCHER.read_text(encoding="utf-8")

    expected = {"install", "start", "stop", "restart", "status", "health", "verify", "logs"}

    bash_commands = set(re.findall(r"^  (\w+)\)\s+cmd_", bash_source, re.MULTILINE))
    powershell_commands = set(re.findall(r"^    '(\w+)'\s+\{", powershell_source, re.MULTILINE))

    assert bash_commands == expected, f"smartmatch.sh dispatches {sorted(bash_commands)}"
    assert powershell_commands == expected, (
        f"smartmatch.ps1 dispatches {sorted(powershell_commands)}"
    )


def test_launcher_exit_codes_match_across_platforms() -> None:
    """The documented exit codes are the same numbers on both platforms.

    A script that exits 3 for a missing prerequisite on Linux and 1 on Windows
    makes every wrapper around it wrong on one of them.
    """
    bash_source = BASH_LAUNCHER.read_text(encoding="utf-8")
    powershell_source = POWERSHELL_LAUNCHER.read_text(encoding="utf-8")

    expected = {"OK": 0, "UNHEALTHY": 1, "USAGE": 2, "PREREQ": 3, "PORT": 4, "TIMEOUT": 5}

    for name, value in expected.items():
        assert re.search(rf"^EXIT_{name}={value}$", bash_source, re.MULTILINE), (
            f"smartmatch.sh does not define EXIT_{name}={value}"
        )
        powershell_name = name.capitalize() if name != "OK" else "Ok"
        assert re.search(
            rf"^\$script:Exit{powershell_name}\s*=\s*{value}$", powershell_source, re.MULTILINE
        ), f"smartmatch.ps1 does not define $script:Exit{powershell_name} = {value}"


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda path: path.name)
def test_shell_scripts_parse(script: Path) -> None:
    """`bash -n` on every shell script this repository ships."""
    assert script.is_file(), f"{script} is missing"
    result = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"{script.name} does not parse:\n{result.stderr}"


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda path: path.name)
def test_shell_scripts_are_executable(script: Path) -> None:
    """A launcher that is not executable fails with 'permission denied'."""
    assert script.stat().st_mode & 0o111, f"{script.name} is not executable"


@pytest.mark.parametrize("path", NO_VOLUME_DELETION, ids=lambda path: path.name)
def test_no_operational_path_removes_a_volume(path: Path) -> None:
    """`docker compose down -v` never appears outside developer documentation.

    It is the one command that discards the database. `down` alone is also
    refused in these files: it removes the containers a restart policy would
    otherwise bring back, and it is one keystroke from the volume-destroying
    form.
    """
    source = path.read_text(encoding="utf-8")
    # Ignore comments: these files explain at length what they will not do, and
    # naming the command in order to forbid it is the point. Both comment
    # syntaxes in play are stripped — `#` line comments (shell, YAML, systemd)
    # and PowerShell's `<# ... #>` block comments.
    without_blocks = re.sub(r"<#.*?#>", "", source, flags=re.DOTALL)
    code = "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith(("#", "//"))
    )

    assert not re.search(r"compose[^\n]*\bdown\b[^\n]*(-v|--volumes)", code), (
        f"{path.name} removes a volume; that discards the pilot database"
    )
    assert not re.search(r"docker\s+compose[^\n]*\bdown\b", code), (
        f"{path.name} runs 'docker compose down'; use 'stop', which keeps containers and volumes"
    )
    assert not re.search(r"docker\s+volume\s+rm", code), f"{path.name} removes a docker volume"


def test_powershell_launcher_uses_no_dynamic_evaluation() -> None:
    """No Invoke-Expression in a script that takes a service name from argv."""
    source = POWERSHELL_LAUNCHER.read_text(encoding="utf-8")
    assert "Invoke-Expression" not in source
    assert "iex " not in source


def test_powershell_braces_balance() -> None:
    """A crude structural check, since a PowerShell parser is not available here.

    It cannot prove the file is valid, and does not pretend to; it catches the
    unbalanced-brace edit, which is the one that makes the whole file fail to
    load rather than one command misbehave.
    """
    source = POWERSHELL_LAUNCHER.read_text(encoding="utf-8")
    # Strip single-quoted here-strings and quoted strings crudely — enough to
    # keep brace counting honest for this file's style.
    stripped = re.sub(r"@'.*?'@", "", source, flags=re.DOTALL)
    stripped = re.sub(r"'[^'\n]*'", "", stripped)
    assert stripped.count("{") == stripped.count("}"), "unbalanced braces in smartmatch.ps1"
    assert stripped.count("(") == stripped.count(")"), "unbalanced parentheses in smartmatch.ps1"


# --- behavior that needs no Docker -----------------------------------------
#
# Argument parsing happens before the launcher looks for a Docker daemon, so
# these run identically on a developer's machine and on a CI runner with no
# daemon. That ordering is itself the property under test: a usage error must
# exit 2 whether or not Docker happens to be running, or every wrapper around
# the launcher has to special-case the environment.


def _launcher(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BASH_LAUNCHER), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        timeout=60,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("bogus",),
        ("install", "--nope"),
        ("status", "--nope"),
        ("health", "--nope"),
        ("health", "--timeout"),
        ("verify", "--nope"),
        ("logs", "--nope"),
        ("logs", "not-a-service"),
        ("logs", "api", "worker"),
    ],
)
def test_usage_errors_exit_two(arguments: tuple[str, ...]) -> None:
    result = _launcher(*arguments)
    assert result.returncode == 2, (
        f"`smartmatch.sh {' '.join(arguments)}` exited {result.returncode}, not 2\n"
        f"{result.stdout}{result.stderr}"
    )


def test_help_exits_zero_and_lists_every_command() -> None:
    result = _launcher("--help")
    assert result.returncode == 0
    for command in ("install", "start", "stop", "restart", "status", "health", "verify", "logs"):
        assert command in result.stdout, f"--help does not mention {command}"


def test_the_health_suite_rejects_a_non_numeric_timeout() -> None:
    result = subprocess.run(
        [str(HEALTH_SCRIPT), "--timeout", "soon"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert result.returncode == 2, result.stdout + result.stderr


def test_the_expected_release_is_resolved_the_way_compose_resolves_it(tmp_path: Path) -> None:
    """`.env` wins over the compose default, and the environment wins over `.env`.

    Getting this order wrong makes the api-health check disagree with the value
    compose actually passed to the container, which turns a correct stack red —
    the most expensive kind of wrong, because the fix people reach for is to
    delete the check.
    """
    source = HEALTH_SCRIPT.read_text(encoding="utf-8")
    function = re.search(
        r"^resolve_expected_release\(\) \{.*?^\}", source, re.MULTILINE | re.DOTALL
    )
    assert function is not None, "resolve_expected_release is no longer a plain function"

    (tmp_path / ".env").write_text("SMARTMATCH_RELEASE=from-dotenv\n", encoding="utf-8")
    harness = f'REPO_ROOT="{tmp_path}"\n{function.group(0)}\nresolve_expected_release\n'

    from_file = subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if k != "SMARTMATCH_RELEASE"},
    )
    assert from_file.stdout == "from-dotenv"

    from_environment = subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "SMARTMATCH_RELEASE": "from-environment"},
    )
    assert from_environment.stdout == "from-environment"

    (tmp_path / ".env").unlink()
    default = subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if k != "SMARTMATCH_RELEASE"},
    )
    assert default.stdout == "compose-dev"


def test_the_optional_pilot_login_seed_is_reported_but_never_required() -> None:
    """`seed-logins` is shown by `status` and counted by nothing.

    It seeds the optional pilot logins from the `SMARTMATCH_PILOT_*` pairs and
    exits 2 when none is configured — which is the default, and what CI runs.
    Counting it would report a perfectly healthy stack as broken, and the
    launcher's own `status --json` assertion in CI would fail on every run.
    """
    bash_source = BASH_LAUNCHER.read_text(encoding="utf-8")
    powershell_source = POWERSHELL_LAUNCHER.read_text(encoding="utf-8")
    health_source = HEALTH_SCRIPT.read_text(encoding="utf-8")

    # Reported by both launchers...
    assert "seed-logins" in _bash_array(bash_source, "COMPOSE_SERVICES")
    assert "seed-logins" in _powershell_array(powershell_source, "script:ComposeServices")

    # ...and required by neither, nor by the health suite.
    required = _powershell_array(powershell_source, "script:OneShotServices")
    assert set(required) == {"migrate", "seed", "seed-review"}, required
    assert re.search(r"^      migrate\|seed\|seed-review\)$", bash_source, re.MULTILINE), (
        "smartmatch.sh's required-one-shot case arm changed; check seed-logins is still out of it"
    )
    assert not any(
        identifier.startswith("seed-logins")
        for identifier in _bash_array(health_source, "CHECK_IDS")
    )
