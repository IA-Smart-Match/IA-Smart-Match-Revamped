"""Tests for the Stage B scoring entry point (the registry join)."""

from __future__ import annotations

import pytest
from smartmatch_domain import factor_registry, scoring
from smartmatch_domain.factor_registry import (
    REGISTRY_VERSION,
    RegistryNotApprovedError,
    RegistryNotReadyError,
)
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.factors.topic_relevance import TopicRelevanceInputs
from smartmatch_domain.factors.travel_burden import GeoPoint, TravelInputs
from smartmatch_domain.scoring import (
    STAGE_B_FORMULA_VERSION,
    CandidateEvidence,
    rank_candidates,
    score_candidate,
)

LOS_ANGELES = GeoPoint(34.0522, -118.2437)


def _evidence(
    subject_id: str,
    *,
    expertise_topics: tuple[str, ...] | None = ("artificial_intelligence",),
    required_topics: tuple[str, ...] = ("artificial_intelligence",),
    preferred_topics: tuple[str, ...] = (),
    origin: GeoPoint | None = LOS_ANGELES,
    destination: GeoPoint | None = LOS_ANGELES,
) -> CandidateEvidence:
    """A candidate that is a perfect topic + zero-distance match by default."""
    return CandidateEvidence(
        subject_id=subject_id,
        topic=TopicRelevanceInputs(
            expertise_topics=expertise_topics,
            required_topics=required_topics,
            preferred_topics=preferred_topics,
        ),
        travel=TravelInputs(origin=origin, destination=destination),
    )


def test_score_candidate_calls_the_registry_guards_first(monkeypatch):
    call_log: list[str] = []

    def fake_registry_approved() -> None:
        call_log.append("assert_registry_approved")

    def fake_scoring_ready() -> None:
        call_log.append("assert_scoring_ready")

    def fake_score_topic_relevance(inputs: TopicRelevanceInputs) -> FactorScore:
        call_log.append("score_topic_relevance")
        return FactorScore("topic_relevance", 1.0, basis="patched for test")

    def fake_score_travel_burden(inputs: TravelInputs) -> FactorScore:
        call_log.append("score_travel_burden")
        return FactorScore("travel_burden", 0.0, basis="patched for test")

    monkeypatch.setattr(scoring, "assert_registry_approved", fake_registry_approved)
    monkeypatch.setattr(scoring, "assert_scoring_ready", fake_scoring_ready)
    monkeypatch.setattr(scoring, "score_topic_relevance", fake_score_topic_relevance)
    monkeypatch.setattr(scoring, "score_travel_burden", fake_score_travel_burden)

    score_candidate(_evidence("SYNTH-PRO-GUARD"))

    assert call_log[:2] == ["assert_registry_approved", "assert_scoring_ready"]
    assert set(call_log[2:]) == {"score_topic_relevance", "score_travel_burden"}


def test_applied_weights_are_the_normalized_registry_weights():
    result = score_candidate(_evidence("SYNTH-PRO-WEIGHTS"))
    assert result.applied_weights == {
        "topic_relevance": pytest.approx(0.70),
        "travel_burden": pytest.approx(0.30),
    }
    assert sum(result.applied_weights.values()) == pytest.approx(1.0)


def test_weights_are_normalized_on_apply_not_hardcoded():
    result = score_candidate(
        _evidence("SYNTH-PRO-OVERRIDE"),
        weight_overrides={"topic_relevance": 7.0, "travel_burden": 3.0},
    )
    assert result.applied_weights == {
        "topic_relevance": pytest.approx(0.70),
        "travel_burden": pytest.approx(0.30),
    }


def test_perfect_candidate_scores_one():
    result = score_candidate(_evidence("SYNTH-PRO-PERFECT"))
    assert result.value == pytest.approx(1.0)


def test_disjoint_topics_and_zero_distance_scores_the_penalty_weight():
    result = score_candidate(
        _evidence("SYNTH-PRO-DISJOINT", expertise_topics=("municipal_finance",))
    )
    assert result.value == pytest.approx(0.3)


def test_unknown_topic_relevance_makes_the_composite_unknown():
    result = score_candidate(_evidence("SYNTH-PRO-UNKNOWN-TOPIC", expertise_topics=None))
    assert result.value is None
    assert result.unknown_factor_keys == ("topic_relevance",)


def test_unknown_travel_makes_the_composite_unknown():
    result = score_candidate(_evidence("SYNTH-PRO-UNKNOWN-TRAVEL", origin=None))
    assert result.value is None
    assert result.unknown_factor_keys == ("travel_burden",)


