"""Two teams working at the same time cannot see or change each other's work.

Team 1 and team 2 each hold their own cookie and go through settings, the
Northline run, the asking choice and the refresh, phase by phase with both
teams' calls in flight together. After each phase every read a team can make
is checked for the other team's data. Runs against a privately named database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from exercise_class_driver import (
    HEADER,
    ROUND_ONE,
    ROUND_TWO,
    TEAM_BASE,
    RecordingClient,
    asking_choice,
    build_app,
    enter,
    instructor,
    unlock,
)
from exercise_private_db import seeded_private_database
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

_TEAMS = (1, 2)
_KEYS = (
    "same_major",
    "stated_interest_overlap",
    "career_goal_fit",
    "past_event_topic_overlap",
)


@pytest.fixture(scope="module")
def sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    with seeded_private_database(engine, "twoteam") as factory:
        yield factory


def _weights(team: int) -> dict[str, float]:
    """A weighting only this team uses: the lean differs by team."""
    return dict(zip(_KEYS, (1.0, 1.0 + team, 2.0, float(team % 2)), strict=True))


def _setting(team: int) -> str:
    return f"team {team} only"


def _together(work: Callable[[int], Any]) -> dict[int, Any]:
    with ThreadPoolExecutor(max_workers=len(_TEAMS)) as pool:
        return dict(zip(_TEAMS, pool.map(work, _TEAMS), strict=True))


def _without_times(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _without_times(v) for k, v in value.items() if k not in {"created_at", "refreshed_at"}
        }
    if isinstance(value, list):
        return [_without_times(v) for v in value]
    return value


def test_two_teams_working_together_stay_apart(sessions: sessionmaker[Session]) -> None:
    app = build_app(sessions)
    log: list = []
    clients: dict[int, RecordingClient] = {n: enter(app, log, n) for n in _TEAMS}
    unlock(instructor(app, log), ROUND_ONE)

    # Each cookie names its own team.
    for n, client in clients.items():
        assert client.get("/v1/exercise/workspaces/current").json()["team_number"] == n

    # Phase 1: both save a setting at once. Each sees only its own name.
    def save(n: int) -> int:
        return (
            clients[n]
            .put(
                f"{TEAM_BASE}/events/{ROUND_ONE}/settings/{_setting(n)}",
                json={"weights": _weights(n)},
                headers=HEADER,
            )
            .status_code
        )

    assert _together(save) == {1: 200, 2: 200}
    for n, client in clients.items():
        saved = client.get(f"{TEAM_BASE}/events/{ROUND_ONE}/settings").json()["settings"]
        assert [s["name"] for s in saved] == [_setting(n)]
        assert saved[0]["weights"] == _weights(n)

    # A team cannot run on the other's saved name.
    other = _setting(2)
    stolen = clients[1].post(
        f"{TEAM_BASE}/events/{ROUND_ONE}/results", json={"setting_name": other}, headers=HEADER
    )
    assert stolen.status_code == 404, stolen.text

    # Phase 2: both run Northline at once; each stores its own, once.
    def go(n: int) -> Any:
        return clients[n].post(
            f"{TEAM_BASE}/events/{ROUND_ONE}/results",
            json={"setting_name": _setting(n)},
            headers=HEADER,
        )

    ran = _together(go)
    assert {n: r.status_code for n, r in ran.items()} == {1: 201, 2: 201}
    for n, client in clients.items():
        read = client.get(f"{TEAM_BASE}/events/{ROUND_ONE}/results").json()
        assert read["team"] == ran[n].json()["team"]
    assert ran[1].json()["team"] != ran[2].json()["team"]

    # Phase 3: both choose how to ask, at once. A re-choice is refused and
    # leaves the other team's choice alone.
    def ask(n: int) -> int:
        return (
            clients[n]
            .post(
                f"{TEAM_BASE}/asking-choice",
                json={"choice": asking_choice(n).value},
                headers=HEADER,
            )
            .status_code
        )

    assert _together(ask) == {1: 200, 2: 200}
    for n, client in clients.items():
        assert client.get(f"{TEAM_BASE}/asking-choice").json()["choice"] == asking_choice(n).value
    again = clients[1].post(
        f"{TEAM_BASE}/asking-choice", json={"choice": asking_choice(2).value}, headers=HEADER
    )
    assert again.status_code == 409
    assert clients[2].get(f"{TEAM_BASE}/asking-choice").json()["choice"] == asking_choice(2).value

    # Phase 4: team 1 refreshes alone. Team 2's results, asking state and every
    # list (the overlay the refresh writes to) are exactly as they were.
    watched = [
        f"{TEAM_BASE}/events/{ROUND_ONE}/results",
        f"{TEAM_BASE}/asking-choice",
        f"{TEAM_BASE}/events/{ROUND_ONE}/list",
        f"{TEAM_BASE}/events/{ROUND_TWO}/list",
        f"{TEAM_BASE}/events/{ROUND_ONE}/settings",
    ]

    def snapshot(n: int) -> list[Any]:
        return [_without_times(clients[n].get(path).json()) for path in watched]

    before = snapshot(2)
    refreshed = clients[1].post(f"{TEAM_BASE}/refresh", headers=HEADER)
    assert refreshed.status_code == 200, refreshed.text
    assert snapshot(2) == before
    assert clients[2].get(f"{TEAM_BASE}/asking-choice").json()["refreshed"] is False

    # Team 2 then refreshes; team 1's reads do not move.
    before_one = snapshot(1)
    assert clients[2].post(f"{TEAM_BASE}/refresh", headers=HEADER).status_code == 200
    assert snapshot(1) == before_one
    assert clients[1].get("/v1/exercise/workspaces/current").json()["team_number"] == 1
