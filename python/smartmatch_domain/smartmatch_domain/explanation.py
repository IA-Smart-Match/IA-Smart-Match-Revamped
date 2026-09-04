"""Per-factor explanations, and the ratified presentation rules (card M9).

:mod:`smartmatch_domain.scoring` produces a :class:`~smartmatch_domain.scoring.
StageBScore`: a composite value, the factor scores behind it, and the weights
that were applied. That is the arithmetic. This module is the *account* of it —
the object a coordinator-facing surface renders, carrying the one fact the
arithmetic alone cannot be trusted to preserve on its way to a screen:

    **an unknown factor is not a zero.**

ADR-0011 is the whole reason this module exists as a type rather than as a
serializer somewhere in the API. ``FactorScore.value is None`` is easy to write
and easy to lose: a ``value or 0.0`` in a response model, a ``?? 0`` in a
TypeScript client, a chart library that treats ``null`` as the origin. So the
distinction is carried as a *discriminator* — :class:`ScoreState` — beside the
value rather than encoded only in the value's nullness. A renderer that reads
``state`` cannot accidentally read an absence as a measurement, because the two
are different strings rather than the same missing number.

## The three ratified presentation rules

``docs/plans/workshops/g1-workshop-output-worksheet.md`` (agenda item 1,
"Presentation (not a factor)") and the Dr. Wang program direction it records:

1. **Return 2-3 candidates.** :data:`MIN_SHORTLIST_SIZE` and
   :data:`MAX_SHORTLIST_SIZE`, named here rather than typed into the router, so
   the API and any later surface agree by construction.
2. **No percentage.** :data:`SCORE_PROVENANCE_LABEL` is the only label a score
   may travel under, and nothing in this module renders, formats, or multiplies
   a value by 100. A score leaves here as a bare number in ``[0.0, 1.0]``
   beside the words "heuristic score"; turning that into "70%" would be the
   legacy "Topic Relevance 0%" surface returning under a new registry, and the
   worksheet's classification table exists precisely because those percentages
   were the symptom stakeholders reported.
3. **Every score carries its registry version.** Agenda item 4 —
   "every run records registry version hash" — is a rule about storage; this is
   its display half. :attr:`CandidateExplanation.registry_version` is not
   optional and is not defaulted, so there is no code path that renders a score
   without saying which rulebook produced it.

## Why the payload round-trip lives here

An explanation is assembled once, on the request that submits a match run, and
read back later by the request that renders it. In between it is JSON on a
durable ``job.payload``. :func:`explanation_to_payload` and
:func:`explanation_from_payload` are that boundary, and they are in the domain
rather than in the router because the property they protect is a domain
property: :func:`explanation_from_payload` refuses a payload in which
``state`` and ``heuristic_score`` disagree, so a stored row that has been
edited, truncated, or written by an older release cannot resurrect the very
collapse this module exists to prevent. A reader that silently repaired such a
row would be inventing the measurement it could not find.

Both directions also call
:func:`~smartmatch_domain.factor_registry.assert_registry_approved`. Reading a
stored score back onto a screen *is* a scoring path — it is the only part of
one a coordinator ever sees — and the standing rule ("every scoring path calls
``assert_registry_approved()``") is worth less if it guards the computation and
not the display.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from smartmatch_domain.factor_registry import (
    PROPOSED_FACTORS,
    FactorSpec,
    assert_registry_approved,
)
from smartmatch_domain.factors import FactorScore, ZeroClassification
from smartmatch_domain.scoring import StageBScore

__all__ = [
    "MAX_SHORTLIST_SIZE",
    "MIN_SHORTLIST_SIZE",
    "SCORE_PROVENANCE_LABEL",
    "CandidateExplanation",
    "FactorExplanation",
    "ScoreState",
    "explain_candidate",
    "explain_candidates",
    "explanation_from_payload",
    "explanation_to_payload",
]

#: The only words a value from this module may be labelled with on a
#: coordinator-facing surface. Ratified: the G1 worksheet's program direction
#: calls the output a heuristic shortlist and forbids a ranked percentage, and
#: the plan's M9 fence requires "the provenance label 'heuristic score' per the
#: artifact's wording". A constant rather than a string typed into each surface
#: so the label cannot drift into "match score" — the legacy name for a number
#: that was systematically deflated to a 0.90 ceiling.
SCORE_PROVENANCE_LABEL: Final[str] = "heuristic score"

#: Fewest candidates a shortlist may contain ("return 2-3 speakers").
#: Enforced where a shortlist is *requested* rather than where it is rendered:
#: a run that could only ever produce one name is a run whose result would
#: break the rule, and refusing it at submission is the only point at which
#: refusing is still cheap.
MIN_SHORTLIST_SIZE: Final[int] = 2

#: Most candidates a shortlist may contain. The other half of "2-3".
MAX_SHORTLIST_SIZE: Final[int] = 3

#: Registry specs by key, built once. Used only to attach a factor's
#: coordinator-facing label and its Stage A/B kind to an explanation; the
#: weights come from the score's own ``applied_weights`` and never from here,
#: because the weights that applied to a *stored* score are the ones that were
#: in force then, not the ones in force now.
_SPECS_BY_KEY: Final[Mapping[str, FactorSpec]] = {spec.key: spec for spec in PROPOSED_FACTORS}


class ScoreState(StrEnum):
    """Whether a number exists, stated beside the number itself (ADR-0011).

    ``MEASURED`` means the evidence was there and the value — possibly
    ``0.0`` — is what it measured. ``UNKNOWN`` means the evidence was absent
    and there is no value at all. The two are different strings so that a
    consumer choosing what to draw makes the choice explicitly; a consumer
    that only looked at the value would have to infer the difference from a
    null, which is the inference every surface in the legacy system got wrong.
    """

    MEASURED = "measured"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FactorExplanation:
    """One factor's contribution to one candidate's score, or its absence.

    Attributes:
        factor_key: The registry key, e.g. ``"topic_relevance"``.
        display_label: :attr:`~smartmatch_domain.factor_registry.FactorSpec.
            display_label` — the coordinator-facing name.
        kind: ``"suitability"`` or ``"penalty"``. Carried because the two read
            in opposite directions: a high suitability value is good and a high
            penalty value is not, and a surface that showed both as bars
            without saying which is which would mislead in exactly one of the
            two cases.
        weight: The normalized Stage B weight actually applied to this factor
            for this score. From the score, not from today's registry.
        state: :class:`ScoreState`.
        value: The factor value in ``[0.0, 1.0]``, or ``None`` when
            :attr:`state` is ``UNKNOWN``. Never a placeholder.
        zero_classification: ``"measured_zero"`` when the value is a genuine
            zero, ``"unknown"`` when there is no value, ``None`` otherwise —
            :attr:`~smartmatch_domain.factors.FactorScore.zero_classification`
            carried through unchanged. This is the field the G1 worksheet's
            agenda-item-3 table is written in terms of ("Show 0% with source"
            versus "'Unknown' — not 0%"), which is why it is reported rather
            than left for a consumer to re-derive from ``value == 0.0``.
        basis: The factor's own account of where its number came from.
            Non-empty by :class:`~smartmatch_domain.factors.FactorScore`'s own
            validation, including on the unknown branch — an unknown carries a
            reason, never a blank.
        estimate_label: Set when the value is an explicitly coarse estimate
            (today: the straight-line travel proxy while D3 is deferred),
            otherwise ``None``.
    """

    factor_key: str
    display_label: str
    kind: str
    weight: float
    state: ScoreState
    value: float | None
    zero_classification: str | None
    basis: str
    estimate_label: str | None = None

    def __post_init__(self) -> None:
        """Refuse an explanation whose state and value disagree.

        The one invariant this type exists to carry, checked rather than
        assumed: ``UNKNOWN`` with a value would be an absence wearing a
        measurement, and ``MEASURED`` without one would be a measurement that
        renders as blank — which some consumer would then fill in with a zero.
        """
        if (self.state is ScoreState.UNKNOWN) != (self.value is None):
            raise ValueError(
                f"{self.factor_key}: state {self.state.value!r} and value "
                f"{self.value!r} disagree (ADR-0011: an unknown has no value, "
                "and a measured value is never absent)"
            )
        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError(
                f"{self.factor_key}: value must be in [0.0, 1.0] or None, got {self.value!r}"
            )
        if not self.basis.strip():
            raise ValueError(f"{self.factor_key}: basis must be a non-empty, non-blank string")


@dataclass(frozen=True, slots=True)
class CandidateExplanation:
    """One candidate's heuristic score and the factors behind it.

    Attributes:
        subject_id: The professional this explains.
        heuristic_score: The Stage B composite in ``[0.0, 1.0]``, or ``None``
            when any factor's evidence was absent. Never coerced, and never
            rendered as a percentage — see :data:`SCORE_PROVENANCE_LABEL`.
        state: :class:`ScoreState` for the composite. ``UNKNOWN`` exactly when
            :attr:`unknown_factor_keys` is non-empty, which is ADR-0011's
            aggregate rule (``scoring.py``: an unknown factor makes the
            composite unknown; the remaining weights are never re-spread over
            the known subset).
        score_label: :data:`SCORE_PROVENANCE_LABEL`, carried on the object so a
            surface renders the label it was given rather than one it chose.
        registry_version: The factor registry version this score was produced
            against. Required — see the module docstring, rule 3.
        formula_version: The Stage B composition formula version.
        unknown_factor_keys: The factors that had no evidence, in registry
            order. Reported separately from :attr:`factors` so "why is this
            unknown" is answerable without scanning, and so an empty tuple is a
            positive statement that every factor was measured.
        factors: Every implemented Stage B factor, in registry order,
            **including the unknown ones**. An unknown factor is never dropped:
            a list that omitted it would make "no evidence for travel" look
            identical to "travel was not part of this score".
    """

    subject_id: str
    heuristic_score: float | None
    state: ScoreState
    score_label: str
    registry_version: str
    formula_version: str
    unknown_factor_keys: tuple[str, ...]
    factors: tuple[FactorExplanation, ...]

    def __post_init__(self) -> None:
        """Check the three things a consumer would otherwise have to trust."""
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        if (self.state is ScoreState.UNKNOWN) != (self.heuristic_score is None):
            raise ValueError(
                f"{self.subject_id}: state {self.state.value!r} and heuristic_score "
                f"{self.heuristic_score!r} disagree (ADR-0011)"
            )
        if bool(self.unknown_factor_keys) != (self.state is ScoreState.UNKNOWN):
            raise ValueError(
                f"{self.subject_id}: unknown_factor_keys "
                f"{list(self.unknown_factor_keys)} does not agree with state "
                f"{self.state.value!r}; an unknown factor makes the composite unknown"
            )
        if not self.registry_version.strip():
            raise ValueError(f"{self.subject_id}: registry_version must not be blank")
        if self.score_label != SCORE_PROVENANCE_LABEL:
            raise ValueError(
                f"{self.subject_id}: score_label must be {SCORE_PROVENANCE_LABEL!r}, "
                f"got {self.score_label!r}"
            )

    @property
    def is_shortlistable(self) -> bool:
        """Whether this candidate can enter a portfolio at all.

        A candidate with no composite has no utility, and
        :class:`~smartmatch_domain.optimizer.PortfolioCandidate` refuses an
        unknown utility rather than coercing it — so an unscorable candidate is
        excluded from the pool and *reported* as excluded, never quietly
        entered at ``0.0`` where it would rank below every measured candidate
        as though it had been measured badly.
        """
        return self.state is ScoreState.MEASURED


def _explain_factor(score: FactorScore, weight: float) -> FactorExplanation:
    """Build one :class:`FactorExplanation` from a factor's own result."""
    spec = _SPECS_BY_KEY.get(score.factor_key)
    classification: ZeroClassification | None = score.zero_classification
    return FactorExplanation(
        factor_key=score.factor_key,
        # A factor that is scored but not in the registry cannot happen —
        # ``score_candidate`` raises ``RegistryNotReadyError`` when its computed
        # keys and the registry's weighted keys diverge — so the fallback is a
        # label for an impossible row rather than a default anybody relies on.
        display_label=spec.display_label if spec is not None else score.factor_key,
        kind=str(spec.kind.value) if spec is not None else "unknown",
        weight=weight,
        state=ScoreState.UNKNOWN if score.is_unknown else ScoreState.MEASURED,
        value=score.value,
        zero_classification=None if classification is None else str(classification.value),
        basis=score.basis,
        estimate_label=score.estimate_label,
    )


