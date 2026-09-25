"""Unit tests for the class exercise's simulated-results rule (ADR-0025 D7).

Every coefficient set constructed in this file is **test-only**; these exist to
exercise the shape of the rule, and none of them is a proposal for Ann. The set
the module ships (OQ-CE-03, still OPEN) is read, never constructed, by the
tests under "the shipped set".
"""

from __future__ import annotations

import dataclasses
import math
import random

import pytest
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.simulation import (
    EVENT_SEATS,
    EXERCISE_SIMULATION_COEFFICIENTS,
    EXISTING_SIGNUPS,
    CoefficientsNotConfirmedError,
    InviteLimitExceededError,
    SimulationCoefficients,
    SimulationCoefficientsError,
    SimulationEvent,
    SimulationProfile,
    SimulationResult,
    _fit_share,
    require_coefficients,
    run_email_everyone,
    seats_empty,
    simulate_results,
)

# --- Test-only coefficients (NOT a proposal for OQ-CE-03) ------------------

TEST_ONLY_COEFFICIENTS = SimulationCoefficients(
    base_signup_rate=0.10,
    true_fit_lift=0.60,
    frequent_attender_lift=0.05,
    same_major_lift=0.08,
    chance_spread=0.10,
    attend_given_signup=0.90,
    frequent_attender_events=3,
    true_interest_share_of_fit=0.5,
)

EVENT = SimulationEvent(
    event_key="northline",
    topic_tags=frozenset({"analytics", "data_career"}),
    target_majors=frozenset({"marketing"}),
)


def _true_fit_profile(profile_no: int) -> SimulationProfile:
    """A profile whose hidden interests and career goal both fit the event."""
    return SimulationProfile(
        profile_no=profile_no,
        major="history",
        true_interests=frozenset({"analytics"}),
        career_goal="data_career",
    )


def _same_major_only_profile(profile_no: int) -> SimulationProfile:
    """A profile in the target major with nothing true that fits."""
    return SimulationProfile(
        profile_no=profile_no,
        major="marketing",
        true_interests=frozenset({"theatre"}),
        career_goal="stage_career",
    )


def _mixed_list() -> tuple[SimulationProfile, ...]:
    """A small invited list with every branch of the rule represented."""
    return (
        _true_fit_profile(1),
        _same_major_only_profile(2),
        SimulationProfile(profile_no=3, major="history", past_event_count=9),
        SimulationProfile(profile_no=4, major="history", career_goal=None),
        SimulationProfile(
            profile_no=5,
            major="marketing",
            true_interests=frozenset({"analytics"}),
            non_responding=True,
        ),
    )


# --- Determinism -----------------------------------------------------------


