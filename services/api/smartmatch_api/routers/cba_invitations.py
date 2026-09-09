"""Speaker invitations: batch a reviewed shortlist, send it, and track two facts.

Customer §6 steps 7-8, §13 ("send speaker invitations", "batch-invite candidates
where supported", "track invitation responses/acceptances") and §14 (the Speaker
accepts or declines). Six operations:

* ``POST /v1/units/{unit_id}/speaker-invitations/batches`` — compose a batch.
  Nothing is sent.
* ``GET  /v1/units/{unit_id}/speaker-invitations/batches`` — a Connector's list.
* ``GET  /v1/units/{unit_id}/speaker-invitations/batches/{batch_id}`` — one
  batch, every outcome in it, and both facts about each.
* ``POST /v1/units/{unit_id}/speaker-invitations/batches/{batch_id}/dispatch`` —
  submit one ``outreach.send`` per pending invitation. Returns ``202``.
* ``POST /v1/units/{unit_id}/speaker-invitations/{invitation_id}/response`` — a
  Connector records what a Speaker told them out of band.
* ``POST /v1/speaker-invitations/respond`` — the Speaker's own answer, from the
  link in their invitation. Unauthenticated by design.

## This rides the consented path; it does not build a second one

Every message here is an ``outreach_draft`` composed by
``smartmatch_domain.outreach.compose_draft`` from the closed template registry,
sent by the existing ``outreach.send`` command, delivered by the one handler in
``smartmatch_worker/outreach.py``. This module adds no provider call, no second
send path, and no way to reach an address that is not already an
``active_candidate`` contact channel with an approved consent source and no
suppression. The legacy cold path is not touched, extended, or referenced.

That reuse is not laziness — it is what makes the delivery-time consent recheck
apply to invitations for free. Which matters, because:

## Consent is checked three times, and the third is the one that protects anybody

1. **At batch creation**, per recipient, by ``classify_recipient`` — which is how
   a Connector is told *at the moment they act* that three of their twelve names
   cannot be written to, and why.
2. **At dispatch**, again, against state read now. A channel can be suppressed in
   the minutes or days between composing a batch and pressing send, and an
   invitation composed before that suppression must not go out after it.
3. **At delivery**, by the worker, against state read at delivery time. This is
   the only one that closes the window after the ``202``, and it is the one that
   actually protects the recipient.

Removing the first would let a Connector discover the problem from a job log.
Removing the second would send mail the platform already knew it should not.
Removing the third would let an unsubscribe between the dispatch and the delivery
be ignored.

## The two facts this card exists to keep apart

A batch read returns, per invitation, a ``delivery`` object and a
``speaker_response`` object. They are **two nested objects, never two fields of
one flat record**, because:

* ``delivery.disposition`` is a *mail provider's* word. ``accepted`` there means
  a mail system took custody of some bytes. It may be ``null``, which means an
  attempt is in flight — a third state, rendered as in-progress and never as a
  failure — and ``delivery`` itself is ``null`` when no send has been submitted,
  which is a different unknown again.
* ``speaker_response.response`` is a *human being's* word, and its vocabulary
  shares no value with the first: ``accepted_invitation``, never ``accepted``.

An Event Host handed the first as though it were the second books a room for
nobody. ``tests/contract/test_cba_invitations_api.py`` asserts the two are
disjoint over the live enums rather than over a list written here.

## A batch is idempotent, and reports who it left out

The ``Idempotency-Key`` header is required on the create and is unique per unit.
A replay returns the *stored* outcomes with ``replayed: true`` and composes
nothing — a Connector who double-clicked has not invited anybody twice.

And every name they submitted comes back, invited or skipped, with a reason a
person can act on. A batch that answered "9 invited" to a list of twelve would be
reporting the good news and burying the three decisions.

## Quota is charged first

ADR-0015's ordering, ahead of the load, the authorization and the validation, as
every other route in this package does it.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Header, Path, Query, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.cba_invitations import (
    INVITATION_TEMPLATE_ID,
    MAX_BATCH_RECIPIENTS,
    InvitationResponseConflict,
    InvitationStatus,
    SkipReason,
    SpeakerResponse,
    choose_invitation_channel,
    classify_recipient,
    record_response,
)
from smartmatch_domain.consent import ConsentSource, ConsentViolationError, ContactState
from smartmatch_domain.outreach import (
    OUTREACH_SEND_COMMAND_TYPE,
    DraftRecipient,
    DraftStatus,
    OutreachCompositionError,
    compose_draft,
)
from smartmatch_persistence.cba_contacts import SpeakerContactRepository
from smartmatch_persistence.cba_invitations import (
    DEFAULT_BATCH_PAGE_SIZE,
    MAX_BATCH_PAGE_SIZE,
    InvitationRepository,
    InvitationWithDelivery,
)
from smartmatch_persistence.contacts import ContactChannelRepository
from smartmatch_persistence.outreach import OutreachRepository
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.commands import submit_command
from smartmatch_api.config import get_settings
from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import OrgUnitRow, load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["speaker-invitations"])

#: The Speaker's own answer is not unit-scoped and not authenticated, so it gets
#: its own router rather than a path exception on the one above —
#: ``routers/outreach.py``'s arrangement, for its reason: "this route takes no
#: principal" is a property worth being visible in the declaration.
public_router = APIRouter(tags=["speaker-invitations"])

_invites: Final[InvitationRepository] = InvitationRepository()

#: The §13 roster, read to prove a named recipient is somebody this unit put on
#: its own list before anything is composed about them.
_roster: Final[SpeakerContactRepository] = SpeakerContactRepository()

_channels: Final[ContactChannelRepository] = ContactChannelRepository()

#: Drafts and the live suppression check are the outreach repository's. Reusing
#: it rather than reimplementing either is what keeps ``suppression_record`` one
#: authoritative list: a second reader with its own matching rule would be a
#: second answer to "has this person told us to stop", and the two would be free
#: to disagree in the direction that sends.
_outreach: Final[OutreachRepository] = OutreachRepository()

#: Customer §13's Speaker Connector, and nobody else. ``volunteer`` — the stored
#: role the Event Host persona maps to — is deliberately absent: the party who
#: benefits from a speaker being invited must not be the party who authorizes the
#: invitation. A literal ``frozenset`` rather than an import of one of the other
#: role sets, for ``tests/authz/test_route_roles.py``'s reason: several sets
#: agreeing today is not a reason a widening of one should widen the others.
_SPEAKER_INVITATION_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: Composing a batch writes rows and sends nothing; dispatching it is the
#: consequential act, and its limit is tighter for that reason rather than a
#: capacity one — the same relationship ``routers/outreach.py`` draws between its
#: draft and send limits. Here one dispatch can submit up to
#: ``MAX_BATCH_RECIPIENTS`` sends, so ten a minute is already a great deal of
#: mail.
INVITATION_BATCH_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_invitation.batch", max_requests=20, window=timedelta(minutes=1)
)
INVITATION_DISPATCH_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_invitation.dispatch", max_requests=10, window=timedelta(minutes=1)
)
INVITATION_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_invitation.read", max_requests=120, window=timedelta(minutes=1)
)
INVITATION_RESPONSE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_invitation.response", max_requests=60, window=timedelta(minutes=1)
)

# **No rate limit on `POST /v1/speaker-invitations/respond`,** and the absence is
# the same deliberate one `routers/outreach.py` documents for `/v1/unsubscribe`:
# `charge_quota` keys its counter by tenant and user id against a table with a
# foreign key to `tenant`, so applying it to an unauthenticated route requires
# inventing a principal that does not exist. The blast radius is bounded by the
# constraints instead — a request writes at most one row per distinct valid
# token, nothing at all for an invalid one, and a second answer to an
# already-answered invitation writes nothing either. A real deployment puts an
# edge rate limit in front of it.


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class BatchCreateRequest(BaseModel):
    """Compose invitations for a reviewed shortlist.

    Note what cannot be supplied: **a template**, **a body**, **a recipient
    address**, and **a response link**. The template is
    :data:`~smartmatch_domain.cba_invitations.INVITATION_TEMPLATE_ID`, because
    which words an institution uses is a copy decision recorded in the closed
    registry rather than one a caller makes per batch. The address is resolved
    from the recipient's own stored channels. The response link is composed
    server-side from the configured origin and a freshly minted token — a caller
    supplying one would be putting an arbitrary link into an institutional email
    over an already-consented address, which is a phishing primitive rather than
    a parameter.

    What a caller does supply is who to invite and what the event is.
    """

    professional_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=MAX_BATCH_RECIPIENTS,
        description=(
            "The shortlisted people to invite, as §13 roster ids. Every one of "
            "them produces an outcome in the response — an invitation, or a skip "
            "with a reason. §6 puts a shortlist at 2-3 candidates; the ceiling is "
            "far above that and exists so a mistake stays reviewable."
        ),
    )
    match_run_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The match run whose shortlist this batch came from, when it came "
            "from one. Optional because a Connector may pick people by hand, and "
            "requiring a run id would make the honest case unrepresentable."
        ),
    )
    event_name: str = Field(min_length=1, max_length=200)
    event_date: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "The date as it should appear in the message. Stored and rendered "
            "verbatim, never parsed: this string's only job is to be read by a "
            "person, and parsing it would mean guessing a timezone for it."
        ),
    )
    coordinator_name: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "How the Connector signs the message. A display name, not an "
            "identity: who *submitted* the batch is the authenticated caller and "
            "is recorded separately, so this cannot be used to attribute a batch "
            "to somebody else."
        ),
    )


class DeliveryView(BaseModel):
    """What a **mail provider** did with the message. Never what a Speaker said.

    ``null`` at the top level when no send has been submitted for this
    invitation. A non-null object whose ``disposition`` is ``null`` is an attempt
    in flight — a third state, to be rendered as in-progress and never as a
    failure.
    """

    send_id: uuid.UUID
    disposition: str | None = Field(
        description=(
            "'accepted', 'blocked', 'failed', or null while the attempt is still "
            "in flight. 'accepted' means a provider took custody of the message. "
            "It does **not** mean the message was delivered, and it emphatically "
            "does not mean the Speaker agreed to anything — that is "
            "`speaker_response`, which shares no value with this field."
        )
    )
    provider: str | None
    failure_reason: str | None
    concluded_at: str | None


class SpeakerResponseView(BaseModel):
    """What the **Speaker** said. Never what a mail provider did."""

    response: str = Field(
        description=(
            "'awaiting_response', 'accepted_invitation' or 'declined_invitation'. "
            "Every value names the invitation, so none of them can be confused "
            "with a delivery disposition. 'awaiting_response' is a real state — "
            "the ordinary condition of every invitation until somebody reads "
            "their mail — and is not a failure."
        )
    )
    recorded_at: str | None
    channel: str | None = Field(
        description=(
            "'speaker_link' when the Speaker followed the link in their own "
            "invitation, 'connector_recorded' when a coordinator entered what "
            "they were told. Reported because the second is a weaker evidentiary "
            "claim than the first, and a screen that showed them alike would "
            "assert a directness nobody has."
        )
    )
    recorded_by_user_id: uuid.UUID | None = Field(
        description="The coordinator who entered it, or null for a Speaker's own answer."
    )


class InvitationOutcomeView(BaseModel):
    """One named recipient's outcome, and the two facts about it, kept apart."""

    invitation_id: uuid.UUID
    professional_id: uuid.UUID
    status: str = Field(
        description=(
            "'pending', 'dispatched' or 'skipped'. What this platform did. Says "
            "nothing about what the recipient did."
        )
    )
    skip_reason: str | None = Field(
        description="Why nobody was written to, present exactly when status is 'skipped'."
    )
    recipient_address: str | None = Field(
        description="The address the invitation was composed for, or null for a skip."
    )
    delivery: DeliveryView | None = Field(
        description="What the provider did, or null when no send has been submitted."
    )
    speaker_response: SpeakerResponseView