def explain_candidate(score: StageBScore) -> CandidateExplanation:
    """Assemble the coordinator-facing account of one Stage B score.

    Args:
        score: The result of :func:`smartmatch_domain.scoring.score_candidate`.

    Returns:
        A :class:`CandidateExplanation` carrying every factor — measured and
        unknown alike — the weights that applied, and the registry version the
        score was produced against.

    Raises:
        RegistryNotApprovedError: while the factor registry is not approved.
            Raised before anything is assembled: an explanation is the visible
            end of a scoring path, and the standing rule guards it too.
    """
    assert_registry_approved()

    state = ScoreState.UNKNOWN if score.value is None else ScoreState.MEASURED
    return CandidateExplanation(
        subject_id=score.subject_id,
        heuristic_score=score.value,
        state=state,
        score_label=SCORE_PROVENANCE_LABEL,
        registry_version=score.registry_version,
        formula_version=score.formula_version,
        unknown_factor_keys=tuple(score.unknown_factor_keys),
        factors=tuple(
            # ``applied_weights`` and ``factor_scores`` are guaranteed to cover
            # the same keys — ``score_candidate`` refuses to return a score
            # where they diverge, which is its guard against the legacy
            # deflation defect — so this lookup cannot miss.
            _explain_factor(factor, score.applied_weights[factor.factor_key])
            for factor in score.factor_scores
        ),
    )


