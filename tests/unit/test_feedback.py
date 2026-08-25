"""Tests for the shadow-mode feedback loop (migration manifest MM-005)."""

from __future__ import annotations

import dataclasses

import pytest
from smartmatch_domain.feedback import (
    MAX_FACTOR_DELTA,
    MIN_DECLINES_PER_FACTOR,
    REASON_TO_FACTOR,
    Decision,
    DeclineReason,
    FeedbackEntry,
    WeightProposal,
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
    return [FeedbackEntry(match_run_id=RUN, decision=Decision.ACCEPTED) for _ in range(count)]


# ---------------------------------------------------------------------------
# Entry validation
# ---------------------------------------------------------------------------


def test_feedback_must_be_attributed_to_a_match_run():
    """Attribution is load-bearing: it is how a proposal is traced to its model."""
    for blank in ("", "   "):
        with pytest.raises(ValueError, match="attributed to a match run"):
            FeedbackEntry(match_run_id=blank, decision=Decision.ACCEPTED)


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


def test_no_proposal_below_the_minimum_decline_count():
    """The legacy would 'learn' from a single click; this refuses to."""
    entries = _declines(DeclineReason.TOO_FAR, MIN_DECLINES_PER_FACTOR - 1)
    assert propose_weight_adjustments(entries) is None


def test_accepts_do_not_unlock_a_movement_driven_by_one_decline():
    """The floor counts declines, not decisions.

    Counting every decision meant four unrelated accepts were enough to admit a
    weight movement resting on exactly one decline — the legacy failure the
    floor was added to prevent, behind a floor that looked like it prevented it.
    """
    entries = [*_accepts(MIN_DECLINES_PER_FACTOR - 1), *_declines(DeclineReason.TOO_FAR, 1)]
    assert propose_weight_adjustments(entries) is None
    assert propose_weight_adjustments([*_accepts(99), *_declines(DeclineReason.TOO_FAR, 1)]) is None


def test_the_floor_is_per_factor_not_per_proposal():
    """A factor moves on its own declines, not on another factor's."""
    entries = [
        *_declines(DeclineReason.TOO_FAR, MIN_DECLINES_PER_FACTOR),
        *_declines(DeclineReason.WRONG_ROLE, 1),
    ]
    proposal = propose_weight_adjustments(entries)
    assert proposal is not None
    assert "travel_burden" in proposal.deltas
    assert "role_fit" not in proposal.deltas


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
    """A hundred declines must not swing the model arbitrarily far.

    A lone factor is also the case the aggregate bound must leave alone: it
    scales a crowded proposal down, it does not shrink a single-factor one.
    """
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


def test_aggregate_movement_is_deliberately_unbounded():
    """Pins the absence of an aggregate bound, which is a deferral, not an oversight.

    Each delta is bounded by ``MAX_FACTOR_DELTA``; their sum is not. Six
    factors implicated at once propose +0.48 against weights that total 1.0,
    and nothing here renormalizes — the legacy did both, clamping each factor
    into a band around its baseline and then renormalizing the vector.

    This is left as it is on purpose. The real defect (review finding F-25,
    ``docs/plans/defect-remediation.md`` §4.5) is that the number a human
    approves is not the number that gets applied, because normalization happens
    outside this module. Fixing that means choosing between normalizing on
    apply and bounding the sum at proposal time, and that choice belongs with
    the consumer that applies weights — it arrives with weight sets in M1/M8
    behind gate G1. Until then this test states the behavior so the next reader
    cannot mistake the per-factor bound for a bound on the proposal, and so
    that whichever semantics are chosen has to change a failing test rather
    than slip in beside a silent assumption.
    """
    entries = [
        entry
        for reason, factor in REASON_TO_FACTOR.items()
        if factor is not None
        for entry in _declines(reason, 40)
    ]
    proposal = propose_weight_adjustments(entries)
    assert proposal is not None
    assert len(proposal.deltas) == 6
    assert all(d == pytest.approx(MAX_FACTOR_DELTA) for d in proposal.deltas.values())
    assert sum(proposal.deltas.values()) == pytest.approx(0.48)


# ---------------------------------------------------------------------------
# The shadow-mode control (F-24, F-27)
# ---------------------------------------------------------------------------


def test_proposal_always_requires_human_approval():
    """v1.1 Appendix B: shadow mode. Nothing here applies a weight change.

    Asserting ``requires_approval is True`` proves nothing about a property
    whose body is ``return True``; it passes against an empty implementation.
    These are the routes by which a caller could try to mark a proposal
    auto-applicable, and each must fail: assignment to the property (no setter)
    and to any field (``frozen=True``),
    ``object.__setattr__`` (no setter, and ``slots=True`` removed the
    ``__dict__`` that would otherwise absorb it), the constructor and
    ``dataclasses.replace`` (not a field). Together they fail if anyone removes
    ``frozen``, removes ``slots``, or converts the property to a field.
    """
    proposal = propose_weight_adjustments(_declines(DeclineReason.TOO_FAR, 5))
    assert proposal is not None
    assert proposal.requires_approval is True

    with pytest.raises((AttributeError, TypeError)):
        proposal.requires_approval = False  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        proposal.deltas = {}  # type: ignore[misc]
    with pytest.raises(AttributeError):
        object.__setattr__(proposal, "requires_approval", False)
    with pytest.raises(TypeError):
        WeightProposal(  # type: ignore[call-arg]
            deltas=proposal.deltas,
            based_on=proposal.based_on,
            rationale=proposal.rationale,
            requires_approval=False,
        )
    with pytest.raises(TypeError):
        dataclasses.replace(proposal, requires_approval=False)  # type: ignore[type-var]

    assert WeightProposal.requires_approval.fset is None
    assert not hasattr(proposal, "__dict__")
    assert proposal.requires_approval is True


def test_the_approval_control_cannot_be_subclassed_away():
    """A subclass overriding the property still satisfies ``isinstance``.

    ``@final`` closes this for a type-checked caller; the class refuses the
    subclass at runtime so an untyped one cannot smuggle a proposal that reports
    ``requires_approval is False`` past a consumer typed on ``WeightProposal``.
    """
    with pytest.raises(TypeError, match="final"):

        class AutoApplied(WeightProposal):  # type: ignore[misc]
            @property
            def requires_approval(self) -> bool:
                return False


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