class BatchResponse(BaseModel):
    """One batch and every outcome in it."""

    batch_id: uuid.UUID
    match_run_id: uuid.UUID | None
    template_id: str
    event_name: str
    event_date: str
    created_at: str
    replayed: bool = Field(
        description=(
            "True when this request replayed an idempotency key already used in "
            "this unit. Nothing was composed and nobody was invited a second "
            "time; the outcomes are the first submission's."
        )
    )
    invited_count: int
    skipped_count: int
    invitations: list[InvitationOutcomeView] = Field(
        description=(
            "Every professional_id the request named, invited or skipped. A "
            "shorter list than the request would be a batch reporting the good "
            "news and burying the decisions."
        )
    )


class BatchSummaryView(BaseModel):
    """One batch in a listing, without its outcomes."""

    batch_id: uuid.UUID
    match_run_id: uuid.UUID | None
    template_id: str
    event_name: str
    event_date: str
    created_at: str


class BatchListResponse(BaseModel):
    """A page of batches, and how many were asked for."""

    batches: list[BatchSummaryView]
    limit: int
    offset: int


class DispatchedView(BaseModel):
    """One invitation whose send command was accepted. **Nothing has been sent.**"""

    invitation_id: uuid.UUID
    job_id: uuid.UUID
    events_url: str
    replayed: bool = Field(
        description="True when this exact command had already been accepted under the same key."
    )


