"""Class-load fixes for the results screen (Track E, Ann #413 checklist row 95).

A stored round-two run never changes, so its before/after rows are worked out
once per run, not on every read of the results page.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.routers import exercise_results_compare
from smartmatch_domain.exercise.simulation import SimulationCoefficients

from tests.unit.exercise_results_router.conftest import (  # noqa: F401 - pytest fixtures
    client,
    confirmed,
    fakes,
)
from tests.unit.exercise_results_router.support import (
    _FINAL_BODY,
    _HEADER,
    _REFRESH,
    _RESULTS,
    _RESULTS_TWO,
    _Fakes,
    _prepare_refresh,
    _run_round_one,
)


def test_reading_results_does_not_simulate_again(
    fakes: _Fakes,  # noqa: F811
    client: TestClient,  # noqa: F811
    confirmed: SimulationCoefficients,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    real = exercise_results_compare.run_the_rule

    def counting(*args: object, **kwargs: object) -> object:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(exercise_results_compare, "run_the_rule", counting)
    _prepare_refresh(fakes, client)
    assert client.post(_REFRESH, json={}, headers=_HEADER).status_code == 200
    posted = client.post(_RESULTS_TWO, json=_FINAL_BODY, headers=_HEADER).json()
    assert len(calls) == 2  # one simulate pair: before asking + major first

    first = client.get(_RESULTS_TWO).json()
    second = client.get(_RESULTS_TWO).json()

    assert len(calls) == 2
    assert first["before_after"] == second["before_after"] == posted["before_after"]


def _count_profile_reads(held: _Fakes, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    reads: list[int] = []
    real = held.team_view.list_team_profiles

    def counting(*args: object, **kwargs: object) -> object:
        reads.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(held.team_view, "list_team_profiles", counting)
    return reads


def test_reading_round_one_results_reads_no_profiles(
    fakes: _Fakes,  # noqa: F811
    client: TestClient,  # noqa: F811
    confirmed: SimulationCoefficients,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round one has no before/after rows, so its read needs no profiles."""
    _run_round_one(fakes, client)
    reads = _count_profile_reads(fakes, monkeypatch)
    assert client.get(_RESULTS).status_code == 200
    assert reads == []


def test_rereading_round_two_results_reads_no_profiles(
    fakes: _Fakes,  # noqa: F811
    client: TestClient,  # noqa: F811
    confirmed: SimulationCoefficients,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_refresh(fakes, client)
    assert client.post(_REFRESH, json={}, headers=_HEADER).status_code == 200
    assert client.post(_RESULTS_TWO, json=_FINAL_BODY, headers=_HEADER).status_code == 201
    reads = _count_profile_reads(fakes, monkeypatch)
    assert client.get(_RESULTS_TWO).json()["before_after"] is not None
    assert reads == []


def test_a_teammates_press_waits_before_the_already_run_read(
    fakes: _Fakes,  # noqa: F811
    client: TestClient,  # noqa: F811
    confirmed: SimulationCoefficients,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Class load: the second press queues on the team key, then 409s from one read."""
    order: list[str] = []
    real_get_run = fakes.results.get_run
    real_wait = fakes.results.wait_for_teammates_run

    def get_run(*args: Any, **kwargs: Any) -> Any:
        order.append("read")
        return real_get_run(*args, **kwargs)

    def wait(*args: Any, **kwargs: Any) -> None:
        order.append("wait")
        real_wait(*args, **kwargs)

    monkeypatch.setattr(fakes.results, "get_run", get_run)
    monkeypatch.setattr(fakes.results, "wait_for_teammates_run", wait)
    _run_round_one(fakes, client)
    del order[:]
    again = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "exercise_results_already_run"
    assert order[-2:] == ["wait", "read"]
    assert fakes.results.waited == [fakes.results.waited[0]] * 2  # one team key, both presses
