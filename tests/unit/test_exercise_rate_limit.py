"""The instructor login's limiter (PLACEHOLDER OQ-CE-06).

This file exists because the first version of the limiter was a
denial-of-service hole wearing a rate limiter's clothes, and the shape of that
mistake is worth pinning rather than remembering.

It charged the **global** window before the **per-key** one. So sixty posts
from one address spent sixty global units — fifty of them on attempts that
address's own key had already refused — and the real instructor, on a different
address, was locked out for the rest of the window. A caller could spend budget
it was not allowed to use, on somebody else's behalf, from one laptop.

What is pinned, in the order the failures would hurt:

1. **A caller cannot spend a bound it is not allowed to use.** Exhausting your
   own key costs the global window nothing after the first allowance.
2. **One caller cannot lock out another.**
3. **A refund is floored**, so it cannot mint budget.
4. The ordinary properties: both bounds hold, windows roll over, the key table
   is capped.

The half this file cannot see — that a *correct passcode* survives a spent
global window — is a property of the login handler, and lives in
``tests/unit/test_exercise_instructor_router.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_api.exercise_rate_limit import (
    INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT,
    INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL,
    INSTRUCTOR_LOGIN_WINDOW,
    MAX_TRACKED_CLIENTS,
    FixedWindowLimiter,
)

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=5)


def _limiter(*, per_key: int = 3, total: int = 10) -> FixedWindowLimiter:
    return FixedWindowLimiter(per_key=per_key, total=total, window=WINDOW)


# ---------------------------------------------------------------------------
# The hole this file exists for
# ---------------------------------------------------------------------------


def test_exhausting_your_own_key_does_not_spend_the_global_window() -> None:
    """The fix for H1's first half: refused attempts burn no shared budget."""
    limiter = _limiter(per_key=3, total=10)

    for _ in range(3):
        assert limiter.charge("10.0.0.1", now=NOW).key_allows is True
    for _ in range(50):
        refused = limiter.charge("10.0.0.1", now=NOW)
        assert refused.key_allows is False

    # Three units spent, not fifty-three: the seven left are the seven a second
    # caller can still have.
    for index in range(7):
        allowance = limiter.charge(f"10.0.0.{index + 2}", now=NOW)
        assert allowance.key_allows is True
        assert allowance.global_allows is True


def test_one_caller_cannot_lock_another_out() -> None:
    """H1 stated as the thing that actually happens in a classroom."""
    limiter = _limiter(per_key=3, total=10)
    for _ in range(60):
        limiter.charge("10.0.0.1", now=NOW)

    instructor = limiter.charge("10.0.0.99", now=NOW)

    assert instructor.key_allows is True
    assert instructor.global_allows is True


def test_the_per_key_bound_is_reported_separately_from_the_global_one() -> None:
    """The two are different questions and the caller must treat them differently."""
    limiter = _limiter(per_key=10, total=2)

    first = limiter.charge("10.0.0.1", now=NOW)
    second = limiter.charge("10.0.0.2", now=NOW)
    third = limiter.charge("10.0.0.3", now=NOW)

    assert (first.key_allows, first.global_allows) == (True, True)
    assert (second.key_allows, second.global_allows) == (True, True)
    # Its own key is fine; the shared bound is not. The handler checks the
    # passcode anyway and only refuses a *wrong* one.
    assert (third.key_allows, third.global_allows) == (True, False)


# ---------------------------------------------------------------------------
# The refund
# ---------------------------------------------------------------------------


def test_a_refund_returns_one_global_unit() -> None:
    limiter = _limiter(per_key=10, total=2)
    limiter.charge("10.0.0.1", now=NOW)
    limiter.charge("10.0.0.2", now=NOW)
    assert limiter.charge("10.0.0.3", now=NOW).global_allows is False

    limiter.refund_global()

    assert limiter.charge("10.0.0.4", now=NOW).global_allows is True


def test_a_refund_cannot_mint_budget() -> None:
    """Floored at zero: refunds without matching spends do not accumulate."""
    limiter = _limiter(per_key=10, total=2)
    for _ in range(20):
        limiter.refund_global()

    assert limiter.charge("10.0.0.1", now=NOW).global_allows is True
    assert limiter.charge("10.0.0.2", now=NOW).global_allows is True
    assert limiter.charge("10.0.0.3", now=NOW).global_allows is False


def test_a_refund_before_any_charge_is_harmless() -> None:
    limiter = _limiter()
    limiter.refund_global()
    assert limiter.charge("10.0.0.1", now=NOW).key_allows is True


# ---------------------------------------------------------------------------
# The ordinary properties
# ---------------------------------------------------------------------------


def test_the_per_key_bound_holds() -> None:
    limiter = _limiter(per_key=3, total=100)
    for _ in range(3):
        assert limiter.charge("10.0.0.1", now=NOW).key_allows is True
    assert limiter.charge("10.0.0.1", now=NOW).key_allows is False


def test_a_window_rolls_over() -> None:
    limiter = _limiter(per_key=3, total=100)
    for _ in range(3):
        limiter.charge("10.0.0.1", now=NOW)
    assert limiter.charge("10.0.0.1", now=NOW).key_allows is False

    later = NOW + WINDOW
    assert limiter.charge("10.0.0.1", now=later).key_allows is True


def test_a_window_does_not_roll_over_early() -> None:
    limiter = _limiter(per_key=1, total=100)
    limiter.charge("10.0.0.1", now=NOW)
    just_inside = NOW + WINDOW - timedelta(seconds=1)

    assert limiter.charge("10.0.0.1", now=just_inside).key_allows is False


def test_the_key_table_is_bounded() -> None:
    """An unbounded dictionary keyed on a caller-controlled value is a leak."""
    limiter = _limiter(per_key=2, total=10**9)
    for index in range(MAX_TRACKED_CLIENTS + 50):
        limiter.charge(f"10.0.{index // 256}.{index % 256}", now=NOW)

    assert len(limiter._keys) <= MAX_TRACKED_CLIENTS


def test_the_shipped_constants_are_the_ones_the_login_uses() -> None:
    """A guard against the module and the route disagreeing about the numbers."""
    assert INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT == 10
    assert INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL == 60
    assert INSTRUCTOR_LOGIN_WINDOW.total_seconds() == 300
    assert INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL > INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT, (
        "a global bound at or below the per-key bound would make the per-key "
        "bound unreachable and every caller share one allowance"
    )


@pytest.mark.parametrize("key", ["", "a", "10.0.0.1", "client-address-unavailable"])
def test_any_key_shape_is_accepted(key: str) -> None:
    """The key is a caller-controlled string; nothing here parses it."""
    assert _limiter().charge(key, now=NOW).key_allows is True
