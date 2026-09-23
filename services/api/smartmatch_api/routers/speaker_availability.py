"""A Connector's read and full-replace write of a roster contact's availability (B26 T3).

* ``GET   /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability``
* ``PATCH /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability``

The statement is the speaker's own (T1 domain, T2 storage); a Speaker Connector
may read it and correct it on the speaker's behalf, and every accepted write
is recorded with ``updated_source = 'connector'``.

## Order in each handler

1. Quota first (ADR-0015): a refused or not-found request still pays.
2. ``_authorize_speaker_contacts`` — the §13 roster's own authorizer and role
   set, imported, so a widening applies to the roster and this route together.
3. The profile must be on *this* unit's roster; otherwise ``404
   speaker_contact_not_found``, identical for unknown and other-unit ids. This
   runs before any availability row is read or written.
4. PATCH only: a stale ``expected_version`` is ``409`` before domain
   validation — re-reading fixes both, and the expired-pause drop rule needs
   the current row.
5. PATCH only: :func:`write_statement` validates, then upserts; the router
   never calls the repository's ``upsert`` itself.

"Today" is the UTC date of :func:`utc_now` (plan C1).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Path
from smartmatch_persistence.cba_contacts import SpeakerContactRepository
from smartmatch_persistence.speaker_availability import (
    AvailabilitySource,
    SpeakerAvailabilityRepository,
    StoredSpeakerAvailability,
)
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.routers.cba_contacts import (
    SPEAKER_CONTACT_READ_RATE_LIMIT,
    SPEAKER_CONTACT_WRITE_RATE_LIMIT,
    _authorize_speaker_contacts,
    _not_found,
)
from smartmatch_api.routers.speaker_availability_models import (
    SpeakerAvailabilityResponse,
    SpeakerAvailabilityUpdateRequest,
    availability_response,
    stale_error,
    statement_from_request,
    write_statement,
)
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["speaker-contacts"])

_roster: Final[SpeakerContactRepository] = SpeakerContactRepository()
_availability: Final[SpeakerAvailabilityRepository] = SpeakerAvailabilityRepository()


def _load(
    session: Session,
    principal: CurrentPrincipal,
    *,
    owning_unit_id: uuid.UUID,
    professional_id: uuid.UUID,
) -> StoredSpeakerAvailability | None:
    """The stored statement, after proving the profile is on this unit's roster."""
    contact = _roster.get(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
    )
    if contact is None:
        raise _not_found()
    return _availability.get(
        session, tenant_id=principal.tenant_id, professional_id=professional_id
    )


@router.get(
    "/{unit_id}/speaker-contacts/{professional_id}/availability",
    response_model=SpeakerAvailabilityResponse,
    summary="Read a roster contact's stated availability",
)
def get_speaker_contact_availability(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> SpeakerAvailabilityResponse:
    """The statement, or ``stated: false`` when the speaker has said nothing.

    Raises:
        ApiError: 404 ``unit_not_found`` / ``speaker_contact_not_found``; 403.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_READ_RATE_LIMIT)
    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    stored = _load(
        session, principal, owning_unit_id=owning_unit_id, professional_id=professional_id
    )
    return availability_response(professional_id, stored)


@router.patch(
    "/{unit_id}/speaker-contacts/{professional_id}/availability",
    response_model=SpeakerAvailabilityResponse,
    summary="Replace a roster contact's stated availability",
)
def update_speaker_contact_availability(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
    body: SpeakerAvailabilityUpdateRequest,
) -> SpeakerAvailabilityResponse:
    """Full replace: omitted windows are deleted, ``null`` clears pause and capacity.

    ``expected_version`` is always checked; ``null`` means "I read no row".

    Raises:
        ApiError: 404 ``unit_not_found`` / ``speaker_contact_not_found``; 403;
            409 ``speaker_availability_stale``; 422 with a
            ``speaker_availability_*`` code.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_WRITE_RATE_LIMIT)
    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    stored = _load(
        session, principal, owning_unit_id=owning_unit_id, professional_id=professional_id
    )
    if body.expected_version != (stored.version if stored is not None else None):
        raise stale_error()

    now = utc_now()
    today = now.date()
    result = write_statement(
        session,
        _availability,
        tenant_id=principal.tenant_id,
        professional_id=professional_id,
        statement=statement_from_request(body, stored, today),
        today=today,
        source=AvailabilitySource.CONNECTOR,
        actor_user_id=principal.user_id,
        expected_version=body.expected_version,
        now=now,
    )
    session.commit()
    return availability_response(professional_id, result)
