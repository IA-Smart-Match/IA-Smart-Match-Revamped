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
a legacy score value anywhere, including the legacy tie value — that
characterization is forbidden (the legacy engine's maximum attainable score
is 0.90, the defect the registry exists to kill).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from smartmatch_domain.factor_registry import (
    PROPOSED_FACTORS,
    SUPERSEDED_G1_MODEL,
    FactorKind,
    RegistryNotReadyError,
    ScoringModel,
    assert_registry_approved,
    assert_scoring_ready,
    factor_keys,
    normalize_weights,
    resolve_scoring_model,
)
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.factors.cba_semantic_topic import (
    CBA_SEMANTIC_TOPIC_FACTOR_KEY,
    SemanticTopicProvider,
    SpeakerTopicEvidence,
    score_cba_semantic_topic,
)
from smartmatch_domain.factors.industry_match import IndustryMatchInputs, score_industry_match
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    ProximityInputs,
    SpeakerLocation,
    proximity_is_scored,
    score_proximity,
)
from smartmatch_domain.factors.role_match import RoleMatchInputs, score_role_match
from smartmatch_domain.factors.topic_relevance import TopicRelevanceInputs, score_topic_relevance
from smartmatch_domain.factors.travel_burden import TravelInputs, score_travel_burden

__all__ = [
    "CBA_STAGE_B_FORMULA_VERSION",
    "STAGE_B_FORMULA_VERSION",
    "CandidateEvidence",
    "CbaCandidateEvidence",
    "StageBScore",
    "rank_candidates",
    "rank_cba_candidates",
    "score_candidate",
    "score_cba_candidate",
]

#: Versioned independently of both the registry version and each factor's own
#: formula version: any change to *how* factor scores are composed into one
#: Stage B value (the weighting, the penalty-complement rule, the unknown
#: propagation rule) is a new formula version.
STAGE_B_FORMULA_VERSION: Final[str] = "1.0.0"

