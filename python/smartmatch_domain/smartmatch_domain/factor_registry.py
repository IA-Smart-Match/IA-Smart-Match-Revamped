"""Canonical, versioned matching factor registry.

Architecture v1.1 §1.2 requires **one** registry before any matching port, and
gate G1 ("factor registry + golden cases approved") blocks R1 until a named
program owner signs off on its contents.

Status: **APPROVED** — gate G1 closed 2026-09-03 (Danny Tran, @dangt).

Legacy evidence (Nebiux-Team-IA-West-SmartMatch@bdce024, verified):

    src/config.py:97       FACTOR_REGISTRY declares 9 factors, weights sum 1.00
    src/matching/engine.py:109  compute_match_score computes only 7 of them
    README.md:229          documents the system as "8-factor matching"

`event_urgency` (0.05) and `coverage_diversity` (0.05) are declared and carry
normalized weight, but no implementation ever writes them into
`weighted_factor_scores`. Because `_normalize_weights` normalizes across all
nine declared keys while the sum is taken over only the seven computed ones,
**every legacy match score is systematically deflated: the maximum attainable
total is 0.90, not 1.00.** That is a correctness defect, not a naming
inconsistency, and it is why porting the legacy scoring path is blocked rather
than merely deferred.

See docs/architecture/review/contract-findings.md (F-001) and
docs/migration/migration-manifest.yaml (MM-002).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "PROHIBITED_INPUTS",
    "PROPOSED_FACTORS",
    "REGISTRY_STATUS",
    "REGISTRY_VERSION",
    "FactorKind",
    "FactorSpec",
    "RegistryNotApprovedError",
    "active_weights",
    "assert_registry_approved",
    "factor_keys",
    "normalize_weights",
    "proposed_weights",
]

REGISTRY_VERSION: Final[str] = "1.1.0-approved-g1"

#: Approved 2026-09-03 by Danny Tran (@dangt) per
#: ``docs/plans/workshops/g1-workshop-output-worksheet.md`` and Dr. Wang program
#: direction (topic_relevance + proximity; 2–3 speaker shortlist; no % display).
REGISTRY_STATUS: Final[str] = "approved"


class FactorKind(StrEnum):
    """How a factor participates in assignment.

    Architecture v1.1 §1.2 splits matching into Stage A (hard eligibility
    filtering) and Stage B (global CP-SAT optimization). A factor is one or the
    other; the same quantity may appear as both only when the contract says so
    explicitly, as the Engagement Load Index does (§1.3: hard cap in Stage A,
    soft penalty in Stage B).
    """

    #: Contributes positively to the Stage B utility function.
    SUITABILITY = "suitability"
    #: Subtracts from the Stage B utility function.
    PENALTY = "penalty"
    #: Removes a (professional, event) pair in Stage A. Never scored.
    ELIGIBILITY = "eligibility"


@dataclass(frozen=True, slots=True)
class FactorSpec:
    """One factor's canonical definition.

    The distinction between :attr:`proposed_weight` and :attr:`active_weight` is
    what prevents the legacy defect. The registry may *propose* a weight for a
    factor that is not built yet — that is what a proposal is for — but only an
    implemented factor contributes an *active* weight, and normalization ranges
    over active weights alone. The legacy conflated the two: it normalized
    across all nine declared weights while summing over the seven it computed,
    silently discarding the difference.

    Attributes:
        key: Stable identifier. Never reused for a different meaning.
        display_label: Coordinator-facing name.
        kind: Stage A eligibility, or Stage B suitability/penalty.
        proposed_weight: The Stage B weight this registry proposes, pending gate
            G1 approval. Zero for eligibility factors, which are not scored.
        implemented: Whether a verified implementation exists in this package.
        rationale: Why the factor exists, in operational terms.
    """

    key: str
    display_label: str
    kind: FactorKind
    proposed_weight: float
    implemented: bool
    rationale: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.proposed_weight <= 1.0:
            raise ValueError(f"{self.key}: proposed_weight must be in [0.0, 1.0]")
        if self.kind is FactorKind.ELIGIBILITY and self.proposed_weight != 0.0:
            raise ValueError(
                f"{self.key}: eligibility factors are Stage A filters and carry no Stage B weight"
            )

    @property
    def is_scoring(self) -> bool:
        """Whether this factor participates in the Stage B utility function."""
        return self.kind is not FactorKind.ELIGIBILITY

    @property
    def active_weight(self) -> float:
        """The weight this factor actually contributes today.

        Zero unless the factor is both a scoring factor and implemented. A
        proposed-but-unbuilt factor contributes nothing, and — critically —
        :func:`normalize_weights` never counts it in the denominator either.
        """
        if not self.is_scoring or not self.implemented:
            return 0.0
        return self.proposed_weight


#: Proposed canonical set. Weights over implemented factors sum to 1.0 — asserted
#: by ``tests/unit/test_factor_registry.py``, so the legacy deflation defect
#: cannot recur unnoticed.
PROPOSED_FACTORS: Final[tuple[FactorSpec, ...]] = (
    FactorSpec(
        key="topic_relevance",
        display_label="Topic Relevance",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.70,
        implemented=False,
        rationale=(
            "Alignment between the professional's expertise and the event_need's "
            "required and preferred topics. Primary scoring factor per G1 "
            "approval (2026-09-03)."
        ),
    ),
    FactorSpec(
        key="travel_burden",
        display_label="Travel Burden (proximity)",
        kind=FactorKind.PENALTY,
        proposed_weight=0.30,
        implemented=False,
        rationale=(
            "Proximity / route-matrix travel time (v1.1 §3.1). Straight-line "
            "interim until D3 provider. Secondary scoring factor per G1 approval."
        ),
    ),
    FactorSpec(
        key="availability",
        display_label="Availability / Blackout",
        kind=FactorKind.ELIGIBILITY,
        proposed_weight=0.0,
        implemented=False,
        rationale=(
            "Applied after shortlist per program direction: match before "
            "availability; coordinator batch-invites and tracks responses."
        ),
    ),
)

#: Inputs the registry schema refuses, enforced by :class:`FactorSpec` review and
#: by ``tests/unit/test_factor_registry.py`` — not by convention (v1.1 §1.3).
PROHIBITED_INPUTS: Final[frozenset[str]] = frozenset(
    {
        "age",
        "disability",
        "health_inference",
        "protected_characteristic",
        "subjective_admin_opinion",
        "unrelated_student_feedback",
        "unverified_external_activity",
        "llm_generated_assumption",
    }
)


class RegistryNotApprovedError(RuntimeError):
    """Raised when scoring is attempted before the G1 gate closes."""


def assert_registry_approved() -> None:
    """Fail closed unless the factor registry has been approved.

    Any code path that produces a user-visible match score must call this first.
    Architecture v1.1 gate G1 blocks R1 on registry approval; failing closed here
    means the gate is enforced by the code rather than by a checklist.

    Raises:
        RegistryNotApprovedError: while ``REGISTRY_STATUS`` is not ``"approved"``.
    """
    if REGISTRY_STATUS != "approved":
        raise RegistryNotApprovedError(
            f"Factor registry {REGISTRY_VERSION} is {REGISTRY_STATUS!r}. "
            "Architecture v1.1 gate G1 blocks match scoring until the program owner "
            "approves the registry contents and the golden case set. "
            "See docs/architecture/review/contract-findings.md (F-001)."
        )


def factor_keys() -> tuple[str, ...]:
    """Return every declared factor key, in registry order."""
    return tuple(spec.key for spec in PROPOSED_FACTORS)


def proposed_weights() -> Mapping[str, float]:
    """Return the weights this registry *proposes*, including unbuilt factors.

    For review and documentation. Never use this to score — proposed weights
    include factors with no implementation, and summing scores against them is
    exactly the legacy defect. Use :func:`normalize_weights` instead.
    """
    return MappingProxyType({spec.key: spec.proposed_weight for spec in PROPOSED_FACTORS})


def active_weights() -> Mapping[str, float]:
    """Return the unnormalized weights that implemented scoring factors carry."""
    return MappingProxyType(
        {spec.key: spec.active_weight for spec in PROPOSED_FACTORS if spec.active_weight > 0.0}
    )


def normalize_weights(weights: Mapping[str, float] | None = None) -> Mapping[str, float]:
    """Normalize Stage B weights across **implemented scoring factors only**.

    This is the corrected form of the legacy ``_normalize_weights``. The legacy
    normalized across all nine declared keys but summed over the seven it
    actually computed, losing the remaining weight mass and capping every score
    at 0.90. Here the denominator and the numerator range over the same set, so
    the returned weights always sum to 1.0 (or are all zero when no implemented
    scoring factor has positive weight).

    Args:
        weights: Optional overrides keyed by factor key. Keys that are unknown,
            unimplemented, or eligibility-only are ignored. Omitted keys fall
            back to the registry default. Negative values are rejected.

    Returns:
        An immutable mapping over implemented scoring factors summing to 1.0,
        or all zeros when the total is zero.

    Raises:
        ValueError: if any supplied weight is negative.
    """
    scoring = {
        spec.key: spec.proposed_weight
        for spec in PROPOSED_FACTORS
        if spec.implemented and spec.is_scoring
    }

    if weights is not None:
        for key, value in weights.items():
            if value < 0.0:
                raise ValueError(f"{key}: weight must not be negative (got {value})")
            if key in scoring:
                scoring[key] = float(value)

    total = sum(scoring.values())
    if total <= 0.0:
        return MappingProxyType(dict.fromkeys(scoring, 0.0))

    return MappingProxyType({key: value / total for key, value in scoring.items()})
