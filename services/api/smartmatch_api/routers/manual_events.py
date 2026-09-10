"""Manually filed events, and each one's external feedback QR redirect.

Ratified by ``docs/decisions/manual-events-and-feedback-qr-2026-09-07.md``.
Administrators create, edit, and publish events for their unit; coordinators
may read the published ones. This authorization is independent of the
crawler — it does not authorize crawler routes, provider calls, scheduled
discovery, or a bypass of the existing crawler security gate.

Every manual event is a row in the canonical ``event`` table
(``routers/events.py`` reads it back), written with
``origin='coordinator_entry'`` through
``smartmatch_persistence.events.EventRepository`` — the same repository and
the same ADR-0010/ADR-0012 machinery every extracted event goes through.
There is **no** ``managed_event`` table: the plan-gate review rejected one as
invisible to main's own catalog reads (PORT_PLAN.md §0.5, finding 2). The
event-only extras ``event`` has no column for live in the side table
``event_manual_detail`` (migration ``0035``), and the feedback QR pair lives
in ``event_feedback_qr`` / ``event_feedback_qr_open``.

No crawler, provider, or outbound HTTP client belongs here
=============================================================
This module renders no destination it stores. The public redirect
(``open_feedback_qr``) records a data-minimised open and issues an HTTP
redirect to the stored URL — it never fetches, inspects, proxies, or submits
it. There is no client here, no OAuth scope, and no environment variable a
later edit could point at a crawler.

Who may call these
=====================
``_WRITE_ROLES`` (``{admin}``) governs every write: create, patch, publish,
and both feedback-QR routes. ``_READ_ROLES`` (``{admin, coordinator}``)
governs reading one published event; a draft is admin-only regardless of
role, because a coordinator has no business seeing a unit's unpublished
draft. Both authorizers load the unit first and authorize against *that
row's* path, so a unit in another tenant is a ``404`` rather than a ``403``
that would confirm the id names something real.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from fastapi import APIRouter, Header, Path, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.events import (
    DateOnlyTime,
    EventTime,
    ExactTime,
    UnresolvedTime,
    normalize_title,
    resolved_date,
)
from smartmatch_persistence import schema
from smartmatch_persistence.events import (
    ORIGIN_COORDINATOR_ENTRY,
    EventNotPublishableError,
    EventRepository,
)
from smartmatch_persistence.manual_events import ManualEventDetailRepository
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["events"])
public_router = APIRouter(tags=["events"])

_events = EventRepository()
_details = ManualEventDetailRepository()

#: Every write in this module: create, patch, publish, and both feedback-QR
#: routes. Deliberately admin-only — a coordinator reads published events
#: (``_READ_ROLES``) but does not file them on this surface.
_WRITE_ROLES: Final[frozenset[str]] = frozenset({"admin"})

#: Reading one published event. A draft is gated to ``_WRITE_ROLES``
#: regardless — see ``get_event`` below.
_READ_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"hackathon", "datathon", "competition", "guest lecturer event", "school event"}
)

EVENT_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="manual_event.write", max_requests=60, window=timedelta(minutes=1)
)

_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TimePrecision = Literal["exact", "date_only", "unresolved"]
EventStatus = Literal["draft", "published"]

#: The event-only fields this router persists in ``event_manual_detail``,
#: keyed to that table's column names.
_DETAIL_FIELDS: Final[tuple[str, ...]] = (
    "category",
    "location",
    "capacity",
    "volunteer_openings",
    "volunteer_needs",
    "audience",
    "contact_name",
    "contact_email",
    "speaker_topics",
    "region",
)

#: The core ``event`` fields a patch may touch, beyond the detail extras.
_CORE_FIELDS: Final[tuple[str, ...]] = (
    "title",
    "description",
    "time_precision",
    "starts_at",
    "ends_at",
    "on_date",
    "time_zone",
)

#: The fields the decision doc and the reference implementation require before
#: an event may publish, beyond ADR-0010's resolved-schedule requirement
#: (enforced by ``EventRepository.publish`` / ``ck_event_publishable``).
_REQUIRED_DETAIL_TO_PUBLISH: Final[tuple[str, ...]] = (
    "category",
    "location",
    "capacity",
    "volunteer_openings",
    "volunteer_needs",
    "audience",
    "contact_name",
    "contact_email",
)


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


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

    def event_time(self) -> EventTime:
        """This body's schedule as an ``EventTime`` for ``EventRepository``."""
        if self.time_precision == "exact":
            assert self.starts_at is not None and self.time_zone is not None
            return ExactTime(starts_at=self.starts_at, time_zone=self.time_zone, ends_at=self.ends_at)
        if self.time_precision == "date_only":
            assert self.on_date is not None and self.time_zone is not None
            return DateOnlyTime(on_date=self.on_date, time_zone=self.time_zone)
        return UnresolvedTime()


