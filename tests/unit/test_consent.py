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
    ESCALATING_STATES,
    REGISTRABLE_STATES,
    STATE_TRANSITIONS,
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_registrable,
    assert_send_eligible,
    assert_transition,
    can_transition,
    is_escalation,
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


# ---------------------------------------------------------------------------
# Registration — the invite-to-consent loophole, closed at its cheapest entry
#
# `assert_registrable` exists because a create has no prior state, so
# `assert_transition` has no edge to check and a surface that asked it anyway
# would have to invent a predecessor. These tests pin what a create may assert.
# ---------------------------------------------------------------------------


def test_a_contact_cannot_be_created_already_send_eligible():
    """The whole card in one assertion: creation alone grants nothing."""
    with pytest.raises(ConsentViolationError, match="cannot be created in"):
        assert_registrable(ContactState.ACTIVE_CANDIDATE, consent_source=ConsentSource.IN_PERSON)


def test_active_candidate_is_not_registrable_even_with_every_approved_source():
    """No approved source buys a shortcut past the activation step."""
    for source in APPROVED_CONSENT_SOURCES:
        with pytest.raises(ConsentViolationError, match="cannot be created in"):
            assert_registrable(ContactState.ACTIVE_CANDIDATE, consent_source=source)


def test_registrable_states_exclude_active_candidate_as_a_set_property():
    """Stated as a set property so a future edit cannot quietly add it back."""
    assert ContactState.ACTIVE_CANDIDATE not in REGISTRABLE_STATES
    assert sorted(s.value for s in REGISTRABLE_STATES) == ["consented", "discovered"]


def test_registering_as_discovered_asserts_nothing_and_needs_no_source():
    """Holding an address is not a claim about permission, so none is demanded."""
    assert_registrable(ContactState.DISCOVERED)


def test_registering_as_consented_requires_a_source():
    with pytest.raises(ConsentViolationError, match="consent source is required"):
        assert_registrable(ContactState.CONSENTED)


@pytest.mark.parametrize(
    "source",
    [ConsentSource.SCRAPED, ConsentSource.PURCHASED, ConsentSource.INFERRED],
)
def test_registering_as_consented_refuses_research_provenance(source: ConsentSource):
    """A scraped address may be *recorded*; it may never be recorded as consented."""
    with pytest.raises(ConsentViolationError, match="not an approved consent source"):
        assert_registrable(ContactState.CONSENTED, consent_source=source)


@pytest.mark.parametrize("source", sorted(APPROVED_CONSENT_SOURCES, key=lambda s: s.value))
def test_registering_as_consented_accepts_the_four_approved_sources(source: ConsentSource):
    assert_registrable(ContactState.CONSENTED, consent_source=source)


def test_a_registrable_consented_contact_is_still_not_send_eligible():
    """Registration at `consented` is a permission on file, not a live recipient.

    This is the pairing the card turns on: the strictest legal create still
    produces something no send may address, because `is_send_eligible` accepts
    `active_candidate` and nothing else.
    """
    assert_registrable(ContactState.CONSENTED, consent_source=ConsentSource.IN_PERSON)
    assert not is_send_eligible(
        ContactState.CONSENTED, consent_source=ConsentSource.IN_PERSON, suppressed=False
    )


# ---------------------------------------------------------------------------
# Suppression wins over the lifecycle, not merely over the send
# ---------------------------------------------------------------------------


def test_escalating_states_are_derived_from_the_send_rule():
    """The set paraphrases `is_send_eligible`, so it cannot drift from it."""
    assert sorted(s.value for s in ESCALATING_STATES) == ["active_candidate", "consented"]
    for state in ContactState:
        assert is_escalation(state) == (state in ESCALATING_STATES)


def test_suppression_blocks_activation_of_a_properly_consented_contact():
    """The one move that would make a suppressed person writable-to."""
    # Legal, correctly sourced, and refused anyway — on suppression alone.
    assert_transition(ContactState.CONSENTED, ContactState.ACTIVE_CANDIDATE)
    with pytest.raises(ConsentViolationError, match="suppressed"):
        assert_transition(ContactState.CONSENTED, ContactState.ACTIVE_CANDIDATE, suppressed=True)


def test_suppression_blocks_reaching_consented_from_an_approved_source():
    """Suppression outranks the approval, not the other way round."""
    with pytest.raises(ConsentViolationError, match="suppressed"):
        assert_transition(
            ContactState.RELATIONSHIP_RECORDED,
            ContactState.CONSENTED,
            consent_source=ConsentSource.IN_PERSON,
            suppressed=True,
        )


def test_suppression_is_reported_ahead_of_edge_legality():
    """An illegal *and* suppressed move names the suppression, not the edge.

    The order matters to the person reading the refusal: an edge error reads as
    "try a different move", and for a suppressed address there is no move.
    """
    with pytest.raises(ConsentViolationError, match="suppressed"):
        assert_transition(
            ContactState.DISCOVERED,
            ContactState.ACTIVE_CANDIDATE,
            consent_source=ConsentSource.IN_PERSON,
            suppressed=True,
        )


def test_suppression_does_not_block_de_escalating_moves():
    """Recording that a suppressed contact went stale or was rejected still works.

    Suppression forbids moves *toward* a send. Forbidding every move as well
    would freeze a suppressed contact in whatever state it was in, which records
    the person's wishes less accurately rather than more.
    """
    assert_transition(ContactState.ACTIVE_CANDIDATE, ContactState.STALE, suppressed=True)
    assert_transition(ContactState.REVIEWED, ContactState.REJECTED, suppressed=True)


def test_every_escalating_move_in_the_state_machine_is_refused_when_suppressed():
    """Exhaustive over the graph, so a new edge into either state is covered."""
    for current, allowed in STATE_TRANSITIONS.items():
        for requested in allowed:
            if requested not in ESCALATING_STATES:
                continue
            with pytest.raises(ConsentViolationError, match="suppressed"):
                assert_transition(
                    current,
                    requested,
                    consent_source=ConsentSource.IN_PERSON,
                    suppressed=True,
                )


def test_suppression_defaults_off_so_existing_callers_are_unchanged():
    """The keyword is opt-in; a caller that cannot see suppression is not lied to."""
    assert_transition(
        ContactState.RELATIONSHIP_RECORDED,
        ContactState.CONSENTED,
        consent_source=ConsentSource.IN_PERSON,
    )