def explain_candidates(scores: Sequence[StageBScore]) -> tuple[CandidateExplanation, ...]:
    """Explain a whole scored pool, preserving the order it arrives in.

    Order is the caller's — :func:`smartmatch_domain.scoring.rank_candidates`
    has already applied the ratified tie-break (known scores first, then
    descending value, then ascending ``subject_id``), and re-sorting here would
    be a second ordering rule nothing approved.
    """
    return tuple(explain_candidate(score) for score in scores)


def explanation_to_payload(explanation: CandidateExplanation) -> dict[str, Any]:
    """Render one explanation as the JSON that goes onto a durable payload.

    Plain built-ins only, and every field written out — including the ``None``
    values. A serializer that omitted nulls to keep the payload lean would make
    "unknown" and "this release did not record it" the same absence on the way
    back in, and :func:`explanation_from_payload` would then have to guess.
    """
    return {
        "subject_id": explanation.subject_id,
        "heuristic_score": explanation.heuristic_score,
        "state": explanation.state.value,
        "score_label": explanation.score_label,
        "registry_version": explanation.registry_version,
        "formula_version": explanation.formula_version,
        "unknown_factor_keys": list(explanation.unknown_factor_keys),
        "factors": [
            {
                "factor_key": factor.factor_key,
                "display_label": factor.display_label,
                "kind": factor.kind,
                "weight": factor.weight,
                "state": factor.state.value,
                "value": factor.value,
                "zero_classification": factor.zero_classification,
                "basis": factor.basis,
                "estimate_label": factor.estimate_label,
            }
            for factor in explanation.factors
        ],
    }