#: The CBA composition's own version. Separate from
#: :data:`STAGE_B_FORMULA_VERSION` because the two compositions differ in a way
#: a single version string could not express: the CBA one admits ADR-0016's
#: third evidence state, so a ``policy_neutral`` factor participates instead of
#: making the composite unknown. A stored run says which composition produced
#: it, and neither version is ever read as the other.
CBA_STAGE_B_FORMULA_VERSION: Final[str] = "2.0.0-cba"

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
        policy_neutral_factor_keys: The keys among ``factor_scores`` whose
            value came from a stated customer policy rather than a
            measurement, in registry order (ADR-0016 Proposal 7). These
            factors **do** participate in the composite; they are listed so a
            consumer can say which parts of a score were policy without
            comparing floats to a constant.
        scoring_mode: The mode this score was produced under, or ``None`` for
            the superseded pre-ADR-0016 model. ``None`` is not
            ``cba-physical-1``.
        scoring_mode_version: The mode vocabulary's version, set exactly when
            ``scoring_mode`` is.
    """

    subject_id: str
    value: float | None
    factor_scores: tuple[FactorScore, ...]
    applied_weights: Mapping[str, float]
    unknown_factor_keys: tuple[str, ...]
    registry_version: str
    formula_version: str
    policy_neutral_factor_keys: tuple[str, ...] = ()
    scoring_mode: str | None = None
    scoring_mode_version: str | None = None

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        if self.value is not None and not (
            -_BOUND_TOLERANCE <= self.value <= 1.0 + _BOUND_TOLERANCE
        ):
            raise ValueError(f"value: must be in [0.0, 1.0] or None, got {self.value!r}")
        overlap = set(self.unknown_factor_keys) & set(self.policy_neutral_factor_keys)
        if overlap:
            raise ValueError(
                f"{sorted(overlap)}: reported as both unknown and policy_neutral. A "
                "factor is in exactly one of ADR-0016's three states."
            )
        if (self.scoring_mode is None) != (self.scoring_mode_version is None):
            raise ValueError(
                f"scoring_mode {self.scoring_mode!r} and scoring_mode_version "
                f"{self.scoring_mode_version!r} must be set or unset together"
            )


def score_candidate(
    evidence: CandidateEvidence,
    *,
    weight_overrides: Mapping[str, float] | None = None,
) -> StageBScore:
    """Score one candidate's Stage B composite under the **superseded** model.

    This is the G1 two-factor composition (``topic_relevance`` 0.70 /
    ``travel_burden`` 0.30) and it is retained, unchanged in arithmetic, so
    that a run stored against ``1.1.1-approved-g1-m6j`` can still be
    reproduced (OQ-CBA-025: coexist). It pins
    :data:`~smartmatch_domain.factor_registry.SUPERSEDED_G1_MODEL` explicitly
    rather than reading ``REGISTRY_VERSION``, which is the whole point: after
    the 2.0.0 bump a score produced by *this* function must still say it came
    from the rulebook that defines these two factors, not from the one that
    superseded them. Its ``scoring_mode`` is ``None``, because the mode
    vocabulary did not exist when this composition was approved.

    New CBA work calls :func:`score_cba_candidate`.

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
            the approved scoring set (raised before any evidence is read), or
            if this module's computed factor_scores keys diverge from the
            registry's applied_weights keys (the legacy deflation defect
            recurring in this module — see the inline comment above the
            check).
        ValueError: if a supplied weight override is negative, if the
            resulting applied weights do not sum to 1.0 (an all-zero or
            otherwise degenerate override), or if ``evidence.subject_id`` is
            empty or blank.
    """
    assert_registry_approved()
    assert_scoring_ready()

    applied_weights = normalize_weights(weight_overrides, model=SUPERSEDED_G1_MODEL)
    # assert_scoring_ready() only validates the *default* normalize_weights()
    # call — it has no way to see caller-supplied weight_overrides. A
    # degenerate override (e.g. every implemented factor zeroed) makes
    # normalize_weights() fall back to all-zero weights rather than raising,
    # which would otherwise let a well-evidenced candidate silently compose
    # to a fabricated 0.0 that is indistinguishable from a genuine measured
    # zero. Re-checking the sum-to-one invariant here, on the weights this
    # call actually applies, closes that path.
    applied_total = sum(applied_weights.values())
    if abs(applied_total - 1.0) > _BOUND_TOLERANCE:
        raise ValueError(
            f"applied weights sum to {applied_total!r}, not 1.0 "
            f"(weight_overrides={weight_overrides!r}); refusing to compose a "
            "score from weights that do not sum to one"
        )

    scores_by_key: dict[str, FactorScore] = {
        "topic_relevance": score_topic_relevance(evidence.topic),
        "travel_burden": score_travel_burden(evidence.travel),
    }
    factor_scores = tuple(scores_by_key[key] for key in factor_keys() if key in scores_by_key)

    # scores_by_key above is a hand-written literal; applied_weights comes from
    # the registry. Nothing else ties them together, so a future card that adds
    # a third approved factor to both PROPOSED_FACTORS and
    # APPROVED_SCORING_KEYS without also editing scores_by_key here would leave
    # applied_weights with three entries summing to 1.0 while factor_scores
    # still has two — this is the legacy deflation defect
    # (factor_registry.py: normalizing across all nine declared keys while
    # summing over only the seven computed ones, capping every score at 0.90)
    # recurring inside this module instead of the registry. The reverse
    # direction (a computed factor with no matching weight) already fails
    # loudly below via applied_weights[score.factor_key]; this closes the
    # silent, deflating direction.
    scored_keys = {score.factor_key for score in factor_scores}
    weighted_keys = set(applied_weights)
    if scored_keys != weighted_keys:
        raise RegistryNotReadyError(
            "Stage B composite would silently deflate: factor_scores covers "
            f"{sorted(scored_keys)} but applied_weights covers "
            f"{sorted(weighted_keys)}. This is the legacy deflation defect "
            "(factor_registry.py's stated reason for existing) recurring in "
            "scoring.py — update scores_by_key to match the approved scoring "
            "set before scoring can proceed."
        )

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
        # The superseded model's own pin, not today's REGISTRY_VERSION. A score
        # composed from topic_relevance and travel_burden was produced by the
        # rulebook that declares them, and labelling it 2.0.0 would make a 1.x
        # score comparable-looking against a CBA one — the precise confusion
        # the major bump exists to prevent.
        registry_version=SUPERSEDED_G1_MODEL.registry_version,
        formula_version=STAGE_B_FORMULA_VERSION,
        # No mode: the vocabulary postdates this composition, and ADR-0016
        # Proposal 7 says a run with no mode is read as pre-ADR-0016 rather
        # than as cba-physical-1.
        scoring_mode=SUPERSEDED_G1_MODEL.scoring_mode,
        scoring_mode_version=SUPERSEDED_G1_MODEL.scoring_mode_version,
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
    return _ranked(scores)


def _ranked(scores: tuple[StageBScore, ...]) -> tuple[StageBScore, ...]:
    """Apply the ratified tie-break, shared by both compositions.

    Known scores first (unknown scores sort last and are never treated as
    ``0.0``), then descending value, then ascending ``subject_id``. A
    policy-neutral composite is a known score and sorts by its value like any
    other — that is the point of the state.
    """
    return tuple(
        sorted(
            scores,
            key=lambda result: (result.value is None, -(result.value or 0.0), result.subject_id),
        )
    )


# ---------------------------------------------------------------------------
# The CBA four-factor composition (ADR-0016, accepted 2026-09-05)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CbaCandidateEvidence:
    """Everything :func:`score_cba_candidate` is permitted to see for one candidate.

    Per-candidate only. The request description, the provider, and the scoring
    mode are properties of the *run* and are passed to the scorer once, not
    copied onto every candidate — a per-candidate description would let two
    candidates in one pool be scored against different requests and still look
    comparable.

    Attributes:
        subject_id: Stable identifier for the speaker. Non-empty.
        industry: Resolved sectors for the ``industry_match`` factor.
        role: Resolved role categories for the ``role_match`` factor.
        topic_evidence: What was found when this speaker's profile was looked
            for. Constructed through
            :meth:`~smartmatch_domain.factors.cba_semantic_topic.SpeakerTopicEvidence.from_profile`
            or ``.no_profile_record()``, so the caller cannot say "absent"
            without saying which absence it means — that distinction is the
            whole of ADR-0016 Proposal 1 and it belongs to the caller who read
            the row, not to the scorer.
        location: The speaker's city/postal code, or ``None`` when no location
            record exists. Ignored under ``cba-virtual-1``.
        distance_miles: The already-resolved distance from the CPP campus, or
            ``None`` when the place on file was not resolved to a coordinate.
            This module never resolves one (OQ-CBA-024) and never guesses:
            an unresolved address is an unknown distance, not the Far band.
    """

    subject_id: str
    industry: IndustryMatchInputs
    role: RoleMatchInputs
    topic_evidence: SpeakerTopicEvidence
    location: SpeakerLocation | None = None
    distance_miles: float | None = None

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")


def score_cba_candidate(
    evidence: CbaCandidateEvidence,
    *,
    request_description: str,
    topic_provider: SemanticTopicProvider,
    scoring_mode: str = CBA_PHYSICAL_SCORING_MODE,
    weight_overrides: Mapping[str, float] | None = None,
) -> StageBScore:
    """Score one candidate against the approved CBA four-factor model.

    The composition ADR-0016 accepted, and the one difference from
    :func:`score_candidate` that matters: a ``policy_neutral`` factor
    **participates** in the composite with its policy value, while an
    ``unknown`` factor still makes the composite unknown. Weights are never
    re-spread per candidate in either case — the virtual model's three weights
    are chosen before any candidate is read, which is what makes them a
    different thing from re-spreading around a per-candidate absence.

    Args:
        evidence: This candidate's factor inputs.
        request_description: The Speaker Request's description, compared
            against every candidate's topic evidence. One per run.
        topic_provider: The semantic comparison adapter. Under
            ``ALLOW_LIVE_PROVIDERS=false`` this is always the deterministic
            fixture.
        scoring_mode: ``"cba-physical-1"`` or ``"cba-virtual-1"``, resolved
            from the event before scoring and never inferred here.
        weight_overrides: Optional weight overrides, normalized on apply.

    Returns:
        A :class:`StageBScore` pinned to the CBA registry version, the
        resolved scoring mode, and :data:`CBA_STAGE_B_FORMULA_VERSION`.
        ``value`` is ``None`` when any factor is unknown.

    Raises:
        RegistryNotApprovedError: if the registry is not approved.
        RegistryNotReadyError: if the implemented scoring set is not the
            approved set, or if the computed factor keys diverge from the
            model's weighted keys.
        UnknownScoringModeError: if ``scoring_mode`` is outside the closed
            vocabulary, or names the superseded model (``None``), which this
            function cannot produce.
        ValueError: if a supplied override is negative or the applied weights
            do not sum to one.
    """
    assert_registry_approved()
    assert_scoring_ready()

    model = resolve_scoring_model(scoring_mode)
    return _compose_cba(
        evidence,
        request_description=request_description,
        topic_provider=topic_provider,
        model=model,
        weight_overrides=weight_overrides,
    )


def _cba_factor_scores(
    evidence: CbaCandidateEvidence,
    *,
    request_description: str,
    topic_provider: SemanticTopicProvider,
    model: ScoringModel,
) -> dict[str, FactorScore]:
    """Compute every factor the model admits, and only those.

    Proximity is *absent* under ``cba-virtual-1`` rather than unknown or zero:
    customer §11 removes it from the model, so there is no number to report and
    no absence to explain. ``score_proximity`` refuses to be called in that
    mode at all, which is why the guard is a branch here and not a try/except.
    """
    topic = score_cba_semantic_topic(request_description, evidence.topic_evidence, topic_provider)
    scores: dict[str, FactorScore] = {
        "industry_match": score_industry_match(evidence.industry),
        "role_match": score_role_match(evidence.role),
        CBA_SEMANTIC_TOPIC_FACTOR_KEY: FactorScore(
            CBA_SEMANTIC_TOPIC_FACTOR_KEY,
            topic.value,
            basis=topic.basis,
            policy_id=topic.policy_id,
            policy_version=topic.policy_version,
        ),
    }

    if proximity_is_scored(str(model.scoring_mode)):
        assessment = score_proximity(
            ProximityInputs(
                location=evidence.location,
                distance_miles=evidence.distance_miles,
                scoring_mode=str(model.scoring_mode),
            )
        )
        scores[assessment.score.factor_key] = assessment.score

    return scores


def _compose_cba(
    evidence: CbaCandidateEvidence,
    *,
    request_description: str,
    topic_provider: SemanticTopicProvider,
    model: ScoringModel,
    weight_overrides: Mapping[str, float] | None,
) -> StageBScore:
    """Weight and sum one candidate's CBA factor scores."""
    applied_weights = normalize_weights(weight_overrides, model=model)
    applied_total = sum(applied_weights.values())
    if abs(applied_total - 1.0) > _BOUND_TOLERANCE:
        raise ValueError(
            f"applied weights sum to {applied_total!r}, not 1.0 "
            f"(weight_overrides={weight_overrides!r}); refusing to compose a "
            "score from weights that do not sum to one"
        )

    scores_by_key = _cba_factor_scores(
        evidence,
        request_description=request_description,
        topic_provider=topic_provider,
        model=model,
    )
    factor_scores = tuple(scores_by_key[key] for key in factor_keys() if key in scores_by_key)

    # The same deflation guard ``score_candidate`` carries, for the same
    # reason: the factor set above is written out by hand while the weights
    # come from the registry, and nothing else ties them together. A model that
    # gained a fifth weighted factor without gaining a fifth computed one would
    # normalize over five and sum over four — the legacy defect, in this
    # module, under a new registry.
    scored_keys = {score.factor_key for score in factor_scores}
    weighted_keys = set(applied_weights)
    if scored_keys != weighted_keys:
        raise RegistryNotReadyError(
            "CBA Stage B composite would silently deflate: factor_scores covers "
            f"{sorted(scored_keys)} but applied_weights covers {sorted(weighted_keys)} "
            f"under scoring mode {model.scoring_mode!r}. Update the computed factor "
            "set to match the model before scoring can proceed."
        )

    unknown_factor_keys = tuple(score.factor_key for score in factor_scores if score.is_unknown)
    policy_neutral_factor_keys = tuple(
        score.factor_key for score in factor_scores if score.policy_id is not None
    )

    value: float | None
    if unknown_factor_keys:
        # Unchanged from ADR-0011 and unchanged by ADR-0016: an unknown factor
        # makes the composite unknown, is never dropped, is never substituted
        # with 0.0, and the remaining weights are never re-spread over the
        # known subset. Unknown dominates a policy-neutral factor in the same
        # candidate.
        value = None
    else:
        total = 0.0
        for score in factor_scores:
            factor_value = score.value
            assert factor_value is not None, (
                f"{score.factor_key}: unreachable — is_unknown was False"
            )
            kind = _FACTOR_KIND[score.factor_key]
            # Every current CBA factor is SUITABILITY, including proximity —
            # its band table is stated on the proximity scale, so complementing
            # it would invert the customer's own numbers. The penalty branch is
            # kept because the rule belongs to the composition, not to today's
            # factor set.
            contribution = factor_value if kind is FactorKind.SUITABILITY else 1.0 - factor_value
            total += applied_weights[score.factor_key] * contribution
        value = round(total, 6)

    return StageBScore(
        subject_id=evidence.subject_id,
        value=value,
        factor_scores=factor_scores,
        applied_weights=applied_weights,
        unknown_factor_keys=unknown_factor_keys,
        policy_neutral_factor_keys=policy_neutral_factor_keys,
        registry_version=model.registry_version,
        formula_version=CBA_STAGE_B_FORMULA_VERSION,
        scoring_mode=model.scoring_mode,
        scoring_mode_version=model.scoring_mode_version,
    )


