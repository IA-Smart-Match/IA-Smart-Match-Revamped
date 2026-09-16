/**
 * The coordinator's outreach drafts, and the command that sends one.
 *
 * This hook is what closes `docs/plans/frontend-broken-buttons.md` B17. The
 * legacy Send button called `console.log("Message sent:")`, rendered
 * "Message sent!" for two seconds, and closed the dialog — having issued no
 * request. What replaces it is not "the same button with a fetch in it": the
 * difference that matters is that this hook has **no state that means success**.
 *
 * ## Four states, and none of them is "sent"
 *
 * `sendState` is `"idle" | "submitting" | "queued" | "failed"`, and `"queued"`
 * is as far as it goes. A queued send is a command the server has recorded and
 * the dispatcher has not moved; saying anything stronger would be inventing an
 * outcome the browser cannot know. The actual outcome arrives from
 * {@link refreshSend}, which reads the send back and reports the server's own
 * `disposition` — `null` while in flight, then `"accepted"`, `"blocked"`, or
 * `"failed"`.
 *
 * Even `"accepted"` is rendered as "the provider took custody", not as
 * "delivered". Delivery is a later event in the stream and may never arrive.
 *
 * ## Why `null` is carried rather than defaulted
 *
 * `disposition: null` is a third state, not a missing value, and this hook
 * passes it through untouched. Collapsing it to `"pending"` in the browser
 * would be the same class of defect as ADR-0011's "unknown is never zero": a
 * consumer that cannot tell "we have not heard" from "we heard nothing
 * happened" will eventually render one as the other.
 *
 * ## The unit this reads, and why it is a parameter
 *
 * `unitId` is an argument, not a lookup. It is the unit the **server** granted
 * the account — `PortalDescriptor.default_unit_id` out of `GET /v1/me/portals`
 * — and the caller passes it because the caller is what holds the grant.
 *
 * This hook used to call `getConfiguredUnitId()` and scope itself by the
 * `VITE_SMARTMATCH_UNIT_ID` build variable. That is the defect this parameter
 * closes. On a deployment where the variable is unset — the classroom VM, where
 * the bundle is built without it — the hook short-circuited to `"unavailable"`
 * before issuing a single request, so a coordinator whose unit held drafts was
 * told outreach was unavailable. Where the variable *is* set it is worse than
 * useless on a multi-unit pilot: it would show one unit's drafts under another
 * unit's name. `CoordinatorEvents.tsx` states the rule this now follows.
 *
 * Taking the unit as an argument rather than calling `usePortalAccess()` here
 * is deliberate. Which portal a unit is granted through is a fact about the
 * *page*: this hook's caller sits in the coordinator portal and
 * {@link useRewards}' caller sits in the student one, so a `PortalKind` baked
 * in here would only be a second wrong constant in place of the first. It also
 * keeps this hook outside `PortalAccessProvider`'s context, which
 * `usePortalAccess()` throws without.
 *
 * ## `"idle"` is not `"unavailable"`
 *
 * `unitId === null` puts this hook in `"idle"` with no `loadError`. With no
 * unit there is nothing to ask for, and nothing to report either. Whether that
 * null means "the portal mapping is still in flight" or "the grant carries no
 * unit" is a fact the caller holds and this hook does not, so the caller is the
 * one that says which — see {@link OUTREACH_NO_UNIT_REASON}.
 *
 * ## No polling
 *
 * `refreshSend` is called by the page, not by a timer. A send that has been
 * submitted is followed by reading it, and a coordinator who wants to know now
 * asks now. An automatic poll would be a nicety this hook cannot honestly
 * provide anyway — the send id does not exist until the worker has run, so
 * there is nothing to poll until there is something to report.
 */
import { useCallback, useState } from "react";

import {
  createOutreachDraft,
  fetchOutreachDrafts,
  fetchOutreachSend,
  hasSmartmatchAuth,
  submitOutreachSend,
  type OutreachDraft,
  type OutreachSend,
} from "../../lib/api";
import { useScopedQuery } from "./useScopedQuery";

export type OutreachStatus = "idle" | "loading" | "ready" | "unavailable";

/** How far a submitted send has got, as the browser is entitled to say. */
export type SendState = "idle" | "submitting" | "queued" | "failed";

/**
 * Why outreach could not be read at all: this browser holds no API credential.
 *
 * The only remaining half of the old two-part condition. It names a state a
 * reader can act on — sign in again — rather than the build variable the copy
 * this replaced named, which a coordinator cannot set and cannot rebuild a
 * bundle around. `hasSmartmatchAuth()` is satisfied by the session token
 * `LoginPage` stores, so a signed-in coordinator does not see this.
 */
export const OUTREACH_UNAVAILABLE_REASON =
  "Outreach could not be read: this browser is not holding a credential for the API. Sign in again.";

