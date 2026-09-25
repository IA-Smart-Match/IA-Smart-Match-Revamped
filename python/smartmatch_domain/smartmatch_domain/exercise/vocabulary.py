"""The class exercise's closed vocabularies, as Ann's data file states them.

Ann's final file arrived on 2026-09-24 and its Read Me is the spec for every
value below: six majors, four years, a fixed list of 13 career fields (the
topics), and sixteen career-goal labels. The owner ruled the same day that all
four are **closed** in code: a value outside them is refused at ingest with one
plain sentence rather than stored and compared as free text.

Every term is written **exactly as Ann spells it**. A cell is matched through
:func:`smartmatch_domain.events.normalize_tag_value` — the fold the CBA path
already uses — so ``"technology / Information Systems"`` finds its entry, and
the entry's own spelling is what is stored. ``Supply chain / logistics /
operation`` is singular in Ann's file and stays singular here.

The role→topic table (OQ-CE-14, decided 2026-09-25)
===================================================
:data:`CAREER_GOAL_TOPICS` was the owner's ruling of 2026-09-24, and Ann
confirmed it in her email reply of 2026-09-25. Thirteen labels are
"<field> role" and map to their field, which is what the file shows (each such
profile's first true interest is that field); ``Start my own business`` maps to
``Entrepreneurship / startups`` (Ann: "yes"); ``Graduate school`` points at no
topic (Ann: "no specific event topic: yes"), which scores a *measured* ``0.0``
on "career goal fits this event", never unknown.

``Undecided`` also points at no topic, but it is not a plain miss. Ann's
answer: an undecided student "should match broad exploratory events (company
talks, industry panels, career fairs), at half credit, so a student whose goal
clearly fits still ranks higher", and "the results step should treat undecided
students the same way". So :func:`goal_is_undecided` names it, and
"exploratory" is a property of an event, read off its ``event_type`` through
:data:`EXERCISE_EVENT_TYPES`. The half itself lives beside the factor
(:data:`~smartmatch_domain.student_factors.UNDECIDED_EXPLORATORY_GOAL_FIT`), so
the matching factor and the results rule read one number.

Ann's event types, and which are exploratory
============================================
Her file's ``event_type`` column holds seven kinds of event. Her words map onto
them as: *company talks* = ``Employer talk`` and ``Employer info session``;
*industry panels* = ``Industry panel``; *career fairs* = ``Career fair``. The
other three — ``Workshop``, ``Competition``, ``Networking`` — are not
exploratory. Northline and Harbor are both ``Employer talk``, and Ann: "Treat
both Northline and Harbor as exploratory, since they are company events."

Ann writes the two exercise events' type with a note in brackets —
``Employer talk (exercise event 1)`` and ``Employer talk (exercise event 2)``
— and both spellings are in the table exactly as she wrote them, beside the
bare ``Employer talk`` they name. The vocabulary is closed like the other four:
an ``event_type`` outside it is refused at ingest.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from smartmatch_domain.events import normalize_tag_value

__all__ = [
    "ALL_MAJORS_LABEL",
    "CAREER_GOAL_TOPICS",
    "EXERCISE_CAREER_GOALS",
    "EXERCISE_CLASS_YEARS",
    "EXERCISE_CLASS_YEAR_RANK",
    "EXERCISE_EVENT_TYPES",
    "EXERCISE_MAJORS",
    "EXERCISE_TOPICS",
    "UNDECIDED_CAREER_GOAL",
    "canonical_career_goal",
    "canonical_class_year",
    "canonical_event_type",
    "canonical_major",
    "canonical_topic",
    "career_goal_topic",
    "event_type_is_exploratory",
    "goal_is_undecided",
    "goal_topic_for_matching",
    "is_all_majors",
]

#: The six majors, as the file spells them. One contains a comma.
EXERCISE_MAJORS: Final[tuple[str, ...]] = (
    "Accounting",
    "Computer Information Systems",
    "Finance, Real Estate & Law",
    "International Business & Marketing",
    "Management & Human Resources",
    "Technology & Operations Management",
)

#: What an event's ``target_major`` cell says when the event is for everyone.
#: Only past events carry it in Ann's file; ingest expands it to
#: :data:`EXERCISE_MAJORS` so "same major" is a plain set test for every event.
ALL_MAJORS_LABEL: Final[str] = "All majors"

#: The four years, youngest first, as the file spells them.
EXERCISE_CLASS_YEARS: Final[tuple[str, ...]] = ("Freshman", "Sophomore", "Junior", "Senior")

#: Design spec §4.4's "seniors first", as the ``year_rank`` the tie-break
#: reads: a higher number sorts earlier. The owner's ruling of 2026-09-24.
EXERCISE_CLASS_YEAR_RANK: Final[Mapping[str, int]] = MappingProxyType(
    {year: rank for rank, year in enumerate(EXERCISE_CLASS_YEARS, start=1)}
)

#: The thirteen topics, as the file spells them.
EXERCISE_TOPICS: Final[tuple[str, ...]] = (
    "Accounting / professional services",
    "Consulting",
    "Entertainment / sports / media",
    "Entrepreneurship / startups",
    "Finance / banking / insurance / real estate",
    "Government / nonprofit / public policy",
    "Healthcare administration",
    "Hospitality / tourism / events",
    "Marketing / advertising / public relations",
    "Retail / consumer goods",
    "Sales / business development",
    "Supply chain / logistics / operation",
    "Technology / information systems",
)

#: Each career-goal label, and the topic "career goal fits this event" compares
#: with the event's topics. ``None`` means the goal points at no topic, which is
#: a measured miss — except for :data:`UNDECIDED_CAREER_GOAL` on an exploratory
#: event (see :func:`goal_is_undecided`). OQ-CE-14, decided 2026-09-25, Ann
#: Wang, email reply to the team's question list.
CAREER_GOAL_TOPICS: Final[Mapping[str, str | None]] = MappingProxyType(
    {
        "Accounting or audit role (CPA path)": "Accounting / professional services",
        "Consulting role": "Consulting",
        "Media or entertainment business role": "Entertainment / sports / media",
        "Startup or small business role": "Entrepreneurship / startups",
        "Finance or real estate role": "Finance / banking / insurance / real estate",
        "Government or nonprofit role": "Government / nonprofit / public policy",
        "Healthcare administration role": "Healthcare administration",
        "Hospitality or events role": "Hospitality / tourism / events",
        "Marketing or brand role": "Marketing / advertising / public relations",
        "Retail or consumer goods role": "Retail / consumer goods",
        "Sales or business development role": "Sales / business development",
        "Supply chain or operations role": "Supply chain / logistics / operation",
        "Data, analytics or IT role": "Technology / information systems",
        "Start my own business": "Entrepreneurship / startups",
        "Undecided": None,
        "Graduate school": None,
    }
)

#: The sixteen career-goal labels, in the table's order.
EXERCISE_CAREER_GOALS: Final[tuple[str, ...]] = tuple(CAREER_GOAL_TOPICS)

#: The one career-goal label that half-fits an exploratory event (OQ-CE-14).
UNDECIDED_CAREER_GOAL: Final[str] = "Undecided"

#: Ann's event types, as her file spells them, and whether each is a broad
#: exploratory event (OQ-CE-14, decided 2026-09-25, Ann Wang, email reply to the
#: team's question list). See the module docstring for how her words map here.
EXERCISE_EVENT_TYPES: Final[Mapping[str, bool]] = MappingProxyType(
    {
        "Workshop": False,
        "Career fair": True,
        "Employer info session": True,
        "Industry panel": True,
        "Competition": False,
        "Networking": False,
        "Employer talk": True,
        "Employer talk (exercise event 1)": True,
        "Employer talk (exercise event 2)": True,
    }
)


def _index(terms: tuple[str, ...]) -> Mapping[str, str]:
    """Folded spelling to Ann's spelling, refusing a vocabulary that collides."""
    index = {normalize_tag_value(term): term for term in terms}
    if len(index) != len(terms):  # pragma: no cover - a build with this state cannot import
        raise RuntimeError("two vocabulary terms fold to the same key")
    return MappingProxyType(index)


