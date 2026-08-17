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

from enum import Enum
from types import MappingProxyType
from typing import Final, Mapping

__all__ = [
    "ContactState",
    "ConsentSource",
    "APPROVED_CONSENT_SOURCES",
    "ConsentViolationError",
    "STATE_TRANSITIONS",
    "can_transition",
    "assert_transition",
    "is_send_eligible",
    "assert_send_eligible",
]


class ContactState(str, Enum):
    """States in the contact-confidence lifecycle (v1.1 §2.3)."""

    DISCOVERED = "discovered"
    CORROBORATED = "corroborated"
    REVIEWED = "reviewed"
    RELATIONSHIP_RECORDED = "relationship_recorded"
    REJECTED = "rejected"
    CONSENTED = "consented"
    ACTIVE_CANDIDATE = "active_candidate"
    STALE = "stale"


class ConsentSource(str, Enum):
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


class ConsentViolationError(PermissionError):
    """Raised when an operation would contact someone without valid consent.

    A ``PermissionError`` rather than a ``ValueError``: this is an authorization
    failure, and it must fail closed everywhere it is raised.
    """


def can_transition(current: ContactState, requested: ContactState) -> bool:
    """Return whether ``current -> requested`` is a legal lifecycle move."""
    return requested in STATE_TRANSITIONS[current]


def assert_transition(
    current: ContactState,
    requested: ContactState,
    *,
    consent_source: ConsentSource | None = None,
) -> None:
    """Raise unless the lifecycle transition is legal and properly sourced.

    Args:
        current: The contact's present state.
        requested: The state being moved to.
        consent_source: Required when ``requested`` is ``CONSENTED``. Must be
            one of :data:`APPROVED_CONSENT_SOURCES`.

    Raises:
        ConsentViolationError: if the transition is illegal, or if a move to
            ``CONSENTED`` lacks an approved consent source.
    """
    if not can_transition(current, requested):
        allowed = sorted(s.value for s in STATE_TRANSITIONS[current])
        raise ConsentViolationError(
            f"illegal contact lifecycle transition {current.value!r} -> "
            f"{requested.value!r}; legal moves are {allowed or ['(terminal)']}"
        )

    if requested is ContactState.CONSENTED:
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
