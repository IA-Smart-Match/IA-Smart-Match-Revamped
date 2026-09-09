"""Unit-scoped manual events and external feedback QR redirects.

No crawler, provider, or outbound HTTP client belongs here. Administrators
supply event details and a feedback destination; the public QR route records
a data-minimized open and redirects without fetching the destination.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Header, Path, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.events import normalize_title
from smartmatch_persistence.events import EventRepository
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.exc import IntegrityError

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["events"])
public_router = APIRouter(tags=["events"])

_events = EventRepository()
_READ_ROLES = frozenset({"admin", "coordinator"})
_WRITE_ROLES = frozenset({"admin"})
_CATEGORIES = frozenset(
    {"hackathon", "datathon", "competition", "guest lecturer event", "school event"}
)
EVENT_WRITE_RATE_LIMIT = RateLimit(
    operation="event.write", max_requests=60, window=timedelta(minutes=1)
)
_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EventStatus = Literal["draft", "published", "cancelled"]
TimePrecision = Literal["exact", "date_only", "unresolved"]


class EventWrite(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = None
    time_precision: TimePrecision = "unresolved"
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    on_date: date | None = None
    time_zone: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, ge=0)
    volunteer_openings: int | None = Field(default=None, ge=0)
    volunteer_needs: str | None = Field(default=None, max_length=2000)
    audience: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    speaker_topics: list[str] = Field(default_factory=list, max_length=30)
    region: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()

    @field_validator("category")
    @classmethod
    def category_is_approved(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if normalized not in _CATEGORIES:
            raise ValueError("category is not an approved event category")
        return normalized

    @field_validator("contact_email")
    @classmethod
    def contact_email_is_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized and not _EMAIL.fullmatch(normalized):
            raise ValueError("contact_email must be a valid email address")
        return normalized or None

    @field_validator("speaker_topics")
    @classmethod
    def normalize_speaker_topics(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 100 for value in normalized):
            raise ValueError("speaker topics must be at most 100 characters")
        return normalized

    @field_validator("region")
    @classmethod
    def normalize_region(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def schedule_is_honest(self) -> EventWrite:
        if self.time_zone:
            try:
                ZoneInfo(self.time_zone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("time_zone must be a valid IANA zone name") from exc
        if self.time_precision == "exact":
            if self.starts_at is None or self.starts_at.utcoffset() is None or not self.time_zone:
                raise ValueError("a timed event needs an offset-aware start and named time zone")
            if self.on_date is not None:
                raise ValueError("a timed event cannot also carry an all-day date")
            if self.ends_at is not None and (
                self.ends_at.utcoffset() is None or self.ends_at <= self.starts_at
            ):
                raise ValueError("ends_at must be offset-aware and later than starts_at")
        elif self.time_precision == "date_only":
            if self.on_date is None or not self.time_zone or self.starts_at or self.ends_at:
                raise ValueError("an all-day event needs a date and zone, without clock times")
        elif self.starts_at or self.ends_at or self.on_date:
            raise ValueError("an unresolved schedule cannot carry a date or time")
        if (
            self.capacity is not None
            and self.volunteer_openings is not None
            and self.volunteer_openings > self.capacity
        ):
            raise ValueError("volunteer_openings cannot exceed capacity")
        return self


class EventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = None
    time_precision: TimePrecision | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    on_date: date | None = None
    time_zone: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, ge=0)
    volunteer_openings: int | None = Field(default=None, ge=0)
    volunteer_needs: str | None = Field(default=None, max_length=2000)
    audience: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    speaker_topics: list[str] | None = Field(default=None, max_length=30)
    region: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def optional_title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value.strip() if value is not None else None

    @field_validator("category")
    @classmethod
    def optional_category_is_approved(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if normalized not in _CATEGORIES:
            raise ValueError("category is not an approved event category")
        return normalized

    @field_validator("contact_email")
    @classmethod
    def optional_contact_email_is_valid(cls, value: str | None) -> str | None:
        return EventWrite.contact_email_is_valid(value)

    @field_validator("speaker_topics")
    @classmethod
    def optional_speaker_topics(cls, values: list[str] | None) -> list[str] | None:
        return EventWrite.normalize_speaker_topics(values) if values is not None else None

    @field_validator("region")
    @classmethod
    def optional_region(cls, value: str | None) -> str | None:
        return EventWrite.normalize_region(value)


class EventResponse(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    time_precision: TimePrecision
    starts_at: datetime | None
    ends_at: datetime | None
    on_date: date | None
    time_zone: str | None
    location: str | None
    capacity: int | None
    volunteer_openings: int | None
    volunteer_needs: str | None
    audience: str | None
    contact_name: str | None
    contact_email: str | None
    speaker_topics: list[str]
    region: str | None
    status: EventStatus
    provenance: Literal["observed"] = "observed"
    created_at: datetime
    updated_at: datetime
    version: int
    attendance_closed_at: datetime | None
    cancelled_at: datetime | None


class EventListResponse(BaseModel):
    data: list[EventResponse]
    total: int


class FeedbackQrRequest(BaseModel):
    destination_url: str = Field(min_length=1, max_length=2048)

    @field_validator("destination_url")
    @classmethod
    def safe_external_https_url(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("destination URL contains control characters")
        try:
            parts = urlsplit(value.strip())
        except ValueError as exc:
            raise ValueError("destination URL is invalid") from exc
        host = parts.hostname
        if parts.scheme.lower() != "https" or not host:
            raise ValueError("destination URL must be an absolute HTTPS URL")
        if parts.username is not None or parts.password is not None:
            raise ValueError("destination URL cannot contain credentials")
        lowered = host.casefold().rstrip(".")
        if (
            lowered == "localhost"
            or "." not in lowered
            or not _HOSTNAME.fullmatch(host)
            or any(not label or len(label) > 63 for label in lowered.split("."))
            or _looks_like_ip(host)
        ):
            raise ValueError("destination URL must use a public DNS hostname")
        return value.strip()


class FeedbackQrResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    destination_url: str
    redirect_url: str
    open_count: int
    last_opened_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _authorize(session: Any, principal: Any, unit_id: uuid.UUID, roles: frozenset[str]) -> None:
    if roles not in (_READ_ROLES, _WRITE_ROLES):
        raise RuntimeError("event routes must use a declared event role set")
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit.id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=roles,
        require_membership=True,
    )


def _event_response(row: Any) -> EventResponse:
    payload = dict(row)
    payload["unit_id"] = payload.pop("owning_unit_id")
    return EventResponse.model_validate(payload)


def _qr_response(row: Any, request: Request) -> FeedbackQrResponse:
    payload = dict(row)
    payload["redirect_url"] = str(
        request.url_for("open_feedback_qr", public_token=payload.pop("public_token"))
    )
    return FeedbackQrResponse.model_validate(payload)


def _write_values(body: EventWrite | EventPatch) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    if values.get("title") is not None:
        values["normalized_title"] = normalize_title(values["title"])
    return values


def _not_found() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="event_not_found",
        message="No such event.",
    )


@router.post("/{unit_id}/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    principal: CurrentPrincipal,
    session: DbSession,
    body: EventWrite,
    unit_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> EventResponse:
    charge_quota(session, principal, EVENT_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _WRITE_ROLES)
    payload = body.model_dump(mode="json")
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        row, _replayed = _events.create_draft(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            actor_id=principal.user_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            values=_write_values(body),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="idempotency_conflict",
            message="That request key was already used for different event details.",
        ) from exc
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="duplicate_event",
            message="An event with this title and date already exists for the unit.",
        ) from exc
    return _event_response(row)


@router.get("/{unit_id}/events", response_model=EventListResponse)
def list_events(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_status: Annotated[
        Literal["published", "draft", "all"], Query(alias="status")
    ] = "published",
) -> EventListResponse:
    roles = _READ_ROLES if event_status == "published" else _WRITE_ROLES
    _authorize(session, principal, unit_id, roles)
    rows = _events.list_events(
        session,
        tenant_id=principal.tenant_id,
        unit_id=unit_id,
        event_status=event_status,
    )
    data = [_event_response(row) for row in rows]
    return EventListResponse(data=data, total=len(data))


@router.get("/{unit_id}/events/{event_id}", response_model=EventResponse)
def get_event(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> EventResponse:
    _authorize(session, principal, unit_id, _READ_ROLES)
    row = _events.get_event(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if row is None:
        raise _not_found()
    if row["status"] != "published":
        _authorize(session, principal, unit_id, _WRITE_ROLES)
    return _event_response(row)


@router.patch("/{unit_id}/events/{event_id}", response_model=EventResponse)
def update_event(
    principal: CurrentPrincipal,
    session: DbSession,
    body: EventPatch,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> EventResponse:
    charge_quota(session, principal, EVENT_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _WRITE_ROLES)
    current = _events.get_event(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if current is None:
        raise _not_found()
    if current["status"] == "cancelled":
        raise ApiError(
            status_code=409,
            code="event_cancelled",
            message="A cancelled event cannot be edited.",
        )
    merged = {key: current[key] for key in EventWrite.model_fields}
    merged.update(body.model_dump(exclude_unset=True))
    validated = EventWrite.model_validate(merged)
    try:
        row = _events.update_event(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            event_id=event_id,
            values=_write_values(validated),
        )
        assert row is not None
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="event_conflict",
            message="The event details conflict with an existing event or schedule.",
        ) from exc
    return _event_response(row)


@router.post("/{unit_id}/events/{event_id}/publish", response_model=EventResponse)
def publish_event(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> EventResponse:
    charge_quota(session, principal, EVENT_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _WRITE_ROLES)
    current = _events.get_event(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if current is None:
        raise _not_found()
    if current["status"] == "cancelled":
        raise ApiError(
            status_code=409,
            code="event_cancelled",
            message="A cancelled event cannot be published again.",
        )
    required = (
        "description",
        "category",
        "location",
        "capacity",
        "volunteer_openings",
        "volunteer_needs",
        "audience",
        "contact_name",
        "contact_email",
    )
    missing = [
        key
        for key in required
        if current[key] is None or (isinstance(current[key], str) and not current[key].strip())
    ]
    if current["time_precision"] == "unresolved":
        missing.append("schedule")
    if missing:
        raise ApiError(
            status_code=409,
            code="event_not_publishable",
            message="Complete the required event details before publishing.",
            details={"fields": missing},
        )
    row = _events.update_event(
        session,
        tenant_id=principal.tenant_id,
        unit_id=unit_id,
        event_id=event_id,
        values={"status": "published"},
    )
    assert row is not None
    session.commit()
    return _event_response(row)


@router.get("/{unit_id}/events/{event_id}/feedback-qr", response_model=FeedbackQrResponse)
def get_feedback_qr(
    principal: CurrentPrincipal,
    session: DbSession,
    request: Request,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> FeedbackQrResponse:
    _authorize(session, principal, unit_id, _WRITE_ROLES)
    event = _events.get_event(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if event is None:
        raise _not_found()
    row = _events.get_qr(session, tenant_id=principal.tenant_id, event_id=event_id)
    if row is None:
        raise ApiError(
            status_code=404,
            code="feedback_qr_not_found",
            message="No feedback QR code has been configured for this event.",
        )
    return _qr_response(row, request)


@router.put("/{unit_id}/events/{event_id}/feedback-qr", response_model=FeedbackQrResponse)
def put_feedback_qr(
    principal: CurrentPrincipal,
    session: DbSession,
    request: Request,
    body: FeedbackQrRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> FeedbackQrResponse:
    charge_quota(session, principal, EVENT_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _WRITE_ROLES)
    event = _events.get_event(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if event is None:
        raise _not_found()
    row = _events.upsert_qr(
        session,
        tenant_id=principal.tenant_id,
        unit_id=unit_id,
        event_id=event_id,
        actor_id=principal.user_id,
        destination_url=body.destination_url,
    )
    session.commit()
    return _qr_response(row, request)


@public_router.get("/q/{public_token}", status_code=status.HTTP_302_FOUND)
def open_feedback_qr(
    session: DbSession,
    public_token: Annotated[str, Path()],
) -> RedirectResponse:
    if not 20 <= len(public_token) <= 100:
        raise ApiError(
            status_code=404,
            code="feedback_qr_not_found",
            message="This feedback QR code is not active.",
        )
    destination = _events.record_open(session, public_token=public_token)
    if destination is None:
        raise ApiError(
            status_code=404,
            code="feedback_qr_not_found",
            message="This feedback QR code is not active.",
        )
    session.commit()
    return RedirectResponse(
        destination,
        status_code=status.HTTP_302_FOUND,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
