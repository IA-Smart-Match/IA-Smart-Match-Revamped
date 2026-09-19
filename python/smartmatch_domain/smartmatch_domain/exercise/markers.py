""""How much we know", and "who is on the list" (requirements; design spec §7).

Two things Janice's screens need and nothing else does:

**The marker.** Next to every profile, one of three words: major only, major
plus events attended, completed card. Derived — never stored, never typed by a
caller — from the same three-state evidence the factors read, so a profile
cannot be labelled "completed card" on one screen and score unknown on the
card-fed factors on another.

The rule follows the pattern :mod:`smartmatch_domain.match_depth` sets: absent
information is unknown, and **an empty card is not the same as no card**. A
card with nothing written on it is still a completed card — the person
answered — and its factors score a measured zero. A profile with an attendance
record naming no event is "major only", because there is no event whose topics
could be compared; the record's existence is still preserved on the evidence.

**The counts.** For the current list, counts by major, by class year, and by
marker, each beside the same count over every profile. Counts are not scores:
ADR-0025 D8 forbids a number that ranks a person, and "eleven Finance majors
on this list" ranks nobody.

The empty-group notice is **not** re-implemented here. It already exists as
:func:`smartmatch_domain.exercise_list_coverage.find_uncovered_groups`, and
:func:`list_composition` composes it rather than deriving the same answer a
second way.

**PLACEHOLDER (OQ-CE-01).** No vocabulary of majors and no vocabulary of class
years: every label arrives as data and is counted under the spelling it
arrived with.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from smartmatch_domain.exercise_list_coverage import (
    GroupValues,
    ListCoverage,
    find_uncovered_groups,
)
from smartmatch_domain.student_factors import ProfileEvidence

__all__ = [
    "INFORMATION_RANK",
    "GroupCounts",
    "InformationMarker",
    "ListComposition",
    "derive_marker",
    "information_rank",
    "list_composition",
]


class InformationMarker(StrEnum):
    """How much is on file about one profile, in Ann's three groups."""

    #: Nothing but the major (and the year, which every profile has).
    MAJOR_ONLY = "major_only"
    #: The major, plus at least one past event attended.
    MAJOR_PLUS_EVENTS = "major_plus_events"
    #: A profile card exists, however little is written on it.
    COMPLETED_CARD = "completed_card"


#: Design spec §4.4's ``info_rank``: 2 for a completed card, 1 for major plus
#: events, 0 for major only. Declared as a table beside the enum rather than as
#: three literals inside the tie-break, so "more information on file first" has
#: exactly one definition.
INFORMATION_RANK: Final[Mapping[InformationMarker, int]] = MappingProxyType(
    {
        InformationMarker.COMPLETED_CARD: 2,
        InformationMarker.MAJOR_PLUS_EVENTS: 1,
        InformationMarker.MAJOR_ONLY: 0,
    }
)


def derive_marker(profile: ProfileEvidence) -> InformationMarker:
    """Which of the three groups a profile is in.

    Args:
        profile: The profile's evidence.

    Returns:
        :attr:`InformationMarker.COMPLETED_CARD` when a card exists, whatever
        is written on it; :attr:`InformationMarker.MAJOR_PLUS_EVENTS` when no
        card exists but at least one past event was attended; otherwise
        :attr:`InformationMarker.MAJOR_ONLY`. A profile with an attendance
        record that names no event, and a profile with no attendance record at
        all, are both "major only" — neither has an event to say anything
        about — and the difference between them stays on the evidence.
    """
    if profile.card is not None:
        return InformationMarker.COMPLETED_CARD
    if profile.attended_event_count:
        return InformationMarker.MAJOR_PLUS_EVENTS
    return InformationMarker.MAJOR_ONLY


def information_rank(marker: InformationMarker) -> int:
    """The tie-break's ``info_rank`` for one marker. Higher sorts first."""
    return INFORMATION_RANK[marker]


@dataclass(frozen=True, slots=True)
class GroupCounts:
    """One dimension's counts, for the list and for every profile.

    Attributes:
        dimension: What is being counted by, in the caller's own words.
        on_list: ``{label: count}`` over the current ranked list.
        all_profiles: ``{label: count}`` over every profile in the dataset.
    """

    dimension: str
    on_list: Mapping[str, int]
    all_profiles: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ListComposition:
    """The "who is on the list" table, beside the notice behind it.

    Attributes:
        by_major: Counts by major.
        by_class_year: Counts by class year.
        by_marker: Counts by "how much we know" group. Every marker appears,
            including one no profile is in, so the table has three rows
            whatever the data holds.
        coverage: Which majors and class years exist among every profile and
            have nobody on the list —
            :func:`~smartmatch_domain.exercise_list_coverage.find_uncovered_groups`,
            composed rather than re-derived.
    """

    by_major: GroupCounts
    by_class_year: GroupCounts
    by_marker: GroupCounts
    coverage: ListCoverage


def _counted(labels: Sequence[str], *, seed: Sequence[str] = ()) -> Mapping[str, int]:
    """Count labels, keeping first-appearance order and any seeded rows."""
    counts: dict[str, int] = {label: 0 for label in seed}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return MappingProxyType(counts)


def list_composition(
    listed: Sequence[tuple[str, str, InformationMarker]],
    everyone: Sequence[tuple[str, str, InformationMarker]],
) -> ListComposition:
    """Counts for the current list beside the same counts for every profile.

    Args:
        listed: One ``(major, class_year, marker)`` triple per profile on the
            current ranked list.
        everyone: The same, one per profile in the whole dataset.

    Returns:
        A :class:`ListComposition`. No share, percentage, or score is computed
        — the screen puts the two counts side by side and the reader does the
        comparing (ADR-0025 D8).
    """
    marker_labels = tuple(str(marker) for marker in InformationMarker)
    listed_majors = [major for major, _, _ in listed]
    listed_years = [year for _, year, _ in listed]
    all_majors = [major for major, _, _ in everyone]
    all_years = [year for _, year, _ in everyone]

    return ListComposition(
        by_major=GroupCounts(
            dimension="major",
            on_list=_counted(listed_majors),
            all_profiles=_counted(all_majors),
        ),
        by_class_year=GroupCounts(
            dimension="class_year",
            on_list=_counted(listed_years),
            all_profiles=_counted(all_years),
        ),
        by_marker=GroupCounts(
            dimension="marker",
            on_list=_counted([str(marker) for _, _, marker in listed], seed=marker_labels),
            all_profiles=_counted([str(marker) for _, _, marker in everyone], seed=marker_labels),
        ),
        coverage=find_uncovered_groups(
            majors=GroupValues(
                dimension="major",
                all_profiles=tuple(all_majors),
                on_list=tuple(listed_majors),
            ),
            class_years=GroupValues(
                dimension="class_year",
                all_profiles=tuple(all_years),
                on_list=tuple(listed_years),
            ),
        ),
    )