class NotDispatchedView(BaseModel):
    """One pending invitation this dispatch declined to submit, and why."""

    invitation_id: uuid.UUID
    reason: str = Field(
        description=(
            "A consent fact read *now*, not at batch creation: a channel can be "
            "suppressed, de-activated, or removed between composing a batch and "
            "sending it. The invitation stays pending and can be dispatched later "
            "if the reason is resolved."
        )
    )


class DispatchResponse(BaseModel):
    """What a dispatch submitted, and what it refused to.

    **No status field, and no count of messages sent.** When this returns nothing
    has been sent: each entry of ``dispatched`` is a command the dispatcher has
    not moved yet. Follow ``events_url``, then read the batch.
    """

    batch_id: uuid.UUID
    dispatched: list[DispatchedView]
    not_dispatched: list[NotDispatchedView]


class RecordResponseRequest(BaseModel):
    """What a Speaker told a Connector, as the Connector enters it."""

    response: Literal["accept", "decline"] = Field(
        description=(
            "The Speaker's answer, in verbs so that neither value can be pasted "
            "from a delivery disposition. Stored as 'accepted_invitation' or "
            "'declined_invitation'."
        )
    )


class RecordResponseResponse(BaseModel):
    """The invitation's answer after this call, and whether this call wrote it."""

    invitation_id: uuid.UUID
    response: str
    recorded: bool = Field(
        description=(
            "False when the invitation already carried this exact answer. That is "
            "a success: somebody clicking twice has not made an error, and the "
            "recorded time stays the time of the first answer rather than being "
            "redated by a repeat."
        )
    )


class SpeakerRespondRequest(BaseModel):
    """The Speaker's own answer, from the link in their invitation."""

    token: str = Field(min_length=16, max_length=256)
    response: Literal["accept", "decline"]


