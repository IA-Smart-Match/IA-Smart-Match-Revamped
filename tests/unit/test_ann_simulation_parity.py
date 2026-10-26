"""Parity: tools/ann_simulation.py (the copy Dr. Wang re-runs) equals the app's rule.

The copy is standalone (stdlib only), so this test pins it to the app: same class
file, same lists, same asking plan, same per-student outcomes, for every setting,
both list sizes and every way of asking, on a handful of team seeds.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_api.routers.exercise_results_models import simulation_event
from smartmatch_api.routers.exercise_results_refresh import refresh_plan
from smartmatch_domain.exercise import simulation as S
from smartmatch_domain.exercise.asking import AskingChoice, copied_card_career_goal
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.vocabulary import goal_topic_for_matching

from tests.golden.exercise.test_exercise_ann_dataset_golden import _dataset, _events, _rows
from tests.golden.exercise.test_exercise_results_rule_sample_golden import _simulation_profiles
from tools import ann_simulation as A

KEYS = ("same_major", "stated_interest_overlap", "career_goal_fit", "past_event_topic_overlap")
CHOICE = {
    "promise": AskingChoice.BETTER_RECOMMENDATIONS,
    "reward": AskingChoice.SMALL_REWARD,
    "required": AskingChoice.REQUIRED,
}
SEEDS = (1, 2, 977, 4242)


def app_data() -> dict:
    """The class file as the copy embeds it (names left out)."""
    d = _dataset()
    return {
        "checksum": d.checksum,
        "events": [
            [e.event_key, e.name, list(e.topic_tags), list(e.target_majors)] for e in d.events
        ],
        "profiles": [
            [
                p.profile_no,
                p.major,
                p.class_year,
                list(p.past_event_keys),
                None if p.stated_interests is None else list(p.stated_interests),
                p.career_goal,
                p.tiebreak_order,
                list(p.hidden_true_interests),
                p.hidden_true_career_goal,
            ]
            for p in d.profiles
        ],
    }


EV = {e.event_key: e for e in _events()}
ROWS = _rows()
HIDDEN = {p.profile_no: p for p in _dataset().profiles}
BASE = _simulation_profiles()
C = S.EXERCISE_SIMULATION_COEFFICIENTS


def app_rank(key, setting, limit, completed=frozenset(), gainers=frozenset()):
    rows = []
    for r in ROWS:
        kw = {}
        if r.profile_no in gainers:
            kw["overlay_added_event_topics"] = tuple(EV[A.NORTHLINE].topic_tags)
        if r.profile_no in completed:
            h = HIDDEN[r.profile_no]
            kw["overlay_card_interests"] = tuple(h.hidden_true_interests)
            kw["overlay_card_career_goal"] = copied_card_career_goal(
                r.career_goal, hidden_true_career_goal=h.hidden_true_career_goal
            )
        rows.append(replace(r, **kw) if kw else r)
    rs = rankable_set(tuple(rows), _events())
    weights = dict(zip(KEYS, A.SETTINGS[setting], strict=True))
    lst = exercise_ranked_list(
        event_evidence(EV[key]),
        rs.profiles,
        weights=weights,
        invite_limit=limit,
        year_rank=rs.year_rank,
        dataset_checksum=_dataset().checksum,
    )
    return tuple(int(e.profile_id) for e in lst.entries)


def app_play(key, listed, seed, silent=frozenset()):
    people = tuple(
        replace(p, non_responding=True) if p.profile_no in silent else p for p in BASE.values()
    )
    by = {p.profile_no: p for p in people}
    ev = simulation_event(EV[key])
    a = S.run_email_everyone(people, ev, seed=seed, coefficients=C)
    b = S.simulate_results(
        tuple(by[n] for n in listed), ev, seed=seed, coefficients=C, invite_limit=len(listed)
    )
    su, at = set(a.signed_up) | set(b.signed_up), set(a.attended) | set(b.attended)
    ex = S.existing_attended(seed, key, C.attend_given_signup)
    return (
        len(a.signed_up),
        len(su),
        len(su) - len(a.signed_up),
        len(a.attended),
        len(at),
        len(at) - len(a.attended),
        ex,
        S.seats_empty(len(at), ex),
    ), at


def test_embedded_class_file_is_the_apps():
    assert app_data() == A.DATA


def test_goal_topics_and_chances_match():
    for p in A.PROFILES:
        assert A.goal_topic(p.true_goal) == goal_topic_for_matching(p.true_goal)
        assert A.goal_topic(p.goal) == goal_topic_for_matching(p.goal)
    for key in (A.NORTHLINE, A.HARBOR):
        ev = simulation_event(EV[key])
        for no, p in BASE.items():
            app_p = min(1.0, max(0.0, C.base_signup_rate + S._sign_up_lift(p, ev, C)))
            assert A.chances(key)[no] == app_p


def test_coefficients_match():
    assert (
        C.base_signup_rate,
        C.true_fit_lift,
        C.true_interest_share_of_fit,
        C.frequent_attender_lift,
        C.frequent_attender_events,
        C.many_attender_lift,
        C.many_attender_events,
        C.same_major_lift,
        C.mass_email_notice,
        C.cbach_email_notice,
        C.attend_given_signup,
    ) == (
        A.BASE_SIGNUP,
        A.TRUE_FIT_LIFT,
        A.INTEREST_SHARE_OF_FIT,
        A.FEW_EVENTS_LIFT,
        A.FEW_EVENTS_FROM,
        A.MANY_EVENTS_LIFT,
        A.MANY_EVENTS_FROM,
        A.SAME_MAJOR_LIFT,
        A.MASS_NOTICE,
        A.CBACH_NOTICE,
        A.ATTEND,
    )
    assert (A.SEATS, A.EXISTING) == (S.EVENT_SEATS, S.EXISTING_SIGNUPS)


@pytest.mark.parametrize("setting", ["major", "interest", "balanced"])
@pytest.mark.parametrize("limit", A.LIMITS)
def test_lists_before_asking_match(setting, limit):
    for key in (A.NORTHLINE, A.HARBOR):
        assert A.list_before(key, setting, limit) == app_rank(key, setting, limit)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_scenario_matches_the_app(seed):
    """Asking plan, after-asking lists and every per-run number, as the app computes them."""
    ours = A.one_run(seed)
    for c, ch in CHOICE.items():
        no_card = tuple(r.profile_no for r in ROWS if r.stated_interests is None)
        for limit in A.LIMITS:
            for s in A.SETTINGS:
                listed = (
                    A.best_list(A.NORTHLINE, limit)
                    if s == "best"
                    else app_rank(A.NORTHLINE, s, limit)
                )
                nl, att = app_play(A.NORTHLINE, listed, seed)
                assert ours[(limit, "nl", s)] == nl
                hb_list = (
                    A.best_list(A.HARBOR, limit) if s == "best" else app_rank(A.HARBOR, s, limit)
                )
                assert ours[(limit, "before", s)] == app_play(A.HARBOR, hb_list, seed)[0]
                plan = refresh_plan(
                    choice=ch,
                    seed=seed,
                    attended_profile_nos=tuple(att),
                    no_card_profile_nos=no_card,
                )
                done, silent = A.asking(c, seed)
                assert (done, silent) == (plan.card_completers, plan.non_responding)
                silent = frozenset(silent)
                if s == "best":
                    after = A.best_list(A.HARBOR, limit, silent)
                else:
                    after = app_rank(A.HARBOR, s, limit, frozenset(done), frozenset(att))
                    assert after == A.rank(
                        A.HARBOR,
                        s,
                        limit,
                        frozenset(done),
                        frozenset(att),
                        A.EVENTS[A.NORTHLINE].topics,
                    )
                assert ours[(limit, f"after_{c}", s)] == app_play(A.HARBOR, after, seed, silent)[0]
