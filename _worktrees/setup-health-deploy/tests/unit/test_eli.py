"""Tests for the Engagement Load Index."""

from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta

import pytest
from smartmatch_domain.eli import (
    ELI_FORMULA_VERSION,
    CapDecision,
    EngagementRecord,
    LoadInputs,
    LoadModifier,
    compute_eli,
    evaluate_cap,
    load_penalty,
)
from smartmatch_domain.factor_registry import PROHIBITED_INPUTS

AS_OF = date(2026, 8, 17)


def _inputs(**overrides: object) -> LoadInputs:
    base: dict[str, object] = {"as_of": AS_OF, "declared_capacity_hours": 40.0}
    base.update(overrides)
    return LoadInputs(**base)  # type: ignore[arg-type]


def test_no_engagements_scores_zero():
    snapshot = compute_eli(_inputs())
    assert snapshot.score == 0.0
    assert snapshot.raw_hours == 0.0
    assert snapshot.utilization == 0.0


def test_score_reflects_utilization_of_declared_capacity():
    """20 hours today against a 40-hour capacity is 50% utilization."""
    snapshot = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=20.0),))
    )
    assert snapshot.utilization == pytest.approx(0.5)
    assert snapshot.score == pytest.approx(50.0)


def test_travel_hours_count_toward_load():
    """Travel is real workload; v1.1 §1.3 names it as a permitted input."""
    without = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=10.0),))
    )
    with_travel = compute_eli(
        _inputs(
            engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=10.0, travel_hours=6.0),)
        )
    )
    assert with_travel.score > without.score


def test_recency_decay_reduces_older_engagement_weight():
    """An engagement 45 days ago counts half, per the documented half-life."""
    recent = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=20.0),))
    )
    older = compute_eli(
        _inputs(
            engagements=(
                EngagementRecord(occurred_on=AS_OF - timedelta(days=45), event_hours=20.0),
            )
        )
    )
    assert older.decayed_hours == pytest.approx(recent.decayed_hours / 2, rel=1e-3)


def test_engagements_outside_the_window_are_ignored_not_rejected():
    """A 91-day-old engagement falls out of the rolling window silently."""
    snapshot = compute_eli(
        _inputs(
            engagements=(
                EngagementRecord(occurred_on=AS_OF - timedelta(days=91), event_hours=40.0),
            )
        )
    )
    assert snapshot.raw_hours == 0.0
    assert snapshot.score == 0.0


def test_raw_hours_are_reported_alongside_decayed_hours():
    """Explanations need both: decayed drives the score, raw is what happened."""
    snapshot = compute_eli(
        _inputs(
            engagements=(
                EngagementRecord(occurred_on=AS_OF - timedelta(days=45), event_hours=20.0),
            )
        )
    )
    assert snapshot.raw_hours == pytest.approx(20.0)
    assert snapshot.decayed_hours == pytest.approx(10.0, rel=1e-3)


def test_modifiers_raise_the_score_but_are_bounded():
    """Modifiers express schedule pressure without dominating measured hours."""
    plain = compute_eli(_inputs())
    modified = compute_eli(
        _inputs(
            modifiers=frozenset(
                {
                    LoadModifier.BACK_TO_BACK,
                    LoadModifier.SHORT_RECOVERY,
                    LoadModifier.LONG_TRAVEL,
                    LoadModifier.SHORT_NOTICE,
                    LoadModifier.CONSECUTIVE_WEEKENDS,
                    LoadModifier.AT_DECLARED_FREQUENCY,
                }
            )
        )
    )
    assert modified.score > plain.score
    # Six modifiers at 4 points each would be 24; the cap holds it to 20.
    assert modified.score == pytest.approx(20.0)


