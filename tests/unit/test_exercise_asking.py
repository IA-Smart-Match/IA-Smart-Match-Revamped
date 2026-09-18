"""Unit tests for the "asking for more" constants and share selector (§12)."""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
from smartmatch_domain.exercise.asking import (
    CARD_COMPLETION_SHARE,
    REQUIRED_NON_RESPONDING_SHARE,
    AskingChoice,
    select_share,
)

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "migrations"
    / "versions"
    / "0037_exercise_tables.py"
)


# --- The three names -------------------------------------------------------


def test_the_three_choices_are_exactly_the_ones_the_spec_names():
    assert [choice.value for choice in AskingChoice] == [
        "better_recommendations",
        "small_reward",
        "required",
    ]


def test_the_choice_values_match_the_database_check_constraint():
    """0037's ``ck_exercise_team_workspace_asking_choice`` is the other copy."""
    source = MIGRATION.read_text(encoding="utf-8")
    constraint = re.search(r"asking_choice IS NULL OR asking_choice IN \"\s*\"\(([^)]*)\)", source)
    assert constraint is not None, "the asking_choice check constraint moved"
    in_database = {value.strip().strip("'") for value in constraint.group(1).split(",")}
    assert in_database == {choice.value for choice in AskingChoice}


def test_a_choice_is_usable_as_a_string():
    assert AskingChoice.SMALL_REWARD == "small_reward"
    assert f"{AskingChoice.REQUIRED}" == "required"


# --- The placeholder shares ------------------------------------------------


def test_the_completion_shares_are_anns_build_table_numbers():
    assert CARD_COMPLETION_SHARE == {
        AskingChoice.BETTER_RECOMMENDATIONS: 0.30,
        AskingChoice.SMALL_REWARD: 0.55,
        AskingChoice.REQUIRED: 0.80,
    }


def test_every_choice_has_a_completion_share():
    assert set(CARD_COMPLETION_SHARE) == set(AskingChoice)


def test_the_required_non_responding_share_is_anns_number():
    assert REQUIRED_NON_RESPONDING_SHARE == 0.15


def test_the_completion_shares_cannot_be_retuned_at_runtime():
    with pytest.raises(TypeError):
        CARD_COMPLETION_SHARE[AskingChoice.REQUIRED] = 0.99  # type: ignore[index]


# --- select_share ----------------------------------------------------------


def test_the_same_call_twice_picks_the_same_profiles():
    profile_nos = tuple(range(1, 101))
    first = select_share(profile_nos, 0.30, seed=99, salt="card_completion")
    second = select_share(profile_nos, 0.30, seed=99, salt="card_completion")
    assert first == second


def test_the_order_of_the_input_does_not_matter():
    profile_nos = list(range(1, 101))
    straight = select_share(profile_nos, 0.55, seed=4, salt="card_completion")
    shuffler = random.Random(7)
    for _ in range(5):
        shuffler.shuffle(profile_nos)
        assert select_share(profile_nos, 0.55, seed=4, salt="card_completion") == straight


def test_duplicates_are_folded_into_one_profile():
    assert select_share([3, 3, 3, 9, 9], 1.0, seed=1, salt="x") == (3, 9)


def test_a_share_of_zero_picks_nobody():
    assert select_share(range(1, 101), 0.0, seed=1, salt="x") == ()


def test_a_share_of_one_picks_everybody():
    assert select_share(range(1, 101), 1.0, seed=1, salt="x") == tuple(range(1, 101))


def test_an_empty_group_picks_nobody():
    assert select_share((), 0.8, seed=1, salt="x") == ()


@pytest.mark.parametrize(("share", "expected"), [(0.30, 30), (0.55, 55), (0.80, 80), (0.15, 15)])
def test_the_count_is_the_rounded_share_of_the_group(share: float, expected: int):
    assert len(select_share(range(1, 101), share, seed=2, salt="x")) == expected


def test_the_result_is_sorted():
    picked = select_share(range(1, 101), 0.55, seed=8, salt="x")
    assert list(picked) == sorted(picked)


def test_two_salts_over_one_seed_pick_differently():
    completers = select_share(range(1, 201), 0.80, seed=3, salt="card_completion")
    silent = select_share(range(1, 201), 0.15, seed=3, salt="non_responding")
    assert set(silent) - set(completers) or set(completers) - set(silent)
    assert completers != silent


def test_two_seeds_generally_pick_differently():
    picks = {select_share(range(1, 201), 0.5, seed=seed, salt="x") for seed in range(6)}
    assert len(picks) > 1


def test_one_teams_pick_is_a_subset_shape_that_does_not_depend_on_group_size():
    """A profile's rank comes from its own number, not from its neighbours."""
    big = select_share(range(1, 201), 1.0, seed=5, salt="x")
    assert set(big) == set(range(1, 201))


@pytest.mark.parametrize("share", [-0.01, 1.01, 2.0, -1.0])
def test_a_share_outside_zero_to_one_is_refused(share: float):
    with pytest.raises(ValueError, match="between 0 and 1"):
        select_share(range(1, 10), share, seed=1, salt="x")
