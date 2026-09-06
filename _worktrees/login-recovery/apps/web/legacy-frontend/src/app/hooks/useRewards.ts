/**
 * The server rewards catalog, the server balance, and the caller's own tickets.
 *
 * This hook is what replaced `lib/studentPoints.ts` and
 * `lib/studentRewardsCatalog.ts`, both deleted in the commit that added it. The
 * difference is not where the code lives: those two files *computed* a balance
 * (`attendance_streak * 100 + events_attended * 25`) and *held* a catalog (seven
 * hard-coded items priced 2,500-45,000 against a 25-point event, the documented
 * defect Fix #15 named). Nothing here computes or holds either. Every number
 * below arrives from `GET /v1/units/{unit_id}/rewards`, where the balance is a
 * fold over `point_ledger_entry` and the catalog is the rows whose budget owner
 * and funded balance the database could actually confirm.
 *
 * ## Four states, and none of them is zero
 *
 * `status` is `"idle" | "loading" | "ready" | "unavailable"`, the same machine
 * `useUnitMetrics` uses, and no consumer may render a points figure outside the
 * `"ready"` branch. Even inside it, `catalog.balance.state` may be `"unknown"`,
 * in which case `catalog.balance.points` is `null` and stays `null`: ADR-0011,
 * and the specific defect the deleted call sites had, where an unloaded profile
 * rendered as "0 points".
 *
 * ## No filtering happens here
 *
 * `catalog.items` is rendered as received. The unfunded and unowned items were
 * never selected by the server's query, so there is no client-side predicate
 * that could accidentally be relaxed into showing one. This hook deliberately
 * exposes no `filter`, no sort, and no category grouping — the server orders by
 * cost, and re-ordering in the browser would be the first step back toward a
 * catalog the browser owns.
 */
import { useCallback, useEffect, useState } from "react";

import {
  fetchOwnRedemptions,
  fetchRewardCatalog,
  getConfiguredUnitId,
  hasSmartmatchAuth,
  requestRedemption,
  type Redemption,
  type RewardCatalogResponse,
} from "../../lib/api";

export type RewardsStatus = "idle" | "loading" | "ready" | "unavailable";

export const REWARDS_UNAVAILABLE_REASON =
  "The rewards catalog requires VITE_SMARTMATCH_UNIT_ID and a bearer token (VITE_SMARTMATCH_BEARER_TOKEN or session storage).";

export interface UseRewardsResult {
  unitId: string | null;
  status: RewardsStatus;
  catalog: RewardCatalogResponse | null;
  redemptions: Redemption[];
  loadError: string | null;
  /** Item ids with a request in flight, so a button can disable itself without lying. */
  pendingItemIds: ReadonlySet<string>;
  requestError: string | null;
  requestItem: (itemId: string) => Promise<void>;
}

/**
 * Load the catalog and the caller's tickets, and expose the redemption command.
 *
 * `requestItem` re-reads both after a successful request rather than patching
 * local state with an optimistic guess. The server decides what a redemption is
 * — including handing back an *existing* in-flight ticket for a second request
 * on the same item — so guessing would sometimes render a ticket that does not
 * exist, and the balance behind it is only correct after a real read anyway.
 */
export function useRewards(): UseRewardsResult {
  const unitId = getConfiguredUnitId();
  const authConfigured = hasSmartmatchAuth();
  const enabled = Boolean(unitId) && authConfigured;

  const [status, setStatus] = useState<RewardsStatus>(enabled ? "loading" : "unavailable");
  const [catalog, setCatalog] = useState<RewardCatalogResponse | null>(null);
  const [redemptions, setRedemptions] = useState<Redemption[]>([]);
  const [loadError, setLoadError] = useState<string | null>(
    enabled ? null : REWARDS_UNAVAILABLE_REASON,
  );
  const [pendingItemIds, setPendingItemIds] = useState<Set<string>>(() => new Set());
  const [requestError, setRequestError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!enabled || !unitId) {
      setStatus("unavailable");
      setLoadError(REWARDS_UNAVAILABLE_REASON);
      return;
    }

    let mounted = true;
    setStatus("loading");
    setLoadError(null);

    async function load(id: string) {
      try {
        const [nextCatalog, tickets] = await Promise.all([
          fetchRewardCatalog(id),
          fetchOwnRedemptions(id),
        ]);
        if (!mounted) return;
        setCatalog(nextCatalog);
        setRedemptions(tickets.redemptions);
        setStatus("ready");
      } catch (error) {
        if (!mounted) return;
        // The catalog is left as it was rather than cleared to an empty list: an
        // empty catalog is a claim ("nothing is funded") and a failed read is
        // not, so `status` carries the failure and the consumer renders that
        // instead of an emptied shelf.
        setStatus("unavailable");
        setLoadError(error instanceof Error ? error.message : "Failed to load rewards.");
      }
    }

    void load(unitId);
    return () => {
      mounted = false;
    };
  }, [enabled, unitId, reloadToken]);

  const requestItem = useCallback(
    async (itemId: string) => {
      if (!unitId) return;
      setRequestError(null);
      setPendingItemIds((previous) => new Set([...previous, itemId]));
      try {
        await requestRedemption(unitId, itemId);
        setReloadToken((token) => token + 1);
      } catch (error) {
        setRequestError(
          error instanceof Error ? error.message : "Could not request that redemption.",
        );
      } finally {
        setPendingItemIds((previous) => {
          const next = new Set(previous);
          next.delete(itemId);
          return next;
        });
      }
    },
    [unitId],
  );

  return {
    unitId,
    status,
    catalog,
    redemptions,
    loadError,
    pendingItemIds,
    requestError,
    requestItem,
  };
}
