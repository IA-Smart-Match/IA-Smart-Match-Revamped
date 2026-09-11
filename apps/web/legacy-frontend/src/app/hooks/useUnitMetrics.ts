/**
 * Accountable-metrics data hook, backed by the shared TanStack Query cache
 * (plan P4, lane F1 -- see `src/lib/queryClient.ts` for the cache-key
 * scoping + identity-clear rules this hook relies on for correctness).
 *
 * ## The unit this reads, and why it is a parameter
 *
 * `unitId` is an argument, not a lookup. It is the unit the **server** granted
 * the account — `PortalDescriptor.default_unit_id` out of `GET /v1/me/portals`
 * — and the caller passes it because the caller is what holds the grant.
 *
 * This hook used to call `getConfiguredUnitId()` and scope itself by the
 * `VITE_SMARTMATCH_UNIT_ID` build variable. That is the defect this parameter
 * closes, and it is the same defect PR #139 closed in `useOutreach`,
 * `useSpeakerInvitations` and `useRewards`. On the deployed pilot VM the
 * bundle is built without that variable, so this hook short-circuited to
 * `"unavailable"` before issuing a single request and told the reader to set a
 * build variable — an instruction nobody holding a browser can act on. Where
 * the variable *is* set it is worse than useless on a multi-unit pilot: it
 * would render one unit's metrics under another unit's name.
 *
 * ## Why these surfaces are portal surfaces after all
 *
 * The four call sites — `Dashboard.tsx`, `Pipeline.tsx`, `Opportunities.tsx`
 * and `PipelineFunnelTiles.tsx` — sit under the pathless `Layout` route rather
 * than one of the three portal shells, so it is tempting to read them as
 * deployment-configured admin surfaces for which a build variable would be a
 * legitimate input. They are not. `GET /v1/me/portals` maps the stored `admin`
 * role to the portal `admin` with `home_path: "/dashboard"`
 * (`services/api/smartmatch_api/routers/portals.py`'s `_PORTAL_FOR_ROLE`), and
 * `PortalGate` links a signed-in account straight at it. `/dashboard` is that
 * portal's home screen, reachable by an ordinary signed-in pilot account, and
 * its unit is therefore the one the server granted that account — exactly as
 * for the other three portals. `PortalKind` has carried `"admin"` since the
 * mapping existed; nothing here is a new claim.
 *
 * Taking the unit as an argument rather than calling `usePortalAccess()` here
 * follows `useOutreach`'s reasoning and adds one of its own. All four callers
 * happen to resolve the *same* portal today, so a `PortalKind` baked in here
 * would not be wrong the way it would be for the shared hooks — but it would
 * be the second constant this hook resolves its unit from, and the first one
 * is what this change is removing. The caller holds the grant; the caller
 * passes the unit.
 *
 * ## Three distinct facts, and `"idle"` is not `"unavailable"`
 *
 * `unitId === null` puts this hook in `"idle"` with no `loadError`. With no
 * unit there is nothing to ask for, and nothing to report either. Whether that
 * null means "`GET /v1/me/portals` is still in flight" or "the grant carries
 * no unit" is a fact the caller holds and this hook does not, so the caller
 * says which — see {@link METRICS_UNIT_RESOLVING_REASON} and
 * {@link METRICS_NO_UNIT_REASON}. Loading, genuinely-unavailable, and
 * empty-but-working stay three separate statements, per ADR-0011 rule 1's
 * corollary that "we did not ask" is never "there is none".
 *
 * PUBLIC SHAPE CONTRACT: the object this hook returns -- every property name,
 * type, and observable state machine (`status`, `loadError`,
 * `metricsUnavailableReason`, the `drilldown*` family, `openDrilldown`) -- is
 * preserved, with `metricsNoUnitReason` added beside them. Only the
 * *arguments* grew: `unitId` is now the first parameter and `reloadToken` the
 * second. The earlier revision of this header promised `Dashboard.tsx` and
 * `PipelineFunnelTiles.tsx` would need no edit at all; that promise belonged
 * to the lane that moved this hook onto `useQuery`, and closing a wrong-unit
 * defect is not something a caller can be spared from — the caller is the only
 * thing that holds the grant.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  fetchMetricDrillDown,
  fetchUnitMetrics,
  hasSmartmatchAuth,
  type MetricDrillDownResponse,
  type MetricSummary,
} from "@/lib/api";
import { indexMetricsByName } from "@/lib/metrics";
import { drilldownQueryKey, metricsQueryKey } from "@/lib/queryClient";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";

export type UnitMetricsStatus = "idle" | "loading" | "ready" | "unavailable";

/**
 * Why the register could not be read at all: this browser holds no API
 * credential.
 *
 * The only remaining half of the old two-part condition. It names a state a
 * reader can act on — sign in again — rather than the build variable the copy
 * this replaces named. `hasSmartmatchAuth()` is satisfied by the session token
 * `LoginPage` stores, so a signed-in reader does not see this.
 */
