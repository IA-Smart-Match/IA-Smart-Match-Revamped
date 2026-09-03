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

/** Matches `factor_registry.REGISTRY_STATUS == "proposed"` — no scores until G1 closes. */
export const MATCHING_UNAVAILABLE_REASON =
  "Match scoring, ranks, and factor explanations remain blocked until gate G1 approves the factor registry and golden cases.";

/** Placeholder until D1/G1 approves the factor registry and match_run exists. */
export function unavailableMatchingMetric(
  reason: string = MATCHING_UNAVAILABLE_REASON,
): AccountableMetric {
  return {
    name: "Match score",
    definition:
      "Heuristic match score from an approved factor registry and match_run (pending gate G1).",
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

/**
 * Stage-to-stage conversion between two *registered* funnel metrics.
 *
 * Both endpoints come from the same metrics API, so the ratio inherits their
 * accountability: unknown at either end (or a zero denominator, which is a
 * measured "nothing entered this stage" rather than a rate of zero) yields an
 * unknown value, never a fabricated `0.0%`.
 */
export function stageConversionMetric(
  from: PipelineFunnelMetricName,
  to: PipelineFunnelMetricName,
  metricsByName: Record<string, MetricSummary>,
  unavailableReason: string,
): AccountableMetric {
  const fromLabel = PIPELINE_FUNNEL_STAGE_LABELS[from];
  const toLabel = PIPELINE_FUNNEL_STAGE_LABELS[to];
  const name = `${fromLabel} → ${toLabel}`;
  const definition =
    `Registered \`${to}\` divided by registered \`${from}\`. ` +
    "Both operands come from the metrics register; no client-side row merge is involved.";

  const fromSummary = metricsByName[from];
  const toSummary = metricsByName[to];

  function unknown(reason: string): AccountableMetric {
    return { name, definition, value: unknownValue(reason), provenance: "observed" };
  }

  if (!fromSummary || !toSummary) {
    return unknown(unavailableReason);
  }
  if (fromSummary.value === null) {
    return unknown(
      fromSummary.unknown_reason ?? `\`${from}\` is unknown, so the ratio is unknown.`,
    );
  }
  if (toSummary.value === null) {
    return unknown(
      toSummary.unknown_reason ?? `\`${to}\` is unknown, so the ratio is unknown.`,
    );
  }
  if (fromSummary.value === 0) {
    return unknown(
      `No records have reached ${fromLabel}, so there is no denominator for this conversion rate.`,
    );
  }

  return {
    name,
    definition,
    value: knownValue(toSummary.value / fromSummary.value),
    provenance: "observed",
  };
}
