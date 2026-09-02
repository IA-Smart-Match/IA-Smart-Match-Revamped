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

``opportunities`` carries the same honest-unknown shape as the Pipeline
metrics: S12 pipeline persistence (which owns its evidence source) has not
started, so card O1 can only register the definition, not resolve a value.
Cards O2 (persistence) and O3 (owning-query binding) close that gap later; see
`docs/decisions/p8-opportunities-decision-draft.md` (CLOSED 2026-09-02) for the
ratified counting rule this module copies verbatim.

Every entry encodes ADR-0011's four rules:

* ``unknown_reason`` makes absence explicit and keeps it distinct from zero;
* ``canonical_name`` and ``definition`` give the number one name and meaning;
* singular ``owning_query`` names its only calculation;
* ``drill_down`` defines the constituent rows that same query must return.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "METRIC_REGISTER",
    "OPPORTUNITIES_UNKNOWN_REASON",
    "OPPORTUNITY_IN_LIST_CATEGORIES",
    "MetricDefinition",
    "OpportunityCategoryShape",
    "get_metric",
    "shape_opportunity_category",
]


PIPELINE_UNKNOWN_REASON = "No evidence source yet: S12 Pipeline persistence is not started."

OPPORTUNITIES_UNKNOWN_REASON = (
    "No evidence source yet: S12 pipeline persistence is not started, "
    "so opportunities has no owning query to resolve a value from."
)

# The ratified in-list programmatic engagement types, copied verbatim from
# `docs/decisions/p8-opportunities-decision-draft.md` §1 (CLOSED 2026-09-02).
# This set is non-exhaustive by design: the IA West Coordinator may extend
# practice through review without treating an unmapped label as an error.
# Comparison against it must be case-insensitive (see
# `shape_opportunity_category`), so the set itself is stored lower-cased.
OPPORTUNITY_IN_LIST_CATEGORIES: frozenset[str] = frozenset(
    {
        "hackathon",
        "datathon",
        "competition",
        "guest lecturer event",
        "school event",
    }
)


class OpportunityCategoryShape(Enum):
    """The three honest outcomes for one event row's category.

    A boolean in-list/out-of-list flag would misreport "out-of-list" as an
    error. It is not: the decision record is explicit that the in-list set is
    non-exhaustive and an out-of-list category is *pending coordinator
    review*, not invalid. An absent category carries the same pending state —
    there is nothing to review yet, but nothing disqualifying either.
    """

    IN_LIST = "in-list"
    PENDING_REVIEW = "pending-review"


def shape_opportunity_category(category: str | None) -> OpportunityCategoryShape:
    """Classify one event row's category per the ratified counting rule.

    Returns ``IN_LIST`` when ``category`` (case-insensitively) matches
    `OPPORTUNITY_IN_LIST_CATEGORIES`, and ``PENDING_REVIEW`` otherwise —
    whether the category is an out-of-list label or is absent entirely.
    Neither non-``IN_LIST`` case is ever reported as an error.
    """
    if category is not None and category.strip().casefold() in OPPORTUNITY_IN_LIST_CATEGORIES:
        return OpportunityCategoryShape.IN_LIST
    return OpportunityCategoryShape.PENDING_REVIEW


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
    MetricDefinition(
        canonical_name="opportunities",
        display_name="Opportunities",
        definition=(
            "An event row counts toward opportunities when its category is one of the "
            "in-list programmatic engagement types: hackathon, datathon, competition, "
            "guest lecturer event, school event. Rows whose category is out-of-list "
            "(including raw/unmapped examples) do not count until the IA West Coordinator "
            "reviews and either assigns an in-list category or explicitly approves "
            "inclusion. Out-of-list does not mean invalid — the in-list set is "
            "non-exhaustive; coordinators may extend practice through review without "
            "treating unknown labels as errors."
        ),
        owning_query="opportunities_rows_v1",
        drill_down="The event rows whose category is in-list under the counting rule above.",
        unknown_reason=OPPORTUNITIES_UNKNOWN_REASON,
    ),
)


def get_metric(canonical_name: str) -> MetricDefinition | None:
    """Return the one registered definition for ``canonical_name``, if any."""
    return next(
        (metric for metric in METRIC_REGISTER if metric.canonical_name == canonical_name),
        None,
    )
