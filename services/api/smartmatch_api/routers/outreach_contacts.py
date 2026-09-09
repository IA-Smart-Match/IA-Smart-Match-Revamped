"""Contact channels: register one, correct its evidence, move it through consent.

``routers/outreach.py`` is the surface that *writes to* people. This one is the
surface that decides who those people are, which is the operational half of
OQ-004: migration ``0021`` created ``contact_channel`` and deliberately seeded
nothing, because every row asserts that a named person agreed to be contacted
and a migration is not in a position to make that assertion. A coordinator is.
Until this module existed there was no way for one to say so, so the consent
lifecycle in ``smartmatch_domain.consent`` was a state machine nothing could
drive.

## Five operations

* ``GET   /v1/units/{unit_id}/outreach/contacts`` — a unit's contacts.
* ``GET   /v1/units/{unit_id}/outreach/contacts/{contact_channel_id}`` — one
  contact and its consent history.
* ``POST  /v1/units/{unit_id}/outreach/contacts`` — register one.
* ``PATCH /v1/units/{unit_id}/outreach/contacts/{contact_channel_id}`` —
  correct the consent evidence, or suppress the address.
* ``POST  /v1/units/{unit_id}/outreach/contacts/{contact_channel_id}/transitions``
  — move it, and record who moved it.

They authorize through :func:`~smartmatch_api.routers.outreach._authorize_outreach`
— the *same* function the draft and send routes call, against the same
``org_unit`` resource — rather than a second helper of their own. That is not
convenience: it is what makes "may this caller work with this unit's outreach"
one question with one answer, so a widening applies to all of it or to none of
it and cannot reach the contact routes by accident. ``tests/authz`` holds this
to it in both directions.

## The state machine lives in one place, and it is not this one

Every move is checked with ``smartmatch_domain.consent.can_transition`` and
``assert_transition``. This module contains no edge list, no "allowed next
states" table, and no shortcut past either — it reads the contact's present
state from the database, asks the domain whether the requested move is legal,
and either performs it or reports why not. A router that decided legality itself
would be a second copy of ``STATE_TRANSITIONS`` free to disagree with the first,
and the disagreement would be invisible until a legal move started failing in
production.

The database enforces the narrower rule underneath both (arriving at
``consented`` names an approved source), for the reason migration ``0021``
gives: an application check stops application code, and a CHECK constraint stops
a hand-written INSERT in a psql session.

## Two refusals with different meanings, and different status codes

An **illegal edge** — ``discovered`` straight to ``active_candidate``, say — is a
``409``. The caller is permitted to work with this contact, and the contact is
in a state where the requested move does not mean anything yet; a ``403`` would
send them looking at their roles for a problem that is about the resource.

An **unapproved consent source** — scraped, purchased, inferred — is a ``403``.
That is not a state problem and no sequence of legal moves fixes it: research
evidence is never permission, and an email asking a scraped address to opt in is
itself prohibited outreach (v1.1 §1.8). Reporting it as a validation error would
invite the caller to try different inputs, and there are none that work.

## What registration will not do

A contact may be registered in exactly two states: ``discovered``, which asserts
nothing beyond "we have this address", and ``consented``, which asserts that a
named person agreed and names the approved source and the evidence. It may
**not** be registered directly as ``active_candidate``, even though the database
would accept the row: activation is a separate act by a named actor, and
allowing it in the same call would mean the audit trail could contain a
send-eligible contact with no recorded moment at which anyone activated it.

There is no bulk import here and no self-service opt-in form. Both are OQ-004's
remaining half and are deferred deliberately — see
``docs/plans/open-questions/r4-outreach-deferred.md``.

## Quota is charged first

ADR-0015's ordering, ahead of the load, the authorization, and the validation,
as every other route in this package does it.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel, Field
from smartmatch_domain.consent import (
    APPROVED_CONSENT_SOURCES,
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_transition,
    can_transition,
    is_send_eligible,
)
from smartmatch_persistence.contacts import (
    DEFAULT_CONTACT_PAGE_SIZE,
    MAX_CONTACT_PAGE_SIZE,
    ContactChannelRepository,
    ContactChannelRow,
)
from smartmatch_persistence.outreach import OutreachRepository
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.routers.outreach import READ_RATE_LIMIT, _authorize_outreach
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["outreach"])

_contacts: Final[ContactChannelRepository] = ContactChannelRepository()

#: Suppression is written through the outreach repository rather than duplicated
#: here, because ``suppression_record`` is one authoritative list and a second
#: writer with its own idempotency rule would be a second answer to "has this
#: person told us to stop".
_outreach: Final[OutreachRepository] = OutreachRepository()

#: Tighter than the draft limit and for a different reason. Registering contacts
#: is the operation that grows the set of people this platform can write to, so
#: the ceiling is set where a mistake is still a handful of rows a person can
#: review rather than a list.
CONTACT_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="outreach.contact.write", max_requests=30, window=timedelta(minutes=1)
)

#: The states a contact may be *created* in. See the module docstring: not
#: ``active_candidate``, which is an act rather than an initial condition.
_REGISTRABLE_STATES: Final[frozenset[ContactState]] = frozenset(
    {ContactState.DISCOVERED, ContactState.CONSENTED}
)


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class ContactResponse(BaseModel):
    """One contact channel, with the two facts a coordinator actually needs.

    ``suppressed`` and ``send_eligible`` are both **computed at read time**,
    never stored. ``suppressed`` comes from a join against ``suppression_record``
    (migration ``0021`` explains why there is no column), and ``send_eligible``
    is :func:`smartmatch_domain.consent.is_send_eligible` over this row — the
    same function the send path uses, called here rather than re-expressed, so
    the answer a coordinator reads is the answer the send path will give.

    It is still not a promise. The worker rechecks at delivery time against state
    read then, and this field describes the contact at the instant it was read.
    """

    contact_channel_id: uuid.UUID
    professional_id: uuid.UUID
    channel_kind: str
    address: str
    contact_state: str
    consent_source: str | None
    consent_recorded_at: str | None
    consent_evidence: str | None
    suppressed: bool
    send_eligible: bool = Field(
        description=(
            "Whether this contact could be written to right now: active_candidate, "
            "an approved consent source, and no suppression. Computed at read time "
            "and rechecked by the worker at delivery time."
        )
    )
    created_at: str
    updated_at: str


class ContactListResponse(BaseModel):
    """A page of contacts, and how many were asked for."""

    contacts: list[ContactResponse]
    limit: int
    offset: int


class TransitionView(BaseModel):
    """One entry of a contact's consent history.

    ``from_state`` is ``null`` for the registration entry, which is a real move
    — from not existing to an initial state — rather than a missing value.
    """

    from_state: str | None
    to_state: str
    consent_source: str | None
    consent_evidence: str | None
    reason: str | None
    actor_user_id: uuid.UUID
    occurred_at: str


class ContactWithHistoryResponse(BaseModel):
    """A contact and the trail of every move made to it."""

    contact: ContactResponse
    transitions: list[TransitionView]


class RegisterContactRequest(BaseModel):
    """Register one contact channel.

    ``professional_id`` is supplied rather than looked up: no professional table
    exists in this schema yet (migration ``0012`` records the same situation for
    ``professional_unit_relationship``), so the column is an identifier this
    platform stores and does not resolve. Inventing a lookup that cannot fail
    would be worse than storing what the caller names.
    """

    professional_id: uuid.UUID = Field(description="The person this address belongs to.")
    address: str = Field(
        min_length=3,
        max_length=320,
        description=(
            "The address itself. Pilot data uses RFC 2606 reserved domains "
            "(.invalid), which cannot resolve and therefore cannot be written to by "
            "accident."
        ),
    )
    contact_state: ContactState = Field(
        default=ContactState.DISCOVERED,
        description=(
            "'discovered' (we hold this address, and assert nothing more) or "
            "'consented' (a named person agreed, and this request names the source "
            "and the evidence). Registering directly as 'active_candidate' is "
            "refused: activation is an act with an actor, not an initial state."
        ),
    )
    consent_source: ConsentSource | None = Field(
        default=None,
        description=(
            "Required when registering as 'consented', and then it must be an "
            "approved source. Scraped, purchased, and inferred are storable as "
            "provenance on a 'discovered' contact and can never authorize a send."
        ),
    )
    consent_evidence: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "How the consent was captured — a form submission id, a coordinator's "
            "note, an institutional agreement's reference. Required with a consent "
            "source: an auditor asking to see the evidence needs somewhere for the "
            "answer to live."
        ),
    )
    reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Why this contact is being registered, recorded on its first trail entry.",
    )


class UpdateContactRequest(BaseModel):
    """Correct a contact's evidence, or suppress its address.

    Note what cannot be supplied: **the lifecycle state and the address**. Moving
    a contact is :func:`transition_contact`'s, which writes the audit trail with
    the move; a PATCH that changed state would be a state change with no record
    of who made it. Changing the address would move a recorded consent onto a
    different person, which is the one edit that can never be a correction.
    """

    consent_evidence: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Replaces the stored evidence. Omit to leave it alone.",
    )
    suppressed: bool | None = Field(
        default=None,
        description=(
            "Pass true to record that this address must not be written to again. "
            "False is refused rather than honoured — see the handler: reinstating a "
            "suppressed address is a decision nobody has ratified (OQ-009)."
        ),
    )


class TransitionRequest(BaseModel):
    """Move a contact to the next state in the consent lifecycle."""

    to_state: ContactState = Field(description="The state to move to.")
    consent_source: ConsentSource | None = Field(
        default=None,
        description=(
            "Required to reach 'consented', and then it must be approved. Ignored "
            "for every other move: the source that authorized a contact was recorded "
            "when it reached 'consented', and rewriting it later would redate a "
            "permission granted earlier."
        ),
    )
    consent_evidence: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Required with a consent source, for the reason registration requires it.",
    )
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Why this move was made, in the actor's own words. Recorded on the trail.",
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _view(row: ContactChannelRow) -> ContactResponse:
    """Render one stored contact, computing the two derived facts honestly."""
    return ContactResponse(
        contact_channel_id=row.id,
        professional_id=row.professional_id,
        channel_kind=row.channel_kind,
        address=row.address,
        contact_state=row.contact_state,
        consent_source=row.consent_source,
        consent_recorded_at=(
            row.consent_recorded_at.isoformat() if row.consent_recorded_at is not None else None
        ),
        consent_evidence=row.consent_evidence,
        suppressed=row.suppressed,
        send_eligible=is_send_eligible(
            ContactState(row.contact_state),
            consent_source=(
                ConsentSource(row.consent_source) if row.consent_source is not None else None
            ),
            suppressed=row.suppressed,
        ),
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _load_or_404(
    session: Session,
    principal: CurrentPrincipal,
    *,
    owning_unit_id: uuid.UUID,
    contact_channel_id: uuid.UUID,
) -> ContactChannelRow:
    """The contact, or a 404 that says nothing about which half failed.

    A contact that exists under a *different* unit is reported identically to one
    that does not exist, exactly as ``create_draft`` does it: a 403 would confirm
    that an id the caller may not read names something real.
    """
    row = _contacts.get(
        session, tenant_id=principal.tenant_id, contact_channel_id=contact_channel_id
    )
    if row is None or row.owning_unit_id != owning_unit_id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="contact_channel_not_found",
            message="No such contact channel.",
        )
    return row


def _require_approved_consent(
    source: ConsentSource | None, evidence: str | None, *, to_state: ContactState
) -> None:
    """Refuse a consent claim that names no approved source or no evidence.

    ``assert_transition`` already refuses an unapproved source; this adds the
    evidence half, which the domain does not model because evidence is a stored
    artifact rather than a lifecycle fact. Both are required together for the
    reason ``ck_contact_channel_consent_dated`` pairs source and date: a
    permission nobody can produce evidence for is a permission nobody can audit.
    """
    if source is None:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="outreach_consent_source_required",
            message=(
                f"Reaching {to_state.value!r} requires naming an approved consent "
                "source: self-service, authenticated, in-person, or an "
                "institutionally approved pre-existing relationship (v1.1 §2.3)."
            ),
        )
    if source not in APPROVED_CONSENT_SOURCES:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="outreach_consent_source_not_approved",
            message=(
                f"{source.value!r} is not an approved consent source. Scraped, "
                "purchased, and inferred addresses are research evidence, never "
                "permission to contact — and an email asking such an address to opt "
                "in is itself prohibited outreach (v1.1 §1.8)."
            ),
        )
    if evidence is None or not evidence.strip():
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="outreach_consent_evidence_required",
            message=(
                "A consent source must arrive with the evidence for it — the form "
                "submission, the coordinator's note, the agreement's reference. A "
                "consent record nobody can produce evidence for is one nobody can "
                "audit."
            ),
        )


def _history(
    session: Session, principal: CurrentPrincipal, contact_channel_id: uuid.UUID
) -> list[TransitionView]:
    """One contact's trail, rendered oldest first."""
    return [
        TransitionView(
            from_state=entry.from_state,
            to_state=entry.to_state,
            consent_source=entry.consent_source,
            consent_evidence=entry.consent_evidence,
            reason=entry.reason,
            actor_user_id=entry.actor_user_id,
            occurred_at=entry.occurred_at.isoformat(),
        )
        for entry in _contacts.list_transitions(
            session, tenant_id=principal.tenant_id, contact_channel_id=contact_channel_id
        )
    ]


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/outreach/contacts",
    response_model=ContactListResponse,
    summary="List a unit's contact channels",
)
def list_contacts(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    limit: Annotated[int, Query(ge=1, le=MAX_CONTACT_PAGE_SIZE)] = DEFAULT_CONTACT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ContactListResponse:
    """One unit's contacts, ordered by address.

    ``send_eligible`` is on every row, so the answer to "why can I not write to
    this person" is visible in the list rather than only discoverable by trying.
    """
    charge_quota(session, principal, READ_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)

    rows = _contacts.list_for_unit(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        limit=limit,
        offset=offset,
    )
    return ContactListResponse(contacts=[_view(row) for row in rows], limit=limit, offset=offset)


@router.get(
    "/{unit_id}/outreach/contacts/{contact_channel_id}",
    response_model=ContactWithHistoryResponse,
    summary="Read one contact channel and its consent history",
)
def read_contact(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    contact_channel_id: Annotated[uuid.UUID, Path()],
) -> ContactWithHistoryResponse:
    """One contact and every move ever made to it, oldest first.

    The history is returned in full rather than paged. It is bounded by the
    lifecycle itself — a contact that has moved many times has been re-reviewed
    many times — and an audit trail delivered in pieces is one a reader can
    accidentally read half of.

    Raises:
        ApiError: 404 when the contact is not in this unit.
    """
    charge_quota(session, principal, READ_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)
    row = _load_or_404(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        contact_channel_id=contact_channel_id,
    )

    return ContactWithHistoryResponse(
        contact=_view(row),
        transitions=_history(session, principal, contact_channel_id),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/outreach/contacts",
    status_code=status.HTTP_201_CREATED,
    response_model=ContactResponse,
    summary="Register a contact channel",
)
def register_contact(
    principal: CurrentPrincipal,
    session: DbSession,
    body: RegisterContactRequest,
    unit_id: Annotated[uuid.UUID, Path()],
) -> ContactResponse:
    """Store one contact channel and open its audit trail.

    ``201``: this has completed when it returns. A row exists, and so does the
    first entry of its history — the registration itself, recorded with the
    authenticated caller as the actor, because "who says this person consented"
    is the question the whole feature rests on.

    The actor is never a body field. Letting a request name who recorded a
    consent would be the caller-selected-identity pattern (MM-A01) in the one
    place it would matter most.

    Raises:
        ApiError: 403 when a consent claim names no approved source; 400 when it
            names one without evidence, or when the initial state is not one a
            contact may be registered in; 409 when this tenant already holds this
            address.
    """
    charge_quota(session, principal, CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)

    if body.contact_state not in _REGISTRABLE_STATES:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="outreach_contact_state_not_registrable",
            message=(
                f"A contact cannot be registered as {body.contact_state.value!r}. "
                "Register it as 'discovered' or, when a named person has agreed, as "
                "'consented' — then move it with a transition, which records who "
                "made the move."
            ),
        )

    if body.contact_state is ContactState.CONSENTED:
        _require_approved_consent(
            body.consent_source, body.consent_evidence, to_state=body.contact_state
        )

    now = utc_now()
    # A source and a date arrive together or not at all —
    # `ck_contact_channel_consent_dated`. A `discovered` contact may still carry
    # provenance, including scraped, because how a row came to exist is what a
    # reviewer needs; what provenance can never do is authorize a send, and
    # `ck_contact_channel_sendable_consent` is what makes that structural rather
    # than a convention this route keeps.
    consent_recorded_at = now if body.consent_source is not None else None

    contact_channel_id = _contacts.register(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=body.professional_id,
        address=body.address.strip(),
        contact_state=body.contact_state.value,
        consent_source=body.consent_source.value if body.consent_source is not None else None,
        consent_recorded_at=consent_recorded_at,
        consent_evidence=body.consent_evidence,
        reason=body.reason,
        actor_user_id=principal.user_id,
        occurred_at=now,
    )
    if contact_channel_id is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="contact_channel_exists",
            message=(
                "This tenant already holds an email channel for that address. Two "
                "rows for one address would be two consent states for one person, "
                "and a send path reading either would be right half the time."
            ),
        )

    session.commit()

    row = _contacts.get(
        session, tenant_id=principal.tenant_id, contact_channel_id=contact_channel_id
    )
    if row is None:  # pragma: no cover - the row was committed in this transaction
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="contact_channel_not_readable",
            message="The contact was written but could not be read back.",
        )
    return _view(row)