class SpeakerRespondResponse(BaseModel):
    """The answer to a Speaker's response, which is the same for every token.

    See :func:`speaker_respond`: a response that distinguished a real token from
    an invented one would let anyone holding a guess confirm whether a given
    person was invited to speak.
    """

    recorded: bool = Field(
        description="Always true. The request was accepted; nothing is confirmed about the token."
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_speaker_invitations(
    session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID
) -> OrgUnitRow:
    """Load the unit and authorize a Speaker Connector against *that row's* path.

    Shared by all five unit-scoped operations, in the spirit of
    ``_authorize_outreach`` and ``_authorize_speaker_contacts``: they ask the
    identical question against the identical resource, so a widening applies to
    all of them or to none and cannot reach one operation by accident.

    ``load_unit_or_404`` scopes the lookup by the caller's own tenant, so a unit
    in another tenant is a 404 rather than a 403 that would confirm the id names
    something real.

    No ``require_membership`` — :data:`_SPEAKER_INVITATION_ROLES` is non-empty,
    so ``evaluate`` already refuses a bare ``resource_grant`` on the
    required-roles check (S-007). No ``tenant_wide_roles`` — the metrics decision
    is the only artifact that makes anything tenant-wide, and it says so of
    aggregate reads rather than of a department writing to people.

    Returns:
        The loaded unit row, not merely its id. The display name is what the
        invitation says the host institution is, and reading it from the row the
        request was authorized against is what stops a caller naming an
        institution they do not speak for.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_SPEAKER_INVITATION_ROLES,
    )
    return unit


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    """SHA-256 of a response token, which is the only form ever stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _response_url(token: str) -> str:
    """The page an invitation links to, built from configured settings only.

    Never from a request. See :class:`BatchCreateRequest` — a caller-supplied URL
    in an institutional email to a consented address is a phishing primitive.
    """
    return f"{get_settings().outreach_public_base_url.rstrip('/')}/i/{token}"


def _speaker_response(verb: str) -> SpeakerResponse:
    """Map the API's verb onto the stored vocabulary.

    Two vocabularies on purpose. The wire takes ``accept``/``decline``, which are
    things a person does; the column takes ``accepted_invitation`` /
    ``declined_invitation``, which are things that are true of an invitation and
    which no delivery disposition can be spelled like. Neither is ever the
    provider's ``accepted``.
    """
    return (
        SpeakerResponse.ACCEPTED_INVITATION
        if verb == "accept"
        else SpeakerResponse.DECLINED_INVITATION
    )


def _outcome_view(entry: InvitationWithDelivery) -> InvitationOutcomeView:
    """Render one invitation with its two facts in two separate objects."""
    row = entry.invitation
    return InvitationOutcomeView(
        invitation_id=row.id,
        professional_id=row.professional_id,
        status=row.status,
        skip_reason=row.skip_reason,
        recipient_address=row.recipient_address,
        delivery=(
            None
            if entry.delivery is None
            else DeliveryView(
                send_id=entry.delivery.send_id,
                disposition=entry.delivery.disposition,
                provider=entry.delivery.provider,
                failure_reason=entry.delivery.failure_reason,
                concluded_at=(
                    entry.delivery.concluded_at.isoformat()
                    if entry.delivery.concluded_at is not None
                    else None
                ),
            )
        ),
        speaker_response=SpeakerResponseView(
            response=row.response_status,
            recorded_at=(
                row.response_recorded_at.isoformat()
                if row.response_recorded_at is not None
                else None
            ),
            channel=row.response_channel,
            recorded_by_user_id=row.response_recorded_by_user_id,
        ),
    )


def _batch_response(
    session: Session,
    principal: CurrentPrincipal,
    *,
    batch_id: uuid.UUID,
    replayed: bool,
) -> BatchResponse:
    """Read a batch back and render it. The one renderer both writes and reads use.

    Deliberately re-reads rather than echoing what a create just assembled, so a
    replay and a first submission answer through the identical code path — which
    is what makes "a replay reports the same thing" a property of the read rather
    than of two hand-kept-in-sync response builders.
    """
    batch = _invites.get_batch(session, tenant_id=principal.tenant_id, batch_id=batch_id)
    if batch is None:  # pragma: no cover - the caller has just reserved it
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_invitation_batch_not_found",
            message="No such invitation batch in this unit.",
        )

    entries = _invites.list_invitations(session, tenant_id=principal.tenant_id, batch_id=batch_id)
    views = [_outcome_view(entry) for entry in entries]

    return BatchResponse(
        batch_id=batch.id,
        match_run_id=batch.match_run_id,
        template_id=batch.template_id,
        event_name=batch.event_name,
        event_date=batch.event_date,
        created_at=batch.created_at.isoformat(),
        replayed=replayed,
        invited_count=sum(1 for view in views if view.status != InvitationStatus.SKIPPED.value),
        skipped_count=sum(1 for view in views if view.status == InvitationStatus.SKIPPED.value),
        invitations=views,
    )


def _load_batch_or_404(
    session: Session, principal: CurrentPrincipal, *, unit_id: uuid.UUID, batch_id: uuid.UUID
) -> uuid.UUID:
    """The batch id, proven to belong to this unit, or a 404 that says nothing more."""
    batch = _invites.get_batch(session, tenant_id=principal.tenant_id, batch_id=batch_id)
    if batch is None or batch.owning_unit_id != unit_id:
        # A 404 rather than a 403: the batch may exist under a unit this request
        # was not authorized for, and "forbidden" would confirm that an id the
        # caller may not read names something real.
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_invitation_batch_not_found",
            message="No such invitation batch in this unit.",
        )
    return batch.id


def _require_idempotency_key(idempotency_key: str | None) -> str:
    """Raise 400 unless the caller named a key. Composing invitations needs one.

    Required rather than defaulted, for ``submit_command``'s reason: a generated
    key would make every retry a new batch, which on this surface means a second
    set of messages in the same inboxes.
    """
    if idempotency_key is None or not idempotency_key.strip():
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="idempotency_key_required",
            message=(
                "An Idempotency-Key header is required. Without one a retried "
                "submission is a second batch, and a second batch is a second "
                "message to everybody in the first."
            ),
        )
    return idempotency_key.strip()


