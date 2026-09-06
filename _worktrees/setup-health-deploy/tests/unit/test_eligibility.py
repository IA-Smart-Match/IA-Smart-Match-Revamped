"""Tests for the Stage A `availability` eligibility filter."""

from __future__ import annotations

import pytest
from smartmatch_domain.eligibility import (
    AVAILABILITY_STAGE_B_WEIGHT,
    AvailabilityEvidence,
    AvailabilityState,
    EligibilityDecision,
    EligibilityOutcome,
    apply_availability_filter,
)
from smartmatch_domain.factor_registry import (
    PROPOSED_FACTORS,
    FactorKind,
    normalize_weights,
)


def test_available_subject_is_eligible():
    shortlist = ("SYNTH-PRO-0001",)
    evidence = {
        "SYNTH-PRO-0001": AvailabilityEvidence("SYNTH-PRO-0001", AvailabilityState.AVAILABLE),
    }
    decisions = apply_availability_filter(shortlist, evidence)
    assert decisions == (
        EligibilityDecision(
            "SYNTH-PRO-0001",
            EligibilityOutcome.ELIGIBLE,
            reason="availability recorded as available",
        ),
    )


def test_blacked_out_subject_is_excluded():
    shortlist = ("SYNTH-PRO-0001",)
    evidence = {
        "SYNTH-PRO-0001": AvailabilityEvidence("SYNTH-PRO-0001", AvailabilityState.BLACKED_OUT),
    }
    decisions = apply_availability_filter(shortlist, evidence)
    assert decisions == (
        EligibilityDecision(
            "SYNTH-PRO-0001",
            EligibilityOutcome.EXCLUDED,
            reason="availability recorded as blacked out",
        ),
    )


def test_unknown_availability_is_undetermined_not_excluded():
    """ADR-0011 pair partner: an unknown record must not silently drop the candidate."""
    shortlist = ("SYNTH-PRO-0001",)
    evidence = {
        "SYNTH-PRO-0001": AvailabilityEvidence("SYNTH-PRO-0001", AvailabilityState.UNKNOWN),
    }
    decisions = apply_availability_filter(shortlist, evidence)
    assert decisions[0].outcome is EligibilityOutcome.UNDETERMINED
    assert decisions[0].outcome is not EligibilityOutcome.EXCLUDED
    assert decisions[0].reason == "availability record is unknown"


def test_missing_availability_record_is_undetermined_not_excluded():
    shortlist = ("SYNTH-PRO-0001",)
    decisions = apply_availability_filter(shortlist, {})
    assert decisions[0].outcome is EligibilityOutcome.UNDETERMINED
    assert decisions[0].outcome is not EligibilityOutcome.EXCLUDED
    assert decisions[0].reason == "no availability record for this subject"


def test_recorded_blackout_and_missing_record_are_distinguishable():
    """Explicit unknown-vs-measured pair: BLACKED_OUT -> EXCLUDED, absent -> UNDETERMINED."""
    shortlist = ("SYNTH-PRO-0001", "SYNTH-PRO-0002")
    evidence = {
        "SYNTH-PRO-0001": AvailabilityEvidence("SYNTH-PRO-0001", AvailabilityState.BLACKED_OUT),
    }
    decisions = apply_availability_filter(shortlist, evidence)
    blacked_out, missing = decisions
    assert blacked_out.outcome is EligibilityOutcome.EXCLUDED
    assert missing.outcome is EligibilityOutcome.UNDETERMINED
    assert blacked_out.reason != missing.reason


def test_shortlist_order_is_preserved():
    """Decisions come back in shortlist order regardless of evidence-mapping order."""
    shortlist = ("SYNTH-PRO-0003", "SYNTH-PRO-0001", "SYNTH-PRO-0002")
    evidence = {
        "SYNTH-PRO-0001": AvailabilityEvidence("SYNTH-PRO-0001", AvailabilityState.AVAILABLE),
        "SYNTH-PRO-0002": AvailabilityEvidence("SYNTH-PRO-0002", AvailabilityState.BLACKED_OUT),
        "SYNTH-PRO-0003": AvailabilityEvidence("SYNTH-PRO-0003", AvailabilityState.AVAILABLE),
    }
    decisions = apply_availability_filter(shortlist, evidence)
    assert tuple(decision.subject_id for decision in decisions) == shortlist


def test_evidence_for_subjects_outside_the_shortlist_is_ignored():
    shortlist = ("SYNTH-PRO-0001",)
    evidence = {
        "SYNTH-PRO-0001": AvailabilityEvidence("SYNTH-PRO-0001", AvailabilityState.AVAILABLE),
        "SYNTH-PRO-9999": AvailabilityEvidence("SYNTH-PRO-9999", AvailabilityState.BLACKED_OUT),
    }
    decisions = apply_availability_filter(shortlist, evidence)
    assert len(decisions) == 1
    assert decisions[0].subject_id == "SYNTH-PRO-0001"


def test_duplicate_subject_in_shortlist_is_rejected():
    shortlist = ("SYNTH-PRO-0001", "SYNTH-PRO-0001")
    with pytest.raises(ValueError):
        apply_availability_filter(shortlist, {})


def test_empty_shortlist_returns_empty_tuple():
    assert apply_availability_filter((), {}) == ()


def test_availability_carries_no_stage_b_weight():
    assert AVAILABILITY_STAGE_B_WEIGHT == 0.0
    spec = next(spec for spec in PROPOSED_FACTORS if spec.key == "availability")
    assert spec.kind is FactorKind.ELIGIBILITY
    assert spec.is_scoring is False
    assert spec.active_weight == 0.0


def test_availability_is_not_in_the_normalized_stage_b_weights():
    assert "availability" not in normalize_weights()


def test_blank_subject_id_is_rejected():
    with pytest.raises(ValueError):
        AvailabilityEvidence("   ", AvailabilityState.AVAILABLE)
    with pytest.raises(ValueError):
        EligibilityDecision("   ", EligibilityOutcome.ELIGIBLE, reason="some reason")


def test_blank_reason_is_rejected():
    with pytest.raises(ValueError):
        EligibilityDecision("SYNTH-PRO-0001", EligibilityOutcome.ELIGIBLE, reason="   ")
