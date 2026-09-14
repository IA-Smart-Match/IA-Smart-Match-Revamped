"""The Speaker Pipeline derivation: shape, thresholds, and the non-answers.

Every test here is pure. The module under test measures nothing, so nothing
here needs a database; what it must get right is which ratios exist, what
happens when one side of a ratio does not, and which sentence each threshold
produces.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.metrics import cba_metric_register
from smartmatch_domain.speaker_pipeline import (
    COMPANION_METRIC_NAMES,
    INSUFFICIENT_ACTIVITY_MESSAGE,
    MAX_INSIGHTS,
    MINIMUM_BASELINE_FOR_INSIGHTS,
    REVIEW_BACKLOG_SHARE_PCT,
    SPEAKER_FUNNEL_BASELINE,
    SPEAKER_FUNNEL_STAGES,
    STRONG_CONFIRMATION_RATE_PCT,
    STRONG_PRESENTATION_RATE_PCT,
    WEAK_OUTREACH_RATE_PCT,
    build_speaker_pipeline,
    format_percent,
)

DISPLAY_NAMES = {metric.canonical_name: metric.display_name for metric in cba_metric_register()}


def values(**overrides: int | None) -> dict[str, int | None]:
    """Six measured metrics, overridable one at a time."""
    base: dict[str, int | None] = {
        "pipeline_matched": 100,
        "pipeline_contacted": 60,
        "pipeline_confirmed": 30,
        "pipeline_attended": 15,
        "opportunities": 8,
        "pending_review_items": 2,
    }
    base.update(overrides)
    return base


def codes(pipeline) -> set[str]:
    return {insight.code for insight in pipeline.insights}


def rate_to(pipeline, to_metric: str):
    return next(c for c in pipeline.conversions if c.to_metric == to_metric)


# ---------------------------------------------------------------------------
# Which stages exist, and in which order
# ---------------------------------------------------------------------------


def test_funnel_stages_follow_the_stored_lifecycle_order() -> None:
    """Confirmed precedes Attended, as `ck_pipeline_record_stage_prefix` requires.

    The reference design draws "presented" above "confirmed". Stored order is
    the other way round, and a funnel drawn the design's way would produce a
    backwards arrow and a ratio above 100%.
    """
    assert SPEAKER_FUNNEL_STAGES == (
        "pipeline_matched",
        "pipeline_contacted",
        "pipeline_confirmed",
        "pipeline_attended",
    )
    assert SPEAKER_FUNNEL_BASELINE == "pipeline_matched"


def test_member_inquiry_is_not_a_stage_on_this_surface() -> None:
    """The CBA exclusion is read from the register, not restated here."""
    assert "pipeline_member_inquiry" not in SPEAKER_FUNNEL_STAGES


def test_review_metrics_are_companions_and_never_stages() -> None:
    """`opportunities` and `pending_review_items` count a different entity."""
    assert COMPANION_METRIC_NAMES == ("opportunities", "pending_review_items")
    for name in COMPANION_METRIC_NAMES:
        assert name not in SPEAKER_FUNNEL_STAGES


def test_only_adjacent_lifecycle_transitions_are_published() -> None:
    """Three conversions, not five: no arrow reaches a companion metric."""
    pipeline = build_speaker_pipeline(values(), DISPLAY_NAMES)
    assert [(c.from_metric, c.to_metric) for c in pipeline.conversions] == [
        ("pipeline_matched", "pipeline_contacted"),
        ("pipeline_contacted", "pipeline_confirmed"),
        ("pipeline_confirmed", "pipeline_attended"),
    ]
    touched = {c.from_metric for c in pipeline.conversions} | {
        c.to_metric for c in pipeline.conversions
    }
    assert touched.isdisjoint(COMPANION_METRIC_NAMES)


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------


def test_conversions_are_downstream_over_upstream() -> None:
    pipeline = build_speaker_pipeline(values(), DISPLAY_NAMES)
    assert rate_to(pipeline, "pipeline_contacted").rate_pct == pytest.approx(60.0)
    assert rate_to(pipeline, "pipeline_confirmed").rate_pct == pytest.approx(50.0)
    assert rate_to(pipeline, "pipeline_attended").rate_pct == pytest.approx(50.0)


def test_stage_widths_are_shares_of_the_baseline_stage() -> None:
    pipeline = build_speaker_pipeline(values(), DISPLAY_NAMES)
    shares = {stage.metric_name: stage.share_of_baseline_pct for stage in pipeline.stages}
    assert shares["pipeline_matched"] == pytest.approx(100.0)
    assert shares["pipeline_contacted"] == pytest.approx(60.0)
    assert shares["pipeline_attended"] == pytest.approx(15.0)


def test_a_zero_denominator_is_a_named_absence_not_infinity() -> None:
    """Zero upstream records yields no rate, an em dash, and a stated reason."""
    pipeline = build_speaker_pipeline(
        values(pipeline_matched=0, pipeline_contacted=0, pipeline_confirmed=0, pipeline_attended=0),
        DISPLAY_NAMES,
    )
    conversion = rate_to(pipeline, "pipeline_contacted")
    assert conversion.rate_pct is None
    assert conversion.display == "—"
    assert "No records reached the upstream stage" in (conversion.unavailable_reason or "")


def test_an_unknown_metric_never_becomes_a_zero() -> None:
    """ADR-0011 rule 1 survives the derivation, on both sides of the ratio."""
    pipeline = build_speaker_pipeline(values(pipeline_contacted=None), DISPLAY_NAMES)

    downstream_unknown = rate_to(pipeline, "pipeline_contacted")
    assert downstream_unknown.rate_pct is None
    assert "downstream stage was not measured" in (downstream_unknown.unavailable_reason or "")

    upstream_unknown = rate_to(pipeline, "pipeline_confirmed")
    assert upstream_unknown.rate_pct is None
    assert "upstream stage was not measured" in (upstream_unknown.unavailable_reason or "")

    contacted = next(s for s in pipeline.stages if s.metric_name == "pipeline_contacted")
    assert contacted.value is None
    assert contacted.share_of_baseline_pct is None
    assert contacted.share_display == "—"


def test_a_metric_absent_from_the_mapping_is_unknown_not_zero() -> None:
    """A name this surface was never given is not silently measured as none."""
    supplied = values()
    del supplied["pipeline_attended"]
    pipeline = build_speaker_pipeline(supplied, DISPLAY_NAMES)
    attended = next(s for s in pipeline.stages if s.metric_name == "pipeline_attended")
    assert attended.value is None
    assert rate_to(pipeline, "pipeline_attended").rate_pct is None


def test_no_conversion_can_exceed_one_hundred_percent_on_valid_data() -> None:
    """The stored prefix invariant means downstream never exceeds upstream."""
    pipeline = build_speaker_pipeline(
        values(pipeline_matched=9, pipeline_contacted=9, pipeline_confirmed=9, pipeline_attended=9),
        DISPLAY_NAMES,
    )
    assert all(c.rate_pct == pytest.approx(100.0) for c in pipeline.conversions)


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(None, "—"), (0.0, "0%"), (41.6, "42%"), (100.0, "100%")],
)
def test_percent_formatting_is_owned_in_one_place(rate: float | None, expected: str) -> None:
    assert format_percent(rate) == expected


# ---------------------------------------------------------------------------
# Insight thresholds
# ---------------------------------------------------------------------------


def test_thin_activity_yields_the_neutral_message_only() -> None:
    pipeline = build_speaker_pipeline(
        values(pipeline_matched=MINIMUM_BASELINE_FOR_INSIGHTS - 1), DISPLAY_NAMES
    )
    assert [insight.code for insight in pipeline.insights] == ["insufficient_activity"]
    assert pipeline.insights[0].detail == INSUFFICIENT_ACTIVITY_MESSAGE


def test_an_unmeasured_baseline_yields_the_neutral_message() -> None:
    pipeline = build_speaker_pipeline(values(pipeline_matched=None), DISPLAY_NAMES)
    assert codes(pipeline) == {"insufficient_activity"}


def test_weak_outreach_is_reported_just_below_its_threshold() -> None:
    below = build_speaker_pipeline(
        values(pipeline_matched=100, pipeline_contacted=int(WEAK_OUTREACH_RATE_PCT) - 1),
        DISPLAY_NAMES,
    )
    at = build_speaker_pipeline(
        values(pipeline_matched=100, pipeline_contacted=int(WEAK_OUTREACH_RATE_PCT)),
        DISPLAY_NAMES,
    )
    assert "weak_outreach" in codes(below)
    assert "weak_outreach" not in codes(at)


def test_strong_confirmation_and_presentation_are_reported_at_threshold() -> None:
    pipeline = build_speaker_pipeline(
        values(
            pipeline_matched=100,
            pipeline_contacted=100,
            pipeline_confirmed=int(STRONG_CONFIRMATION_RATE_PCT),
            pipeline_attended=int(
                STRONG_CONFIRMATION_RATE_PCT * STRONG_PRESENTATION_RATE_PCT / 100
            ),
        ),
        DISPLAY_NAMES,
    )
    assert {"strong_confirmation", "strong_presentation"} <= codes(pipeline)


def test_review_backlog_is_reported_and_labelled_as_a_queue_depth() -> None:
    pipeline = build_speaker_pipeline(
        values(opportunities=1, pending_review_items=9), DISPLAY_NAMES
    )
    backlog = next(i for i in pipeline.insights if i.code == "review_backlog")
    assert backlog.tone == "attention"
    # The wording must refuse the funnel reading, not merely avoid it.
    assert "not a funnel stage" in backlog.detail


def test_review_backlog_is_silent_below_its_threshold() -> None:
    pipeline = build_speaker_pipeline(
        values(opportunities=9, pending_review_items=1), DISPLAY_NAMES
    )
    assert "review_backlog" not in codes(pipeline)
    share = 1 / 10 * 100
    assert share < REVIEW_BACKLOG_SHARE_PCT


def test_no_review_rows_at_all_produces_no_backlog_insight() -> None:
    """A zero denominator here is silence, not a divide-by-zero."""
    pipeline = build_speaker_pipeline(
        values(opportunities=0, pending_review_items=0), DISPLAY_NAMES
    )
    assert "review_backlog" not in codes(pipeline)


def test_insights_are_capped_and_ordered_most_actionable_first() -> None:
    pipeline = build_speaker_pipeline(
        values(
            pipeline_matched=100,
            pipeline_contacted=10,
            pipeline_confirmed=10,
            pipeline_attended=10,
            opportunities=0,
            pending_review_items=10,
        ),
        DISPLAY_NAMES,
    )
    assert len(pipeline.insights) <= MAX_INSIGHTS
    assert pipeline.insights[0].code == "review_backlog"
    assert pipeline.insights[0].tone == "attention"


def test_a_healthy_pipeline_says_so_rather_than_saying_nothing() -> None:
    pipeline = build_speaker_pipeline(
        values(
            pipeline_matched=100,
            pipeline_contacted=60,
            pipeline_confirmed=30,
            pipeline_attended=15,
            opportunities=9,
            pending_review_items=1,
        ),
        DISPLAY_NAMES,
    )
    assert codes(pipeline) == {"nothing_notable"}


def test_insights_are_deterministic_for_the_same_input() -> None:
    first = build_speaker_pipeline(values(), DISPLAY_NAMES)
    second = build_speaker_pipeline(values(), DISPLAY_NAMES)
    assert first == second
