"""Tests for the contact-confidence lifecycle and send eligibility.

The single most important property here is that no path leads from research
evidence to a sendable recipient. Several tests assert that directly, because it
is the rule that keeps SmartMatch inside Resend's acceptable-use policy.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from smartmatch_domain.consent import (
    APPROVED_CONSENT_SOURCES,
    STATE_TRANSITIONS,
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_send_eligible,
    assert_transition,
    can_transition,
    is_send_eligible,
)


def test_happy_path_walks_discovery_to_active_candidate():
    """The full lifecycle is reachable — but only in order, and only via consent."""
    path = [
        ContactState.DISCOVERED,
        ContactState.CORROBORATED,
        ContactState.REVIEWED,
        ContactState.RELATIONSHIP_RECORDED,
        ContactState.CONSENTED,
        ContactState.ACTIVE_CANDIDATE,
    ]
    for current, following in pairwise(path):
        source = ConsentSource.SELF_SERVICE if following is ContactState.CONSENTED else None
        assert_transition(current, following, consent_source=source)


def test_no_research_state_reaches_active_candidate_without_consent():
    """The core rule of v1.1 §2.3, asserted over every research state."""
    research_states = [
        ContactState.DISCOVERED,
        ContactState.CORROBORATED,
        ContactState.REVIEWED,
        ContactState.RELATIONSHIP_RECORDED,
    ]
    for state in research_states:
        assert not can_transition(state, ContactState.ACTIVE_CANDIDATE), (
            f"{state.value} can reach active_candidate without passing through "
            "consented — this would make scraped contacts send-eligible"
        )


def test_consented_is_the_only_predecessor_of_active_candidate():
    """Stated as a graph property so a future edit cannot quietly add a shortcut."""
    predecessors = {
        state
        for state, allowed in STATE_TRANSITIONS.items()
        if ContactState.ACTIVE_CANDIDATE in allowed
    }
    assert predecessors == {ContactState.CONSENTED}


def test_reaching_consented_requires_a_consent_source():
    with pytest.raises(ConsentViolationError, match="consent source is required"):
        assert_transition(ContactState.RELATIONSHIP_RECORDED, ContactState.CONSENTED)


@pytest.mark.parametrize(
    "source",
    [ConsentSource.SCRAPED, ConsentSource.PURCHASED, ConsentSource.INFERRED],
)
def test_unapproved_consent_sources_are_rejected(source: ConsentSource):
    """Scraped, purchased, and inferred addresses are evidence, never permission."""
    with pytest.raises(ConsentViolationError, match="not an approved consent source"):
        assert_transition(
            ContactState.RELATIONSHIP_RECORDED,
            ContactState.CONSENTED,
            consent_source=source,
        )


@pytest.mark.parametrize("source", sorted(APPROVED_CONSENT_SOURCES, key=lambda s: s.value))
def test_approved_consent_sources_are_accepted(source: ConsentSource):
    assert_transition(
        ContactState.RELATIONSHIP_RECORDED,
        ContactState.CONSENTED,
        consent_source=source,
    )


def test_rejected_is_terminal():
    """A rejected candidate cannot be quietly revived."""
    assert STATE_TRANSITIONS[ContactState.REJECTED] == frozenset()


def test_illegal_transition_is_refused():
    with pytest.raises(ConsentViolationError, match="illegal contact lifecycle"):
        assert_transition(
            ContactState.DISCOVERED,
            ContactState.CONSENTED,
            consent_source=ConsentSource.SELF_SERVICE,
        )


def test_stale_returns_to_review_not_straight_back_to_active():
    """Re-verification goes through a human, as it did the first time."""
    assert can_transition(ContactState.STALE, ContactState.REVIEWED)
    assert not can_transition(ContactState.STALE, ContactState.ACTIVE_CANDIDATE)


# ---------------------------------------------------------------------------
# Send eligibility
# ---------------------------------------------------------------------------


def test_send_eligible_only_when_all_three_conditions_hold():
    assert is_send_eligible(
        ContactState.ACTIVE_CANDIDATE,
        consent_source=ConsentSource.SELF_SERVICE,
        suppressed=False,
    )


def test_suppression_blocks_send_even_for_a_consented_active_candidate():
    assert not is_send_eligible(
        ContactState.ACTIVE_CANDIDATE,
        consent_source=ConsentSource.SELF_SERVICE,
        suppressed=True,
    )
    with pytest.raises(ConsentViolationError, match="suppressed"):
        assert_send_eligible(
            ContactState.ACTIVE_CANDIDATE,
            consent_source=ConsentSource.SELF_SERVICE,
            suppressed=True,
        )


def test_scraped_source_is_never_send_eligible_in_any_state():
    """Belt and braces: even if a state machine bug let it through, sending fails."""
    for state in ContactState:
        assert not is_send_eligible(state, consent_source=ConsentSource.SCRAPED, suppressed=False)


def test_missing_consent_source_is_not_send_eligible():
    assert not is_send_eligible(
        ContactState.ACTIVE_CANDIDATE, consent_source=None, suppressed=False
    )


def test_non_active_states_are_not_send_eligible():
    for state in ContactState:
        if state is ContactState.ACTIVE_CANDIDATE:
            continue
        assert not is_send_eligible(
            state, consent_source=ConsentSource.SELF_SERVICE, suppressed=False
        )


def test_send_violation_is_a_permission_error():
    """Fails closed everywhere it is raised, including in generic handlers."""
    assert issubclass(ConsentViolationError, PermissionError)