def _require_distinct_recipients(professional_ids: list[uuid.UUID]) -> None:
    """Raise 400 when the same person is named more than once.

    Refused rather than folded, and the choice is not fussiness. A batch holds
    one outcome per person — ``uq_cba_invitation_batch_recipient``, which is the
    constraint that makes a replay safe — so a repeated name has nowhere to
    produce a second outcome, and quietly dropping it would return fewer
    outcomes than the Connector sent. That is the silent shrink this surface is
    arranged against, and a list with a name twice in it is a list somebody
    should look at before anything is sent.

    The repeated ids are named in the message, because "your list has a
    duplicate" without saying which one makes a Connector re-read twelve UUIDs.

    Raises:
        ApiError: 400, naming every id that appears more than once.
    """
    seen: set[uuid.UUID] = set()
    repeated: list[uuid.UUID] = []
    for professional_id in professional_ids:
        if professional_id in seen and professional_id not in repeated:
            repeated.append(professional_id)
        seen.add(professional_id)

    if repeated:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_invitation_duplicate_recipient",
            message=(
                "The same person is named more than once: "
                f"{', '.join(str(pid) for pid in repeated)}. A batch holds one "
                "outcome per person, so a repeat has no second outcome to "
                "report — and dropping it silently would hand back a shorter "
                "list than the one submitted. Nothing was composed."
            ),
        )


# ---------------------------------------------------------------------------
# Compose a batch
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-invitations/batches",
    status_code=status.HTTP_201_CREATED,
    response_model=BatchResponse,
    summary="Compose a batch of speaker invitations",
)
def create_invitation_batch(
    principal: CurrentPrincipal,
    session: DbSession,
    body: BatchCreateRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description="Required. Makes retries safe."),
    ] = None,
) -> BatchResponse:
    """Compose one invitation per eligible recipient. **Nothing is sent.**

    ``201`` rather than ``202``: unlike the dispatch, this has completed when it
    returns — the batch and every outcome in it are rows a Connector can read
    back. Reserving ``202`` for the operation that genuinely defers work is what
    keeps the distinction meaningful.

    Each named recipient is resolved in three steps, and each step's failure is a
    *skip with a reason* rather than an error, because a batch that refused
    wholesale on one bad name would make a Connector fix their list by bisection:

    1. They must be on **this unit's** §13 roster — otherwise ``not_on_roster``.
    2. They must hold a channel an invitation may address — otherwise the reason
       ``choose_invitation_channel`` gives, which names the condition that failed
       rather than saying "ineligible".
    3. The message must compose — which, having passed step 2, it does.

    Sending an invitation does not advance anybody's consent, and there is no
    path here that could: the eligibility question is asked of stored state and
    nothing writes back to ``contact_channel``. A contact who is not already an
    ``active_candidate`` is skipped and stays exactly where they were.

    Raises:
        ApiError: 404 when the unit does not exist in this tenant; 400 when the
            idempotency key is missing, or when the same person is named twice
            (see :func:`_require_distinct_recipients` — a repeat has no second
            outcome to report, and dropping it would shorten the answer).
    """
    charge_quota(session, principal, INVITATION_BATCH_RATE_LIMIT)

    unit = _authorize_speaker_invitations(session, principal, unit_id)
    key = _require_idempotency_key(idempotency_key)
    _require_distinct_recipients(body.professional_ids)

    reservation = _invites.reserve_batch(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit.id,
        idempotency_key=key,
        template_id=INVITATION_TEMPLATE_ID,
        event_name=body.event_name,
        event_date=body.event_date,
        created_by_user_id=principal.user_id,
        match_run_id=body.match_run_id,
    )

    if reservation.was_replayed:
        # Compose nothing, invite nobody, and report what the first submission
        # decided. Recomputing would be a second set of messages under a key
        # whose entire purpose is to prevent exactly that — and it would also
        # quietly answer a *different* question, because eligibility may have
        # changed since.
        return _batch_response(session, principal, batch_id=reservation.batch.id, replayed=True)

    for professional_id in body.professional_ids:
        _compose_one(
            session,
            principal,
            unit=unit,
            batch_id=reservation.batch.id,
            professional_id=professional_id,
            body=body,
        )

    # The one commit. Without it `get_session`'s unconditional rollback discards
    # the batch, every draft and every outcome, and this route returns a clean
    # 201 having stored nothing.
    session.commit()

    return _batch_response(session, principal, batch_id=reservation.batch.id, replayed=False)


def _skip(
    session: Session,
    principal: CurrentPrincipal,
    *,
    unit_id: uuid.UUID,
    batch_id: uuid.UUID,
    professional_id: uuid.UUID,
    reason: SkipReason,
) -> None:
    """Record that a named recipient produced no invitation, and why.

    Stored rather than only returned. A skip that lived in one response body
    would vanish the moment the Connector navigated away, and the skips are the
    part of a batch that needs somebody to do something.
    """
    _invites.add_invitation(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit_id,
        batch_id=batch_id,
        professional_id=professional_id,
        status=InvitationStatus.SKIPPED.value,
        response_status=SpeakerResponse.AWAITING_RESPONSE.value,
        skip_reason=reason.value,
    )


