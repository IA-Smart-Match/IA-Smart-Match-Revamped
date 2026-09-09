"""The Resend adapter works, and cannot reach a mailbox.

Two jobs, and the second is the reason this can land while OQ-002 is open.

First, prove the adapter is real: it composes the exact Resend call — endpoint,
method, bearer credential, idempotency key, ``List-Unsubscribe`` — reads an
acceptance into a :class:`~smartmatch_providers.base.SendResult`, and turns
every other response into a loud failure rather than a plausible one.

Second, prove the isolation claims that let it land unconnected:

* the module imports no HTTP client, so it has no way to reach the network;
* nothing in this repository passes it a transport, so the one it gets refuses;
* the classroom edition cannot construct it, with or without a credential and
  with or without a transport;
* an adapter that was not told the copy is reviewed refuses before it touches
  the transport at all; and
* a booted worker, with the settings a deployment gets by writing nothing,
  still composes ``FixtureEmailProvider``.

Every credential here is an obvious test literal. ``re_`` is Resend's real key
prefix, so the fakes below deliberately do **not** use it: a string shaped like
a genuine key in a committed test file is indistinguishable, to a scanner and
to a reader skimming a diff, from one that leaked.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from smartmatch_providers.base import (
    Edition,
    ProviderConfigurationError,
    SendRequest,
    SendResult,
)
from smartmatch_providers.fixtures import FixtureEmailProvider
from smartmatch_providers.registry import build_email_provider
from smartmatch_providers.resend import (
    RESEND_ENDPOINT,
    UNWIRED_TRANSPORT,
    ResendEmailProvider,
    ResendHttpRequest,
    ResendHttpResponse,
    ResendSendError,
)
from smartmatch_worker.config import WorkerSettings
from smartmatch_worker.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "python" / "smartmatch_providers" / "smartmatch_providers" / "resend.py"

#: Not shaped like a real Resend key on purpose — see the module docstring.
FAKE_KEY = "test-credential-not-a-real-key"

#: A sender the adapter will accept. ``.invalid``/``.test`` are refused by the
#: adapter, which is itself asserted below, so the happy path needs a
#: plausible-looking one. No message is ever composed against a live transport.
FROM_ADDRESS = "outreach@smartmatch-pilot.example.org"

#: A DSN that is never connected to. ``create_app``'s lifespan builds a session
#: factory from it, which opens no connection, and no test here runs a command.
_UNUSED_DSN = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"


class RecordingTransport:
    """A fake transport. Records what it was handed and returns a canned reply.

    This is the whole of the "mocked HTTP" in this file: there is no client
    library to patch, because the module under test never had one.
    """

    def __init__(self, response: ResendHttpResponse) -> None:
        self._response = response
        self.calls: list[ResendHttpRequest] = []

    def __call__(self, request: ResendHttpRequest) -> ResendHttpResponse:
        self.calls.append(request)
        return self._response


def _accepting(message_id: str = "0197a1f2-test-message-id") -> RecordingTransport:
    return RecordingTransport(ResendHttpResponse(status_code=200, body={"id": message_id}))


def _send_request(**overrides: object) -> SendRequest:
    base: dict[str, object] = {
        "to_address": "person@example.edu",
        "subject": "Invitation to a placement conversation",
        "body_text": "Hello.",
        "approval_id": "approval-1",
        "approved_draft_version": 2,
        "idempotency_key": "outreach-send:job-1",
        "list_unsubscribe_url": "https://example.test/u/abc",
        "list_unsubscribe_post_url": "https://example.test/v1/unsubscribe",
    }
    base.update(overrides)
    return SendRequest(**base)  # type: ignore[arg-type]


def _provider(**overrides: Any) -> ResendEmailProvider:
    kwargs: dict[str, Any] = {
        "api_key": FAKE_KEY,
        "from_address": FROM_ADDRESS,
        "transport": _accepting(),
        "content_approved": True,
    }
    kwargs.update(overrides)
    return ResendEmailProvider(**kwargs)


# ---------------------------------------------------------------------------
# The adapter composes a real Resend call
# ---------------------------------------------------------------------------


class TestComposedRequest:
    """What would go over the wire, asserted without a wire."""

    def test_posts_to_the_resend_endpoint(self):
        request = _provider().build_request(_send_request())

        assert request.method == "POST"
        assert request.url == RESEND_ENDPOINT

    def test_carries_the_credential_as_a_bearer_token(self):
        headers = _provider().build_request(_send_request()).headers

        assert headers["Authorization"] == f"Bearer {FAKE_KEY}"
        assert headers["Content-Type"] == "application/json"

    def test_reuses_our_idempotency_key_verbatim(self):
        """A re-drive must de-duplicate at the provider, not only in our tables."""
        request = _provider().build_request(_send_request(idempotency_key="outreach-send:job-9"))

        assert request.headers["Idempotency-Key"] == "outreach-send:job-9"

    def test_body_carries_the_approved_text_and_nothing_else(self):
        body = _provider().build_request(_send_request()).json_body

        assert body["from"] == FROM_ADDRESS
        assert body["to"] == ["person@example.edu"]
        assert body["subject"] == "Invitation to a placement conversation"
        assert body["text"] == "Hello."
        # An HTML part would be a second body able to disagree with the one
        # that was approved.
        assert "html" not in body

    def test_list_unsubscribe_link_is_always_sent(self):
        headers = _provider().build_request(_send_request()).json_body["headers"]

        assert headers["List-Unsubscribe"] == "<https://example.test/u/abc>"

    def test_one_click_is_not_advertised_by_default(self):
        """OQ-006 is a deliverability trade nobody has made. Default: silent."""
        headers = _provider().build_request(_send_request()).json_body["headers"]

        assert "List-Unsubscribe-Post" not in headers

    def test_one_click_is_advertised_only_when_asked_for(self):
        provider = _provider(advertise_one_click=True)
        headers = provider.build_request(_send_request()).json_body["headers"]

        assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    def test_redacted_headers_hide_the_credential(self):
        request = _provider().build_request(_send_request())

        assert FAKE_KEY not in str(request.redacted_headers())
        assert request.redacted_headers()["Idempotency-Key"] == "outreach-send:job-1"


# ---------------------------------------------------------------------------
# Reading the response
# ---------------------------------------------------------------------------


class TestResponseHandling:
    """An acceptance is read strictly; anything else fails loudly."""

    def test_accepted_send_returns_the_provider_message_id(self):
        transport = _accepting("msg-abc")
        result = _provider(transport=transport).send(_send_request())

        assert result == SendResult(provider_message_id="msg-abc", provider="resend")
        assert len(transport.calls) == 1

    def test_the_provider_name_is_distinct_from_the_fixture(self):
        """A real send and a synthetic one must never be confusable in the DB."""
        result = _provider().send(_send_request())

        assert result.provider == "resend"
        assert "fixture" not in result.provider_message_id

    @pytest.mark.parametrize("status", [400, 401, 403, 422, 429, 500, 503])
    def test_a_non_2xx_response_is_a_failed_attempt(self, status: int):
        transport = RecordingTransport(
            ResendHttpResponse(status_code=status, body={"message": "domain not verified"})
        )
        with pytest.raises(ResendSendError, match=f"HTTP {status}"):
            _provider(transport=transport).send(_send_request())

    def test_a_rejection_message_is_surfaced_without_the_credential(self):
        transport = RecordingTransport(
            ResendHttpResponse(status_code=403, body={"message": "domain not verified"})
        )
        with pytest.raises(ResendSendError) as caught:
            _provider(transport=transport).send(_send_request())

        assert "domain not verified" in str(caught.value)
        assert FAKE_KEY not in str(caught.value)

    def test_a_2xx_with_no_message_id_is_a_failure_not_a_success(self):
        """Better a re-drivable failure than a fabricated claim of custody."""
        transport = RecordingTransport(ResendHttpResponse(status_code=200, body={}))
        with pytest.raises(ResendSendError, match="no message id"):
            _provider(transport=transport).send(_send_request())

    @pytest.mark.parametrize("value", ["", "   ", 12345, None])
    def test_an_unreadable_message_id_is_a_failure(self, value: object):
        transport = RecordingTransport(ResendHttpResponse(status_code=201, body={"id": value}))
        with pytest.raises(ResendSendError, match="no message id"):
            _provider(transport=transport).send(_send_request())

    def test_a_transport_level_exception_is_not_swallowed(self):
        class Broken:
            def __call__(self, request: ResendHttpRequest) -> ResendHttpResponse:
                raise TimeoutError("connect timeout")

        with pytest.raises(TimeoutError):
            _provider(transport=Broken()).send(_send_request())


# ---------------------------------------------------------------------------
# Construction fails closed
# ---------------------------------------------------------------------------


class TestConstruction:
    """A misconfigured live adapter must not exist, not merely not work."""

    @pytest.mark.parametrize("api_key", ["", "   "])
    def test_a_blank_credential_is_refused(self, api_key: str):
        with pytest.raises(ProviderConfigurationError, match="not a credential"):
            ResendEmailProvider(api_key=api_key, from_address=FROM_ADDRESS)

    @pytest.mark.parametrize("address", ["", "nobody", "a@b@c", "@example.org", "sender@"])
    def test_a_malformed_from_address_is_refused(self, address: str):
        with pytest.raises(ProviderConfigurationError, match="usable From address"):
            ResendEmailProvider(api_key=FAKE_KEY, from_address=address)

    @pytest.mark.parametrize(
        "address",
        [
            "noreply@example.invalid",
            "outreach@smartmatch.test",
            "a@b.localhost",
            "a@b.example",
        ],
    )
    def test_the_undeliverable_placeholder_cannot_reach_a_live_adapter(self, address: str):
        """``noreply@example.invalid`` is the worker's default. It must not send."""
        with pytest.raises(ProviderConfigurationError, match="reserved domain"):
            ResendEmailProvider(api_key=FAKE_KEY, from_address=address)

    def test_repr_does_not_leak_the_credential(self):
        """A repr is the most common accidental way a secret reaches a log."""
        rendered = repr(_provider())

        assert FAKE_KEY not in rendered
        assert "redacted" in rendered
        assert FROM_ADDRESS in rendered