# ---------------------------------------------------------------------------
# Correction and suppression
# ---------------------------------------------------------------------------


@router.patch(
    "/{unit_id}/outreach/contacts/{contact_channel_id}",
    response_model=ContactResponse,
    summary="Correct a contact's consent evidence, or suppress it",
)
def update_contact(
    principal: CurrentPrincipal,
    session: DbSession,
    body: UpdateContactRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    contact_channel_id: Annotated[uuid.UUID, Path()],
) -> ContactResponse:
    """Update the two things about a contact that are not lifecycle moves.

    **Suppression is not a column.** ``suppressed: true`` writes a
    ``suppression_record`` with source ``coordinator``, which is the single
    authoritative list every send path joins against; migration ``0021`` records
    why a flag on the contact would be worse. A repeat is a no-op and still
    succeeds — someone recording the same instruction twice has not made an
    error.

    **``suppressed: false`` is refused, not ignored.** Reinstating an address
    somebody asked us to stop writing to is a decision with a real person on the
    other end of it, and no artifact in this repository ratifies who may make it
    or on what evidence (OQ-009). Silently accepting the field and doing nothing
    would be a fake success; accepting it and un-suppressing would be the worst
    write on this surface.

    Raises:
        ApiError: 404 when the contact is not in this unit; 400 when the request
            changes nothing, or asks to un-suppress.
    """
    charge_quota(session, principal, CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)
    row = _load_or_404(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        contact_channel_id=contact_channel_id,
    )

    if body.consent_evidence is None and body.suppressed is None:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="outreach_contact_update_empty",
            message=(
                "Nothing to change. Send 'consent_evidence' to correct the record of "
                "how consent was captured, or 'suppressed': true to stop all sends to "
                "this address. The lifecycle state moves through the transitions "
                "endpoint, which records who moved it."
            ),
        )

    if body.suppressed is False:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="outreach_unsuppress_not_supported",
            message=(
                "A suppression cannot be lifted through this API. Who may reinstate "
                "an address somebody asked us to stop writing to, and on what "
                "evidence, is an open question (OQ-009) — and a wrong answer reaches "
                "a real person."
            ),
        )

    now = utc_now()

    if body.consent_evidence is not None:
        _contacts.update_evidence(
            session,
            tenant_id=principal.tenant_id,
            contact_channel_id=contact_channel_id,
            consent_evidence=body.consent_evidence.strip(),
            updated_at=now,
        )

    if body.suppressed:
        _outreach.suppress(
            session,
            tenant_id=principal.tenant_id,
            address=row.address,
            source="coordinator",
            suppressed_at=now,
        )

    session.commit()

    updated = _contacts.get(
        session, tenant_id=principal.tenant_id, contact_channel_id=contact_channel_id
    )
    if updated is None:  # pragma: no cover - loaded and updated in this transaction
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="contact_channel_not_readable",
            message="The contact was updated but could not be read back.",
        )
    return _view(updated)


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/outreach/contacts/{contact_channel_id}/transitions",
    status_code=status.HTTP_201_CREATED,
    response_model=ContactWithHistoryResponse,
    summary="Move a contact through the consent lifecycle",
)
def transition_contact(
    principal: CurrentPrincipal,
    session: DbSession,
    body: TransitionRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    contact_channel_id: Annotated[uuid.UUID, Path()],
) -> ContactWithHistoryResponse:
    """Move the contact, and record who moved it and why.

    A ``POST`` to a *transitions* collection rather than a ``PATCH`` of the state
    field, because that is what happens: a row is appended to a history and the
    contact's state follows from it. ``201`` for the same reason — the thing
    created is the transition — and the response returns the contact beside the
    whole trail, so the caller can see what it now says about itself.

    The legality of the move is ``smartmatch_domain.consent``'s decision, asked
    twice for two different questions: :func:`can_transition` for the edge, and
    :func:`assert_transition` for whether a move to ``consented`` is properly
    sourced. Both refusals name the state the contact was actually in, which is
    the fact a caller working from a stale screen needs.

    Raises:
        ApiError: 404 when the contact is not in this unit; 409 when the move is
            not a legal edge from the contact's present state, or when the
            contact moved underneath this request; 403 when a consent claim names
            no approved source; 400 when it names one without evidence.
    """
    charge_quota(session, principal, CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)
    row = _load_or_404(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        contact_channel_id=contact_channel_id,
    )

    current = ContactState(row.contact_state)

    if not can_transition(current, body.to_state):
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="outreach_contact_transition_illegal",
            message=(
                f"A contact in {current.value!r} cannot move to "
                f"{body.to_state.value!r}. There is deliberately no path from any "
                "research state to a send-eligible one except through 'consented', "
                "and 'consented' requires an approved source (v1.1 §2.3)."
            ),
        )

    if body.to_state is ContactState.CONSENTED:
        _require_approved_consent(
            body.consent_source, body.consent_evidence, to_state=body.to_state
        )

    try:
        # The domain's own entry point, called even though the two checks above
        # have already run and not redundant with them: a rule added to
        # `assert_transition` later applies here without this module being edited
        # to learn about it.
        assert_transition(current, body.to_state, consent_source=body.consent_source)
    except ConsentViolationError as exc:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="outreach_consent_source_not_approved",
            message=str(exc),
        ) from exc

    consenting = body.to_state is ContactState.CONSENTED
    updated = _contacts.apply_transition(
        session,
        tenant_id=principal.tenant_id,
        contact_channel_id=contact_channel_id,
        expected_state=current.value,
        to_state=body.to_state.value,
        consent_source=(
            body.consent_source.value if consenting and body.consent_source is not None else None
        ),
        consent_evidence=body.consent_evidence if consenting else None,
        reason=body.reason,
        actor_user_id=principal.user_id,
        occurred_at=utc_now(),
    )

    if updated is None:
        # The guarded UPDATE matched nothing: somebody else moved this contact
        # between the read above and the write. Reported rather than retried —
        # the move that is now legal may not be the move this caller intended.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="outreach_contact_transition_conflict",
            message=(
                f"The contact was no longer in {current.value!r} when the move was "
                "applied; somebody else changed it. Read it again and decide against "
                "what it says now."
            ),
        )

    session.commit()

    return ContactWithHistoryResponse(
        contact=_view(updated),
        transitions=_history(session, principal, contact_channel_id),
    )
