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
