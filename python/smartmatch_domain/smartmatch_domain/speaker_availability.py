"""Speaker self-service availability: the verdict and the statement limits (B26 T1).

A speaker states their own availability as one *statement*: an optional
invitation pause, an optional declared capacity, and up to
:data:`MAX_WINDOWS` inclusive date windows during which they cannot speak.
This module turns a statement plus one event's local date span into an
:class:`AvailabilityAssessment` — a state and the reason for it — which
:meth:`AvailabilityAssessment.to_evidence` hands to the unchanged Stage A gate,
:func:`smartmatch_domain.eligibility.apply_availability_filter`.

Pure domain: no I/O, no clock. The caller chooses ``as_of`` and ``today``.

Verdict order (first match wins):

0. ``event_span`` must be ``None`` or a ``(first, last)`` pair of ``date``
   with ``first <= last``; otherwise ``ValueError``.
1. No statement -> ``UNKNOWN / NOT_STATED``.
2. Event has no local date -> ``UNKNOWN / EVENT_UNRESOLVED`` (wins over an
   active pause).
3. ``invitations_paused_until >= as_of`` -> ``BLACKED_OUT / PAUSED``.
4. A window overlaps the event span (inclusive) -> ``BLACKED_OUT / WINDOW``.
5. Otherwise -> ``AVAILABLE / CLEAR``.

Declared capacity never affects the verdict; it is only validated here.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final, TypeAlias
from zoneinfo import ZoneInfo

from smartmatch_domain.eligibility import (
    AvailabilityEvidence,
    AvailabilityReason,
    AvailabilityState,
)
from smartmatch_domain.events import DateOnlyTime, EventTime, ExactTime, resolved_date

__all__ = [
    "CAPACITY_MAX",
    "CAPACITY_MIN_EXCLUSIVE",
    "MAX_WINDOWS",
    "PAUSE_HORIZON_MONTHS",
    "WINDOW_HORIZON_MONTHS",
    "WINDOW_MAX_SPAN_DAYS",
    "AvailabilityAssessment",
    "AvailabilityErrorCode",
    "AvailabilityReason",
    "AvailabilityStatement",
    "AvailabilityStatementInvalid",
    "EventDateSpan",
    "UnavailableWindow",
    "availability_state_for_event",
    "event_local_span",
    "validate_availability_statement",
]

MAX_WINDOWS: Final[int] = 20
WINDOW_MAX_SPAN_DAYS: Final[int] = 366
WINDOW_HORIZON_MONTHS: Final[int] = 18
PAUSE_HORIZON_MONTHS: Final[int] = 12
CAPACITY_MIN_EXCLUSIVE: Final[Decimal] = Decimal("0")
CAPACITY_MAX: Final[Decimal] = Decimal("720")

_CAPACITY_QUANTUM: Final[Decimal] = Decimal("0.1")

#: ``(first, last)`` local dates of an event, both inclusive.
EventDateSpan: TypeAlias = tuple[date, date]


@dataclass(frozen=True, slots=True)
class UnavailableWindow:
    """An inclusive range of dates the speaker cannot speak on."""

    starts_on: date
    ends_on: date

    def __post_init__(self) -> None:
        for name, value in (("starts_on", self.starts_on), ("ends_on", self.ends_on)):
            if isinstance(value, datetime) or not isinstance(value, date):
                raise TypeError(f"{name}: must be a date, got {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class AvailabilityStatement:
    """One speaker's stated availability: a ``speaker_availability`` row and its windows.

    Attributes:
        invitations_paused_until: Last date (inclusive) on which invitations
            are paused, or ``None``.
        declared_capacity_hours_per_90_days: Stated capacity, or ``None`` when
            not stated. Must be a ``Decimal``; range and precision are checked
            by :func:`validate_availability_statement`.
        unavailable: The speaker's unavailable windows.
    """

    invitations_paused_until: date | None
    declared_capacity_hours_per_90_days: Decimal | None
    unavailable: tuple[UnavailableWindow, ...] = ()

    def __post_init__(self) -> None:
        capacity = self.declared_capacity_hours_per_90_days
        if capacity is not None and not isinstance(capacity, Decimal):
            raise TypeError(
                "declared_capacity_hours_per_90_days: must be a Decimal or None, "
                f"got {type(capacity).__name__}"
            )
        if not isinstance(self.unavailable, tuple):
            raise TypeError(f"unavailable: must be a tuple, got {type(self.unavailable).__name__}")


@dataclass(frozen=True, slots=True)
class AvailabilityAssessment:
    """The verdict for one (statement, event) pair."""

    state: AvailabilityState
    reason: AvailabilityReason

    def to_evidence(self, subject_id: str) -> AvailabilityEvidence:
        """Wrap this verdict as Stage A evidence for ``subject_id``."""
        return AvailabilityEvidence(subject_id, self.state, self.reason)


class AvailabilityErrorCode(StrEnum):
    """Validation failure codes; values are the API error codes (all 422)."""

    CAPACITY_INVALID = "speaker_availability_capacity_invalid"
    PAUSE_INVALID = "speaker_availability_pause_invalid"
    TOO_MANY_WINDOWS = "speaker_availability_too_many_windows"
    WINDOW_INVALID = "speaker_availability_window_invalid"


class AvailabilityStatementInvalid(ValueError):
    """A statement broke one of the limits.

    Attributes:
        code: Which rule failed.
        field: The statement field at fault.
        index: For a window failure, the offending window's index; else ``None``.
    """

    def __init__(self, code: AvailabilityErrorCode, field: str, index: int | None = None) -> None:
        self.code = code
        self.field = field
        self.index = index
        where = f"{field}[{index}]" if index is not None else field
        super().__init__(f"{code.value}: {where}")


def _add_months(start: date, months: int) -> date:
    """``start`` plus ``months`` calendar months, clamping the day to month end."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def event_local_span(event_time: EventTime) -> EventDateSpan | None:
    """The event's ``(first, last)`` local dates in its own zone, or ``None`` if unresolved.

    An ``ExactTime`` end is exclusive: an event ending at local midnight does
    not reach the next day.
    """
    if isinstance(event_time, DateOnlyTime):
        return (event_time.on_date, event_time.on_date)
    if isinstance(event_time, ExactTime):
        first = resolved_date(event_time)
        if first is None:  # pragma: no cover - ExactTime always resolves
            raise RuntimeError("resolved_date returned None for an ExactTime")
        if event_time.ends_at is None:
            return (first, first)
        last_instant = event_time.ends_at - timedelta(microseconds=1)
        last = last_instant.astimezone(ZoneInfo(event_time.time_zone)).date()
        return (first, last)
    return None


