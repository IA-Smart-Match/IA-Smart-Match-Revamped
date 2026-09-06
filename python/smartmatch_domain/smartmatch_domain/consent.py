"""Contact-confidence lifecycle and send eligibility.

Architecture v1.1 §2.3. Encodes the single rule that keeps SmartMatch inside
Resend's acceptable-use policy: **research evidence is never send-eligible.**

There is no transition from any research state to ``RECIPIENT`` except through
``CONSENTED``, and ``CONSENTED`` requires an approved consent source. A public
business email discovered by the research pipeline is evidence about a person,
not permission to contact them — and an email asking a scraped address to opt in
is itself prohibited outreach, which is why no "invite to consent" path exists
here.

This replaces the v1.0 circular opt-in design (v1.1 Appendix A, diagram 17).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "APPROVED_CONSENT_SOURCES",
    "ESCALATING_STATES",
    "REGISTRABLE_STATES",
    "STATE_TRANSITIONS",
    "ConsentSource",
    "ConsentViolationError",
    "ContactState",
    "assert_registrable",
    "assert_send_eligible",
    "assert_transition",
    "can_transition",
    "is_escalation",
    "is_send_eligible",
]


class ContactState(StrEnum):
    """States in the contact-confidence lifecycle (v1.1 §2.3)."""

    DISCOVERED = "discovered"
    CORROBORATED = "corroborated"
    REVIEWED = "reviewed"
    RELATIONSHIP_RECORDED = "relationship_recorded"
    REJECTED = "rejected"
    CONSENTED = "consented"
    ACTIVE_CANDIDATE = "active_candidate"
    STALE = "stale"


class ConsentSource(StrEnum):
    """Where a consent record originated."""

    #: The person opted in themselves through a SmartMatch form.
    SELF_SERVICE = "self_service"
    #: The person opted in while authenticated to their own profile.
    AUTHENTICATED = "authenticated"
    #: Recorded in person by a coordinator, with an audit trail.
    IN_PERSON = "in_person"
    #: An institutionally approved pre-existing relationship.
    INSTITUTIONAL_RELATIONSHIP = "institutional_relationship"

    # --- Never valid. Present so the rejection is explicit and testable. ---
    #: Address found by the research pipeline. Evidence, never permission.
    SCRAPED = "scraped"
    #: Address obtained from a list vendor.
    PURCHASED = "purchased"
    #: Address inferred by a model.
    INFERRED = "inferred"


#: The closed set of sources that may produce a ``CONSENTED`` record.
APPROVED_CONSENT_SOURCES: Final[frozenset[ConsentSource]] = frozenset(
    {
        ConsentSource.SELF_SERVICE,
        ConsentSource.AUTHENTICATED,
        ConsentSource.IN_PERSON,
        ConsentSource.INSTITUTIONAL_RELATIONSHIP,
    }
)

#: Legal lifecycle transitions, transcribed from the v1.1 §2.3 state diagram.
#: Note there is no edge from any research state directly to ACTIVE_CANDIDATE.
STATE_TRANSITIONS: Final[Mapping[ContactState, frozenset[ContactState]]] = MappingProxyType(
    {
        ContactState.DISCOVERED: frozenset({ContactState.CORROBORATED}),
        ContactState.CORROBORATED: frozenset({ContactState.REVIEWED}),
        ContactState.REVIEWED: frozenset(
            {ContactState.RELATIONSHIP_RECORDED, ContactState.REJECTED}
        ),
        ContactState.RELATIONSHIP_RECORDED: frozenset({ContactState.CONSENTED}),
        ContactState.CONSENTED: frozenset({ContactState.ACTIVE_CANDIDATE}),
        ContactState.ACTIVE_CANDIDATE: frozenset({ContactState.STALE}),
        ContactState.STALE: frozenset({ContactState.REVIEWED}),
        ContactState.REJECTED: frozenset(),
    }
)


#: The two states that *increase* what may be done to a person: reaching either
#: moves a contact closer to being written to, and ``ACTIVE_CANDIDATE`` is the
#: one state :func:`is_send_eligible` accepts at all.
#:
#: Derived rather than typed out, so it cannot drift from the send rule it
#: paraphrases: ``ACTIVE_CANDIDATE`` because that is what a send requires, and
#: whatever leads directly into it because that is the last human decision before
#: it. Today that is ``CONSENTED`` alone, which
#: ``test_consented_is_the_only_predecessor_of_active_candidate`` already pins.
ESCALATING_STATES: Final[frozenset[ContactState]] = frozenset(
    {ContactState.ACTIVE_CANDIDATE}
    | {
        state
        for state, allowed in STATE_TRANSITIONS.items()
        if ContactState.ACTIVE_CANDIDATE in allowed
    }
)

#: The only states a contact may be *created* in.
#:
#: ``ACTIVE_CANDIDATE`` is deliberately absent, and its absence is the whole
#: point: activation is an act with an actor and a trail entry, never an initial
#: value. Creating a row already sendable would make "who activated this person"
#: a question with no answer, which is the shape a coordinator surface must not
#: be able to produce. The research states past ``DISCOVERED`` are absent for a
#: quieter reason — a contact that has been corroborated or reviewed got there by
#: somebody doing that, so registering directly into one asserts work nobody did.
REGISTRABLE_STATES: Final[frozenset[ContactState]] = frozenset(
    {ContactState.DISCOVERED, ContactState.CONSENTED}
)


class ConsentViolationError(PermissionError):
    """Raised when an operation would contact someone without valid consent.

    A ``PermissionError`` rather than a ``ValueError``: this is an authorization
    failure, and it must fail closed everywhere it is raised.
    """


def can_transition(current: ContactState, requested: ContactState) -> bool:
    """Return whether ``current -> requested`` is a legal lifecycle move."""
    return requested in STATE_TRANSITIONS[current]


def is_escalation(requested: ContactState) -> bool:
    """Return whether moving to ``requested`` brings a contact closer to a send."""
    return requested in ESCALATING_STATES


def assert_registrable(
    initial: ContactState,
    *,
    consent_source: ConsentSource | None = None,
) -> None:
    """Raise unless a contact may be *created* in ``initial``.

    Registration is not a transition — there is no prior state to check an edge
    against — so :func:`assert_transition` cannot answer this, and a surface that
    asked it anyway would have to invent a fake predecessor. What can be checked
    is that the initial state is one a create is allowed to assert, and that a
    create asserting consent names an approved source for it.

    This is the rule that closes the invite-to-consent loophole at its cheapest
    entry point. A form that types an address and a state in one request is
    exactly where "created, therefore contactable" would slip in; here creating
    a contact can assert at most that the address is *held*, or that a named,
    approved, dated permission already exists — never that the person is live.

    Args:
        initial: The state the caller wants the new contact created in.
        consent_source: Required when ``initial`` is ``CONSENTED``.

    Raises:
        ConsentViolationError: if ``initial`` is not registrable, or if a
            registration at ``CONSENTED`` lacks an approved consent source.
    """
    if initial not in REGISTRABLE_STATES:
        allowed = sorted(s.value for s in REGISTRABLE_STATES)
        raise ConsentViolationError(
            f"a contact cannot be created in {initial.value!r}; a create may assert "
            f"only {allowed}. Activation is an act with an actor and a recorded "
            "move, never an initial value (v1.1 §2.3)."
        )

    if initial is ContactState.CONSENTED:
        _assert_approved_source(consent_source)


def assert_transition(
    current: ContactState,
    requested: ContactState,
    *,
    consent_source: ConsentSource | None = None,
    suppressed: bool = False,
) -> None:
    """Raise unless the lifecycle transition is legal and properly sourced.

    Args:
        current: The contact's present state.
        requested: The state being moved to.
        consent_source: Required when ``requested`` is ``CONSENTED``. Must be
            one of :data:`APPROVED_CONSENT_SOURCES`.
        suppressed: Whether this address is under a suppression record. When it
            is, no move into :data:`ESCALATING_STATES` is permitted — checked
            **first**, ahead of edge legality, because suppression wins over
            every other fact about the contact. Defaults to ``False`` so that
            existing callers keep their present behaviour, and a caller that can
            see the suppression is expected to pass it.

    Raises:
        ConsentViolationError: if the address is suppressed and the move would
            escalate it, if the transition is illegal, or if a move to
            ``CONSENTED`` lacks an approved consent source.
    """
    # Suppression is asked before legality on purpose. A suppressed person who
    # is also mid-lifecycle would otherwise get the *edge* refusal, which reads
    # as "try a different move" — and the answer is that there is no move.
    if suppressed and is_escalation(requested):
        raise ConsentViolationError(
            f"this address is suppressed; it cannot move to {requested.value!r}. "
            "A suppression is a person saying stop, and it outranks every consent "
            "record, lifecycle state, and approval that might otherwise permit a "
            "send (v1.1 §1.8)."
        )

    if not can_transition(current, requested):
        allowed = sorted(s.value for s in STATE_TRANSITIONS[current])
        raise ConsentViolationError(
            f"illegal contact lifecycle transition {current.value!r} -> "
            f"{requested.value!r}; legal moves are {allowed or ['(terminal)']}"
        )

    if requested is ContactState.CONSENTED:
        _assert_approved_source(consent_source)


def _assert_approved_source(consent_source: ConsentSource | None) -> None:
    """Raise unless ``consent_source`` is one of the four approved origins.

    Shared by :func:`assert_transition` and :func:`assert_registrable` rather
    than written twice, so the closed set of four has exactly one gate. Two
    copies of this check would be two places a fifth source could be admitted.
    """
    if consent_source is None:
        raise ConsentViolationError(
            "a consent source is required to reach 'consented'; consent "
            "originates only through self-service, authenticated, in-person, or "
            "institutionally approved pre-existing relationships (v1.1 §2.3)"
        )
    if consent_source not in APPROVED_CONSENT_SOURCES:
        raise ConsentViolationError(
            f"{consent_source.value!r} is not an approved consent source. "
            "Scraped, purchased, and inferred addresses are research evidence, "
            "never permission to contact — and an email asking such an address "
            "to opt in is itself prohibited outreach (v1.1 §1.8)."
        )


def is_send_eligible(
    state: ContactState,
    *,
    consent_source: ConsentSource | None,
    suppressed: bool,
) -> bool:
    """Return whether a recipient may be sent to.

    All three conditions are necessary: the contact has reached an active,
    consented state; the consent came from an approved source; and no
    suppression applies. This is one of the five gates the worker rechecks at
    send time (v1.1 §1.8) — never the only one.
    """
    if suppressed:
        return False
    if state is not ContactState.ACTIVE_CANDIDATE:
        return False
    return consent_source in APPROVED_CONSENT_SOURCES


def assert_send_eligible(
    state: ContactState,
    *,
    consent_source: ConsentSource | None,
    suppressed: bool,
) -> None:
    """Raise unless the recipient may be sent to.

    Raises:
        ConsentViolationError: with the specific failing condition named, so the
            blocked send attempt can be audited with a reason (v1.1 §1.8).
    """
    if suppressed:
        raise ConsentViolationError("recipient is suppressed; send blocked")
    if state is not ContactState.ACTIVE_CANDIDATE:
        raise ConsentViolationError(
            f"recipient is in state {state.value!r}, not 'active_candidate'; send blocked"
        )
    if consent_source not in APPROVED_CONSENT_SOURCES:
        raise ConsentViolationError(
            f"consent source {consent_source.value if consent_source else None!r} is not "
            "approved; send blocked"
        )