def test_duplicate_modifiers_are_counted_once_not_per_element():
    """The score must count what the explanation names.

    ``modifiers`` is annotated ``frozenset[LoadModifier]``, but the annotation is
    not a runtime check. A caller passing a list of six identical modifiers used
    to score 20 while the snapshot reported a single modifier — an explanation
    that contradicts the number it explains.
    """
    duplicated = compute_eli(_inputs(modifiers=[LoadModifier.BACK_TO_BACK] * 6))
    single = compute_eli(_inputs(modifiers=frozenset({LoadModifier.BACK_TO_BACK})))

    assert duplicated.modifiers == frozenset({LoadModifier.BACK_TO_BACK})
    assert duplicated.score == pytest.approx(4.0)
    assert duplicated.score == single.score


def test_score_is_clamped_to_one_hundred():
    snapshot = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=500.0),))
    )
    assert snapshot.score == 100.0


def test_utilization_is_not_clamped_so_overload_is_visible():
    """The score saturates at 100, but the explanation must show how far over."""
    snapshot = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=80.0),))
    )
    assert snapshot.score == 100.0
    assert snapshot.utilization == pytest.approx(2.0)


def test_snapshot_records_formula_version():
    """Stored snapshots must say which formula produced them (v1.1 §2.2)."""
    assert compute_eli(_inputs()).formula_version == ELI_FORMULA_VERSION


# ---------------------------------------------------------------------------
# Stage A hard cap
# ---------------------------------------------------------------------------


def test_within_cap_when_under_declared_capacity():
    snapshot = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=20.0),))
    )
    assert evaluate_cap(snapshot) is CapDecision.WITHIN_CAP


def test_over_cap_when_utilization_exceeds_one():
    snapshot = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=50.0),))
    )
    assert evaluate_cap(snapshot) is CapDecision.OVER_CAP


def test_manual_blackout_wins_over_spare_capacity():
    """A blackout is an instruction, not a load judgement."""
    snapshot = compute_eli(_inputs(modifiers=frozenset({LoadModifier.MANUAL_BLACKOUT})))
    assert snapshot.utilization == 0.0
    assert evaluate_cap(snapshot) is CapDecision.BLACKED_OUT

    # ...which means it is not measured workload either. An idle professional who
    # blocked out their calendar has done no work, and the persisted snapshot and
    # the Stage B penalty must both say so: v1.1 §5.1 gives the professional the
    # right to correct the workload data used about them, and points that
    # correspond to no engagement cannot be corrected.
    assert snapshot.score == 0.0
    assert load_penalty(snapshot) == 0.0
    # It stays visible in the explanation; only its contribution to load is gone.
    assert snapshot.modifiers == frozenset({LoadModifier.MANUAL_BLACKOUT})

    # Nor does it inflate a professional who has done real work.
    with_work = compute_eli(
        _inputs(
            engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=20.0),),
            modifiers=frozenset({LoadModifier.MANUAL_BLACKOUT}),
        )
    )
    assert with_work.score == pytest.approx(50.0)


def test_stage_a_cap_is_decided_on_the_unrounded_utilization():
    """A display precision must not decide an eligibility boundary.

    ``utilization`` was stored rounded to 4 dp and ``evaluate_cap`` tested the
    rounded value, so 100.000–100.005 % of declared capacity reported
    ``WITHIN_CAP``. The width of that window is incidental; the defect is that a
    hard eligibility control read a number rounded for readability, and a later
    decision to render 2 dp instead would have widened it a hundredfold without
    failing a test.
    """
    over = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=40.0001),))
    )
    assert over.utilization > 1.0
    assert evaluate_cap(over) is CapDecision.OVER_CAP

    # Every display precision a coordinator-facing number would plausibly use
    # hides the overage. None of them may move the decision.
    for precision in (0, 1, 2, 3, 4):
        assert round(over.utilization, precision) <= 1.0

    # The boundary itself is unchanged: exactly at the declared cap is within it.
    exactly_at_cap = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=40.0),))
    )
    assert exactly_at_cap.utilization == 1.0
    assert evaluate_cap(exactly_at_cap) is CapDecision.WITHIN_CAP


