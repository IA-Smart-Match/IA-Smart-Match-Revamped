"""The class exercise's closed vocabularies (owner ruling of 2026-09-24).

Pinned against Ann's own file where the file can answer, so a vocabulary that
drifts from what she sent fails here rather than as a refused upload in class.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from openpyxl import load_workbook
from smartmatch_domain.exercise import vocabulary
from smartmatch_domain.exercise.vocabulary import (
    ALL_MAJORS_LABEL,
    CAREER_GOAL_TOPICS,
    EXERCISE_CAREER_GOALS,
    EXERCISE_CLASS_YEAR_RANK,
    EXERCISE_CLASS_YEARS,
    EXERCISE_MAJORS,
    EXERCISE_TOPICS,
    canonical_career_goal,
    canonical_class_year,
    canonical_major,
    canonical_topic,
    career_goal_topic,
    goal_topic_for_matching,
    is_all_majors,
)

from tests.unit.exercise_workbooks import ANN_FULL_FILE


@cache
def _anns_profiles() -> tuple[dict[str, object], ...]:
    book = load_workbook(ANN_FULL_FILE, read_only=True, data_only=True)
    try:
        rows = list(book["Profiles"].iter_rows(values_only=True))
    finally:
        book.close()
    header = [str(cell) for cell in rows[0]]
    return tuple(dict(zip(header, row, strict=False)) for row in rows[1:] if any(row))


def _split(cell: object) -> list[str]:
    return [part for part in str(cell or "").split(";") if part]


def test_the_list_sizes_are_anns() -> None:
    assert (len(EXERCISE_MAJORS), len(EXERCISE_CLASS_YEARS)) == (6, 4)
    assert (len(EXERCISE_TOPICS), len(EXERCISE_CAREER_GOALS)) == (13, 16)


def test_every_value_in_anns_file_is_in_the_vocabulary_as_she_spells_it() -> None:
    profiles = _anns_profiles()

    assert {p["major"] for p in profiles} == set(EXERCISE_MAJORS)
    assert {p["year"] for p in profiles} == set(EXERCISE_CLASS_YEARS)
    topics = {
        topic
        for p in profiles
        for column in ("stated_interests", "hidden_true_interests")
        for topic in _split(p[column])
    }
    assert topics == set(EXERCISE_TOPICS)
    goals = {p["hidden_true_career_goal"] for p in profiles} | {
        p["stated_career_goal"] for p in profiles if p["stated_career_goal"]
    }
    assert goals == set(EXERCISE_CAREER_GOALS)


def test_supply_chain_stays_singular_as_ann_wrote_it() -> None:
    assert "Supply chain / logistics / operation" in EXERCISE_TOPICS
    assert canonical_topic("supply chain / logistics / operations") is None


def test_a_cell_is_matched_through_the_fold_and_answered_in_anns_spelling() -> None:
    assert canonical_topic("  technology /Information   SYSTEMS ") == (
        "Technology / information systems"
    )
    assert canonical_major("finance, real estate & law") == "Finance, Real Estate & Law"
    assert canonical_class_year("SENIOR") == "Senior"
    assert canonical_career_goal("data analytics or it role") == "Data, analytics or IT role"


@pytest.mark.parametrize("text", ["", "   ", "---", "Astronaut"])
def test_anything_else_is_not_a_term(text: str) -> None:
    assert canonical_topic(text) is None
    assert canonical_major(text) is None
    assert canonical_class_year(text) is None
    assert canonical_career_goal(text) is None


def test_all_majors_is_recognised_but_is_not_itself_a_major() -> None:
    assert is_all_majors("all MAJORS")
    assert canonical_major(ALL_MAJORS_LABEL) is None
    assert not is_all_majors("Accounting")


def test_the_year_order_is_seniors_first() -> None:
    ordered = sorted(EXERCISE_CLASS_YEAR_RANK, key=EXERCISE_CLASS_YEAR_RANK.__getitem__)
    assert ordered == ["Freshman", "Sophomore", "Junior", "Senior"]
    with pytest.raises(TypeError):
        EXERCISE_CLASS_YEAR_RANK["Senior"] = 0  # type: ignore[index]


def test_the_role_table_is_marked_as_a_placeholder_for_ann() -> None:
    source = Path(vocabulary.__file__).read_text(encoding="utf-8")
    assert "PLACEHOLDER (Ann to confirm role→topic table)" in source


def test_every_role_maps_to_the_first_true_interest_of_every_profile_with_it() -> None:
    """The owner's reading of the file, checked against every one of the 300 rows."""
    for profile in _anns_profiles():
        goal = str(profile["hidden_true_career_goal"])
        if goal in {"Undecided", "Graduate school", "Start my own business"}:
            continue
        assert CAREER_GOAL_TOPICS[goal] == _split(profile["hidden_true_interests"])[0], goal


