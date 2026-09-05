"""The outreach surface: compose a draft, submit a send, read what happened (card L6).

Six operations, and the shape of the whole module follows from one rule: **the
request path records intent and nothing else** (v1.1 §1.6). Composing a draft
writes a row. Sending submits a command and answers ``202``. Nothing here calls a
provider, and nothing here can — ``tests/unit/test_no_external_calls_on_request_path.py``
asserts that no module under ``services/api/`` imports an HTTP client at all, so
a synchronous send is not merely absent, it is unreachable.

## What each operation is for

* ``POST   /v1/units/{unit_id}/outreach/drafts`` — compose and store a draft.
* ``POST   /v1/units/{unit_id}/outreach/drafts/{draft_id}/send`` — submit
  ``outreach.send``. Returns ``202`` with a job id.
* ``GET    /v1/units/{unit_id}/outreach/drafts`` — a coordinator's list.
* ``GET    /v1/units/{unit_id}/outreach/sends`` — a unit's sends, newest first.
* ``GET    /v1/units/{unit_id}/outreach/sends/{send_id}`` — one send and its
  delivery projection.
* ``POST   /v1/unsubscribe`` — the mutating unsubscribe, unauthenticated by
  design. Lives in this module beside the surface it protects.

The contact channels these operations address — registering one, correcting its
evidence, moving it through the consent lifecycle — are
``routers/outreach_contacts.py``'s, which shares this module's
:func:`_authorize_outreach` rather than declaring a second answer to the same
question.

## The response to a send has no field that could be read as delivery

:class:`SendAcceptedResponse` carries a job id and an events URL. It does not
carry a status, a disposition, or anything a client could render as "sent",
because when it returns *nothing has happened yet*: the command is recorded and
the dispatcher has not moved it. This is the direct correction of B17 in
``docs/plans/frontend-broken-buttons.md`` — the legacy Send button logged to the
console and told the coordinator "Message sent!" — and returning ``200`` with an
optimistic body would be the same defect wearing a real network request.

Delivery is read back from :func:`read_send`, whose ``disposition`` is ``null``
until an attempt concludes. That null is a third state, not a missing value, and
a client must render it as "in progress" rather than as any kind of failure.

## Consent is checked here *and* checked again by the worker

:func:`create_draft` calls ``compose_draft``, which runs the consent gate before
any message text exists. That is not the send-time check — it is what stops a
coordinator from composing a message about someone who may not be contacted, and
what gives them a 403 at the moment they are looking at the screen rather than a
job failure minutes later. The gate that actually protects the recipient is the
worker's, against state read at delivery time.

:func:`send_draft` runs the same gate a third time, against the contact as it
stands when the send is submitted. All three matter and none is redundant, and
what distinguishes them is *which window they close*. Composition proves what
was true while a coordinator was looking at the screen. Submission catches a
withdrawal in the hours between composing and sending, and reports it to the
person who is acting rather than as a job failure nobody is watching. The
worker's catches the window after the ``202``, which no request-path check can
see, and it is the one that actually protects the recipient.

Removing the first would let ineligible drafts accumulate. Removing the second
would turn every withdrawn consent into a failed job. Removing the third would
let an unsubscribe between approval and delivery be ignored — the only one of
the three whose absence reaches a real person.

## Why approval is not its own route

A draft is created ``draft`` or ``approved`` in one call, by the same
coordinator, and there is deliberately no ``POST .../approve``. Two-person
approval is a policy nobody has ratified, and a route that let one person create
and a second approve would be *implying* a control that does not exist — the
approver field would record a second name without any rule requiring one. What
is stored is honest: who composed it, and who approved it, which today is the
same person, and the schema is ready for the day a policy says otherwise.

## Quota is charged first

ADR-0015's ordering, ahead of the load, the authorization, and the validation, so
a caller producing 404s against invented ids spends exactly what a caller
composing real drafts spends.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Header, Path, Query, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.consent import (
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_send_eligible,
)
from smartmatch_domain.outreach import (
    OUTREACH_SEND_COMMAND_TYPE,
    TEMPLATES,
    DraftRecipient,
    DraftStatus,
    OutreachCompositionError,
    compose_draft,
)
from smartmatch_persistence.outreach import (
    DEFAULT_DRAFT_PAGE_SIZE,
    DEFAULT_SEND_PAGE_SIZE,
    MAX_DRAFT_PAGE_SIZE,
    MAX_SEND_PAGE_SIZE,
    OutreachRepository,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.commands import submit_command
from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["outreach"])

#: A second router for the one operation that is not unit-scoped and not
#: authenticated. Separate rather than a path exception on the router above,
#: because "this route takes no principal" is a property worth being visible in
#: the declaration rather than discoverable by reading a handler.
public_router = APIRouter(tags=["outreach"])

_repo: Final[OutreachRepository] = OutreachRepository()

#: Roles that may compose, list, send, and read. The same set for all four: a
#: widening applies to the whole surface or to none of it, and cannot reach one
#: operation by accident (``_authorize_match_run`` makes the same argument).
_OUTREACH_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: Composition is cheap; sending is the consequential one, and its limit is
#: tighter for that reason rather than for a capacity one. A coordinator who can
#: submit sixty sends a minute can empty a contact list before anyone notices.
DRAFT_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="outreach.draft", max_requests=60, window=timedelta(minutes=1)
)
SEND_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="outreach.send", max_requests=20, window=timedelta(minutes=1)
)
READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="outreach.read", max_requests=120, window=timedelta(minutes=1)
)

# **No `UNSUBSCRIBE_RATE_LIMIT`, and the absence is deliberate.** The obvious
# thing to write here is a limit like the three above, and it cannot be written
# honestly. `charge_quota` keys a counter by tenant and user id, and
# `rate_limit_counter.tenant_id` carries a foreign key to `tenant` — so applying
# it to an unauthenticated route requires inventing a tenant that does not
# exist, and the database refuses the row (which is how this was found: an
# earlier draft of this module used a nil-UUID stand-in principal and every
# unsubscribe request failed on the constraint).
#
# Inventing a `tenant` row to hang the counter off would have satisfied the
# constraint and been worse: a synthetic tenant that exists only to make a
# limiter work is a row every tenant-scoped query in the system now has to know
# to ignore.
#
# So this route is not application-rate-limited, and that is stated rather than
# papered over. It is an unauthenticated POST that writes at most one row per
# distinct valid token and nothing at all for an invalid one, so the blast
# radius of abuse is bounded by the constraint on `suppression_record` rather
# than by a counter. A real deployment puts an edge rate limit in front of it;
# OQ-006, where the one-click decision lives, is where that belongs.


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class DraftRequest(BaseModel):
    """Compose one message from a registry template.

    Note what cannot be supplied: **body text**. A caller names a template and
    its placeholder values, and the closed registry in
    ``smartmatch_domain.outreach`` decides what the words are. Accepting free-form
    text would reopen by a different door the hole the template registry closes —
    there would be nothing stopping a message that asks a scraped address to opt
    in, which ``consent.py`` records as itself prohibited outreach.
    """

    contact_channel_id: uuid.UUID = Field(description="The stored contact to address.")
    template_id: str = Field(
        description="A key of the closed outreach template registry.",
        examples=sorted(TEMPLATES),
    )
    values: dict[str, str] = Field(
        description="Exactly the template's declared placeholders — no more, no fewer."
    )
    approve: bool = Field(
        default=False,
        description=(
            "Approve this draft on creation. An unapproved draft cannot be sent. "
            "Defaults to false so approving is an act, not an omission."
        ),
    )


class DraftResponse(BaseModel):
    """One stored draft, including the text that was actually composed."""

    draft_id: uuid.UUID
    contact_channel_id: uuid.UUID
    template_id: str
    content_status: str = Field(
        description=(
            "'synthetic' for pilot copy that has not been through institutional "
            "review, 'reviewed' otherwise. A synthetic draft sends against the "
            "fixture provider and is refused by a live send."
        )
    )
    subject: str
    body: str
    status: str
    version: int
    recipient_address: str


class DraftListResponse(BaseModel):
    """A page of drafts, and how many were asked for."""

    drafts: list[DraftResponse]
    limit: int
    offset: int


class SendAcceptedResponse(BaseModel):
    """What a submitted send command reports.

    A job id and where to follow it. **No status field**, deliberately: when
    this is returned nothing has been sent, and the smallest hint otherwise is
    the fake success this whole slice exists to remove.
    """

    job_id: uuid.UUID
    events_url: str
    replayed: bool = Field(
        description="True when this exact request had already been accepted under the same key."
    )


class DeliveryEventView(BaseModel):
    """One entry of the append-only delivery stream."""

    event_type: str
    occurred_at: str
    provider_event_id: str | None


class SendResponse(BaseModel):
    """One send attempt and the events recorded against it."""

    send_id: uuid.UUID
    draft_id: uuid.UUID
    job_id: uuid.UUID
    recipient_address: str
    disposition: str | None = Field(
        description=(
            "'accepted', 'blocked', 'failed', or null while the attempt is still "
            "in flight. Null is a third state, not a missing value: render it as "
            "in-progress, never as a failure. Note that 'accepted' means a "
            "provider took custody — delivery is a later event in the stream, "
            "and may never arrive."
        )
    )
    provider: str | None
    provider_message_id: str | None
    failure_reason: str | None
    delivery_events: list[DeliveryEventView]


class SendSummaryView(BaseModel):
    """One send in a listing, without its delivery stream.

    The stream is deliberately absent rather than summarised. Folding a send's
    events into one word is a choice about which fact to forget — a provider can
    report ``delivered`` and then ``complained`` — and making that choice once
    per row in a list would bury it where nobody reviews it. A reader who needs
    to explain what happened to one message reads that send.
    """

    send_id: uuid.UUID
    draft_id: uuid.UUID
    job_id: uuid.UUID
    recipient_address: str
    disposition: str | None = Field(
        description=(
            "'accepted', 'blocked', 'failed', or null while the attempt is still "
            "in flight. Null is a third state: render it as in-progress, never as "
            "a failure."
        )
    )
    provider: str | None
    provider_message_id: str | None
    failure_reason: str | None
    created_at: str
    concluded_at: str | None = Field(
        description="When the attempt reached an outcome, or null while it has not."
    )


class SendListResponse(BaseModel):
    """A page of sends, and how many were asked for."""

    sends: list[SendSummaryView]
    limit: int
    offset: int


class UnsubscribeRequest(BaseModel):
    """The signed token from a message's unsubscribe link."""

    token: str = Field(min_length=16, max_length=256)