export const METRICS_UNAVAILABLE_REASON =
  "Registered metrics could not be read: this browser is not holding a credential for the API. Sign in again.";

/**
 * Why there is nothing to read even though everything is working: the server
 * granted this account no unit to report on.
 *
 * Distinct from {@link METRICS_UNAVAILABLE_REASON}, which is a credential
 * failure, and distinct again from {@link METRICS_UNIT_RESOLVING_REASON},
 * which is a read still in flight. This is the resolved, honest, act-on-able
 * case, and it covers both shapes of it — the account holds no membership that
 * opens this surface, or the one it holds is granted over a path no `org_unit`
 * row occupies (`units_in_subtree` reports that emptiness rather than filling
 * it in). Deliberately names no portal: the role behind this surface is
 * presented as "Speaker Connector (administrator)", and a second name for it
 * here would be a third vocabulary for one grant.
 */
export const METRICS_NO_UNIT_REASON =
  "The server granted this account no unit to report on, so there are no registered metrics to read. Ask your program administrator to grant a membership over a unit.";

/**
 * Why nothing is on screen yet, when the unit itself is still being resolved.
 *
 * `grantedPortal()` returns `null` both while `GET /v1/me/portals` is in
 * flight and when the answer came back without a grant, so a caller that
 * rendered {@link METRICS_NO_UNIT_REASON} for every `null` would tell a reader
 * their membership is missing during the second it takes to find out that it
 * is not. Exported so all four surfaces say this in the same words.
 */
export const METRICS_UNIT_RESOLVING_REASON =
  "Checking which unit the server granted this account…";

/**
 * Placeholder first key segment used only while the principal is still
 * resolving. The metrics query is `enabled: false` for the entire time this
 * placeholder would be part of the key, so it never populates the cache
 * under a fake identity -- see `PrincipalQueryProvider`'s "do not enable
 * principal-scoped queries until a key is known" rule.
 */
const UNRESOLVED_PRINCIPAL = "unresolved-principal";

/**
 * @param unitId The unit the server granted this account
 *   (`grantedPortal(...)?.default_unit_id ?? null`), or `null` while the
 *   mapping is still in flight or the grant carries no unit. Never a value the
 *   browser composed, and never a build variable.
 * @param reloadToken A caller-driven "reload now" counter; incrementing it
 *   refetches the existing cache entry.
 */
export function useUnitMetrics(unitId: string | null, reloadToken = 0) {
  const authConfigured = hasSmartmatchAuth();
  const principalKey = usePrincipalKey();

  const metricsEnabled = unitId !== null && authConfigured && principalKey !== null;

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

  if (unitId === null) {
    // Nothing was asked for, so nothing failed. `loadError` stays null: an
    // error string here would be this hook claiming a failure that did not
    // happen, and the caller would render it beside the honest states as
    // though it were one. Which flavour of "no unit" this is, the caller says.
    status = "idle";
  } else if (!authConfigured) {
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
      if (unitId === null || !authConfigured) {
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
    metricsNoUnitReason: METRICS_NO_UNIT_REASON,
    drilldownOpen,
    setDrilldownOpen,
    drilldownLoading,
    drilldownError,
    drilldown,
    openDrilldown,
  };
}
