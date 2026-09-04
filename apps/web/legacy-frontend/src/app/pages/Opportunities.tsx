/**
 * Opportunities (P8 card O4a).
 *
 * The count on this page is the registered `opportunities` metric read from
 * `GET /v1/units/{unit_id}/metrics`, and the list behind it is the drill-down
 * of that same owning query (`GET …/metrics/opportunities/drill-down`) — one
 * definition, one query, one number (ADR-0011 rules 3 and 4).
 *
 * There is deliberately no client-side merge of the legacy CSV/crawler rows
 * here: no fabricated dates or roles, no locally computed count, and no match
 * scores (blocked on gate G1). When the register cannot be read the value
 * renders as unknown with the reason — never as zero.
 */
import { AlertCircle, Briefcase } from "lucide-react";

import { AccountableValue, MetricDrilldownSheet } from "@/app/components/provenance";
import { useUnitMetrics } from "@/app/hooks/useUnitMetrics";
import {
  accountableMetricFromSummary,
  MATCHING_UNAVAILABLE_REASON,
  OPPORTUNITIES_METRIC_NAME,
  OPPORTUNITIES_UNKNOWN_REASON,
  unavailableOpportunitiesMetric,
} from "@/lib/metrics";

export function Opportunities() {
  const {
    metricsByName,
    status,
    loadError,
    metricsUnavailableReason,
    openDrilldown,
    drilldownOpen,
    setDrilldownOpen,
    drilldownLoading,
    drilldownError,
    drilldown,
  } = useUnitMetrics();

  const summary = metricsByName[OPPORTUNITIES_METRIC_NAME];
  const unavailableReason =
    status === "unavailable"
      ? (loadError ?? metricsUnavailableReason)
      : status === "loading"
        ? "Loading the registered opportunities metric…"
        : OPPORTUNITIES_UNKNOWN_REASON;

  const opportunitiesMetric = summary
    ? accountableMetricFromSummary(summary, {
        provenance: "observed",
        onOpenDrilldown: () => {
          void openDrilldown(OPPORTUNITIES_METRIC_NAME);
        },
      })
    : unavailableOpportunitiesMetric(unavailableReason);

  const definition =
    summary?.definition ??
    "Events eligible for coordinator outreach under the registered opportunities counting rule.";

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-gray-900">Opportunities</h1>
        <p className="mt-1 text-gray-600">
          The count and the list both come from the registered <code>opportunities</code> metric and
          its drill-down. Nothing on this page is merged or counted in the browser.
        </p>
      </div>

      <div
        className="rounded-2xl border border-[#d9cbc4] bg-white p-8 shadow-sm"
        aria-labelledby="opportunities-metric-heading"
      >
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#edf5f0] text-[#005030]">
            {summary ? (
              <Briefcase className="h-5 w-5" aria-hidden="true" />
            ) : (
              <AlertCircle className="h-5 w-5" aria-hidden="true" />
            )}
          </div>
          <div className="space-y-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#005030]/70">
                Registered metric · {OPPORTUNITIES_METRIC_NAME}
              </p>
              <h2
                id="opportunities-metric-heading"
                className="mt-2 text-2xl font-semibold text-gray-900"
              >
                {summary?.display_name ?? "Opportunities"}
              </h2>
            </div>
            <p className="text-3xl font-semibold tracking-tight text-gray-900">
              <AccountableValue
                metric={opportunitiesMetric}
                formatNumber={(value) => value.toLocaleString("en-US")}
              />
            </p>
            <p className="text-sm leading-6 text-gray-600">{definition}</p>
            {summary?.value === null ? (
              <p className="text-sm leading-6 text-gray-600">
                {summary.unknown_reason ??
                  "The server reported this metric as unknown. Unknown is not zero."}
              </p>
            ) : null}
            {summary ? null : (
              <p className="text-sm leading-6 text-gray-600">{unavailableReason}</p>
            )}
            <p className="text-sm leading-6 text-gray-600">
              Clicking the value lists exactly the rows the aggregate was calculated from. Match
              scores stay off this page: {MATCHING_UNAVAILABLE_REASON}
            </p>
          </div>
        </div>
      </div>

      <MetricDrilldownSheet
        open={drilldownOpen}
        onOpenChange={setDrilldownOpen}
        loading={drilldownLoading}
        drilldown={drilldown}
        error={drilldownError}
      />
    </div>
  );
}
