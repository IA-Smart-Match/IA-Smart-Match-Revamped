"""The four student factors, implemented once (ADR-0025 D3, design spec §4.2).

Four pure functions over ``(ProfileEvidence, EventEvidence)``, each returning a
:class:`~smartmatch_domain.factors.FactorScore`. They are the *only* thing this
package holds. There is deliberately no registry here, no ranker, no
``rank_events_for_student``, and no student-side entry point of any kind: the
rows that would need those (OQ-SE-01, OQ-SE-02) are deferred, and a shared
module that grew them would be building a deferred feature by accident.

| Function | Value | Unknown when |
|---|---|---|
| :func:`same_major` | 1.0 if the major is a target major, else 0.0 | never |
| :func:`stated_interest_overlap` | Jaccard of card interests and event topics | no card |
| :func:`career_goal_fit` | 1.0 if the career goal is a topic of the event, else 0.0 | no card |
| :func:`past_event_topic_overlap` | Jaccard of past topics and this event's | no past events |

**Unknown is ``None``, never ``0.0`` (ADR-0011).** A profile with no card is
not a profile whose interests verifiably miss this event, and the two must stay
distinguishable all the way to the reason line. An *empty* card, by contrast,
scores: the person answered and the answer overlapped nothing. See
:mod:`smartmatch_domain.student_factors.evidence` for the three-state rule the
types enforce.

**Prohibited inputs.** :data:`~smartmatch_domain.factor_registry.PROHIBITED_INPUTS`
is imported here, never restated, and no function below reads anything outside
its two arguments. In particular nothing reads ``hidden_true_interests``
(ADR-0025 D6): the name does not appear in this package, which
``tests/unit/test_student_factors.py`` asserts by walking the source.
"""

from __future__ import annotations

from typing import Final

from smartmatch_domain.factor_registry import PROHIBITED_INPUTS
from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorScore
from smartmatch_domain.student_factors.evidence import EventEvidence, ProfileEvidence
from smartmatch_domain.student_factors.terms import jaccard

__all__ = [
    "CAREER_GOAL_FIT_FACTOR_KEY",
    "PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY",
    "SAME_MAJOR_FACTOR_KEY",
    "STATED_INTEREST_OVERLAP_FACTOR_KEY",
    "STUDENT_FACTOR_KEYS",
    "career_goal_fit",
    "past_event_topic_overlap",
    "same_major",
    "stated_interest_overlap",
]

#: Registry keys for the four functions. Declared beside the implementations so
#: that any registry composing them names the same string the function answers
#: to; a registry is free to label them differently for a human, and
#: :data:`~smartmatch_domain.exercise.registry.EXERCISE_REGISTRY` does exactly
#: that with Ann's plain words.
SAME_MAJOR_FACTOR_KEY: Final[str] = "same_major"
STATED_INTEREST_OVERLAP_FACTOR_KEY: Final[str] = "stated_interest_overlap"
CAREER_GOAL_FIT_FACTOR_KEY: Final[str] = "career_goal_fit"
PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: Final[str] = "past_event_topic_overlap"

#: The four keys, in the order the spec's table states them.
STUDENT_FACTOR_KEYS: Final[tuple[str, ...]] = (
    SAME_MAJOR_FACTOR_KEY,
    STATED_INTEREST_OVERLAP_FACTOR_KEY,
    CAREER_GOAL_FIT_FACTOR_KEY,
    PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
)

# ADR-0025 D3: the prohibited-input set is *imported* from the registry, never
# restated here, and it is used rather than merely referenced — a key that
# named a prohibited input would be a factor scoring something the schema
# refuses, and it fails at import rather than at review.
_PROHIBITED_KEYS: Final[frozenset[str]] = frozenset(STUDENT_FACTOR_KEYS) & PROHIBITED_INPUTS
if _PROHIBITED_KEYS:  # pragma: no cover - a build with this state cannot import
    raise RuntimeError(
        f"student factor keys {sorted(_PROHIBITED_KEYS)} name prohibited inputs "
        "(smartmatch_domain.factor_registry.PROHIBITED_INPUTS)"
    )


def _rounded(value: float) -> float:
    """One factor value at the precision every factor leaves at."""
    return round(value, FACTOR_SCORE_PRECISION)


