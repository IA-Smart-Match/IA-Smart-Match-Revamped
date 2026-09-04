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
import { useUnitMetrics } from "@/app/hooks/useUnitMetrics";

const TILE_ICONS: Record<PipelineFunnelMetricName, LucideIcon> = {
  pipeline_matched: Users,
  pipeline_contacted: CalendarDays,
  pipeline_confirmed: CheckCircle2,
  pipeline_attended: UserPlus,
  pipeline_member_inquiry: Briefcase,
};

const TILE_ICON_CLASS: Record<PipelineFunnelMetricName, string> = {
  pipeline_matched: "bg-primary/10 text-primary",
  pipeline_contacted: "bg-primary/10 text-primary",
  pipeline_confirmed: "bg-green-100 text-green-600",
  pipeline_attended: "bg-orange-100 text-orange-600",
  pipeline_member_inquiry: "bg-indigo-100 text-indigo-600",
};

export interface PipelineFunnelTilesProps {
  reloadToken?: number;
  className?: string;
}

export function PipelineFunnelTiles({
  reloadToken = 0,
  className,
}: PipelineFunnelTilesProps) {
  const {
    metricsByName,
    status,
    loadError,
    metricsUnavailableReason,
    drilldownOpen,
    setDrilldownOpen,
    drilldownLoading,
    drilldownError,
    drilldown,
    openDrilldown,
  } = useUnitMetrics(reloadToken);

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

    const fallbackReason =
      status === "unavailable"
        ? (loadError ?? metricsUnavailableReason)
        : status === "loading"
          ? "Loading registered metrics…"
          : "Registered metric is not available.";

    return unavailablePipelineMetric(metricName, fallbackReason);
  }

  return (
    <>
      <div className={className ?? "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4"}>
        {PIPELINE_FUNNEL_METRIC_NAMES.map((metricName) => {
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
