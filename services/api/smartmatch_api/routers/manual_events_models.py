"""Request/response models for manual events and the feedback QR redirect.

Split out of ``routers/manual_events.py`` to keep that module under this
repository's 800-line ceiling. Behaviour is unchanged — every validator here
is exactly what the router used inline before the split.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import date, datetime
from typing import Final, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from smartmatch_domain.events import DateOnlyTime, EventTime, ExactTime, UnresolvedTime

__all__ = [
    "EventPatch",
    "EventResponse",
    "EventStatus",
    "EventWrite",
    "FeedbackQrRequest",
    "FeedbackQrResponse",
    "TimePrecision",
]

_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"hackathon", "datathon", "competition", "guest lecturer event", "school event"}
)

_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TimePrecision = Literal["exact", "date_only", "unresolved"]
EventStatus = Literal["draft", "published"]


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


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
            return ExactTime(
                starts_at=self.starts_at, time_zone=self.time_zone, ends_at=self.ends_at
            )
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
