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
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt
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
    "EngagementWithoutEndTimeView",
    "SpeakerAvailabilityResponse",
    "SpeakerAvailabilityUpdateRequest",
    "SpeakerLoadView",
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


class EngagementWithoutEndTimeView(BaseModel):
    """One counted engagement whose hours are unknown (T8b R4), labelled for this caller (T8d)."""

    engagement_id: uuid.UUID | None = Field(
        description=(
            "The engagement's record id. On the Connector route it is null unless "
            "the Connector's unit owns the record (always null for other_unit): no "
            "other unit's record id reaches a Speaker Connector."
        )
    )
    shown: Literal["event", "other_unit", "event_missing"] = Field(
        description=(
            "event: title and date are shown. other_unit: the Connector route, and "
            "another unit hosts the event. event_missing: no event record."
        )
    )
    event_title: str | None = Field(description="Set exactly when shown is event.")
    local_date: date | None = Field(
        description="The event's local date when shown is event and it is resolved; else null."
    )
    time_precision: Literal["exact", "date_only", "unresolved"] | None = Field(
        description="Null unless shown is event."
    )
    editable_here: bool = Field(
        description=(
            "Connector route only: this unit hosts the event and entered it, so its "
            "end time can be added on the Events page. Always false for the Speaker."
        )
    )


class SpeakerLoadView(BaseModel):
    """The Speaker's current load band (B26 T8d).

    A band word's inputs only: no hours, no ratio, no capacity echo (OQ-CBA-005;
    owner ruling R-A: load numbers never reach the API wire).
    Computed at request time with the code a 3.x run uses.
    """

    band: Literal["light", "moderate", "heavy", "full", "unknown"]
    reason: Literal["measured", "capacity_not_stated", "hours_unknown", "full_by_known_hours"]
    as_of: date = Field(description="The UTC date the band was measured on.")
    used_in_matching: bool = Field(
        description=(
            "Whether the current matching registry applies engagement load. False "
            "while registry 3.0.0 is only proposed: the band is shown, not used."
        )
    )
    engagements_without_end_time: list[EngagementWithoutEndTimeView] = Field(
        description="Counted engagements whose hours are unknown, at most 20, earliest first."
    )
    engagements_without_end_time_truncated: bool


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
    #: The current load band (B26 T8d); always present, a band word's inputs only.
    load: SpeakerLoadView


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
    professional_id: uuid.UUID,
    stored: StoredSpeakerAvailability | None,
    *,
    load: SpeakerLoadView,
) -> SpeakerAvailabilityResponse:
    """The response body; no row is ``stated: false`` with everything else empty.

    ``load`` is a required keyword (B26 T8d), so no call site can forget it.
    """
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
            load=load,
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
        load=load,
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
