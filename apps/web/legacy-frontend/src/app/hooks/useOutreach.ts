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
 * ## No polling
 *
 * `refreshSend` is called by the page, not by a timer. A send that has been
 * submitted is followed by reading it, and a coordinator who wants to know now
 * asks now. An automatic poll would be a nicety this hook cannot honestly
 * provide anyway — the send id does not exist until the worker has run, so
 * there is nothing to poll until there is something to report.
 */
import { useCallback, useEffect, useState } from "react";

import {
  createOutreachDraft,
  fetchOutreachDrafts,
  fetchOutreachSend,
  getConfiguredUnitId,
  hasSmartmatchAuth,
  submitOutreachSend,
  type OutreachDraft,
  type OutreachSend,
} from "../../lib/api";

export type OutreachStatus = "idle" | "loading" | "ready" | "unavailable";

/** How far a submitted send has got, as the browser is entitled to say. */
export type SendState = "idle" | "submitting" | "queued" | "failed";

export const OUTREACH_UNAVAILABLE_REASON =
  "Outreach requires VITE_SMARTMATCH_UNIT_ID and a bearer token (VITE_SMARTMATCH_BEARER_TOKEN or session storage).";

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

export function useOutreach(): UseOutreachResult {
  const unitId = getConfiguredUnitId();
  const enabled = Boolean(unitId) && hasSmartmatchAuth();

  const [status, setStatus] = useState<OutreachStatus>(enabled ? "loading" : "unavailable");
  const [drafts, setDrafts] = useState<OutreachDraft[]>([]);
  const [loadError, setLoadError] = useState<string | null>(
    enabled ? null : OUTREACH_UNAVAILABLE_REASON,
  );
  const [sendState, setSendState] = useState<SendState>("idle");
  const [sendError, setSendError] = useState<string | null>(null);
  const [queued, setQueued] = useState<QueuedSend | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!enabled || !unitId) {
      setStatus("unavailable");
      setLoadError(OUTREACH_UNAVAILABLE_REASON);
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setLoadError(null);

    fetchOutreachDrafts(unitId)
      .then((response) => {
        if (cancelled) return;
        setDrafts(response.drafts);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // The list is left empty rather than populated with anything. A failed
        // read renders as "unavailable", never as "no drafts" — an empty list
        // is a claim, and this is not in a position to make it.
        setDrafts([]);
        setLoadError(describeError(error));
        setStatus("unavailable");
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, unitId, reloadToken]);

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
        setReloadToken((token) => token + 1);
      } catch (error: unknown) {
        setSendError(describeError(error));
        throw error;
      }
    },
    [unitId],
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
