"""Stage A `availability` eligibility filter.

Architecture v1.1 §1.2 splits matching into Stage A (hard eligibility
filtering over a fixed shortlist) and Stage B (global CP-SAT optimization
over scored candidates). ``availability`` is registered in
:mod:`smartmatch_domain.factor_registry` as a Stage A eligibility factor with
``FactorKind.ELIGIBILITY`` and **weight 0** — per ratified program direction
(gate G1, 2026-09-03) it is applied **after** the Stage B shortlist has
already been computed: match first, then availability; the coordinator
batch-invites the eligible remainder and tracks responses. Availability never
enters the Stage B score, is never normalized alongside ``topic_relevance``
or ``travel_burden``, and never becomes a scoring factor. This module filters
a fixed, already-ordered shortlist; it does not rank or score anything.

ADR-0011 governs :class:`EligibilityOutcome` the same way it governs every
factor's ``None`` branch: an *unknown* availability record is neither an
exclusion nor a pass. Silently excluding a subject with no availability
record on file discards a candidate on missing evidence — the "N/A becomes a
rejection" mirror image of "N/A becomes zero." Silently including one asserts
a fact ("this subject is available") the data does not carry. Both are
wrong, so an unknown record resolves to a third, explicit outcome,
``UNDETERMINED``, distinct from both ``ELIGIBLE`` and ``EXCLUDED``, that a
coordinator-facing explanation can surface honestly instead of masking as a
pass or a rejection.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "AVAILABILITY_STAGE_B_WEIGHT",
    "AvailabilityEvidence",
    "AvailabilityState",
    "EligibilityDecision",
    "EligibilityOutcome",
    "apply_availability_filter",
]

#: Fixed by the ratified factor registry (gate G1, 2026-09-03) — availability
#: is a Stage A eligibility filter, never a Stage B scoring input, and this
#: value is not a tunable. See ``smartmatch_domain.factor_registry`` for the
#: canonical ``FactorSpec`` this mirrors.
AVAILABILITY_STAGE_B_WEIGHT: Final[float] = 0.0


class AvailabilityState(StrEnum):
    """The recorded availability fact for one subject, or its absence."""

    AVAILABLE = "available"
    BLACKED_OUT = "blacked_out"
    UNKNOWN = "unknown"


class EligibilityOutcome(StrEnum):
    """The Stage A gate's verdict for one (professional, event) pair.

    ``UNDETERMINED`` is deliberately distinct from both ``ELIGIBLE`` and
    ``EXCLUDED`` — see the module docstring's ADR-0011 discussion.
    """

    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class AvailabilityEvidence:
    """One subject's recorded availability state.

    Attributes:
        subject_id: Stable identifier for the professional this evidence
            describes. Non-empty.
        state: The recorded availability state.
    """

    subject_id: str
    state: AvailabilityState

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """The Stage A gate's verdict for one subject, with its provenance.

    Attributes:
        subject_id: Stable identifier for the professional this decision
            describes. Non-empty.
        outcome: The gate's verdict.
        reason: Human-readable provenance for the verdict. Non-empty.
    """

    subject_id: str
    outcome: EligibilityOutcome
    reason: str

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        if not self.reason.strip():
            raise ValueError("reason: must not be empty or blank")


def apply_availability_filter(
    shortlist: tuple[str, ...],
    evidence: Mapping[str, AvailabilityEvidence],
) -> tuple[EligibilityDecision, ...]:
    """Apply the Stage A availability gate to an already-ordered shortlist.

    Runs strictly after the Stage B shortlist has been computed and ranked
    (including its ``subject_id`` tie-break); this function never reorders,
    scores, or reshapes that ordering, it only annotates each entry with an
    eligibility verdict.

    Args:
        shortlist: Subject ids in Stage B shortlist order. Each id must be
            unique.
        evidence: Availability evidence keyed by ``subject_id``. Entries for
            subjects outside ``shortlist`` are ignored — Stage A runs only
            over the shortlist. A missing entry for a shortlisted subject is
            treated as an absent record, not as an error.

    Returns:
        One :class:`EligibilityDecision` per shortlist entry, in the exact
        order of ``shortlist``.

    Raises:
        ValueError: if ``shortlist`` contains a duplicate ``subject_id``.
    """
    seen: set[str] = set()
    for subject_id in shortlist:
        if subject_id in seen:
            raise ValueError(f"subject_id: duplicate entry in shortlist: {subject_id!r}")
        seen.add(subject_id)

    decisions: list[EligibilityDecision] = []
    for subject_id in shortlist:
        record = evidence.get(subject_id)
        if record is None:
            decisions.append(
                EligibilityDecision(
                    subject_id,
                    EligibilityOutcome.UNDETERMINED,
                    reason="no availability record for this subject",
                )
            )
        elif record.state is AvailabilityState.AVAILABLE:
            decisions.append(
                EligibilityDecision(
                    subject_id,
                    EligibilityOutcome.ELIGIBLE,
                    reason="availability recorded as available",
                )
            )
        elif record.state is AvailabilityState.BLACKED_OUT:
            decisions.append(
                EligibilityDecision(
                    subject_id,
                    EligibilityOutcome.EXCLUDED,
                    reason="availability recorded as blacked out",
                )
            )
        else:
            decisions.append(
                EligibilityDecision(
                    subject_id,
                    EligibilityOutcome.UNDETERMINED,
                    reason="availability record is unknown",
                )
            )

    return tuple(decisions)
