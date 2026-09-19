"""The exercise's scorer, tie-break, and ranked list (design spec §4.3–§4.6).

Importing this module is what puts ``exercise-0.1.0`` in the registry map: it
imports :mod:`smartmatch_domain.exercise.registry`, whose import-time
:func:`~smartmatch_domain.factor_registry.register_registry` call is the only
binding of that version anywhere. Nothing in the CBA composition imports this
module, so nothing in the CBA process can resolve the exercise rulebook.

## What this module is not

:func:`smartmatch_domain.scoring._ranked` is untouched (ADR-0025 D5).
:func:`_exercise_ranked` is a second tie-break beside it, not a change to it,
and neither ranker imports the other. There is likewise no
``rank_events_for_student`` here: that is OQ-SE-01's, and it is deferred.

## The composition, and the one place it differs from ADR-0011

ADR-0011 makes an unknown factor make the *composite* unknown, and
:func:`~smartmatch_domain.scoring.score_cba_candidate` implements exactly that.
The exercise cannot: Ann's requirement is that the other three factors "count
only for profiles that have that information", and about two thirds of the 300
have no card. A rule that made every one of them unscorable would produce a
ranked list of the seventy profiles with cards and no others, which is neither
what she asked for nor a list a marketer would recognise.

So in this composition an unknown factor **contributes nothing**, and — this
is the part ADR-0016 governs and the part a plausible implementation gets
wrong — **its weight is not re-spread over the factors that are known**. A
profile with only a major on file receives exactly the major factor's
contribution: not that contribution scaled up to fill the other three
factors' share, which would let a profile nobody knows anything about outrank
one whose card genuinely matches. The absence costs what it costs.

Unknown is still never ``0.0``: the factor score keeps ``value=None``, the
key is listed in ``unknown_factor_keys``, the marker says what is on file, and
the reason line says so in Ann's words. What the composite does with the
absence, and what the record says about it, are two different questions.

## No numeric score reaches a screen (ADR-0025 D8)

:func:`score_exercise_pair` and :func:`rank_profiles_for_event` return
:class:`~smartmatch_domain.scoring.StageBScore`, which carries the number,
because the ranking needs one. That type is internal to the domain.
:func:`exercise_ranked_list` is what a surface renders, and it carries rank,
reason, marker, and the contributing factor keys — no value, no percentage,
no confidence. ``tests/unit/test_exercise_list_shape.py`` walks the public
types' fields to keep it that way.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from smartmatch_domain.exercise.determinism import exercise_permutation
from smartmatch_domain.exercise.markers import (
    InformationMarker,
    derive_marker,
    information_rank,
)
from smartmatch_domain.exercise.reasons import TieBreakKey, exercise_reason
from smartmatch_domain.exercise.registry import (
    EXERCISE_REGISTRY,
    EXERCISE_SCORING_MODE,
    EXERCISE_SCORING_MODE_VERSION,
    exercise_applied_weights,
)
from smartmatch_domain.factor_registry import (
    assert_registry_approved,
    assert_scoring_ready,
    factor_keys,
)
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.scoring import StageBScore
from smartmatch_domain.student_factors import (
    CAREER_GOAL_FIT_FACTOR_KEY,
    PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
    SAME_MAJOR_FACTOR_KEY,
    STATED_INTEREST_OVERLAP_FACTOR_KEY,
    EventEvidence,
    ProfileEvidence,
    career_goal_fit,
    past_event_topic_overlap,
    same_major,
    stated_interest_overlap,
)

__all__ = [
    "EXERCISE_STAGE_B_FORMULA_VERSION",
    "ExerciseList",
    "ExerciseListEntry",
    "ExerciseProfile",
    "exercise_ranked_list",
    "rank_profiles_for_event",
    "score_exercise_pair",
    "unlisted_class_years",
]

#: This composition's own version, distinct from both
#: :data:`~smartmatch_domain.scoring.STAGE_B_FORMULA_VERSION` and
#: :data:`~smartmatch_domain.scoring.CBA_STAGE_B_FORMULA_VERSION`, because it
#: composes unknowns differently from either and a stored score must say which
#: rule produced it.
EXERCISE_STAGE_B_FORMULA_VERSION: Final[str] = "1.0.0-exercise"


@dataclass(frozen=True, slots=True)
class ExerciseProfile:
    """One of the 300, as the ranker needs to read it.

    **PLACEHOLDER (OQ-CE-01).** ``class_year`` is free text compared by the
    caller's own ``year_rank`` mapping; no vocabulary of year names is declared
    anywhere in this package.

    Attributes:
        profile_no: The profile's number in the data file. The input to the
            fixed order, and nothing else.
        class_year: The profile's year, as the data file spells it.
        evidence: What the four factors may see.
    """

    profile_no: int
    class_year: str
    evidence: ProfileEvidence

    def __post_init__(self) -> None:
        if not self.class_year.strip():
            raise ValueError("class_year: must not be empty or blank")


@dataclass(frozen=True, slots=True)
class ExerciseListEntry:
    """One name on the list, as a class participant sees it (ADR-0025 D8).

    Attributes:
        rank: Position on the list, from 1.
        profile_id: The profile's identifier.
        marker: The "how much we know" group.
        reason: One sentence, in Ann's words.
        contributing_factor_keys: The factors that counted for this name, in
            registry order. Keys, not numbers: the screen renders them through
            :data:`~smartmatch_domain.exercise.registry.EXERCISE_FACTOR_LABELS`.
    """

    rank: int
    profile_id: str
    marker: InformationMarker
    reason: str
    contributing_factor_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExerciseList:
    """The ranked list, cut at the invite limit.

    Attributes:
        entries: The names on the list, in order.
        invite_limit: The cap the list was cut at.
        unlisted_class_years: Class years carried by a profile that were not in
            the caller's ``year_rank`` mapping. Such a year ranks last and is
            reported here rather than guessed at (OQ-CE-01).
    """

    entries: tuple[ExerciseListEntry, ...]
    invite_limit: int
    unlisted_class_years: tuple[str, ...]


def score_exercise_pair(
    profile: ProfileEvidence,
    event: EventEvidence,
    *,
    weights: Mapping[str, float] | None = None,
) -> StageBScore:
    """Score one (profile, event) pair under ``EXERCISE_REGISTRY``.

    Args:
        profile: The profile's evidence.
        event: The event's evidence.
        weights: The team's weights, keyed by factor key. ``None`` uses the
            placeholder defaults (OQ-CE-02). Validate a team's input through
            :func:`~smartmatch_domain.exercise.registry.validate_exercise_weight_overrides`
            before it reaches here.

    Returns:
        A :class:`~smartmatch_domain.scoring.StageBScore` pinned to
        ``exercise-0.1.0`` / ``exercise-1``, with ``subject_id`` holding the
        profile id (ADR-0025 D4). Every factor appears in ``factor_scores``,
        unknown ones included; an unknown contributes nothing to ``value`` and
        its weight is not re-spread.

    Raises:
        RegistryNotApprovedError: if the exercise rulebook is not approved.
        RegistryNotReadyError: if its implemented set is not its approved set.
        ValueError: if a supplied weight is negative.
    """
    assert_registry_approved(registry=EXERCISE_REGISTRY)
    assert_scoring_ready(registry=EXERCISE_REGISTRY)

    applied_weights = exercise_applied_weights(weights)
    by_key: dict[str, FactorScore] = {
        SAME_MAJOR_FACTOR_KEY: same_major(profile, event),
        STATED_INTEREST_OVERLAP_FACTOR_KEY: stated_interest_overlap(profile, event),
        CAREER_GOAL_FIT_FACTOR_KEY: career_goal_fit(profile, event),
        PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: past_event_topic_overlap(profile, event),
    }
    factor_scores = tuple(
        by_key[key] for key in factor_keys(registry=EXERCISE_REGISTRY) if key in by_key
    )
    if {score.factor_key for score in factor_scores} != set(applied_weights):
        raise RuntimeError(
            "the exercise composite would silently deflate: the computed factor set "
            f"{sorted(score.factor_key for score in factor_scores)} is not the weighted set "
            f"{sorted(applied_weights)}"
        )

    unknown_factor_keys = tuple(score.factor_key for score in factor_scores if score.is_unknown)
    total = sum(
        applied_weights[score.factor_key] * score.value
        for score in factor_scores
        if score.value is not None
    )

    return StageBScore(
        subject_id=profile.profile_id,
        value=round(total, 6),
        factor_scores=factor_scores,
        applied_weights=applied_weights,
        unknown_factor_keys=unknown_factor_keys,
        registry_version=EXERCISE_REGISTRY.version,
        formula_version=EXERCISE_STAGE_B_FORMULA_VERSION,
        scoring_mode=EXERCISE_SCORING_MODE,
        scoring_mode_version=EXERCISE_SCORING_MODE_VERSION,
    )


@dataclass(frozen=True, slots=True)
class _Ranked:
    """One profile's score and every key the tie-break reads. Internal."""

    score: StageBScore
    profile: ExerciseProfile
    marker: InformationMarker
    info_rank: int
    year_rank: int
    permutation_position: int


