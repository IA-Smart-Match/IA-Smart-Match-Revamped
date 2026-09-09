"""Channels for §13 roster contacts: the bridge OQ-CBA-011 deliberately left unbuilt.

``routers/cba_contacts.py`` keeps a Speaker Connector's roster of people. It
writes **no** ``contact_channel`` row on any path, and an address typed into its
create form is recognised, discarded, and reported in ``withheld_fields`` — the
ratified posture of OQ-CBA-011, and the reason a Connector who typed an address
there cannot email anybody. That posture answers "does typing make a person
contactable" with *no*. It does not answer "then how does a person ever become
contactable", and until this module existed the answer was: not through §13 at
all.

This module is that answer, and it is deliberately not the same shape as the
form. Three operations:

* ``POST  /v1/units/{unit_id}/speaker-contacts/{professional_id}/channels``
  — record an address for a roster contact, with the evidence for it.
* ``GET   /v1/units/{unit_id}/speaker-contacts/{professional_id}/channels``
  — that person's channels, each with its trail.
* ``POST  /v1/units/{unit_id}/speaker-contacts/{professional_id}/channels/
  {contact_channel_id}/transitions`` — move one, and record who moved it.

## What separates this from the form it completes

A create here is a **second, explicit act**, taken against a contact that
already exists, naming an approved source and the evidence for it, by an
identified caller, recorded in an append-only trail. The §13 create form is one
POST that types a name and an address together; this is a different request,
made later, that a Connector has to mean. Nothing about registering a contact
record causes a row here to appear, and no field of the create form is carried
forward into one — there is no path from "typed an address" to "holds a
channel" that does not pass through this module's own authorization, its own
approved-source check, and its own audit row.

**Activation is a third act.** A create may assert at most that the address is
held (``discovered``), or that a named, dated, approved permission already
exists (``consented``). It may never create an ``active_candidate``, because
that is the one state a send may address, and a row born sendable makes "who
activated this person" a question with no answer. Reaching it requires a
transition, which carries an actor.

## Why not three more routes in ``routers/cba_contacts.py``

Because the two modules make different assertions, and the split is what keeps
OQ-CBA-011's guarantee legible. That module's docstring promises, in terms, that
it writes no ``contact_channel`` row on any path and does not import the schema
object — a promise a reader verifies by reading one file. Adding channel writes
to it would delete that promise, and the next reader would have to re-derive
which of its routes can make somebody writable-to. Here the answer is: these
three, all of which say so in their names.

## Why not ``routers/outreach_contacts.py``, which writes the same table

That module registers a channel against a ``professional_id`` it stores and does
not resolve — the honest thing to do when no professional table exists (its own
docstring, and migration ``0012``'s note). This surface has one: the §13 roster.
So every operation here first loads the ``speaker_profile`` row through
``SpeakerContactRepository.get``, scoped by tenant *and* unit, and answers ``404``
when the person is not on this unit's roster. That is a real precondition rather
than a decoration: it is what makes "this address belongs to somebody a Connector
put on their list" checkable, where the generic route can only take the caller's
word for it. The generic route remains, and remains correct for its own callers.

Everything else is deliberately *not* duplicated: the state machine is
``smartmatch_domain.consent``'s, the storage is
``smartmatch_persistence.contacts``', and the suppression list is the one
``suppression_record`` table. This module contains no edge list, no second
approved-source vocabulary, and no ``suppressed`` flag of its own.

## Suppression outranks everything this module can do

A suppression is a person saying stop, and it wins over any consent record,
lifecycle state or coordinator approval that might otherwise permit a send. It
is enforced here twice, at both points where it could be lost:

* **Create** refuses outright, ``409``, when the address is already suppressed.
  Recording a fresh consent for somebody who has told us to stop is precisely
  the "we got a new form" reasoning that suppression exists to overrule, and the
  refusal must land before the row exists rather than after.
* **Transition** passes the channel's live suppression into
  ``assert_transition``, which refuses any move into ``consented`` or
  ``active_candidate``. De-escalating moves — to ``stale``, to ``rejected`` —
  are still allowed, because freezing a suppressed contact records the person's
  wishes less accurately, not more.

Neither check reads a cached flag: ``ContactChannelRow.suppressed`` is computed
by a join on every read, for the reason migration ``0021`` gives for there being
no column.

## One authorizer, shared with the roster it hangs off

Every route calls ``cba_contacts._authorize_speaker_contacts`` against the same
``org_unit`` resource, with the same ``_SPEAKER_CONTACT_ROLES``, imported rather
than re-declared. Reaching a channel *through* the roster path must not be a way
of reaching one the roster path's own authorizer would refuse, and a widening
must apply to all eight §13 operations or to none. ``tests/authz`` holds this in
both directions.

Quota is charged first — ADR-0015's ordering, ahead of the load, the
authorization and the validation, as every other route in this package does it.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel, Field
from smartmatch_domain.consent import (
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_registrable,
    assert_transition,
    is_send_eligible,
)
from smartmatch_persistence.cba_contacts import SpeakerContactRepository
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
from smartmatch_api.routers.cba_contacts import (
    SPEAKER_CONTACT_READ_RATE_LIMIT,
    _authorize_speaker_contacts,
)
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["speaker-contacts"])

#: The §13 roster, read to prove the person exists before anything is recorded
#: about how to reach them.
_roster: Final[SpeakerContactRepository] = SpeakerContactRepository()

_contacts: Final[ContactChannelRepository] = ContactChannelRepository()

#: Suppression is read through the outreach repository rather than reimplemented,
#: because ``suppression_record`` is one authoritative list. A second reader with
#: its own matching rule would be a second answer to "has this person told us to
#: stop", and the two would be free to disagree in the direction that sends.
_outreach: Final[OutreachRepository] = OutreachRepository()

#: Tighter than the roster's own write limit, and for a different reason: this
#: is the operation that grows the set of people the platform can write to, so
#: the ceiling sits where a mistake is still a handful of rows a person can
#: review rather than a list. Matched to ``outreach.contact.write``, which is
#: the same act on the other surface.
SPEAKER_CONTACT_CHANNEL_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_contact.channel.write", max_requests=30, window=timedelta(minutes=1)
)


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class ChannelTransitionView(BaseModel):
    """One recorded move, as the trail holds it."""

    from_state: str | None = Field(
        default=None,
        description=(
            "The state moved out of, or null for the registration entry — which is "
            "a real entry rather than an absent one: the contact moved from not "
            "existing to its initial state, and somebody did that."
        ),
    )
    to_state: str
    consent_source: str | None = None
    consent_evidence: str | None = None
    reason: str | None = None
    actor_user_id: uuid.UUID = Field(
        description="The authenticated caller who made this move. Never a body field."
    )
    occurred_at: str


class ChannelResponse(BaseModel):
    """One channel belonging to one §13 roster contact.

    ``suppressed`` and ``send_eligible`` are both computed at read time rather
    than stored — the first by a join against ``suppression_record``, the second
    by ``smartmatch_domain.consent.is_send_eligible`` over the row's own state,
    source and suppression. A stored copy of either would be a second place for
    the answer to live, and the disagreement between two such places always
    resolves toward sending.
    """

    contact_channel_id: uuid.UUID
    professional_id: uuid.UUID
    channel_kind: str
    address: str
    contact_state: str
    consent_source: str | None = None
    consent_recorded_at: str | None = None
    consent_evidence: str | None = None
    suppressed: bool = Field(
        description="Whether this address is under a suppression record. Outranks everything."
    )
    send_eligible: bool = Field(
        description=(
            "Whether a send may address this channel: 'active_candidate', an "
            "approved consent source, and no suppression. All three, always."
        )
    )
    created_at: str
    updated_at: str


class ChannelWithHistoryResponse(BaseModel):
    """A channel and the trail of every move made to it."""

    channel: ChannelResponse
    transitions: list[ChannelTransitionView]


class ChannelListResponse(BaseModel):
    """One roster contact's channels, each with its trail."""

    professional_id: uuid.UUID
    channels: list[ChannelWithHistoryResponse]
    limit: int
    offset: int