# ---------------------------------------------------------------------------
# Stage B soft penalty
# ---------------------------------------------------------------------------


def test_penalty_is_zero_at_no_load_and_one_at_full_load():
    idle = compute_eli(_inputs())
    assert load_penalty(idle) == 0.0

    saturated = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=40.0),))
    )
    assert load_penalty(saturated) == pytest.approx(1.0)


def test_penalty_is_progressive_not_linear():
    """Light load is close to free; the penalty steepens near the cap."""
    light = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=10.0),))
    )
    heavy = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=30.0),))
    )
    # Quadratic: 0.25^2 = 0.0625 vs 0.75^2 = 0.5625 — a 3x load increase is a 9x
    # penalty increase.
    assert load_penalty(light) == pytest.approx(0.0625)
    assert load_penalty(heavy) == pytest.approx(0.5625)


def test_hard_cap_and_soft_penalty_are_separately_observable():
    """v1.1 §1.3 requires both applications be visible in the explanation."""
    snapshot = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=50.0),))
    )
    assert evaluate_cap(snapshot) is CapDecision.OVER_CAP
    assert 0.0 <= load_penalty(snapshot) <= 1.0


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_negative_hours_are_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        EngagementRecord(occurred_on=AS_OF, event_hours=-1.0)
    with pytest.raises(ValueError, match="non-negative"):
        EngagementRecord(occurred_on=AS_OF, event_hours=1.0, travel_hours=-1.0)


def test_nonpositive_declared_capacity_is_rejected():
    """An undeclared capacity is not zero capacity, and must not be defaulted to it."""
    with pytest.raises(ValueError, match="must be positive"):
        LoadInputs(as_of=AS_OF, declared_capacity_hours=0.0)


def test_future_dated_engagements_are_rejected_not_silently_dropped():
    """ELI measures load that has occurred, and says so out loud.

    A future-dated engagement used to be skipped inside ``compute_eli``, so a
    caller who passed next week's commitment got a score computed as though it
    did not exist. Whether committed load should count is a forward-horizon and
    forward-weighting question owned by open decision 2; discarding the record
    without telling the caller is not an answer to it.
    """
    with pytest.raises(ValueError, match="must not be dated after as_of"):
        LoadInputs(
            as_of=AS_OF,
            engagements=(EngagementRecord(occurred_on=AS_OF + timedelta(days=1), event_hours=8.0),),
        )

    # The boundary: an engagement dated on ``as_of`` has occurred and still counts.
    same_day = compute_eli(
        _inputs(engagements=(EngagementRecord(occurred_on=AS_OF, event_hours=8.0),))
    )
    assert same_day.raw_hours == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Prohibited inputs
# ---------------------------------------------------------------------------


def test_prohibited_inputs_cannot_reach_the_computation():
    """The enforcement ``eli.py``'s module docstring claims, actually performed.

    The docstring says the prohibited-input list is enforced "by the registry
    schema and by ``tests/unit/test_eli.py``, not by convention", and this file
    contained no such assertion. Documentation is not a control; this is.
    """
    permitted = {f.name for f in fields(LoadInputs)} | {f.name for f in fields(EngagementRecord)}
    assert not permitted & PROHIBITED_INPUTS

    for prohibited in sorted(PROHIBITED_INPUTS):
        with pytest.raises(TypeError):
            LoadInputs(as_of=AS_OF, **{prohibited: "x"})
        with pytest.raises(TypeError):
            EngagementRecord(occurred_on=AS_OF, event_hours=1.0, **{prohibited: "x"})

    # Nor can one be attached after construction: ``slots=True`` leaves no
    # ``__dict__`` for a stray attribute to land in, and ``frozen=True`` refuses
    # the assignment outright.
    inputs = _inputs()
    assert not hasattr(inputs, "__dict__")
    for prohibited in sorted(PROHIBITED_INPUTS):
        with pytest.raises((AttributeError, TypeError)):
            setattr(inputs, prohibited, "x")
