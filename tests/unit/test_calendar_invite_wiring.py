"""The calendar-invite facade is scaffolded and deliberately unwired (gate G5).

`tests/golden/test_calendar_invite_golden.py` covers what
`smartmatch_domain.calendar_invite` *does*. What is covered here is what it is
not allowed to do yet, which no test of the facade itself can see: reach a
running deployment.

The synthetic pilot development authorization (2026-09-03, §3) leaves **G5
(Calendar API)** deferred to public-release planning and permits "ICS artifacts"
only. An ICS builder that no request path and no worker command can call is
exactly that permission and nothing more; the moment a route serves it or the
shipped registry routes a command that produces it, the pilot has quietly taken
a capability the gate has not granted. So the absence of wiring is the control
under test, not an unfinished edge — the same argument
`tests/unit/test_paid_extraction_wiring.py` makes for spend.

These assertions are written so that wiring the facade later fails *here*, in a
file that names the gate, rather than passing silently.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from smartmatch_worker.handlers import default_registry

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The module that must stay unreachable from either composition root.
FACADE_MODULE = "smartmatch_domain.calendar_invite"

#: Mirrors `[tool.pytest.ini_options] pythonpath` so a subprocess sees the same
#: workspace packages this session imported.
_WORKSPACE_PATHS = (
    ".",
    "python/smartmatch_domain",
    "python/smartmatch_authz",
    "python/smartmatch_providers",
    "python/smartmatch_persistence",
    "services/api",
    "services/worker",
)

#: Substrings that would betray a calendar capability appearing in a path or a
#: command type. Deliberately broader than the module name: the point is to
#: catch a route named `/v1/.../invite.ics` as readily as an import. A bare
#: "ics" is not usable as a marker — it is a substring of "metrics", which is a
#: real and unrelated route — so the extension and command-namespace forms are
#: matched instead.
_CALENDAR_MARKERS = ("calendar", "invite", ".ics", "ics.")


def _import_in_a_fresh_interpreter(module: str) -> frozenset[str]:
    """Import `module` alone and report every module it dragged in.

    A subprocess rather than `sys.modules`: this pytest session has already
    imported the facade for the golden tests, so an in-process check would be
    answering a question about the test run instead of about the composition
    root.
    """
    script = (
        "import sys, json\n"
        f"sys.path[:0] = {list(_WORKSPACE_PATHS)!r}\n"
        f"__import__({module!r})\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"importing {module} failed:\n{completed.stdout}\n{completed.stderr}"
    )
    return frozenset(json.loads(completed.stdout.splitlines()[-1]))


class TestNoHttpSurface:
    """Nothing the API serves exposes a calendar invite."""

    def test_the_served_openapi_paths_still_match_the_committed_contract(self):
        """The no-new-route claim, stated against the artifact clients are built from.

        Checking the live app against `contracts/openapi/smartmatch.json` catches
        both halves of the failure at once: a route added without regenerating
        the contract, and a contract edited to accommodate one.
        """
        from smartmatch_api.main import app

        committed = json.loads(
            (REPO_ROOT / "contracts" / "openapi" / "smartmatch.json").read_text(encoding="utf-8")
        )

        assert sorted(app.openapi()["paths"]) == sorted(committed["paths"])

    def test_no_route_path_mentions_a_calendar_artifact(self):
        """Stated independently of the contract, so regenerating it cannot help."""
        from smartmatch_api.main import app

        offenders = [
            path
            for path in app.openapi()["paths"]
            for marker in _CALENDAR_MARKERS
            if marker in str(path).lower()
        ]

        assert offenders == [], f"G5 is deferred; these routes serve a calendar: {offenders}"

    def test_the_api_composition_root_never_imports_the_facade(self):
        """Import reachability, not just route names.

        A route serving ICS through a helper module would still show up here.
        """
        imported = _import_in_a_fresh_interpreter("smartmatch_api.main")

        assert FACADE_MODULE not in imported


class TestNoWorkerSurface:
    """The shipped worker routes no command that produces a calendar artifact."""

    def test_the_shipped_registry_routes_no_calendar_command(self):
        command_types = default_registry().command_types
        offenders = [
            command
            for command in command_types
            for marker in _CALENDAR_MARKERS
            if marker in command.lower()
        ]

        assert offenders == [], f"G5 is deferred; these commands are routed: {offenders}"
        # The rest of the shipped registry is unaffected by this PR.
        assert {"test.noop", "import.create"} <= set(command_types)

    def test_the_worker_composition_root_never_imports_the_facade(self):
        imported = _import_in_a_fresh_interpreter("smartmatch_worker.main")

        assert FACADE_MODULE not in imported


class TestNoGoogleCalendarDependency:
    """G5 is about the Calendar *API*; the scaffold must not reach for it."""

    #: Names that only appear where a Google Calendar client is being set up.
    _FORBIDDEN = (
        "googleapiclient",
        "google_auth_oauthlib",
        "google-api-python-client",
        "auth/calendar",
        "calendar.events",
        "GOOGLE_CALENDAR",
        "CALENDAR_CREDENTIALS",
    )

    @pytest.mark.parametrize("token", _FORBIDDEN)
    def test_the_facade_names_no_google_calendar_client_scope_or_env_var(self, token: str):
        source = (
            REPO_ROOT / "python" / "smartmatch_domain" / "smartmatch_domain" / "calendar_invite.py"
        ).read_text(encoding="utf-8")

        assert token not in source

    def test_the_facade_imports_nothing_but_stdlib_and_the_ics_module(self):
        """The domain layer stays pure: no client, no transport, no credentials."""
        imported = _import_in_a_fresh_interpreter(FACADE_MODULE)
        third_party = {
            name
            for name in imported
            if name.split(".")[0] in {"googleapiclient", "google", "httpx", "requests", "urllib3"}
        }

        assert third_party == set()
        assert "smartmatch_domain.ics" in imported