class RegisterChannelRequest(BaseModel):
    """Record one address for a roster contact, and the evidence for it.

    ``professional_id`` is **not** a field: it is the path, and the person named
    there has to already be on this unit's roster. That is the difference between
    this create and ``routers/outreach_contacts.py``'s, which stores an identifier
    it cannot resolve.
    """

    address: str = Field(
        min_length=3,
        max_length=320,
        description=(
            "The address itself. Pilot and test data use RFC 2606 reserved domains "
            "(.invalid), which cannot resolve and therefore cannot be written to by "
            "accident."
        ),
    )
    contact_state: ContactState = Field(
        default=ContactState.DISCOVERED,
        description=(
            "'discovered' (this unit holds the address, and asserts nothing more) "
            "or 'consented' (a named person agreed, and this request names the "
            "approved source and the evidence). Creating an 'active_candidate' is "
            "refused: activation is an act with an actor, not an initial value."
        ),
    )
    consent_source: ConsentSource | None = Field(
        default=None,
        description=(
            "Required when creating as 'consented', and then it must be one of the "
            "four approved sources. Scraped, purchased and inferred are storable as "
            "provenance on a 'discovered' channel and can never authorize a send."
        ),
    )
    consent_evidence: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "How the consent was captured — a form submission id, the coordinator's "
            "note, the institutional agreement's reference. Required with a source: "
            "an auditor asking to see the evidence needs somewhere for the answer "
            "to live that is not a comment on a ticket."
        ),
    )
    reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Why this channel is being recorded, kept on its first trail entry.",
    )


