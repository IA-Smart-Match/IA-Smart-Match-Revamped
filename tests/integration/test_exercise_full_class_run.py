"""A whole class, end to end, on Ann's 300-row file and the approved rule.

Every route in this walk has unit tests over fakes, and the repositories have
integration tests of their own. What had never run is the *class*: six teams
on the real file, through the real routes, on the coefficients Chau approved
(wave-2 decision D7), with every row in PostgreSQL. This file runs it once, in
the order Ann's flow gives (Ann to Chau, Discord, 2026-09-24):

1. the file is seeded the way ``make exercise-seed`` seeds it (CE-SEED, #234);
2. six teams enter their numbers;
3. each sets weights, saves three settings, compares two and picks one final;
4. the instructor unlocks Northline (E11); each team runs round one once, and
   a second run is refused;
5. each team chooses one of the three ways of asking for more and refreshes;
6. the instructor unlocks Harbor (E12); each team runs round two;
7. the instructor resets team 3; team 3 then repeats its work on its old seed.

The tests below read the record of that walk. What they hold the class to:

* **Determinism** — a stored result is the rule applied to the team's seed and
  list; and after a reset, the same seed and the same list give the same
  result, round one and round two.
* **Reset isolation** — resetting team 3 changes nothing any other team, or the
  instructor, can read about any other team.
* **Nothing withheld leaks** — no ``hidden_true_*`` name and no ``OQ-CE-``
  register ID in any response body of the whole class.
* **Plausible figures** — 0 ≤ sign-ups ≤ 30, attended ⊆ signed up ⊆ invited,
  empty seats = 60 - 8 - attended.
* **An undecided true goal reaches the rule** — for every profile whose
  withheld true career goal is "Undecided", the route answers exactly what the
  rule answers on the same stored rows. Ann's revisions of 2026-10-02 removed
  the half credit such a goal earned; this holds the route to the rule as it
  now stands.

Runs against its own scratch database, migrated to head and dropped afterwards;
skipped where no PostgreSQL is reachable.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from exercise_class_driver import (
    HEADER,
    INSTRUCTOR_BASE,
    ROUND_ONE,
    ROUND_TWO,
    TEAM_BASE,
    Exchange,
    RecordingClient,
    asking_choice,
    build_app,
    enter,
    instructor,
    lock,
    numbers_of,
    panel_of,
    prepare_round,
    read_everything,
    recompute,
    run,
    set_seed,
    team_snapshot,
    undecided_true_goal_profile_nos,
    unlock,
    weightings,
    workspace_row,
)
from migration_harness import alembic, connected, scratch_database
from smartmatch_api.exercise_seed import seed_exercise_dataset
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS
from smartmatch_domain.exercise.simulation import (
    EVENT_SEATS,
    EXISTING_SIGNUPS,
)
from smartmatch_persistence.exercise import schema
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from tests.unit.exercise_workbooks import ANN_FULL_FILE

pytestmark = pytest.mark.integration

#: The team whose reset is checked against the other five.
_RESET_TEAM = 3


@dataclass
class _ClassRun:
    """What the walk produced, for the tests to read."""

    log: list[Exchange] = field(default_factory=list)
    round_one: dict[int, dict[str, Any]] = field(default_factory=dict)
    round_two: dict[int, dict[str, Any]] = field(default_factory=dict)
    round_one_read_back: dict[int, dict[str, Any]] = field(default_factory=dict)
    second_run: dict[int, tuple[int, dict[str, Any]]] = field(default_factory=dict)
    locked_run: dict[int, tuple[int, dict[str, Any]]] = field(default_factory=dict)
    fourth_setting: tuple[int, dict[str, Any]] = (0, {})
    final_lists: dict[tuple[int, str], list[int]] = field(default_factory=dict)
    seeds_after_reset: dict[int, int] = field(default_factory=dict)
    reset_seed_everyone: Any = None
    refresh: dict[int, dict[str, Any]] = field(default_factory=dict)
    asking_after_refresh: dict[int, dict[str, Any]] = field(default_factory=dict)
    recomputed: dict[tuple[int, str], tuple[Any, Any]] = field(default_factory=dict)
    seeds: dict[int, int] = field(default_factory=dict)
    before_reset: dict[int, dict[str, tuple[int, Any]]] = field(default_factory=dict)
    after_reset: dict[int, dict[str, tuple[int, Any]]] = field(default_factory=dict)
    reset_seed: int = 0
    rerun_round_one: dict[str, Any] = field(default_factory=dict)
    rerun_refresh: dict[str, Any] = field(default_factory=dict)
    rerun_round_two: dict[str, Any] = field(default_factory=dict)
    undecided_profile_nos: frozenset[int] = frozenset()


@contextmanager
def _seeded_database(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """A scratch database at head, seeded from Ann's file, dropped afterwards."""
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        with connected(url) as scratch:
            factory = sessionmaker(bind=scratch, expire_on_commit=False, future=True)
            with factory() as session:
                outcome = seed_exercise_dataset(
                    session, ANN_FULL_FILE.read_bytes(), source_filename=ANN_FULL_FILE.name
                )
            assert getattr(outcome, "seeded", None) is True, outcome
            yield factory


