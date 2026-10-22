"""Pure diff behind the two-run scenario-compare read (#306)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace as NS

from smartmatch_api.routers.match_runs import compare_runs


def _run(weights, shortlist, registry="3.0.0", solver="1"):
    return NS(
        id=uuid.uuid4(),
        weights=weights,
        registry_version=registry,
        solver_version=solver,
        shortlist=[NS(subject_id=s) for s in shortlist],
    )


def test_diff_reports_weights_versions_and_movement() -> None:
    base = _run({"a": 0.5, "b": 0.5}, ["x", "y", "z"])
    cand = _run({"a": 0.75, "c": 0.25}, ["y", "x", "w"], registry="3.1.0")

    out = compare_runs(base, cand)

    assert out.base_run_id == base.id and out.candidate_run_id == cand.id
    assert out.registry_version_equal is False and out.solver_version_equal is True
    assert out.weight_deltas == {"a": 0.25, "b": None, "c": None}
    moves = {
        m.subject_id: (m.base_rank, m.candidate_rank, m.movement) for m in out.shortlist_movement
    }
    assert moves == {
        "x": (1, 2, "moved"),
        "y": (2, 1, "moved"),
        "z": (3, None, "left"),
        "w": (None, 3, "entered"),
    }


def test_identical_runs_are_unchanged() -> None:
    run = _run({"a": 1.0}, ["x"])
    out = compare_runs(run, run)
    assert out.weight_deltas == {"a": 0.0}
    assert [m.movement for m in out.shortlist_movement] == ["unchanged"]