# ---------------------------------------------------------------------------
# Gate: reviewed copy (OQ-003)
# ---------------------------------------------------------------------------


class TestContentApproval:
    """Synthetic copy is refused before the transport is touched."""

    def test_an_unapproved_adapter_refuses_to_send(self):
        with pytest.raises(ProviderConfigurationError, match="reviewed"):
            _provider(content_approved=False).send(_send_request())

    def test_approval_defaults_to_false(self):
        """The safe outcome is what a caller gets by writing nothing."""
        provider = ResendEmailProvider(api_key=FAKE_KEY, from_address=FROM_ADDRESS)

        assert provider.content_approved is False

    def test_the_transport_is_never_reached_without_approval(self):
        """Not merely un-sent: never composed into a live call."""
        transport = _accepting()
        with pytest.raises(ProviderConfigurationError):
            _provider(transport=transport, content_approved=False).send(_send_request())

        assert transport.calls == []


# ---------------------------------------------------------------------------
# Gate: no transport (OQ-002)
# ---------------------------------------------------------------------------


class TestUnwiredTransport:
    """The default transport refuses rather than pretending."""

    def test_the_default_transport_refuses(self):
        provider = ResendEmailProvider(
            api_key=FAKE_KEY, from_address=FROM_ADDRESS, content_approved=True
        )
        with pytest.raises(ProviderConfigurationError, match="OQ-002"):
            provider.send(_send_request())

    def test_the_refusal_names_the_missing_decision_not_a_bug(self):
        with pytest.raises(ProviderConfigurationError) as caught:
            UNWIRED_TRANSPORT(
                ResendHttpRequest(method="POST", url=RESEND_ENDPOINT, headers={}, json_body={})
            )

        message = str(caught.value)
        assert "verified sending domain" in message
        assert "data-processing contract" in message