@pytest.fixture(scope="module")
def sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """The module's own seeded scratch database."""
    with _seeded_database(engine) as factory:
        yield factory


def _body(response: Any) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    return body


def _without_times(value: Any) -> Any:
    """A response body with its ``created_at`` stamps removed, at any depth."""
    if isinstance(value, dict):
        return {key: _without_times(item) for key, item in value.items() if key != "created_at"}
    if isinstance(value, list):
        return [_without_times(item) for item in value]
    return value


def _round_one(
    record: _ClassRun,
    sessions: sessionmaker[Session],
    teams: dict[int, RecordingClient],
) -> None:
    for number, client in teams.items():
        response = run(client, ROUND_ONE, number)
        assert response.status_code == 201, response.text
        record.round_one[number] = _body(response)
        again = run(client, ROUND_ONE, number)
        record.second_run[number] = (again.status_code, _body(again))
        read_back = client.get(f"{TEAM_BASE}/events/{ROUND_ONE}/results")
        assert read_back.status_code == 200, read_back.text
        record.round_one_read_back[number] = _body(read_back)
        invited = record.round_one[number]["team"]["invited_profile_nos"]
        record.recomputed[(number, ROUND_ONE)] = recompute(sessions, number, ROUND_ONE, invited)


def _ask_and_refresh(record: _ClassRun, teams: dict[int, RecordingClient]) -> None:
    for number, client in teams.items():
        chosen = client.post(
            f"{TEAM_BASE}/asking-choice",
            json={"choice": asking_choice(number).value},
            headers=HEADER,
        )
        assert chosen.status_code == 200, chosen.text
        refreshed = client.post(f"{TEAM_BASE}/refresh", headers=HEADER)
        assert refreshed.status_code == 200, refreshed.text
        record.refresh[number] = _body(refreshed)
        record.asking_after_refresh[number] = _body(client.get(f"{TEAM_BASE}/asking-choice"))


def _round_two(
    record: _ClassRun,
    sessions: sessionmaker[Session],
    teams: dict[int, RecordingClient],
) -> None:
    for number, client in teams.items():
        record.final_lists[(number, ROUND_TWO)] = prepare_round(client, ROUND_TWO, number)
        response = run(client, ROUND_TWO, number)
        assert response.status_code == 201, response.text
        record.round_two[number] = _body(response)
        invited = record.round_two[number]["team"]["invited_profile_nos"]
        record.recomputed[(number, ROUND_TWO)] = recompute(sessions, number, ROUND_TWO, invited)