class ChannelTransitionRequest(BaseModel):
    """Move one channel to the next state in the consent lifecycle."""

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
        description="Required with a consent source, for the reason a create requires it.",
    )
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Why this move was made, in the actor's own words. Kept on the trail.",
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _view(row: ContactChannelRow) -> ChannelResponse:
    """Render one stored channel, computing the two derived facts honestly."""
    return ChannelResponse(
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
        # Asked of the domain rather than recomputed from the three fields here.
        # A rule added to `is_send_eligible` later applies to this surface
        # without this module being edited to learn about it.
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


def _require_roster_contact(
    session: Session,
    principal: CurrentPrincipal,
    *,
    owning_unit_id: uuid.UUID,
    professional_id: uuid.UUID,
) -> None:
    """Raise 404 unless this person is on *this* unit's §13 roster.

    The precondition that distinguishes this surface from the generic one. A
    person known to another unit is reported identically to one who does not
    exist, so the 404 and the authorization agree about what "not yours" means —
    a 403 would confirm that an id the caller may not read names somebody real.
    """
    if (
        _roster.get(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=owning_unit_id,
            professional_id=professional_id,
        )
        is None
    ):
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_contact_not_found",
            message="No such speaker contact in this unit.",
        )


def _load_channel_or_404(
    session: Session,
    principal: CurrentPrincipal,
    *,
    owning_unit_id: uuid.UUID,
    professional_id: uuid.UUID,
    contact_channel_id: uuid.UUID,
) -> ContactChannelRow:
    """The channel, or a 404 that says nothing about which of the three failed.

    All three of tenant, unit and professional must match. The last is what stops
    this route becoming a way to move *any* channel in a unit the caller may
    reach by naming a roster contact they may reach — the person in the path has
    to be the person the channel belongs to.
    """
    row = _contacts.get(
        session, tenant_id=principal.tenant_id, contact_channel_id=contact_channel_id
    )
    if (
        row is None
        or row.owning_unit_id != owning_unit_id
        or row.professional_id != professional_id
    ):
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_contact_channel_not_found",
            message="No such contact channel for this speaker contact.",
        )
    return row


def _require_evidence(evidence: str | None) -> None:
    """Raise 400 unless a consent claim arrives with the evidence for it.

    Separate from the domain's approved-source gate because evidence is a stored
    artifact rather than a lifecycle fact, which is why ``assert_registrable``
    and ``assert_transition`` do not model it. Both halves are required together
    for ``ck_contact_channel_consent_dated``'s reason: a permission nobody can
    produce evidence for is a permission nobody can audit.
    """
    if evidence is None or not evidence.strip():
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_contact_channel_consent_evidence_required",
            message=(
                "A consent source must arrive with the evidence for it — the form "
                "submission, the coordinator's note, the agreement's reference. A "
                "consent record nobody can produce evidence for is one nobody can "
                "audit."
            ),
        )


