"""The Speaker Pipeline analytics surface: one read, one owning query each.

This router adds no measurement. It calls the *same* owning queries
``smartmatch_api.routers.metrics`` already binds each registered metric to
(:func:`~smartmatch_api.routers.metrics._evidence_for`), under the *same*
authorization (:func:`~smartmatch_api.routers.metrics._authorize_aggregate_read`),
and hands the resulting values to
:func:`smartmatch_domain.speaker_pipeline.build_speaker_pipeline` for shaping.
A number served here and the same number served by ``GET
/v1/units/{unit_id}/metrics`` cannot disagree, because only one query
produced either.

It exists as a separate route rather than as extra fields on the metrics
collection for one reason: the metrics collection is a *register* listing —
every entry, whatever product view was asked for — and a funnel is a claim
about six particular entries and the order three of the transitions between
them run in. Folding a claim that specific into the general listing would
make every consumer of the register carry it.

## Why one request and not six

The reference design's six figures are six registered metrics. Fetching them
one at a time would be six round trips and six independent authorizations for
one screen, and — worse — six moments at which the underlying rows could
change, so a conversion rate could be computed from a numerator and a
denominator measured seconds apart. Every metric here is measured inside one
request, against one session.

## Date range

There is no date filter, and the payload says so in
:class:`SpeakerPipelineRange` rather than leaving the client to invent a
label. None of the three owning queries takes a window today; adding one
would change what four published metrics mean on every surface that already
reads them, which is a decision about the register and not a detail of this
screen. The honest label for what this route returns is "all time", and the
client renders that.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Path, Request, Response
from pydantic import BaseModel, Field
from smartmatch_domain.metrics import MetricDefinition
from smartmatch_domain.speaker_pipeline import (
    COMPANION_METRIC_DESCRIPTIONS,
    COMPANION_METRIC_NAMES,
    SPEAKER_FUNNEL_BASELINE,
    SPEAKER_FUNNEL_STAGES,
    build_speaker_pipeline,
)

from smartmatch_api.dependencies import CurrentPrincipal, DbSession

# Imported under their own names, underscores and all, rather than renamed in
# `routers/metrics.py` to make this import read more tidily.
#
# The underscore marks these private to the *package*, not unreachable from a
# sibling module, and reaching for them here is the whole point: this route
# must authorize and measure through the identical objects `metrics.py` uses,
# not through equivalents of them.
#
# Renaming them was tried and was wrong, for a reason worth recording rather
# than rediscovering: `tests/authz/test_policy_matrix.py` matches an operation
# to its authorization runner by the authorizer's *name*, so renaming
# `_authorize_aggregate_read` quietly moved both metric routes outside that
# matrix's coverage until the matrix itself was edited to follow. A public
# alias has the same defect with an extra indirection — two names for one
# permit, and a reader or a grep that finds only one of them.
from smartmatch_api.routers.metrics import (
    _NOT_MODIFIED_RESPONSE,
    MetricSummary,
    MetricSurface,
    _authorize_aggregate_read,
    _conditional_json_response,
    _evidence_for,
    _register_for,
    _summary,
)

router = APIRouter(prefix="/v1/units", tags=["metrics"])

#: The register view this surface is written against. The Speaker Pipeline is
#: a CBA screen: its labels ("Speakers matched") and its four-stage funnel are
#: the CBA view of the register, ``pipeline_member_inquiry`` excluded. Passing
#: this explicitly rather than accepting a ``surface`` query parameter keeps
#: the funnel's stage list and the payload's metric list from ever disagreeing.
_SURFACE: MetricSurface = "cba"

#: What the absence of date filtering is called in the payload.
_ALL_TIME_LABEL: Final[str] = "All time"
_ALL_TIME_NOTE: Final[str] = (
    "These figures are not filtered by date. Each one counts every record this unit "
    "owns, because the owning query behind it takes no time window."
)


class SpeakerPipelineRange(BaseModel):
    """The window these figures cover, named rather than assumed."""

    kind: str = Field(description="Machine-readable window identifier; only 'all_time' today.")
    label: str = Field(description="What to show the reader in the range control.")
    note: str = Field(description="Why the window is what it is.")


class FunnelStageOut(BaseModel):
    """One lifecycle stage, with the width it may be drawn at."""

    metric_name: str
    display_name: str
    description: str
    value: int | None = Field(description="Measured count, or null when unmeasured.")
    unknown_reason: str | None = None
    share_of_baseline_pct: float | None = Field(
        description="Share of the baseline stage, or null when it cannot be calculated."
    )
    share_display: str = Field(description="The server's rendering of that share.")


class ConversionOut(BaseModel):
    """One cohort conversion between adjacent lifecycle stages."""

    from_metric: str
    to_metric: str
    label: str = Field(description="Panel label using an arrow; not for a screen reader.")
    accessible_label: str = Field(description="The same relation in prose, for aria-label.")
    numerator: int | None
    denominator: int | None
    rate_pct: float | None
    display: str = Field(description="The server's rendering; an em dash when there is no rate.")
    unavailable_reason: str | None = None


class InsightOut(BaseModel):
    """One deterministic sentence derived from the figures above."""

    code: str
    tone: str
    title: str
    detail: str


class CompanionMetricOut(BaseModel):
    """A registered metric shown beside the funnel but not inside it."""

    metric_name: str
    display_name: str
    description: str
    definition: str
    value: int | None
    unknown_reason: str | None = None


class SpeakerPipelineResponse(BaseModel):
    """Everything the Speaker Pipeline screen renders, from one read."""

    unit_id: uuid.UUID
    range: SpeakerPipelineRange
    metrics: list[MetricSummary] = Field(
        description="Every registered metric in this surface's view, unchanged."
    )
    baseline_metric: str = Field(description="The stage funnel widths are normalized against.")
    stages: list[FunnelStageOut]
    companions: list[CompanionMetricOut] = Field(
        description=(
            "Registered metrics presented beside the funnel. They count a different "
            "entity, so no conversion is defined between them and any stage."
        )
    )
    conversions: list[ConversionOut] = Field(
        description="Only transitions the stored lifecycle makes a cohort conversion."
    )
    insights: list[InsightOut]


def _definitions(surface: MetricSurface) -> dict[str, MetricDefinition]:
    return {metric.canonical_name: metric for metric in _register_for(surface)}


@router.get(
    "/{unit_id}/speaker-pipeline",
    response_model=SpeakerPipelineResponse,
    responses=_NOT_MODIFIED_RESPONSE,
    summary="The Speaker Pipeline funnel, conversions and insights for a unit",
)
def speaker_pipeline(
    principal: CurrentPrincipal,
    session: DbSession,
    request: Request,
    unit_id: Annotated[uuid.UUID, Path()],
) -> Response:
    """Measure every metric on this surface once, then shape the result.

    Authorization is the metrics collection's aggregate rule verbatim — any
    active unit membership with a role, tenant-wide for ``admin`` — and it
    runs before any conditional-request handling, so an ``If-None-Match``
    header can never tell an unauthorized caller that a representation
    exists.

    A metric whose owning query answered unknown stays unknown the whole way
    through: it is ``null`` in ``metrics`` and in its stage, and every
    conversion that would have used it carries an ``unavailable_reason``
    instead of a rate. Nothing here substitutes a zero for an absence.
    """
    _authorize_aggregate_read(session, principal, unit_id)

    definitions = _definitions(_SURFACE)
    summaries: list[MetricSummary] = []
    values: dict[str, int | None] = {}
    for metric in _register_for(_SURFACE):
        evidence = _evidence_for(session, principal.tenant_id, unit_id, metric)
        summaries.append(_summary(unit_id, metric, evidence, _SURFACE))
        values[metric.canonical_name] = evidence.value

    by_name = {summary.name: summary for summary in summaries}
    display_names = {name: definition.display_name for name, definition in definitions.items()}
    shaped = build_speaker_pipeline(values, display_names)

    stages = [
        FunnelStageOut(
            metric_name=stage.metric_name,
            display_name=display_names.get(stage.metric_name, stage.metric_name),
            description=stage.description,
            value=stage.value,
            unknown_reason=by_name[stage.metric_name].unknown_reason
            if stage.metric_name in by_name
            else None,
            share_of_baseline_pct=stage.share_of_baseline_pct,
            share_display=stage.share_display,
        )
        for stage in shaped.stages
        if stage.metric_name in by_name
    ]

    companions = [
        CompanionMetricOut(
            metric_name=name,
            display_name=by_name[name].display_name,
            description=COMPANION_METRIC_DESCRIPTIONS.get(name, ""),
            definition=by_name[name].definition,
            value=by_name[name].value,
            unknown_reason=by_name[name].unknown_reason,
        )
        for name in COMPANION_METRIC_NAMES
        if name in by_name
    ]

    response_model = SpeakerPipelineResponse(
        unit_id=unit_id,
        range=SpeakerPipelineRange(kind="all_time", label=_ALL_TIME_LABEL, note=_ALL_TIME_NOTE),
        metrics=summaries,
        baseline_metric=SPEAKER_FUNNEL_BASELINE,
        stages=stages,
        companions=companions,
        conversions=[
            ConversionOut(
                from_metric=conversion.from_metric,
                to_metric=conversion.to_metric,
                label=conversion.label,
                accessible_label=conversion.accessible_label,
                numerator=conversion.numerator,
                denominator=conversion.denominator,
                rate_pct=conversion.rate_pct,
                display=conversion.display,
                unavailable_reason=conversion.unavailable_reason,
            )
            for conversion in shaped.conversions
            # A stage the register did not return has no card on the screen,
            # so a conversion into or out of it would annotate nothing.
            if conversion.from_metric in by_name and conversion.to_metric in by_name
        ],
        insights=[
            InsightOut(
                code=insight.code, tone=insight.tone, title=insight.title, detail=insight.detail
            )
            for insight in shaped.insights
        ],
    )
    return _conditional_json_response(response_model, request)


#: Re-exported so a reader of this module can see which stages it claims
#: without following two imports. Not used here; the stage list travels in
#: the payload.
__all__ = ["SPEAKER_FUNNEL_STAGES", "router"]