def _unlisted_year_rank(year_rank: Mapping[str, int]) -> int:
    """The rank a year nobody listed carries: below every listed one.

    Derived from the caller's own mapping rather than fixed at a literal, so a
    caller whose ranks are negative still gets "last" rather than "somewhere in
    the middle". Never guessed from the year's own spelling: OQ-CE-01 is open
    and the year vocabulary is Ann's to state.
    """
    return min(year_rank.values(), default=0) - 1


def unlisted_class_years(
    profiles: Sequence[ExerciseProfile], year_rank: Mapping[str, int]
) -> tuple[str, ...]:
    """The class years present among ``profiles`` and absent from ``year_rank``.

    In first-appearance order, each once. Reported rather than guessed: an
    unrecognised year ranks last, and the caller is told which years those
    were so a missing row in the mapping is a visible fact and not a silent
    reordering.
    """
    missing: list[str] = []
    seen: set[str] = set()
    for profile in profiles:
        year = profile.class_year
        if year in year_rank or year in seen:
            continue
        seen.add(year)
        missing.append(year)
    return tuple(missing)


def _exercise_ranked(entries: Sequence[_Ranked]) -> tuple[_Ranked, ...]:
    """Design spec §4.4's key, ascending.

    ``(value is None, -value, -info_rank, -year_rank, permutation_position)``:
    a known score first, then the higher composite, then more information on
    file, then the earlier year (seniors first, as the caller's ``year_rank``
    defines "earlier"), then the fixed order seeded from the dataset checksum.
    The last element is a total order over the dataset, so the sort never falls
    through to input order and never depends on it.
    """
    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                entry.score.value is None,
                -(entry.score.value or 0.0),
                -entry.info_rank,
                -entry.year_rank,
                entry.permutation_position,
            ),
        )
    )


