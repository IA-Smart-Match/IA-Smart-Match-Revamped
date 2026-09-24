"""The signed-in Speaker's own channel consent (B26 T6b-3).

* ``GET  /v1/me/contact-channels``
* ``POST /v1/me/contact-channels/{contact_channel_id}/opt-in``
* ``POST /v1/me/contact-channels/{contact_channel_id}/opt-out``

Mounted only under ``Capability.SPEAKER_PORTAL`` (off in every scope).

## Order in every handler (T6b-2 §2.1)

1. ``charge_quota`` (ADR-0015): an unlinked caller pays too.
2. ``_authorize_speaker_self``, **imported** from ``routers/speaker_self.py``:
   ``404 speaker_profile_not_linked`` when no profile is bound to the login,
   else ``{speaker}`` at the profile's unit (``403``). This module writes no
   subject lookup of its own.
3. The work, in ``smartmatch_api.speaker_channel_consent``, keyed by
   ``bound.professional_id``. The only path parameter is the channel id; a
   channel that is not the bound profile's is ``404``.
4. Writes commit, then read back.

Auth is a bearer session, not a cookie, so there is no CSRF surface.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Any, Final

from fastapi import APIRouter, Path
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api import speaker_channel_consent as consent
from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ErrorEnvelope
from smartmatch_api.routers.speaker_self import _authorize_speaker_self

__all__ = [
    "ME_CONTACT_CHANNELS_READ_RATE_LIMIT",
    "ME_CONTACT_CHANNELS_WRITE_RATE_LIMIT",
    "router",
]

router = APIRouter(prefix="/v1/me", tags=["speaker-portal"])

ME_CONTACT_CHANNELS_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="me.contact_channels.read", max_requests=60, window=timedelta(minutes=1)
)
#: An opt-in or opt-out is a consent decision about a real address; ten a
#: minute is far above what a person clicking needs.
ME_CONTACT_CHANNELS_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="me.contact_channels.write", max_requests=10, window=timedelta(minutes=1)
)


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        403: "Bound, but no active `speaker` membership covers the profile's unit.",
        404: "No Speaker profile is linked to this account, or no such channel of yours.",
        409: "The opt-in cannot be applied; `code` and `details` say why.",
        429: "Quota spent. Charged before anything else.",
    }
    return {code: {"model": ErrorEnvelope, "description": descriptions[code]} for code in codes}


@router.get(
    "/contact-channels",
    response_model=consent.MyContactChannelList,
    summary="List my contact channels and whether messages may reach them",
    responses=_errors(403, 404, 429),
)
def list_my_contact_channels(
    principal: CurrentPrincipal, session: DbSession
) -> consent.MyContactChannelList:
    """Every channel of the bound profile in this tenant, across units (OQ-7)."""
    charge_quota(session, principal, ME_CONTACT_CHANNELS_READ_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    return consent.list_channels(
        session,
        tenant_id=principal.tenant_id,
        professional_id=bound.professional_id,
        account_user_id=principal.user_id,
    )


@router.post(
    "/contact-channels/{contact_channel_id}/opt-in",
    response_model=consent.MyContactChannelResult,
    summary="Opt in to messages at one of my addresses",
    responses=_errors(403, 404, 409, 429),
)
def opt_in_my_contact_channel(
    principal: CurrentPrincipal,
    session: DbSession,
    contact_channel_id: Annotated[uuid.UUID, Path()],
) -> consent.MyContactChannelResult:
    """Lift what the Speaker may lift and make the channel sendable (plan §6).

    Raises:
        ApiError: 404 ``speaker_profile_not_linked`` / ``speaker_contact_channel_not_found``;
            403; 409 ``speaker_contact_channel_address_unverified``,
            ``…_suppression_not_liftable``, ``…_opt_in_unavailable``,
            ``…_transition_conflict``; 429.
    """
    charge_quota(session, principal, ME_CONTACT_CHANNELS_WRITE_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    changed = consent.opt_in(
        session,
        tenant_id=principal.tenant_id,
        bound=bound,
        actor_user_id=principal.user_id,
        contact_channel_id=contact_channel_id,
    )
    return _finish(session, principal, bound.professional_id, contact_channel_id, changed)


@router.post(
    "/contact-channels/{contact_channel_id}/opt-out",
    response_model=consent.MyContactChannelResult,
    summary="Stop messages to one of my addresses",
    responses=_errors(403, 404, 429),
)
def opt_out_my_contact_channel(
    principal: CurrentPrincipal,
    session: DbSession,
    contact_channel_id: Annotated[uuid.UUID, Path()],
) -> consent.MyContactChannelResult:
    """Immediate and prospective (ADR-0014 rule 2): every later send check refuses.

    Raises:
        ApiError: 404 ``speaker_profile_not_linked`` / ``speaker_contact_channel_not_found``;
            403; 429.
    """
    charge_quota(session, principal, ME_CONTACT_CHANNELS_WRITE_RATE_LIMIT)
    bound = _authorize_speaker_self(session, principal)
    changed = consent.opt_out(
        session,
        tenant_id=principal.tenant_id,
        bound=bound,
        actor_user_id=principal.user_id,
        contact_channel_id=contact_channel_id,
    )
    return _finish(session, principal, bound.professional_id, contact_channel_id, changed)


def _finish(
    session: Session,
    principal: CurrentPrincipal,
    professional_id: uuid.UUID,
    contact_channel_id: uuid.UUID,
    changed: bool,
) -> consent.MyContactChannelResult:
    """Commit a write (release the locks either way), then read the channel back."""
    if changed:
        session.commit()
    else:
        session.rollback()
    return consent.MyContactChannelResult(
        channel=consent.read_channel(
            session,
            tenant_id=principal.tenant_id,
            professional_id=professional_id,
            account_user_id=principal.user_id,
            contact_channel_id=contact_channel_id,
        ),
        changed=changed,
    )