def _reset_and_repeat(
    record: _ClassRun,
    sessions: sessionmaker[Session],
    teams: dict[int, RecordingClient],
    teacher: RecordingClient,
) -> None:
    """Reset team 3, snapshot everybody, then repeat team 3's work on its old seed."""
    record.before_reset = {n: team_snapshot(c, teacher, n) for n, c in teams.items()}
    old = workspace_row(sessions, _RESET_TEAM)
    reset = teacher.post(f"{INSTRUCTOR_BASE}/workspaces/{_RESET_TEAM}/reset", headers=HEADER)
    assert reset.status_code == 200, reset.text
    record.after_reset = {n: team_snapshot(c, teacher, n) for n, c in teams.items()}
    record.seeds_after_reset = {n: workspace_row(sessions, n).seed for n in teams}
    record.reset_seed = record.seeds_after_reset[_RESET_TEAM]
    # The rule on the new seed, same list, with the overlay cleared as it was
    # before round one: the seed has to matter, or the rerun below proves nothing.
    invited = record.round_one[_RESET_TEAM]["team"]["invited_profile_nos"]
    _, record.reset_seed_everyone = recompute(
        sessions, _RESET_TEAM, ROUND_ONE, invited, seed=record.reset_seed
    )

    set_seed(sessions, old.id, old.seed)
    client = teams[_RESET_TEAM]
    prepare_round(client, ROUND_ONE, _RESET_TEAM)
    first = run(client, ROUND_ONE, _RESET_TEAM)
    assert first.status_code == 201, first.text
    record.rerun_round_one = _body(first)
    chosen = client.post(
        f"{TEAM_BASE}/asking-choice",
        json={"choice": asking_choice(_RESET_TEAM).value},
        headers=HEADER,
    )
    assert chosen.status_code == 200, chosen.text
    refreshed = client.post(f"{TEAM_BASE}/refresh", headers=HEADER)
    assert refreshed.status_code == 200, refreshed.text
    record.rerun_refresh = _body(refreshed)
    prepare_round(client, ROUND_TWO, _RESET_TEAM)
    second = run(client, ROUND_TWO, _RESET_TEAM)
    assert second.status_code == 201, second.text
    record.rerun_round_two = _body(second)


@pytest.fixture(scope="module")
def class_run(sessions: sessionmaker[Session]) -> _ClassRun:
    """Walk the whole class once; every test below reads this record."""
    record = _ClassRun()
    app = build_app(sessions)
    teacher = instructor(app, record.log)
    teams = {number: enter(app, record.log, number) for number in EXERCISE_TEAM_NUMBERS}

    for number, client in teams.items():
        record.final_lists[(number, ROUND_ONE)] = prepare_round(client, ROUND_ONE, number)
        locked = run(client, ROUND_ONE, number)
        record.locked_run[number] = (locked.status_code, _body(locked))
    fourth = teams[6].put(
        f"{TEAM_BASE}/events/{ROUND_ONE}/settings/one too many",
        json={"weights": weightings(6)["balanced"]},
        headers=HEADER,
    )
    record.fourth_setting = (fourth.status_code, _body(fourth))

    unlock(teacher, ROUND_ONE)
    _round_one(record, sessions, teams)
    _ask_and_refresh(record, teams)
    unlock(teacher, ROUND_TWO)
    _round_two(record, sessions, teams)
    for client in teams.values():
        read_everything(client, teacher)
    record.seeds = {n: workspace_row(sessions, n).seed for n in EXERCISE_TEAM_NUMBERS}
    record.undecided_profile_nos = undecided_true_goal_profile_nos(sessions, _RESET_TEAM)
    _reset_and_repeat(record, sessions, teams, teacher)
    return record


# ---------------------------------------------------------------------------
# The walk itself
# ---------------------------------------------------------------------------


def test_the_fixture_has_the_two_rounds_this_file_names(sessions: sessionmaker[Session]) -> None:
    event = schema.exercise_event
    with sessions() as session:
        rows = session.execute(
            sa.select(event.c.event_key, event.c.name)
            .where(event.c.is_exercise_event.is_(True))
            .order_by(event.c.sequence)
        ).all()
    assert [(key, name.split(":")[0]) for key, name in rows] == [
        (ROUND_ONE, "Northline Analytics"),
        (ROUND_TWO, "Harbor Consumer Brands"),
    ]


def test_every_team_is_refused_before_the_instructor_unlocks(class_run: _ClassRun) -> None:
    for number in EXERCISE_TEAM_NUMBERS:
        status, body = class_run.locked_run[number]
        assert (status, body["error"]["code"]) == (409, "exercise_results_locked"), number


def test_a_fourth_saved_setting_is_refused(class_run: _ClassRun) -> None:
    status, body = class_run.fourth_setting
    assert (status, body["error"]["code"]) == (409, "exercise_too_many_settings")


