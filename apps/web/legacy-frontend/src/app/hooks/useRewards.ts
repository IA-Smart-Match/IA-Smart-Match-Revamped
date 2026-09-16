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
 * ## The unit this reads, and why it is a parameter
 *
 * `unitId` is an argument — `PortalDescriptor.default_unit_id` out of
 * `GET /v1/me/portals`, passed in by the page that holds the grant — for
 * {@link useOutreach}'s reasons, and for one extra that is specific to this
 * hook. It used to call `getConfiguredUnitId()`, the `VITE_SMARTMATCH_UNIT_ID`
 * build variable, which is unset on the classroom VM and so put the whole
 * rewards page into `"unavailable"` without asking the server for a catalog
 * that exists.
 *
 * The extra reason not to call `usePortalAccess()` in here instead: this hook's
 * caller is `StudentRewards`, inside the **student** portal, while
 * {@link useOutreach}'s caller is inside the coordinator one. A `PortalKind`
 * resolved inside the hook would have to be one of them, and would be the wrong
 * constant for the other — trading the build-variable coupling for a
 * portal-kind coupling rather than removing it. The page knows which portal it
 * is; the hook does not need to.
 *
 * `unitId === null` is `"idle"` — one of the four states already named above —
 * with no `loadError`. It is not `"unavailable"`: no unit means nothing was
 * asked for, which is not the same as something having failed. Whether the null
 * is "still resolving" or "the grant carries no unit" is the caller's fact; see
 * {@link REWARDS_NO_UNIT_REASON}.
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
import { useCallback, useState } from "react";

import {
  fetchOwnRedemptions,
  fetchRewardCatalog,
  hasSmartmatchAuth,
  requestRedemption,
  type Redemption,
  type RewardCatalogResponse,
} from "../../lib/api";
import { useScopedQuery } from "./useScopedQuery";

export type RewardsStatus = "idle" | "loading" | "ready" | "unavailable";

/**
 * Why the catalog could not be read at all: no API credential in this browser.
 *
 * The build-variable half of the sentence this replaced is gone. A student
 * cannot set `VITE_SMARTMATCH_UNIT_ID` and cannot rebuild the bundle, so naming
 * it told them nothing they could use; signing in again is something they can
 * do. `hasSmartmatchAuth()` is satisfied by the session token `LoginPage`
 * stores, so a signed-in student does not see this.
 */
export const REWARDS_UNAVAILABLE_REASON =
  "The rewards catalog could not be read: this browser is not holding a credential for the API. Sign in again.";

/**
 * Why there is no catalog even though everything is working: the portal the
 * server granted carries no unit.
 *
 * A rewards catalog is a unit's funded rows, so with no unit there is no
 * catalog to be empty *or* full — which is why this is its own sentence and not
 * an empty shelf. Rendering "no rewards" here would be exactly the ADR-0011
 * mistake this hook's docstring opens with, one level up.
 */
export const REWARDS_NO_UNIT_REASON =
  "The portal the server granted this account carries no unit, so there is no rewards catalog to read. Ask your program administrator to attach a unit to your membership.";

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
/**
 * @param unitId The unit the server granted this account
 *   (`grantedPortal(...)?.default_unit_id ?? null`), or `null` while the
 *   mapping is unresolved or the grant carries none. Never a browser-composed
 *   identifier and never a build variable — see the module docstring.
 */
export function useRewards(unitId: string | null): UseRewardsResult {
  const authConfigured = hasSmartmatchAuth();
  // No unit is not a failure, so it does not start in `"unavailable"`.
  const unresolved = unitId === null;
  const enabled = !unresolved && authConfigured;

  const [pendingItemIds, setPendingItemIds] = useState<Set<string>>(() => new Set());
  const [requestError, setRequestError] = useState<string | null>(null);

  // The catalog read is the same slot `useStudentPortalData` fills for the
  // student home page — a student who opened Home first finds this already
  // warm. The pair still fails together (`Promise.all`'s rule, kept): either
  // read's refusal marks the hook "unavailable" rather than showing half a
  // wallet.
  const catalogQuery = useScopedQuery({
    resource: "reward-catalog",
    params: [unitId],
    queryFn: () => fetchRewardCatalog(unitId as string),
    enabled,
  });
  const redemptionsQuery = useScopedQuery({
    resource: "own-redemptions",
    params: [unitId],
    queryFn: () => fetchOwnRedemptions(unitId as string),
    enabled,
  });

  const failedQuery = catalogQuery.isError
    ? catalogQuery
    : redemptionsQuery.isError
      ? redemptionsQuery
      : null;

  const status: RewardsStatus = unresolved
    ? "idle"
    : !enabled
      ? "unavailable"
      : catalogQuery.isPending || redemptionsQuery.isPending
        ? "loading"
        : failedQuery !== null
          ? "unavailable"
          : "ready";
  // `.data ?? …`, not an `isSuccess` gate: a failed *re*fetch keeps the last
  // good answer in `data`, and the rule is that a failed read leaves the
  // catalog as it was rather than clearing it to an empty shelf.
  const catalog = catalogQuery.data ?? null;
  const redemptions: Redemption[] = redemptionsQuery.data?.redemptions ?? [];
  const loadError = unresolved
    ? null
    : !enabled
      ? REWARDS_UNAVAILABLE_REASON
      : failedQuery !== null
        ? failedQuery.error instanceof Error
          ? failedQuery.error.message
          : "Failed to load rewards."
        : null;

  const requestItem = useCallback(
    async (itemId: string) => {
      if (!unitId) return;
      setRequestError(null);
      setPendingItemIds((previous) => new Set([...previous, itemId]));
      try {
        await requestRedemption(unitId, itemId);
        await Promise.all([catalogQuery.refetch(), redemptionsQuery.refetch()]);
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
    [unitId, catalogQuery, redemptionsQuery],
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
