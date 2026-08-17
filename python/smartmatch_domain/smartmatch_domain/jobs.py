"""Durable job state machine.

Architecture v1.1 §1.7. Encodes the legal transitions as data so both the API
and the worker validate against one definition rather than each re-implementing
the rules.

Two states carry specific corrections from v1.0:

* ``PARTIAL`` — the state the legacy agentic stream refused to represent. Work
  that half-succeeded is labeled as such, with results retained; it is never
  reported as success (v1.1 §3.6 N2).
* ``REDRIVE_PENDING`` — replaces the v1.0 ``dead_letter`` state. Cloud Tasks has
  no native dead-letter queue, so terminal failures park in a PostgreSQL table
  and re-drive is an authorized, audited command (v1.1 §1.6).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "TERMINAL_STATES",
    "TRANSITIONS",
    "InvalidTransitionError",
    "JobState",
    "assert_transition",
    "can_transition",
    "is_terminal",
]


class JobState(StrEnum):
    """Every state a durable job may occupy."""

    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED_PROVIDER = "failed_provider"
    FAILED_BUDGET = "failed_budget"
    FAILED_POLICY = "failed_policy"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    REDRIVE_PENDING = "redrive_pending"
    ABANDONED = "abandoned"


#: Legal transitions, transcribed from the v1.1 §1.7 state diagram.
TRANSITIONS: Final[Mapping[JobState, frozenset[JobState]]] = MappingProxyType(
    {
        JobState.QUEUED: frozenset({JobState.DISPATCHED, JobState.CANCELLED}),
        JobState.DISPATCHED: frozenset({JobState.RUNNING, JobState.CANCELLED}),
        JobState.RUNNING: frozenset(
            {
                JobState.SUCCEEDED,
                JobState.PARTIAL,
                JobState.FAILED_PROVIDER,
                JobState.FAILED_BUDGET,
                JobState.FAILED_POLICY,
                JobState.CANCELLED,
                JobState.TIMED_OUT,
            }
        ),
        # Bounded automatic retry returns to queued; exhausted retries park.
        JobState.FAILED_PROVIDER: frozenset({JobState.QUEUED, JobState.REDRIVE_PENDING}),
        JobState.TIMED_OUT: frozenset({JobState.QUEUED, JobState.REDRIVE_PENDING}),
        # Re-drive is an authorized command, and attempt history is preserved.
        JobState.REDRIVE_PENDING: frozenset({JobState.QUEUED, JobState.ABANDONED}),
        JobState.SUCCEEDED: frozenset(),
        JobState.PARTIAL: frozenset(),
        JobState.CANCELLED: frozenset(),
        JobState.FAILED_BUDGET: frozenset(),
        JobState.FAILED_POLICY: frozenset(),
        JobState.ABANDONED: frozenset(),
    }
)

#: States from which no further transition is legal.
TERMINAL_STATES: Final[frozenset[JobState]] = frozenset(
    state for state, allowed in TRANSITIONS.items() if not allowed
)


class InvalidTransitionError(ValueError):
    """Raised when a caller attempts an illegal job state transition."""

    def __init__(self, current: JobState, requested: JobState) -> None:
        allowed = sorted(s.value for s in TRANSITIONS[current])
        super().__init__(
            f"cannot move job from {current.value!r} to {requested.value!r}; "
            f"legal transitions are {allowed or ['(terminal)']}"
        )
        self.current = current
        self.requested = requested


def can_transition(current: JobState, requested: JobState) -> bool:
    """Return whether ``current -> requested`` is legal."""
    return requested in TRANSITIONS[current]


def assert_transition(current: JobState, requested: JobState) -> None:
    """Raise unless ``current -> requested`` is legal.

    Raises:
        InvalidTransitionError: if the transition is not in :data:`TRANSITIONS`.
    """
    if not can_transition(current, requested):
        raise InvalidTransitionError(current, requested)


def is_terminal(state: JobState) -> bool:
    """Return whether ``state`` admits no further transitions."""
    return state in TERMINAL_STATES