_MAJORS: Final[Mapping[str, str]] = _index((*EXERCISE_MAJORS, ALL_MAJORS_LABEL))
_YEARS: Final[Mapping[str, str]] = _index(EXERCISE_CLASS_YEARS)
_TOPICS: Final[Mapping[str, str]] = _index(EXERCISE_TOPICS)
_GOALS: Final[Mapping[str, str]] = _index(EXERCISE_CAREER_GOALS)
_EVENT_TYPES: Final[Mapping[str, str]] = _index(tuple(EXERCISE_EVENT_TYPES))

if UNDECIDED_CAREER_GOAL not in CAREER_GOAL_TOPICS:  # pragma: no cover
    raise RuntimeError("the undecided career goal is not one of the career-goal labels")

if set(CAREER_GOAL_TOPICS.values()) - {None} - set(EXERCISE_TOPICS):  # pragma: no cover
    raise RuntimeError("a career goal points at a topic that is not in the topic list")


def _lookup(index: Mapping[str, str], text: str) -> str | None:
    """Ann's spelling of ``text``, or ``None`` when it is not in ``index``."""
    if not text.strip():
        return None
    try:
        return index.get(normalize_tag_value(text))
    except ValueError:
        # ``normalize_tag_value`` refuses a value that folds to nothing, such as
        # a cell of punctuation only. That is not a term either.
        return None


