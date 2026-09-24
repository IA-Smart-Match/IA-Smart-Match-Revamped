"""The signed-in Speaker's own routes (B26 T6b-2).

* ``GET   /v1/me/availability`` · ``PATCH /v1/me/availability``
* ``GET   /v1/me/invitations`` · ``POST /v1/me/invitations/{invitation_id}/response``
* ``GET   /v1/me/engagements?when=upcoming|past``

Mounted only under ``Capability.SPEAKER_PORTAL`` (off in every scope).

## Subject

**No route takes a subject.** The only path parameter is ``invitation_id`` and
the only query parameter is ``when``. The subject is the profile bound to
``principal.user_id`` (:func:`_authorize_speaker_self`), and every row is keyed
by that profile's ``professional_id``, never by the login id: after T6b-5's
merged login the two differ (MM-A01).

## Order in every handler

1. ``charge_quota`` (ADR-0015): an unlinked caller pays too.
2. :func:`_authorize_speaker_self`: ``404 speaker_profile_not_linked`` when no
   profile is bound to the login, else ``{speaker}`` at the profile's unit
   (``403``).
3. Route work, scoped by the caller's tenant and ``bound.professional_id``.
4. Writes commit, then answer. Reads never commit.

T6b-3 imports :func:`_authorize_speaker_self`, :data:`_SPEAKER_SELF_ROLES`,
:class:`SpeakerPortalRepository` and :class:`BoundSpeakerProfile` from this
module. Renaming any of them is a cross-track change.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Final, Literal, cast

from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel, ConfigDict
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.cba_invitations import (
    InvitationResponseConflict,
    SpeakerResponse,
    record_response,
)
from smartmatch_persistence.cba_invitations import InvitationRepository, SpeakerInvitationRow
from smartmatch_persistence.pipeline import PipelineRepository, SpeakerEngagementRow
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.speaker_availability import (
    AvailabilitySource,
    SpeakerAvailabilityRepository,
)
from smartmatch_persistence.speaker_portal import BoundSpeakerProfile, SpeakerPortalRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError, ErrorEnvelope
from smartmatch_api.routers.cba_invitations import _speaker_response
from smartmatch_api.routers.speaker_availability_models import (
    SpeakerAvailabilityResponse,
    SpeakerAvailabilityUpdateRequest,
    availability_response,
    stale_error,
    statement_from_request,
    write_statement,
)
from smartmatch_api.utils import utc_now

__all__ = [
    "MAX_ROWS",
    "SPEAKER_SELF_READ_RATE_LIMIT",
    "SPEAKER_SELF_WRITE_RATE_LIMIT",
    "BoundSpeakerProfile",
    "SpeakerOwnResponseRequest",
    "SpeakerPortalRepository",
    "engagement_state",
    "engagement_view",
    "invitation_view",
    "router",
]

router = APIRouter(prefix="/v1/me", tags=["speaker-portal"])

_LOGGER = logging.getLogger(__name__)

_portal: Final[SpeakerPortalRepository] = SpeakerPortalRepository()
_invites: Final[InvitationRepository] = InvitationRepository()
_availability: Final[SpeakerAvailabilityRepository] = SpeakerAvailabilityRepository()
_pipeline: Final[PipelineRepository] = PipelineRepository()

#: The Speaker, and nobody else. A Connector reads a contact through T3's and
#: the roster's routes; an Event Host (``volunteer``) is not a Speaker.
_SPEAKER_SELF_ROLES: Final[frozenset[str]] = frozenset({"speaker"})

#: The ``cba_contacts.py`` numbers: the write is the consequential one.
SPEAKER_SELF_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_self.read", max_requests=120, window=timedelta(minutes=1)
)
SPEAKER_SELF_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_self.write", max_requests=30, window=timedelta(minutes=1)
)

#: G3's 200-record cap, as ``cba_contacts.MAX_ROWS``. No paging: ``truncated``
#: keeps a full page from reading as a complete one.
MAX_ROWS: Final[int] = 200

InvitationStatus = Literal["awaiting_response", "accepted_invitation", "declined_invitation"]
EngagementWhen = Literal["upcoming", "past"]
EngagementState = Literal["confirmed", "attended", "cancelled"]
TimePrecision = Literal["exact", "date_only", "unresolved"]

#: A Speaker's own answer, by link or signed in, reads as ``speaker``; a
#: Connector's entry as ``speaker_connector``. Never a user id.
_RECORDED_BY: Final[dict[str, Literal["speaker", "speaker_connector"]]] = {
    "speaker_link": "speaker",
    "speaker_portal": "speaker",
    "connector_recorded": "speaker_connector",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SpeakerOwnResponseRequest(BaseModel):
    """The Speaker's answer. No subject, channel or actor field (MM-A01)."""

    model_config = ConfigDict(extra="forbid")

    response: Literal["accept", "decline"]