def _tie_break_key(entries: Sequence[_Ranked], index: int) -> TieBreakKey:
    """Which key settled this name's place against an equal-valued neighbour.

    The *finest* key that had to be read against any adjacent neighbour of the
    same composite value: if some neighbour ties on value, information, and
    year, the fixed order is what separated them; if one ties on value and
    information but not year, the year did; if one only ties on value, how much
    is on file did.
    """
    entry = entries[index]
    finest = TieBreakKey.NONE
    for offset in (-1, 1):
        neighbour_index = index + offset
        if not 0 <= neighbour_index < len(entries):
            continue
        neighbour = entries[neighbour_index]
        if neighbour.score.value != entry.score.value:
            continue
        if neighbour.info_rank != entry.info_rank:
            if finest is TieBreakKey.NONE:
                finest = TieBreakKey.INFORMATION
            continue
        if neighbour.year_rank != entry.year_rank:
            if finest in {TieBreakKey.NONE, TieBreakKey.INFORMATION}:
                finest = TieBreakKey.YEAR
            continue
        return TieBreakKey.FIXED_ORDER
    return finest


def _contributing_keys(score: StageBScore) -> tuple[str, ...]:
    """The factor keys that actually added to the composite, in registry order.

    Known and above zero. A measured zero added nothing, and naming it would
    tell a class participant that something counted when it did not.
    """
    return tuple(
        factor.factor_key
        for factor in score.factor_scores
        if factor.value is not None and factor.value > 0.0
    )


