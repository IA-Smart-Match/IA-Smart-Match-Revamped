"""The class-load list memo is never stale after a refresh (Ann #413, lane L4).

Fable's risk: Harbor lists read after asking must show the refreshed profiles,
not the list kept from before. The memo keys on a digest of the team's overlay
computed in PostgreSQL; this drives a real refresh and compares the kept answer
with one built from scratch. Runs against a privately named database.
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
    prepare_round,
    run,
    unlock,
)
from exercise_private_db import seeded_private_database
from smartmatch_api.routers import exercise_matching
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

_HARBOR = f"{TEAM_BASE}/events/{ROUND_TWO}/list"


@pytest.fixture(scope="module")
def sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    with seeded_private_database(engine, "listmemo") as factory:
        yield factory


def _harbor(client: Any) -> Any:
    response = client.get(_HARBOR)
    assert response.status_code == 200, response.text
    return response.json()


def test_harbor_after_asking_is_the_refreshed_list_not_the_kept_one(
    sessions: sessionmaker[Session],
) -> None:
    app = build_app(sessions)
    log: list[Any] = []
    teacher = instructor(app, log)
    team = enter(app, log, 1)
    other = enter(app, log, 2)

    before = _harbor(team)
    assert _harbor(other) == before  # neither team has an overlay yet

    prepare_round(team, ROUND_ONE, 1)
    unlock(teacher, ROUND_ONE)
    assert run(team, ROUND_ONE, 1).status_code == 201
    chosen = team.post(
        f"{TEAM_BASE}/asking-choice", json={"choice": asking_choice(1).value}, headers=HEADER
    )
    assert chosen.status_code == 200, chosen.text
    refreshed = team.post(f"{TEAM_BASE}/refresh", headers=HEADER)
    assert refreshed.status_code == 200, refreshed.text

    after = _harbor(team)
    exercise_matching._LIST_MEMO.clear()
    assert _harbor(team) == after  # the kept answer is the one built from scratch
    assert after != before  # and the refresh did change what the team sees
    assert _harbor(other) == before  # the other team's list is untouched
