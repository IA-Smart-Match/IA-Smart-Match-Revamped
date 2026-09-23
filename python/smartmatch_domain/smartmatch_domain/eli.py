"""Engagement Load Index (ELI).

Architecture v1.1 §1.3. Replaces the legacy "volunteer fatigue" factor
(Nebiux-Team-IA-West-SmartMatch@bdce024:src/matching/factors.py:549), which
implied a health assessment SmartMatch has no evidence to make and surfaced
coordinator-facing labels like "Rest Recommended". Migration manifest MM-003
records the behavior retained and rejected.

Retained from the legacy: the *shape* of the computation — recent assignment
pressure and travel burden combined into a bounded score.

This sentence previously also named "event cadence". It was not true, and the
port review recorded it as finding F-4: **there is no event-cadence input.** ELI
is computed from a professional's own workload facts and is never given the
event under consideration, so it has no way to express that event's cadence.
The modifiers that read as cadence-flavoured are caller-supplied booleans, not a
computed cadence. Corrected here as well as in the manifest, because a docstring
claiming an input the module does not have is the same defect wherever it is
written.

Rejected: the health framing and its labels; the implicit inference from a
pipeline "stage_order" column to "days since last assignment", which invented a
number the data never contained; and the single blended score with no separable
hard cap.

ELI is computed **only** from operational workload facts. The prohibited-input
list in :data:`~smartmatch_domain.factor_registry.PROHIBITED_INPUTS` is enforced
by the registry schema and by ``tests/unit/test_eli.py``, not by convention.

The index is applied twice, and both applications are separately visible in the
match explanation (v1.1 §1.3):

* **Stage A** — over the declared cap is a hard constraint. The pair is
  ineligible without an authorized, expiring override.
* **Stage B** — under the cap, load applies a progressive soft penalty that
  reduces assignment utility.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Context, Decimal, Inexact, InvalidOperation, localcontext
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from smartmatch_domain.events import EventTime, ExactTime, resolved_date

__all__ = [
    "COMPLETED_WINDOW_DAYS",
    "CONFIRMED_WINDOW_DAYS",
    "ELI_FORMULA_VERSION",
    "Q7_LOAD_BAND_TABLE",
    "Engagement",
    "LoadAssessment",
    "LoadBand",
    "LoadBandTable",
    "LoadInputs",
    "LoadReason",
    "compute_eli",
]

#: Versioned with the factor registry. Any change to the arithmetic below is a
#: new version, because a stored load assessment records which formula
#: produced it.
ELI_FORMULA_VERSION: Final[str] = "2.0.0"

#: Completed window: event local date in ``[as_of - 45, as_of)``, days -45 .. -1.
COMPLETED_WINDOW_DAYS: Final[int] = 45
#: Confirmed window: event local date in ``[as_of, as_of + 45)``, days 0 .. +44.
CONFIRMED_WINDOW_DAYS: Final[int] = 45
# 45 + 45 = 90 days, the period declared capacity is stated over (R2).

_US_PER_HOUR: Final[int] = 3_600_000_000
_ONE_MICROSECOND: Final[timedelta] = timedelta(microseconds=1)

#: Context for the explanation-only quotients (hour totals, utilization). Fixed
#: rather than the caller's thread context, so the same inputs always give the
#: same stored numbers. No band decision reads these values.
_QUOTIENT_CONTEXT: Final[Context] = Context(prec=28)

#: Precision for the band comparisons. They multiply short Decimals by integers,
#: so they are always exact at this precision; ``Inexact`` is trapped so that any
#: rounding raises instead of silently moving a boundary.
_EXACT_PRECISION: Final[int] = 60


class LoadBand(StrEnum):
    """Q7 load band. ``FULL`` removes the pair before the solve (T8c)."""

    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    FULL = "full"
    UNKNOWN = "unknown"


class LoadReason(StrEnum):
    """Why the band is what it is."""

    #: Capacity stated and every counted engagement has hours.
    MEASURED = "measured"
    #: No declared capacity, so there is no bound to measure against (Q6).
    CAPACITY_NOT_STATED = "capacity_not_stated"
    #: At least one counted engagement has no hours or no resolved date.
    HOURS_UNKNOWN = "hours_unknown"
    #: Known hours alone exceed ``full_above``: a certain lower bound (ADR-0011).
    FULL_BY_KNOWN_HOURS = "full_by_known_hours"


#: The bands a table carries a multiplier for. ``FULL`` has none: a Full pair
#: is removed, not down-weighted.
_MULTIPLIER_BANDS: Final[frozenset[LoadBand]] = frozenset(
    {LoadBand.LIGHT, LoadBand.MODERATE, LoadBand.HEAVY, LoadBand.UNKNOWN}
)


def _require_finite_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class LoadBandTable:
    """Cut points and multipliers for the Q7 bands.

    The edge semantics are code, not table data: utilization ``>=
    moderate_from`` is at least Moderate, ``>= heavy_from`` is at least Heavy,
    and ``> full_above`` is Full. A table moves the cut points; it cannot move
    which side of an edge a value falls on.

    Ownership (approver, approval status) is not here. T8c wraps a table in a
    registry-side type that carries it, so the registry never edits this type.

    Attributes:
        moderate_from: Utilization at or above this is at least Moderate.
        heavy_from: Utilization at or above this is at least Heavy.
        full_above: Utilization strictly above this is Full.
        multipliers: One multiplier in ``(0, 1]`` for each of Light, Moderate,
            Heavy and Unknown; no Full key. Stored read-only. Excluded from
            ``hash()`` because a ``MappingProxyType`` is unhashable; it still
            takes part in ``==``.
    """

    moderate_from: Decimal
    heavy_from: Decimal
    full_above: Decimal
    multipliers: Mapping[LoadBand, Decimal] = field(hash=False)

    def __post_init__(self) -> None:
        moderate = _require_finite_decimal(self.moderate_from, "moderate_from")
        heavy = _require_finite_decimal(self.heavy_from, "heavy_from")
        full = _require_finite_decimal(self.full_above, "full_above")
        if not Decimal(0) < moderate < heavy <= full:
            raise ValueError(
                "band cut points must satisfy 0 < moderate_from < heavy_from <= full_above; "
                f"got {moderate}, {heavy}, {full}"
            )
        if not isinstance(self.multipliers, Mapping):
            raise TypeError("multipliers must be a mapping of LoadBand to Decimal")
        keys = frozenset(self.multipliers)
        if keys != _MULTIPLIER_BANDS:
            raise ValueError(
                "multipliers must have exactly the keys light, moderate, heavy and "
                f"unknown; got {sorted(str(k) for k in keys)}"
            )
        for band, multiplier in self.multipliers.items():
            value = _require_finite_decimal(multiplier, f"multipliers[{band}]")
            if not Decimal(0) < value <= Decimal(1):
                raise ValueError(f"multipliers[{band}] must be in (0, 1], got {value}")
        object.__setattr__(self, "multipliers", MappingProxyType(dict(self.multipliers)))


#: Q7 table (owner-approved, parent plan header Q7).
Q7_LOAD_BAND_TABLE: Final[LoadBandTable] = LoadBandTable(
    moderate_from=Decimal("0.50"),
    heavy_from=Decimal("0.80"),
    full_above=Decimal("1.00"),
    multipliers={
        LoadBand.LIGHT: Decimal("1.00"),
        LoadBand.MODERATE: Decimal("0.90"),
        LoadBand.HEAVY: Decimal("0.70"),
        LoadBand.UNKNOWN: Decimal("1.00"),
    },
)


@dataclass(frozen=True, slots=True)
class Engagement:
    """One booking of the professional, as ELI is allowed to see it.

    Attributes:
        ref: Opaque pipeline-record id, so the explanation can name which
            engagement lacks hours.
        event_date: The event's first local date; ``None`` when the event's
            date is unresolved.
        duration: Event hours as an exact ``timedelta``; ``None`` when unknown.
            Never 0 (ADR-0011): unknown is not zero.
        confirmed: The booking was confirmed.
        attended: Attendance was recorded. Implies ``confirmed``.
        cancelled: The booking was cancelled. Implies ``confirmed``. A plain
            input; the caller derives it from the database.
    """

    ref: str
    event_date: date | None
    duration: timedelta | None
    confirmed: bool
    attended: bool
    cancelled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise ValueError("ref must be a non-blank string")
        if self.duration is not None:
            if not isinstance(self.duration, timedelta):
                raise TypeError("duration must be a timedelta or None")
            if self.duration <= timedelta(0):
                raise ValueError("duration must be positive; unknown hours are None, never 0")
        if self.attended and not self.confirmed:
            raise ValueError("an attended engagement must be confirmed")
        if self.cancelled and not self.confirmed:
            raise ValueError("a cancelled engagement must be confirmed")

    @classmethod
    def from_event_time(
        cls,
        ref: str,
        event_time: EventTime,
        *,
        confirmed: bool,
        attended: bool,
        cancelled: bool,
    ) -> Engagement:
        """Build an engagement from an event's ``EventTime``.

        The date is ``resolved_date(event_time)``: the start's local date in the
        event's zone (the first date of a multi-day event), ``on_date`` for a
        date-only event, ``None`` when unresolved. Hours are ``ends_at -
        starts_at`` for an exact time with a stated end, otherwise unknown.
        """
        duration: timedelta | None = None
        if isinstance(event_time, ExactTime) and event_time.ends_at is not None:
            duration = event_time.ends_at - event_time.starts_at
        return cls(
            ref=ref,
            event_date=resolved_date(event_time),
            duration=duration,
            confirmed=confirmed,
            attended=attended,
            cancelled=cancelled,
        )


@dataclass(frozen=True, slots=True)
class LoadInputs:
    """Everything ELI is permitted to see.

    Deliberately a closed structure: a field that is not here cannot reach the
    computation, which is how the prohibited-input rule is enforced structurally
    rather than by review.

    Attributes:
        as_of: The date the assessment is for (the caller passes the UTC date
            of run creation).
        engagements: The professional's engagements. Any date may be passed;
            the window rules decide what counts.
        declared_capacity_hours: The professional's declared capacity per 90
            days, or ``None`` when not stated. Required, with no default: an
            unstated capacity is Unknown, never an assumed number (Q6).
    """

    as_of: date
    engagements: tuple[Engagement, ...]
    declared_capacity_hours: Decimal | None

    def __post_init__(self) -> None:
        capacity = self.declared_capacity_hours
        if capacity is not None:
            _require_finite_decimal(capacity, "declared_capacity_hours")
            if capacity <= 0:
                raise ValueError(
                    "declared_capacity_hours must be positive; an unstated capacity is "
                    "None, not zero"
                )
        engagements = tuple(self.engagements)
        refs = [e.ref for e in engagements]
        if len(set(refs)) != len(refs):
            duplicates = sorted({r for r in refs if refs.count(r) > 1})
            raise ValueError(f"engagement refs must be unique; duplicated: {duplicates}")
        object.__setattr__(self, "engagements", engagements)


@dataclass(frozen=True, slots=True)
class LoadAssessment:
    """A computed load band and the facts behind it.

    ``utilization`` and the hour totals are for the explanation only; the band
    was decided on exact integer-microsecond comparisons, never on these
    quotients.

    Attributes:
        band: The Q7 band.
        reason: Why the band is what it is.
        measurable: ``reason`` is ``MEASURED``.
        completed_hours: Known hours of attended engagements in
            ``[as_of - 45, as_of)``.
        confirmed_hours: Known hours of confirmed, not-cancelled engagements
            in ``[as_of, as_of + 44]``, attended or not.
        capacity_hours: The declared capacity, or ``None``.
        utilization: ``(completed + confirmed) / capacity``; a lower bound when
            not measurable; ``None`` without capacity.
        unknown_hours_refs: Sorted refs of counted engagements without hours or
            without a resolved date. Filled even when capacity is ``None``.
        formula_version: The formula that produced this assessment.
    """

    band: LoadBand
    reason: LoadReason
    measurable: bool
    completed_hours: Decimal
    confirmed_hours: Decimal
    capacity_hours: Decimal | None
    utilization: Decimal | None
    unknown_hours_refs: tuple[str, ...]
    formula_version: str


def _micros(duration: timedelta) -> int:
    return duration // _ONE_MICROSECOND


def _hours(us: int) -> Decimal:
    return _QUOTIENT_CONTEXT.divide(Decimal(us), Decimal(_US_PER_HOUR))


def _tally(inputs: LoadInputs) -> tuple[int, int, tuple[str, ...]]:
    """Sum known completed and confirmed microseconds; collect unknown refs."""
    completed_us = 0
    confirmed_us = 0
    unknown: list[str] = []
    for engagement in inputs.engagements:
        if not engagement.confirmed or engagement.cancelled:
            continue
        if engagement.event_date is None:
            unknown.append(engagement.ref)
            continue
        offset = (engagement.event_date - inputs.as_of).days
        is_confirmed = 0 <= offset < CONFIRMED_WINDOW_DAYS
        is_completed = engagement.attended and -COMPLETED_WINDOW_DAYS <= offset <= -1
        if not (is_confirmed or is_completed):
            continue
        if engagement.duration is None:
            unknown.append(engagement.ref)
        elif is_confirmed:
            confirmed_us += _micros(engagement.duration)
        else:
            completed_us += _micros(engagement.duration)
    return completed_us, confirmed_us, tuple(sorted(unknown))


def _classify(
    known_us: int, capacity: Decimal, has_unknown: bool, table: LoadBandTable
) -> tuple[LoadBand, LoadReason]:
    """Apply parent §5.2 / plan §4 on exact integer-microsecond comparisons."""
    with localcontext() as ctx:
        ctx.prec = _EXACT_PRECISION
        ctx.traps[Inexact] = True
        ctx.traps[InvalidOperation] = True
        load = Decimal(known_us)
        cap_us = capacity * _US_PER_HOUR
        if load > table.full_above * cap_us:
            reason = LoadReason.FULL_BY_KNOWN_HOURS if has_unknown else LoadReason.MEASURED
            return LoadBand.FULL, reason
        if has_unknown:
            return LoadBand.UNKNOWN, LoadReason.HOURS_UNKNOWN
        if load >= table.heavy_from * cap_us:
            return LoadBand.HEAVY, LoadReason.MEASURED
        if load >= table.moderate_from * cap_us:
            return LoadBand.MODERATE, LoadReason.MEASURED
        return LoadBand.LIGHT, LoadReason.MEASURED


def compute_eli(inputs: LoadInputs, table: LoadBandTable = Q7_LOAD_BAND_TABLE) -> LoadAssessment:
    """Compute the load band for one professional.

    Args:
        inputs: The permitted operational facts.
        table: Band cut points and multipliers; the registry passes its own.

    Returns:
        The band, its reason, the known hour totals and the refs that lack
        hours.
    """
    completed_us, confirmed_us, unknown_refs = _tally(inputs)
    known_us = completed_us + confirmed_us
    capacity = inputs.declared_capacity_hours

    if capacity is None:
        band, reason, utilization = LoadBand.UNKNOWN, LoadReason.CAPACITY_NOT_STATED, None
    else:
        band, reason = _classify(known_us, capacity, bool(unknown_refs), table)
        utilization = _QUOTIENT_CONTEXT.divide(
            Decimal(known_us), _QUOTIENT_CONTEXT.multiply(capacity, Decimal(_US_PER_HOUR))
        )

    return LoadAssessment(
        band=band,
        reason=reason,
        measurable=reason is LoadReason.MEASURED,
        completed_hours=_hours(completed_us),
        confirmed_hours=_hours(confirmed_us),
        capacity_hours=capacity,
        utilization=utilization,
        unknown_hours_refs=unknown_refs,
        formula_version=ELI_FORMULA_VERSION,
    )
