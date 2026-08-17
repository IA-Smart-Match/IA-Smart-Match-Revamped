"""Tests for the shadow-mode feedback loop (migration manifest MM-005)."""

from __future__ import annotations

import pytest

from smartmatch_domain.feedback import (
    MAX_FACTOR_DELTA,
    MIN_DECISIONS_FOR_PROPOSAL,
    REASON_TO_FACTOR,
    Decision,
    DeclineReason,
    FeedbackEntry,
    aggregate,
    propose_weight_adjustments,
)

RUN = "match-run-1"


def _declines(reason: DeclineReason, count: int) -> list[FeedbackEntry]:
    return [
        FeedbackEntry(match_run_id=RUN, decision=Decision.DECLINED, reason=reason)
        for _ in range(count)
    ]


def _accepts(count: int) -> list[FeedbackEntry]:
    return [
        FeedbackEntry(match_run_id=RUN, decision=Decision.ACCEPTED) for _ in range(count)
    ]


# ---------------------------------------------------------------------------
# Entry validation
# ---------------------------------------------------------------------------


def test_declined_entry_requires_a_reason():
    with pytest.raises(ValueError, match="must carry a decline reason"):
        FeedbackEntry(match_run_id=RUN, decision=Decision.DECLINED)


def test_accepted_entry_must_not_carry_a_reason():
    with pytest.raises(ValueError, match="must not carry"):
        FeedbackEntry(
            match_run_id=RUN,
            decision=Decision.ACCEPTED,
            reason=DeclineReason.WRONG_TOPIC,
        )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_empty_feedback_reports_unknown_not_zero_percent():
    """``None`` means unknown. Rendering 0% would be a confident fabrication."""
    assert aggregate([]).acceptance_rate is None


def test_acceptance_rate_is_computed_over_all_decisions():
    counts = aggregate([*_accepts(3), *_declines(DeclineReason.TOO_FAR, 1)])
    assert counts.total == 4
    assert counts.acceptance_rate == pytest.approx(0.75)


def test_reason_counts_are_tallied():
    counts = aggregate(
        [*_declines(DeclineReason.TOO_FAR, 2), *_declines(DeclineReason.WRONG_ROLE, 1)]
    )
    assert counts.reason_counts[DeclineReason.TOO_FAR] == 2
    assert counts.reason_counts[DeclineReason.WRONG_ROLE] == 1


# ---------------------------------------------------------------------------
# Weight proposals
# ---------------------------------------------------------------------------


def test_no_proposal_below_the_minimum_decision_count():
    """The legacy would 'learn' from a single click; this refuses to."""
    entries = _declines(DeclineReason.TOO_FAR, MIN_DECISIONS_FOR_PROPOSAL - 1)
    assert propose_weight_adjustments(entries) is None


def test_no_proposal_when_there_are_no_categorized_declines():
    """All-accepted feedback yields no opinion, not a zero-delta proposal."""
    assert propose_weight_adjustments(_accepts(20)) is None


def test_other_reason_moves_no_weight():
    """An uncategorized decline is signal that something is wrong, not which factor."""
    assert REASON_TO_FACTOR[DeclineReason.OTHER] is None
    assert propose_weight_adjustments(_declines(DeclineReason.OTHER, 20)) is None


def test_declines_raise_the_implicated_factor():
    proposal = propose_weight_adjustments(_declines(DeclineReason.TOO_FAR, 5))
    assert proposal is not None
    assert proposal.deltas["travel_burden"] > 0.0


def test_each_reason_maps_to_its_documented_factor():
    for reason, factor in REASON_TO_FACTOR.items():
        if factor is None:
            continue
        proposal = propose_weight_adjustments(_declines(reason, 5))
        assert proposal is not None
        assert factor in proposal.deltas


def test_delta_is_clamped_regardless_of_decline_volume():
    """A hundred declines must not swing the model arbitrarily far."""
    proposal = propose_weight_adjustments(_declines(DeclineReason.TOO_FAR, 100))
    assert proposal is not None
    assert proposal.deltas["travel_burden"] == pytest.approx(MAX_FACTOR_DELTA)


def test_every_delta_respects_the_bound():
    entries = [
        *_declines(DeclineReason.TOO_FAR, 40),
        *_declines(DeclineReason.WRONG_ROLE, 40),
        *_declines(DeclineReason.OVERCOMMITTED, 40),
    ]
    proposal = propose_weight_adjustments(entries)
    assert proposal is not None
    assert all(0.0 < d <= MAX_FACTOR_DELTA for d in proposal.deltas.values())


def test_proposal_always_requires_human_approval():
    """v1.1 Appendix B: shadow mode. Nothing here applies a weight change."""
    proposal = propose_weight_adjustments(_declines(DeclineReason.TOO_FAR, 5))
    assert proposal is not None
    assert proposal.requires_approval is True


def test_proposal_carries_a_human_readable_rationale():
    proposal = propose_weight_adjustments(_declines(DeclineReason.WRONG_TOPIC, 5))
    assert proposal is not None
    assert proposal.rationale
    assert "topic_relevance" in proposal.rationale[0]


def test_proposal_records_the_aggregate_it_derived_from():
    """Traceability: a weight change must be explainable from its evidence."""
    entries = [*_declines(DeclineReason.TOO_FAR, 5), *_accepts(5)]
    proposal = propose_weight_adjustments(entries)
    assert proposal is not None
    assert proposal.based_on.total == 10
    assert proposal.based_on.acceptance_rate == pytest.approx(0.5)


def test_deltas_mapping_is_immutable():
    proposal = propose_weight_adjustments(_declines(DeclineReason.TOO_FAR, 5))
    assert proposal is not None
    with pytest.raises(TypeError):
        proposal.deltas["travel_burden"] = 1.0  # type: ignore[index]
