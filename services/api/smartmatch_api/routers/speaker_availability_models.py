"""Request/response models and helpers for speaker availability (B26 T3).

No router here. Shared by the Connector's
``/v1/units/{unit_id}/speaker-contacts/{professional_id}/availability`` routes
and, later, the speaker's own ``/v1/me/availability`` (T6b-2) — the precedent
is ``manual_events_models.py``.

## The write goes through :func:`write_statement` only

It validates with the T1 domain rules and only then calls the T2 repository's
``upsert``, which never validates. A route that upserted directly could store a
statement the matcher would later trust; routing every write through one
function makes that impossible to do by accident.

## Numbers

Capacity is a JSON number in both directions. The request accepts a strict
float or int (a bool or string is ``invalid_request``) and converts it with
``Decimal(str(value))`` so ``24.05`` stays ``24.05`` and fails the one-decimal
rule rather than being rounded into passing. The response is
``float(stored)``.

## Errors

Every message is fixed per code and never echoes the submitted value
(``errors.py``'s rule). The 409 carries no ``details``: the client re-reads.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal

from fastapi import status
from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt
from smartmatch_domain.speaker_availability import (
    MAX_WINDOWS,
    AvailabilityErrorCode,
    AvailabilityStatement,
    AvailabilityStatementInvalid,
    UnavailableWindow,
    validate_availability_statement,
)
from smartmatch_persistence.speaker_availability import (
    AvailabilitySource,
    SpeakerAvailabilityRepository,
    StaleSpeakerAvailabilityError,
    StoredSpeakerAvailability,
)
from sqlalchemy.orm import Session

from smartmatch_api.errors import ApiError

__all__ = [
    "AvailabilityWindowInput",
    "AvailabilityWindowView",
    "SpeakerAvailabilityResponse",
    "SpeakerAvailabilityUpdateRequest",
    "availability_error",
    "availability_response",
    "stale_error",
    "statement_from_request",
    "write_statement",
]

STALE_CODE: Final[str] = "speaker_availability_stale"

_MESSAGES: Final[dict[AvailabilityErrorCode, str]] = {
    AvailabilityErrorCode.CAPACITY_INVALID: (
        "Declared capacity must be more than 0 and at most 720 hours, with at most one decimal."
    ),
    AvailabilityErrorCode.PAUSE_INVALID: (
        "The pause must end between today and twelve months from today."
    ),
    AvailabilityErrorCode.TOO_MANY_WINDOWS: "Too many unavailable windows.",
    AvailabilityErrorCode.WINDOW_INVALID: (
        "An unavailable window is out of order, too long, too far ahead, or repeated."
    ),
}


class AvailabilityWindowInput(BaseModel):
    """One inclusive date range the speaker cannot speak on."""

    model_config = ConfigDict(extra="forbid")

    starts_on: date
    ends_on: date


class SpeakerAvailabilityUpdateRequest(BaseModel):
    """Full replace. Every key is required; ``null`` clears. No subject field (MM-A01)."""

    model_config = ConfigDict(extra="forbid")

    #: The version read, or ``null`` for "I read stated: false" (T2 C1). Strict:
    #: lax int would turn ``true`` into version 1 and ``"3"`` into 3.
    expected_version: StrictInt | None
    invitations_paused_until: date | None
    declared_capacity_hours_per_90_days: StrictFloat | StrictInt | None
    #: No ``max_length``: the domain reports ``too_many_windows``.
    unavailable: list[AvailabilityWindowInput]


class AvailabilityWindowView(BaseModel):
    """A stored window and which surface first wrote it."""

    starts_on: date
    ends_on: date
    source: Literal["speaker", "connector"]


class SpeakerAvailabilityResponse(BaseModel):
    """A speaker's stated availability; ``stated: false`` means no row ("Not stated")."""

    professional_id: uuid.UUID
    stated: bool
    #: ``null`` exactly when ``stated`` is false.
    version: int | None
    #: The stored value, even if already past.
    invitations_paused_until: date | None
    declared_capacity_hours_per_90_days: float | None
    unavailable: list[AvailabilityWindowView]
    updated_source: Literal["speaker", "connector"] | None
    updated_at: datetime | None