def _read_number(raw: object, field: str) -> float | None:
    """Read a nullable number, refusing a ``bool`` and refusing a string.

    ``bool`` first, for the reason
    :class:`~smartmatch_domain.optimizer.PortfolioCandidate` gives: it is a
    subclass of ``int`` and would otherwise be read as ``1.0``/``0.0``, which
    on this path would manufacture exactly the fabricated zero ADR-0011
    forbids.
    """
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"{field}: must be a number or null, got {type(raw).__name__}")
    return float(raw)


def _read_text(raw: object, field: str, *, allow_none: bool = False) -> str | None:
    """Read a string field, refusing a blank one."""
    if raw is None and allow_none:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field}: must be a non-blank string")
    return raw


def _factor_from_payload(entry: object, index: int) -> FactorExplanation:
    """Read one factor explanation back, or say which entry was unreadable."""
    if not isinstance(entry, Mapping):
        raise ValueError(f"factors[{index}]: must be an object")
    state_value = _read_text(entry.get("state"), f"factors[{index}].state")
    if state_value not in {member.value for member in ScoreState}:
        raise ValueError(f"factors[{index}].state: unrecognised state {state_value!r}")
    weight = _read_number(entry.get("weight"), f"factors[{index}].weight")
    if weight is None:
        raise ValueError(f"factors[{index}].weight: must be a number")
    classification = _read_text(
        entry.get("zero_classification"),
        f"factors[{index}].zero_classification",
        allow_none=True,
    )
    # ``FactorExplanation.__post_init__`` is what rejects a state/value
    # disagreement; this function only has to get the values across the
    # boundary without repairing them.
    return FactorExplanation(
        factor_key=str(_read_text(entry.get("factor_key"), f"factors[{index}].factor_key")),
        display_label=str(
            _read_text(entry.get("display_label"), f"factors[{index}].display_label")
        ),
        kind=str(_read_text(entry.get("kind"), f"factors[{index}].kind")),
        weight=weight,
        state=ScoreState(state_value),
        value=_read_number(entry.get("value"), f"factors[{index}].value"),
        zero_classification=classification,
        basis=str(_read_text(entry.get("basis"), f"factors[{index}].basis")),
        estimate_label=_read_text(
            entry.get("estimate_label"), f"factors[{index}].estimate_label", allow_none=True
        ),
    )


