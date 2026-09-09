"""Tests for the topic_relevance scoring factor."""

from __future__ import annotations

import pytest
from smartmatch_domain.factor_registry import factor_keys
from smartmatch_domain.factors import FactorScore, ZeroClassification
from smartmatch_domain.factors.topic_relevance import (
    PREFERRED_TOPIC_SUBWEIGHT,
    REQUIRED_TOPIC_SUBWEIGHT,
    TopicRelevanceInputs,
    score_topic_relevance,
)


def _inputs(**overrides: object) -> TopicRelevanceInputs:
    base: dict[str, object] = {
        "expertise_topics": (),
        "required_topics": (),
        "preferred_topics": (),
    }
    base.update(overrides)
    return TopicRelevanceInputs(**base)  # type: ignore[arg-type]


def test_absent_expertise_record_is_unknown_not_zero():
    result = score_topic_relevance(
        _inputs(expertise_topics=None, required_topics=("artificial_intelligence",))
    )
    assert result.value is None
    assert result.is_unknown is True
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_recorded_disjoint_topics_are_measured_zero():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("municipal_finance", "public_procurement"),
            required_topics=("artificial_intelligence",),
            preferred_topics=("machine_learning",),
        )
    )
    assert result.value == pytest.approx(0.0)
    assert result.zero_classification is ZeroClassification.MEASURED_ZERO


def test_recorded_empty_expertise_is_measured_zero():
    result = score_topic_relevance(
        _inputs(expertise_topics=(), required_topics=("artificial_intelligence",))
    )
    assert result.value == pytest.approx(0.0)
    assert result.zero_classification is ZeroClassification.MEASURED_ZERO


def test_full_required_and_preferred_coverage_scores_one():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("artificial_intelligence", "machine_learning"),
            required_topics=("artificial_intelligence",),
            preferred_topics=("machine_learning",),
        )
    )
    assert result.value == pytest.approx(1.0)


def test_required_only_coverage_scores_the_required_subweight():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("artificial_intelligence",),
            required_topics=("artificial_intelligence",),
            preferred_topics=("machine_learning",),
        )
    )
    assert result.value == pytest.approx(REQUIRED_TOPIC_SUBWEIGHT)


def test_preferred_only_coverage_scores_the_preferred_subweight():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("machine_learning",),
            required_topics=("artificial_intelligence",),
            preferred_topics=("machine_learning",),
        )
    )
    assert result.value == pytest.approx(PREFERRED_TOPIC_SUBWEIGHT)


def test_partial_required_coverage_is_proportional():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("a",),
            required_topics=("a", "b"),
            preferred_topics=(),
        )
    )
    assert result.value == pytest.approx(0.5)


def test_event_with_no_topics_is_unknown():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("artificial_intelligence",),
            required_topics=(),
            preferred_topics=(),
        )
    )
    assert result.value is None
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_no_required_topics_falls_back_to_preferred_only():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("machine_learning",),
            required_topics=(),
            preferred_topics=("machine_learning",),
        )
    )
    assert result.value == pytest.approx(1.0)


def test_topic_matching_is_case_and_whitespace_insensitive():
    result = score_topic_relevance(
        _inputs(
            expertise_topics=("  Artificial_Intelligence ",),
            required_topics=("artificial_intelligence",),
            preferred_topics=(),
        )
    )
    assert result.value == pytest.approx(1.0)


def test_duplicate_topics_do_not_change_the_score():
    deduplicated = score_topic_relevance(
        _inputs(
            expertise_topics=("artificial_intelligence",),
            required_topics=("artificial_intelligence", "machine_learning"),
            preferred_topics=(),
        )
    )
    duplicated = score_topic_relevance(
        _inputs(
            expertise_topics=("artificial_intelligence", "artificial_intelligence"),
            required_topics=(
                "artificial_intelligence",
                "machine_learning",
                "machine_learning",
            ),
            preferred_topics=(),
        )
    )
    assert duplicated.value == pytest.approx(deduplicated.value)


def test_subweights_sum_to_one():
    assert pytest.approx(1.0) == REQUIRED_TOPIC_SUBWEIGHT + PREFERRED_TOPIC_SUBWEIGHT


def test_value_is_always_within_bounds():
    cases = [
        _inputs(expertise_topics=None, required_topics=("a",)),
        _inputs(expertise_topics=(), required_topics=("a",)),
        _inputs(expertise_topics=("a",), required_topics=("a",), preferred_topics=("b",)),
        _inputs(expertise_topics=("b",), required_topics=("a",), preferred_topics=("b",)),
        _inputs(expertise_topics=("a", "b"), required_topics=("a",), preferred_topics=("b",)),
        _inputs(expertise_topics=("c",), required_topics=(), preferred_topics=()),
        _inputs(expertise_topics=("a",), required_topics=("a", "b", "c")),
    ]
    for case in cases:
        result = score_topic_relevance(case)
        assert result.value is None or 0.0 <= result.value <= 1.0


def test_blank_topic_string_is_rejected():
    with pytest.raises(ValueError, match="topic strings must not be empty"):
        _inputs(expertise_topics=("   ",), required_topics=("a",))


def test_factor_key_is_declared_in_the_registry():
    assert "topic_relevance" in factor_keys()


def test_factor_score_rejects_out_of_range_value():
    with pytest.raises(ValueError, match="value must be in"):
        FactorScore("topic_relevance", 1.5, basis="test")


def test_factor_score_rejects_empty_basis():
    with pytest.raises(ValueError, match="basis must be a non-empty"):
        FactorScore("topic_relevance", 0.5, basis="   ")


def test_factor_score_zero_classification_is_none_for_a_positive_value():
    result = FactorScore("topic_relevance", 0.5, basis="test")
    assert result.zero_classification is None
