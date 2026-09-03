"""Tests for the CP-SAT portfolio optimizer."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import random

import ortools
import pytest
from ortools.sat.python import cp_model
from smartmatch_domain import optimizer as optimizer_module
from smartmatch_domain.factors.topic_relevance import TopicRelevanceInputs
from smartmatch_domain.factors.travel_burden import GeoPoint, TravelInputs
from smartmatch_domain.optimizer import (
    OPTIMIZER_MODEL_VERSION,
    SOLVER_NAME,
    PortfolioCandidate,
    PortfolioRequest,
    PortfolioStatus,
    solve_portfolio,
)
from smartmatch_domain.scoring import CandidateEvidence, rank_candidates

LOS_ANGELES = GeoPoint(34.0522, -118.2437)
NEW_YORK = GeoPoint(40.7128, -74.0060)

#: Five candidates with distinct utilities, deliberately not in id order, so
#: that "top N" and "first N" disagree unless the optimizer actually ranks by
#: utility.
_FIVE_CANDIDATES = (
    PortfolioCandidate(subject_id="SYNTH-PORT-E", utility=0.95),
    PortfolioCandidate(subject_id="SYNTH-PORT-A", utility=0.10),
    PortfolioCandidate(subject_id="SYNTH-PORT-C", utility=0.80),
    PortfolioCandidate(subject_id="SYNTH-PORT-B", utility=0.65),
    PortfolioCandidate(subject_id="SYNTH-PORT-D", utility=0.50),
)

#: Three candidates with identical utility, supplied in reverse id order, so
#: a pass can only be explained by the tie-break actually running — used both
#: to test the tie-break directly and to test that a genuinely tied problem
#: (not just a problem with a unique optimum) is deterministic across repeat
#: solves, which a nondeterministic multi-worker search could pass by luck.
_TIED_UTILITY = 0.5
_TIED_CANDIDATES = (
    PortfolioCandidate(subject_id="SYNTH-PORT-TIE-C", utility=_TIED_UTILITY),
    PortfolioCandidate(subject_id="SYNTH-PORT-TIE-B", utility=_TIED_UTILITY),
    PortfolioCandidate(subject_id="SYNTH-PORT-TIE-A", utility=_TIED_UTILITY),
)


def test_selects_the_highest_utility_candidates():
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-TOP3",
        candidates=_FIVE_CANDIDATES,
        portfolio_size=3,
    )
    result = solve_portfolio(request)
    assert result.selected_subject_ids == (
        "SYNTH-PORT-B",
        "SYNTH-PORT-C",
        "SYNTH-PORT-E",
    )
    assert result.status == PortfolioStatus.OPTIMAL


@pytest.mark.parametrize("size", [1, 2, 3, 4])
def test_portfolio_size_is_a_parameter_not_a_constant(size):
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-SIZE",
        candidates=_FIVE_CANDIDATES,
        portfolio_size=size,
    )
    result = solve_portfolio(request)
    assert len(result.selected_subject_ids) == size
    assert result.portfolio_size == size


def test_no_two_or_three_is_hardcoded():
    source = inspect.getsource(optimizer_module)
    tree = ast.parse(source)
    int_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    }
    assert 2 not in int_literals
    assert 3 not in int_literals

    portfolio_size_field = next(
        field for field in dataclasses.fields(PortfolioRequest) if field.name == "portfolio_size"
    )
    assert portfolio_size_field.default is dataclasses.MISSING
    assert portfolio_size_field.default_factory is dataclasses.MISSING


def test_portfolio_size_larger_than_the_candidate_pool_returns_everyone():
    candidates = (
        PortfolioCandidate(subject_id="SYNTH-PORT-ONLY-B", utility=0.4),
        PortfolioCandidate(subject_id="SYNTH-PORT-ONLY-A", utility=0.9),
    )
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-OVERSIZED",
        candidates=candidates,
        portfolio_size=5,
    )
    result = solve_portfolio(request)
    assert result.selected_subject_ids == ("SYNTH-PORT-ONLY-A", "SYNTH-PORT-ONLY-B")
    assert result.status == PortfolioStatus.OPTIMAL


def test_empty_candidate_pool_returns_an_empty_portfolio():
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-EMPTY",
        candidates=(),
        portfolio_size=3,
    )
    result = solve_portfolio(request)
    assert result.selected_subject_ids == ()
    assert result.objective_value == 0
    assert result.status == PortfolioStatus.OPTIMAL


@pytest.mark.parametrize(
    ("candidates", "portfolio_size"),
    [
        pytest.param(_FIVE_CANDIDATES, 3, id="unique_optimum"),
        pytest.param(_TIED_CANDIDATES, 2, id="tied_optimum"),
    ],
)
def test_result_is_deterministic_across_repeated_solves(candidates, portfolio_size):
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-REPEAT",
        candidates=candidates,
        portfolio_size=portfolio_size,
        random_seed=7,
    )
    results = [solve_portfolio(request) for _ in range(20)]
    first = results[0]
    for result in results[1:]:
        assert result.selected_subject_ids == first.selected_subject_ids
        assert result.objective_value == first.objective_value
        assert result.status == first.status


def test_result_is_deterministic_regardless_of_input_order():
    shuffled = list(_FIVE_CANDIDATES)
    random.Random(1234).shuffle(shuffled)
    assert tuple(shuffled) != _FIVE_CANDIDATES  # sanity: the shuffle actually moved things

    original_request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-ORDER",
        candidates=_FIVE_CANDIDATES,
        portfolio_size=3,
        random_seed=3,
    )
    shuffled_request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-ORDER",
        candidates=tuple(shuffled),
        portfolio_size=3,
        random_seed=3,
    )
    original_result = solve_portfolio(original_request)
    shuffled_result = solve_portfolio(shuffled_request)
    assert original_result.selected_subject_ids == shuffled_result.selected_subject_ids
    assert original_result.objective_value == shuffled_result.objective_value


def test_ties_are_broken_lexicographically_by_subject_id():
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-TIE",
        candidates=_TIED_CANDIDATES,
        portfolio_size=2,
    )
    result = solve_portfolio(request)
    assert result.selected_subject_ids == ("SYNTH-PORT-TIE-A", "SYNTH-PORT-TIE-B")


def test_infeasible_solve_status_is_reported_as_infeasible(monkeypatch):
    monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda self, model: cp_model.INFEASIBLE)
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-STATUS-INFEASIBLE",
        candidates=_FIVE_CANDIDATES,
        portfolio_size=3,
    )
    result = solve_portfolio(request)
    assert result.status == PortfolioStatus.INFEASIBLE
    assert result.selected_subject_ids == ()
    assert result.objective_value == 0


@pytest.mark.parametrize("raw_status", [cp_model.UNKNOWN, cp_model.MODEL_INVALID])
def test_a_stalled_or_invalid_search_is_reported_as_unknown_not_infeasible(monkeypatch, raw_status):
    monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda self, model: raw_status)
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-STATUS-UNKNOWN",
        candidates=_FIVE_CANDIDATES,
        portfolio_size=3,
    )
    result = solve_portfolio(request)
    assert result.status == PortfolioStatus.UNKNOWN
    assert result.selected_subject_ids == ()
    assert result.objective_value == 0


def test_result_records_the_solver_version():
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-VERSION",
        candidates=_FIVE_CANDIDATES,
        portfolio_size=2,
        random_seed=42,
    )
    result = solve_portfolio(request)
    assert result.solver_name == SOLVER_NAME
    assert result.solver_version == ortools.__version__
    assert result.solver_version != ""
    assert result.model_version == OPTIMIZER_MODEL_VERSION
    assert result.random_seed == 42


def test_unknown_utility_is_rejected_never_coerced_to_zero():
    with pytest.raises(ValueError):
        PortfolioCandidate(subject_id="SYNTH-PORT-UNKNOWN", utility=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PortfolioCandidate(subject_id="SYNTH-PORT-NAN", utility=float("nan"))


@pytest.mark.parametrize("utility", [-0.1, 1.1])
def test_utility_out_of_range_is_rejected(utility):
    with pytest.raises(ValueError):
        PortfolioCandidate(subject_id="SYNTH-PORT-OOR", utility=utility)


@pytest.mark.parametrize("utility", [True, False])
def test_utility_bool_is_rejected(utility):
    # bool is a subclass of int and duck-types as a float in comparisons, so
    # True/False would silently pass the [0.0, 1.0] range check as 1.0/0.0
    # unless rejected by type explicitly.
    with pytest.raises(ValueError):
        PortfolioCandidate(subject_id="SYNTH-PORT-BOOL", utility=utility)  # type: ignore[arg-type]


def test_duplicate_subject_id_is_rejected():
    candidates = (
        PortfolioCandidate(subject_id="SYNTH-PORT-DUP", utility=0.5),
        PortfolioCandidate(subject_id="SYNTH-PORT-DUP", utility=0.6),
    )
    with pytest.raises(ValueError):
        PortfolioRequest(
            event_need_id="SYNTH-EVENT-DUP",
            candidates=candidates,
            portfolio_size=1,
        )


@pytest.mark.parametrize("size", [0, -1])
def test_portfolio_size_below_one_is_rejected(size):
    with pytest.raises(ValueError):
        PortfolioRequest(
            event_need_id="SYNTH-EVENT-BADSIZE",
            candidates=_FIVE_CANDIDATES,
            portfolio_size=size,
        )


@pytest.mark.parametrize("size", [True, False])
def test_portfolio_size_bool_is_rejected(size):
    # bool is a subclass of int, so True/False would silently pass the >= 1
    # check as 1/0 unless rejected by type explicitly.
    with pytest.raises(ValueError):
        PortfolioRequest(
            event_need_id="SYNTH-EVENT-BOOL-SIZE",
            candidates=_FIVE_CANDIDATES,
            portfolio_size=size,  # type: ignore[arg-type]
        )


def test_no_llm_or_network_import():
    source = inspect.getsource(optimizer_module)
    tree = ast.parse(source)

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    allowed_roots = {"__future__", "dataclasses", "enum", "typing", "ortools", "smartmatch_domain"}
    assert imported_roots <= allowed_roots

    forbidden_modules = {
        "openai",
        "anthropic",
        "google.generativeai",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "os",
    }
    for forbidden in forbidden_modules:
        assert forbidden.split(".")[0] not in imported_roots


def test_integrates_with_stage_b_scores():
    strong = CandidateEvidence(
        subject_id="SYNTH-PRO-STRONG",
        topic=TopicRelevanceInputs(
            expertise_topics=("artificial_intelligence",),
            required_topics=("artificial_intelligence",),
        ),
        travel=TravelInputs(origin=LOS_ANGELES, destination=LOS_ANGELES),
    )
    weak = CandidateEvidence(
        subject_id="SYNTH-PRO-WEAK",
        topic=TopicRelevanceInputs(
            expertise_topics=("robotics",),
            required_topics=("artificial_intelligence",),
        ),
        travel=TravelInputs(origin=NEW_YORK, destination=LOS_ANGELES),
    )

    ranked = rank_candidates([strong, weak])
    known = [candidate for candidate in ranked if candidate.value is not None]
    assert len(known) >= 1  # sanity: the fixture must yield at least one known value

    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-INTEGRATION",
        candidates=tuple(
            PortfolioCandidate(subject_id=candidate.subject_id, utility=candidate.value)
            for candidate in known
        ),
        portfolio_size=1,
    )
    result = solve_portfolio(request)
    assert result.selected_subject_ids == (known[0].subject_id,)