def test_measured_zero_and_unknown_produce_different_composites():
    disjoint = score_candidate(
        _evidence("SYNTH-PRO-MEASURED-ZERO", expertise_topics=("municipal_finance",))
    )
    absent = score_candidate(_evidence("SYNTH-PRO-ABSENT", expertise_topics=None))
    assert disjoint.value == pytest.approx(0.3)
    assert absent.value is None
    assert disjoint.value != absent.value


def test_unknown_factors_are_still_reported_in_factor_scores():
    result = score_candidate(_evidence("SYNTH-PRO-REPORTED", expertise_topics=None))
    assert [fs.factor_key for fs in result.factor_scores] == ["topic_relevance", "travel_burden"]
    assert result.factor_scores[0].is_unknown is True
    assert result.factor_scores[1].is_unknown is False


@pytest.mark.parametrize(
    ("expertise_topics", "destination"),
    [
        (("artificial_intelligence",), LOS_ANGELES),
        (("municipal_finance",), GeoPoint(35.0522, -118.2437)),
        ((), GeoPoint(36.0522, -118.2437)),
        (("artificial_intelligence", "machine_learning"), GeoPoint(34.0522, -119.2437)),
    ],
)
def test_composite_is_always_within_bounds(expertise_topics, destination):
    result = score_candidate(
        _evidence("SYNTH-PRO-BOUNDS", expertise_topics=expertise_topics, destination=destination)
    )
    if result.value is not None:
        assert 0.0 <= result.value <= 1.0


def test_penalty_enters_as_its_complement():
    near = score_candidate(_evidence("SYNTH-PRO-NEAR"))
    far = score_candidate(_evidence("SYNTH-PRO-FAR", destination=GeoPoint(34.2522, -118.2437)))
    assert far.value < near.value


def test_ranking_breaks_ties_lexicographically_by_subject_id():
    second = _evidence(
        "SYNTH-PRO-0002",
        expertise_topics=("artificial_intelligence", "machine_learning"),
        required_topics=("artificial_intelligence",),
        preferred_topics=("machine_learning",),
    )
    first = _evidence(
        "SYNTH-PRO-0001",
        expertise_topics=("artificial_intelligence", "machine_learning"),
        required_topics=("artificial_intelligence",),
        preferred_topics=("machine_learning",),
    )
    ranked = rank_candidates([second, first])
    assert [result.subject_id for result in ranked] == ["SYNTH-PRO-0001", "SYNTH-PRO-0002"]


def test_ranking_orders_by_descending_value_before_the_tie_break():
    low = _evidence("SYNTH-PRO-LOW", expertise_topics=("municipal_finance",))
    high = _evidence("SYNTH-PRO-HIGH")
    mid = _evidence("SYNTH-PRO-MID", destination=GeoPoint(34.2522, -118.2437))
    ranked = rank_candidates([low, high, mid])
    assert [result.subject_id for result in ranked] == [
        "SYNTH-PRO-HIGH",
        "SYNTH-PRO-MID",
        "SYNTH-PRO-LOW",
    ]


def test_unknown_candidates_rank_last_and_are_not_treated_as_zero():
    zero_candidate = _evidence(
        "SYNTH-PRO-ZERO",
        expertise_topics=("municipal_finance",),
        destination=GeoPoint(36.0522, -118.2437),
    )
    unknown_candidate = _evidence("SYNTH-PRO-UNKNOWN", expertise_topics=None)
    ranked = rank_candidates([unknown_candidate, zero_candidate])
    assert [result.subject_id for result in ranked] == ["SYNTH-PRO-ZERO", "SYNTH-PRO-UNKNOWN"]
    assert ranked[0].value == pytest.approx(0.0)
    assert ranked[1].value is None


def test_duplicate_subject_id_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        rank_candidates([_evidence("SYNTH-PRO-DUP"), _evidence("SYNTH-PRO-DUP")])


def test_result_records_registry_and_formula_versions():
    result = score_candidate(_evidence("SYNTH-PRO-VERSIONS"))
    assert result.registry_version == REGISTRY_VERSION
    assert result.registry_version == "1.1.1-approved-g1-m6j"
    assert result.formula_version == STAGE_B_FORMULA_VERSION


def test_scoring_raises_when_the_registry_is_not_approved(monkeypatch):
    monkeypatch.setattr(factor_registry, "REGISTRY_STATUS", "proposed")
    with pytest.raises(RegistryNotApprovedError):
        score_candidate(_evidence("SYNTH-PRO-NOT-APPROVED"))


def test_scoring_raises_when_an_approved_factor_is_unimplemented(monkeypatch):
    monkeypatch.setattr(
        factor_registry,
        "implemented_scoring_keys",
        lambda: frozenset({"topic_relevance"}),
    )
    with pytest.raises(RegistryNotReadyError):
        score_candidate(_evidence("SYNTH-PRO-NOT-READY"))
