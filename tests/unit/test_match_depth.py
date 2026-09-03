"""Tests for the `match_depth` derived display quantity."""

from __future__ import annotations

import pytest
from smartmatch_domain.factor_registry import factor_keys, proposed_weights
from smartmatch_domain.factors import ZeroClassification
from smartmatch_domain.match_depth import (
    EngagementHistoryEvidence,
    MatchDepth,
    derive_match_depth,
)


def test_absent_history_is_unknown_not_zero():
    """G1-GC-007: engagement_ids=None -> count is None, classification UNKNOWN."""
    evidence = EngagementHistoryEvidence("SYNTH-PRO-0001", "SYNTH-UNIT-0001", None)
    depth = derive_match_depth(evidence)
    assert depth.count is None
    assert depth.is_unknown is True
    assert depth.zero_classification is ZeroClassification.UNKNOWN
    assert depth.basis == "no engagement history record for this subject and unit"


def test_recorded_empty_history_is_measured_zero():
    """G1-GC-008: engagement_ids=() -> count == 0, classification MEASURED_ZERO."""
    evidence = EngagementHistoryEvidence("SYNTH-PRO-0001", "SYNTH-UNIT-0001", ())
    depth = derive_match_depth(evidence)
    assert depth.count == 0
    assert depth.is_unknown is False
    assert depth.zero_classification is ZeroClassification.MEASURED_ZERO
    assert depth.basis == "engagement history recorded and empty for this unit"


def test_recorded_history_counts_engagements():
    evidence = EngagementHistoryEvidence(
        "SYNTH-PRO-0001",
        "SYNTH-UNIT-0001",
        ("ENG-0001", "ENG-0002", "ENG-0003"),
    )
    depth = derive_match_depth(evidence)
    assert depth.count == 3
    assert depth.zero_classification is None
    assert depth.basis == "3 recorded engagements with this unit"


def test_duplicate_engagement_id_is_rejected():
    evidence = EngagementHistoryEvidence(
        "SYNTH-PRO-0001",
        "SYNTH-UNIT-0001",
        ("ENG-0001", "ENG-0001"),
    )
    with pytest.raises(ValueError):
        derive_match_depth(evidence)


def test_negative_count_is_rejected():
    with pytest.raises(ValueError):
        MatchDepth("SYNTH-PRO-0001", "SYNTH-UNIT-0001", -1, basis="some basis")


def test_match_depth_is_not_a_registry_factor():
    assert "match_depth" not in factor_keys()
    assert "match_depth" not in proposed_weights()


def test_absent_and_empty_history_have_different_bases():
    absent = derive_match_depth(
        EngagementHistoryEvidence("SYNTH-PRO-0001", "SYNTH-UNIT-0001", None)
    )
    empty = derive_match_depth(EngagementHistoryEvidence("SYNTH-PRO-0001", "SYNTH-UNIT-0001", ()))
    assert absent.basis != empty.basis


def test_blank_subject_or_unit_id_is_rejected():
    with pytest.raises(ValueError):
        EngagementHistoryEvidence("   ", "SYNTH-UNIT-0001", None)
    with pytest.raises(ValueError):
        EngagementHistoryEvidence("SYNTH-PRO-0001", "   ", None)
    with pytest.raises(ValueError):
        MatchDepth("   ", "SYNTH-UNIT-0001", None, basis="some basis")
    with pytest.raises(ValueError):
        MatchDepth("SYNTH-PRO-0001", "   ", None, basis="some basis")
