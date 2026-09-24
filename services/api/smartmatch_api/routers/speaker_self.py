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

import uuid
from datetime import date, datetime, timedelta
from typing import Final, Literal, cast

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence.cba_invitations import SpeakerInvitationRow
from smartmatch_persistence.pipeline import SpeakerEngagementRow
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.speaker_portal import BoundSpeakerProfile, SpeakerPortalRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal
from smartmatch_api.errors import ApiError
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

_portal: Final[SpeakerPortalRepository] = SpeakerPortalRepository()

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
