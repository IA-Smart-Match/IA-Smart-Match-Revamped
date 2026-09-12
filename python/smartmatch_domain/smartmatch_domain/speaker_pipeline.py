"""The Speaker Pipeline view of the ADR-0011 register: shape, not measurement.

This module derives *nothing new*. Every number it handles was already
measured by exactly one owning query (``smartmatch_api.routers.metrics``);
what is added here is the one place that decides which of those numbers form
a cohort funnel, which ratios between them are legitimate, and which
sentences a coordinator is shown about them. Keeping that here rather than in
the browser is the same rule ADR-0011 rule 4 states for counts, applied to
the ratios computed *from* counts: a conversion rate is a published number
too, and a second copy of it in JSX is a second definition.

## Why six cards but only four funnel stages

The surface presents six registered metrics. Only four of them are stages of
one lifecycle:

``pipeline_matched`` → ``pipeline_contacted`` → ``pipeline_confirmed`` →
``pipeline_attended``

These are cumulative "reached this stage or a later one" counts over a single
table, ``pipeline_record``, and migration ``0011``'s
``ck_pipeline_record_stage_prefix`` makes the nesting a database invariant:
``contacted_at`` may not be set without ``matched_at``, ``confirmed_at``
without ``contacted_at``, ``attended_at`` without ``confirmed_at``. Each
stage's rows are therefore a strict subset of the previous stage's, which is
precisely what makes ``downstream / upstream`` a cohort conversion rate and
not merely a quotient of two numbers.

``pipeline_member_inquiry`` is a fifth such stage and is deliberately absent:
``Capability.MEMBER_INQUIRY_NARRATIVE`` is off under ``ProductScope.CBA``,
and :data:`smartmatch_domain.metrics.CBA_EXCLUDED_METRICS` already says so
once. This module reads that exclusion rather than restating it.

The remaining two registered metrics are **not** stages of that lifecycle and
no arrow may be drawn to or from them:

* ``opportunities`` ("Speaker Requests") counts ``review_item`` rows in
  ``status = 'accepted'`` whose category is in-list — *opportunity* rows, not
  speakers, on a different table, with no membership relation to any pipeline
  record.
* ``pending_review_items`` counts ``review_item`` rows in
  ``status = 'pending'`` — a current-state queue depth, not a cumulative
  lifecycle total, and one that *falls* as work is done rather than rising.

A design that chains all six — matched → invited → requests → review →
presented → confirmed — reads a causal conversion into four pairs that have
none, and its arithmetic says so out loud: a "conversion" above 100% is the
visible symptom of dividing two independent aggregates. This module therefore
publishes three conversions, not five, and carries the other two metrics as
:data:`COMPANION_METRIC_NAMES` — presented beside the funnel, never inside it.

## Unknown is never zero, and never a denominator

A registered metric may answer ``None`` (ADR-0011 rule 1: absence is not
zero). Every derivation here propagates that instead of substituting a
number: a conversion whose numerator or denominator is unknown is
:class:`Conversion` with ``rate_pct=None`` and an ``unavailable_reason``
naming which side was missing, and insights that would have needed it are not
generated. A zero denominator is the same shape of answer with a different
reason — never ``inf``, never ``nan``, never a silent ``0%``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from smartmatch_domain.metrics import is_cba_visible_metric

__all__ = [
    "COMPANION_METRIC_NAMES",
    "FUNNEL_STAGE_DESCRIPTIONS",
    "INSUFFICIENT_ACTIVITY_MESSAGE",
    "MAX_INSIGHTS",
    "MINIMUM_BASELINE_FOR_INSIGHTS",
    "REVIEW_BACKLOG_SHARE_PCT",
    "SPEAKER_FUNNEL_BASELINE",
    "SPEAKER_FUNNEL_STAGES",
    "STRONG_CONFIRMATION_RATE_PCT",
    "STRONG_PRESENTATION_RATE_PCT",
    "WEAK_OUTREACH_RATE_PCT",
    "Conversion",
    "FunnelStage",
    "Insight",
    "SpeakerPipeline",
    "build_speaker_pipeline",
    "format_percent",
]

#: The lifecycle stages, in the order ``pipeline_record`` enforces.
#:
#: Order is not a display preference here: it is the order
#: ``ck_pipeline_record_stage_prefix`` requires, so adjacent pairs of this
#: tuple are exactly the transitions on which a cohort conversion is defined.
#: Note that **Confirmed precedes Attended**. The supplied reference design
#: places "presented" above "confirmed"; the stored lifecycle is the other way
#: round (a record cannot carry ``attended_at`` without ``confirmed_at``), and
#: rendering the design's order would draw an arrow backwards through the
#: funnel and produce a ratio above 100%.
SPEAKER_FUNNEL_STAGES: Final[tuple[str, ...]] = tuple(
    name
    for name in (
        "pipeline_matched",
        "pipeline_contacted",
        "pipeline_confirmed",
        "pipeline_attended",
        "pipeline_member_inquiry",
    )
    if is_cba_visible_metric(name)
)

#: The stage every stage's funnel width is drawn relative to: the widest one.
SPEAKER_FUNNEL_BASELINE: Final[str] = SPEAKER_FUNNEL_STAGES[0]

#: Registered metrics shown beside the funnel but never inside it.
#:
#: Both count ``review_item`` rows rather than pipeline records. Neither is a
#: subset of any funnel stage, so no ratio between either of them and a stage
#: is a conversion — see this module's docstring.
COMPANION_METRIC_NAMES: Final[tuple[str, ...]] = (
    "opportunities",
    "pending_review_items",
)

#: One short line under each stage label, in the product's own vocabulary.
#:
#: Deliberately *not* the register's ``definition``, which travels in the API
#: payload beside it and is the authoritative sentence. These are captions;
#: where the two could disagree the definition wins, which is why none of
#: these restates a counting rule.
FUNNEL_STAGE_DESCRIPTIONS: Final[Mapping[str, str]] = {
    "pipeline_matched": "Matched to your criteria",
    "pipeline_contacted": "Outreach sent",
    "pipeline_confirmed": "Confirmed to speak",
    "pipeline_attended": "Successfully presented",
    "pipeline_member_inquiry": "Followed up after the event",
}

#: One short line for each companion measure.
COMPANION_METRIC_DESCRIPTIONS: Final[Mapping[str, str]] = {
    "opportunities": "Accepted and in-list",
    "pending_review_items": "Awaiting internal review",
}

# ---------------------------------------------------------------------------
# Insight thresholds
# ---------------------------------------------------------------------------
#
# Every number an insight compares against lives here, named and commented,
# so that "why did this sentence appear" is answerable by reading one block
# rather than by grepping JSX for literals. They are product judgement, not
# measurements: changing one changes which sentence a coordinator reads and
# changes no count anywhere.

#: Below this matched→contacted rate, outreach is called out as an opportunity.
#: Half of matched speakers never being contacted is the point at which the
#: bottleneck is the outreach step rather than the match quality.
WEAK_OUTREACH_RATE_PCT: Final[float] = 50.0

#: At or above this contacted→confirmed rate, confirmation is called a strength.
STRONG_CONFIRMATION_RATE_PCT: Final[float] = 70.0

#: At or above this confirmed→attended rate, follow-through is called a strength.
STRONG_PRESENTATION_RATE_PCT: Final[float] = 80.0

#: At or above this share of all review items still pending, the queue is
#: called a backlog. Expressed against *all* review rows this unit owns
#: (pending plus accepted-in-list), because a pending count on its own says
#: nothing about whether the queue is being worked.
REVIEW_BACKLOG_SHARE_PCT: Final[float] = 50.0

#: Fewest baseline records before any insight is generated at all. One
#: matched record produces ratios that are arithmetically valid and
#: editorially meaningless ("0% of 1 speaker was contacted"), so the neutral
#: message is the honest answer below this.
MINIMUM_BASELINE_FOR_INSIGHTS: Final[int] = 5

#: Most insights shown at once, so the panel stays scannable.
MAX_INSIGHTS: Final[int] = 3

#: What to say when nothing above can be said.
INSUFFICIENT_ACTIVITY_MESSAGE: Final[str] = (
    "Not enough activity in this period to generate pipeline insights."
)

#: Rendered in place of a percentage that does not exist.
UNAVAILABLE_DISPLAY: Final[str] = "—"


def format_percent(rate_pct: float | None) -> str:
    """Render a percentage the one way every surface renders it.

    Whole numbers, no decimal point, and :data:`UNAVAILABLE_DISPLAY` for a
    rate that does not exist. This function is the rounding rule; a client
    that re-rounds ``rate_pct`` itself is a second rule, and the two disagree
    at every half-percent.
    """
    if rate_pct is None:
        return UNAVAILABLE_DISPLAY
    return f"{round(rate_pct)}%"


@dataclass(frozen=True, slots=True)
class FunnelStage:
    """One lifecycle stage, sized relative to the baseline stage."""

    metric_name: str
    description: str
    value: int | None
    #: This stage's value as a share of :data:`SPEAKER_FUNNEL_BASELINE`'s.
    #: ``None`` when either is unknown or the baseline is zero — a stage is
    #: never drawn at some default width to stand in for a share nobody
    #: measured.
    share_of_baseline_pct: float | None
    share_display: str


@dataclass(frozen=True, slots=True)
class Conversion:
    """One cohort conversion between adjacent lifecycle stages."""

    from_metric: str
    to_metric: str
    #: Panel label, e.g. "Speakers matched → Speakers invited". The arrow is
    #: visual shorthand and is deliberately not what a screen reader gets:
    #: "→" is announced inconsistently across readers, and in some it is
    #: silent, which would collapse two stage names into one phrase.
    label: str
    #: The same relation in prose, for ``aria-label`` and any text equivalent.
    accessible_label: str
    numerator: int | None
    denominator: int | None
    rate_pct: float | None
    display: str
    #: Why ``rate_pct`` is ``None``; ``None`` when the rate was computed.
    unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class Insight:
    """One deterministic sentence about the current numbers."""

    #: Stable identifier for tests and for the client's icon choice. Never a
    #: translated or displayed string.
    code: str
    #: ``"attention"``, ``"opportunity"``, ``"strength"`` or ``"neutral"``.
    tone: str
    title: str
    detail: str


@dataclass(frozen=True, slots=True)
class SpeakerPipeline:
    """The whole derived view: stages, conversions and insights."""

    stages: tuple[FunnelStage, ...]
    conversions: tuple[Conversion, ...]
    insights: tuple[Insight, ...]


#: Insight tones in the order they are offered, most actionable first. The
#: panel is capped at :data:`MAX_INSIGHTS`, so this ordering decides what a
#: coordinator reads when more than three apply.
_TONE_PRIORITY: Final[Mapping[str, int]] = {
    "attention": 0,
    "opportunity": 1,
    "strength": 2,
    "neutral": 3,
}


def _rate(numerator: int | None, denominator: int | None) -> tuple[float | None, str | None]:
    """Return ``(rate_pct, unavailable_reason)`` for one ratio.

    Three non-answers, kept apart because they are different facts: an
    unknown numerator, an unknown denominator, and a denominator of zero. The
    last is a *measured* emptiness — the query ran and found no upstream
    records — so its reason says that rather than implying a missing source.
    """
    if denominator is None:
        return None, "The upstream stage was not measured, so no rate can be calculated."
    if numerator is None:
        return None, "The downstream stage was not measured, so no rate can be calculated."
    if denominator == 0:
        return None, "No records reached the upstream stage, so there is no rate to calculate."
    return (numerator / denominator) * 100.0, None


def _stage_label(display_names: Mapping[str, str], metric_name: str) -> str:
    """The product's label for a metric, falling back to its canonical name.

    The fallback is a visible, greppable oddity rather than a crash: this
    function runs on a read path, and a register entry that gained a metric
    before this surface learned its label should degrade to showing the
    canonical name, not to a 500.
    """
    return display_names.get(metric_name, metric_name)


def _build_stages(
    values: Mapping[str, int | None],
    display_names: Mapping[str, str],
) -> tuple[FunnelStage, ...]:
    baseline = values.get(SPEAKER_FUNNEL_BASELINE)
    stages: list[FunnelStage] = []
    for metric_name in SPEAKER_FUNNEL_STAGES:
        value = values.get(metric_name)
        share, _reason = _rate(value, baseline)
        stages.append(
            FunnelStage(
                metric_name=metric_name,
                description=FUNNEL_STAGE_DESCRIPTIONS.get(
                    metric_name, _stage_label(display_names, metric_name)
                ),
                value=value,
                share_of_baseline_pct=share,
                share_display=format_percent(share),
            )
        )
    return tuple(stages)


def _build_conversions(
    values: Mapping[str, int | None],
    display_names: Mapping[str, str],
) -> tuple[Conversion, ...]:
    conversions: list[Conversion] = []
    for upstream, downstream in pairwise(SPEAKER_FUNNEL_STAGES):
        numerator = values.get(downstream)
        denominator = values.get(upstream)
        rate, reason = _rate(numerator, denominator)
        conversions.append(
            Conversion(
                from_metric=upstream,
                to_metric=downstream,
                label=(
                    f"{_stage_label(display_names, upstream)} → "
                    f"{_stage_label(display_names, downstream)}"
                ),
                accessible_label=(
                    f"{_stage_label(display_names, upstream)} to "
                    f"{_stage_label(display_names, downstream)}"
                ),
                numerator=numerator,
                denominator=denominator,
                rate_pct=rate,
                display=format_percent(rate),
                unavailable_reason=reason,
            )
        )
    return tuple(conversions)


def _conversion_rate(conversions: Sequence[Conversion], to_metric: str) -> float | None:
    return next(
        (c.rate_pct for c in conversions if c.to_metric == to_metric),
        None,
    )


def _build_insights(
    values: Mapping[str, int | None],
    conversions: Sequence[Conversion],
) -> tuple[Insight, ...]:
    """Derive at most :data:`MAX_INSIGHTS` sentences from the current numbers.

    Deterministic by construction: every branch is a comparison against a
    named threshold above, and nothing here samples, randomises or ranks by
    anything but :data:`_TONE_PRIORITY` and the order the rules are written.
    """
    baseline = values.get(SPEAKER_FUNNEL_BASELINE)
    if baseline is None or baseline < MINIMUM_BASELINE_FOR_INSIGHTS:
        return (
            Insight(
                code="insufficient_activity",
                tone="neutral",
                title="Not enough activity yet",
                detail=INSUFFICIENT_ACTIVITY_MESSAGE,
            ),
        )

    candidates: list[Insight] = []

    outreach = _conversion_rate(conversions, "pipeline_contacted")
    if outreach is not None and outreach < WEAK_OUTREACH_RATE_PCT:
        candidates.append(
            Insight(
                code="weak_outreach",
                tone="opportunity",
                title="Outreach is the narrowest step",
                detail=(
                    f"{format_percent(outreach)} of matched speakers have been invited. "
                    "Inviting more of the existing matches is the cheapest way to widen "
                    "everything downstream."
                ),
            )
        )

    confirmation = _conversion_rate(conversions, "pipeline_confirmed")
    if confirmation is not None and confirmation >= STRONG_CONFIRMATION_RATE_PCT:
        candidates.append(
            Insight(
                code="strong_confirmation",
                tone="strength",
                title="Invitations convert well",
                detail=(
                    f"{format_percent(confirmation)} of invited speakers go on to confirm, "
                    "which points to well-targeted matches."
                ),
            )
        )

    presentation = _conversion_rate(conversions, "pipeline_attended")
    if presentation is not None and presentation >= STRONG_PRESENTATION_RATE_PCT:
        candidates.append(
            Insight(
                code="strong_presentation",
                tone="strength",
                title="Confirmed speakers show up",
                detail=(
                    f"{format_percent(presentation)} of confirmed speakers presented, so "
                    "little is being lost between confirmation and the event."
                ),
            )
        )

    pending = values.get("pending_review_items")
    accepted = values.get("opportunities")
    if pending is not None and accepted is not None and pending + accepted > 0:
        # Both sides count `review_item` rows, which is what makes this share
        # legitimate where a pending-to-pipeline ratio would not be. It is
        # still a queue depth, not a conversion, and its wording says so.
        backlog_share = (pending / (pending + accepted)) * 100.0
        if backlog_share >= REVIEW_BACKLOG_SHARE_PCT:
            candidates.append(
                Insight(
                    code="review_backlog",
                    tone="attention",
                    title="The review queue is filling up",
                    detail=(
                        f"{format_percent(backlog_share)} of this unit's review items are "
                        "still pending. This is a queue depth, not a funnel stage — no "
                        "speaker is waiting on it."
                    ),
                )
            )

    if not candidates:
        return (
            Insight(
                code="nothing_notable",
                tone="neutral",
                title="Nothing stands out",
                detail=(
                    "Every stage is converting within its expected range, so there is no "
                    "single step to act on."
                ),
            ),
        )

    candidates.sort(key=lambda insight: _TONE_PRIORITY.get(insight.tone, len(_TONE_PRIORITY)))
    return tuple(candidates[:MAX_INSIGHTS])


def build_speaker_pipeline(
    values: Mapping[str, int | None],
    display_names: Mapping[str, str],
) -> SpeakerPipeline:
    """Shape measured metric values into the Speaker Pipeline view.

    Args:
        values: Canonical metric name to its measured value, or ``None`` for
            a metric the register answered as unknown. A name missing from
            the mapping is treated identically to ``None`` — this function
            never invents a zero for a metric it was not given.
        display_names: Canonical metric name to the label this product uses,
            as the register's CBA view already resolved it. Used for
            conversion labels only; no count is looked up by label.

    Returns:
        The stages, conversions and insights, all derived and none measured.
    """
    conversions = _build_conversions(values, display_names)
    return SpeakerPipeline(
        stages=_build_stages(values, display_names),
        conversions=conversions,
        insights=_build_insights(values, conversions),
    )
