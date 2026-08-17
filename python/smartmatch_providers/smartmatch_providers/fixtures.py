"""Deterministic fixture adapters.

Used by the classroom edition, CI, and local development. Fixtures record what
they were asked to do so tests can assert on it, and they never touch the
network.

Deliberately *not* a demo-data source: a fixture returns an obviously synthetic
result labeled as such. The legacy pattern of falling back to seed content so a
screen stays populated — and presenting it as live — is the anti-pattern
architecture v1.1 §5.5 exists to kill.
"""

from __future__ import annotations

from datetime import timedelta

from smartmatch_providers.base import (
    SendRequest,
    SendResult,
    TravelEstimate,
)

__all__ = ["FixtureEmailProvider", "FixtureRouteMatrixProvider"]


class FixtureEmailProvider:
    """An email adapter that records sends instead of performing them.

    The returned ``provider_message_id`` is prefixed ``fixture-`` so a synthetic
    send can never be mistaken for a real one in logs, in the database, or in
    the UI.
    """

    name = "fixture-email"

    def __init__(self) -> None:
        self.sent: list[SendRequest] = []

    def send(self, request: SendRequest) -> SendResult:
        """Record the request and return a clearly synthetic result."""
        self.sent.append(request)
        return SendResult(
            provider_message_id=f"fixture-{request.idempotency_key}",
            provider=self.name,
        )


class FixtureRouteMatrixProvider:
    """A route-matrix adapter returning fixed, clearly-labeled estimates.

    Args:
        available: When ``False``, every call returns
            :meth:`~smartmatch_providers.base.TravelEstimate.unavailable`, which
            is how tests exercise the "travel estimate unavailable" degradation
            path required by v1.1 §3.6 without needing a provider outage.
    """

    name = "fixture-routes"

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.requested: list[tuple[str, str]] = []

    def estimate(self, origin: str, destination: str) -> TravelEstimate:
        """Return a deterministic estimate, or an explicit unavailable result."""
        self.requested.append((origin, destination))
        if not self._available:
            return TravelEstimate.unavailable()
        if origin == destination:
            return TravelEstimate(duration=timedelta(0), is_available=True, quality="route_matrix")
        return TravelEstimate(
            duration=timedelta(minutes=45), is_available=True, quality="route_matrix"
        )