def test_every_team_ran_both_rounds(class_run: _ClassRun) -> None:
    assert sorted(class_run.round_one) == list(EXERCISE_TEAM_NUMBERS)
    assert sorted(class_run.round_two) == list(EXERCISE_TEAM_NUMBERS)
    for number in EXERCISE_TEAM_NUMBERS:
        assert class_run.round_one[number]["round"] == 1
        assert class_run.round_two[number]["round"] == 2


def test_a_second_run_of_round_one_is_refused(class_run: _ClassRun) -> None:
    for number in EXERCISE_TEAM_NUMBERS:
        status, body = class_run.second_run[number]
        assert (status, body["error"]["code"]) == (409, "exercise_results_already_run"), number


def test_the_stored_run_reads_back_as_it_was_answered(class_run: _ClassRun) -> None:
    for number in EXERCISE_TEAM_NUMBERS:
        assert class_run.round_one_read_back[number] == class_run.round_one[number]


def test_round_two_carries_the_teams_own_round_one(class_run: _ClassRun) -> None:
    for number in EXERCISE_TEAM_NUMBERS:
        carried = class_run.round_two[number]["round_one"]
        assert carried is not None
        assert carried["team"] == class_run.round_one[number]["team"]
        assert carried["seats_empty"] == class_run.round_one[number]["seats_empty"]


def test_the_asking_route_reports_the_same_counts_the_refresh_did(
    class_run: _ClassRun,
) -> None:
    """M2 B4: the counts survive a reload, read back from the stored overlay."""
    for number in EXERCISE_TEAM_NUMBERS:
        posted = class_run.refresh[number]
        assert class_run.asking_after_refresh[number]["refresh_counts"] == {
            key: posted[key] for key in ("cards_completed", "non_responding", "topics_added")
        }, number


def test_each_team_used_its_own_way_of_asking(class_run: _ClassRun) -> None:
    for number in EXERCISE_TEAM_NUMBERS:
        assert class_run.refresh[number]["choice"] == asking_choice(number).value


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event_key", [ROUND_ONE, ROUND_TWO])
def test_a_stored_result_is_the_rule_on_the_teams_seed_and_list(
    class_run: _ClassRun, event_key: str
) -> None:
    answered = class_run.round_one if event_key == ROUND_ONE else class_run.round_two
    for number in EXERCISE_TEAM_NUMBERS:
        team, everyone = class_run.recomputed[(number, event_key)]
        assert numbers_of(answered[number]["team"]) == panel_of(team), number
        assert numbers_of(answered[number]["email_everyone"]) == panel_of(everyone), number


@pytest.mark.parametrize("event_key", [ROUND_ONE, ROUND_TWO])
def test_each_team_invited_exactly_its_final_settings_list(
    class_run: _ClassRun, event_key: str
) -> None:
    """The run invites the list the final setting showed — no more, no other."""
    answered = class_run.round_one if event_key == ROUND_ONE else class_run.round_two
    for number in EXERCISE_TEAM_NUMBERS:
        shown = class_run.final_lists[(number, event_key)]
        assert len(shown) == 30, number
        assert answered[number]["team"]["invited_profile_nos"] == sorted(shown), number


def test_the_seed_changes_the_result(class_run: _ClassRun) -> None:
    """Same list, new seed, different outcome — so the same-seed rerun means something."""
    original = numbers_of(class_run.round_one[_RESET_TEAM]["email_everyone"])
    assert panel_of(class_run.reset_seed_everyone) != original


def test_after_a_reset_the_same_seed_and_list_give_the_same_round_one(
    class_run: _ClassRun,
) -> None:
    assert _without_times(class_run.rerun_round_one) == _without_times(
        class_run.round_one[_RESET_TEAM]
    )


def test_after_a_reset_the_same_seed_and_choice_give_the_same_refresh(
    class_run: _ClassRun,
) -> None:
    assert class_run.rerun_refresh == class_run.refresh[_RESET_TEAM]