def same_major(profile: ProfileEvidence, event: EventEvidence) -> FactorScore:
    """Ann's "same major". Never unknown: every profile has a major on file.

    Args:
        profile: The profile's evidence.
        event: The event's evidence.

    Returns:
        ``1.0`` when the profile's major is one of the event's target majors,
        otherwise a measured ``0.0``. An event that targets no major in
        particular gives every profile a measured ``0.0`` — nobody's major is
        among none — rather than an unknown, because the event's row was read
        and it named no major.
    """
    majors = event.normalized_majors
    matched = profile.major.strip().casefold() in majors
    return FactorScore(
        SAME_MAJOR_FACTOR_KEY,
        1.0 if matched else 0.0,
        basis=(
            "major on file is a target major of this event"
            if matched
            else "major on file is not a target major of this event"
        ),
    )


def stated_interest_overlap(profile: ProfileEvidence, event: EventEvidence) -> FactorScore:
    """Ann's "said they are interested in this topic". Unknown with no card.

    Args:
        profile: The profile's evidence.
        event: The event's evidence.

    Returns:
        The Jaccard index of the card's interests and the event's topics, or
        ``None`` when no card exists. A card that exists and lists nothing
        scores ``0.0`` — a measured zero, not an unknown.
    """
    if profile.card is None:
        return FactorScore(
            STATED_INTEREST_OVERLAP_FACTOR_KEY,
            None,
            basis="no profile card on file, so no stated interests to compare",
        )
    interests = profile.card.normalized_interests
    value = jaccard(interests, event.normalized_topics)
    return FactorScore(
        STATED_INTEREST_OVERLAP_FACTOR_KEY,
        _rounded(value),
        basis=(
            f"{len(interests)} stated interests on the card compared with "
            f"{len(event.normalized_topics)} event topics"
        ),
    )


def career_goal_fit(profile: ProfileEvidence, event: EventEvidence) -> FactorScore:
    """Ann's "career goal fits this event". Unknown with no card.

    Args:
        profile: The profile's evidence.
        event: The event's evidence.

    Returns:
        ``1.0`` when the card's career goal is one of the event's topics,
        ``0.0`` when it is not or when the card exists with that field blank,
        and ``None`` when no card exists at all.
    """
    if profile.card is None:
        return FactorScore(
            CAREER_GOAL_FIT_FACTOR_KEY,
            None,
            basis="no profile card on file, so no career goal to compare",
        )
    goal = profile.card.normalized_career_goal
    if goal is None:
        return FactorScore(
            CAREER_GOAL_FIT_FACTOR_KEY,
            0.0,
            basis="profile card on file leaves the career goal blank",
        )
    matched = goal in event.normalized_topics
    return FactorScore(
        CAREER_GOAL_FIT_FACTOR_KEY,
        1.0 if matched else 0.0,
        basis=(
            "career goal on the card is a topic of this event"
            if matched
            else "career goal on the card is not a topic of this event"
        ),
    )


def past_event_topic_overlap(profile: ProfileEvidence, event: EventEvidence) -> FactorScore:
    """Ann's "went to similar events before". Unknown with no past events.

    Args:
        profile: The profile's evidence.
        event: The event's evidence.

    Returns:
        The Jaccard index of the union of the attended events' topics and this
        event's topics, or ``None`` when the profile attended no past event.
        Both "no attendance record on file" and "a record that names no event"
        are unknown here: with no attended event there is no topic set to
        compare, which is a missing input rather than a measured miss. A
        profile that attended events whose topics simply do not overlap scores
        a measured ``0.0``, and the two stay distinguishable.
    """
    attended = profile.normalized_attended_topics
    count = profile.attended_event_count
    if attended is None or not count:
        return FactorScore(
            PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
            None,
            basis=(
                "no past events attended, so there are no earlier topics to compare"
                if count == 0
                else "no attendance record on file, so there are no earlier topics to compare"
            ),
        )
    value = jaccard(attended, event.normalized_topics)
    return FactorScore(
        PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
        _rounded(value),
        basis=(
            f"topics of {count} past events attended compared with "
            f"{len(event.normalized_topics)} event topics"
        ),
    )
