"""The check-in token module is scaffolded and deliberately unwired (B08).

``tests/unit/test_checkin_token.py`` covers what
:mod:`smartmatch_domain.checkin` *does*. What is covered here is what it is not
allowed to do yet, which no test of the module itself can see: reach a running
deployment.

``docs/plans/frontend-broken-buttons.md`` **B08** puts the QR check-in flow
behind **S11** and **D8** (the disclosure-consent policy, including the
minimization copy a scanning surface would need). A token rule that no request
path and no worker command can call is not that flow; the moment a route issues
or verifies one, the pilot has taken a capability neither decision has granted.
So the absence of wiring is the control under test, not an unfinished edge —
the same argument ``tests/unit/test_calendar_invite_wiring.py`` makes for B07
and gate G5, and this file is deliberately its twin.

Note what is *not* asserted here: that the engagement router declares nothing.
It declares one route now — the read-only attendance summary — and
``tests/unit/test_matching_fail_closed.py`` bounds that to an exact allowlist
and pins it to ``GET``. This file's claim is narrower and different: whatever
that router serves, no check-in token is issued or verified anywhere behind it.
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
TOKEN_MODULE = "smartmatch_domain.checkin"

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

#: Substrings that would betray a check-in capability appearing in a path or a
#: command type. Broader than the module name on purpose: a route named
#: `/v1/.../scan` is the same capability arriving under another word. `qr` is
#: matched with its separators rather than bare, because a bare two-letter
#: substring matches innocent words.
_CHECK_IN_MARKERS = ("check-in", "checkin", "check_in", "/qr", "qr-", "qr_", "scan")


def _import_in_a_fresh_interpreter(module: str) -> frozenset[str]:
    """Import `module` alone and report every module it dragged in.

    A subprocess rather than `sys.modules`: this pytest session has already
    imported the token module for its own tests, so an in-process check would
    answer a question about the test run instead of about the composition root.
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
    """Nothing the API serves issues or accepts a check-in token."""

    def test_the_served_openapi_paths_still_match_the_committed_contract(self):
        """Catches a route added without regenerating the contract, and the reverse."""
        from smartmatch_api.main import app

        committed = json.loads(
            (REPO_ROOT / "contracts" / "openapi" / "smartmatch.json").read_text(encoding="utf-8")
        )

        assert sorted(app.openapi()["paths"]) == sorted(committed["paths"])

    def test_no_route_path_mentions_a_check_in_or_a_scan(self):
        """Stated independently of the contract, so regenerating it cannot help."""
        from smartmatch_api.main import app

        offenders = [
            path
            for path in app.openapi()["paths"]
            for marker in _CHECK_IN_MARKERS
            if marker in str(path).lower()
        ]

        assert offenders == [], f"B08 is blocked on S11 and D8; these routes check in: {offenders}"

    def test_the_api_composition_root_never_imports_the_token_module(self):
        """Import reachability, not just route names.

        A route verifying a token through a helper module would still show here.
        """
        imported = _import_in_a_fresh_interpreter("smartmatch_api.main")

        assert TOKEN_MODULE not in imported


class TestNoWorkerSurface:
    """The shipped worker routes no command that issues or verifies a token."""

    def test_the_shipped_registry_routes_no_check_in_command(self):
        command_types = default_registry().command_types
        offenders = [
            command
            for command in command_types
            for marker in _CHECK_IN_MARKERS
            if marker in command.lower()
        ]

        assert offenders == [], f"B08 is blocked; these commands are routed: {offenders}"

    def test_the_worker_composition_root_never_imports_the_token_module(self):
        imported = _import_in_a_fresh_interpreter("smartmatch_worker.main")

        assert TOKEN_MODULE not in imported


class TestThePurityTheImportLinterCannotSeeAtRuntime:
    """Domain purity, checked as reachability rather than as configuration."""

    def test_the_token_module_imports_nothing_but_stdlib(self):
        imported = _import_in_a_fresh_interpreter(TOKEN_MODULE)
        third_party = {
            name
            for name in imported
            if name.split(".")[0]
            in {"fastapi", "starlette", "sqlalchemy", "httpx", "requests", "pydantic"}
        }

        assert third_party == set()

    @pytest.mark.parametrize("token", ["qrcode", "segno", "PIL", "cv2", "pyzbar"])
    def test_the_token_module_names_no_qr_rendering_or_scanning_library(self, token: str):
        """It returns text. Drawing or reading a barcode is somebody else's job."""
        source = (
            REPO_ROOT / "python" / "smartmatch_domain" / "smartmatch_domain" / "checkin.py"
        ).read_text(encoding="utf-8")

        assert f"import {token}" not in source