def test_after_a_reset_the_same_seed_and_list_give_the_same_round_two(
    class_run: _ClassRun,
) -> None:
    assert _without_times(class_run.rerun_round_two) == _without_times(
        class_run.round_two[_RESET_TEAM]
    )


# ---------------------------------------------------------------------------
# Reset isolation
# ---------------------------------------------------------------------------


def test_resetting_team_3_changes_nothing_about_any_other_team(class_run: _ClassRun) -> None:
    for number in EXERCISE_TEAM_NUMBERS:
        if number == _RESET_TEAM:
            continue
        before, after = class_run.before_reset[number], class_run.after_reset[number]
        changed = sorted(label for label in before if before[label] != after[label])
        assert changed == [], f"team {number}: {changed}"


def test_resetting_team_3_changes_no_other_teams_seed(class_run: _ClassRun) -> None:
    for number in EXERCISE_TEAM_NUMBERS:
        if number != _RESET_TEAM:
            assert class_run.seeds_after_reset[number] == class_run.seeds[number], number


def test_the_reset_cleared_team_3_and_gave_it_a_new_seed(class_run: _ClassRun) -> None:
    after = class_run.after_reset[_RESET_TEAM]
    for event_key in (ROUND_ONE, ROUND_TWO):
        status, body = after[f"results {event_key}"]
        assert (status, body["error"]["code"]) == (404, "exercise_results_not_run")
        assert after[f"settings {event_key}"][1]["settings"] == []
    assert after["asking"][1]["choice"] is None
    assert after["asking"][1]["refreshed"] is False
    assert class_run.reset_seed != class_run.seeds[_RESET_TEAM]


# ---------------------------------------------------------------------------
# Nothing withheld, no register IDs
# ---------------------------------------------------------------------------


def _keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_the_class_made_enough_requests_to_mean_something(class_run: _ClassRun) -> None:
    """Six teams through two rounds is well over a hundred exchanges."""
    assert len(class_run.log) > 100
    assert {exchange.status for exchange in class_run.log} >= {200, 201, 404, 409}


def test_no_response_body_names_a_withheld_column(class_run: _ClassRun) -> None:
    offenders = [
        f"{exchange.method} {exchange.path}"
        for exchange in class_run.log
        if "hidden_true" in exchange.text
        or any("hidden" in key or key.startswith("true_") for key in _keys(_json(exchange)))
    ]
    assert offenders == []


def test_no_response_body_carries_a_register_id(class_run: _ClassRun) -> None:
    offenders = [
        f"{exchange.method} {exchange.path}"
        for exchange in class_run.log
        if "OQ-CE-" in exchange.text
    ]
    assert offenders == []


def _json(exchange: Exchange) -> Any:
    try:
        return json.loads(exchange.text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Plausible figures
# ---------------------------------------------------------------------------


def _all_results(class_run: _ClassRun) -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"team {n} {label}", body)
        for label, source in (
            ("round one", class_run.round_one),
            ("round two", class_run.round_two),
        )
        for n, body in source.items()
    ]


def test_the_figures_are_plausible(class_run: _ClassRun) -> None:
    for label, body in _all_results(class_run):
        team, everyone = body["team"], body["email_everyone"]
        assert 0 < team["invited_count"] <= 30, label
        assert 0 <= team["signed_up_count"] <= 30, label
        assert 0 <= team["attended_count"] <= team["signed_up_count"], label
        assert everyone["invited_count"] == 300, label
        # The shipped rule tops out near 0.68 per profile, so a panel where
        # most of the 300 sign up means the rule has stopped discriminating.
        assert everyone["signed_up_count"] < 250, label
        for panel in (team, everyone):
            invited = set(panel["invited_profile_nos"])
            signed = set(panel["signed_up_profile_nos"])
            attended = set(panel["attended_profile_nos"])
            assert attended <= signed <= invited, label
            assert (len(invited), len(signed), len(attended)) == (
                panel["invited_count"],
                panel["signed_up_count"],
                panel["attended_count"],
            ), label
        assert set(team["invited_profile_nos"]) <= set(everyone["invited_profile_nos"]), label
        assert (body["event_seats"], body["existing_signups"]) == (
            EVENT_SEATS,
            EXISTING_SIGNUPS,
        ), label
        assert body["seats_empty"] == max(
            0, EVENT_SEATS - EXISTING_SIGNUPS - team["attended_count"]
        ), label


