"""Fixtures shared by the results-router tests in this directory.

Moved unchanged from ``tests/unit/test_exercise_results_router.py`` when it
was split by topic.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from smartmatch_domain.exercise.simulation import SimulationCoefficients

from tests.unit.exercise_results_router.support import (
    _TEST_ONLY_COEFFICIENTS,
    _entered,
    _Fakes,
)


@pytest.fixture
def fakes() -> _Fakes:
    return _Fakes()


@pytest.fixture
def confirmed(monkeypatch: pytest.MonkeyPatch) -> SimulationCoefficients:
    """Inject **test-only** coefficients, so no outcome here moves with the shipped set.

    Patched onto the domain module rather than written into it: the shipped
    value is the approved set (D7), pinned in
    ``tests/unit/test_exercise_coefficients_approved.py``.
    """
    monkeypatch.setattr(
        "smartmatch_domain.exercise.simulation.EXERCISE_SIMULATION_COEFFICIENTS",
        _TEST_ONLY_COEFFICIENTS,
    )
    return _TEST_ONLY_COEFFICIENTS


@pytest.fixture
def client(fakes: _Fakes) -> Iterator[TestClient]:
    with _entered(fakes, 1) as entered:
        yield entered
