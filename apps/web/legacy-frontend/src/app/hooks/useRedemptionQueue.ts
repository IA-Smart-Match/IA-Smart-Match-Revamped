/**
 * The coordinator's redemption queue: one status at a time, and a decision
 * that re-reads rather than splices.
 *
 * The shape follows `CoordinatorReviewQueue`: the list is a principal-scoped
 * `useScopedQuery` keyed on `[unitId, status]`, so each tab is its own cache
 * slot; a decision is a plain mutation call with a `busyId` held here; and
 * after a decision — success or failure — the list is **re-read**. The server
 * is the thing that knows what happened to a ticket, and removing a row
 * locally would be this hook inventing a result it was not told (ADR-0011
 * rule 3: one owning query).
 *
 * `unitId` is a parameter, for the reason `useRewards` gives: the page holds
 * the grant and knows which portal it is in; the hook does not need to.
 *
 * Nothing here filters, sorts or counts. `redemptions` is rendered as
 * received (oldest first, as the server orders it), `truncated` is read off
 * the response and never inferred from length, and the only number a page may
 * show is `redemptions.length` of a **loaded** response — while the read is
 * pending there is no count, and the page renders none.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import {
  ApiRequestError,
  decideRedemption,
  fetchRedemptionQueue,
  type RedemptionDecision,
  type RedemptionQueueItem,
  type RedemptionQueueStatus,
} from "../../lib/api";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import { scopedQueryKey } from "@/lib/queryClient";

import { useScopedQuery } from "./useScopedQuery";

/** What the last decision left behind, as a sentence the page announces. */
export type DecisionOutcome =
  | { readonly kind: "decided"; readonly sentence: string }
  | { readonly kind: "conflict"; readonly sentence: string }
  | { readonly kind: "refused"; readonly sentence: string };

/** One sentence per read failure, in the server's words wherever it gave any. */
export type QueueLoadFailure =
  /** A 4xx: the server's considered answer. Repeating the read cannot change it. */
  | { readonly kind: "refused"; readonly sentence: string }
  | { readonly kind: "rate_limited"; readonly sentence: string }
  /** A 5xx: the server's fault, and the one refusal a retry may honestly undo. */
  | { readonly kind: "server_error"; readonly sentence: string }
  | { readonly kind: "unreachable"; readonly sentence: string };

export interface RedemptionQueueState {
  readonly status: RedemptionQueueStatus;
  readonly setStatus: (status: RedemptionQueueStatus) => void;
  /** `null` until the current status has loaded. Not `[]`: unknown is not empty. */
  readonly redemptions: readonly RedemptionQueueItem[] | null;
  readonly truncated: boolean;
  readonly loading: boolean;
  readonly loadFailure: QueueLoadFailure | null;
  readonly reload: () => Promise<void>;
  /** The ticket whose decision is in flight, or `null`. */
  readonly busyId: string | null;
  readonly outcome: DecisionOutcome | null;
  readonly decide: (item: RedemptionQueueItem, decision: RedemptionDecision) => Promise<void>;
}

const PAST_TENSE: Readonly<Record<RedemptionDecision, string>> = {
  approved: "approved",
  fulfilled: "marked fulfilled",
  denied: "denied",
};

function describeLoadFailure(cause: unknown): QueueLoadFailure {
  if (cause instanceof ApiRequestError) {
    if (cause.status === 429) {
      return {
        kind: "rate_limited",
        sentence: `${cause.message} The queue is unchanged; try again after that.`,
      };
    }
    if (cause.status >= 500) {
      return {
        kind: "server_error",
        sentence:
          "The server could not answer for the redemption queue. Nothing was changed; try again.",
      };
    }
    return { kind: "refused", sentence: cause.message };
  }
  return {
    kind: "unreachable",
    sentence:
      "The redemption queue could not be loaded and the server gave no reason. " +
      "Check your connection and try again.",
  };
}

function describeDecisionFailure(cause: unknown, item: RedemptionQueueItem): DecisionOutcome {
  if (cause instanceof ApiRequestError && cause.status === 409) {
    return {
      kind: "conflict",
      sentence:
        `Someone already decided this ticket, or it can no longer make that move: ` +
        `${cause.message} The queue has been re-read.`,
    };
  }
  return {
    kind: "refused",
    sentence:
      cause instanceof ApiRequestError
        ? cause.message
        : `The decision on ${item.item_name} could not be recorded and the server gave no reason.`,
  };
}

export function useRedemptionQueue(unitId: string | null): RedemptionQueueState {
  const [status, setStatusState] = useState<RedemptionQueueStatus>("requested");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<DecisionOutcome | null>(null);
  // Set synchronously on entry, so a second press that lands before React
  // has re-rendered the buttons `disabled` is refused here, not posted.
  const inFlightRef = useRef(false);

  const listQuery = useScopedQuery({
    resource: "redemption-queue",
    params: [unitId, status],
    queryFn: () => fetchRedemptionQueue(unitId as string, status),
    enabled: unitId !== null,
  });

  // A failed or pending read shows no rows rather than another tab's rows
  // under this tab's heading, and `null` rather than `[]` so the page cannot
  // mistake "not loaded" for "nothing here".
  const redemptions = listQuery.isSuccess ? listQuery.data.redemptions : null;
  const truncated = listQuery.isSuccess ? listQuery.data.truncated : false;
  const loadFailure = listQuery.isError ? describeLoadFailure(listQuery.error) : null;

  // Depend on `refetch`, which TanStack keeps stable, not on the result
  // object, which is new every render and would re-render every row.
  const refetch = listQuery.refetch;
  const reload = useCallback(async () => {
    await refetch();
  }, [refetch]);

  // A decision moves a ticket between tabs, so every tab's cached read for
  // this unit is now wrong, not only the one on screen. Invalidating the
  // unit's prefix refetches the active tab and marks the rest stale.
  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();
  const invalidateUnit = useCallback(async () => {
    if (principalKey === null) {
      await refetch();
      return;
    }
    await queryClient.invalidateQueries({
      queryKey: scopedQueryKey(principalKey, "redemption-queue", unitId),
    });
  }, [principalKey, queryClient, refetch, unitId]);

  const setStatus = useCallback((next: RedemptionQueueStatus) => {
    setStatusState(next);
    // An outcome belongs to the tab it happened on; carrying it across would
    // announce a decision beside rows it never touched.
    setOutcome(null);
  }, []);

  const decide = useCallback(
    async (item: RedemptionQueueItem, decision: RedemptionDecision) => {
      // Unreachable while `redemptions` is null (no unit means no rows to
      // decide), but the guard is what keeps `/v1/units/null/...` impossible.
      if (unitId === null || inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      setBusyId(item.redemption_id);
      setOutcome(null);
      try {
        await decideRedemption(unitId, item.redemption_id, decision);
        setOutcome({
          kind: "decided",
          sentence: `${item.item_name} ${PAST_TENSE[decision]}.`,
        });
      } catch (cause) {
        setOutcome(describeDecisionFailure(cause, item));
      } finally {
        // Re-read either way: on success the row has left this status; on a
        // 409 it already had, and the screen must stop showing it.
        await invalidateUnit();
        inFlightRef.current = false;
        setBusyId(null);
      }
    },
    [invalidateUnit, unitId],
  );

  return {
    status,
    setStatus,
    redemptions,
    truncated,
    loading: listQuery.isPending,
    loadFailure,
    reload,
    busyId,
    outcome,
    decide,
  };
}
