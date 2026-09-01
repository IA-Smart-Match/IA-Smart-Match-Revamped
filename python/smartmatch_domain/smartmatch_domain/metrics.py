"""The accountable metric register required by ADR-0011.

The register describes numbers; it does not calculate them.  Query identifiers
are stable names that an outer adapter may bind to storage-backed functions.
Keeping that boundary explicit preserves the domain package's purity while
still making every metric answerable to exactly one query.

The five Pipeline metrics deliberately carry an ``unknown_reason``.  S12 has no
evidence source yet, so returning ``None`` is the truthful result.  An empty
drill-down alongside that value means "no rows can be known", not a measured
zero.  ``pending_review_items`` is different: its evidence already exists in
``review_item`` and the API binds its owning query to that table.

Every entry encodes ADR-0011's four rules:

* ``unknown_reason`` makes absence explicit and keeps it distinct from zero;
* ``canonical_name`` and ``definition`` give the number one name and meaning;
* singular ``owning_query`` names its only calculation;
* ``drill_down`` defines the constituent rows that same query must return.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["METRIC_REGISTER", "MetricDefinition", "get_metric"]


PIPELINE_UNKNOWN_REASON = "No evidence source yet: S12 Pipeline persistence is not started."


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """One immutable, accountable user-visible aggregate."""

    canonical_name: str
    display_name: str
    definition: str
    owning_query: str
    drill_down: str
    unknown_reason: str | None = None


METRIC_REGISTER: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        canonical_name="pipeline_matched",
        display_name="Matched",
        definition="Pipeline records that have reached the Matched stage or a later stage.",
        owning_query="pipeline_funnel_rows_v1",
        drill_down="The Pipeline records at Matched or any later funnel stage.",
        unknown_reason=PIPELINE_UNKNOWN_REASON,
    ),
    MetricDefinition(
        canonical_name="pipeline_contacted",
        display_name="Contacted",
        definition="Pipeline records that have reached the Contacted stage or a later stage.",
        owning_query="pipeline_funnel_rows_v1",
        drill_down="The Pipeline records at Contacted or any later funnel stage.",
        unknown_reason=PIPELINE_UNKNOWN_REASON,
    ),
    MetricDefinition(
        canonical_name="pipeline_confirmed",
        display_name="Confirmed",
        definition="Pipeline records that have reached the Confirmed stage or a later stage.",
        owning_query="pipeline_funnel_rows_v1",
        drill_down="The Pipeline records at Confirmed or any later funnel stage.",
        unknown_reason=PIPELINE_UNKNOWN_REASON,
    ),
    MetricDefinition(
        canonical_name="pipeline_attended",
        display_name="Attended",
        definition="Pipeline records that have reached the Attended stage or a later stage.",
        owning_query="pipeline_funnel_rows_v1",
        drill_down="The Pipeline records at Attended or the Member Inquiry funnel stage.",
        unknown_reason=PIPELINE_UNKNOWN_REASON,
    ),
    MetricDefinition(
        canonical_name="pipeline_member_inquiry",
        display_name="Member Inquiry",
        definition="Pipeline records that have reached the Member Inquiry stage.",
        owning_query="pipeline_funnel_rows_v1",
        drill_down="The Pipeline records at the Member Inquiry funnel stage.",
        unknown_reason=PIPELINE_UNKNOWN_REASON,
    ),
    MetricDefinition(
        canonical_name="pending_review_items",
        display_name="Pending review items",
        definition=(
            "Review items owned by this organizational unit whose review status is pending."
        ),
        owning_query="pending_review_item_rows_v1",
        drill_down="The pending review_item rows owned by this organizational unit.",
    ),
)


def get_metric(canonical_name: str) -> MetricDefinition | None:
    """Return the one registered definition for ``canonical_name``, if any."""
    return next(
        (metric for metric in METRIC_REGISTER if metric.canonical_name == canonical_name),
        None,
    )
