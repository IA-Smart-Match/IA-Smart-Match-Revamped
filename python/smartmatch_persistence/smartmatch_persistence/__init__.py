"""PostgreSQL persistence for SmartMatch.

Architecture v1.1 §2.4 and §3.1: PostgreSQL is the single authoritative store
*and* the coordination store at pilot scale. Redis, Pub/Sub, and BigQuery are
deferred with objective adoption triggers, so everything durable — job state,
the outbox, budgets, concurrency leases, and SSE cursors — lives here.

This package holds table definitions and repositories. It depends on
``smartmatch_domain`` for enums and rules; the dependency never runs the other
way, which is enforced by the import-linter layering contract.
"""

from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.idempotency import (
    IdempotencyConflictError,
    IdempotencyRepository,
    IdempotencyResult,
)
from smartmatch_persistence.jobs import JobRecord, JobRepository
from smartmatch_persistence.outbox import (
    ClaimedOutboxRecord,
    OutboxRepository,
    OutboxStatus,
)

__all__ = [
    "ClaimedOutboxRecord",
    "IdempotencyConflictError",
    "IdempotencyRepository",
    "IdempotencyResult",
    "JobRecord",
    "JobRepository",
    "OutboxRepository",
    "OutboxStatus",
    "create_session_factory",
]

__version__ = "0.1.0"
