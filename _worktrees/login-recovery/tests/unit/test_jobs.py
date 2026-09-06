"""Tests for the durable job state machine (v1.1 §1.7)."""

from __future__ import annotations

import pytest
from smartmatch_domain.jobs import (
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransitionError,
    JobState,
    assert_transition,
    can_transition,
    is_terminal,
)


def test_every_state_has_a_transition_entry():
    """A state missing from the table would raise KeyError at runtime."""
    assert set(TRANSITIONS) == set(JobState)


def test_normal_lifecycle():
    for current, following in [
        (JobState.QUEUED, JobState.DISPATCHED),
        (JobState.DISPATCHED, JobState.RUNNING),
        (JobState.RUNNING, JobState.SUCCEEDED),
    ]:
        assert_transition(current, following)


def test_partial_is_representable_and_terminal():
    """The state the legacy agentic stream refused to represent."""
    assert can_transition(JobState.RUNNING, JobState.PARTIAL)
    assert is_terminal(JobState.PARTIAL)


def test_provider_failure_retries_then_parks_for_redrive():
    assert can_transition(JobState.FAILED_PROVIDER, JobState.QUEUED)
    assert can_transition(JobState.FAILED_PROVIDER, JobState.REDRIVE_PENDING)


def test_timeout_follows_the_same_retry_and_redrive_path():
    assert can_transition(JobState.TIMED_OUT, JobState.QUEUED)
    assert can_transition(JobState.TIMED_OUT, JobState.REDRIVE_PENDING)


def test_redrive_requires_an_explicit_move_and_can_be_abandoned():
    """Re-drive is an authorized command, not an automatic retry."""
    assert can_transition(JobState.REDRIVE_PENDING, JobState.QUEUED)
    assert can_transition(JobState.REDRIVE_PENDING, JobState.ABANDONED)


def test_budget_and_policy_failures_are_terminal_not_retryable():
    """Retrying a budget or authorization failure would just burn quota.

    v1.1 §1.8: never retry validation, recipient, policy, or auth errors without
    intervention.
    """
    assert is_terminal(JobState.FAILED_BUDGET)
    assert is_terminal(JobState.FAILED_POLICY)


def test_cancellation_is_reachable_before_and_during_execution():
    assert can_transition(JobState.QUEUED, JobState.CANCELLED)
    assert can_transition(JobState.DISPATCHED, JobState.CANCELLED)
    assert can_transition(JobState.RUNNING, JobState.CANCELLED)


def test_succeeded_is_terminal():
    assert is_terminal(JobState.SUCCEEDED)
    with pytest.raises(InvalidTransitionError):
        assert_transition(JobState.SUCCEEDED, JobState.RUNNING)


def test_cannot_skip_dispatch():
    """A job cannot run without the outbox dispatcher having created a task."""
    with pytest.raises(InvalidTransitionError):
        assert_transition(JobState.QUEUED, JobState.RUNNING)


def test_cannot_resurrect_a_cancelled_job():
    with pytest.raises(InvalidTransitionError):
        assert_transition(JobState.CANCELLED, JobState.QUEUED)


def test_terminal_states_match_the_empty_transition_sets():
    expected = {
        JobState.SUCCEEDED,
        JobState.PARTIAL,
        JobState.CANCELLED,
        JobState.FAILED_BUDGET,
        JobState.FAILED_POLICY,
        JobState.ABANDONED,
    }
    assert expected == TERMINAL_STATES


def test_error_message_lists_the_legal_moves():
    """Operators debugging a stuck job should not have to read the source."""
    with pytest.raises(InvalidTransitionError, match="dispatched"):
        assert_transition(JobState.QUEUED, JobState.SUCCEEDED)


def test_transition_table_is_immutable():
    with pytest.raises(TypeError):
        TRANSITIONS[JobState.SUCCEEDED] = frozenset({JobState.RUNNING})  # type: ignore[index]
