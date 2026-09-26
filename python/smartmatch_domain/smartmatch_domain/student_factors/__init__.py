"""The four student factors, and the evidence they read. Nothing else.

ADR-0025 D3 / design spec §4.2. The factors Ann names are implemented **once**,
as pure functions over a ``(ProfileEvidence, EventEvidence)`` pair, so that the
class exercise's :data:`~smartmatch_domain.exercise.registry.EXERCISE_REGISTRY`
and ADR-0024's later student registry compose the same code rather than two
copies of it.

**What this package deliberately does not hold.** No registry, no weights, no
ranking, no ``rank_events_for_student``, and no student-side entry point.
OQ-SE-01 and OQ-SE-02 are deferred rows; a shared module that grew a
``STUDENT_REGISTRY`` would be shipping a deferred decision under cover of a
shared one. The composition — which rulebook, which weights, which order —
belongs to whichever registry composes these functions, and today that is
:mod:`smartmatch_domain.exercise.registry` alone.

No vocabulary is declared here: terms are compared as exact normalized
strings. The class exercise closes its vocabularies at ingest
(:mod:`smartmatch_domain.exercise.vocabulary`), and these functions are shared
with a student registry that may not share that list.
"""

from __future__ import annotations

from smartmatch_domain.student_factors.evidence import (
    EventEvidence,
    ProfileCard,
    ProfileEvidence,
)
from smartmatch_domain.student_factors.factors import (
    CAREER_GOAL_FIT_FACTOR_KEY,
    PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
    SAME_MAJOR_FACTOR_KEY,
    STATED_INTEREST_OVERLAP_FACTOR_KEY,
    STUDENT_FACTOR_KEYS,
    UNDECIDED_EXPLORATORY_GOAL_FIT,
    career_goal_fit,
    past_event_topic_overlap,
    same_major,
    stated_interest_overlap,
)
from smartmatch_domain.student_factors.terms import jaccard, normalized_term, normalized_terms

__all__ = [
    "CAREER_GOAL_FIT_FACTOR_KEY",
    "PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY",
    "SAME_MAJOR_FACTOR_KEY",
    "STATED_INTEREST_OVERLAP_FACTOR_KEY",
    "STUDENT_FACTOR_KEYS",
    "UNDECIDED_EXPLORATORY_GOAL_FIT",
    "EventEvidence",
    "ProfileCard",
    "ProfileEvidence",
    "career_goal_fit",
    "jaccard",
    "normalized_term",
    "normalized_terms",
    "past_event_topic_overlap",
    "same_major",
    "stated_interest_overlap",
]