class MyInvitationEvent(BaseModel):
    """What the invitation said, and the event's own date once one is linked."""

    title: str
    #: Verbatim from the invitation; never parsed.
    date_text: str
    local_date: date | None
    time_zone: str | None


class MyInvitationResponse(BaseModel):
    recorded_at: datetime
    recorded_by: Literal["speaker", "speaker_connector"]


class MyInvitation(BaseModel):
    invitation_id: uuid.UUID
    event: MyInvitationEvent
    #: When the send was queued. Not proof of delivery.
    dispatched_at: datetime
    status: InvitationStatus
    #: ``null`` while awaiting an answer.
    response: MyInvitationResponse | None
    answerable: bool


class MyInvitationList(BaseModel):
    invitations: list[MyInvitation]
    truncated: bool


class MyInvitationAnswerResult(BaseModel):
    invitation: MyInvitation
    #: ``false`` when the same answer was already recorded; nothing was written.
    recorded: bool


class MyEngagementEvent(BaseModel):
    title: str
    #: The event's date in its own time zone.
    local_date: date | None
    time_zone: str | None
    time_precision: TimePrecision
    starts_at: datetime | None
    ends_at: datetime | None


class MyEngagement(BaseModel):
    engagement_id: uuid.UUID
    #: ``null`` when the journey's event row is missing.
    event: MyEngagementEvent | None
    state: EngagementState
    confirmed_at: datetime
    attended_at: datetime | None
    cancelled_at: datetime | None


class MyEngagementList(BaseModel):
    when: EngagementWhen
    #: The UTC date the split was made against.
    as_of: date
    engagements: list[MyEngagement]
    truncated: bool


# ---------------------------------------------------------------------------
# View builders (pure)
# ---------------------------------------------------------------------------


def engagement_state(row: SpeakerEngagementRow) -> EngagementState:
    """Cancelled, else attended, else confirmed."""
    if row.cancelled_at is not None:
        return "cancelled"
    if row.attended_at is not None:
        return "attended"
    return "confirmed"


def invitation_view(row: SpeakerInvitationRow) -> MyInvitation:
    """One own invitation; no batch, recipient, delivery or recorder id."""
    response = None
    if row.response_recorded_at is not None and row.response_channel is not None:
        response = MyInvitationResponse(
            recorded_at=row.response_recorded_at,
            recorded_by=_RECORDED_BY[row.response_channel],
        )
    return MyInvitation(
        invitation_id=row.id,
        event=MyInvitationEvent(
            title=row.event_name,
            date_text=row.event_date,
            local_date=row.event_local_date,
            time_zone=row.event_time_zone,
        ),
        dispatched_at=row.dispatched_at,
        status=cast(InvitationStatus, row.response_status),
        response=response,
        answerable=row.response_status == "awaiting_response",
    )


