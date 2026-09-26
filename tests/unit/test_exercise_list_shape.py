"""No numeric score reaches a class participant (ADR-0025 D8, design spec §4.6).

The rule is easy to state and easy to break by accident: a later card adds a
``value`` to the list entry "just for debugging", and a percentage appears on
the projector. So the outward types are walked by field, by annotation, and by
constructed instance, rather than reviewed.

``rank`` and ``invite_limit`` are integers and are deliberately allowed: a
position in a list and a cap the instructor set are not measurements of a
person. What is refused is a float anywhere, and any field whose *name* would
read as a score.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest
from smartmatch_domain.exercise.markers import InformationMarker
from smartmatch_domain.exercise.matching import (
    ExerciseList,
    ExerciseListEntry,
    ExerciseProfile,
    exercise_ranked_list,
)
from smartmatch_domain.student_factors import ProfileCard, ProfileEvidence
from smartmatch_domain.student_factors.evidence import EventEvidence

#: Any field whose name contains one of these reads as a measurement of a
#: person, whatever its type.
FORBIDDEN_FRAGMENTS = (
    "score",
    "value",
    "weight",
    "confidence",
    "percent",
    "pct",
    "rating",
    "probability",
)

OUTWARD_TYPES = (ExerciseListEntry, ExerciseList)

EVENT = EventEvidence(
    event_key="northline",
    topic_tags=("analytics", "careers"),
    target_majors=("Marketing",),
)
TEST_ONLY_YEAR_RANK = {"Senior": 2, "Junior": 1}


@pytest.mark.parametrize("outward", OUTWARD_TYPES)
def test_no_outward_field_is_named_like_a_score(outward: type) -> None:
    for field in dataclasses.fields(outward):
        lowered = field.name.lower()
        for fragment in FORBIDDEN_FRAGMENTS:
            assert fragment not in lowered, f"{outward.__name__}.{field.name}"


@pytest.mark.parametrize("outward", OUTWARD_TYPES)
def test_no_outward_field_is_annotated_as_a_float(outward: type) -> None:
    hints = typing.get_type_hints(outward)
    for name, annotation in hints.items():
        flattened = str(annotation)
        assert "float" not in flattened, f"{outward.__name__}.{name}: {flattened}"


def _listing() -> ExerciseList:
    profiles = [
        ExerciseProfile(
            1,
            "Senior",
            ProfileEvidence(
                "rich",
                "Marketing",
                card=ProfileCard(("analytics",), career_goal="analytics"),
                attended_event_topics=(("analytics",),),
            ),
        ),
        ExerciseProfile(2, "Junior", ProfileEvidence("thin", "Marketing")),
    ]
    return exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=30,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum="sha256:testonly0001",
    )


def _walk(value: object) -> list[object]:
    """Every leaf reachable from a constructed outward value."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        leaves: list[object] = []
        for field in dataclasses.fields(value):
            leaves.extend(_walk(getattr(value, field.name)))
        return leaves
    if isinstance(value, tuple | list):
        leaves = []
        for item in value:
            leaves.extend(_walk(item))
        return leaves
    if isinstance(value, dict):
        leaves = []
        for item in value.values():
            leaves.extend(_walk(item))
        return leaves
    return [value]


def test_a_constructed_list_carries_no_float_anywhere() -> None:
    for leaf in _walk(_listing()):
        assert not isinstance(leaf, float), leaf


def test_a_constructed_list_carries_no_percentage_in_any_sentence() -> None:
    for entry in _listing().entries:
        assert "%" not in entry.reason
        assert not any(character.isdigit() for character in entry.reason)


def test_the_outward_entry_carries_section_4_6s_things_plus_one_display_flag() -> None:
    """Section 4.6's fields, plus ``undecided_goal_half`` (wave 3, CE chip).

    The extra field is a display hint for the reason chip: a boolean saying the
    career goal counted only as an undecided goal's half. It is not a score, a
    share or a rank (ADR-0025 D8), and it carries no hidden value (D6) — it is
    derived from the card the team can already see. Anything else added here
    has to make the same case.
    """
    names = {field.name for field in dataclasses.fields(ExerciseListEntry)}
    assert names == {
        "rank",
        "profile_id",
        "marker",
        "reason",
        "contributing_factor_keys",
        "undecided_goal_half",
    }
    for entry in _listing().entries:
        assert isinstance(entry.undecided_goal_half, bool)


def test_the_marker_leaves_as_one_of_the_three_words() -> None:
    for entry in _listing().entries:
        assert entry.marker in set(InformationMarker)
        assert str(entry.marker) in {
            "major_only",
            "major_plus_events",
            "completed_card",
        }
