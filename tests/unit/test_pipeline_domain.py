"""Tests for the S12 funnel's pure stage-sequence rules (P8 card O2 app writers)."""

from __future__ import annotations

import pytest
from smartmatch_domain.pipeline import (
    PIPELINE_STAGE_SEQUENCE,
    InvalidPipelineStageTransitionError,
    PipelineStage,
    assert_stage_reachable,
    prerequisite_stage,
)


def test_every_stage_appears_exactly_once_in_sequence() -> None:
    assert set(PIPELINE_STAGE_SEQUENCE) == set(PipelineStage)
    assert len(PIPELINE_STAGE_SEQUENCE) == len(set(PIPELINE_STAGE_SEQUENCE))


def test_matched_has_no_prerequisite() -> None:
    """The entry stage — satisfied by construction, per migration 0011's NOT NULL."""
    assert prerequisite_stage(PipelineStage.MATCHED) is None


@pytest.mark.parametrize(
    ("stage", "expected_prerequisite"),
    [
        (PipelineStage.CONTACTED, PipelineStage.MATCHED),
        (PipelineStage.CONFIRMED, PipelineStage.CONTACTED),
        (PipelineStage.ATTENDED, PipelineStage.CONFIRMED),
        (PipelineStage.MEMBER_INQUIRY, PipelineStage.ATTENDED),
    ],
)
def test_each_stage_requires_the_one_before_it(
    stage: PipelineStage, expected_prerequisite: PipelineStage
) -> None:
    """Transcribed one-for-one from ck_pipeline_record_stage_prefix's four clauses."""
    assert prerequisite_stage(stage) == expected_prerequisite


def test_a_stage_is_reachable_once_its_prerequisite_is_reached() -> None:
    assert_stage_reachable(frozenset({PipelineStage.MATCHED}), PipelineStage.CONTACTED)
    assert_stage_reachable(
        frozenset({PipelineStage.MATCHED, PipelineStage.CONTACTED, PipelineStage.CONFIRMED}),
        PipelineStage.ATTENDED,
    )


@pytest.mark.parametrize(
    ("reached", "target"),
    [
        (frozenset(), PipelineStage.CONTACTED),
        (frozenset({PipelineStage.MATCHED}), PipelineStage.CONFIRMED),
        (frozenset({PipelineStage.MATCHED, PipelineStage.CONTACTED}), PipelineStage.ATTENDED),
        (
            frozenset({PipelineStage.MATCHED, PipelineStage.CONTACTED, PipelineStage.CONFIRMED}),
            PipelineStage.MEMBER_INQUIRY,
        ),
    ],
)
def test_a_stage_is_unreachable_when_its_prerequisite_is_missing(
    reached: frozenset[PipelineStage], target: PipelineStage
) -> None:
    """The same refusal ck_pipeline_record_stage_prefix backs, raised before any SQL runs."""
    with pytest.raises(InvalidPipelineStageTransitionError):
        assert_stage_reachable(reached, target)


def test_matched_is_always_reachable_since_it_has_no_prerequisite() -> None:
    """Never actually exercised by a caller (record_matched inserts it directly),
    but the function must not misbehave if one ever did call it this way.
    """
    assert_stage_reachable(frozenset(), PipelineStage.MATCHED)


def test_a_journey_cannot_skip_ahead_more_than_one_stage_at_a_time() -> None:
    """Reaching Attended with only Matched (skipping Contacted and Confirmed)
    is refused — the funnel narrows one stage at a time, and no shortcut
    around an intermediate stage is legal.
    """
    with pytest.raises(InvalidPipelineStageTransitionError):
        assert_stage_reachable(frozenset({PipelineStage.MATCHED}), PipelineStage.ATTENDED)
