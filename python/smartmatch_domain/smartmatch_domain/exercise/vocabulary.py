"""The class exercise's closed vocabularies, as Ann's data file states them.

Ann's final file arrived on 2026-09-24 and its Read Me is the spec for every
value below: six majors, four years, one fixed list of thirteen topics ("the
same list as the 2026 Fall Career Readiness Survey"), and sixteen career-goal
labels. The owner ruled the same day that all four are **closed** in code: a
value outside them is refused at ingest with one plain sentence rather than
stored and compared as free text.

Every term is written **exactly as Ann spells it**. A cell is matched through
:func:`smartmatch_domain.events.normalize_tag_value` — the fold the CBA path
already uses — so ``"technology / Information Systems"`` finds its entry, and
the entry's own spelling is what is stored. ``Supply chain / logistics /
operation`` is singular in Ann's file and stays singular here.

PLACEHOLDER (Ann to confirm role→topic table)
=============================================
:data:`CAREER_GOAL_TOPICS` is the owner's ruling of 2026-09-24, not Ann's
statement. Thirteen labels are "<field> role" and map to their field, which is
what the file shows (each such profile's first true interest is that field);
``Start my own business`` maps to ``Entrepreneurship / startups``; and
``Undecided`` and ``Graduate school`` point at no topic, which scores a
*measured* ``0.0`` on "career goal fits this event", never unknown.
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
    "EXERCISE_MAJORS",
    "EXERCISE_TOPICS",
    "canonical_career_goal",
    "canonical_class_year",
    "canonical_major",
    "canonical_topic",
    "career_goal_topic",
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

#: PLACEHOLDER (Ann to confirm role→topic table). Each career-goal label, and
#: the topic "career goal fits this event" compares with the event's topics.
#: ``None`` means the goal points at no topic, which is a measured miss.
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
