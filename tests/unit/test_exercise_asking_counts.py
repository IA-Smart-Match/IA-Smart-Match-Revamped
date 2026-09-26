"""The asking route reports what the team's refresh changed, after a reload too.

M2 B4: the three refresh counts (cards filled in, stopped answering, topics
added) reached the screen only in the ``POST …/refresh`` response. A reload lost
them, and a team refreshed by the instructor's "ask for every team" never saw
them at all. ``GET …/asking-choice`` now carries ``refresh_counts``: ``null``
before the refresh, the three counts after it, read from the team's own view
so they are the same whoever pressed the button.

Uses the route fakes from ``test_exercise_results_router.py`` rather than a
second copy; that file is past the length limit, so new tests live here.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.routers.exercise_results_refresh import refresh_counts_from_view
from smartmatch_domain.exercise.simulation import SimulationCoefficients

import tests.unit.test_exercise_results_router as router_tests
from tests.unit.test_exercise_results_router import (
    _ASKING,
    _FINAL_BODY,
    _HEADER,
    _PROFILES,
    _REFRESH,
    _REFRESH_ALL,
    _RESULTS,
    _TEST_ONLY_COEFFICIENTS,
    _entered,
    _Fakes,
    _instructor,
    _prepare_refresh,
)

_COUNT_KEYS = ("cards_completed", "non_responding", "topics_added")


@pytest.fixture
def fakes() -> _Fakes:
    return _Fakes()


@pytest.fixture
def client(fakes: _Fakes) -> Iterator[TestClient]:
    with _entered(fakes, 1) as entered:
        yield entered


@pytest.fixture
def confirmed(monkeypatch: pytest.MonkeyPatch) -> SimulationCoefficients:
    """Test-only coefficients, as the router tests inject them."""
    monkeypatch.setattr(
        "smartmatch_domain.exercise.simulation.EXERCISE_SIMULATION_COEFFICIENTS",
        _TEST_ONLY_COEFFICIENTS,
    )
    return _TEST_ONLY_COEFFICIENTS


def test_there_are_no_counts_before_the_refresh(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    assert client.get(_ASKING).json()["refresh_counts"] is None
    _prepare_refresh(fakes, client)
    assert client.get(_ASKING).json()["refresh_counts"] is None


def test_the_counts_survive_a_reload(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    _prepare_refresh(fakes, client)
    posted = client.post(_REFRESH, json={}, headers=_HEADER).json()

    read = client.get(_ASKING).json()["refresh_counts"]

    assert read == {
        "cards_completed": posted["cards_completed"],
        "non_responding": posted["non_responding"],
        "topics_added": posted["topics_added"],
    }
    assert read["non_responding"] >= 1


def test_a_view_nobody_refreshed_counts_nothing() -> None:
    counts = refresh_counts_from_view(_PROFILES)
    assert (counts.cards_completed, counts.non_responding, counts.topics_added) == (0, 0, 0)


def test_a_team_the_instructor_refreshed_reads_its_counts(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """Team 2 never presses refresh; "ask for every team" does it for them.

    Every fake team shares one seed, so team 2 refreshed by the instructor must
    read exactly what team 1 was told by its own button.
    """
    fakes.unlock("round-one")
    with _entered(fakes, 1) as one, _entered(fakes, 2) as two:
        for client in (one, two):
            client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
            client.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        by_hand = one.post(_REFRESH, json={}, headers=_HEADER).json()
        assert two.get(_ASKING).json()["refresh_counts"] is None
        with _instructor(fakes) as instructor:
            refreshed = instructor.post(_REFRESH_ALL, headers=_HEADER).json()
        read = two.get(_ASKING).json()["refresh_counts"]

    assert refreshed["refreshed_team_numbers"] == [2]
    assert read == {key: by_hand[key] for key in _COUNT_KEYS}
    assert read["cards_completed"] >= 1


def test_a_round_one_with_no_topics_reports_no_topics_added_both_ways(
    fakes: _Fakes, confirmed: SimulationCoefficients, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding on #240: POST said N, GET said 0, for an empty-topic event.

    Ingest accepts an exercise event with an empty topic cell. Nobody gains a
    topic from it, so both answers must say 0.
    """
    no_topics = replace(router_tests._ROUND_ONE, topic_tags=())
    monkeypatch.setattr(
        router_tests, "_EVENTS", (router_tests._PAST, no_topics, router_tests._ROUND_TWO)
    )
    with _entered(fakes, 1) as client:
        _prepare_refresh(fakes, client)
        posted = client.post(_REFRESH, json={}, headers=_HEADER).json()
        read = client.get(_ASKING).json()["refresh_counts"]

    assert posted["topics_added"] == 0
    assert read == {key: posted[key] for key in _COUNT_KEYS}


def test_the_choice_route_answers_without_counts(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Choosing happens before any refresh, so its answer carries none."""
    fakes.unlock("round-one")
    response = client.post(_ASKING, json={"choice": "small_reward"}, headers=_HEADER)
    assert response.status_code == 200
    assert response.json()["refresh_counts"] is None
