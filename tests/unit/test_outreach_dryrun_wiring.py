"""The outreach dry run is not wired into anything, and these tests keep it that way.

G4 (outreach send) is deferred until public-release planning
(`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` §3),
so `smartmatch_domain.outreach_dryrun` is a scaffold: it exists, it is tested,
and nothing in the running system can reach it. That last clause is the part
worth a test. A domain module that composes messages is exactly the kind of
thing someone registers "just to see it work", and the moment a command type
routes to it the deferred gate has been opened by accident rather than by
decision.

So these are absence tests, in the shape of `test_paid_extraction_wiring.py`:
they assert what the composition root does *not* route, what the shipped
contract does *not* publish, and what the service entry points do *not*
import. Each one fails the day someone wires this up, which is the day the
decision should be made deliberately instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from smartmatch_worker.config import WorkerSettings
from smartmatch_worker.handlers import default_registry
from smartmatch_worker.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A DSN that is never connected to. `create_app`'s lifespan builds a session
#: factory from it, which opens no connection, and no test here runs a command.
_UNUSED_DSN = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"

#: Entry points that must not reach the scaffold. Checked as source text rather
#: than by import, because an import-time check would only see the modules a
#: test happened to load; the file either contains the import or it does not.
_ENTRY_POINTS = (
    "services/api/smartmatch_api/main.py",
    "services/worker/smartmatch_worker/main.py",
    "services/worker/smartmatch_worker/handlers.py",
)

#: Words that would name a send path in a routed command type.
_OUTREACH_WORDS = ("outreach", "dry_run", "dryrun", "would_send")


def _routed_command_types() -> frozenset[str]:
    """Boot the worker through its real lifespan and report what it routes."""
    app = create_app(settings=WorkerSettings(database_url=_UNUSED_DSN))
    with TestClient(app):
        return frozenset(app.state.registry.command_types)


class TestRegistryAbsence:
    """No command type reaches the dry run."""

    def test_default_registry_routes_no_outreach_command(self):
        for command_type in default_registry().command_types:
            assert not any(word in command_type for word in _OUTREACH_WORDS), command_type

    def test_the_shipped_registry_is_exactly_what_it_was(self):
        """This branch adds no handler at all — not one that is off by default."""
        assert set(default_registry().command_types) == {"test.noop", "import.create"}

    def test_a_booted_worker_routes_no_outreach_command(self):
        """Nor is one composed on at boot, the way paid extraction is."""
        routed = _routed_command_types()

        for command_type in routed:
            assert not any(word in command_type for word in _OUTREACH_WORDS), command_type
        # The shipped registry is still there; absence here is not breakage.
        assert {"test.noop", "import.create"} <= routed


class TestImportAbsence:
    """No service entry point imports the scaffold."""

    @pytest.mark.parametrize("relative_path", _ENTRY_POINTS)
    def test_the_entry_point_does_not_import_the_dry_run(self, relative_path: str):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "outreach_dryrun" not in source

    def test_the_domain_module_imports_no_provider_or_transport(self):
        """The dry run cannot leave the process, by what it does not import.

        The import-linter contract already forbids the domain layer `os`,
        `socket`, `httpx`, `requests`, and `smartmatch_providers`. This adds the
        names that contract does not enumerate — an SMTP client, a mail vendor's
        SDK, and the send credential — so the absence of a send path is pinned
        here too, in the file a reviewer of this module actually opens.
        """
        source = (
            REPO_ROOT / "python/smartmatch_domain/smartmatch_domain/outreach_dryrun.py"
        ).read_text(encoding="utf-8")
        code_only = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        # Everything after the module docstring's closing quotes is code. The
        # prose above names these things precisely in order to say they are absent.
        body = code_only.split('"""', 2)[-1]

        for forbidden in (
            "smtplib",
            "resend",
            "sendgrid",
            "googleapiclient",
            "SMARTMATCH_EMAIL_API_KEY",
            "smartmatch_providers",
        ):
            assert forbidden not in body


class TestContractAbsence:
    """The shipped OpenAPI contract publishes no send surface."""

    def _contract(self) -> dict:
        return json.loads(
            (REPO_ROOT / "contracts/openapi/smartmatch.json").read_text(encoding="utf-8")
        )

    def test_the_contract_publishes_no_outreach_send_path(self):
        for path in self._contract()["paths"]:
            assert not any(word in path.lower() for word in _OUTREACH_WORDS), path

    def test_the_only_outreach_tagged_operation_is_the_unsubscribe_page(self):
        """The one outreach-tagged operation that ships is a GET that renders.

        Pinned so that "the contract mentions outreach" cannot quietly come to
        mean something more than the unsubscribe confirmation page it means
        today.
        """
        tagged = {
            f"{method.upper()} {path}"
            for path, operations in self._contract()["paths"].items()
            for method, operation in operations.items()
            if "outreach" in operation.get("tags", [])
        }

        assert tagged == {"GET /u/{token}"}