/**
 * Why there is nothing to read even though everything is working.
 *
 * Distinct from {@link OUTREACH_UNAVAILABLE_REASON}, which is a credential
 * failure, and distinct again from the caller rendering nothing while
 * `GET /v1/me/portals` is still in flight. This is the resolved, honest,
 * act-on-able case: the server answered, and the portal it granted carries no
 * unit. Exported so the drafts section and the sends listing say it in the same
 * words rather than two slightly different ones.
 */
export const OUTREACH_NO_UNIT_REASON =
  "The portal the server granted this account carries no unit, so there are no outreach drafts to read. Ask your program administrator to attach a unit to your membership.";

export interface QueuedSend {
  draftId: string;
  jobId: string;
  eventsUrl: string;
  /**
   * The server's own outcome once it has one, or `null` while the command has
   * not been executed. Never defaulted — see the module docstring.
   */
  send: OutreachSend | null;
}

export interface UseOutreachResult {
  unitId: string | null;
  status: OutreachStatus;
  drafts: OutreachDraft[];
  loadError: string | null;
  sendState: SendState;
  sendError: string | null;
  queued: QueuedSend | null;
  composeDraft: (input: {
    contactChannelId: string;
    templateId: string;
    values: Record<string, string>;
    approve: boolean;
  }) => Promise<void>;
  sendDraft: (draftId: string) => Promise<void>;
  refreshSend: (sendId: string) => Promise<void>;
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

/**
 * @param unitId The unit the server granted this account
 *   (`grantedPortal(...)?.default_unit_id ?? null`), or `null` while the
 *   mapping is unresolved or the grant carries none. Never a browser-composed
 *   identifier and never a build variable — see the module docstring.
 */
export function useOutreach(unitId: string | null): UseOutreachResult {
  // No unit is not a failure, so it does not start in `"unavailable"`.
  const unresolved = unitId === null;
  const enabled = !unresolved && hasSmartmatchAuth();

  const [sendState, setSendState] = useState<SendState>("idle");
  const [sendError, setSendError] = useState<string | null>(null);
  const [queued, setQueued] = useState<QueuedSend | null>(null);

  // The drafts listing through the shared cache — the same slot
  // `CoordinatorHome`'s drafts read uses, so the dashboard's count is this
  // page's warm-up. A failed read renders as "unavailable", never as "no
  // drafts" — an empty list is a claim, and a failed read is not in a
  // position to make it.
  const draftsQuery = useScopedQuery({
    resource: "outreach-drafts",
    params: [unitId],
    // The slot holds the drafts array itself — the same shape
    // `CoordinatorHome` caches under this key, so the two readers share one
    // entry rather than colliding on it.
    queryFn: async () => (await fetchOutreachDrafts(unitId as string)).drafts,
    enabled,
  });

  const status: OutreachStatus = unresolved
    ? "idle"
    : !enabled
      ? "unavailable"
      : draftsQuery.isPending
        ? "loading"
        : draftsQuery.isError
          ? "unavailable"
          : "ready";
  const drafts: OutreachDraft[] = draftsQuery.isSuccess ? draftsQuery.data : [];
  const loadError = unresolved
    ? null
    : !enabled
      ? OUTREACH_UNAVAILABLE_REASON
      : draftsQuery.isError
        ? describeError(draftsQuery.error)
        : null;

  const composeDraft = useCallback(
    async (input: {
      contactChannelId: string;
      templateId: string;
      values: Record<string, string>;
      approve: boolean;
    }) => {
      if (!unitId) return;
      setSendError(null);
      try {
        await createOutreachDraft(unitId, input);
        // Re-read rather than appending the response optimistically. The server
        // decides what a draft is, and a list patched locally would drift from
        // it the first time it decided something we did not predict.
        await draftsQuery.refetch();
      } catch (error: unknown) {
        setSendError(describeError(error));
        throw error;
      }
    },
    [unitId, draftsQuery],
  );

  const sendDraft = useCallback(
    async (draftId: string) => {
      if (!unitId) return;
      setSendState("submitting");
      setSendError(null);
      setQueued(null);
      try {
        const accepted = await submitOutreachSend(unitId, draftId);
        // `"queued"`, and no further. The server answered 202; the dispatcher
        // has not moved the command and no message exists.
        setQueued({
          draftId,
          jobId: accepted.job_id,
          eventsUrl: accepted.events_url,
          send: null,
        });
        setSendState("queued");
      } catch (error: unknown) {
        setSendState("failed");
        setSendError(describeError(error));
      }
    },
    [unitId],
  );

  const refreshSend = useCallback(
    async (sendId: string) => {
      if (!unitId) return;
      try {
        const send = await fetchOutreachSend(unitId, sendId);
        setQueued((current) => (current === null ? current : { ...current, send }));
      } catch (error: unknown) {
        // Deliberately does not clear `queued`. A read that failed says nothing
        // about the send, and dropping the job id would leave a coordinator
        // with no way to ask again about a command that may well have
        // succeeded.
        setSendError(describeError(error));
      }
    },
    [unitId],
  );

  return {
    unitId,
    status,
    drafts,
    loadError,
    sendState,
    sendError,
    queued,
    composeDraft,
    sendDraft,
    refreshSend,
  };
}