class EventPatch(BaseModel):
    version: int = Field(ge=1)
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
        return EventWrite.category_is_approved(value)

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


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize(
    session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID, roles: frozenset[str]
) -> None:
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
    )


def _authorize_write(session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID) -> None:
    _authorize(session, principal, unit_id, _WRITE_ROLES)


def _authorize_read(session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID) -> None:
    _authorize(session, principal, unit_id, _READ_ROLES)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _not_found() -> ApiError:
    return ApiError(status_code=status.HTTP_404_NOT_FOUND, code="event_not_found", message="No such event.")


def _load_event_and_detail(
    session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, event_id: uuid.UUID
) -> tuple[Any, Any] | None:
    """The ``event`` row and its ``event_manual_detail`` row, or ``None``.

    Scoped to ``origin = 'coordinator_entry'`` — this router only ever reads
    back the events it (or another manual-entry caller) wrote; an extracted
    event has no detail row to join and is not this router's concern.
    """
    event_row = session.execute(
        sa.select(schema.event).where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            schema.event.c.id == event_id,
            schema.event.c.origin == ORIGIN_COORDINATOR_ENTRY,
        )
    ).mappings().one_or_none()
    if event_row is None:
        return None
    detail_row = _details.get_detail(session, tenant_id=tenant_id, event_id=event_id)
    if detail_row is None:
        return None
    return event_row, detail_row


def _response(event_row: Any, detail_row: Any) -> EventResponse:
    status_value: EventStatus = (
        "published" if event_row["publication_status"] == "published" else "draft"
    )
    return EventResponse(
        id=event_row["id"],
        unit_id=event_row["host_org_unit_id"],
        title=event_row["title"],
        description=event_row["description"],
        category=detail_row["category"],
        time_precision=event_row["time_precision"],
        starts_at=event_row["starts_at"],
        ends_at=event_row["ends_at"],
        on_date=event_row["on_date"],
        time_zone=event_row["time_zone"],
        location=detail_row["location"],
        capacity=detail_row["capacity"],
        volunteer_openings=detail_row["volunteer_openings"],
        volunteer_needs=detail_row["volunteer_needs"],
        audience=detail_row["audience"],
        contact_name=detail_row["contact_name"],
        contact_email=detail_row["contact_email"],
        speaker_topics=list(detail_row["speaker_topics"] or []),
        region=detail_row["region"],
        status=status_value,
        created_at=event_row["created_at"],
        updated_at=detail_row["updated_at"],
        version=detail_row["version"],
    )


def _qr_response(row: Any, request: Request) -> FeedbackQrResponse:
    payload = dict(row)
    payload["redirect_url"] = str(
        request.url_for("open_feedback_qr", public_token=payload.pop("public_token"))
    )
    return FeedbackQrResponse.model_validate(payload)


def _fingerprint(body: BaseModel) -> str:
    payload = body.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _detail_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: values[key] for key in _DETAIL_FIELDS if key in values}