def test_the_three_goals_that_are_not_roles_follow_the_owners_ruling() -> None:
    assert career_goal_topic("Start my own business") == "Entrepreneurship / startups"
    assert career_goal_topic("Undecided") is None
    assert career_goal_topic("Graduate school") is None


def test_an_unknown_goal_is_refused_by_the_table_lookup() -> None:
    with pytest.raises(KeyError):
        career_goal_topic("Astronaut")


def test_goal_topic_for_matching_maps_a_label_and_keeps_a_legacy_goal_as_written() -> None:
    assert goal_topic_for_matching(None) is None
    assert goal_topic_for_matching("Undecided") is None
    assert goal_topic_for_matching("Data, analytics or IT role") == (
        "Technology / information systems"
    )
    # A dataset stored before the vocabulary closed ranks as it did.
    assert goal_topic_for_matching("analytics") == "analytics"


@pytest.mark.parametrize("goal", ["Undecided", "Graduate school"])
def test_a_goal_that_points_at_no_topic_is_a_measured_miss_not_unknown(goal: str) -> None:
    """Owner ruling 2: measured 0.0, through the API's own row-to-evidence step."""
    from smartmatch_api.exercise_dependencies import ExerciseEventRow, TeamProfileRow
    from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
    from smartmatch_domain.student_factors import career_goal_fit

    row = TeamProfileRow(
        profile_no=1,
        display_name="Fictional One",
        major="Accounting",
        class_year="Senior",
        past_event_keys=(),
        stated_interests=("Consulting",),
        career_goal=goal,
        overlay_added_event_topics=(),
        overlay_card_interests=None,
        overlay_card_career_goal=None,
        non_responding=False,
    )
    event = ExerciseEventRow(
        event_key="E11",
        name="Northline (fictional)",
        topic_tags=("Technology / information systems",),
        target_majors=("Computer Information Systems",),
        is_exercise_event=True,
        sequence=11,
    )

    evidence = rankable_set((row,), (event,)).profiles[0].evidence
    fit = career_goal_fit(evidence, event_evidence(event))

    assert fit.value == 0.0
    assert not fit.is_unknown


def test_the_results_rule_reads_the_hidden_goals_topic() -> None:
    """``simulation_profiles`` turns the hidden goal into the topic the rule compares."""
    from smartmatch_api.exercise_dependencies import SimulationProfileRow
    from smartmatch_api.routers.exercise_results_models import simulation_profiles

    rows = (
        SimulationProfileRow(
            profile_no=1,
            display_name="Fictional One",
            major="Accounting",
            class_year="Senior",
            past_event_keys=(),
            stated_interests=None,
            career_goal="Undecided",
            hidden_true_interests=("Consulting",),
            hidden_true_career_goal="Data, analytics or IT role",
        ),
    )

    (profile,) = simulation_profiles(rows, non_responding_profile_nos=frozenset())

    assert profile.career_goal == "Technology / information systems"
    assert "Technology" not in repr(profile), "derived from a withheld column"