def _history(
    session: Session, principal: CurrentPrincipal, contact_channel_id: uuid.UUID
) -> list[ChannelTransitionView]:
    """One channel's trail, oldest first and in full.

    Not paged. It is bounded by the lifecycle itself — a contact that has moved
    many times has been re-reviewed many times — and an audit trail delivered in
    pieces is one a reader can accidentally read half of.
    """
    return [
        ChannelTransitionView(
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
# Read
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/speaker-contacts/{professional_id}/channels",
    response_model=ChannelListResponse,
    summary="List a speaker contact's channels and their consent history",
)
def list_speaker_contact_channels(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
    limit: Annotated[int, Query(ge=1, le=MAX_CONTACT_PAGE_SIZE)] = DEFAULT_CONTACT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChannelListResponse:
    """Every channel this unit holds for this person, each with its full trail.

    ``send_eligible`` is on every row, so "why can I not write to this person" is
    answerable by reading rather than only by trying. A person with no channel at
    all — the ordinary case for a contact added through the §13 form, which
    writes none — returns an empty list, which is the honest answer and not a
    404: the contact exists, and holds nothing.

    Raises:
        ApiError: 404 when the person is not on this unit's roster.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_READ_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    _require_roster_contact(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
    )

    rows = _contacts.list_for_professional(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
        limit=limit,
        offset=offset,
    )
    return ChannelListResponse(
        professional_id=professional_id,
        channels=[
            ChannelWithHistoryResponse(
                channel=_view(row),
                transitions=_history(session, principal, row.id),
            )
            for row in rows
        ],
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-contacts/{professional_id}/channels",
    status_code=status.HTTP_201_CREATED,
    response_model=ChannelWithHistoryResponse,
    summary="Record a contact channel for a speaker contact",
)
def register_speaker_contact_channel(
    principal: CurrentPrincipal,
    session: DbSession,
    body: RegisterChannelRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> ChannelWithHistoryResponse:
    """Store one channel for a roster contact and open its audit trail.

    ``201``: when this returns, a row exists and so does the first entry of its
    history — the registration itself, recorded with the authenticated caller as
    the actor, because "who says this person agreed" is the question the whole
    feature rests on. The actor is never a body field: letting a request name who
    recorded a consent would be the caller-selected-identity pattern (MM-A01) in
    the one place it would matter most.

    The response carries the trail as well as the row, so a caller can see the
    single entry it just caused rather than having to fetch it to believe it.

    Raises:
        ApiError: 404 when the person is not on this unit's roster; 409 when the
            address is suppressed, or when this tenant already holds a channel
            for it; 403 when a consent claim names no approved source or the
            initial state is not one a channel may be created in; 400 when a
            source arrives without evidence.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_CHANNEL_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    _require_roster_contact(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
    )

    address = body.address.strip()

    # Suppression first, before the state is even looked at. A fresh consent for
    # somebody who has told us to stop is exactly the reasoning suppression
    # exists to overrule, and the refusal has to land before the row exists —
    # afterwards it is a row somebody has to notice and remove.
    if _outreach.is_suppressed(session, tenant_id=principal.tenant_id, address=address):
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_contact_channel_suppressed",
            message=(
                "That address is suppressed: somebody at it has told us to stop. A "
                "suppression outranks every consent record and approval that might "
                "otherwise permit a send, including a new one recorded now."
            ),
        )

    try:
        # The domain owns both halves of "may a channel be created like this":
        # the registrable states, and the approved-source rule when the create
        # claims consent. Refused as 403 rather than 400 because no sequence of
        # legal inputs fixes either — reporting them as validation would invite
        # the caller to try other values until one is accepted.
        assert_registrable(body.contact_state, consent_source=body.consent_source)
    except ConsentViolationError as exc:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="speaker_contact_channel_not_registrable",
            message=str(exc),
        ) from exc

    if body.contact_state is ContactState.CONSENTED:
        _require_evidence(body.consent_evidence)

    now = utc_now()
    # A source and a date arrive together or not at all —
    # `ck_contact_channel_consent_dated`. A `discovered` channel may still carry
    # provenance, including scraped, because how a row came to exist is what a
    # reviewer needs; what provenance can never do is authorize a send, and
    # `ck_contact_channel_sendable_consent` makes that structural rather than a
    # convention this route keeps.
    consent_recorded_at = now if body.consent_source is not None else None

    contact_channel_id = _contacts.register(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
        address=address,
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
            code="speaker_contact_channel_exists",
            message=(
                "This tenant already holds an email channel for that address. Two "
                "rows for one address would be two consent states for one person, "
                "and a send path reading either would be right half the time."
            ),
        )

    # `get_session` rolls back unconditionally: without this the route would
    # return a clean 201 and store nothing at all.
    session.commit()

    row = _contacts.get(
        session, tenant_id=principal.tenant_id, contact_channel_id=contact_channel_id
    )
    if row is None:  # pragma: no cover - the row was committed in this transaction
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="speaker_contact_channel_not_readable",
            message="The channel was written but could not be read back.",
        )
    return ChannelWithHistoryResponse(
        channel=_view(row),
        transitions=_history(session, principal, contact_channel_id),
    )


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-contacts/{professional_id}/channels/{contact_channel_id}/transitions",
    status_code=status.HTTP_201_CREATED,
    response_model=ChannelWithHistoryResponse,
    summary="Move a speaker contact's channel through the consent lifecycle",
)
def transition_speaker_contact_channel(
    principal: CurrentPrincipal,
    session: DbSession,
    body: ChannelTransitionRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
    contact_channel_id: Annotated[uuid.UUID, Path()],
) -> ChannelWithHistoryResponse:
    """Move the channel, and record who moved it and why.

    A ``POST`` to a *transitions* collection rather than a ``PATCH`` of the state
    field, because that is what happens: a row is appended to a history and the
    channel's state follows from it. ``201`` for the same reason — the thing
    created is the transition.

    The legality of the move is ``smartmatch_domain.consent``'s decision, and it
    is asked **with the live suppression**, which is what makes suppression win
    here rather than only at send time. A suppressed address cannot reach
    ``consented`` or ``active_candidate`` by any route, however well sourced the
    request; a move that does not increase what may be done to the person still
    works, so a Connector can record that a suppressed contact went stale.

    Raises:
        ApiError: 404 when the channel is not this person's, in this unit; 409
            when the address is suppressed and the move would escalate it, when
            the move is not a legal edge, or when the channel moved underneath
            this request; 403 when a consent claim names no approved source; 400
            when it names one without evidence.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_CHANNEL_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    _require_roster_contact(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
    )
    row = _load_channel_or_404(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
        contact_channel_id=contact_channel_id,
    )

    current = ContactState(row.contact_state)

    if body.to_state is ContactState.CONSENTED:
        _require_evidence(body.consent_evidence)

    try:
        # One call, three rules: suppression, edge legality, approved source —
        # in that order, and all of them the domain's. This module holds no edge
        # list and no second vocabulary of sources, so a rule added there
        # applies here without this file being edited to learn about it.
        assert_transition(
            current,
            body.to_state,
            consent_source=body.consent_source,
            suppressed=row.suppressed,
        )
    except ConsentViolationError as exc:
        message = str(exc)
        # A refusal that names the *person's* decision, or an edge that does not
        # exist, is a conflict with the world as it stands: reading the channel
        # again is the caller's next move. A refused consent source is not — no
        # sequence of legal moves admits a scraped address, so it is a 403 and
        # the caller should stop rather than retry.
        conflicting = "suppressed" in message or "illegal contact lifecycle" in message
        raise ApiError(
            status_code=(status.HTTP_409_CONFLICT if conflicting else status.HTTP_403_FORBIDDEN),
            code=(
                "speaker_contact_channel_transition_refused"
                if conflicting
                else "speaker_contact_channel_consent_source_not_approved"
            ),
            message=message,
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
        # The guarded UPDATE matched nothing: somebody else moved this channel
        # between the read above and the write. Reported rather than retried —
        # the move that is now legal may not be the move this caller intended.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_contact_channel_transition_conflict",
            message=(
                f"The channel was no longer in {current.value!r} when the move was "
                "applied; somebody else changed it. Read it again and decide against "
                "what it says now."
            ),
        )

    session.commit()

    return ChannelWithHistoryResponse(
        channel=_view(updated),
        transitions=_history(session, principal, contact_channel_id),
    )