# ---------------------------------------------------------------------------
# Gate: the registry selects it, and only under four conditions
# ---------------------------------------------------------------------------


class TestRegistrySelection:
    """``build_email_provider`` is where credential and edition are checked."""

    @pytest.mark.parametrize("edition", [Edition.DEV, Edition.STAGING, Edition.PRODUCTION])
    def test_a_credential_and_a_transport_yield_the_resend_adapter(self, edition: Edition):
        provider = build_email_provider(
            edition,
            api_key=FAKE_KEY,
            from_address=FROM_ADDRESS,
            transport=_accepting(),
            content_approved=True,
        )

        assert isinstance(provider, ResendEmailProvider)
        assert provider.name == "resend"

    @pytest.mark.parametrize("edition", [Edition.DEV, Edition.STAGING, Edition.PRODUCTION])
    def test_a_credential_without_a_transport_fails_at_boot(self, edition: Edition):
        """Not at send time: a deployment must not learn this one message at a time."""
        with pytest.raises(ProviderConfigurationError, match="no transport is wired"):
            build_email_provider(edition, api_key=FAKE_KEY, from_address=FROM_ADDRESS)

    def test_a_transport_without_a_credential_still_fails(self):
        with pytest.raises(ProviderConfigurationError, match="no email credential"):
            build_email_provider(
                Edition.PRODUCTION, transport=_accepting(), from_address=FROM_ADDRESS
            )

    def test_a_live_adapter_without_a_from_address_is_refused(self):
        with pytest.raises(ProviderConfigurationError, match="no From address"):
            build_email_provider(Edition.PRODUCTION, api_key=FAKE_KEY, transport=_accepting())

    def test_the_classroom_edition_refuses_a_transport(self):
        """With or without a credential: a transport is not a way in."""
        with pytest.raises(ProviderConfigurationError, match="may only ever construct fixture"):
            build_email_provider(Edition.CLASSROOM, transport=_accepting())

        with pytest.raises(ProviderConfigurationError, match="may only ever construct fixture"):
            build_email_provider(
                Edition.CLASSROOM,
                api_key=FAKE_KEY,
                from_address=FROM_ADDRESS,
                transport=_accepting(),
            )

    def test_use_fixture_wins_over_a_transport(self):
        """An explicit fixture request is never overridden by a live argument."""
        provider = build_email_provider(
            Edition.PRODUCTION,
            api_key=FAKE_KEY,
            use_fixture=True,
            transport=_accepting(),
            content_approved=True,
        )

        assert isinstance(provider, FixtureEmailProvider)

    def test_content_approval_is_not_enough_on_its_own(self):
        """Approving copy does not conjure a tenant."""
        with pytest.raises(ProviderConfigurationError, match="no transport is wired"):
            build_email_provider(
                Edition.PRODUCTION,
                api_key=FAKE_KEY,
                from_address=FROM_ADDRESS,
                content_approved=True,
            )

    def test_the_registry_passes_approval_through_rather_than_assuming_it(self):
        transport = _accepting()
        provider = build_email_provider(
            Edition.PRODUCTION,
            api_key=FAKE_KEY,
            from_address=FROM_ADDRESS,
            transport=transport,
        )

        assert isinstance(provider, ResendEmailProvider)
        with pytest.raises(ProviderConfigurationError, match="reviewed"):
            provider.send(_send_request())
        assert transport.calls == []


