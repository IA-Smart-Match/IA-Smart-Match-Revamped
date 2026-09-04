"""Outreach is wired, and these tests pin exactly how far.

## What this file replaces

``tests/unit/test_outreach_dryrun_wiring.py`` was the mirror image of this one.
It asserted that no command type reached the outreach scaffold, that no entry
point imported it, and that the shipped contract published no send surface —
because G4 was deferred and *"the moment a command type routes to it the
deferred gate has been opened by accident rather than by decision"*.

That was the right test for that state. The decision has now been made
deliberately (plan
``docs/plans/2026-09-04-r4-outreach-g4-implementation-plan.md``, card L7), so
each assertion is **rewritten rather than deleted**: every "no outreach command
is routed" becomes "exactly ``outreach.send`` is routed, and it is the only
one". The guard keeps its shape and changes its expectation, which is what lets
a sixth outreach route added later still arrive in a diff a reviewer sees.

Deleting the file instead would have been the cheaper commit and the worse one.
An absence test that becomes a presence test leaves a record of what was
decided; an absence test that is removed leaves nothing where a control used to
be, and the next person cannot tell whether it was retired or lost.

## The one thing that did not change

The domain layer still cannot leave the process. No SMTP client, no vendor SDK,
no credential, no ``smartmatch_providers`` import — asserted below against the
same file list, unchanged from the absence-test era. G4 opening moved the send
*into* the worker; it did not move it into the domain, and the import-linter
contract "Domain is pure" is what keeps that true structurally.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from smartmatch_domain.outreach import OUTREACH_SEND_COMMAND_TYPE
from smartmatch_worker.config import WorkerSettings
from smartmatch_worker.handlers import default_registry
from smartmatch_worker.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A DSN that is never connected to. ``create_app``'s lifespan builds a session
#: factory from it, which opens no connection, and no test here runs a command.
_UNUSED_DSN = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"


def _routed_command_types() -> frozenset[str]:
    """Boot the worker through its real lifespan and report what it routes."""
    app = create_app(settings=WorkerSettings(database_url=_UNUSED_DSN))
    with TestClient(app):
        return frozenset(app.state.registry.command_types)


class TestRegistry:
    """Exactly one outreach command is routed, and it is the send."""

    def test_a_booted_worker_routes_the_send_command(self):
        assert OUTREACH_SEND_COMMAND_TYPE in _routed_command_types()

    def test_the_booted_registry_is_exactly_what_it_was_plus_the_send(self):
        """Exhaustive on purpose, as its predecessor was.

        A handler added anywhere has to come through here, so nobody registers
        one without a reviewer seeing it in the diff. That was the value of the
        absence version and it is unchanged by the gate opening.
        """
        assert _routed_command_types() == {
            "test.noop",
            "import.create",
            "match-run.create",
            OUTREACH_SEND_COMMAND_TYPE,
        }

    def test_outreach_send_is_the_only_outreach_command(self):
        """A second send path is the thing this file exists to catch.

        The R5 agentic stream is out of scope precisely because a parallel send
        that bypassed the command registry would make every guarantee in this
        slice conditional on which path a caller took.
        """
        outreach_commands = {
            command
            for command in _routed_command_types()
            if "outreach" in command or "send" in command
        }

        assert outreach_commands == {OUTREACH_SEND_COMMAND_TYPE}

    def test_the_bare_registry_does_not_route_it(self):
        """Composed at the root, not in ``default_registry``.

        Not a weaker guarantee than registering it there — a stronger statement
        about *how*. The handler needs a provider, a From address, and an HMAC
        key, so it cannot exist without a deployment that supplied them, and a
        registry function taking no arguments could only have supplied defaults.
        See ``smartmatch_worker/main.py``, where the composition is, and
        ``with_paid_extraction`` for the same pattern.
        """
        assert OUTREACH_SEND_COMMAND_TYPE not in default_registry().command_types


class TestContract:
    """The shipped contract publishes the send surface, and nothing more."""

    def _contract(self) -> dict:
        return json.loads(
            (REPO_ROOT / "contracts/openapi/smartmatch.json").read_text(encoding="utf-8")
        )

    def test_the_outreach_tagged_operations_are_exactly_these(self):
        """The successor to "the only outreach operation is the unsubscribe page".

        Pinned as an exact set so that "the contract mentions outreach" cannot
        quietly come to mean something more than these five.
        """
        tagged = {
            f"{method.upper()} {path}"
            for path, operations in self._contract()["paths"].items()
            for method, operation in operations.items()
            if "outreach" in operation.get("tags", [])
        }

        assert tagged == {
            "GET /u/{token}",
            "POST /v1/units/{unit_id}/outreach/drafts",
            "GET /v1/units/{unit_id}/outreach/drafts",
            "POST /v1/units/{unit_id}/outreach/drafts/{draft_id}/send",
            "GET /v1/units/{unit_id}/outreach/sends/{send_id}",
            "POST /v1/unsubscribe",
        }

    def test_the_unsubscribe_get_is_still_the_only_outreach_get_that_could_mutate(self):
        """v1.1 §1.10's split, still intact.

        ``GET /u/{token}`` renders and does not mutate; the POST beside it is
        what suppresses. A link scanner or mail-client prefetcher following the
        GET must not unsubscribe anybody, and the mutating verb being a POST is
        what makes that structural rather than careful.
        """
        paths = self._contract()["paths"]

        assert "get" in paths["/u/{token}"]
        assert "post" not in paths["/u/{token}"]
        assert "post" in paths["/v1/unsubscribe"]
        assert "get" not in paths["/v1/unsubscribe"]

    def test_the_send_response_publishes_no_field_that_could_read_as_delivery(self):
        """B17, closed at the contract level.

        The 202 body is a job id and where to follow it. A generated client
        cannot render "sent" from this schema, because there is no field in it
        that says anything about a message.
        """
        schema = self._contract()["components"]["schemas"]["SendAcceptedResponse"]
        fields = set(schema["properties"])

        assert fields == {"job_id", "events_url", "replayed"}
        for forbidden in ("status", "sent", "delivered", "disposition", "message"):
            assert forbidden not in fields

    def test_submitting_a_send_is_a_202(self):
        """A 200 would report success for work that has not started (v1.1 §3.6 N2)."""
        operation = self._contract()["paths"][
            "/v1/units/{unit_id}/outreach/drafts/{draft_id}/send"
        ]["post"]

        assert "202" in operation["responses"]
        assert "200" not in operation["responses"]

    def test_a_read_send_can_report_that_nothing_is_known_yet(self):
        """``disposition`` is nullable, and that is a documented third state.

        An in-flight attempt has no outcome. A schema that made this a required
        string would force a client to invent one, which is where "pending"
        becomes "failed" in somebody's UI.
        """
        schema = self._contract()["components"]["schemas"]["SendResponse"]
        disposition = schema["properties"]["disposition"]

        assert "null" in {entry.get("type") for entry in disposition.get("anyOf", [])}


class TestDomainPurity:
    """The domain still cannot send anything, gate or no gate."""

    #: Both modules, because the send path moved into ``outreach.py`` and the
    #: shim delegates to it. Checking only the old file would have quietly
    #: stopped covering the code that matters.
    _DOMAIN_MODULES = (
        "python/smartmatch_domain/smartmatch_domain/outreach.py",
        "python/smartmatch_domain/smartmatch_domain/outreach_dryrun.py",
    )

    @pytest.mark.parametrize("relative_path", _DOMAIN_MODULES)
    def test_the_module_imports_no_provider_or_transport(self, relative_path: str):
        """Adds the names the import-linter contract does not enumerate.

        The contract already forbids the domain layer ``os``, ``socket``,
        ``httpx``, ``requests``, and ``smartmatch_providers``. This adds an SMTP
        client, the mail vendors' SDKs, and the send credential — so the absence
        of a send path is pinned in the file a reviewer of these modules
        actually opens.

        Checked by AST rather than by substring, unlike its predecessor: these
        modules' prose names several of these things precisely in order to say
        they are absent, and a text scan of a file that discusses SMTP in order
        to disclaim it is a scan that fails on its own documentation.
        """
        tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        forbidden = {
            "smtplib",
            "resend",
            "sendgrid",
            "googleapiclient",
            "smartmatch_providers",
            "os",
            "socket",
            "httpx",
            "requests",
        }

        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        assert not (imported & forbidden), f"{relative_path} imports {imported & forbidden}"

    @pytest.mark.parametrize("relative_path", _DOMAIN_MODULES)
    def test_the_module_never_names_the_send_credential(self, relative_path: str):
        """The one thing still worth a text scan.

        An environment variable is read by name, so its literal appearing
        anywhere in domain code is the finding — there is no legitimate reason
        for the layer that decides *whether* to send to know what the credential
        is called.
        """
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "SMARTMATCH_EMAIL_API_KEY" not in source


class TestSendPathLocation:
    """Exactly one module can cause a message to leave."""

    def test_only_the_worker_handler_calls_a_provider_send(self):
        """The claim ``smartmatch_worker/outreach.py``'s docstring makes, tested.

        "To answer *under what conditions does this system email a person*, a
        reader has to read one function" is only true while one module holds the
        call. This scans every non-test module for a ``.send(`` call against
        something obtained from the provider layer, and expects one file.
        """
        callers: set[str] = set()
        for root in ("services", "python"):
            for path in (REPO_ROOT / root).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                source = path.read_text(encoding="utf-8")
                if "SendRequest(" in source and ".send(" in source:
                    callers.add(str(path.relative_to(REPO_ROOT)))

        assert callers == {"services/worker/smartmatch_worker/outreach.py"}