def _compose_one(
    session: Session,
    principal: CurrentPrincipal,
    *,
    unit: OrgUnitRow,
    batch_id: uuid.UUID,
    professional_id: uuid.UUID,
    body: BatchCreateRequest,
) -> None:
    """Resolve one recipient and either compose their invitation or skip them."""
    contact = _roster.get(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit.id,
        professional_id=professional_id,
    )
    if contact is None:
        _skip(
            session,
            principal,
            unit_id=unit.id,
            batch_id=batch_id,
            professional_id=professional_id,
            reason=SkipReason.NOT_ON_ROSTER,
        )
        return

    channels = _channels.list_for_professional(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit.id,
        professional_id=professional_id,
    )
    channel, reason = choose_invitation_channel(channels)
    if channel is None:
        # `reason` is non-None whenever `channel` is None — the domain function's
        # contract, which `RecipientOutcome.__post_init__` states one layer up.
        # The fallback keeps mypy honest without inventing a reason.
        _skip(
            session,
            principal,
            unit_id=unit.id,
            batch_id=batch_id,
            professional_id=professional_id,
            reason=reason or SkipReason.NO_CONTACT_CHANNEL,
        )
        return

    token = secrets.token_urlsafe(32)

    try:
        composed = compose_draft(
            recipient=DraftRecipient(
                address=channel.address,
                contact_state=ContactState(channel.contact_state),
                consent_source=(
                    ConsentSource(channel.consent_source)
                    if channel.consent_source is not None
                    else None
                ),
                suppressed=channel.suppressed,
            ),
            template_id=INVITATION_TEMPLATE_ID,
            values={
                # Derived from the roster row and the authorized unit, never from
                # the request: a caller naming the professional or the host
                # institution would be a caller writing a message in somebody
                # else's name.
                "professional_name": contact.full_name,
                "unit_name": unit.display_name,
                "event_name": body.event_name,
                "event_date": body.event_date,
                "coordinator_name": body.coordinator_name,
                "response_url": _response_url(token),
            },
        )
    except ConsentViolationError:
        # Unreachable while `choose_invitation_channel` and `compose_draft` ask
        # the same gate, and kept as a *skip* rather than an admission: the day
        # the two disagree, this refuses to compose rather than composing a
        # message the consent layer would have refused.
        _skip(
            session,
            principal,
            unit_id=unit.id,
            batch_id=batch_id,
            professional_id=professional_id,
            reason=SkipReason.CHANNEL_NOT_ACTIVE_CANDIDATE,
        )
        return
    except OutreachCompositionError as exc:  # pragma: no cover - the values are server-built
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_invitation_composition_failed",
            message=str(exc),
        ) from exc

    now = utc_now()
    draft_id = _outreach.create_draft(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit.id,
        contact_channel_id=channel.id,
        template_id=composed.template_id,
        content_status=composed.content_status.value,
        subject=composed.subject,
        body=composed.body,
        created_by=principal.user_id,
        # Composed approved, by the caller, in one act. This is not the outreach
        # surface's two-step: composing a batch of invitations *is* the decision
        # to invite these people, and a Connector who then had to approve twelve
        # drafts one at a time would be doing a second job with no second
        # decision in it. Who approved is still recorded, and it is still never a
        # body field.
        status=DraftStatus.APPROVED.value,
        approved_by=principal.user_id,
        approved_at=now,
    )

    _invites.add_invitation(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit.id,
        batch_id=batch_id,
        professional_id=professional_id,
        status=InvitationStatus.PENDING.value,
        response_status=SpeakerResponse.AWAITING_RESPONSE.value,
        contact_channel_id=channel.id,
        recipient_address=channel.address,
        outreach_draft_id=draft_id,
        response_token_hash=_token_hash(token),
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/speaker-invitations/batches",
    response_model=BatchListResponse,
    summary="List a unit's speaker-invitation batches",
)
def list_invitation_batches(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    limit: Annotated[int, Query(ge=1, le=MAX_BATCH_PAGE_SIZE)] = DEFAULT_BATCH_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BatchListResponse:
    """One unit's batches, newest first, without their outcomes.

    The outcomes are deliberately absent rather than summarised. Folding a
    batch's twelve outcomes into one word would require choosing which fact to
    forget — three skipped, two declined, one still awaiting — and making that
    choice once per row in a list would bury it where nobody reviews it. A reader
    who needs to know what happened to a batch reads that batch.
    """
    charge_quota(session, principal, INVITATION_READ_RATE_LIMIT)

    unit = _authorize_speaker_invitations(session, principal, unit_id)

    batches = _invites.list_batches(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit.id,
        limit=limit,
        offset=offset,
    )

    return BatchListResponse(
        batches=[
            BatchSummaryView(
                batch_id=batch.id,
                match_run_id=batch.match_run_id,
                template_id=batch.template_id,
                event_name=batch.event_name,
                event_date=batch.event_date,
                created_at=batch.created_at.isoformat(),
            )
            for batch in batches
        ],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{unit_id}/speaker-invitations/batches/{batch_id}",
    response_model=BatchResponse,
    summary="Read one invitation batch, its delivery, and its Speaker responses",
)
def read_invitation_batch(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    batch_id: Annotated[uuid.UUID, Path()],
) -> BatchResponse:
    """§13's tracking view: every outcome, with both facts about each kept apart.

    ``delivery`` is what a mail provider did. ``speaker_response`` is what a
    person said. They are separate objects with disjoint vocabularies, and a
    client must not derive either from the other: a message a provider accepted
    may never be read, and a Speaker who accepted may have done so by phone
    against a message that bounced.

    Raises:
        ApiError: 404 when no such batch exists in this unit.
    """
    charge_quota(session, principal, INVITATION_READ_RATE_LIMIT)

    unit = _authorize_speaker_invitations(session, principal, unit_id)
    resolved = _load_batch_or_404(session, principal, unit_id=unit.id, batch_id=batch_id)

    return _batch_response(session, principal, batch_id=resolved, replayed=False)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-invitations/batches/{batch_id}/dispatch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DispatchResponse,
    summary="Submit send commands for a batch's pending invitations",
)
def dispatch_invitation_batch(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    batch_id: Annotated[uuid.UUID, Path()],
) -> DispatchResponse:
    """Submit one ``outreach.send`` per pending invitation. **Nothing is sent.**

    ``202`` and no status field, for ``send_draft``'s reason: each command is
    recorded and the dispatcher has not moved it. Follow each ``events_url``,
    then read the batch.

    **Consent is rechecked here**, per invitation, against state read now — not
    against what was true when the batch was composed. A channel can be
    suppressed, moved back down the lifecycle, or removed in between, and an
    invitation composed before that must not go out after it. A refused
    invitation appears in ``not_dispatched`` with the reason and **stays
    pending**, so resolving the reason and dispatching again works, and so the
    batch never silently loses a recipient. The worker rechecks a third time at
    delivery, which is the only check that closes the window after this returns.

    Dispatching twice is safe in three independent ways, which is deliberate on a
    route that puts mail in inboxes: only ``pending`` invitations are considered,
    ``mark_dispatched`` is guarded on that same status, and each command carries a
    key derived from the invitation id so ``submit_command`` replays rather than
    queues a second send.

    Raises:
        ApiError: 404 when no such batch exists in this unit.
    """
    charge = charge_quota(session, principal, INVITATION_DISPATCH_RATE_LIMIT)

    unit = _authorize_speaker_invitations(session, principal, unit_id)
    resolved = _load_batch_or_404(session, principal, unit_id=unit.id, batch_id=batch_id)

    dispatched: list[DispatchedView] = []
    not_dispatched: list[NotDispatchedView] = []

    for invitation in _invites.list_pending(
        session, tenant_id=principal.tenant_id, batch_id=resolved
    ):
        if invitation.contact_channel_id is None or invitation.outreach_draft_id is None:
            # Structurally impossible: `ck_cba_invitation_addressed` requires both
            # on any row that is not skipped, and skipped rows are not pending.
            # Reported rather than asserted, because a route that crashed on an
            # impossible row would take the whole batch down with it.
            not_dispatched.append(  # pragma: no cover - refused by a CHECK
                NotDispatchedView(invitation_id=invitation.id, reason="invitation_has_no_recipient")
            )
            continue

        facts = _outreach.load_recipient(
            session,
            tenant_id=principal.tenant_id,
            contact_channel_id=invitation.contact_channel_id,
        )
        if facts is None:
            not_dispatched.append(
                NotDispatchedView(
                    invitation_id=invitation.id, reason=SkipReason.NO_CONTACT_CHANNEL.value
                )
            )
            continue

        reason = classify_recipient(facts)
        if reason is not None:
            not_dispatched.append(
                NotDispatchedView(invitation_id=invitation.id, reason=reason.value)
            )
            continue

        accepted = submit_command(
            session,
            principal,
            command_type=OUTREACH_SEND_COMMAND_TYPE,
            # The loaded unit's own id, never a body value — `submit_command`'s
            # `owning_unit_id` contract.
            owning_unit_id=unit.id,
            payload={"draft_id": str(invitation.outreach_draft_id)},
            # Derived from the invitation rather than taken from a header, and
            # that is what makes a re-dispatch safe without the caller having to
            # remember a key: the same invitation always produces the same
            # command, so a second submission replays the first.
            idempotency_key=f"speaker-invitation:{invitation.id}",
            charge=charge,
        )

        _invites.mark_dispatched(
            session,
            tenant_id=principal.tenant_id,
            invitation_id=invitation.id,
            outreach_send_job_id=accepted.job_id,
            dispatched_at=utc_now(),
        )
        # Committed per invitation rather than once at the end. `submit_command`
        # has already committed the job, so leaving the invitation's link to it
        # uncommitted would let a failure halfway through a batch produce jobs
        # whose invitations still read as pending — and the recovery, a second
        # dispatch, would submit under the same key and replay, which is safe but
        # leaves the row wrong until it does.
        session.commit()

        dispatched.append(
            DispatchedView(
                invitation_id=invitation.id,
                job_id=accepted.job_id,
                events_url=f"/v1/jobs/{accepted.job_id}/events",
                replayed=accepted.is_replay,
            )
        )

    return DispatchResponse(batch_id=resolved, dispatched=dispatched, not_dispatched=not_dispatched)