def engagement_view(row: SpeakerEngagementRow) -> MyEngagement:
    """One own engagement; no canceller, unit, provenance or other person."""
    event = None
    if row.event_title is not None:
        event = MyEngagementEvent(
            title=row.event_title,
            local_date=row.event_local_date,
            time_zone=row.event_time_zone,
            time_precision=cast(TimePrecision, row.event_time_precision),
            starts_at=row.event_starts_at,
            ends_at=row.event_ends_at,
        )
    return MyEngagement(
        engagement_id=row.id,
        event=event,
        state=engagement_state(row),
        confirmed_at=row.confirmed_at,
        attended_at=row.attended_at,
        cancelled_at=row.cancelled_at,
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_speaker_self(session: Session, principal: CurrentPrincipal) -> BoundSpeakerProfile:
    """Resolve the caller's bound profile, then require ``speaker`` at its unit.

    The lookup reads only ``principal.user_id``, so the 404 is no oracle. Any
    role that is not bound gets the same 404; a bound login without an active
    ``speaker`` membership covering the profile's unit gets ``403``.

    Raises:
        ApiError: 404 ``speaker_profile_not_linked``; 403 ``forbidden``.
    """
    bound = _portal.find_bound_profile(
        session, tenant_id=principal.tenant_id, account_user_id=principal.user_id
    )
    if bound is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_profile_not_linked",
            message="No Speaker profile is linked to this account.",
        )
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(bound.owning_unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(bound.owning_unit_path),
        ),
        at=utc_now(),
        required_roles=_SPEAKER_SELF_ROLES,
    )
    return bound


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        403: "Bound, but no active `speaker` membership covers the profile's unit.",
        404: "No Speaker profile is linked to this account, or no such invitation of yours.",
        409: "A conflicting write: re-read and try again.",
        422: "The body or query is malformed, or a statement breaks a limit.",
        429: "Quota spent. Charged before anything else.",
    }
    return {code: {"model": ErrorEnvelope, "description": descriptions[code]} for code in codes}


def _invitation_not_found() -> ApiError:
    """One code, one message for unknown, another Speaker's, and never-sent."""
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="speaker_invitation_not_found",
        message="No such speaker invitation.",
    )


def _decide(row: SpeakerInvitationRow, requested: SpeakerResponse) -> tuple[SpeakerResponse, bool]:
    """The domain's answer rule; a different second answer is ``409``."""
    try:
        return record_response(SpeakerResponse(row.response_status), requested)
    except InvitationResponseConflict as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_invitation_already_answered",
            message=str(exc),
        ) from exc


