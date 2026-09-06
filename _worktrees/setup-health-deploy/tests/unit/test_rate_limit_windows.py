"""Rate-limit window arithmetic and the ceiling the sweep depends on.

Pure unit tests: no database, no counters. What they pin is the invariant that
makes :meth:`~smartmatch_persistence.rate_limit.RateLimiter.sweep_expired` safe
for counters whose operation it was not told about — that no limit can declare a
window longer than the bound the sweep falls back to for them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_persistence.rate_limit import (
    DEFAULT_SWEEP_GRACE,
    MAX_RATE_LIMIT_WINDOW,
    RateLimit,
)


def test_a_window_longer_than_the_sweep_ceiling_is_rejected():
    """The ceiling is load-bearing, not decorative.

    A counter's operation is a plain string in the table, so a sweep given
    today's limits cannot size a counter left by an operation that has since
    been renamed away. It falls back to the ceiling — which is only conservative
    if nothing may exceed it. Accept a longer window here and that fallback
    starts deleting live windows, handing quota back.
    """
    with pytest.raises(ValueError, match="must not exceed"):
        RateLimit(
            operation="quarterly.quota",
            max_requests=1,
            window=MAX_RATE_LIMIT_WINDOW + timedelta(seconds=1),
        )


def test_the_ceiling_leaves_room_for_a_monthly_quota():
    """The rejected case must be the unreasonable one, not the merely long.

    Daily and monthly quotas are the windows this ceiling exists to accommodate;
    if it excluded them, callers would work around it with a shorter window that
    does not mean what they wanted.
    """
    RateLimit(operation="import.daily", max_requests=100, window=timedelta(days=1))
    RateLimit(operation="import.monthly", max_requests=1000, window=timedelta(days=30))


def test_a_long_window_is_still_anchored_to_the_epoch():
    """Long windows must agree across instances exactly as short ones do.

    A daily window anchored to first use would begin at a different moment on
    every instance, so the same caller would hold as many daily quotas as there
    are instances serving them.
    """
    daily = RateLimit(operation="import.daily", max_requests=1, window=timedelta(days=1))

    morning = daily.window_start(datetime(2026, 8, 17, 9, 30, tzinfo=UTC))
    evening = daily.window_start(datetime(2026, 8, 17, 23, 59, 59, tzinfo=UTC))
    tomorrow = daily.window_start(datetime(2026, 8, 18, 0, 0, tzinfo=UTC))

    assert morning == evening == datetime(2026, 8, 17, tzinfo=UTC)
    assert tomorrow == datetime(2026, 8, 18, tzinfo=UTC)


def test_the_sweep_grace_is_shorter_than_the_shortest_useful_window():
    """The grace delays reclamation; it must not dominate it.

    A grace longer than the windows it guards would keep every counter around
    for the grace rather than for its window, which is the unbounded growth the
    sweep exists to prevent, arriving by a different route.
    """
    assert timedelta(0) < DEFAULT_SWEEP_GRACE < MAX_RATE_LIMIT_WINDOW
