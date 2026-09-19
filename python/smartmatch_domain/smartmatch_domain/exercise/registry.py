"""``EXERCISE_REGISTRY``: the class exercise's rulebook, and only its rulebook.

ADR-0025 D3 / design spec §4.3. A second :class:`FactorRegistry` value beside
:data:`~smartmatch_domain.factor_registry.CBA_REGISTRY`, composing the four
shared student factors under Ann's plain-words labels. Nothing in
``factor_registry.py``, ``scoring.py``, or ``explanation.py`` changes to admit
it — that is the whole claim the parameterisation of PR #173 made, and this
module is the first thing to test it.

## It cannot be reached by accident

Three separate things keep this rulebook out of the CBA process:

1. **Its version cannot be mistaken for a CBA pin.** ``exercise-0.1.0`` shares
   no prefix, shape, or suffix with ``2.0.0-approved-oq-cba-004`` or
   ``1.1.1-approved-g1-m6j``, and ``factor_registry``'s impostor guard refuses
   any registry that claims one of those.
2. **Its mode vocabulary is its own.** ``exercise-1`` is the only mode this
   rulebook may name, and ``cba-physical-1`` is not nameable inside it
   (ADR-0016 Proposal 5).
3. **Registration happens on importing this module, and nothing in the CBA
   composition imports it.** ``smartmatch_domain.scoring`` does not,
   ``smartmatch_domain.explanation`` does not, and no CBA router or worker
   does. Until something imports
   :mod:`smartmatch_domain.exercise.registry`, ``registry_for_version(
   "exercise-0.1.0")`` raises, which is the correct answer for a process that
   has no exercise in it. ``tests/unit/test_exercise_registry_isolation.py``
   pins that in a fresh interpreter.

## Weights

**PLACEHOLDER (OQ-CE-02).** The register's stated placeholder is equal weights
— 0.25 each — and that is what the four named constants below carry. They are
placeholders, not a decision: OQ-CE-02 stays OPEN, and Ann and Chau set the
real numbers. A team adjusts them per run through ``weights``, which is the
requirement ("four adjustable factors") and not a way of closing the row.

## Why this module validates weight overrides itself

:func:`smartmatch_domain.weight_settings.validate_weight_overrides` is
CBA-bound in two places that are not parameters: its admissible key set is
``CONFIGURABLE_FACTOR_KEYS = APPROVED_SCORING_KEYS`` (the CBA four), and its
zero-total check resolves defaults through ``normalize_weights(model=model)``
with the registry argument defaulting to ``CBA_REGISTRY``. Passing it the
exercise models would refuse every exercise key as "not a configurable factor"
and then read CBA defaults for the ones it accepted. Widening it is an edit to
a G1-governed module that this track is not authorised to make, so
:func:`validate_exercise_weight_overrides` below is the minimal exercise
equivalent, written to the same rule — refuse, never repair — and naming every
offending field at once.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from smartmatch_domain.factor_registry import (
    FactorKind,
    FactorRegistry,
    FactorSpec,
    ScoringModel,
    normalize_weights,
    register_registry,
)
from smartmatch_domain.student_factors import (
    CAREER_GOAL_FIT_FACTOR_KEY,
    PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
    SAME_MAJOR_FACTOR_KEY,
    STATED_INTEREST_OVERLAP_FACTOR_KEY,
)

__all__ = [
    "CAREER_GOAL_FIT_DEFAULT_WEIGHT",
    "EXERCISE_APPROVED_ON",
    "EXERCISE_APPROVED_SCORING_KEYS",
    "EXERCISE_APPROVER",
    "EXERCISE_DEFAULT_WEIGHTS",
    "EXERCISE_FACTOR_LABELS",
    "EXERCISE_MODE_VOCABULARY",
    "EXERCISE_REGISTRY",
    "EXERCISE_REGISTRY_VERSION",
    "EXERCISE_SCORING_MODE",
    "EXERCISE_SCORING_MODEL",
    "EXERCISE_SCORING_MODE_VERSION",
    "EXERCISE_STATUS",
    "PAST_EVENT_TOPIC_OVERLAP_DEFAULT_WEIGHT",
    "SAME_MAJOR_DEFAULT_WEIGHT",
    "STATED_INTEREST_OVERLAP_DEFAULT_WEIGHT",
    "InvalidExerciseWeightError",
    "exercise_applied_weights",
    "validate_exercise_weight_overrides",
]

#: The exercise rulebook's version. Deliberately unlike a CBA pin in every
#: part: the ``exercise-`` prefix means no string comparison, prefix match, or
#: human skim can confuse the two, and the registry's own impostor guard
#: refuses anything that claims a CBA version without being the CBA registry.
EXERCISE_REGISTRY_VERSION: Final[str] = "exercise-0.1.0"

#: Approved on the authority of the requirements document, not of a gate: the
#: exercise has no real person's data and so no privacy question to wait on
#: (ADR-0025 D3).
EXERCISE_STATUS: Final[str] = "approved"

#: Named, because "approved" with no approver is a checkbox.
EXERCISE_APPROVER: Final[str] = "Ann Wang, class-exercise requirements 2026-09-15"

#: The date of the requirements document this rulebook is approved on.
EXERCISE_APPROVED_ON: Final[str] = "2026-09-15"

#: The exercise's one scoring mode. There is one event shape in the exercise —
#: a room with seats — so there is one model, and the vocabulary that holds it
#: is this rulebook's own.
EXERCISE_SCORING_MODE: Final[str] = "exercise-1"

#: The vocabulary's own version, beside the mode on every score.
EXERCISE_SCORING_MODE_VERSION: Final[str] = "1.0.0"

#: Closed, and containing only this rulebook's mode. ``cba-physical-1`` is not
#: nameable here, which is the point (ADR-0016 Proposal 5).
EXERCISE_MODE_VOCABULARY: Final[frozenset[str]] = frozenset({EXERCISE_SCORING_MODE})

#: **PLACEHOLDER (OQ-CE-02.)** Equal weights, the register's stated
#: placeholder, one named constant per factor so a later decision replaces a
#: number that has a name rather than one of four identical literals.
SAME_MAJOR_DEFAULT_WEIGHT: Final[float] = 0.25
STATED_INTEREST_OVERLAP_DEFAULT_WEIGHT: Final[float] = 0.25
CAREER_GOAL_FIT_DEFAULT_WEIGHT: Final[float] = 0.25
PAST_EVENT_TOPIC_OVERLAP_DEFAULT_WEIGHT: Final[float] = 0.25

#: Ann's plain words, from the requirements "Matching" row, verbatim. These are
#: the labels a class participant reads; the registry keys beside them are
#: never shown.
EXERCISE_FACTOR_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        SAME_MAJOR_FACTOR_KEY: "same major",
        STATED_INTEREST_OVERLAP_FACTOR_KEY: "said they are interested in this topic",
        CAREER_GOAL_FIT_FACTOR_KEY: "career goal fits this event",
        PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: "went to similar events before",
    }
)

#: **PLACEHOLDER (OQ-CE-02.)** The default weights by key, bound to the four
#: constants above rather than restating them.
EXERCISE_DEFAULT_WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(
    {
        SAME_MAJOR_FACTOR_KEY: SAME_MAJOR_DEFAULT_WEIGHT,
        STATED_INTEREST_OVERLAP_FACTOR_KEY: STATED_INTEREST_OVERLAP_DEFAULT_WEIGHT,
        CAREER_GOAL_FIT_FACTOR_KEY: CAREER_GOAL_FIT_DEFAULT_WEIGHT,
        PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: PAST_EVENT_TOPIC_OVERLAP_DEFAULT_WEIGHT,
    }
)

_RATIONALE: Final[Mapping[str, str]] = MappingProxyType(
    {
        SAME_MAJOR_FACTOR_KEY: (
            "Requirements 'Matching': major is always available, so this factor is "
            "never unknown and is the one contribution every profile can earn."
        ),
        STATED_INTEREST_OVERLAP_FACTOR_KEY: (
            "Requirements 'Matching': counts only for a profile with a completed "
            "card; for everyone else the reason line says so."
        ),
        CAREER_GOAL_FIT_FACTOR_KEY: (
            "Requirements 'Matching': counts only for a profile with a completed "
            "card, where the stated career goal is a topic of this event."
        ),
        PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: (
            "Requirements 'Matching': topics of past events attended overlap this "
            "event's topics; counts only for a profile that attended one."
        ),
    }
)


def _exercise_spec(key: str, weight: float) -> FactorSpec:
    """One exercise factor's spec: Ann's label, the placeholder weight, built."""
    return FactorSpec(
        key=key,
        display_label=EXERCISE_FACTOR_LABELS[key],
        kind=FactorKind.SUITABILITY,
        proposed_weight=weight,
        implemented=True,
        rationale=_RATIONALE[key],
    )


#: The four specs, in the order the design spec's table states them — which is
#: therefore the order a reason line names contributing factors in.
EXERCISE_FACTORS: Final[tuple[FactorSpec, ...]] = tuple(
    _exercise_spec(key, EXERCISE_DEFAULT_WEIGHTS[key]) for key in EXERCISE_DEFAULT_WEIGHTS
)

#: All four. Unlike the CBA registry, this rulebook declares nothing it does
#: not score: it has no superseded set to keep readable, because it has never
#: produced a stored score under any other version.
EXERCISE_APPROVED_SCORING_KEYS: Final[frozenset[str]] = frozenset(EXERCISE_DEFAULT_WEIGHTS)

#: The exercise's one model.
EXERCISE_SCORING_MODEL: Final[ScoringModel] = ScoringModel(
    registry_version=EXERCISE_REGISTRY_VERSION,
    scoring_mode=EXERCISE_SCORING_MODE,
    scoring_mode_version=EXERCISE_SCORING_MODE_VERSION,
    scoring_keys=tuple(spec.key for spec in EXERCISE_FACTORS),
    is_current=True,
    mode_vocabulary=EXERCISE_MODE_VOCABULARY,
)

#: The class exercise's rulebook as a value.
EXERCISE_REGISTRY: Final[FactorRegistry] = FactorRegistry(
    version=EXERCISE_REGISTRY_VERSION,
    status=EXERCISE_STATUS,
    approver=EXERCISE_APPROVER,
    approved_on=EXERCISE_APPROVED_ON,
    factors=EXERCISE_FACTORS,
    approved_scoring_keys=EXERCISE_APPROVED_SCORING_KEYS,
    scoring_modes={EXERCISE_SCORING_MODE: EXERCISE_SCORING_MODEL},
    mode_vocabulary=EXERCISE_MODE_VOCABULARY,
)

# Import-time, and only on importing *this* module. A stored exercise score
# names ``exercise-0.1.0``; anything that reads one has necessarily imported
# the exercise domain to have produced it, so the binding exists exactly where
# it is needed and nowhere else.
register_registry(EXERCISE_REGISTRY)


class InvalidExerciseWeightError(ValueError):
    """A proposed team weighting that must be refused rather than normalized.

    A :class:`ValueError` subclass, matching
    :class:`smartmatch_domain.weight_settings.InvalidWeightOverrideError`, so a
    caller that already refuses malformed domain input keeps refusing this too.
    """


def _coerce_weight(key: str, raw: object) -> float:
    """One proposed weight as a float, or a sentence saying why it is not."""
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise TypeError(f"{key}: weight must be a number, got {type(raw).__name__}")
    value = float(raw)
    if value != value or value in {float("inf"), float("-inf")}:
        raise TypeError(f"{key}: weight must be a finite number, got {raw!r}")
    if value < 0.0:
        raise TypeError(f"{key}: weight must not be negative, got {value}")
    return value


def validate_exercise_weight_overrides(raw: Mapping[str, object]) -> Mapping[str, float]:
    """Return ``raw`` as an admissible exercise weighting, or refuse it.

    The minimal exercise equivalent of
    :func:`smartmatch_domain.weight_settings.validate_weight_overrides`; the
    module docstring says why that one could not be reused. Same rule: refuse,
    never repair, and name every offending field at once.

    Args:
        raw: What a team proposed, keyed by factor key. An **empty mapping is
            valid** and means "use the placeholder defaults"; a mapping that
            zeroes every factor is refused, because it says "score nothing"
            and every profile would then tie on 0.0 and be ordered by the
            tie-break alone.

    Returns:
        An immutable ``{factor_key: float}`` map with exactly the keys the
        caller supplied. Absent keys are absent, never defaulted — the registry
        answers for them at scoring time.

    Raises:
        InvalidExerciseWeightError: naming every problem at once.
    """
    problems: list[str] = []
    weights: dict[str, float] = {}

    for key in sorted(raw):
        if key not in EXERCISE_APPROVED_SCORING_KEYS:
            problems.append(
                f"{key}: is not one of the exercise's four factors; expected one of "
                f"{sorted(EXERCISE_APPROVED_SCORING_KEYS)}"
            )
            continue
        try:
            weights[key] = _coerce_weight(key, raw[key])
        except TypeError as exc:
            problems.append(str(exc))

    if not problems and weights:
        effective = dict(EXERCISE_DEFAULT_WEIGHTS)
        effective.update(weights)
        if sum(effective.values()) <= 0.0:
            problems.append(
                "the resulting weights sum to zero; every profile would score the same "
                "and the list would be the tie-break alone. Refused rather than "
                "normalized into something plausible."
            )

    if problems:
        raise InvalidExerciseWeightError("; ".join(problems))

    return MappingProxyType(dict(weights))


def exercise_applied_weights(
    overrides: Mapping[str, float] | None = None,
) -> Mapping[str, float]:
    """The normalized weights one exercise run applies.

    A thin, named wrapper over
    :func:`~smartmatch_domain.factor_registry.normalize_weights` pinned to this
    rulebook and its one model, so no caller has to remember to pass both.
    """
    return normalize_weights(
        overrides, model=EXERCISE_SCORING_MODEL, registry=EXERCISE_REGISTRY
    )
