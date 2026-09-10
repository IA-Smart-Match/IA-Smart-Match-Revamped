import type { LucideIcon } from "lucide-react";
import {
  Briefcase,
  CalendarDays,
  CheckCircle2,
  UserPlus,
  Users,
} from "lucide-react";

import {
  AccountableValue,
  MetricDrilldownSheet,
} from "@/app/components/provenance";
import {
  accountableMetricFromSummary,
  PIPELINE_FUNNEL_METRIC_NAMES,
  PIPELINE_FUNNEL_STAGE_LABELS,
  type PipelineFunnelMetricName,
  unavailablePipelineMetric,
} from "@/lib/metrics";
import {
  METRICS_UNIT_RESOLVING_REASON,
  useUnitMetrics,
} from "@/app/hooks/useUnitMetrics";
import { isCapabilityEnabled } from "@/lib/productScope";

const TILE_ICONS: Record<PipelineFunnelMetricName, LucideIcon> = {
  pipeline_matched: Users,
  pipeline_contacted: CalendarDays,
  pipeline_confirmed: CheckCircle2,
  pipeline_attended: UserPlus,
  pipeline_member_inquiry: Briefcase,
};

const TILE_ICON_CLASS: Record<PipelineFunnelMetricName, string> = {
  pipeline_matched: "bg-blue-100 text-blue-600",
  pipeline_contacted: "bg-blue-100 text-blue-600",
  pipeline_confirmed: "bg-green-100 text-green-600",
  pipeline_attended: "bg-orange-100 text-orange-600",
  pipeline_member_inquiry: "bg-indigo-100 text-indigo-600",
};

/**
 * The stages this product presents, which is not the same as the stages it stores.
 *
 * `member_inquiry` remains a real pipeline stage: the enum, the rows, migration
 * `0011`, the registered `pipeline_member_inquiry` metric, and every historical
 * record are untouched, and `PIPELINE_FUNNEL_METRIC_NAMES` still lists it so the
 * client stays in step with `METRIC_REGISTER`. What the CBA product has is no
 * approved *outcome* it corresponds to — there is no chapter to inquire about
 * (customer §4, §20) — so offering a tile would be reporting on a funnel step
 * this product's users can never reach.
 *
 * Suppressing the presentation rather than the data is the whole point:
 * `docs/plans/open-questions/cba-phase-deferred.md` re-enters this only with a
 * CBA-defined post-event outcome and a metric-register definition, and that
 * re-entry needs the history to still be there.
 */
const OFFERED_FUNNEL_METRIC_NAMES: readonly PipelineFunnelMetricName[] =
  PIPELINE_FUNNEL_METRIC_NAMES.filter(
    (metricName) =>
      metricName !== "pipeline_member_inquiry" ||
      isCapabilityEnabled("member_inquiry_narrative"),
  );

/**
 * Grid columns, keyed by tile count.
 *
 * A template literal (`lg:grid-cols-${n}`) would not survive Tailwind's static
 * extraction — the class would simply not exist in the stylesheet — so the two
 * reachable widths are written out where the scanner can see them.
 */
const FUNNEL_GRID_CLASS: Record<number, string> = {
  4: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4",
  5: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4",
};

export interface PipelineFunnelTilesProps {
  /**
   * The unit the server granted the signed-in account
   * (`grantedPortal(portalAccess, "admin")?.default_unit_id ?? null`), or
   * `null` while `GET /v1/me/portals` is in flight or the grant carries no
   * unit.
   *
   * **Required, and deliberately not optional.** This component has no page of
   * its own and no grant of its own: it is rendered inside `Dashboard.tsx` and
   * `Pipeline.tsx`, and only they know which unit their screen is about. An
   * optional prop defaulting to `null` would let a future third caller mount
   * the funnel with no unit and get five silently unknown tiles — a caller's
   * ignorance rendered as an empty state instead of caught at compile time. A
   * required `string | null` makes it a type error to mount these tiles
   * without having answered the question, while still letting the honest
   * `null` through.
   *
   * It replaces `getConfiguredUnitId()` inside `useUnitMetrics`, the
   * `VITE_SMARTMATCH_UNIT_ID` build variable that is unset on the deployed
   * pilot VM — so on that deployment every tile read "unavailable" and named a
   * build variable at a reader who cannot set one.
   */
  unitId: string | null;
  /**
   * Which flavour of `unitId === null` this is: `true` while the portal
   * mapping is still being read, `false` once it has settled. The two are
   * different sentences on screen, and neither one is "there is none".
   */
  unitResolving?: boolean;
  reloadToken?: number;
  className?: string;
}

export function PipelineFunnelTiles({
  unitId,
  unitResolving = false,
  reloadToken = 0,
  className,
}: PipelineFunnelTilesProps) {
  const {
    metricsByName,
    status,
    loadError,
    metricsUnavailableReason,
    metricsNoUnitReason,
    drilldownOpen,
    setDrilldownOpen,
    drilldownLoading,
    drilldownError,
    drilldown,
    openDrilldown,
  } = useUnitMetrics(unitId, reloadToken);

  function metricForStage(metricName: PipelineFunnelMetricName) {
    const summary = metricsByName[metricName];
    if (summary) {
      return accountableMetricFromSummary(summary, {
        provenance: "observed",
        onOpenDrilldown: () => {
          void openDrilldown(metricName);
        },
      });
    }

    // Four states, kept four sentences. `"idle"` splits in two because
    // `unitId === null` is two different facts (see `unitResolving`), and
    // neither of them is the fifth thing a tile must never say — that the
    // count is zero. Every branch here still produces an *unaccountable
    // unknown* via `unavailablePipelineMetric`, per ADR-0011 rule 1.
    const fallbackReason =
      status === "unavailable"
        ? (loadError ?? metricsUnavailableReason)
        : status === "loading"
          ? "Loading registered metrics…"
          : status === "idle"
            ? unitResolving
              ? METRICS_UNIT_RESOLVING_REASON
              : metricsNoUnitReason
            : "Registered metric is not available.";

    return unavailablePipelineMetric(metricName, fallbackReason);
  }

  return (
    <>
      <div
        className={
          className ??
          FUNNEL_GRID_CLASS[OFFERED_FUNNEL_METRIC_NAMES.length] ??
          "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
        }
      >
        {OFFERED_FUNNEL_METRIC_NAMES.map((metricName) => {
          const Icon = TILE_ICONS[metricName];
          const metric = metricForStage(metricName);
          const stageLabel = PIPELINE_FUNNEL_STAGE_LABELS[metricName];

          return (
            <div
              key={metricName}
              className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm"
            >
              <div className="flex items-center gap-3 mb-2">
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center ${TILE_ICON_CLASS[metricName]}`}
                >
                  <Icon className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-gray-600">{stageLabel}</p>
                  <p className="text-2xl font-semibold text-gray-900">
                    <AccountableValue metric={metric} />
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <MetricDrilldownSheet
        open={drilldownOpen}
        onOpenChange={setDrilldownOpen}
        loading={drilldownLoading}
        drilldown={drilldown}
        error={drilldownError}
      />
    </>
  );
}