def statement_from_request(
    body: SpeakerAvailabilityUpdateRequest,
    stored: StoredSpeakerAvailability | None,
    today: date,
) -> AvailabilityStatement:
    """The domain statement a request asks for.

    Windows keep request order, so a validation ``index`` is the request's.
    An already-expired pause re-sent unchanged (equal to the stored one) is
    dropped to ``None`` so a form that echoes it back can still save; any other
    past pause is kept and fails validation.
    """
    capacity = body.declared_capacity_hours_per_90_days
    paused_until = body.invitations_paused_until
    if (
        paused_until is not None
        and paused_until < today
        and stored is not None
        and paused_until == stored.statement.invitations_paused_until
    ):
        paused_until = None
    return AvailabilityStatement(
        invitations_paused_until=paused_until,
        declared_capacity_hours_per_90_days=None if capacity is None else Decimal(str(capacity)),
        unavailable=tuple(UnavailableWindow(w.starts_on, w.ends_on) for w in body.unavailable),
    )


def availability_error(exc: AvailabilityStatementInvalid) -> ApiError:
    """The 422 for a statement that broke a domain limit."""
    details: dict[str, object] = {"field": exc.field}
    if exc.code is AvailabilityErrorCode.TOO_MANY_WINDOWS:
        details["limit"] = MAX_WINDOWS
    if exc.index is not None:
        details["index"] = exc.index
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=exc.code.value,
        message=_MESSAGES[exc.code],
        details=details,
    )


def stale_error() -> ApiError:
    """The 409 when the caller's ``expected_version`` is not what is stored."""
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=STALE_CODE,
        message="This availability changed since it was read. Re-read it and try again.",
    )


def availability_response(
    professional_id: uuid.UUID, stored: StoredSpeakerAvailability | None
) -> SpeakerAvailabilityResponse:
    """The response body; no row is ``stated: false`` with everything else empty."""
    if stored is None:
        return SpeakerAvailabilityResponse(
            professional_id=professional_id,
            stated=False,
            version=None,
            invitations_paused_until=None,
            declared_capacity_hours_per_90_days=None,
            unavailable=[],
            updated_source=None,
            updated_at=None,
        )
    capacity = stored.statement.declared_capacity_hours_per_90_days
    return SpeakerAvailabilityResponse(
        professional_id=professional_id,
        stated=True,
        version=stored.version,
        invitations_paused_until=stored.statement.invitations_paused_until,
        declared_capacity_hours_per_90_days=None if capacity is None else float(capacity),
        unavailable=[
            AvailabilityWindowView(
                starts_on=window.starts_on,
                ends_on=window.ends_on,
                source=window.created_source.value,
            )
            for window in stored.windows
        ],
        updated_source=stored.updated_source.value,
        updated_at=stored.updated_at,
    )


def write_statement(
    session: Session,
    repository: SpeakerAvailabilityRepository,
    *,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    statement: AvailabilityStatement,
    today: date,
    source: AvailabilitySource,
    actor_user_id: uuid.UUID,
    expected_version: int | None,
    now: datetime,
) -> StoredSpeakerAvailability:
    """Validate ``statement``, then upsert it. The only write path for availability.

    Does not commit; the caller owns the transaction.

    Raises:
        ApiError: 422 with the domain code when the statement breaks a limit
            (nothing is written); 409 ``speaker_availability_stale`` when the
            stored version is not ``expected_version``.
    """
    try:
        validate_availability_statement(statement, today)
    except AvailabilityStatementInvalid as exc:
        raise availability_error(exc) from exc
    try:
        return repository.upsert(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            statement=statement,
            source=source,
            actor_user_id=actor_user_id,
            expected_version=expected_version,
            now=now,
        )
    except StaleSpeakerAvailabilityError as exc:
        raise stale_error() from exc
