"""Engagement Load Index (ELI).

Architecture v1.1 §1.3. Replaces the legacy "volunteer fatigue" factor
(Nebiux-Team-IA-West-SmartMatch@bdce024:src/matching/factors.py:549), which
implied a health assessment SmartMatch has no evidence to make and surfaced
coordinator-facing labels like "Rest Recommended". Migration manifest MM-003
records the behavior retained and rejected.

Retained from the legacy: the *shape* of the computation — recent assignment
pressure, travel burden, and event cadence combined into a bounded score.

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

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Final

__all__ = [
    "ELI_FORMULA_VERSION",
    "LoadModifier",
    "EngagementRecord",
    "LoadInputs",
    "EliSnapshot",
    "CapDecision",
    "compute_eli",
    "evaluate_cap",
    "load_penalty",
]

#: Versioned with the factor registry. Any change to the arithmetic below is a
#: new version, because stored ``eli_snapshot`` rows record which formula
#: produced them (v1.1 §2.2 ELI_SNAPSHOT.formula_version).
ELI_FORMULA_VERSION: Final[str] = "1.1.0"

#: Half-life for recency decay, in days. Proposed default — open decision 2 in
#: architecture v1.1 Appendix C assigns final parameters to the program owner.
_DECAY_HALF_LIFE_DAYS: Final[float] = 45.0

#: Rolling window over which engagements are counted at all.
_ROLLING_WINDOW_DAYS: Final[int] = 90


class LoadModifier(str, Enum):
    """Visible modifiers permitted by v1.1 §1.3.

    Each is a factual, checkable property of the schedule. They are surfaced to
    the coordinator *and* to the professional, who can correct the underlying
    availability data (v1.1 §5.1).
    """

    BACK_TO_BACK = "back_to_back"
    CONSECUTIVE_WEEKENDS = "consecutive_weekends"
    SHORT_RECOVERY = "short_recovery"
    LONG_TRAVEL = "long_travel"
    SHORT_NOTICE = "short_notice"
    AT_DECLARED_FREQUENCY = "at_declared_max_frequency"
    MANUAL_BLACKOUT = "manual_blackout"


@dataclass(frozen=True, slots=True)
class EngagementRecord:
    """One completed or committed engagement.

    Attributes:
        occurred_on: Date of the engagement.
        event_hours: Hours spent at the event itself. Must be non-negative.
        travel_hours: Hours spent travelling. Must be non-negative. Sourced from
            the route matrix; when travel time is unavailable this is 0.0 and
            the caller records the estimate as unavailable rather than guessing
            (v1.1 §3.6 R4).
    """

    occurred_on: date
    event_hours: float
    travel_hours: float = 0.0

    def __post_init__(self) -> None:
        if self.event_hours < 0.0:
            raise ValueError("event_hours must be non-negative")
        if self.travel_hours < 0.0:
            raise ValueError("travel_hours must be non-negative")

    @property
    def total_hours(self) -> float:
        """Combined event and travel hours."""
        return self.event_hours + self.travel_hours


@dataclass(frozen=True, slots=True)
class LoadInputs:
    """Everything ELI is permitted to see.

    Deliberately a closed structure: a field that is not here cannot reach the
    computation, which is how the prohibited-input rule is enforced structurally
    rather than by review.

    Attributes:
        as_of: The date the snapshot is computed for.
        engagements: Engagements within the rolling window. Entries outside the
            window are ignored rather than rejected.
        declared_capacity_hours: The professional's own declared rolling
            capacity. Must be positive — an undeclared capacity is not zero
            capacity, and the caller must not substitute one.
        modifiers: Visible modifiers currently in effect.
    """

    as_of: date
    engagements: tuple[EngagementRecord, ...] = ()
    declared_capacity_hours: float = 40.0
    modifiers: frozenset[LoadModifier] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.declared_capacity_hours <= 0.0:
            raise ValueError(
                "declared_capacity_hours must be positive; an undeclared capacity is "
                "not the same as zero capacity and must be resolved by the caller"
            )


@dataclass(frozen=True, slots=True)
class EliSnapshot:
    """A computed ELI result.

    Attributes:
        score: 0–100. Higher means more loaded.
        decayed_hours: Recency-weighted hours behind the score.
        raw_hours: Undecayed hours in the window, for explanation.
        formula_version: The formula that produced this snapshot.
        modifiers: Modifiers that were in effect.
        utilization: ``decayed_hours / declared_capacity_hours``, uncapped, so
            the explanation can show how far over capacity a professional is.
    """

    score: float
    decayed_hours: float
    raw_hours: float
    formula_version: str
    modifiers: frozenset[LoadModifier]
    utilization: float


class CapDecision(str, Enum):
    """Stage A outcome for the declared-capacity hard constraint."""

    #: Under the declared cap. Proceeds to Stage B with a soft penalty.
    WITHIN_CAP = "within_cap"
    #: Over the declared cap. Ineligible without an authorized override.
    OVER_CAP = "over_cap"
    #: A manual blackout is in effect. Ineligible; not overridable by load math.
    BLACKED_OUT = "blacked_out"


def _decay_weight(days_ago: int) -> float:
    """Exponential recency weight with a 45-day half-life.

    An engagement today counts fully; one 45 days ago counts half. Continuous
    rather than stepped, so a professional's score does not jump when an
    engagement crosses an arbitrary bucket edge.
    """
    return math.pow(0.5, days_ago / _DECAY_HALF_LIFE_DAYS)


def compute_eli(inputs: LoadInputs) -> EliSnapshot:
    """Compute the Engagement Load Index.

    The score is the recency-decayed hours expressed as a percentage of declared
    capacity, clamped to 0–100, then nudged upward by any visible modifiers in
    effect. Modifiers add a bounded amount so they can express real schedule
    pressure without dominating the measured hours.

    Args:
        inputs: The permitted operational facts.

    Returns:
        A snapshot carrying the score, its inputs, and the formula version.
    """
    window_start = inputs.as_of - timedelta(days=_ROLLING_WINDOW_DAYS)

    raw_hours = 0.0
    decayed_hours = 0.0
    for record in inputs.engagements:
        if record.occurred_on < window_start or record.occurred_on > inputs.as_of:
            continue
        days_ago = (inputs.as_of - record.occurred_on).days
        raw_hours += record.total_hours
        decayed_hours += record.total_hours * _decay_weight(days_ago)

    utilization = decayed_hours / inputs.declared_capacity_hours
    base_score = min(100.0, utilization * 100.0)

    # Each modifier adds 4 points, capped at 20 total, so modifiers can never
    # by themselves push an otherwise-idle professional to a high load score.
    modifier_points = min(20.0, 4.0 * len(inputs.modifiers))
    score = min(100.0, base_score + modifier_points)

    return EliSnapshot(
        score=round(score, 2),
        decayed_hours=round(decayed_hours, 2),
        raw_hours=round(raw_hours, 2),
        formula_version=ELI_FORMULA_VERSION,
        modifiers=frozenset(inputs.modifiers),
        utilization=round(utilization, 4),
    )


def evaluate_cap(snapshot: EliSnapshot) -> CapDecision:
    """Apply the Stage A hard constraint.

    A manual blackout is checked first and is not a load judgement — it is the
    professional's or coordinator's explicit instruction, and no amount of spare
    capacity overrides it.

    Args:
        snapshot: A computed ELI snapshot.

    Returns:
        The Stage A decision. ``OVER_CAP`` makes the pair ineligible unless an
        authorized override with reason, author, timestamp, and expiration
        exists (v1.1 §1.3).
    """
    if LoadModifier.MANUAL_BLACKOUT in snapshot.modifiers:
        return CapDecision.BLACKED_OUT
    if snapshot.utilization > 1.0:
        return CapDecision.OVER_CAP
    return CapDecision.WITHIN_CAP


def load_penalty(snapshot: EliSnapshot) -> float:
    """Return the Stage B soft penalty in ``[0.0, 1.0]``.

    Quadratic in the score, so light load is close to free and the penalty rises
    steeply as a professional approaches their declared cap. That keeps the
    optimizer from spreading work so thinly that it ignores suitability, while
    still strongly discouraging assignments near the cap.

    This is the *soft* application only. The hard cap is
    :func:`evaluate_cap`, and the two are reported separately in the match
    explanation.
    """
    normalized = min(1.0, max(0.0, snapshot.score / 100.0))
    return round(normalized**2, 4)
