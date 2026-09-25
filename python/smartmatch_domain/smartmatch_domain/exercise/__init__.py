"""Facts about the class-exercise scope that hold before any of it is built.

ADR-0025 gives the Spring 2027 class exercise its own product scope, its own
tables, and its own routers. Two of its decisions are *constants*, not
behaviour, and both are needed by code that runs long before there is a profile
row to apply them to — so they live here, in the domain, where a router, a
repository, and a test can each read the same copy.

``EXERCISE_TEAM_NUMBERS``
    The teams the entry screen may offer. Six, from
    ``docs/product/class-exercise-requirements.md`` ("Getting in": *a team
    enters its team number (1–6)*). This is a stated requirement, not an open
    question — no row in ``class-exercise-open-questions.md`` governs it.

``EXERCISE_WITHHELD_FIELDS``
    The columns of the data file that are stored and never served (ADR-0025
    D6): Ann's two pink columns, the hidden true interests and the hidden true
    career goal. Her Read Me: "the app must never show them and never use them
    for matching. Used only by the results rule and by the refresh (a new card
    copies these)." No factor function consumes either and no response model
    carries either.

Nothing in this package imports persistence, a framework, or a router. When
CE-SCHEMA lands its ``smartmatch_persistence.exercise`` package, the copy of
``EXERCISE_WITHHELD_FIELDS`` it defines should be deleted in favour of this one
rather than kept beside it: two answers to "what is withheld" is one more than
the question has. That dedupe is noted on this track's pull request.
"""

from __future__ import annotations

from typing import Final

#: Every team number the exercise recognises, in the order a picker shows them.
#: A tuple rather than a range so the value is literal at every read site and a
#: test can compare it without reconstructing the bounds.
EXERCISE_TEAM_NUMBERS: Final[tuple[int, ...]] = (1, 2, 3, 4, 5, 6)

#: Fields stored on an exercise row that leave the server in no response and
#: appear in no exported contract (ADR-0025 D6).
EXERCISE_WITHHELD_FIELDS: Final[frozenset[str]] = frozenset(
    {"hidden_true_interests", "hidden_true_career_goal"}
)

__all__ = ["EXERCISE_TEAM_NUMBERS", "EXERCISE_WITHHELD_FIELDS"]
