"""Small shared helpers."""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["utc_now"]


def utc_now() -> datetime:
    """Return the current instant, timezone-aware.

    A single place to read the clock from the request path, so tests have one
    thing to patch and no handler quietly uses a naive ``datetime.now()``. Naive
    timestamps are how the legacy ICS generator came to claim UTC for local
    times (finding F-003).
    """
    return datetime.now(UTC)