def test_the_class_as_a_whole_got_sign_ups(class_run: _ClassRun) -> None:
    """A rule that signed nobody up across twelve runs would be a dead rule."""
    total = sum(body["team"]["signed_up_count"] for _, body in _all_results(class_run))
    assert total > 0


# ---------------------------------------------------------------------------
# An undecided true career goal, through the route
# ---------------------------------------------------------------------------

#: How many of Ann's 300 profiles have "Undecided" as their withheld true goal.
_UNDECIDED_TRUE_GOALS = 31


@pytest.mark.parametrize("event_key", [ROUND_ONE, ROUND_TWO])
def test_an_undecided_true_goal_gets_from_the_route_what_the_rule_gives_it(
    class_run: _ClassRun, event_key: str
) -> None:
    """Outcomes only: who signed up and who attended, among the undecided.

    "Email everyone" invites all 300, so every undecided profile is in the
    run. The recomputed result is the rule applied to the same stored rows,
    seed and event outside the route.
    """
    undecided = class_run.undecided_profile_nos
    assert len(undecided) == _UNDECIDED_TRUE_GOALS
    answered = class_run.round_one if event_key == ROUND_ONE else class_run.round_two
    for number in EXERCISE_TEAM_NUMBERS:
        route = numbers_of(answered[number]["email_everyone"])
        _, everyone = class_run.recomputed[(number, event_key)]
        rule = panel_of(everyone)
        assert undecided <= set(route["invited_profile_nos"]), number
        for outcome in ("signed_up_profile_nos", "attended_profile_nos"):
            assert undecided & set(route[outcome]) == undecided & set(rule[outcome]), (
                number,
                outcome,
            )


def test_the_undecided_outcomes_compared_are_not_all_empty(class_run: _ClassRun) -> None:
    """Twelve runs in which no undecided profile signed up would compare nothing."""
    signed_up = {
        profile_no
        for answered in (class_run.round_one, class_run.round_two)
        for number in EXERCISE_TEAM_NUMBERS
        for profile_no in answered[number]["email_everyone"]["signed_up_profile_nos"]
    }
    assert class_run.undecided_profile_nos & signed_up


# ---------------------------------------------------------------------------
# Closing results again (D16 amendment, 2026-10-06)
# ---------------------------------------------------------------------------


def _refusal_code(response: Any) -> tuple[int, str]:
    return response.status_code, _body(response).get("error", {}).get("code", "")


def test_closing_results_turns_away_only_the_teams_that_have_not_run(engine: Engine) -> None:
    """Open, run, close, reopen — through the real routes, on its own database.

    The class walk above never closes anything, and by its end every team has
    run both rounds, so this case needs teams of its own. A close deletes
    nothing: the team that ran keeps its results and its one run; the team
    that had not is turned away until the instructor opens the event again.
    """
    with _seeded_database(engine) as own:
        log: list[Exchange] = []
        app = build_app(own)
        teacher = instructor(app, log)
        ran, late = enter(app, log, 1), enter(app, log, 2)
        prepare_round(ran, ROUND_ONE, 1)
        prepare_round(late, ROUND_ONE, 2)
        results = f"{TEAM_BASE}/events/{ROUND_ONE}/results"

        unlock(teacher, ROUND_ONE)
        first = run(ran, ROUND_ONE, 1)
        assert first.status_code == 201, first.text

        lock(teacher, ROUND_ONE)
        assert _refusal_code(run(late, ROUND_ONE, 2)) == (409, "exercise_results_locked")
        assert _refusal_code(run(ran, ROUND_ONE, 1)) == (409, "exercise_results_already_run")
        kept = ran.get(results)
        assert kept.status_code == 200, kept.text
        assert _body(kept) == _body(first)

        unlock(teacher, ROUND_ONE)
        second = run(late, ROUND_ONE, 2)
        assert second.status_code == 201, second.text
        assert _refusal_code(run(ran, ROUND_ONE, 1)) == (409, "exercise_results_already_run")
        assert _body(ran.get(results)) == _body(first)