def rank_cba_candidates(
    candidates: Sequence[CbaCandidateEvidence],
    *,
    request_description: str,
    topic_provider: SemanticTopicProvider,
    scoring_mode: str = CBA_PHYSICAL_SCORING_MODE,
    weight_overrides: Mapping[str, float] | None = None,
) -> tuple[StageBScore, ...]:
    """Score a whole CBA pool and order it by the ratified tie-break.

    Args:
        candidates: The candidates to score. Must not contain a duplicate
            ``subject_id``.
        request_description: The Speaker Request's description. One per pool,
            so every candidate is scored against the same request.
        topic_provider: The semantic comparison adapter.
        scoring_mode: The run's mode, resolved from the event.
        weight_overrides: Optional overrides, passed to every candidate.

    Returns:
        One :class:`StageBScore` per candidate, ordered by :func:`_ranked`.
        Never mutates ``candidates``.

    Raises:
        ValueError: if ``candidates`` contains a duplicate ``subject_id``.
    """
    subject_ids = [candidate.subject_id for candidate in candidates]
    if len(set(subject_ids)) != len(subject_ids):
        raise ValueError("subject_id: duplicate candidate subject_id in rank_cba_candidates")

    return _ranked(
        tuple(
            score_cba_candidate(
                candidate,
                request_description=request_description,
                topic_provider=topic_provider,
                scoring_mode=scoring_mode,
                weight_overrides=weight_overrides,
            )
            for candidate in candidates
        )
    )