class UnsubscribeResponse(BaseModel):
    """The answer to an unsubscribe, which is the same for every token.

    See :func:`unsubscribe`: a response that distinguished a real token from an
    invented one would let anyone holding a guess confirm whether an address is
    on our list.
    """

    unsubscribed: bool = Field(
        description="Always true. The request was accepted; nothing is confirmed about the token."
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_outreach(
    session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID
) -> uuid.UUID:
    """Load the unit and authorize a coordinator against *that row's* path.

    Shared by all four unit-scoped operations, in the spirit of
    ``_authorize_match_run``: they ask the identical question against the
    identical resource, so a widening applies to all of them or to none.

    ``load_unit_or_404`` scopes the lookup by the caller's own tenant, so a unit
    in another tenant is a 404 rather than a 403 that would confirm the id names
    something real.

    Returns:
        The loaded unit's own id — the value handed to ``submit_command`` as
        ``owning_unit_id``, so the job is filed under the subtree the request
        was actually permitted for, never one read out of a body.
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
        required_roles=_OUTREACH_ROLES,
    )
    return unit.id


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/outreach/drafts",
    status_code=status.HTTP_201_CREATED,
    response_model=DraftResponse,
    summary="Compose an outreach draft",
)
def create_draft(
    principal: CurrentPrincipal,
    session: DbSession,
    body: DraftRequest,
    unit_id: Annotated[uuid.UUID, Path()],
) -> DraftResponse:
    """Compose a message and store it. Nothing is sent.

    ``201`` rather than ``202``: unlike the send, this *has* completed when it
    returns — a row exists and a coordinator can read it back. Reserving ``202``
    for the operation that genuinely defers work is what keeps the distinction
    meaningful.

    The consent gate runs inside ``compose_draft``, before any message text
    exists, so an ineligible recipient never has a body composed about them. A
    refusal is a ``403``, not a ``422``: the caller is not permitted to write to
    this person, which is an authorization fact, and reporting it as a validation
    problem would invite them to try different inputs.

    Raises:
        ApiError: 404 when the contact does not exist in this tenant; 403 when
            the recipient may not be contacted; 400 when the template is unknown
            or the placeholder values do not match it.
    """
    # Charged, and the receipt discarded: this route writes a row directly
    # rather than submitting a command, so there is no `submit_command` to
    # hand it to. The charge is still first, per ADR-0015's ordering.
    charge_quota(session, principal, DRAFT_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)

    facts = _repo.load_recipient(
        session,
        tenant_id=principal.tenant_id,
        contact_channel_id=body.contact_channel_id,
    )
    if facts is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="contact_channel_not_found",
            message="No such contact channel.",
        )
    if facts.owning_unit_id != owning_unit_id:
        # A 404, not a 403. The contact exists but not under a unit this request
        # was authorized for, and saying "forbidden" would confirm that an id the
        # caller may not read names something real.
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="contact_channel_not_found",
            message="No such contact channel.",
        )

    try:
        composed = compose_draft(
            recipient=DraftRecipient(
                address=facts.address,
                contact_state=ContactState(facts.contact_state),
                consent_source=(
                    ConsentSource(facts.consent_source)
                    if facts.consent_source is not None
                    else None
                ),
                suppressed=facts.suppressed,
            ),
            template_id=body.template_id,
            values=body.values,
        )
    except ConsentViolationError as exc:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="outreach_recipient_not_eligible",
            message=(
                f"This recipient may not be contacted: {exc} No message was composed "
                "— the consent check runs before any text is rendered."
            ),
        ) from exc
    except OutreachCompositionError as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="outreach_composition_failed",
            message=str(exc),
        ) from exc

    approved_at = utc_now() if body.approve else None
    draft_id = _repo.create_draft(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        contact_channel_id=body.contact_channel_id,
        template_id=composed.template_id,
        content_status=composed.content_status.value,
        subject=composed.subject,
        body=composed.body,
        created_by=principal.user_id,
        status=(DraftStatus.APPROVED if body.approve else DraftStatus.DRAFT).value,
        # The approver is the authenticated caller, never a body field. Letting a
        # request name who approved it would be the caller-selected-identity
        # pattern (MM-A01) in the one place it would matter most.
        approved_by=principal.user_id if body.approve else None,
        approved_at=approved_at,
    )
    session.commit()

    return DraftResponse(
        draft_id=draft_id,
        contact_channel_id=body.contact_channel_id,
        template_id=composed.template_id,
        content_status=composed.content_status.value,
        subject=composed.subject,
        body=composed.body,
        status=(DraftStatus.APPROVED if body.approve else DraftStatus.DRAFT).value,
        version=1,
        recipient_address=composed.recipient_address,
    )


@router.get(
    "/{unit_id}/outreach/drafts",
    response_model=DraftListResponse,
    summary="List a unit's outreach drafts",
)
def list_drafts(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    limit: Annotated[int, Query(ge=1, le=MAX_DRAFT_PAGE_SIZE)] = DEFAULT_DRAFT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DraftListResponse:
    """One unit's drafts, newest first.

    ``limit`` is bounded by the query validator *and* clamped again in the
    repository. Not redundant: the repository is also reachable from the worker,
    and a bound that only exists in a route is a bound that stops applying the
    moment a second caller appears.

    The recipient address is resolved per draft rather than joined, which is a
    page-sized number of small lookups. Left simple deliberately — a coordinator
    list is a screen, not an export, and MAX_DRAFT_PAGE_SIZE is what keeps that
    true.
    """
    charge_quota(session, principal, READ_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)

    drafts = _repo.list_drafts(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        limit=limit,
        offset=offset,
    )

    return DraftListResponse(
        drafts=[
            DraftResponse(
                draft_id=draft.id,
                contact_channel_id=draft.contact_channel_id,
                template_id=draft.template_id,
                content_status=draft.content_status,
                subject=draft.subject,
                body=draft.body,
                status=draft.status,
                version=draft.version,
                recipient_address=_address_for(session, principal, draft.contact_channel_id),
            )
            for draft in drafts
        ],
        limit=limit,
        offset=offset,
    )


def _address_for(
    session: Session, principal: CurrentPrincipal, contact_channel_id: uuid.UUID
) -> str:
    """The contact's address, or an explicit marker when the contact is gone.

    ``"(contact removed)"`` rather than an empty string or the id. A blank would
    render as a message addressed to nobody, and the id would render as an
    address that is not one — both are the fabricated-field shape. The marker
    says what is true: the draft survives, and the contact it named does not.
    """
    facts = _repo.load_recipient(
        session, tenant_id=principal.tenant_id, contact_channel_id=contact_channel_id
    )
    return facts.address if facts is not None else "(contact removed)"


# ---------------------------------------------------------------------------
# The send command
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/outreach/drafts/{draft_id}/send",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SendAcceptedResponse,
    summary="Submit an outreach send command",
)
def send_draft(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    draft_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description="Required. Makes retries safe."),
    ] = None,
) -> SendAcceptedResponse:
    """Enqueue ``outreach.send``. **Nothing is sent when this returns.**

    ``202``, and the response body carries no status: the command is recorded and
    the dispatcher has not moved it. Follow ``events_url``, then read the send.

    The draft's approval and the recipient's current eligibility are both
    checked here so a coordinator is told immediately rather than by a job
    failure — but neither is the gate that protects the recipient. That one is
    the worker's, run against state read at delivery time, because consent can
    be withdrawn in the window this route cannot see. The eligibility check runs
    before the approval check on purpose: "this person may not be written to" is
    the more consequential fact of the two, and it is the one worth reporting
    first when both are true.

    Raises:
        ApiError: 404 when the draft is not in this unit; 403 when the recipient
            may no longer be contacted; 409 when the draft is not approved or
            its contact has been removed; 400 when the idempotency key is
            missing.
    """
    charge = charge_quota(session, principal, SEND_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)

    draft = _repo.get_draft(session, tenant_id=principal.tenant_id, draft_id=draft_id)
    if draft is None or draft.owning_unit_id != owning_unit_id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="outreach_draft_not_found",
            message="No such outreach draft in this unit.",
        )

    facts = _repo.load_recipient(
        session, tenant_id=principal.tenant_id, contact_channel_id=draft.contact_channel_id
    )
    if facts is None:
        # The draft outlived its contact. `_address_for` renders that as
        # "(contact removed)" in a listing, which is fine for a screen and is
        # not fine here: submitting a send whose recipient nothing can be
        # checked against is the one thing this route must never do.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="outreach_recipient_missing",
            message=(
                "The contact this draft addresses no longer exists, so its consent "
                "cannot be checked. Nothing was submitted."
            ),
        )

    try:
        assert_send_eligible(
            ContactState(facts.contact_state),
            consent_source=(
                ConsentSource(facts.consent_source) if facts.consent_source is not None else None
            ),
            suppressed=facts.suppressed,
        )
    except ConsentViolationError as exc:
        # Not redundant with the composition-time check and not redundant with
        # the worker's. Composition proves what was true when a coordinator was
        # looking at the screen; consent can be withdrawn, or a contact moved
        # back down the lifecycle, in the hours between composing and sending.
        # Refusing here means the coordinator is told at the moment they act,
        # rather than by a job that fails minutes later — and the worker still
        # rechecks against state read at delivery time, because this route
        # cannot see the window after it returns.
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="outreach_recipient_not_eligible",
            message=(f"This recipient may not be contacted: {exc} No send was submitted."),
        ) from exc

    if draft.status != DraftStatus.APPROVED.value:
        # 409 rather than 403: the caller is permitted to send from this unit,
        # and the draft is in a state where sending does not mean anything yet.
        # A 403 would send them looking at their roles for a problem that is
        # about the resource.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="outreach_draft_not_approved",
            message=(
                f"The draft is {draft.status!r}, not 'approved'. A draft records an "
                "intention to send; the approval is what a named actor signed off on."
            ),
        )

    accepted = submit_command(
        session,
        principal,
        command_type=OUTREACH_SEND_COMMAND_TYPE,
        # The loaded row's own id, never a body value — `submit_command`'s
        # `owning_unit_id` contract.
        owning_unit_id=owning_unit_id,
        payload={"draft_id": str(draft_id)},
        idempotency_key=idempotency_key,
        charge=charge,
    )

    return SendAcceptedResponse(
        job_id=accepted.job_id,
        events_url=f"/v1/jobs/{accepted.job_id}/events",
        replayed=accepted.is_replay,
    )


@router.get(
    "/{unit_id}/outreach/sends",
    response_model=SendListResponse,
    summary="List a unit's outreach sends",
)
def list_sends(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    limit: Annotated[int, Query(ge=1, le=MAX_SEND_PAGE_SIZE)] = DEFAULT_SEND_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SendListResponse:
    """One unit's send attempts, newest first.

    The listing the coordinator surface was missing: drafts could be listed and
    a single send could be read by id, so the only way to see what a unit had
    actually attempted was to have kept the ids. OQ-008 records that this slice
    stores sends rather than threads, and this is that list — send records, not
    a conversation. Nothing here implies a reply exists.

    A send whose ``disposition`` is null is in flight. That is a third state and
    a client must render it as in-progress; treating null as a failure is the
    same defect as treating a submitted command as a delivered message.

    Delivery events are not included per row — see :class:`SendSummaryView`. A
    reader who needs the stream reads the send.
    """
    charge_quota(session, principal, READ_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)

    sends = _repo.list_sends(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        limit=limit,
        offset=offset,
    )

    return SendListResponse(
        sends=[
            SendSummaryView(
                send_id=send.id,
                draft_id=send.draft_id,
                job_id=send.job_id,
                recipient_address=send.recipient_address,
                disposition=send.disposition,
                provider=send.provider,
                provider_message_id=send.provider_message_id,
                failure_reason=send.failure_reason,
                created_at=send.created_at.isoformat(),
                concluded_at=(
                    send.concluded_at.isoformat() if send.concluded_at is not None else None
                ),
            )
            for send in sends
        ],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{unit_id}/outreach/sends/{send_id}",
    response_model=SendResponse,
    summary="Read one outreach send and its delivery events",
)
def read_send(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    send_id: Annotated[uuid.UUID, Path()],
) -> SendResponse:
    """One send attempt, with the events recorded against it.

    The delivery stream is returned rather than folded into a single status,
    because folding it would require choosing which fact to forget: a provider
    can report ``delivered`` and then ``complained`` an hour later, and both are
    true. A client that wants one word can project the stream itself; a client
    that wants to explain what happened to a coordinator needs all of it.

    Raises:
        ApiError: 404 when the send is not in this unit.
    """
    charge_quota(session, principal, READ_RATE_LIMIT)

    owning_unit_id = _authorize_outreach(session, principal, unit_id)

    send = _repo.get_send(session, tenant_id=principal.tenant_id, send_id=send_id)
    if send is None or send.owning_unit_id != owning_unit_id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="outreach_send_not_found",
            message="No such outreach send in this unit.",
        )

    events = _repo.list_delivery_events(session, tenant_id=principal.tenant_id, send_id=send_id)

    return SendResponse(
        send_id=send.id,
        draft_id=send.draft_id,
        job_id=send.job_id,
        recipient_address=send.recipient_address,
        disposition=send.disposition,
        provider=send.provider,
        provider_message_id=send.provider_message_id,
        failure_reason=send.failure_reason,
        delivery_events=[
            DeliveryEventView(
                event_type=event.event_type,
                occurred_at=event.occurred_at.isoformat(),
                provider_event_id=event.provider_event_id,
            )
            for event in events
        ],
    )


# ---------------------------------------------------------------------------
# Unsubscribe — the mutating half of the pair GET /u/{token} completes
# ---------------------------------------------------------------------------


@public_router.post(
    "/v1/unsubscribe",
    response_model=UnsubscribeResponse,
    summary="Unsubscribe using a signed token",
)
def unsubscribe(session: DbSession, body: UnsubscribeRequest) -> UnsubscribeResponse:
    """Suppress the address a token belongs to. **Unauthenticated by design.**

    This is the mutating half of the pair whose read half is ``GET /u/{token}``.
    The split is v1.1 §1.10's correction of the v1.0 mutating GET: a GET is
    reached by link scanners, mail-client prefetchers, and security proxies,
    which would silently unsubscribe recipients who never clicked. So the GET
    renders a page and this POST does the work.

    No principal, and no way to add one. RFC 8058 one-click unsubscribe is
    issued by the recipient's *mail provider* with no session at all, and a
    person who has stopped reading our mail should not have to sign in to stop
    receiving it. The token is the entire authorization: 256 bits derived by
    HMAC in the worker, stored only as a SHA-256 hash, so possession of the
    database does not confer the ability to unsubscribe anybody.

    ## The response is identical for every token

    A real token and an invented one both return ``{"unsubscribed": true}``, and
    a token that matches nothing writes nothing. This is not sloppiness about
    errors — it is the point. A ``404`` for an unknown token would turn this
    route into an oracle: anyone could confirm whether a guessed token, and
    therefore an address, is on our list. Reporting success for an invented
    token is not a fake success either, because the claim being made is about
    the *request* ("we have accepted this"), not about a person we cannot
    identify.

    Repeating an unsubscribe is a no-op and also returns true. Someone clicking
    twice has not made an error, and showing them one would be alarming for no
    reason.
    """
    token_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    row = _repo.resolve_unsubscribe_token(session, token_hash=token_hash)

    if row is not None:
        _repo.suppress(
            session,
            tenant_id=row.tenant_id,
            address=row.recipient_address,
            source="unsubscribe_link",
            suppressed_at=utc_now(),
            origin_send_id=row.id,
        )
        session.commit()

    return UnsubscribeResponse(unsubscribed=True)
