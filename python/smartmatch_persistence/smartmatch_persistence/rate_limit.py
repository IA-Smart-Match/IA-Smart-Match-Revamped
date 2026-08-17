"""Transactional rate limiting.

Architecture v1.1 §3.4 layer 2. Counters live in PostgreSQL and are incremented
transactionally, because Cloud Run autoscales: an in-process counter lets each
instance independently permit the full quota, so a documented limit of 30/min
silently becomes 30/min *per instance*.

## Fixed windows, and what that costs

Each ``(tenant, subject, operation)`` gets one counter per fixed window. The
known imprecision is boundary bursting: a caller can spend a full quota at the
end of one window and another at the start of the next, briefly achieving twice
the nominal rate.

That is accepted deliberately. A sliding window needs a row per request, and at
pilot volume the storage and vacuum cost buys precision nobody needs — v1.1 §3.4
states the limits are "still hypotheses to be tuned with recorded evidence", and
tuning a hypothesis to sliding-window precision is false rigor. The adoption
trigger for something better is the same one v1.1 §3.5 gives for Redis: measured
contention or throughput that cannot meet SLO after tuning.

## Failing closed

If the limiter cannot reach the database, the caller is denied. v1.1 §3.6 (N4)
prohibits skipping rate or budget checks under partial infrastructure failure —
an unavailable limiter must not become an open door.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["RateLimit", "RateLimitDecision", "RateLimiter"]


@dataclass(frozen=True, slots=True)
class RateLimit:
    """One operation's limit.

    Attributes:
        operation: Stable identifier, e.g. ``"match-run.create"``.
        max_requests: Requests permitted per window.
        window: Window length.
    """

    operation: str
    max_requests: int
    window: timedelta

    def __post_init__(self) -> None:
        if self.max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if self.window <= timedelta(0):
            raise ValueError("window must be positive")

    def window_start(self, moment: datetime) -> datetime:
        """Truncate ``moment`` to the start of its window.

        Computed from the epoch rather than from first use, so every instance
        agrees on where a window begins without coordinating.
        """
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        elapsed = (moment - epoch) // self.window
        return epoch + elapsed * self.window


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The outcome of one limit check.

    Attributes:
        allowed: Whether the request may proceed.
        remaining: Requests left in this window. Zero when denied.
        retry_after: How long until the window resets. Sent as ``Retry-After``
            so a client can back off intelligently rather than hammering.
        limit: The limit that was applied, for the response headers.
    """

    allowed: bool
    remaining: int
    retry_after: timedelta
    limit: RateLimit


class RateLimiter:
    """Increments and checks PostgreSQL-backed counters."""

    def check(
        self,
        session: Session,
        *,
        limit: RateLimit,
        tenant_id: uuid.UUID,
        subject: str,
        now: datetime | None = None,
    ) -> RateLimitDecision:
        """Consume one unit of quota, or deny.

        A single ``INSERT ... ON CONFLICT DO UPDATE`` with a guard on the SET.
        The guard is what makes this correct under concurrency: when the counter
        has already reached the limit the update matches nothing, no row is
        returned, and the request is denied. There is no read-then-write window
        in which two instances both observe room and both proceed.

        Does not commit. The caller commits — usually alongside whatever the
        request does — so a rolled-back request does not consume quota.

        Args:
            subject: The user id, or an IP for unauthenticated endpoints.
            now: Injected for tests so window rollover is exercised directly.

        Returns:
            A :class:`RateLimitDecision`. Never raises for an exhausted quota;
            exhaustion is an expected outcome, not an error.
        """
        now = now or datetime.now(UTC)
        window_start = limit.window_start(now)
        retry_after = (window_start + limit.window) - now

        statement = (
            pg_insert(schema.rate_limit_counter)
            .values(
                tenant_id=tenant_id,
                subject=subject,
                operation=limit.operation,
                window_start=window_start,
                count=1,
            )
            .on_conflict_do_update(
                constraint="pk_rate_limit_counter",
                set_={"count": schema.rate_limit_counter.c.count + 1},
                # The guard. Without it, the counter would keep climbing and the
                # check would be a separate, racy read.
                where=schema.rate_limit_counter.c.count < limit.max_requests,
            )
            # Labelled, because ``Row.count`` resolves to the inherited tuple
            # method rather than the column — reading ``row.count`` silently
            # yields a bound method instead of an integer.
            .returning(schema.rate_limit_counter.c.count.label("current_count"))
        )

        row = session.execute(statement).one_or_none()

        if row is None:
            return RateLimitDecision(
                allowed=False,
                remaining=0,
                retry_after=retry_after,
                limit=limit,
            )

        return RateLimitDecision(
            allowed=True,
            remaining=max(0, limit.max_requests - row.current_count),
            retry_after=retry_after,
            limit=limit,
        )

    def sweep_expired(
        self,
        session: Session,
        *,
        older_than: timedelta = timedelta(hours=1),
        now: datetime | None = None,
    ) -> int:
        """Delete counters for windows that have long since elapsed.

        Without this the table grows with every distinct subject seen, which for
        IP-keyed limits is unbounded. Intended to run periodically from the
        worker, not on the request path — a request that occasionally pays for a
        bulk delete has a latency outlier nobody can explain.

        Returns:
            The number of counters removed.
        """
        now = now or datetime.now(UTC)
        deleted = session.execute(
            sa.delete(schema.rate_limit_counter)
            .where(schema.rate_limit_counter.c.window_start < now - older_than)
            .returning(schema.rate_limit_counter.c.subject)
        ).all()
        return len(deleted)
