"""Unit tests for the "asking for more" constants and share selector (§12)."""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any, cast

import pytest
from smartmatch_domain.exercise import asking
from smartmatch_domain.exercise.asking import (
    CARD_COMPLETION_SHARE,
    COPIED_CARD_CAREER_GOAL,
    REQUIRED_NON_RESPONDING_SHARE,
    AskingChoice,
    CopiedCardCareerGoal,
    copied_card_career_goal,
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


# --- The copied card's career goal (OQ-CE-13) ------------------------------


def test_the_shipped_policy_is_anns_answer():
    """A new card copies the hidden true career goal (Ann's data file, 2026-09-24)."""
    assert COPIED_CARD_CAREER_GOAL is CopiedCardCareerGoal.HIDDEN_GOAL


def test_the_policy_constant_is_no_longer_a_placeholder():
    """OQ-CE-13 is closed; the constant must not still say it is open."""
    source = Path(asking.__file__).read_text(encoding="utf-8")
    marker = source.index("COPIED_CARD_CAREER_GOAL: Final")
    assert "PLACEHOLDER (OQ-CE-13)" not in source
    assert "OQ-CE-13 closed" in source[:marker]


def test_the_policy_has_the_three_readings_that_were_argued():
    assert {member.value for member in CopiedCardCareerGoal} == {
        "base_goal",
        "none",
        "hidden_goal",
    }


@pytest.mark.parametrize("hidden", ["Data, analytics or IT role", None])
def test_under_hidden_goal_the_copied_card_carries_the_hidden_goal(hidden: str | None):
    assert (
        copied_card_career_goal(
            "Undecided", CopiedCardCareerGoal.HIDDEN_GOAL, hidden_true_career_goal=hidden
        )
        == hidden
    )


def test_the_default_reads_the_hidden_goal_and_ignores_the_base():
    assert copied_card_career_goal(None, hidden_true_career_goal="Consulting role") == (
        "Consulting role"
    )


@pytest.mark.parametrize("base", ["analytics", "brand", ""])
def test_under_base_goal_the_copied_card_carries_the_base_goal(base: str):
    assert copied_card_career_goal(base, CopiedCardCareerGoal.BASE_GOAL) == base


def test_under_base_goal_a_base_with_no_goal_carries_none():
    """``NULL`` only when the base has none — the second half of the ruling."""
    assert copied_card_career_goal(None, CopiedCardCareerGoal.BASE_GOAL) is None


@pytest.mark.parametrize("base", ["analytics", None, ""])
def test_under_none_the_copied_card_carries_nothing(base: str | None):
    assert copied_card_career_goal(base, CopiedCardCareerGoal.NONE) is None


@pytest.mark.parametrize("base", ["analytics", None])
def test_the_default_is_the_module_constant(base: str | None):
    assert copied_card_career_goal(base) == copied_card_career_goal(base, COPIED_CARD_CAREER_GOAL)


def test_every_member_is_answered_rather_than_falling_through():
    """A third member added without a branch must not silently mean ``NONE``.

    The membership assertion is the half that can actually fail when somebody
    adds a member: without it this test just reads the two it already knows
    about and stays green while a third falls through.
    """
    answers = {
        member: copied_card_career_goal("analytics", member, hidden_true_career_goal="true")
        for member in CopiedCardCareerGoal
    }
    assert set(answers) == {
        CopiedCardCareerGoal.BASE_GOAL,
        CopiedCardCareerGoal.NONE,
        CopiedCardCareerGoal.HIDDEN_GOAL,
    }, "a member was added; give it a branch in copied_card_career_goal and a case here"
    assert answers[CopiedCardCareerGoal.BASE_GOAL] == "analytics"
    assert answers[CopiedCardCareerGoal.NONE] is None
    assert answers[CopiedCardCareerGoal.HIDDEN_GOAL] == "true"


def test_a_policy_that_is_not_a_member_is_refused_rather_than_answered():
    """The fall-through F1 fixed: an unknown policy must raise, not mean ``NONE``.

    A member added without a branch arrives here as a value ``match`` does not
    cover, and the wrong answer — silently carrying no goal — is the one that
    looks like a deliberate reading. ``assert_never`` raises ``AssertionError``,
    not ``ValueError`` — the point of using it over a hand-rolled raise is that
    mypy also flags an unhandled member statically.
    """
    with pytest.raises(AssertionError, match="stated_interest"):
        copied_card_career_goal("analytics", cast(Any, "stated_interest"))


def test_the_refusal_names_the_policy_and_nothing_else():
    """No base career goal in the message: it is a data-file value."""
    with pytest.raises(AssertionError) as refused:
        copied_card_career_goal("a-private-goal", cast(Any, "stated_interest"))

    assert "a-private-goal" not in str(refused.value)


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


def test_the_rank_key_separates_fields_that_a_naive_join_would_merge():
    """``1 + "a:2"`` and ``1 + "a"`` + ``2`` both join to ``"1:a:2"``."""
    from smartmatch_domain.exercise import asking

    assert asking._rank_key(1, "a:2", 3)[0] != asking._rank_key(1, "a", 23)[0]
    assert asking._rank_key(1, "a:b", 3)[0] != asking._rank_key(1, "a", 3)[0]


def test_salts_containing_a_colon_are_ordinary_salts():
    first = select_share(range(1, 101), 0.5, seed=1, salt="round:1")
    second = select_share(range(1, 101), 0.5, seed=1, salt="round:2")
    again = select_share(range(1, 101), 0.5, seed=1, salt="round:1")
    assert first != second
    assert first == again