def canonical_major(text: str) -> str | None:
    """Ann's spelling of a major, or ``None``. Never returns :data:`ALL_MAJORS_LABEL`."""
    found = _lookup(_MAJORS, text)
    return None if found == ALL_MAJORS_LABEL else found


def is_all_majors(text: str) -> bool:
    """Whether a ``target_major`` cell says the event is for every major."""
    return _lookup(_MAJORS, text) == ALL_MAJORS_LABEL


def canonical_class_year(text: str) -> str | None:
    """Ann's spelling of a year, or ``None``."""
    return _lookup(_YEARS, text)


def canonical_topic(text: str) -> str | None:
    """Ann's spelling of a topic, or ``None``."""
    return _lookup(_TOPICS, text)


def canonical_career_goal(text: str) -> str | None:
    """Ann's spelling of a career-goal label, or ``None``."""
    return _lookup(_GOALS, text)


def canonical_event_type(text: str) -> str | None:
    """Ann's spelling of an event type, or ``None``."""
    return _lookup(_EVENT_TYPES, text)


def event_type_is_exploratory(event_type: str) -> bool:
    """Whether an event of this type is a broad exploratory event (OQ-CE-14).

    Args:
        event_type: An event type, in any spelling the fold accepts.

    Returns:
        ``True`` for a company talk, an industry panel or a career fair.

    Raises:
        KeyError: for a type that is not one of Ann's. Ingest refuses such a
            type, so only a caller holding text from somewhere else reaches
            this, and it decides what an unknown type means.
    """
    label = canonical_event_type(event_type)
    if label is None:
        raise KeyError("event type is not one of the exercise's event types")
    return EXERCISE_EVENT_TYPES[label]


def goal_is_undecided(career_goal: str | None) -> bool:
    """Whether a stored career goal is Ann's ``Undecided`` (OQ-CE-14).

    The flag the matching factor and the results rule read beside
    :func:`goal_topic_for_matching`, so the two agree on who is undecided. A
    goal stored before the vocabulary closed is compared as written and is
    never undecided, which is how it ranked when it was stored.
    """
    if career_goal is None:
        return False
    return canonical_career_goal(career_goal) == UNDECIDED_CAREER_GOAL


def career_goal_topic(career_goal: str) -> str | None:
    """The topic a career goal compares with an event's topics.

    Args:
        career_goal: A career-goal label, in any spelling the fold accepts.

    Returns:
        The topic from :data:`CAREER_GOAL_TOPICS`, or ``None`` for a goal that
        points at no topic (``Undecided``, ``Graduate school``).

    Raises:
        KeyError: for a label that is not one of the sixteen. Ingest refuses
            such a label, so only a caller holding text from somewhere else
            can reach this, and it decides what an unknown label means.
    """
    label = canonical_career_goal(career_goal)
    if label is None:
        raise KeyError("career goal is not one of the exercise's career-goal labels")
    return CAREER_GOAL_TOPICS[label]


def goal_topic_for_matching(career_goal: str | None) -> str | None:
    """What "career goal fits this event" compares, for a stored career goal.

    The one place a stored goal label becomes the topic the factor and the
    simulated-results rule compare with an event's topics, so the two cannot
    disagree about what a goal means.

    Args:
        career_goal: The label as stored, or ``None`` for no goal on file.

    Returns:
        The label's topic from :data:`CAREER_GOAL_TOPICS`; ``None`` for no goal
        or for a goal that points at no topic; and, for a label that is not one
        of the sixteen, the label itself. That last case is only reachable for
        a dataset stored before the vocabulary closed, which then ranks exactly
        as it did when it was stored: its goal compared as written.
    """
    if career_goal is None:
        return None
    try:
        return career_goal_topic(career_goal)
    except KeyError:
        return career_goal
