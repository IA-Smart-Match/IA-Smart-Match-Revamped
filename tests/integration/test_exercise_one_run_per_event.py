"""One Northline run per team: repeat, second tab and a burst of concurrent posts.

The rule is ``uq_exercise_result_run_workspace_event`` taken under the
repository's advisory key, so it has to hold when requests race, not only when
they are polite. Runs against a privately named database.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from exercise_class_driver import (
    ROUND_ONE,
    TEAM_BASE,
    RecordingClient,
    build_app,
    enter,
    instructor,
    prepare_round,
    run,
    unlock,
    workspace_row,
)
from exercise_private_db import seeded_private_database
from smartmatch_persistence.exercise import schema
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

_ALREADY = "exercise_results_already_run"
_BURST = 8


@pytest.fixture(scope="module")
def sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    with seeded_private_database(engine, "onerun") as factory:
        yield factory


def _rows(sessions: sessionmaker[Session], team: int) -> int:
    table = schema.exercise_result_run
    workspace = workspace_row(sessions, team)
    with sessions() as session:
        return int(
            session.execute(
                sa.select(sa.func.count())
                .select_from(table)
                .where(table.c.workspace_id == workspace.id, table.c.event_key == ROUND_ONE)
            ).scalar_one()
        )


def _tab(app: Any, log: list, source: RecordingClient) -> RecordingClient:
    """A second browser tab: a new client carrying the same workspace cookie."""
    tab = RecordingClient(app, log)
    for cookie in source.cookies.jar:
        tab.cookies.set(cookie.name, cookie.value)
    return tab


def test_repeat_second_tab_and_reload(sessions: sessionmaker[Session]) -> None:
    app = build_app(sessions)
    log: list = []
    team = enter(app, log, 1)
    teacher = instructor(app, log)
    unlock(teacher, ROUND_ONE)
    prepare_round(team, ROUND_ONE, 1)

    first = run(team, ROUND_ONE, 1)
    assert first.status_code == 201, first.text
    again = run(team, ROUND_ONE, 1)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == _ALREADY
    tab = _tab(app, log, team)
    from_tab = run(tab, ROUND_ONE, 1)
    assert from_tab.status_code == 409
    assert from_tab.json()["error"]["code"] == _ALREADY

    stored = team.get(f"{TEAM_BASE}/events/{ROUND_ONE}/results")
    assert stored.status_code == 200
    assert stored.json() == tab.get(f"{TEAM_BASE}/events/{ROUND_ONE}/results").json()
    assert stored.json()["team"] == first.json()["team"]
    assert _rows(sessions, 1) == 1


def test_a_burst_of_concurrent_runs_stores_exactly_one(sessions: sessionmaker[Session]) -> None:
    app = build_app(sessions)
    log: list = []
    team = enter(app, log, 2)
    teacher = instructor(app, log)
    unlock(teacher, ROUND_ONE)
    prepare_round(team, ROUND_ONE, 2)
    tabs = [_tab(app, log, team) for _ in range(_BURST)]

    with ThreadPoolExecutor(max_workers=_BURST) as pool:
        responses = list(pool.map(lambda tab: run(tab, ROUND_ONE, 2), tabs))

    codes = sorted(response.status_code for response in responses)
    assert codes == [201] + [409] * (_BURST - 1), codes
    for response in responses:
        if response.status_code == 409:
            assert response.json()["error"]["code"] == _ALREADY
    assert _rows(sessions, 2) == 1
    stored = team.get(f"{TEAM_BASE}/events/{ROUND_ONE}/results").json()
    winner = next(r for r in responses if r.status_code == 201).json()
    assert stored["team"] == winner["team"]
