"""Rate limiter integration tests.

Architecture v1.1 §3.4 layer 2. The property that matters is that counters are
*shared*, not per-process: on Cloud Run an in-process counter lets every instance
permit the full quota independently.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_persistence.rate_limit import RateLimit, RateLimiter
from sqlalchemy import text

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 17, 12, 0, 30, tzinfo=UTC)


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter()


@pytest.fixture
def limit() -> RateLimit:
    return RateLimit(operation="test.op", max_requests=3, window=timedelta(minutes=1))


@pytest.fixture(autouse=True)
def _clear_counters(engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM rate_limit_counter"))
    yield


def _check(session, limiter, limit, tenant_id, *, subject="user-1", now=NOW):
    return limiter.check(session, limit=limit, tenant_id=tenant_id, subject=subject, now=now)


# ---------------------------------------------------------------------------
# Basic behavior
# ---------------------------------------------------------------------------


def test_requests_within_the_limit_are_allowed(session_factory, limiter, limit, tenant_id):
    with session_factory() as session:
        for _ in range(3):
            assert _check(session, limiter, limit, tenant_id).allowed
        session.commit()


def test_the_request_past_the_limit_is_denied(session_factory, limiter, limit, tenant_id):
    with session_factory() as session:
        for _ in range(3):
            _check(session, limiter, limit, tenant_id)
        decision = _check(session, limiter, limit, tenant_id)
        session.commit()

    assert not decision.allowed
    assert decision.remaining == 0


def test_remaining_counts_down(session_factory, limiter, limit, tenant_id):
    """Regression guard for a latent bug.

    ``remaining`` was computed from ``row.count``, which on a SQLAlchemy ``Row``
    resolves to the inherited tuple *method*, not the column. Nothing asserted
    ``remaining``, so the bug was invisible until strict typing found it.
    """
    with session_factory() as session:
        assert _check(session, limiter, limit, tenant_id).remaining == 2
        assert _check(session, limiter, limit, tenant_id).remaining == 1
        assert _check(session, limiter, limit, tenant_id).remaining == 0
        session.commit()


def test_retry_after_points_at_the_window_reset(session_factory, limiter, limit, tenant_id):
    """A client should be told when to come back, not left to guess."""
    with session_factory() as session:
        decision = _check(session, limiter, limit, tenant_id)
        session.commit()

    # NOW is 30 seconds into a 60-second window.
    assert decision.retry_after == timedelta(seconds=30)


# ---------------------------------------------------------------------------
# Isolation between subjects, tenants, and operations
# ---------------------------------------------------------------------------


def test_subjects_have_independent_quotas(session_factory, limiter, limit, tenant_id):
    """One noisy user must not deny everyone else."""
    with session_factory() as session:
        for _ in range(3):
            _check(session, limiter, limit, tenant_id, subject="user-1")
        assert not _check(session, limiter, limit, tenant_id, subject="user-1").allowed
        assert _check(session, limiter, limit, tenant_id, subject="user-2").allowed
        session.commit()


def test_operations_have_independent_quotas(session_factory, limiter, tenant_id):
    """Exhausting imports must not block reads."""
    imports = RateLimit(operation="import.create", max_requests=1, window=timedelta(minutes=1))
    reads = RateLimit(operation="job.read", max_requests=1, window=timedelta(minutes=1))

    with session_factory() as session:
        assert _check(session, limiter, imports, tenant_id).allowed
        assert not _check(session, limiter, imports, tenant_id).allowed
        assert _check(session, limiter, reads, tenant_id).allowed
        session.commit()


def test_tenants_have_independent_quotas(session_factory, engine, limiter, limit, tenant_id):
    other = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :s, :s)"),
            {"id": other, "s": f"other-{other.hex[:8]}"},
        )

    try:
        with session_factory() as session:
            for _ in range(3):
                _check(session, limiter, limit, tenant_id)
            assert not _check(session, limiter, limit, tenant_id).allowed
            assert _check(session, limiter, limit, other).allowed
            session.commit()
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM rate_limit_counter WHERE tenant_id = :t"), {"t": other})
            conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": other})


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


def test_quota_resets_in_the_next_window(session_factory, limiter, limit, tenant_id):
    with session_factory() as session:
        for _ in range(3):
            _check(session, limiter, limit, tenant_id)
        assert not _check(session, limiter, limit, tenant_id).allowed

        later = NOW + timedelta(minutes=1)
        assert _check(session, limiter, limit, tenant_id, now=later).allowed
        session.commit()


def test_window_start_is_anchored_to_the_epoch(limit):
    """Every instance must agree where a window begins, without coordinating.

    Anchoring to the epoch rather than to first use is what makes that true.
    """
    a = limit.window_start(datetime(2026, 8, 17, 12, 0, 5, tzinfo=UTC))
    b = limit.window_start(datetime(2026, 8, 17, 12, 0, 59, tzinfo=UTC))
    c = limit.window_start(datetime(2026, 8, 17, 12, 1, 0, tzinfo=UTC))

    assert a == b == datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)
    assert c == datetime(2026, 8, 17, 12, 1, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The shared-counter property
# ---------------------------------------------------------------------------


def test_the_counter_is_shared_across_sessions(session_factory, limiter, limit, tenant_id):
    """Two sessions stand in for two Cloud Run instances.

    If the counter lived in the process, each would independently allow the full
    quota. Because it is a row, the second session sees the first's consumption.
    """
    with session_factory() as first:
        for _ in range(3):
            _check(first, limiter, limit, tenant_id)
        first.commit()

    with session_factory() as second:
        decision = _check(second, limiter, limit, tenant_id)
        second.commit()

    assert not decision.allowed, "quota must be shared, not per-process"


def test_rolled_back_requests_do_not_consume_quota(session_factory, limiter, limit, tenant_id):
    """Quota spent by a request that then fails should not count against a user."""
    with session_factory() as session:
        _check(session, limiter, limit, tenant_id)
        session.rollback()

    with session_factory() as session:
        assert _check(session, limiter, limit, tenant_id).remaining == 2
        session.commit()


# ---------------------------------------------------------------------------
# Validation and housekeeping
# ---------------------------------------------------------------------------


def test_invalid_limits_are_rejected():
    with pytest.raises(ValueError, match="max_requests"):
        RateLimit(operation="x", max_requests=0, window=timedelta(minutes=1))
    with pytest.raises(ValueError, match="window"):
        RateLimit(operation="x", max_requests=1, window=timedelta(0))


def test_sweep_removes_counters_once_their_own_window_has_elapsed(
    session_factory, limiter, limit, tenant_id
):
    """Without a sweep the table grows unbounded for IP-keyed limits."""
    with session_factory() as session:
        _check(session, limiter, limit, tenant_id)
        session.commit()

    with session_factory() as session:
        removed = limiter.sweep_expired(session, limits=[limit], now=NOW + timedelta(days=1))
        session.commit()

    assert removed == 1


def test_sweep_leaves_current_windows_alone(session_factory, limiter, limit, tenant_id):
    with session_factory() as session:
        _check(session, limiter, limit, tenant_id)
        session.commit()

    with session_factory() as session:
        removed = limiter.sweep_expired(session, limits=[limit], now=NOW)
        session.commit()

    assert removed == 0


def test_sweep_never_reopens_a_window_that_is_still_running(session_factory, limiter, tenant_id):
    """The property the sweep must never violate: it cannot grant quota.

    The window length belongs to the operation, not to the sweep. When the sweep
    deleted anything older than a fixed hour, a daily quota that a caller had
    already spent was erased two hours into its window and the caller got the
    whole day's allowance again — a rate limiter that silently stops limiting,
    which is the failure mode this module exists to prevent (see the module
    docstring on failing closed).

    Asserted on the *decision*, not on the row count: a sweep that deletes
    nothing but leaves the caller able to spend again would satisfy a
    row-counting test and still be the bug.
    """
    daily = RateLimit(operation="import.daily", max_requests=1, window=timedelta(days=1))

    with session_factory() as session:
        assert _check(session, limiter, daily, tenant_id).allowed
        assert not _check(session, limiter, daily, tenant_id).allowed, "quota is spent"
        session.commit()

    # Two hours later: far past any fixed grace the sweep might use, and nowhere
    # near the end of the caller's window.
    midwindow = NOW + timedelta(hours=2)
    with session_factory() as session:
        removed = limiter.sweep_expired(session, limits=[daily], now=midwindow)
        session.commit()

    assert removed == 0

    with session_factory() as session:
        decision = _check(session, limiter, daily, tenant_id, now=midwindow)
        session.commit()

    assert not decision.allowed, "the sweep handed back quota the caller had already spent"


def test_sweep_applies_each_operations_own_window(session_factory, limiter, tenant_id):
    """One pass, two window lengths, one cutoff each.

    A single global cutoff cannot serve both: whatever it is, it either spares
    the short-window rows the sweep exists to remove or deletes the long-window
    rows that are still counting.
    """
    minutely = RateLimit(operation="job.read", max_requests=5, window=timedelta(minutes=1))
    daily = RateLimit(operation="import.daily", max_requests=5, window=timedelta(days=1))

    with session_factory() as session:
        _check(session, limiter, minutely, tenant_id)
        _check(session, limiter, daily, tenant_id)
        session.commit()

    with session_factory() as session:
        removed = limiter.sweep_expired(
            session, limits=[minutely, daily], now=NOW + timedelta(hours=2)
        )
        session.commit()

    assert removed == 1
    assert _operations_with_counters(session_factory) == {"import.daily"}


def test_sweep_waits_out_the_grace_period(session_factory, limiter, limit, tenant_id):
    """A window that closed a moment ago is left alone deliberately.

    Instances do not share a clock, and a request that began before the window
    closed may still be committing its increment. Deleting exactly at the
    boundary would race that increment away and hand the caller a fresh quota;
    the grace makes the sweep wait until no live request can still be counting
    against the row.
    """
    just_closed = NOW + timedelta(minutes=1, seconds=30)

    with session_factory() as session:
        _check(session, limiter, limit, tenant_id)
        session.commit()

    with session_factory() as session:
        assert limiter.sweep_expired(session, limits=[limit], now=just_closed) == 0
        session.commit()

    with session_factory() as session:
        assert limiter.sweep_expired(session, limits=[limit], now=NOW + timedelta(hours=1)) == 1
        session.commit()


def test_sweep_eventually_removes_counters_for_operations_it_was_not_told_about(
    session_factory, engine, limiter, limit, tenant_id
):
    """Renamed and retired operations must not accumulate forever.

    The counter table stores the operation as a plain string, so a sweep given
    today's limits cannot know the window of a counter written by yesterday's
    code. Those rows are removed against
    :data:`~smartmatch_persistence.rate_limit.MAX_RATE_LIMIT_WINDOW` instead —
    conservative, because no ``RateLimit`` may declare a longer window, and
    still bounded, because the alternative is a table that only grows.
    """
    with engine.begin() as conn:
        for label, age in (("retired.recent", timedelta(days=2)), ("retired.ancient", None)):
            conn.execute(
                text(
                    "INSERT INTO rate_limit_counter "
                    "(tenant_id, subject, operation, window_start, count) "
                    "VALUES (:t, 'user-1', :op, :ws, 1)"
                ),
                {
                    "t": tenant_id,
                    "op": label,
                    "ws": NOW - (age if age else timedelta(days=90)),
                },
            )

    with session_factory() as session:
        removed = limiter.sweep_expired(session, limits=[limit], now=NOW)
        session.commit()

    assert removed == 1
    assert _operations_with_counters(session_factory) == {"retired.recent"}


def _operations_with_counters(session_factory) -> set[str]:
    with session_factory() as session:
        return {
            row.operation
            for row in session.execute(text("SELECT operation FROM rate_limit_counter")).all()
        }