def _ranked_entries(
    event: EventEvidence,
    profiles: Sequence[ExerciseProfile],
    *,
    weights: Mapping[str, float] | None,
    year_rank: Mapping[str, int],
    dataset_checksum: str,
) -> tuple[_Ranked, ...]:
    """Score every profile and put the whole set in tie-break order."""
    if not dataset_checksum.strip():
        raise ValueError(
            "dataset_checksum: must not be empty or blank — it is the whole of the "
            "fixed order's seed, and a blank one would make the order depend on "
            "nothing"
        )
    profile_nos = [profile.profile_no for profile in profiles]
    if len(set(profile_nos)) != len(profile_nos):
        raise ValueError("profile_no: duplicate profile number in rank_profiles_for_event")

    permutation = exercise_permutation(dataset_checksum, profile_nos)
    unlisted = _unlisted_year_rank(year_rank)
    entries: list[_Ranked] = []
    for profile in profiles:
        marker = derive_marker(profile.evidence)
        entries.append(
            _Ranked(
                score=score_exercise_pair(profile.evidence, event, weights=weights),
                profile=profile,
                marker=marker,
                info_rank=information_rank(marker),
                year_rank=year_rank.get(profile.class_year, unlisted),
                permutation_position=permutation[profile.profile_no],
            )
        )
    return _exercise_ranked(entries)


def rank_profiles_for_event(
    event: EventEvidence,
    profiles: Sequence[ExerciseProfile],
    *,
    weights: Mapping[str, float] | None = None,
    invite_limit: int,
    year_rank: Mapping[str, int],
    dataset_checksum: str,
) -> tuple[StageBScore, ...]:
    """Rank the whole set for one event and cut it at the invite limit.

    Args:
        event: The event being promoted.
        profiles: Every profile in the dataset.
        weights: The team's weights, or ``None`` for the placeholder defaults.
        invite_limit: The dataset's invite limit (30 by default, set by the
            instructor). Must be positive.
        year_rank: ``{class_year: rank}``, higher first, supplied by the
            caller. **There is no production default** (OQ-CE-01): the year
            vocabulary is Ann's, and a year this mapping does not name ranks
            below every year it does, reported through
            :func:`unlisted_class_years` rather than guessed.
        dataset_checksum: The loaded file's checksum. The whole of the fixed
            order's seed, so the order is identical across runs, teams, and
            processes.

    Returns:
        One :class:`~smartmatch_domain.scoring.StageBScore` per listed profile,
        in tie-break order, cut at ``invite_limit``. ``subject_id`` holds the
        profile id (ADR-0025 D4). Never mutates ``profiles``.

    Raises:
        ValueError: for a non-positive ``invite_limit``, a blank
            ``dataset_checksum``, or a duplicate ``profile_no``.
    """
    if invite_limit <= 0:
        raise ValueError(f"invite_limit: must be positive, got {invite_limit}")
    entries = _ranked_entries(
        event,
        profiles,
        weights=weights,
        year_rank=year_rank,
        dataset_checksum=dataset_checksum,
    )
    return tuple(entry.score for entry in entries[:invite_limit])


def exercise_ranked_list(
    event: EventEvidence,
    profiles: Sequence[ExerciseProfile],
    *,
    weights: Mapping[str, float] | None = None,
    invite_limit: int,
    year_rank: Mapping[str, int],
    dataset_checksum: str,
) -> ExerciseList:
    """The same ranking, as the thing a screen renders (ADR-0025 D8).

    Arguments are :func:`rank_profiles_for_event`'s, and the order is the same
    order — this adds the reason, the marker, and the contributing factor keys,
    and drops every number the ranking used.

    Returns:
        An :class:`ExerciseList`. The tie-break key each name's reason cites is
        read from the **whole** ranked set before the cut, so the last name on
        the list gives the same reason it would have given one place further
        down.
    """
    if invite_limit <= 0:
        raise ValueError(f"invite_limit: must be positive, got {invite_limit}")
    entries = _ranked_entries(
        event,
        profiles,
        weights=weights,
        year_rank=year_rank,
        dataset_checksum=dataset_checksum,
    )
    listed: list[ExerciseListEntry] = []
    for position, entry in enumerate(entries[:invite_limit]):
        contributing = _contributing_keys(entry.score)
        listed.append(
            ExerciseListEntry(
                rank=position + 1,
                profile_id=entry.score.subject_id,
                marker=entry.marker,
                reason=exercise_reason(
                    marker=entry.marker,
                    contributing_keys=contributing,
                    tie_break_key=_tie_break_key(entries, position),
                ),
                contributing_factor_keys=contributing,
            )
        )
    return ExerciseList(
        entries=tuple(listed),
        invite_limit=invite_limit,
        unlisted_class_years=unlisted_class_years(profiles, year_rank),
    )
