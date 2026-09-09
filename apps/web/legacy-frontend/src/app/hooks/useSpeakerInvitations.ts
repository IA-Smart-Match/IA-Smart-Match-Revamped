/**
 * A Speaker Connector's invitation batches, and the two facts about each one.
 *
 * The sibling of {@link useOutreach}, and it keeps that hook's central rule:
 * **there is no state here that means "sent"**, and none that means "the Speaker
 * agreed". Both of those are server reads, and the browser's job is to show them
 * without folding them together.
 *
 * ## Why this hook holds no derived status
 *
 * The tempting shape is a `status` per invitation that a table can colour: sent,
 * delivered, accepted, declined. It is exactly the shape this card exists to
 * refuse, because two of those words belong to a mail provider and two belong to
 * a person, and one of them — "accepted" — is claimed by both.
 *
 * So every outcome keeps the server's own two objects side by side. `delivery`
 * answers "what happened to the message"; `speaker_response` answers "what did
 * the human say". A component renders both or renders one; it never computes one
 * from the other, and there is no field in this module that would let it.
 *
 * ## Three nulls, and none of them is a failure
 *
 * * `delivery === null` — no send has been submitted for this invitation.
 * * `delivery.disposition === null` — a send was submitted and is in flight.
 * * `speaker_response.recorded_at === null` — nobody has answered yet, which is
 *   the ordinary condition of an invitation for as long as it takes somebody to
 *   read their mail.
 *
 * All three are passed through untouched, for {@link useOutreach}'s reason: a
 * consumer that cannot tell "we have not heard" from "we heard nothing happened"
 * will eventually render one as the other (ADR-0011).
 *
 * ## No polling
 *
 * `openBatchById` is called by the page, not by a timer — {@link useOutreach}'s
 * argument again. A Connector who wants to know now asks now, and a poll would
 * imply this surface knows when something changed, which it does not.
 */
import { useCallback, useEffect, useState } from "react";

import {
  dispatchSpeakerInvitationBatch,
  fetchSpeakerInvitationBatch,
  fetchSpeakerInvitationBatches,
  getConfiguredUnitId,
  hasSmartmatchAuth,
  recordSpeakerInvitationResponse,
  type SpeakerInvitationBatch,
  type SpeakerInvitationBatchSummary,
  type SpeakerInvitationDispatchResponse,
} from "../../lib/api";

export type InvitationsStatus = "idle" | "loading" | "ready" | "unavailable";

/** How far a dispatch has got, as the browser is entitled to say. */
export type DispatchState = "idle" | "submitting" | "submitted" | "failed";

export const INVITATIONS_UNAVAILABLE_REASON =
  "Speaker invitations require VITE_SMARTMATCH_UNIT_ID and a bearer token (VITE_SMARTMATCH_BEARER_TOKEN or session storage).";

export interface UseSpeakerInvitationsResult {
  unitId: string | null;
  status: InvitationsStatus;
  batches: SpeakerInvitationBatchSummary[];
  loadError: string | null;
  /** The batch a Connector opened, with every outcome in it, or `null`. */
  openBatch: SpeakerInvitationBatch | null;
  openBatchError: string | null;
  dispatchState: DispatchState;
  dispatchError: string | null;
  /**
   * What the last dispatch submitted and what it refused, or `null`.
   *
   * Kept rather than folded into the batch read, because `not_dispatched` is the
   * half a Connector has to act on and it exists only in this response: an
   * invitation refused at dispatch stays `pending`, so the batch read alone
   * cannot say that anybody tried.
   */
  lastDispatch: SpeakerInvitationDispatchResponse | null;
  openBatchById: (batchId: string) => Promise<void>;
  dispatchBatch: (batchId: string) => Promise<void>;
  recordResponse: (invitationId: string, response: "accept" | "decline") => Promise<void>;
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

export function useSpeakerInvitations(): UseSpeakerInvitationsResult {
  const unitId = getConfiguredUnitId();
  const enabled = Boolean(unitId) && hasSmartmatchAuth();

  const [status, setStatus] = useState<InvitationsStatus>(enabled ? "loading" : "unavailable");
  const [batches, setBatches] = useState<SpeakerInvitationBatchSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(
    enabled ? null : INVITATIONS_UNAVAILABLE_REASON,
  );
  const [openBatch, setOpenBatch] = useState<SpeakerInvitationBatch | null>(null);
  const [openBatchError, setOpenBatchError] = useState<string | null>(null);
  const [dispatchState, setDispatchState] = useState<DispatchState>("idle");
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [lastDispatch, setLastDispatch] = useState<SpeakerInvitationDispatchResponse | null>(null);

  useEffect(() => {
    if (!enabled || !unitId) {
      setStatus("unavailable");
      setLoadError(INVITATIONS_UNAVAILABLE_REASON);
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setLoadError(null);

    fetchSpeakerInvitationBatches(unitId)
      .then((response) => {
        if (cancelled) return;
        setBatches(response.batches);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // Left empty rather than populated with anything, and reported as
        // "unavailable" rather than as "no batches": an empty list is a claim,
        // and a read that failed is not in a position to make it.
        setBatches([]);
        setLoadError(describeError(error));
        setStatus("unavailable");
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, unitId]);

  const openBatchById = useCallback(
    async (batchId: string) => {
      if (!unitId) return;
      setOpenBatchError(null);
      try {
        setOpenBatch(await fetchSpeakerInvitationBatch(unitId, batchId));
      } catch (error: unknown) {
        // The previously open batch is deliberately not cleared. A failed read
        // says nothing about the batch, and blanking the screen would lose the
        // outcomes a Connector was reading.
        setOpenBatchError(describeError(error));
      }
    },
    [unitId],
  );

  const dispatchBatch = useCallback(
    async (batchId: string) => {
      if (!unitId) return;
      setDispatchState("submitting");
      setDispatchError(null);
      setLastDispatch(null);
      try {
        const result = await dispatchSpeakerInvitationBatch(unitId, batchId);
        setLastDispatch(result);
        // `"submitted"`, and no further. The server answered 202 for each
        // command it accepted; the dispatcher has not moved any of them and no
        // message exists.
        setDispatchState("submitted");
        // Re-read rather than patching the outcomes locally: which invitations
        // actually moved to `dispatched` is the server's answer, and a list
        // patched here would drift from it the first time it refused one.
        setOpenBatch(await fetchSpeakerInvitationBatch(unitId, batchId));
      } catch (error: unknown) {
        setDispatchState("failed");
        setDispatchError(describeError(error));
      }
    },
    [unitId],
  );

  const recordResponse = useCallback(
    async (invitationId: string, response: "accept" | "decline") => {
      if (!unitId || openBatch === null) return;
      try {
        await recordSpeakerInvitationResponse(unitId, invitationId, response);
        setOpenBatch(await fetchSpeakerInvitationBatch(unitId, openBatch.batch_id));
      } catch (error: unknown) {
        // Surfaced through the batch error rather than swallowed. A 409 here is
        // meaningful — the invitation already carries a different answer — and a
        // Connector needs to see it rather than watch a button do nothing.
        setOpenBatchError(describeError(error));
      }
    },
    [unitId, openBatch],
  );

  return {
    unitId,
    status,
    batches,
    loadError,
    openBatch,
    openBatchError,
    dispatchState,
    dispatchError,
    lastDispatch,
    openBatchById,
    dispatchBatch,
    recordResponse,
  };
}