# ---------------------------------------------------------------------------
# Responses — the Connector's record, and the Speaker's own
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-invitations/{invitation_id}/response",
    response_model=RecordResponseResponse,
    summary="Record a Speaker's answer received out of band",
)
def record_invitation_response(
    principal: CurrentPrincipal,
    session: DbSession,
    body: RecordResponseRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    invitation_id: Annotated[uuid.UUID, Path()],
) -> RecordResponseResponse:
    """Record what a Speaker told a Connector — on the phone, in a reply, in person.

    Stored with ``channel='connector_recorded'`` and the coordinator's own id, so
    it is never mistaken for an answer the Speaker gave through their own link.
    Both are real answers; one has a weaker chain of evidence, and a system that
    rendered them identically would be asserting a directness nobody has.

    Repeating the same answer succeeds and writes nothing — the recorded time
    stays the time of the first answer rather than being redated by a repeat. A
    *different* answer is refused with ``409``: overwriting an acceptance erases a
    fact an Event Host may already have booked a room on, and whether a Speaker
    may change their mind is OQ-CBA-044.

    Raises:
        ApiError: 404 when no such invitation exists in this unit; 409 when the
            invitation was never dispatched, or already carries a different
            answer.
    """
    charge_quota(session, principal, INVITATION_RESPONSE_RATE_LIMIT)

    unit = _authorize_speaker_invitations(session, principal, unit_id)

    invitation = _invites.get_invitation(
        session, tenant_id=principal.tenant_id, invitation_id=invitation_id
    )
    if invitation is None or invitation.owning_unit_id != unit.id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_invitation_not_found",
            message="No such speaker invitation in this unit.",
        )

    if invitation.status != InvitationStatus.DISPATCHED.value:
        # 409 rather than 403: the caller may work with this invitation, and the
        # invitation is in a state where an answer does not mean anything. An
        # answer to a message nobody submitted is an answer to nothing.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_invitation_not_dispatched",
            message=(
                f"This invitation is {invitation.status!r}, not 'dispatched'. "
                "Nothing was sent to this person, so there is no invitation for "
                "them to have answered."
            ),
        )

    requested = _speaker_response(body.response)
    try:
        resulting, changed = record_response(SpeakerResponse(invitation.response_status), requested)
    except InvitationResponseConflict as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_invitation_already_answered",
            message=str(exc),
        ) from exc

    if changed:
        _invites.record_response(
            session,
            tenant_id=principal.tenant_id,
            invitation_id=invitation.id,
            response_status=resulting.value,
            response_channel="connector_recorded",
            recorded_at=utc_now(),
            recorded_by_user_id=principal.user_id,
        )
        session.commit()

    return RecordResponseResponse(
        invitation_id=invitation.id, response=resulting.value, recorded=changed
    )