def explanation_from_payload(payload: object) -> CandidateExplanation:
    """Read one explanation back off a durable payload.

    The inverse of :func:`explanation_to_payload`, and deliberately strict. The
    payload is a row in a database: it can predate this code, have been written
    by an older release, or have been edited by hand during an incident. A
    reader that filled in a missing ``state`` from the presence of a value —
    or, worse, a missing value with ``0.0`` — would take the one defect this
    whole module exists to prevent and make it a property of the read path.

    Raises:
        ValueError: naming the field that could not be read, or the invariant
            it violated. The caller decides what an unreadable explanation
            means for its response; this function will not guess.
        RegistryNotApprovedError: while the factor registry is not approved.
            Rendering a stored score is a scoring path.
    """
    assert_registry_approved()

    if not isinstance(payload, Mapping):
        raise ValueError("explanation: must be an object")

    raw_factors = payload.get("factors")
    if not isinstance(raw_factors, list):
        raise ValueError("factors: must be a list")

    state_value = _read_text(payload.get("state"), "state")
    if state_value not in {member.value for member in ScoreState}:
        raise ValueError(f"state: unrecognised state {state_value!r}")

    raw_unknown = payload.get("unknown_factor_keys")
    if not isinstance(raw_unknown, list) or not all(
        isinstance(entry, str) for entry in raw_unknown
    ):
        raise ValueError("unknown_factor_keys: must be a list of strings")

    return CandidateExplanation(
        subject_id=str(_read_text(payload.get("subject_id"), "subject_id")),
        heuristic_score=_read_number(payload.get("heuristic_score"), "heuristic_score"),
        state=ScoreState(state_value),
        score_label=str(_read_text(payload.get("score_label"), "score_label")),
        registry_version=str(_read_text(payload.get("registry_version"), "registry_version")),
        formula_version=str(_read_text(payload.get("formula_version"), "formula_version")),
        unknown_factor_keys=tuple(str(entry) for entry in raw_unknown),
        factors=tuple(
            _factor_from_payload(entry, index) for index, entry in enumerate(raw_factors)
        ),
    )