# ---------------------------------------------------------------------------
# Structural isolation: the module cannot reach the network, and nothing wires it
# ---------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    """Every module name the file imports, top-level or from a function body."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestStructuralIsolation:
    """The guarantees are properties of the source, not promises in a docstring."""

    def test_the_module_imports_no_http_client(self):
        """No client library means no way to reach the network, whatever the code says."""
        forbidden = {
            "httpx",
            "requests",
            "aiohttp",
            "urllib",
            "urllib3",
            "http",
            "socket",
            "ssl",
            "smtplib",
            "resend",
        }
        offenders = {
            name for name in _imported_modules(MODULE_PATH) if name.split(".")[0] in forbidden
        }

        assert offenders == set()

    def test_the_module_imports_only_the_standard_library_and_our_own_base(self):
        """No new third-party dependency was added to build this."""
        roots = {name.split(".")[0] for name in _imported_modules(MODULE_PATH)}

        assert roots <= {"__future__", "dataclasses", "typing", "smartmatch_providers"}

    def test_the_adapter_is_not_exported_from_the_package(self):
        """The registry is the only supported way to get one, and it gates."""
        import smartmatch_providers

        assert "ResendEmailProvider" not in smartmatch_providers.__all__
        assert not hasattr(smartmatch_providers, "ResendEmailProvider")

    def test_no_shipped_module_supplies_a_transport(self):
        """The claim "unreachable" checked against the source, not against memory.

        Any call to ``build_email_provider`` passing ``transport=`` anywhere
        under ``services/`` or ``python/`` would connect the adapter. Today
        there are none; adding one has to arrive in a diff a reviewer sees.
        """
        offenders: list[str] = []
        for root in (REPO_ROOT / "services", REPO_ROOT / "python"):
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                    if name != "build_email_provider":
                        continue
                    if any(keyword.arg == "transport" for keyword in node.keywords):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

        assert offenders == []


# ---------------------------------------------------------------------------
# Wiring: a booted worker still composes the fixture
# ---------------------------------------------------------------------------


class TestWorkerComposition:
    """The default remains ``FixtureEmailProvider``, proven through a real boot."""

    def test_a_booted_worker_composes_the_fixture_provider(self):
        """Boot the worker, capture the arguments it actually passes, replay them.

        Capturing and replaying rather than asserting on the recorded kwargs
        alone: what matters is which *object* a default deployment ends up
        with, and only the real builder can answer that.
        """
        calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def _spy(*args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            return build_email_provider(*args, **kwargs)

        with patch("smartmatch_worker.main.build_email_provider", _spy):
            app = create_app(settings=WorkerSettings(database_url=_UNUSED_DSN))
            with TestClient(app):
                pass

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert kwargs["api_key"] is None
        assert kwargs["use_fixture"] is True
        # No transport is passed at all, so even a credential could not connect it.
        assert "transport" not in kwargs
        assert isinstance(build_email_provider(*args, **kwargs), FixtureEmailProvider)