@router.get(
    "/availability",
    response_model=SpeakerAvailabilityResponse,
    summary="Read my stated availability",
    responses=_errors(403, 404, 429),
)
def get_my_availability(
    principal: CurrentPrincipal, session: DbSession
) -> SpeakerAvailabilityResponse:
    """The bound profile's statement, or ``stated: false`` when there is none."""
    charge_quota(session, principal, SPEAKER_SELF_READ_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    stored = _availability.get(
        session, tenant_id=principal.tenant_id, professional_id=bound.professional_id
    )
    return availability_response(bound.professional_id, stored)


@router.patch(
    "/availability",
    response_model=SpeakerAvailabilityResponse,
    summary="Replace my stated availability",
    responses=_errors(403, 404, 409, 429),
)
def update_my_availability(
    principal: CurrentPrincipal, session: DbSession, body: SpeakerAvailabilityUpdateRequest
) -> SpeakerAvailabilityResponse:
    """Full replace through T3's one write path, recorded with source ``speaker``.

    Raises:
        ApiError: 409 ``speaker_availability_stale``; 422 with a
            ``speaker_availability_*`` code.
    """
    charge_quota(session, principal, SPEAKER_SELF_WRITE_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    stored = _availability.get(
        session, tenant_id=principal.tenant_id, professional_id=bound.professional_id
    )
    if body.expected_version != (stored.version if stored is not None else None):
        raise stale_error()

    now = utc_now()
    today = now.date()
    result = write_statement(
        session,
        _availability,
        tenant_id=principal.tenant_id,
        professional_id=bound.professional_id,
        statement=statement_from_request(body, stored, today),
        today=today,
        source=AvailabilitySource.SPEAKER,
        actor_user_id=principal.user_id,
        expected_version=body.expected_version,
        now=now,
    )
    session.commit()
    return availability_response(bound.professional_id, result)


@router.get(
    "/invitations",
    response_model=MyInvitationList,
    summary="List the invitations sent to me",
    responses=_errors(403, 404, 429),
)
def list_my_invitations(principal: CurrentPrincipal, session: DbSession) -> MyInvitationList:
    """Own ``dispatched`` invitations, newest first, capped at :data:`MAX_ROWS`."""
    charge_quota(session, principal, SPEAKER_SELF_READ_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    rows = _invites.list_for_professional(
        session,
        tenant_id=principal.tenant_id,
        professional_id=bound.professional_id,
        limit=MAX_ROWS + 1,
    )
    return MyInvitationList(
        invitations=[invitation_view(row) for row in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
    )


@router.post(
    "/invitations/{invitation_id}/response",
    response_model=MyInvitationAnswerResult,
    summary="Answer an invitation sent to me",
    responses=_errors(403, 404, 409, 429),
)
def answer_my_invitation(
    principal: CurrentPrincipal,
    session: DbSession,
    invitation_id: Annotated[uuid.UUID, Path()],
    body: SpeakerOwnResponseRequest,
) -> MyInvitationAnswerResult:
    """Record the Speaker's own answer: channel ``speaker_portal``, actor the login.

    The first answer stands. The same answer again is ``recorded: false``; a
    different one is ``409`` (OQ-CBA-044). Accepting writes only the
    invitation: no pipeline stage and no consent change.

    Raises:
        ApiError: 404 ``speaker_invitation_not_found``; 409
            ``speaker_invitation_already_answered`` or
            ``speaker_invitation_response_conflict``.
    """
    charge_quota(session, principal, SPEAKER_SELF_WRITE_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    row = _invites.get_for_professional(
        session,
        tenant_id=principal.tenant_id,
        professional_id=bound.professional_id,
        invitation_id=invitation_id,
    )
    if row is None:
        raise _invitation_not_found()

    requested = _speaker_response(body.response)
    resulting, changed = _decide(row, requested)
    if not changed:
        return MyInvitationAnswerResult(invitation=invitation_view(row), recorded=False)

    wrote = _invites.record_response(
        session,
        tenant_id=principal.tenant_id,
        invitation_id=row.id,
        response_status=resulting.value,
        response_channel="speaker_portal",
        recorded_at=utc_now(),
        recorded_by_user_id=principal.user_id,
    )
    if not wrote:
        # Lost a race: a link or Connector answer landed between the read and
        # the guarded write. Re-read once and classify; never write again.
        fresh = _invites.get_for_professional(
            session,
            tenant_id=principal.tenant_id,
            professional_id=bound.professional_id,
            invitation_id=invitation_id,
        )
        if fresh is None or fresh.response_status == "awaiting_response":
            _LOGGER.warning(
                "speaker portal answer matched no row and none was recorded: invitation %s",
                invitation_id,
            )
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="speaker_invitation_response_conflict",
                message="This invitation changed while you answered. Reload it and try again.",
            )
        _decide(fresh, requested)
        return MyInvitationAnswerResult(invitation=invitation_view(fresh), recorded=False)

    session.commit()
    written = _invites.get_for_professional(
        session,
        tenant_id=principal.tenant_id,
        professional_id=bound.professional_id,
        invitation_id=invitation_id,
    )
    if written is None:  # pragma: no cover - the row was just written
        raise _invitation_not_found()
    return MyInvitationAnswerResult(invitation=invitation_view(written), recorded=True)


@router.get(
    "/engagements",
    response_model=MyEngagementList,
    summary="List my confirmed engagements",
    responses=_errors(403, 404, 429),
)
def list_my_engagements(
    principal: CurrentPrincipal,
    session: DbSession,
    when: Annotated[EngagementWhen, Query()] = "upcoming",
) -> MyEngagementList:
    """Own confirmed journeys, cancelled included, split on the event's local date.

    ``as_of`` is today's UTC date; an unknown or missing event date is always
    ``upcoming``.
    """
    charge_quota(session, principal, SPEAKER_SELF_READ_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    today = utc_now().date()
    rows = _pipeline.list_engagements_for_speaker(
        session,
        tenant_id=principal.tenant_id,
        professional_id=bound.professional_id,
        today=today,
        when=when,
        limit=MAX_ROWS + 1,
    )
    return MyEngagementList(
        when=when,
        as_of=today,
        engagements=[engagement_view(row) for row in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
    )
