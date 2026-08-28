import { useCallback, useEffect, useState } from "react";

import {
  fetchMetricDrillDown,
  fetchUnitMetrics,
  getConfiguredUnitId,
  hasSmartmatchAuth,
  type MetricDrillDownResponse,
  type MetricSummary,
} from "@/lib/api";
import { indexMetricsByName } from "@/lib/metrics";

export type UnitMetricsStatus = "idle" | "loading" | "ready" | "unavailable";

const METRICS_UNAVAILABLE_REASON =
  "Registered metrics require VITE_SMARTMATCH_UNIT_ID and a bearer token (VITE_SMARTMATCH_BEARER_TOKEN or session storage).";

export function useUnitMetrics(reloadToken = 0) {
  const unitId = getConfiguredUnitId();
  const [metricsByName, setMetricsByName] = useState<Record<string, MetricSummary>>({});
  const [status, setStatus] = useState<UnitMetricsStatus>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);

  const [drilldownOpen, setDrilldownOpen] = useState(false);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [drilldownError, setDrilldownError] = useState<string | null>(null);
  const [drilldown, setDrilldown] = useState<MetricDrillDownResponse | null>(null);

  useEffect(() => {
    if (!unitId || !hasSmartmatchAuth()) {
      setMetricsByName({});
      setStatus("unavailable");
      setLoadError(METRICS_UNAVAILABLE_REASON);
      return;
    }

    let active = true;
    setStatus("loading");
    setLoadError(null);

    fetchUnitMetrics(unitId)
      .then((response) => {
        if (!active) {
          return;
        }
        setMetricsByName(indexMetricsByName(response.metrics));
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (!active) {
          return;
        }
        setMetricsByName({});
        setStatus("unavailable");
        setLoadError(
          err instanceof Error ? err.message : "Failed to load accountable metrics.",
        );
      });

    return () => {
      active = false;
    };
  }, [unitId, reloadToken]);

  const openDrilldown = useCallback(
    async (metricName: string) => {
      if (!unitId || !hasSmartmatchAuth()) {
        return;
      }
      setDrilldownOpen(true);
      setDrilldownLoading(true);
      setDrilldownError(null);
      setDrilldown(null);

      try {
        const response = await fetchMetricDrillDown(unitId, metricName);
        setDrilldown(response);
      } catch (err: unknown) {
        setDrilldownError(
          err instanceof Error ? err.message : "Failed to load metric drill-down.",
        );
      } finally {
        setDrilldownLoading(false);
      }
    },
    [unitId],
  );

  return {
    unitId,
    metricsByName,
    status,
    loadError,
    metricsUnavailableReason: METRICS_UNAVAILABLE_REASON,
    drilldownOpen,
    setDrilldownOpen,
    drilldownLoading,
    drilldownError,
    drilldown,
    openDrilldown,
  };
}
