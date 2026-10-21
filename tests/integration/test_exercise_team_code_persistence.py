"""The 4-digit team code against PostgreSQL (issue #413, revision 0048).

The migration seeds six codes, entry checks the stored one, and an instructor
reset writes a new one. Runs against a privately named database.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from exercise_class_driver import HEADER, INSTRUCTOR_BASE, build_app, enter, instructor, team_code
from exercise_private_db import seeded_private_database
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    with seeded_private_database(engine, "pin") as factory:
        yield factory


def _stored(sessions: sessionmaker[Session]) -> dict[int, str]:
    with sessions() as session:
        rows = session.execute(text("SELECT team_number, code FROM exercise_team_code"))
        return {team: code for team, code in rows}


def test_the_migration_gives_each_of_six_teams_a_four_digit_code(
    sessions: sessionmaker[Session],
) -> None:
    codes = _stored(sessions)
    assert sorted(codes) == [1, 2, 3, 4, 5, 6]
    assert all(re.fullmatch(r"[0-9]{4}", code) for code in codes.values())


def test_the_instructor_api_shows_the_stored_codes(sessions: sessionmaker[Session]) -> None:
    app = build_app(sessions)
    shown = {n: team_code(app, [], n) for n in range(1, 7)}
    assert shown == _stored(sessions)


def test_entry_needs_the_stored_code(sessions: sessionmaker[Session]) -> None:
    app = build_app(sessions)
    wrong = "0000" if _stored(sessions)[5] != "0000" else "1111"
    client = TestClient(app)
    refused = client.post(
        "/v1/exercise/workspaces", json={"team_number": 5, "code": wrong}, headers=HEADER
    )
    assert refused.status_code == 401
    assert enter(app, [], 5).get("/v1/exercise/workspaces/current").status_code == 200


def test_a_reset_writes_a_new_code(sessions: sessionmaker[Session]) -> None:
    app = build_app(sessions)
    enter(app, [], 2)
    before = _stored(sessions)
    teacher = instructor(app, [])
    for _ in range(3):  # a new random code can equal the old one 1 time in 10,000
        response = teacher.post(f"{INSTRUCTOR_BASE}/workspaces/2/reset", headers=HEADER)
        assert response.status_code == 200, response.text
        if _stored(sessions)[2] != before[2]:
            break
    after = _stored(sessions)
    assert after[2] != before[2]
    assert {n: c for n, c in after.items() if n != 2} == {n: c for n, c in before.items() if n != 2}