def _temporal_columns_for(event_time: EventTime) -> dict[str, Any]:
    if isinstance(event_time, ExactTime):
        return {
            "starts_at": event_time.starts_at,
            "ends_at": event_time.ends_at,
            "on_date": None,
            "time_zone": event_time.time_zone,
            "time_precision": "exact",
        }
    if isinstance(event_time, DateOnlyTime):
        return {
            "starts_at": None,
            "ends_at": None,
            "on_date": event_time.on_date,
            "time_zone": event_time.time_zone,
            "time_precision": "date_only",
        }
    return {
        "starts_at": None,
        "ends_at": None,
        "on_date": None,
        "time_zone": None,
        "time_precision": "unresolved",
    }


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("/{unit_id}/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    principal: CurrentPrincipal,
    session: DbSession,
    body: EventWrite,
    unit_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> EventResponse:
    charge_quota(session, principal, EVENT_WRITE_RATE_LIMIT)
    _authorize_write(session, principal, unit_id)

    fingerprint = _fingerprint(body)
    existing_detail = _details.find_by_idempotency_key(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, idempotency_key=idempotency_key
    )
    if existing_detail is not None:
        if existing_detail["request_fingerprint"] != fingerprint:
            raise ApiError(
                status_code=409,
                code="idempotency_conflict",
                message="That request key was already used for different event details.",
            )
        loaded = _load_event_and_detail(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=existing_detail["event_id"]
        )
        assert loaded is not None
        return _response(*loaded)

    try:
        outcome = _events.upsert_returning_outcome(
            session,
            tenant_id=principal.tenant_id,
            host_org_unit_id=unit_id,
            title=body.title,
            event_time=body.event_time(),
            origin=ORIGIN_COORDINATOR_ENTRY,
            description=body.description,
            filed_by_user_id=principal.user_id,
        )
        detail_row = _details.create_detail(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            event_id=outcome.event_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            values=_detail_values(body.model_dump()),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="duplicate_event",
            message="An event with this title and date already exists for the unit.",
        ) from exc

    event_row = session.execute(
        sa.select(schema.event).where(
            schema.event.c.tenant_id == principal.tenant_id, schema.event.c.id == outcome.event_id
        )
    ).mappings().one()
    return _response(event_row, detail_row)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("/{unit_id}/events/{event_id}", response_model=EventResponse)
def get_event(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> EventResponse:
    _authorize_read(session, principal, unit_id)
    loaded = _load_event_and_detail(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if loaded is None:
        raise _not_found()
    event_row, detail_row = loaded
    if event_row["publication_status"] != "published":
        _authorize_write(session, principal, unit_id)
    return _response(event_row, detail_row)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@router.patch("/{unit_id}/events/{event_id}", response_model=EventResponse)
def update_event(
    principal: CurrentPrincipal,
    session: DbSession,
    body: EventPatch,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> EventResponse:
    charge_quota(session, principal, EVENT_WRITE_RATE_LIMIT)
    _authorize_write(session, principal, unit_id)
    loaded = _load_event_and_detail(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if loaded is None:
        raise _not_found()
    event_row, detail_row = loaded

    # Merge the patch over the stored row (core + detail together) and
    # re-validate the whole thing through EventWrite, so a patch that only
    # touches, say, `capacity` still gets checked against the schedule and
    # capacity/volunteer_openings invariants that were already true of the
    # stored row.
    merged: dict[str, Any] = {key: event_row[key] for key in _CORE_FIELDS}
    merged.update({key: detail_row[key] for key in _DETAIL_FIELDS})
    patch_values = body.model_dump(exclude={"version"}, exclude_unset=True)
    merged.update(patch_values)
    validated = EventWrite.model_validate(merged)

    try:
        detail_row = _details.update_detail(
            session,
            tenant_id=principal.tenant_id,
            event_id=event_id,
            expected_version=body.version,
            values=_detail_values(validated.model_dump()),
        )
        if detail_row is None:
            raise ApiError(
                status_code=409, code="stale_event", message="This event changed. Refresh and try again."
            )
        session.execute(
            sa.update(schema.event)
            .where(schema.event.c.tenant_id == principal.tenant_id, schema.event.c.id == event_id)
            .values(
                title=validated.title,
                normalized_title=normalize_title(validated.title),
                description=validated.description,
                **_temporal_columns_for(validated.event_time()),
                resolved_date=resolved_date(validated.event_time()),
                updated_at=sa.func.now(),
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="event_conflict",
            message="The event details conflict with an existing event or schedule.",
        ) from exc

    event_row = session.execute(
        sa.select(schema.event).where(
            schema.event.c.tenant_id == principal.tenant_id, schema.event.c.id == event_id
        )
    ).mappings().one()
    return _response(event_row, detail_row)


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


@router.post("/{unit_id}/events/{event_id}/publish", response_model=EventResponse)
def publish_event(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> EventResponse:
    charge_quota(session, principal, EVENT_WRITE_RATE_LIMIT)
    _authorize_write(session, principal, unit_id)
    loaded = _load_event_and_detail(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if loaded is None:
        raise _not_found()
    event_row, detail_row = loaded

    missing = [
        field
        for field in _REQUIRED_DETAIL_TO_PUBLISH
        if detail_row[field] is None
        or (isinstance(detail_row[field], str) and not detail_row[field].strip())
    ]
    if event_row["description"] is None or not event_row["description"].strip():
        missing.append("description")
    if event_row["time_precision"] == "unresolved":
        missing.append("schedule")
    if missing:
        raise ApiError(
            status_code=409,
            code="event_not_publishable",
            message="Complete the required event details before publishing.",
            details={"fields": missing},
        )

    try:
        _events.publish(session, tenant_id=principal.tenant_id, event_id=event_id)
    except EventNotPublishableError as exc:
        raise ApiError(status_code=409, code="event_not_publishable", message=str(exc)) from exc
    session.commit()

    loaded = _load_event_and_detail(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    assert loaded is not None
    return _response(*loaded)


# ---------------------------------------------------------------------------
# Feedback QR
# ---------------------------------------------------------------------------


@router.get("/{unit_id}/events/{event_id}/feedback-qr", response_model=FeedbackQrResponse)
def get_feedback_qr(
    principal: CurrentPrincipal,
    session: DbSession,
    request: Request,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> FeedbackQrResponse:
    _authorize_write(session, principal, unit_id)
    loaded = _load_event_and_detail(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if loaded is None:
        raise _not_found()
    row = _details.get_qr(session, tenant_id=principal.tenant_id, event_id=event_id)
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
    _authorize_write(session, principal, unit_id)
    loaded = _load_event_and_detail(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )
    if loaded is None:
        raise _not_found()
    row = _details.upsert_qr(
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
    destination = _details.record_open(session, public_token=public_token)
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