@public_router.post(
    "/v1/speaker-invitations/respond",
    response_model=SpeakerRespondResponse,
    summary="Accept or decline an invitation using its link token",
)
def speaker_respond(session: DbSession, body: SpeakerRespondRequest) -> SpeakerRespondResponse:
    """Record the Speaker's own answer. **Unauthenticated by design.**

    A Speaker on a §13 roster is a *contact*, not an account — nothing in this
    platform issues them a credential — so requiring a session would make the
    route unreachable by the only person it exists for, and §14's "Speakers
    should be able to view invitations" would have to be satisfied by a
    coordinator retyping what they were told. The token is the entire
    authorization: 256 bits minted when the invitation was composed and stored
    only as a SHA-256 hash, so possession of the database confers no ability to
    answer on anybody's behalf.

    ## The response is identical for every token

    A real token and an invented one both return ``{"recorded": true}``, and a
    token that matches nothing writes nothing. This is
    ``routers/outreach.py::unsubscribe``'s posture and it is here for the same
    reason: a ``404`` for an unknown token would turn this route into an oracle,
    letting anyone holding a guess confirm whether a given person was invited to
    speak — which is a fact about a relationship between two institutions and a
    person. Reporting success for an invented token is not a fake success either,
    because the claim is about the *request* ("we have accepted this"), not about
    an invitation we cannot identify.

    Answering twice with the same answer is a no-op and also returns true.
    Answering with a *different* one writes nothing, for
    :func:`record_invitation_response`'s reason — and still answers identically,
    because telling a stranger that a token has already been used is telling them
    the token is real.

    ## What this route cannot do

    It cannot create an answer for an invitation that was never dispatched
    (``record_response`` requires ``status='dispatched'``), and it cannot touch
    consent. A Speaker declining is not a suppression and accepting is not an
    escalation — the two lifecycles are separate, and somebody who declines one
    invitation is still a consented contact who may be invited to a different
    event. A Speaker who wants no more mail at all uses the unsubscribe link,
    which is in the same message.
    """
    row = _invites.resolve_response_token(session, token_hash=_token_hash(body.token))

    if row is not None:
        try:
            resulting, changed = record_response(
                SpeakerResponse(row.response_status), _speaker_response(body.response)
            )
        except InvitationResponseConflict:
            # Refused, silently, and reported as success — see the docstring. The
            # stored answer is untouched.
            return SpeakerRespondResponse(recorded=True)

        if changed:
            _invites.record_response(
                session,
                tenant_id=row.tenant_id,
                invitation_id=row.id,
                response_status=resulting.value,
                response_channel="speaker_link",
                recorded_at=utc_now(),
            )
            session.commit()

    return SpeakerRespondResponse(recorded=True)
