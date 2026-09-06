"""Provider interfaces.

Architecture v1.1 §3.1. Each protocol is deliberately narrow: an adapter can do
exactly what the interface names and nothing else, which is what makes the
classroom-isolation assertion in :mod:`smartmatch_providers.registry`
meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

__all__ = [
    "Edition",
    "EmailProvider",
    "ProviderConfigurationError",
    "RouteMatrixProvider",
    "SendRequest",
    "SendResult",
    "TravelEstimate",
]


class Edition(StrEnum):
    """Which edition of the platform is running.

    ``CLASSROOM`` is not a cosmetic label. Boot-time configuration validation
    asserts that a classroom edition can only construct fixture adapters, and CI
    asserts no classroom code path can construct a live provider client
    (v1.1 §3.3). A diagram label is not a control; this enum plus the registry
    assertion is.
    """

    DEV = "dev"
    STAGING = "staging"
    CLASSROOM = "classroom"
    PRODUCTION = "production"


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider cannot be constructed under the current edition."""


@dataclass(frozen=True, slots=True)
class SendRequest:
    """One outbound message.

    Carries the approval and idempotency evidence the worker rechecks at send
    time (v1.1 §1.8). The adapter does not evaluate policy — it refuses to send
    without the evidence being present, and the five hard gates are enforced by
    the worker before the adapter is ever reached.
    """

    to_address: str
    subject: str
    body_text: str
    approval_id: str
    approved_draft_version: int
    idempotency_key: str
    list_unsubscribe_url: str
    list_unsubscribe_post_url: str

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required; retries must not duplicate sends")
        if not self.approval_id:
            raise ValueError("approval_id is required; no send without a pinned approval")
        if not self.list_unsubscribe_url or not self.list_unsubscribe_post_url:
            raise ValueError(
                "both List-Unsubscribe headers are required (RFC 8058 one-click "
                "requires the POST variant alongside the link)"
            )


@dataclass(frozen=True, slots=True)
class SendResult:
    """The provider's acknowledgement of a send.

    A provider message id only means the provider accepted the message. Delivery
    status is a projection over the ``delivery_event`` stream, never a flag set
    here (v1.1 §1.8).
    """

    provider_message_id: str
    provider: str


@dataclass(frozen=True, slots=True)
class TravelEstimate:
    """A travel-time estimate between two coarse locations.

    Attributes:
        duration: Estimated travel time, or ``None`` when unavailable.
        is_available: Whether an estimate was actually obtained. When ``False``,
            callers must render "travel estimate unavailable" and must not
            substitute a straight-line guess presented as a real estimate
            (v1.1 §3.6 R4/N1).
        quality: ``"route_matrix"`` for a real provider estimate, or ``"coarse"``
            for the interim straight-line approximation, which must be labeled
            as such in the UI (v1.1 Appendix C, open decision 6).
    """

    duration: timedelta | None
    is_available: bool
    quality: str

    @classmethod
    def unavailable(cls) -> TravelEstimate:
        """An explicit "no estimate" result."""
        return cls(duration=None, is_available=False, quality="unavailable")


@runtime_checkable
class EmailProvider(Protocol):
    """Transactional email adapter."""

    name: str

    def send(self, request: SendRequest) -> SendResult:
        """Send one message.

        Implementations must reuse ``request.idempotency_key`` as the provider's
        own idempotency key on retry, so a retried send never duplicates.
        """
        ...


@runtime_checkable
class RouteMatrixProvider(Protocol):
    """Travel-time matrix adapter."""

    name: str

    def estimate(self, origin: str, destination: str) -> TravelEstimate:
        """Estimate travel time between two coarse locations.

        Origins are coarse by contract — never an exact residential address
        (v1.1 §3.1). Implementations return
        :meth:`TravelEstimate.unavailable` on failure rather than raising or
        guessing.
        """
        ...
