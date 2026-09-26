"""Under "required", nobody both completes a card and stops answering.

Owner ruling, 2026-09-25: the card completers and the non-responders are two
separate groups. The M1 full-class run found the overlap on main: team 3's
P24 and team 6's P208, P213 and P259 were in both, because the two groups were
drawn independently from the same pool of invited profiles with no card.

The non-responders are now drawn only from the no-card profiles that did not
complete a card. The count is unchanged: 15% of *all* no-card profiles, a half
rounding up. The shares allow it — 80% + 15% never needs more people than the
pool holds — and a test below walks every pool size a class can produce.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest
from smartmatch_api.routers.exercise_results_refresh import refresh_plan
from smartmatch_domain.exercise.asking import (
    CARD_COMPLETION_SHARE,
    REQUIRED_NON_RESPONDING_SHARE,
    AskingChoice,
    select_share,
)


def _half_up(share: float, size: int) -> int:
    exact = Decimal(str(share)) * size
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _plan(size: int, seed: int, choice: AskingChoice = AskingChoice.REQUIRED) -> object:
    return refresh_plan(
        choice=choice,
        seed=seed,
        attended_profile_nos=(),
        no_card_profile_nos=tuple(range(1, size + 1)),
    )


@pytest.mark.parametrize("seed", [1, 7, 2**40 + 3])
def test_no_profile_both_completes_a_card_and_stops_answering(seed: int) -> None:
    for size in range(0, 301):
        plan = _plan(size, seed)
        both = set(plan.card_completers) & set(plan.non_responding)  # type: ignore[attr-defined]
        assert both == set(), (size, sorted(both))


@pytest.mark.parametrize("seed", [1, 7, 2**40 + 3])
def test_the_counts_still_match_the_shares_of_every_no_card_profile(seed: int) -> None:
    completion = CARD_COMPLETION_SHARE[AskingChoice.REQUIRED]
    for size in range(0, 301):
        plan = _plan(size, seed)
        assert len(plan.card_completers) == _half_up(completion, size), size  # type: ignore[attr-defined]
        assert len(plan.non_responding) == _half_up(  # type: ignore[attr-defined]
            REQUIRED_NON_RESPONDING_SHARE, size
        ), size


def test_both_groups_come_from_the_no_card_profiles() -> None:
    plan = refresh_plan(
        choice=AskingChoice.REQUIRED,
        seed=11,
        attended_profile_nos=(),
        no_card_profile_nos=(24, 208, 213, 259, 300, 5, 17, 99, 101, 150),
    )
    pool = {24, 208, 213, 259, 300, 5, 17, 99, 101, 150}
    assert set(plan.card_completers) <= pool
    assert set(plan.non_responding) <= pool


def test_the_plan_is_the_same_every_time_for_one_seed() -> None:
    assert _plan(30, 4242) == _plan(30, 4242)


def test_the_non_responders_depend_on_the_seed() -> None:
    picks = {_plan(30, seed).non_responding for seed in range(1, 21)}  # type: ignore[attr-defined]
    assert len(picks) > 1


@pytest.mark.parametrize("choice", [AskingChoice.BETTER_RECOMMENDATIONS, AskingChoice.SMALL_REWARD])
def test_only_required_has_non_responders(choice: AskingChoice) -> None:
    assert _plan(30, 3, choice).non_responding == ()  # type: ignore[attr-defined]


def test_select_share_can_count_against_a_larger_group() -> None:
    """15% of all ten no-card profiles is two, drawn from the two left over."""
    picked = select_share((9, 10), 0.15, seed=1, salt="non_responding", of_size=10)
    assert picked == (9, 10)


def test_select_share_refuses_a_count_the_pool_cannot_supply() -> None:
    with pytest.raises(ValueError, match="only 1"):
        select_share((9,), 0.15, seed=1, salt="non_responding", of_size=10)


def test_select_share_refuses_a_group_smaller_than_its_pool() -> None:
    with pytest.raises(ValueError, match="of_size"):
        select_share((1, 2, 3), 0.5, seed=1, salt="x", of_size=2)


@pytest.mark.parametrize("size", [0, 1, 2, 4, 5, 6, 7, 10, 11, 12, 17])
def test_small_pools_where_the_two_roundings_both_go_up_still_fit(size: int) -> None:
    """The sizes where 80% and 15% both round up are the ones that could overflow.

    Named one by one so a change to either share shows which pool broke. Every
    size from 0 to 300 is walked by the tests above as well.
    """
    for seed in range(1, 51):
        plan = _plan(size, seed)
        completers = set(plan.card_completers)  # type: ignore[attr-defined]
        silent = set(plan.non_responding)  # type: ignore[attr-defined]
        assert completers.isdisjoint(silent), (size, seed)
        assert completers | silent <= set(range(1, size + 1)), (size, seed)
