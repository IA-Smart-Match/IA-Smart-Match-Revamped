"""Resend transactional-email adapter — implemented, deliberately not connected.

**Scaffold with no transport of its own.** This module composes a Resend
``POST /emails`` call and reads the response, and it cannot perform one. There
is no HTTP client imported here, no session, no connection pool: the caller
supplies a :class:`ResendTransport`, and the only transports that exist in this
repository are :data:`UNWIRED_TRANSPORT` — which refuses — and the fakes in the
unit tests. Wiring a real one is a deliberate edit under a cleared gate, not a
configuration slip, which is the same property
:mod:`smartmatch_providers.jwks` gets by having no JWKS URI parameter.

Three gates stand between this code and a real recipient, and each is a
different kind of thing so that no single mistake opens all three:

* **A credential and an edition.** ``build_email_provider`` constructs this
  adapter only when an API key is present *and* the edition is not
  fixture-only. That gate lives in :mod:`smartmatch_providers.registry`; the
  classroom edition cannot reach this module at all.
* **A transport.** Absent an explicitly passed one the registry refuses to
  build the adapter, naming OQ-002 — the institutional Resend tenant, the
  verified sending domain, and the contract they sit under are procurement
  decisions nobody has made. A tenant that does not exist cannot be
  misconfigured into existence here.
* **Reviewed copy.** :meth:`ResendEmailProvider.send` refuses a message whose
  template copy has not been through institutional review (OQ-003), *before*
  it calls the transport. The worker already refuses synthetic content in live
  mode in :func:`smartmatch_domain.outreach.assert_send_allowed`; this is the
  second, independent check, on the assumption that the first one will one day
  be edited by somebody who has not read OQ-003.

What this module deliberately does not do: retry, back off, batch, look up
delivery status, or read anything from the response other than the provider's
message id. A provider message id means the provider accepted custody and
nothing more — delivery is a projection over the ``delivery_event`` stream
(architecture v1.1 §1.8), never a value returned from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from smartmatch_providers.base import (
    ProviderConfigurationError,
    SendRequest,
    SendResult,
)

__all__ = [
    "PROVIDER_NAME",
    "RESEND_ENDPOINT",
    "UNWIRED_TRANSPORT",
    "ResendEmailProvider",
    "ResendHttpRequest",
    "ResendHttpResponse",
    "ResendSendError",
    "ResendTransport",
    "UnwiredTransport",
]

#: The single Resend endpoint this adapter knows. Not configurable: a base-URL
#: parameter is how an adapter gets pointed at somebody else's server, and this
#: one has no legitimate reason to talk to anything but Resend.
RESEND_ENDPOINT: Final[str] = "https://api.resend.com/emails"

#: How the adapter names itself in ``SendResult.provider`` and therefore in the
#: ``send`` row and every delivery event. Distinct from ``"fixture-email"`` so a
#: real send and a synthetic one are never confusable in the database.
PROVIDER_NAME: Final[str] = "resend"

#: RFC 8058's one-click value. Advertised only when a deployment opts in — see
#: OQ-006, which is a deliverability trade rather than a code question.
_ONE_CLICK: Final[str] = "List-Unsubscribe=One-Click"

#: Redaction marker. The API key must never appear in a repr, a log line, an
#: exception, or a test failure diff.
_REDACTED: Final[str] = "***redacted***"

#: Domains that can never resolve (RFC 2606 / RFC 6761). A From address on one
#: of these is a placeholder somebody forgot to replace.
_RESERVED_SUFFIXES: Final[tuple[str, ...]] = (".invalid", ".example", ".test", ".localhost")


class ResendSendError(RuntimeError):
    """The provider refused or failed a send.

    Distinct from :class:`~smartmatch_providers.base.ProviderConfigurationError`
    on purpose: a configuration error means this deployment must not send at
    all, and is not re-drivable. This means one attempt failed, which the worker
    records as ``failed_provider`` and may re-drive under the same idempotency
    key.
    """


@dataclass(frozen=True, slots=True)
class ResendHttpRequest:
    """One outbound HTTP request, as data rather than as an action.

    Making the request a value is what lets a test assert on exactly what would
    have gone out — URL, method, headers, body — without a client library and
    without a network. ``headers`` includes the ``Authorization`` line, so this
    object is secret-bearing: never log it, use :meth:`redacted_headers`.
    """

    method: str
    url: str
    headers: dict[str, str]
    json_body: dict[str, Any]

    def redacted_headers(self) -> dict[str, str]:
        """Headers with the credential replaced, safe to log or print."""
        return {
            name: (_REDACTED if name.lower() == "authorization" else value)
            for name, value in self.headers.items()
        }


@dataclass(frozen=True, slots=True)
class ResendHttpResponse:
    """One HTTP response, decoded.

    ``body`` is the parsed JSON object. Parsing happens in the transport, not
    here, so this module has no opinion about — and no dependency on — how
    bytes become a mapping.
    """

    status_code: int
    body: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ResendTransport(Protocol):
    """Performs one HTTP request. The only thing this module cannot do itself.

    An implementation is expected to apply its own timeout and to raise on a
    transport-level failure; :class:`ResendEmailProvider` lets any exception
    from a transport propagate rather than swallowing it, and the worker turns
    that into a re-drivable ``failed_provider``.
    """

    def __call__(self, request: ResendHttpRequest) -> ResendHttpResponse:
        """Perform ``request`` and return the decoded response."""
        ...


class UnwiredTransport:
    """A transport that refuses, so "no transport" is not the same as "no send".

    Used as the value of "the adapter exists but nothing has connected it". It
    raises rather than returning a plausible-looking accepted response, because
    a fake acknowledgement written into ``send`` and a delivery event is exactly
    the fabricated-success shape architecture v1.1 §5.5 exists to prevent.
    """

    def __call__(self, request: ResendHttpRequest) -> ResendHttpResponse:
        """Always raise, naming the decision that is missing."""
        raise ProviderConfigurationError(
            "no Resend transport is wired, so no message can leave this process. "
            "The adapter is implemented; what is missing is OQ-002 — which Resend "
            "tenant, on which verified sending domain, under whose data-processing "
            "contract. That is a procurement decision, and the acceptable-use terms "
            "it comes with are the terms the consent rules were written against."
        )


#: The default. Shared because it holds no state.
UNWIRED_TRANSPORT: Final[UnwiredTransport] = UnwiredTransport()


def _validate_from_address(from_address: str) -> str:
    """Reject a From address that cannot be a real sender.

    Not an RFC 5322 parse — a shape check, so the undeliverable placeholder in
    the worker's settings (``noreply@example.invalid``) cannot reach a live
    adapter by being left alone, and so a blank or malformed value fails at
    construction rather than at the provider.
    """
    address = from_address.strip()
    local, separator, domain = address.partition("@")
    if not separator or not local or not domain or "@" in domain:
        raise ProviderConfigurationError(
            f"{from_address!r} is not a usable From address. Choosing the real one "
            "is an institutional identity claim — see OQ-001."
        )
    if domain.lower().endswith(_RESERVED_SUFFIXES):
        raise ProviderConfigurationError(
            f"the From address {address!r} is on a reserved domain that can never "
            "resolve (RFC 2606/6761). A live adapter configured with it would fail "
            "every send; the placeholder was left unset. See OQ-001."
        )
    return address


class ResendEmailProvider:
    """Sends one message through Resend, given a transport and reviewed copy.

    Args:
        api_key: The Resend credential. Held privately, redacted from
            :meth:`__repr__`, and never included in an exception message.
        from_address: The institutional From address (OQ-001). Validated at
            construction so a placeholder cannot reach the provider.
        transport: Performs the HTTP call. Defaults to
            :data:`UNWIRED_TRANSPORT`, which refuses.
        content_approved: Whether the copy going out through this adapter has
            been through institutional review (OQ-003). ``False`` by default,
            because the safe outcome must be what a caller gets by writing
            nothing.
        advertise_one_click: Whether to send ``List-Unsubscribe-Post``, which
            lets a mailbox provider unsubscribe a recipient with no
            confirmation step. ``False`` by default; see OQ-006. The
            ``List-Unsubscribe`` link header is always sent.

    Raises:
        ProviderConfigurationError: if the credential is blank or the From
            address is unusable.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        transport: ResendTransport = UNWIRED_TRANSPORT,
        content_approved: bool = False,
        advertise_one_click: bool = False,
    ) -> None:
        if not api_key.strip():
            raise ProviderConfigurationError(
                "a blank Resend credential is not a credential. Failing closed."
            )
        self._api_key = api_key
        self._from_address = _validate_from_address(from_address)
        self._transport = transport
        self._content_approved = content_approved
        self._advertise_one_click = advertise_one_click

    def __repr__(self) -> str:
        """Redacted. A repr is the most common accidental way a secret is logged."""
        return (
            f"{type(self).__name__}(from_address={self._from_address!r}, "
            f"api_key={_REDACTED!r}, transport={type(self._transport).__name__}, "
            f"content_approved={self._content_approved})"
        )

    @property
    def from_address(self) -> str:
        """The validated From address. Not a secret."""
        return self._from_address

    @property
    def content_approved(self) -> bool:
        """Whether this adapter was told the outbound copy is reviewed."""
        return self._content_approved

    def build_request(self, request: SendRequest) -> ResendHttpRequest:
        """Compose the HTTP request for ``request`` without performing it.

        Separate from :meth:`send` so the composed call can be asserted on
        directly, and so nothing about composing a message implies sending one.

        ``Idempotency-Key`` carries ``request.idempotency_key`` verbatim: the
        worker derives it from the job id, so a re-drive is de-duplicated at the
        provider as well as in our own tables. Re-deriving it here would break
        that on the first divergence.
        """
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": request.idempotency_key,
        }
        message_headers: dict[str, str] = {
            "List-Unsubscribe": f"<{request.list_unsubscribe_url}>",
        }
        if self._advertise_one_click:
            message_headers["List-Unsubscribe-Post"] = _ONE_CLICK
        return ResendHttpRequest(
            method="POST",
            url=RESEND_ENDPOINT,
            headers=headers,
            json_body={
                "from": self._from_address,
                "to": [request.to_address],
                "subject": request.subject,
                # Text only. An HTML part is a second body that can disagree
                # with the approved one, and the approval is over the text.
                "text": request.body_text,
                "headers": message_headers,
            },
        )

    def send(self, request: SendRequest) -> SendResult:
        """Send one message, if every gate is open.

        Raises:
            ProviderConfigurationError: when the copy has not been reviewed
                (OQ-003) or no transport is wired (OQ-002). Neither is
                re-drivable — the deployment must change first.
            ResendSendError: when the provider rejected the message or returned
                something this adapter cannot read as an acceptance.
        """
        if not self._content_approved:
            # Checked before the transport is touched, so an unreviewed message
            # is not merely un-sent but never composed into a live call.
            raise ProviderConfigurationError(
                "this adapter has not been told the outbound copy is reviewed, so it "
                "will not send. Every shipped template is content_status='synthetic' "
                "until OQ-003 is answered — the postal address, the institution's "
                "identity, and the unsubscribe wording are legal copy for a named "
                "institution, and no engineer can write them."
            )

        response = self._transport(self.build_request(request))
        return self._read_acceptance(response)

    def _read_acceptance(self, response: ResendHttpResponse) -> SendResult:
        """Turn a response into a :class:`SendResult`, or fail loudly.

        Deliberately strict about the id. Returning a placeholder message id for
        a response we could not read would put a value in the ``send`` row that
        looks like provider custody and is not, which is worse than a failure
        the worker can re-drive.
        """
        if not 200 <= response.status_code < 300:
            detail = response.body.get("message") or response.body.get("error")
            suffix = f": {detail}" if isinstance(detail, str) and detail else ""
            raise ResendSendError(
                f"Resend rejected the send with HTTP {response.status_code}{suffix}"
            )

        message_id = response.body.get("id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise ResendSendError(
                f"Resend returned HTTP {response.status_code} with no message id. "
                "Treating that as a failed attempt rather than inventing one: a "
                "fabricated provider id would claim custody nobody confirmed."
            )
        return SendResult(provider_message_id=message_id, provider=PROVIDER_NAME)