def test_same_inputs_twice_give_the_same_result():
    profiles = _mixed_list()
    first = simulate_results(
        profiles, EVENT, seed=4242, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    second = simulate_results(
        profiles, EVENT, seed=4242, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    assert first == second


def test_permuting_the_invited_list_changes_nothing():
    profiles = list(_mixed_list())
    straight = simulate_results(
        tuple(profiles), EVENT, seed=77, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    shuffler = random.Random(0)
    for _ in range(5):
        shuffler.shuffle(profiles)
        assert (
            simulate_results(
                tuple(profiles),
                EVENT,
                seed=77,
                coefficients=TEST_ONLY_COEFFICIENTS,
                invite_limit=30,
            )
            == straight
        )


def test_other_invitees_do_not_change_a_given_profiles_outcome():
    alone = simulate_results(
        (_true_fit_profile(11),),
        EVENT,
        seed=9,
        coefficients=TEST_ONLY_COEFFICIENTS,
        invite_limit=30,
    )
    crowded = simulate_results(
        (_true_fit_profile(11), *(_same_major_only_profile(n) for n in range(20, 40))),
        EVENT,
        seed=9,
        coefficients=TEST_ONLY_COEFFICIENTS,
        invite_limit=30,
    )
    assert (11 in alone.signed_up) == (11 in crowded.signed_up)
    assert (11 in alone.attended) == (11 in crowded.attended)


def test_a_team_list_and_email_everyone_agree_on_a_shared_profile():
    everyone = tuple(_true_fit_profile(n) for n in range(1, 200))
    panel = run_email_everyone(everyone, EVENT, seed=5, coefficients=TEST_ONLY_COEFFICIENTS)
    team = simulate_results(
        everyone[:25], EVENT, seed=5, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    shared = set(team.invited)
    assert set(team.signed_up) == {n for n in panel.signed_up if n in shared}
    assert set(team.attended) == {n for n in panel.attended if n in shared}


def test_a_different_seed_generally_gives_a_different_result():
    everyone = tuple(_true_fit_profile(n) for n in range(1, 200))
    results = {
        run_email_everyone(
            everyone, EVENT, seed=seed, coefficients=TEST_ONLY_COEFFICIENTS
        ).signed_up
        for seed in range(6)
    }
    assert len(results) > 1


def test_a_different_event_key_gives_a_different_draw():
    everyone = tuple(_true_fit_profile(n) for n in range(1, 200))
    harbor = dataclasses.replace(EVENT, event_key="harbor")
    northline = run_email_everyone(everyone, EVENT, seed=5, coefficients=TEST_ONLY_COEFFICIENTS)
    other = run_email_everyone(everyone, harbor, seed=5, coefficients=TEST_ONLY_COEFFICIENTS)
    assert northline.signed_up != other.signed_up


# --- The five behaviours ---------------------------------------------------


def test_true_fit_profiles_sign_up_far_more_often_than_same_major_only_ones():
    """Behaviour (1) against behaviour (3), over a few hundred profiles."""
    true_fit = tuple(_true_fit_profile(n) for n in range(1, 301))
    same_major = tuple(_same_major_only_profile(n) for n in range(301, 601))
    fit_rate = (
        len(
            run_email_everyone(
                true_fit, EVENT, seed=31337, coefficients=TEST_ONLY_COEFFICIENTS
            ).signed_up
        )
        / 300
    )
    major_rate = (
        len(
            run_email_everyone(
                same_major, EVENT, seed=31337, coefficients=TEST_ONLY_COEFFICIENTS
            ).signed_up
        )
        / 300
    )
    # Expected rates are about 0.70 and 0.18; a 0.25 margin is far wider than
    # any sampling wobble at a fixed seed, so this cannot flake.
    assert fit_rate - major_rate > 0.25


def test_a_frequent_attender_gets_less_lift_than_a_true_fit_profile():
    """Behaviour (2): only a little more likely."""
    attender = tuple(
        SimulationProfile(profile_no=n, major="history", past_event_count=9) for n in range(1, 301)
    )
    true_fit = tuple(_true_fit_profile(n) for n in range(1, 301))
    attender_rate = len(
        run_email_everyone(attender, EVENT, seed=555, coefficients=TEST_ONLY_COEFFICIENTS).signed_up
    )
    fit_rate = len(
        run_email_everyone(true_fit, EVENT, seed=555, coefficients=TEST_ONLY_COEFFICIENTS).signed_up
    )
    assert fit_rate > attender_rate


def test_non_responding_profiles_never_sign_up():
    """Behaviour from §13's round two, enforced here."""
    profiles = tuple(
        dataclasses.replace(_true_fit_profile(n), non_responding=True) for n in range(1, 201)
    )
    result = run_email_everyone(profiles, EVENT, seed=12, coefficients=TEST_ONLY_COEFFICIENTS)
    assert result.signed_up == ()
    assert result.attended == ()
    assert len(result.invited) == 200


def test_the_seed_is_the_only_per_team_state():
    """Behaviour (5): one team's reset is another team's business."""
    profiles = _mixed_list()
    before = simulate_results(
        profiles, EVENT, seed=1, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    simulate_results(profiles, EVENT, seed=2, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30)
    after = simulate_results(
        profiles, EVENT, seed=1, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    assert before == after


# --- Output shape ----------------------------------------------------------


def test_attended_is_a_subset_of_signed_up_is_a_subset_of_invited():
    everyone = tuple(_true_fit_profile(n) for n in range(1, 300))
    result = run_email_everyone(everyone, EVENT, seed=808, coefficients=TEST_ONLY_COEFFICIENTS)
    assert set(result.attended) <= set(result.signed_up) <= set(result.invited)


@pytest.mark.parametrize("field", ["invited", "signed_up", "attended"])
def test_every_output_tuple_is_sorted_and_deduplicated(field: str):
    duplicated = (_true_fit_profile(4), _true_fit_profile(4), _true_fit_profile(2))
    result = simulate_results(
        duplicated, EVENT, seed=3, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    values = getattr(result, field)
    assert list(values) == sorted(set(values))


def test_no_output_field_can_carry_true_interests():
    """ADR-0025 D6: the rule reads hidden interests and returns numbers."""
    for field in dataclasses.fields(SimulationResult):
        assert field.name not in EXERCISE_WITHHELD_FIELDS
        assert "interest" not in field.name
        assert field.type in {"tuple[int, ...]"}


def test_the_result_carries_no_number_that_looks_like_a_score():
    """ADR-0025 D8."""
    names = {field.name for field in dataclasses.fields(SimulationResult)}
    assert not {n for n in names if "score" in n or "rate" in n or "probability" in n}


def test_the_result_is_frozen():
    result = simulate_results(
        _mixed_list(), EVENT, seed=1, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.invited = ()  # type: ignore[misc]


# --- Unknown is not a mismatch (ADR-0011) ----------------------------------


def test_a_missing_career_goal_is_not_a_penalty():
    """A profile with no goal scores exactly a profile whose goal is unrelated."""
    without = SimulationProfile(
        profile_no=1, major="history", true_interests=frozenset({"analytics"})
    )
    unrelated = dataclasses.replace(without, career_goal="stage_career")
    a = simulate_results(
        (without,), EVENT, seed=6, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    b = simulate_results(
        (unrelated,), EVENT, seed=6, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )
    assert a == b


def test_terms_are_compared_after_trimming_and_case_folding():
    shouted = SimulationProfile(
        profile_no=1,
        major="  MARKETING ",
        true_interests=frozenset({" Analytics "}),
        career_goal="DATA_CAREER",
    )
    quiet = SimulationProfile(
        profile_no=1,
        major="marketing",
        true_interests=frozenset({"analytics"}),
        career_goal="data_career",
    )
    assert simulate_results(
        (shouted,), EVENT, seed=6, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    ) == simulate_results(
        (quiet,), EVENT, seed=6, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
    )


# --- Invite limit ----------------------------------------------------------


def test_a_list_longer_than_the_invite_limit_is_refused_in_plain_words():
    profiles = tuple(_true_fit_profile(n) for n in range(1, 32))
    with pytest.raises(InviteLimitExceededError) as excinfo:
        simulate_results(
            profiles, EVENT, seed=1, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
        )
    assert "31 profiles" in str(excinfo.value)
    assert "invite limit is 30" in str(excinfo.value)


def test_a_list_exactly_at_the_invite_limit_is_allowed():
    profiles = tuple(_true_fit_profile(n) for n in range(1, 31))
    assert (
        len(
            simulate_results(
                profiles, EVENT, seed=1, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=30
            ).invited
        )
        == 30
    )


def test_email_everyone_has_no_invite_limit():
    everyone = tuple(_true_fit_profile(n) for n in range(1, 301))
    assert (
        len(
            run_email_everyone(everyone, EVENT, seed=1, coefficients=TEST_ONLY_COEFFICIENTS).invited
        )
        == 300
    )


def test_a_negative_invite_limit_is_refused():
    with pytest.raises(ValueError, match="must not be negative"):
        simulate_results((), EVENT, seed=1, coefficients=TEST_ONLY_COEFFICIENTS, invite_limit=-1)


# --- Coefficient validation ------------------------------------------------


def _valid_kwargs() -> dict[str, float | int]:
    return dataclasses.asdict(TEST_ONLY_COEFFICIENTS)


@pytest.mark.parametrize(
    "overrides",
    [
        {"true_fit_lift": 0.05, "frequent_attender_lift": 0.05},
        {"true_fit_lift": 0.04, "frequent_attender_lift": 0.05},
        {"true_fit_lift": 0.08, "same_major_lift": 0.08},
        {"true_fit_lift": 0.07, "same_major_lift": 0.08},
    ],
)
def test_the_requirements_ordering_is_enforced_by_validation(overrides: dict[str, float]):
    with pytest.raises(SimulationCoefficientsError):
        SimulationCoefficients(**{**_valid_kwargs(), **overrides})


@pytest.mark.parametrize(
    "name",
    [
        "base_signup_rate",
        "true_fit_lift",
        "frequent_attender_lift",
        "same_major_lift",
        "chance_spread",
        "attend_given_signup",
        "true_interest_share_of_fit",
    ],
)
@pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan, math.inf, -math.inf])
def test_every_probability_must_be_finite_and_within_the_unit_interval(name: str, bad: float):
    with pytest.raises(SimulationCoefficientsError):
        SimulationCoefficients(**{**_valid_kwargs(), name: bad})


@pytest.mark.parametrize("bad", [0, -1, 2.5, True, "3"])
def test_the_frequent_attender_threshold_must_be_a_positive_whole_number(bad: object):
    with pytest.raises(SimulationCoefficientsError):
        SimulationCoefficients(**{**_valid_kwargs(), "frequent_attender_events": bad})


def test_a_non_numeric_coefficient_is_refused():
    with pytest.raises(SimulationCoefficientsError, match="must be a number"):
        SimulationCoefficients(**{**_valid_kwargs(), "chance_spread": "wide"})


def test_zero_chance_spread_is_allowed_and_removes_the_chance():
    steady = SimulationCoefficients(**{**_valid_kwargs(), "chance_spread": 0.0})
    profiles = tuple(_true_fit_profile(n) for n in range(1, 50))
    assert run_email_everyone(profiles, EVENT, seed=1, coefficients=steady) == (
        run_email_everyone(profiles, EVENT, seed=1, coefficients=steady)
    )


def test_coefficients_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        TEST_ONLY_COEFFICIENTS.chance_spread = 0.5  # type: ignore[misc]


# --- OQ-CE-03: the shipped set (the team's translation, still OPEN) -------


def _shipped() -> SimulationCoefficients:
    assert EXERCISE_SIMULATION_COEFFICIENTS is not None
    return EXERCISE_SIMULATION_COEFFICIENTS


def test_the_exercise_now_ships_a_set_so_a_results_run_stops_refusing():
    assert require_coefficients() is _shipped()


def test_the_shipped_set_honours_anns_a_lot_some_a_little():
    """OQ-CE-03, Ann 2026-09-25: true fit "a lot", attended before "some",
    same major "a little", and "some randomness"."""
    shipped = _shipped()
    assert shipped.true_fit_lift > shipped.frequent_attender_lift > shipped.same_major_lift > 0
    assert shipped.chance_spread > 0


def test_the_shipped_set_counts_any_past_event_as_having_attended_before():
    """Ann's (b) is "has attended events before", so one past event is enough."""
    assert _shipped().frequent_attender_events == 1


def test_the_shipped_set_is_still_marked_as_the_teams_translation():
    """OQ-CE-03 stays OPEN until Chau and Ann confirm the numbers from a sample."""
    from pathlib import Path

    from smartmatch_domain.exercise import simulation

    raw = Path(simulation.__file__).read_text(encoding="utf-8").replace("#: ", "")
    source = " ".join(raw.split())
    assert (
        "PLACEHOLDER (OQ-CE-03: Ann's a lot/some/a little/some; numbers are the team's "
        "translation, Chau to confirm with a sample result)"
    ) in source


def test_the_plain_words_paragraph_states_every_shipped_number():
    """Ann and Dr. Lin receive the paragraph; it must say what the code does."""
    from smartmatch_domain.exercise import simulation
    from smartmatch_domain.student_factors import UNDECIDED_EXPLORATORY_GOAL_FIT

    shipped = _shipped()
    text = " ".join((simulation.__doc__ or "").split())

    def per_100(value: float) -> int:
        return round(value * 100)

    # Each number is checked in the sentence that names it, so two numbers
    # that happen to be equal cannot stand in for each other.
    for sentence in (
        f"Everyone starts with a {per_100(shipped.base_signup_rate)} in 100 chance",
        f"The biggest boost, {per_100(shipped.true_fit_lift)} in 100",
        f"medium boost of {per_100(shipped.frequent_attender_lift)} in 100",
        f"small boost of {per_100(shipped.same_major_lift)} in 100",
        f"up to {per_100(shipped.chance_spread / 2)} in 100 either way",
        f"a {per_100(shipped.attend_given_signup)} in 100 chance of attending",
        "never goes below 0 or above 100 in 100",
    ):
        assert sentence in text, sentence
    assert shipped.frequent_attender_events == 1
    assert "been to at least one past event" in text
    assert shipped.true_interest_share_of_fit == 0.5
    assert "half of it when one of their true interests" in text
    assert UNDECIDED_EXPLORATORY_GOAL_FIT == 0.5
    assert "gets half of that career-goal half" in text


def test_require_coefficients_refuses_while_the_set_is_none(monkeypatch):
    from smartmatch_domain.exercise import simulation

    monkeypatch.setattr(simulation, "EXERCISE_SIMULATION_COEFFICIENTS", None)
    with pytest.raises(CoefficientsNotConfirmedError) as excinfo:
        require_coefficients()
    assert str(excinfo.value) == "The results rule has no confirmed coefficients yet."


# --- OQ-CE-14: an undecided goal is half a fit for an exploratory event ----

EXPLORATORY_EVENT = dataclasses.replace(EVENT, exploratory=True)


def _undecided(profile_no: int = 1) -> SimulationProfile:
    return SimulationProfile(profile_no=profile_no, major="history", career_goal_undecided=True)


def test_an_undecided_goal_earns_half_the_goal_part_on_an_exploratory_event():
    all_on_goal = _with(true_interest_share_of_fit=0.0)
    assert _fit_share(_undecided(), EXPLORATORY_EVENT, all_on_goal) == 0.5
    assert _fit_share(_undecided(), EVENT, all_on_goal) == 0.0


def test_the_half_is_the_same_half_the_matching_factor_gives():
    """The rule and the factor must not disagree about what "undecided" earns."""
    from smartmatch_domain.student_factors import UNDECIDED_EXPLORATORY_GOAL_FIT

    split = _with(true_interest_share_of_fit=0.4)
    assert _fit_share(_undecided(), EXPLORATORY_EVENT, split) == pytest.approx(
        0.6 * UNDECIDED_EXPLORATORY_GOAL_FIT
    )


def test_a_goal_that_fits_outranks_undecided_on_an_exploratory_event():
    fits = SimulationProfile(profile_no=1, major="history", career_goal="data_career")
    split = _with(true_interest_share_of_fit=0.5)
    assert _fit_share(fits, EXPLORATORY_EVENT, split) > _fit_share(
        _undecided(), EXPLORATORY_EVENT, split
    )


def test_a_goal_with_no_topic_that_is_not_undecided_earns_nothing_on_an_exploratory_event():
    """Graduate school: "no specific event topic" (Ann, 2026-09-25)."""
    graduate = SimulationProfile(profile_no=1, major="history")
    assert _fit_share(graduate, EXPLORATORY_EVENT, _with(true_interest_share_of_fit=0.0)) == 0.0


def test_an_undecided_profile_has_no_goal_topic():
    with pytest.raises(ValueError, match="career_goal_undecided"):
        SimulationProfile(
            profile_no=1, major="history", career_goal="data_career", career_goal_undecided=True
        )


def test_a_simulation_profile_never_prints_whether_its_hidden_goal_is_undecided():
    """ADR-0025 D6: the flag is derived from ``hidden_true_career_goal``."""
    assert "career_goal_undecided" not in repr(_undecided())
    assert "True" not in repr(_undecided())


# --- Seats -----------------------------------------------------------------


def test_the_seat_constants_are_the_case_facts():
    assert EVENT_SEATS == 60
    assert EXISTING_SIGNUPS == 8


@pytest.mark.parametrize(
    ("attended", "expected"),
    [(0, 52), (10, 42), (52, 0), (53, 0), (200, 0)],
)
def test_seats_empty_counts_down_and_floors_at_zero(attended: int, expected: int):
    assert seats_empty(attended) == expected


def test_seats_empty_refuses_a_negative_count():
    with pytest.raises(ValueError, match="must not be negative"):
        seats_empty(-1)


# --- The plain-words statement ---------------------------------------------

BEHAVIOUR_PHRASES = [
    # (1) true interests and career goal match the event
    "hidden true interests and its career goal match the event",
    # (2) frequent attenders are only a little more likely
    "smaller than the true-fit lift",
    # (3) same major alone gives only a small lift
    "Same major alone gives only a small lift",
    # (4) a small element of chance, fixed per team
    "A small element of chance, fixed for each team",
    # (5) a reset per team that does not touch other teams
    "A reset per team touches no other team",
]


@pytest.mark.parametrize("phrase", BEHAVIOUR_PHRASES)
def test_the_module_docstring_names_each_of_the_five_behaviours(phrase: str):
    from smartmatch_domain.exercise import simulation

    assert simulation.__doc__ is not None
    assert phrase in simulation.__doc__


def test_the_module_docstring_keeps_the_design_spec_draft_paragraph():
    from smartmatch_domain.exercise import simulation

    assert simulation.__doc__ is not None
    text = " ".join(simulation.__doc__.split())
    assert (
        "For each invited profile the app decides whether the person signs up, "
        "then whether they attend." in text
    )
    assert (
        "The app uses each profile's true interests for this, not what the "
        "profile has told the app" in text
    )


def test_the_module_docstring_records_the_hash_deviation():
    from smartmatch_domain.exercise import simulation

    assert simulation.__doc__ is not None
    text = " ".join(simulation.__doc__.split())
    assert "PYTHONHASHSEED" in text
    assert "SHA-256" in text


def test_the_module_docstring_lists_all_eight_quantities_oq_ce_03_must_supply():
    from smartmatch_domain.exercise import simulation

    assert simulation.__doc__ is not None
    text = " ".join(simulation.__doc__.split())
    assert "The rule needs **eight**" in text
    for field in dataclasses.fields(SimulationCoefficients):
        assert f"``{field.name}``" in text


# --- The true-fit split is a coefficient, not a constant --------------------


def _with(**overrides: object) -> SimulationCoefficients:
    """Test-only coefficients with some fields replaced."""
    return SimulationCoefficients(**{**_valid_kwargs(), **overrides})


def test_the_split_decides_whether_interests_or_the_goal_carry_the_fit():
    interests_only = SimulationProfile(
        profile_no=1, major="history", true_interests=frozenset({"analytics"})
    )
    goal_only = SimulationProfile(profile_no=1, major="history", career_goal="data_career")
    all_on_interests = _with(true_interest_share_of_fit=1.0, chance_spread=0.0)
    all_on_goal = _with(true_interest_share_of_fit=0.0, chance_spread=0.0)

    assert _fit_share(interests_only, EVENT, all_on_interests) == 1.0
    assert _fit_share(goal_only, EVENT, all_on_interests) == 0.0
    assert _fit_share(interests_only, EVENT, all_on_goal) == 0.0
    assert _fit_share(goal_only, EVENT, all_on_goal) == 1.0


def test_a_profile_with_both_reaches_the_whole_lift_at_any_split():
    both = _true_fit_profile(1)
    for share in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert _fit_share(both, EVENT, _with(true_interest_share_of_fit=share)) == 1.0


def test_the_split_is_the_ceiling_for_a_profile_with_no_career_goal():
    """ADR-0011: the unknown is not penalised, it is simply not collected."""
    no_goal = SimulationProfile(
        profile_no=1, major="history", true_interests=frozenset({"analytics"})
    )
    for share in (0.2, 0.5, 0.9):
        assert _fit_share(no_goal, EVENT, _with(true_interest_share_of_fit=share)) == (
            pytest.approx(share)
        )


def test_the_module_defines_no_constant_for_the_true_fit_split():
    """OQ-CE-03 owns the split; a module constant would decide it here."""
    from smartmatch_domain.exercise import simulation

    assert not hasattr(simulation, "_FIT_HALF")


# --- The uniform draw really is half-open ----------------------------------


def test_the_largest_possible_digest_still_draws_below_one(monkeypatch):
    """A draw of exactly 1.0 would make a certainty fail."""
    from smartmatch_domain.exercise import simulation

    monkeypatch.setattr(simulation, "_digest", lambda *fields: b"\xff" * 32)
    drawn = simulation._uniform(1, "northline", 1, "signup")
    assert drawn < 1.0
    assert drawn == pytest.approx(1.0, abs=1e-15)


def test_the_smallest_possible_digest_draws_exactly_zero(monkeypatch):
    from smartmatch_domain.exercise import simulation

    monkeypatch.setattr(simulation, "_digest", lambda *fields: b"\x00" * 32)
    assert simulation._uniform(1, "northline", 1, "signup") == 0.0


def test_a_certain_profile_signs_up_even_on_the_largest_digest(monkeypatch):
    """The bug the bound fixes, seen at the level of a result."""
    from smartmatch_domain.exercise import simulation

    monkeypatch.setattr(simulation, "_digest", lambda *fields: b"\xff" * 32)
    certain = _with(base_signup_rate=1.0, chance_spread=0.0, attend_given_signup=1.0)
    result = simulate_results(
        (_true_fit_profile(1),), EVENT, seed=1, coefficients=certain, invite_limit=30
    )
    assert result.signed_up == (1,)
    assert result.attended == (1,)


# --- Digest fields cannot run together -------------------------------------


def test_the_digest_separates_fields_that_a_naive_join_would_merge():
    """``"a:b" + "c"`` and ``"a" + "b:c"`` both join to ``"a:b:c"``."""
    from smartmatch_domain.exercise import simulation

    assert simulation._digest("a:b", "c") != simulation._digest("a", "b:c")


def test_event_keys_containing_a_colon_are_ordinary_keys():
    profiles = tuple(_true_fit_profile(n) for n in range(1, 60))
    first = run_email_everyone(
        profiles,
        dataclasses.replace(EVENT, event_key="a:1"),
        seed=7,
        coefficients=TEST_ONLY_COEFFICIENTS,
    )
    second = run_email_everyone(
        profiles,
        dataclasses.replace(EVENT, event_key="a:2"),
        seed=7,
        coefficients=TEST_ONLY_COEFFICIENTS,
    )
    again = run_email_everyone(
        profiles,
        dataclasses.replace(EVENT, event_key="a:1"),
        seed=7,
        coefficients=TEST_ONLY_COEFFICIENTS,
    )
    assert first != second
    assert first == again
