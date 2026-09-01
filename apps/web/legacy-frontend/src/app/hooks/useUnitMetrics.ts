/**
 * Accountable-metrics data hook, backed by the shared TanStack Query cache
 * (plan P4, lane F1 -- see `src/lib/queryClient.ts` for the cache-key
 * scoping + identity-clear rules this hook relies on for correctness).
 *
 * PUBLIC SHAPE CONTRACT: `Dashboard.tsx` and `PipelineFunnelTiles.tsx` are
 * owned by other lanes and must not need any edit. The object this hook
 * returns -- every property name, type, and observable state machine
 * (`status: "idle" | "loading" | "ready" | "unavailable"`, `loadError`,
 * `metricsUnavailableReason`, the `drilldown*` family, `openDrilldown`, and
 * the `reloadToken` parameter) -- is preserved exactly. Only the
 * *implementation* changed: data now flows through `useQuery` instead of a
 * hand-rolled `fetch` + `useEffect`, so repeat navigation within a session
 * can render from cache instead of refetch-blocking (R4).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  fetchMetricDrillDown,
  fetchUnitMetrics,
  getConfiguredUnitId,
  hasSmartmatchAuth,
  type MetricDrillDownResponse,
  type MetricSummary,
} from "@/lib/api";
import { indexMetricsByName } from "@/lib/metrics";
import { drilldownQueryKey, metricsQueryKey } from "@/lib/queryClient";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";

export type UnitMetricsStatus = "idle" | "loading" | "ready" | "unavailable";

const METRICS_UNAVAILABLE_REASON =
  "Registered metrics require VITE_SMARTMATCH_UNIT_ID and a bearer token (VITE_SMARTMATCH_BEARER_TOKEN or session storage).";

/**
 * Placeholder first key segment used only while the principal is still
 * resolving. The metrics query is `enabled: false` for the entire time this
 * placeholder would be part of the key, so it never populates the cache
 * under a fake identity -- see `PrincipalQueryProvider`'s "do not enable
 * principal-scoped queries until a key is known" rule.
 */
const UNRESOLVED_PRINCIPAL = "unresolved-principal";

export function useUnitMetrics(reloadToken = 0) {
  const unitId = getConfiguredUnitId();
  const authConfigured = hasSmartmatchAuth();
  const principalKey = usePrincipalKey();

  const metricsEnabled = Boolean(unitId) && authConfigured && principalKey !== null;

  const metricsQuery = useQuery({
    queryKey: metricsQueryKey(principalKey ?? UNRESOLVED_PRINCIPAL, unitId ?? "unscoped"),
    queryFn: () => fetchUnitMetrics(unitId as string),
    enabled: metricsEnabled,
  });

  // `reloadToken` is a caller-driven "reload now" signal (e.g. a manual
  // refresh button). It intentionally is NOT part of the cache key -- it
  // forces a refetch of the existing entry rather than minting a parallel
  // cache slot per reload count.
  const isFirstReloadRun = useRef(true);
  useEffect(() => {
    if (isFirstReloadRun.current) {
      isFirstReloadRun.current = false;
      return;
    }
    if (metricsEnabled) {
      void metricsQuery.refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadToken]);

  let status: UnitMetricsStatus;
  let metricsByName: Record<string, MetricSummary> = {};
  let loadError: string | null = null;

  if (!unitId || !authConfigured) {
    status = "unavailable";
    loadError = METRICS_UNAVAILABLE_REASON;
  } else if (!metricsEnabled || metricsQuery.isPending) {
    // Either the principal identity is still resolving (metricsEnabled is
    // false only in that case, since unitId/authConfigured were already
    // checked above), or the query itself has not settled yet. Both are the
    // same user-facing state as the original hook's "loading".
    status = "loading";
  } else if (metricsQuery.isError) {
    status = "unavailable";
    loadError =
      metricsQuery.error instanceof Error
        ? metricsQuery.error.message
        : "Failed to load accountable metrics.";
  } else {
    status = "ready";
    metricsByName = indexMetricsByName(metricsQuery.data.metrics);
  }

  const [drilldownOpen, setDrilldownOpen] = useState(false);
  const [activeDrilldownMetric, setActiveDrilldownMetric] = useState<string | null>(null);

  const drilldownEnabled =
    metricsEnabled && drilldownOpen && activeDrilldownMetric !== null;

  const drilldownQuery = useQuery({
    queryKey: drilldownQueryKey(
      principalKey ?? UNRESOLVED_PRINCIPAL,
      unitId ?? "unscoped",
      activeDrilldownMetric ?? "none",
    ),
    queryFn: () => fetchMetricDrillDown(unitId as string, activeDrilldownMetric as string),
    enabled: drilldownEnabled,
  });

  const openDrilldown = useCallback(
    (metricName: string) => {
      if (!unitId || !authConfigured) {
        return;
      }
      setDrilldownOpen(true);
      setActiveDrilldownMetric(metricName);
    },
    [unitId, authConfigured],
  );

  const drilldownLoading = drilldownEnabled && drilldownQuery.isPending;
  const drilldownError: string | null =
    drilldownEnabled && drilldownQuery.isError
      ? drilldownQuery.error instanceof Error
        ? drilldownQuery.error.message
        : "Failed to load metric drill-down."
      : null;
  const drilldown: MetricDrillDownResponse | null =
    drilldownEnabled && drilldownQuery.isSuccess ? drilldownQuery.data : null;

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
