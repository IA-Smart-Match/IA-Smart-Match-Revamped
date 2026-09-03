"""Stage B scoring entry point — the registry join.

Architecture v1.1 §1.2 Stage B: a candidate's suitability is a weighted
composite of the registry's implemented Stage B scoring factors
(``topic_relevance`` and ``travel_burden``; ``availability`` is a Stage A
eligibility filter and never enters this composite — see
:mod:`smartmatch_domain.eligibility`). The weights are **normalized on
apply** (F-25;
``docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md``
§5) — computed at scoring time by
:func:`smartmatch_domain.factor_registry.normalize_weights`, never
hand-tuned as a literal in this module. See also ADR-0011.

Every scoring path here calls
:func:`~smartmatch_domain.factor_registry.assert_registry_approved` and
:func:`~smartmatch_domain.factor_registry.assert_scoring_ready` first,
before touching any evidence — the guard is enforced at this join, not left
to each factor module, because :func:`~smartmatch_domain.factors.
topic_relevance.score_topic_relevance` and
:func:`~smartmatch_domain.factors.travel_burden.score_travel_burden` are
themselves publicly exported and reachable without any guard.

ADR-0011 governs what an unknown factor does to the composite: it makes the
composite unknown too. An unknown factor is never dropped from
``factor_scores``, never substituted with ``0.0``, and the remaining weights
are never re-spread over the known subset — re-spreading would let a
candidate with no evidence outrank one with real evidence, which is the
ADR-0011 defect in aggregate form. Presentation of partial evidence is
M9/M10's problem, not this module's.

This module never characterizes the legacy scoring engine and never asserts
a legacy score value anywhere, including the legacy 43% tie value — that
characterization is forbidden (the legacy engine's maximum attainable score
is 0.90, the defect the registry exists to kill).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from smartmatch_domain.factor_registry import (
    PROPOSED_FACTORS,
    REGISTRY_VERSION,
    FactorKind,
    assert_registry_approved,
    assert_scoring_ready,
    factor_keys,
    normalize_weights,
)
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.factors.topic_relevance import TopicRelevanceInputs, score_topic_relevance
from smartmatch_domain.factors.travel_burden import TravelInputs, score_travel_burden

__all__ = [
    "STAGE_B_FORMULA_VERSION",
    "CandidateEvidence",
    "StageBScore",
    "rank_candidates",
    "score_candidate",
]

#: Versioned independently of both the registry version and each factor's own
#: formula version: any change to *how* factor scores are composed into one
#: Stage B value (the weighting, the penalty-complement rule, the unknown
#: propagation rule) is a new formula version.
STAGE_B_FORMULA_VERSION: Final[str] = "1.0.0"

#: Kind lookup for composing a factor's contribution (F-25 / ADR-0011): a
#: SUITABILITY factor's value contributes directly, a PENALTY factor's value
#: contributes as its complement. Built once from the registry so this module
#: never hand-encodes which key is which kind.
_FACTOR_KIND: Final[Mapping[str, FactorKind]] = {spec.key: spec.kind for spec in PROPOSED_FACTORS}

#: Tolerance for the composite-score bound check, matching the tolerance
#: :func:`~smartmatch_domain.factor_registry.assert_scoring_ready` uses for
#: the weight-sum invariant. Convex combinations of values in ``[0.0, 1.0]``
#: against weights summing to ``1.0`` stay in ``[0.0, 1.0]`` mathematically;
#: this only absorbs floating-point rounding at the boundary.
_BOUND_TOLERANCE: Final[float] = 1e-9


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    """Everything :func:`score_candidate` is permitted to see for one candidate.

    Attributes:
        subject_id: Stable identifier for the professional. Non-empty.
        topic: Inputs for the ``topic_relevance`` factor.
        travel: Inputs for the ``travel_burden`` factor.
    """

    subject_id: str
    topic: TopicRelevanceInputs
    travel: TravelInputs

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")


@dataclass(frozen=True, slots=True)
class StageBScore:
    """One candidate's Stage B composite score, or its explicit absence.

    Attributes:
        subject_id: Stable identifier for the professional. Non-empty.
        value: The composite score in ``[0.0, 1.0]``, or ``None`` when any
            registered factor's evidence is unknown. ``None`` is never
            coerced to ``0.0`` (ADR-0011).
        factor_scores: Every implemented Stage B factor's score, in registry
            (``factor_keys()``) order, including unknown ones — the
            explanation layer needs to see that a factor was unknown, not
            just that the composite is.
        applied_weights: The normalized weights actually applied.
        unknown_factor_keys: The keys among ``factor_scores`` whose value was
            unknown, in registry order.
        registry_version: The factor registry version this score was
            produced against.
        formula_version: The Stage B composition formula version.
    """

    subject_id: str
    value: float | None
    factor_scores: tuple[FactorScore, ...]
    applied_weights: Mapping[str, float]
    unknown_factor_keys: tuple[str, ...]
    registry_version: str
    formula_version: str

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        if self.value is not None and not (
            -_BOUND_TOLERANCE <= self.value <= 1.0 + _BOUND_TOLERANCE
        ):
            raise ValueError(f"value: must be in [0.0, 1.0] or None, got {self.value!r}")


def score_candidate(
    evidence: CandidateEvidence,
    *,
    weight_overrides: Mapping[str, float] | None = None,
) -> StageBScore:
    """Score one candidate's Stage B composite.

    Args:
        evidence: The candidate's factor inputs.
        weight_overrides: Optional weight overrides, normalized on apply by
            :func:`~smartmatch_domain.factor_registry.normalize_weights`
            rather than hand-tuned (F-25).

    Returns:
        A :class:`StageBScore`. ``value`` is ``None`` when any registered
        factor's evidence is unknown (ADR-0011); otherwise it is the
        weighted composite — a PENALTY factor entering as its complement so
        every factor contributes positively to the sum — rounded to 6
        decimal places.

    Raises:
        RegistryNotApprovedError: if the factor registry has not been
            approved. Raised before any evidence is read.
        RegistryNotReadyError: if the implemented scoring set is not exactly
            the approved scoring set. Raised before any evidence is read.
        ValueError: if a supplied weight override is negative, or if
            ``evidence.subject_id`` is empty or blank.
    """
    assert_registry_approved()
    assert_scoring_ready()

    applied_weights = normalize_weights(weight_overrides)

    scores_by_key: dict[str, FactorScore] = {
        "topic_relevance": score_topic_relevance(evidence.topic),
        "travel_burden": score_travel_burden(evidence.travel),
    }
    factor_scores = tuple(scores_by_key[key] for key in factor_keys() if key in scores_by_key)

    unknown_factor_keys = tuple(score.factor_key for score in factor_scores if score.is_unknown)

    value: float | None
    if unknown_factor_keys:
        # ADR-0011: an unknown factor makes the composite unknown. Never
        # dropped, never substituted with 0.0, and the remaining weights are
        # never re-spread over the known subset (that would let an
        # evidence-free candidate outrank an evidenced one).
        value = None
    else:
        total = 0.0
        for score in factor_scores:
            factor_value = score.value
            # unknown_factor_keys is empty in this branch, so every score's
            # value is a float, not None; this makes that fact explicit for
            # mypy rather than asserting it silently.
            assert factor_value is not None, (
                f"{score.factor_key}: unreachable — is_unknown was False"
            )
            kind = _FACTOR_KIND[score.factor_key]
            # F-25 penalty-complement rule: subtracting a penalty directly
            # would put the composite in [-w_penalty, 1 - w_penalty], which
            # is not a score. Its complement (1 - value) is an affine
            # reparameterization that adds the constant sum(weights over
            # penalty factors), preserves the ranking of every pair of
            # candidates exactly, and keeps the composite in [0.0, 1.0] with
            # weights summing to 1.0.
            contribution = factor_value if kind is FactorKind.SUITABILITY else 1.0 - factor_value
            total += applied_weights[score.factor_key] * contribution
        value = round(total, 6)

    return StageBScore(
        subject_id=evidence.subject_id,
        value=value,
        factor_scores=factor_scores,
        applied_weights=applied_weights,
        unknown_factor_keys=unknown_factor_keys,
        registry_version=REGISTRY_VERSION,
        formula_version=STAGE_B_FORMULA_VERSION,
    )


def rank_candidates(
    candidates: Sequence[CandidateEvidence],
    *,
    weight_overrides: Mapping[str, float] | None = None,
) -> tuple[StageBScore, ...]:
    """Score every candidate and order them by the ratified tie-break.

    Args:
        candidates: The candidates to score. Must not contain a duplicate
            ``subject_id``.
        weight_overrides: Optional weight overrides, passed through to every
            :func:`score_candidate` call.

    Returns:
        One :class:`StageBScore` per candidate. Known scores sort first
        (unknown scores sort last and are never treated as ``0.0``), then by
        descending ``value``, then by ascending ``subject_id``
        (lexicographic). Never mutates ``candidates``.

    Raises:
        ValueError: if ``candidates`` contains a duplicate ``subject_id``.
    """
    subject_ids = [candidate.subject_id for candidate in candidates]
    if len(set(subject_ids)) != len(subject_ids):
        raise ValueError("subject_id: duplicate candidate subject_id in rank_candidates")

    scores = tuple(
        score_candidate(candidate, weight_overrides=weight_overrides) for candidate in candidates
    )
    return tuple(
        sorted(
            scores,
            key=lambda result: (result.value is None, -(result.value or 0.0), result.subject_id),
        )
    )
