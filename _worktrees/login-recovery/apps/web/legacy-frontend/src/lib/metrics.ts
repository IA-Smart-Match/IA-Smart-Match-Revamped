/**
 * Maps ADR-0011 metric API payloads onto accountable UI primitives.
 * Pure functions — verified by `tsc --noEmit`.
 */
import type {
  AccountableMetric,
  MetricValue,
  Provenance,
} from "@/app/components/provenance";
import { knownValue, unknownValue } from "@/app/components/provenance";
import type { MetricDrillDownResponse, MetricSummary } from "@/lib/api";

/** Registered pipeline funnel metrics in display order (matches METRIC_REGISTER). */
export const PIPELINE_FUNNEL_METRIC_NAMES = [
  "pipeline_matched",
  "pipeline_contacted",
  "pipeline_confirmed",
  "pipeline_attended",
  "pipeline_member_inquiry",
] as const;

export type PipelineFunnelMetricName = (typeof PIPELINE_FUNNEL_METRIC_NAMES)[number];

export const PIPELINE_FUNNEL_STAGE_LABELS: Record<PipelineFunnelMetricName, string> = {
  pipeline_matched: "Matched",
  pipeline_contacted: "Contacted",
  pipeline_confirmed: "Confirmed",
  pipeline_attended: "Attended",
  pipeline_member_inquiry: "Member Inquiry",
};

/** Canonical name of the registered opportunities metric (`METRIC_REGISTER`). */
export const OPPORTUNITIES_METRIC_NAME = "opportunities";

/**
 * Why the opportunities number can be missing on the client.
 *
 * The metric itself *is* registered and bound server-side
 * (`_opportunities_rows_v1`), so the client never decides the value: it
 * either renders what `/v1/units/{id}/metrics` measured, or says it could
 * not read the register. It never substitutes a locally merged count.
 */
export const OPPORTUNITIES_UNKNOWN_REASON =
  "The registered `opportunities` metric could not be read from /v1/units/{unit_id}/metrics, so no count is available. This page never derives one from local CSV or crawler rows.";

/**
 * Canonical name of the registered pending-review metric (`METRIC_REGISTER`).
 *
 * This is the coordinator's discovery queue: `pending_review_item_rows_v1`
 * counts the review items this unit owns whose review status is still
 * pending — the rows a coordinator has to categorise before they can count
 * as opportunities under the approved counting rule. It is the one
 * registered metric that answers "what has discovery put in front of me",
 * which is why the discovery feed is built on it rather than on a number
 * assembled in the browser.
 */
export const PENDING_REVIEW_ITEMS_METRIC_NAME = "pending_review_items";

/** Why the pending-review count can be missing on the client. */
export const PENDING_REVIEW_UNKNOWN_REASON =
  "The registered `pending_review_items` metric could not be read from /v1/units/{unit_id}/metrics, so the size of the review queue is unknown. This feed never estimates it.";

/** Unknown-state stand-in for the registered pending-review metric. */
export function unavailablePendingReviewMetric(
  reason: string = PENDING_REVIEW_UNKNOWN_REASON,
): AccountableMetric {
  return {
    name: "Pending review items",
    definition:
      "Review items owned by this organizational unit whose review status is pending.",
    value: unknownValue(reason),
    provenance: "observed",
  };
}

/**
 * Why a score is absent on every page that is not the shortlist surface.
 *
 * Updated with card M10, and the change is a narrowing rather than a removal.
 * It used to say match scoring was not yet available at all, which was true
 * while G1 was open and no routes existed. Both have since changed: the factor
 * registry is approved and implemented (M6j), and
 * `/v1/units/{unit_id}/match-runs/{match_run_id}` reads persisted runs (M8b).
 * What remains true — and is the only honest thing these pages can say — is
 * that *they* do not fetch one. Leaving the old wording would have made a
 * stale claim about the platform; replacing it with nothing would have left a
 * bare "Unknown" carrying no reason, which ADR-0011 rule 1 exists to prevent.
 */
export const MATCHING_UNAVAILABLE_REASON =
  "The factor registry is approved, and heuristic scores live on persisted match runs read from /v1/units/{unit_id}/match-runs/{match_run_id} on the speaker-shortlist surface. This page does not fetch one, and it never derives a score locally.";

