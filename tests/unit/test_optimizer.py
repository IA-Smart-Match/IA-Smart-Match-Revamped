"""Tests for the CP-SAT portfolio optimizer."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import random

import ortools
import pytest
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


def test_result_is_deterministic_across_repeated_solves():
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-REPEAT",
        candidates=_FIVE_CANDIDATES,
        portfolio_size=3,
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
    tied_utility = 0.5
    candidates = (
        PortfolioCandidate(subject_id="SYNTH-PORT-TIE-C", utility=tied_utility),
        PortfolioCandidate(subject_id="SYNTH-PORT-TIE-B", utility=tied_utility),
        PortfolioCandidate(subject_id="SYNTH-PORT-TIE-A", utility=tied_utility),
    )
    request = PortfolioRequest(
        event_need_id="SYNTH-EVENT-TIE",
        candidates=candidates,
        portfolio_size=2,
    )
    result = solve_portfolio(request)
    assert result.selected_subject_ids == ("SYNTH-PORT-TIE-A", "SYNTH-PORT-TIE-B")


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
