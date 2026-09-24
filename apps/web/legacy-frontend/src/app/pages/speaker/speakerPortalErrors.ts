/**
 * The Speaker Portal's error map (B26 T6b-4 §7). Pure.
 *
 * Branches on `ApiRequestError.code`, then `status`, never on the message.
 * Every message is fixed text: DESIGN.md's "do not show raw server text", and
 * a Speaker is the last person who should read a server's internal wording.
 *
 * `refetch` says whether the page re-reads its own list after the failure.
 * Only the codes that mean "the list you are looking at is out of date" do; a
 * 403, 429 or network failure changes nothing the list would show.
 */
import { ApiRequestError } from "@/lib/api";

/** A page-load read, by the thing it reads. */
export type SpeakerReadContext =
  | "read-invitations"
  | "read-engagements"
  | "read-availability"
  | "read-addresses";

/** A write, by the page action. */
export type SpeakerWriteContext = "answer" | "availability" | "channel";

export type SpeakerPortalContext = SpeakerReadContext | SpeakerWriteContext;

export interface SpeakerPortalError {
  readonly message: string;
  readonly refetch: boolean;
}

/** The three failures that replace a whole page, whatever it reads. */
export type SelfNoticeKind = "not_linked" | "denied" | "signed_out";

export const NOT_LINKED_MESSAGE =
  "Your account is not linked to a Speaker profile, so there is nothing to show here. Ask your Speaker Connector to send you a new portal invitation.";
export const DENIED_MESSAGE =
  "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector.";
export const SIGNED_OUT_MESSAGE =
  "Your session has ended. Sign in again; nothing on this page was changed.";

const RATE_LIMITED_MESSAGE = "Too many requests just now. Wait a minute, then try again.";
const INVALID_REQUEST_MESSAGE = "The server could not read this request, so nothing was changed.";
const WRITE_FALLBACK_MESSAGE =
  "This could not be saved, and the server gave no reason. Nothing was changed. Try again.";

const READ_SUBJECT: Record<SpeakerReadContext, string> = {
  "read-invitations": "Your invitations",
  "read-engagements": "Your engagements",
  "read-availability": "Your availability",
  "read-addresses": "Your addresses",
};

/** Codes that mean the page's list is stale: say so and re-read it. */
const REFETCH_MESSAGES: Record<"answer" | "channel", Record<string, string>> = {
  answer: {
    speaker_invitation_not_found:
      "This invitation is no longer open to you. The list has been refreshed.",
    speaker_invitation_already_answered:
      "This invitation already has a different answer, and the first answer is final. To change it, contact your Speaker Connector.",
    speaker_invitation_response_conflict:
      "Your answer could not be recorded just now. The list has been refreshed; try again.",
  },
  channel: {
    speaker_contact_channel_not_found:
      "This address is no longer on your record. The list has been refreshed.",
    speaker_contact_channel_address_unverified:
      "This address was unsubscribed and is not the one you sign in with. Ask your Speaker Connector.",
    speaker_contact_channel_opt_in_unavailable:
      "This address has not been confirmed for invitations yet, so you cannot opt in here. Ask your Speaker Connector.",
    speaker_contact_channel_transition_conflict:
      "Something changed while you were opting in. The list has been refreshed; try again.",
  },
};

const NOT_LIFTABLE = "speaker_contact_channel_suppression_not_liftable";
const NOT_LIFTABLE_CONNECTOR =
  "Your Speaker Connector stopped messages to this address, so it cannot be turned back on here. Ask your Speaker Connector.";
const NOT_LIFTABLE_DELIVERY =
  "Messages to this address could not be delivered, so it cannot be turned back on. Ask your Speaker Connector to add a different address.";

function isRead(context: SpeakerPortalContext): context is SpeakerReadContext {
  return context.startsWith("read-");
}

function fallback(context: SpeakerPortalContext): SpeakerPortalError {
  return {
    message: isRead(context)
      ? `${READ_SUBJECT[context]} could not be loaded, and the server gave no reason. Try again.`
      : WRITE_FALLBACK_MESSAGE,
    refetch: false,
  };
}

/**
 * Which page-level notice a failed read stands for, or `null` when the page
 * shows its own read error with Retry. Not linked and denied get no Retry:
 * repeating the request cannot change the answer.
 */
export function selfNoticeKind(cause: unknown): SelfNoticeKind | null {
  if (!(cause instanceof ApiRequestError)) return null;
  if (cause.status === 404 && cause.code === "speaker_profile_not_linked") return "not_linked";
  if (cause.status === 403) return "denied";
  if (cause.status === 401) return "signed_out";
  return null;
}

/** The fixed words for a failure in `context`, and whether to re-read the list. */
export function speakerPortalError(
  context: SpeakerPortalContext,
  cause: unknown,
): SpeakerPortalError {
  if (!(cause instanceof ApiRequestError)) return fallback(context);

  if (context === "answer" || context === "channel") {
    const refetchMessage = REFETCH_MESSAGES[context][cause.code];
    if (refetchMessage !== undefined) return { message: refetchMessage, refetch: true };
    if (context === "channel" && cause.code === NOT_LIFTABLE) {
      const reason = cause.details?.reason;
      return {
        message: reason === "connector" ? NOT_LIFTABLE_CONNECTOR : NOT_LIFTABLE_DELIVERY,
        refetch: true,
      };
    }
  }

  switch (selfNoticeKind(cause)) {
    case "not_linked":
      return { message: NOT_LINKED_MESSAGE, refetch: false };
    case "denied":
      return { message: DENIED_MESSAGE, refetch: false };
    case "signed_out":
      return { message: SIGNED_OUT_MESSAGE, refetch: false };
    default:
      break;
  }
  if (cause.status === 429) return { message: RATE_LIMITED_MESSAGE, refetch: false };
  if (!isRead(context) && cause.status === 422 && cause.code === "invalid_request") {
    return { message: INVALID_REQUEST_MESSAGE, refetch: false };
  }
  return fallback(context);
}