/** Unknown-state stand-in for a score this page does not read. */
export function unavailableMatchingMetric(
  reason: string = MATCHING_UNAVAILABLE_REASON,
): AccountableMetric {
  return {
    name: "Match score",
    definition:
      "Heuristic shortlist from approved factors (topic_relevance, travel_burden); no percentage display.",
    value: unknownValue(reason),
    provenance: "observed",
  };
}

/** Placeholder until S12 and the stakeholder-approved opportunities metric exist. */
export function unavailableOpportunitiesMetric(
  reason: string = OPPORTUNITIES_UNKNOWN_REASON,
): AccountableMetric {
  return {
    name: "Opportunities",
    definition:
      "Events eligible for coordinator outreach under the approved opportunities metric definition (pending stakeholder workshop).",
    value: unknownValue(reason),
    provenance: "observed",
  };
}

/** Converts one API summary into a discriminated {@link MetricValue}. */
export function metricValueFromSummary(summary: MetricSummary): MetricValue {
  if (summary.value === null) {
    return unknownValue(
      summary.unknown_reason ?? "No evidence source exists for this metric.",
    );
  }
  return knownValue(summary.value);
}

export interface AccountableMetricOptions {
  provenance: Provenance;
  onOpenDrilldown?: () => void;
}

/** Builds an {@link AccountableMetric} from a registered metric summary. */
export function accountableMetricFromSummary(
  summary: MetricSummary,
  options: AccountableMetricOptions,
): AccountableMetric {
  const value = metricValueFromSummary(summary);
  const rowCount = summary.value ?? undefined;

  return {
    name: summary.display_name,
    definition: summary.definition,
    value,
    provenance: options.provenance,
    drilldown: options.onOpenDrilldown
      ? {
          rowSetDigest: summary.name,
          rowCount,
          label:
            rowCount !== undefined
              ? `View ${rowCount.toLocaleString("en-US")} rows`
              : "View details",
          onOpen: options.onOpenDrilldown,
        }
      : undefined,
  };
}

/** Fallback when the metrics API cannot be reached (no unit scope or auth). */
export function unavailablePipelineMetric(
  metricName: PipelineFunnelMetricName,
  reason: string,
): AccountableMetric {
  const stage = PIPELINE_FUNNEL_STAGE_LABELS[metricName];
  return {
    name: stage,
    definition: `Registered metric \`${metricName}\` — pipeline records at the ${stage} funnel stage or later.`,
    value: unknownValue(reason),
    provenance: "observed",
  };
}

/** Wraps a demo or legacy numeric read with explicit provenance (not in the register). */
export function accountableDemoMetric(
  name: string,
  definition: string,
  numericValue: number | null,
  options: {
    provenance: Provenance;
    unknownReason?: string;
    formatPercent?: boolean;
    onOpenDrilldown?: () => void;
  },
): AccountableMetric {
  const value: MetricValue =
    numericValue === null
      ? unknownValue(options.unknownReason ?? "No evidence for this value.")
      : knownValue(numericValue);

  return {
    name,
    definition,
    value,
    provenance: options.provenance,
    drilldown: options.onOpenDrilldown
      ? {
          rowSetDigest: name,
          rowCount: numericValue ?? undefined,
          label: "View source",
          onOpen: options.onOpenDrilldown,
        }
      : undefined,
  };
}

/** Row fields safe to list in drill-down UI (ADR-0014 minimum disclosure). */
export function drilldownRowPreview(row: Record<string, unknown>): {
  id: string;
  row_index: string;
  status: string;
} {
  return {
    id: String(row.id ?? "—"),
    row_index: String(row.row_index ?? "—"),
    status: String(row.status ?? "—"),
  };
}

export function indexMetricsByName(
  metrics: MetricSummary[],
): Record<string, MetricSummary> {
  return Object.fromEntries(metrics.map((metric) => [metric.name, metric]));
}

export function assertDrilldownMatchesAggregate(
  drilldown: MetricDrillDownResponse,
): boolean {
  if (drilldown.aggregate_value === null) {
    return drilldown.rows.length === 0;
  }
  return drilldown.rows.length === drilldown.aggregate_value;
}