def _check_span(event_span: object) -> None:
    if event_span is None:
        return
    if not isinstance(event_span, tuple) or len(event_span) != 2:
        raise ValueError("event_span: must be None or a (first, last) pair of dates")
    first, last = event_span
    for value in (first, last):
        if isinstance(value, datetime) or not isinstance(value, date):
            raise ValueError("event_span: both ends must be dates, not datetimes")
    if first > last:
        raise ValueError("event_span: first must not be after last")


def availability_state_for_event(
    statement: AvailabilityStatement | None,
    event_span: EventDateSpan | None,
    as_of: date,
) -> AvailabilityAssessment:
    """The availability verdict for one speaker and one event (see module docstring).

    Raises:
        ValueError: if ``event_span`` is malformed or inverted.
    """
    _check_span(event_span)
    if statement is None:
        return AvailabilityAssessment(AvailabilityState.UNKNOWN, AvailabilityReason.NOT_STATED)
    if event_span is None:
        return AvailabilityAssessment(
            AvailabilityState.UNKNOWN, AvailabilityReason.EVENT_UNRESOLVED
        )
    paused_until = statement.invitations_paused_until
    if paused_until is not None and paused_until >= as_of:
        return AvailabilityAssessment(AvailabilityState.BLACKED_OUT, AvailabilityReason.PAUSED)
    first, last = event_span
    if any(w.starts_on <= last and w.ends_on >= first for w in statement.unavailable):
        return AvailabilityAssessment(AvailabilityState.BLACKED_OUT, AvailabilityReason.WINDOW)
    return AvailabilityAssessment(AvailabilityState.AVAILABLE, AvailabilityReason.CLEAR)


def _capacity_ok(capacity: Decimal) -> bool:
    # is_finite() first: no comparison may touch a NaN (sNaN raises on compare).
    if not capacity.is_finite():
        return False
    if not CAPACITY_MIN_EXCLUSIVE < capacity <= CAPACITY_MAX:
        return False
    return capacity == capacity.quantize(_CAPACITY_QUANTUM)


def _window_ok(window: UnavailableWindow, horizon: date) -> bool:
    if window.ends_on < window.starts_on:
        return False
    if (window.ends_on - window.starts_on).days > WINDOW_MAX_SPAN_DAYS:
        return False
    return window.ends_on <= horizon


def validate_availability_statement(statement: AvailabilityStatement, today: date) -> None:
    """Check ``statement`` against the limits; the first failure raises.

    Order: capacity, pause, window count, then each window in order
    (order, span, horizon, duplicate — a duplicate reports the later index).
    Past windows are allowed.

    Raises:
        AvailabilityStatementInvalid: on the first broken rule.
    """
    capacity = statement.declared_capacity_hours_per_90_days
    if capacity is not None and not _capacity_ok(capacity):
        raise AvailabilityStatementInvalid(
            AvailabilityErrorCode.CAPACITY_INVALID, "declared_capacity_hours_per_90_days"
        )

    paused_until = statement.invitations_paused_until
    if paused_until is not None and not (
        today <= paused_until <= _add_months(today, PAUSE_HORIZON_MONTHS)
    ):
        raise AvailabilityStatementInvalid(
            AvailabilityErrorCode.PAUSE_INVALID, "invitations_paused_until"
        )

    if len(statement.unavailable) > MAX_WINDOWS:
        raise AvailabilityStatementInvalid(AvailabilityErrorCode.TOO_MANY_WINDOWS, "unavailable")

    horizon = _add_months(today, WINDOW_HORIZON_MONTHS)
    seen: set[UnavailableWindow] = set()
    for index, window in enumerate(statement.unavailable):
        if not _window_ok(window, horizon) or window in seen:
            raise AvailabilityStatementInvalid(
                AvailabilityErrorCode.WINDOW_INVALID, "unavailable", index
            )
        seen.add(window)
