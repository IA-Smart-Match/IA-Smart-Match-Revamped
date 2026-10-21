"""The 4-digit team code (issue #413): entry needs it, the instructor sees it.

The database half (migration backfill, reset rotating the stored row) is in
``tests/integration/test_exercise_team_code.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.exercise_dependencies import EXERCISE_REQUEST_HEADER, WORKSPACE_COOKIE_NAME
from smartmatch_api.exercise_rate_limit import WrongCodeGuard
from smartmatch_api.routers import exercise_workspace
from smartmatch_api.routers.exercise_workspace import CODE_LOCKED_SENTENCE, WRONG_CODE_SENTENCE

from tests.unit.exercise_team_codes import fake_code
from tests.unit.test_exercise_instructor_router import _exercise_app as instructor_app
from tests.unit.test_exercise_instructor_router import (
    _login,
    state,  # noqa: F401 - fixture
)
from tests.unit.test_exercise_instructor_router import _settings as instructor_settings
from tests.unit.test_exercise_workspace_router import (
    _exercise_app,
    _FakeRepository,
    _settings,
)

_HEADER = {EXERCISE_REQUEST_HEADER: "1"}


@pytest.fixture(autouse=True)
def fresh_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real guard is module-level and would carry counts between tests."""
    monkeypatch.setattr(exercise_workspace, "_CODE_GUARD", WrongCodeGuard())


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_exercise_app(_settings(), _FakeRepository())) as test_client:
        yield test_client


def _enter(client: TestClient, team: int, code: str | None) -> Any:
    body: dict[str, Any] = {"team_number": team}
    if code is not None:
        body["code"] = code
    return client.post("/v1/exercise/workspaces", json=body, headers=_HEADER)


def test_the_right_code_opens_the_team_and_sets_the_cookie(client: TestClient) -> None:
    response = _enter(client, 3, fake_code(3))
    assert response.status_code == 200
    assert client.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise")


def test_a_missing_code_is_refused(client: TestClient) -> None:
    response = _enter(client, 3, None)
    assert response.status_code == 422
    assert client.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise") is None


@pytest.mark.parametrize("code", ["0000", fake_code(4), "", "abcd", "é303"])
def test_a_wrong_code_is_refused_with_one_sentence(client: TestClient, code: str) -> None:
    response = _enter(client, 3, code)
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "exercise_team_code_wrong", "message": WRONG_CODE_SENTENCE}
    }
    assert client.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise") is None


def test_five_wrong_codes_lock_that_team_even_for_the_right_code(client: TestClient) -> None:
    for _ in range(5):
        assert _enter(client, 3, "0000").status_code == 401
    locked = _enter(client, 3, fake_code(3))
    assert locked.status_code == 429
    assert locked.json() == {
        "error": {"code": "exercise_team_code_locked", "message": CODE_LOCKED_SENTENCE}
    }
    # Another team is not locked by team 3's wrong codes.
    assert _enter(client, 4, fake_code(4)).status_code == 200


def test_a_reload_with_the_cookie_needs_no_code(client: TestClient) -> None:
    assert _enter(client, 2, fake_code(2)).status_code == 200
    current = client.get("/v1/exercise/workspaces/current")
    assert current.status_code == 200
    assert current.json()["team_number"] == 2


def test_a_browser_with_no_cookie_must_enter_the_code_again(client: TestClient) -> None:
    assert _enter(client, 2, fake_code(2)).status_code == 200
    client.cookies.clear()
    assert client.get("/v1/exercise/workspaces/current").status_code == 401
    assert _enter(client, 2, "1111").status_code == 401


def test_a_student_cookie_cannot_read_the_codes(client: TestClient) -> None:
    assert _enter(client, 1, fake_code(1)).status_code == 200
    response = client.get("/v1/exercise/instructor/team-codes")
    assert response.status_code == 401
    assert fake_code(1) not in response.text


def test_the_instructor_reads_all_six_codes(state: dict[str, Any]) -> None:  # noqa: F811
    with TestClient(instructor_app(instructor_settings(), state)) as client:
        assert client.get("/v1/exercise/instructor/team-codes").status_code == 401
        assert _login(client).status_code == 200
        response = client.get("/v1/exercise/instructor/team-codes")
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
    assert body == {"teams": [{"team_number": n, "code": fake_code(n)} for n in range(1, 7)]}


def test_a_reset_gives_the_team_a_new_code(state: dict[str, Any]) -> None:  # noqa: F811
    with TestClient(instructor_app(instructor_settings(), state)) as client:
        assert _login(client).status_code == 200
        response = client.post("/v1/exercise/instructor/workspaces/3/reset", headers=_HEADER)
    assert response.status_code == 200
    assert state["codes"].rotated == [3]
    assert state["codes"].codes[3] != fake_code(3)


# ---------------------------------------------------------------------------
# The guard on its own clock
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)


def test_the_lockout_lifts_after_sixty_seconds() -> None:
    guard = WrongCodeGuard()
    for i in range(5):
        assert guard.attempt("3:ip", correct=False, now=_T0 + timedelta(seconds=i))
    last = _T0 + timedelta(seconds=4)
    assert not guard.attempt("3:ip", correct=True, now=last + timedelta(seconds=59))
    assert guard.attempt("3:ip", correct=True, now=last + timedelta(seconds=60))


def test_a_wrong_code_after_the_lockout_locks_again_inside_the_window() -> None:
    guard = WrongCodeGuard()
    for i in range(5):
        guard.attempt("3:ip", correct=False, now=_T0 + timedelta(seconds=i))
    retry = _T0 + timedelta(seconds=70)
    assert guard.attempt("3:ip", correct=False, now=retry)
    assert not guard.attempt("3:ip", correct=True, now=retry + timedelta(seconds=30))


def test_wrong_codes_older_than_ten_minutes_are_forgotten() -> None:
    guard = WrongCodeGuard()
    for i in range(4):
        guard.attempt("3:ip", correct=False, now=_T0 + timedelta(seconds=i))
    later = _T0 + timedelta(minutes=10, seconds=5)
    assert guard.attempt("3:ip", correct=False, now=later)
    assert guard.attempt("3:ip", correct=True, now=later + timedelta(seconds=1))


def test_right_codes_are_never_counted() -> None:
    guard = WrongCodeGuard()
    assert all(guard.attempt("3:ip", correct=True, now=_T0) for _ in range(50))
