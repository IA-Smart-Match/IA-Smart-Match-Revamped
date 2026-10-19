"""Round two is locked until the team has its Northline (round-one) results.

Server-enforced (Dr. Wang, must work before Oct 23): a client that skips the
screen and posts straight to a round-two route is refused with
``exercise_round_two_locked``. Covers the three round-two writes that carry
that code (the Harbor results run, saving a Harbor setting) and the asking
choice, which keeps its older ``exercise_no_first_round_results`` refusal on
the same condition. Runs against a privately named database.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from exercise_class_driver import (
    HEADER,
    ROUND_ONE,
    ROUND_TWO,
    TEAM_BASE,
    asking_choice,
    build_app,
    enter,
    instructor,
    lock,
    prepare_round,
    run,
    unlock,
    weightings,
)
from exercise_private_db import seeded_private_database
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

_LOCKED = "exercise_round_two_locked"
_SENTENCE = "Round 2 opens after your team has its Round 1 results."


@pytest.fixture(scope="module")
def sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    with seeded_private_database(engine, "r2lock") as factory:
        yield factory


def _error(response: Any) -> dict[str, Any]:
    assert response.status_code == 409, response.text
    return response.json()["error"]


def test_round_two_writes_are_refused_until_northline_results_then_allowed(
    sessions: sessionmaker[Session],
) -> None:
    app = build_app(sessions)
    log: list = []
    teacher = instructor(app, log)
    team = enter(app, log, 1)
    unlock(teacher, ROUND_ONE)
    unlock(teacher, ROUND_TWO)
    assert team.get("/v1/exercise/workspaces/current").json()["round_two_open"] is False

    named = weightings(1)
    refused = team.put(
        f"{TEAM_BASE}/events/{ROUND_TWO}/settings/balanced",
        json={"weights": named["balanced"]},
        headers=HEADER,
    )
    assert _error(refused)["code"] == _LOCKED
    assert _error(refused)["message"] == _SENTENCE
    refused = run(team, ROUND_TWO, 1)
    assert _error(refused)["code"] == _LOCKED
    chosen = team.post(
        f"{TEAM_BASE}/asking-choice", json={"choice": asking_choice(1).value}, headers=HEADER
    )
    assert _error(chosen)["code"] == "exercise_no_first_round_results"

    # Nothing was written for round two, and round one is untouched by the lock.
    assert team.get(f"{TEAM_BASE}/events/{ROUND_TWO}/settings").json()["settings"] == []
    prepare_round(team, ROUND_ONE, 1)
    assert run(team, ROUND_ONE, 1).status_code == 201

    assert team.get("/v1/exercise/workspaces/current").json()["round_two_open"] is True
    prepare_round(team, ROUND_TWO, 1)
    chosen = team.post(
        f"{TEAM_BASE}/asking-choice", json={"choice": asking_choice(1).value}, headers=HEADER
    )
    assert chosen.status_code == 200, chosen.text
    # Northline results exist but the team has not asked yet: ask first.
    assert _error(run(team, ROUND_TWO, 1))["code"] == "exercise_ask_first"
    asked = team.post(f"{TEAM_BASE}/refresh", json={}, headers=HEADER)
    assert asked.status_code == 200, asked.text
    assert run(team, ROUND_TWO, 1).status_code == 201


def test_the_round_one_sentence_wins_over_an_instructor_locked_harbor(
    sessions: sessionmaker[Session],
) -> None:
    app = build_app(sessions)
    log: list = []
    teacher = instructor(app, log)
    team = enter(app, log, 2)
    other = enter(app, log, 3)
    unlock(teacher, ROUND_ONE)
    lock(teacher, ROUND_TWO)
    prepare_round(team, ROUND_ONE, 2)
    # Team 3 has no Northline results and asks for the instructor-locked Harbor.
    assert _error(run(other, ROUND_TWO, 3))["code"] == _LOCKED
    # A team that has its Northline results gets the instructor's lock instead.
    assert run(team, ROUND_ONE, 2).status_code == 201
    assert _error(run(team, ROUND_TWO, 2))["code"] != _LOCKED
