/**
 * The Speaker portal's error map (T6b-4 §7): fixed text per context, status and
 * code, and whether the page's own list is re-read. Pure.
 */
import { describe, expect, it } from "vitest";

import { ApiRequestError } from "@/lib/api";

import {
  selfNoticeKind,
  speakerPortalError,
  type SpeakerPortalContext,
} from "./speakerPortalErrors";

const SENTINEL = "SERVER-SENTINEL-TEXT";

function failure(status: number, code: string, details?: Record<string, unknown>) {
  return new ApiRequestError(SENTINEL, status, code, details);
}

const NOT_LINKED =
  "Your account is not linked to a Speaker profile, so there is nothing to show here. Ask your Speaker Connector to send you a new portal invitation.";
const DENIED =
  "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector.";
const SIGNED_OUT = "Your session has ended. Sign in again; nothing on this page was changed.";
const RATE_LIMITED = "Too many requests just now. Wait a minute, then try again.";
const INVALID = "The server could not read this request, so nothing was changed.";
const WRITE_FALLBACK =
  "This could not be saved, and the server gave no reason. Nothing was changed. Try again.";

type Row = [string, SpeakerPortalContext, ApiRequestError, string, boolean];

const ROWS: Row[] = [
  ["any 404 not linked", "answer", failure(404, "speaker_profile_not_linked"), NOT_LINKED, false],
  ["any 403", "channel", failure(403, "forbidden", { reason: "no_grant" }), DENIED, false],
  ["any 401", "read-invitations", failure(401, "unauthenticated"), SIGNED_OUT, false],
  ["any 429", "answer", failure(429, "rate_limited"), RATE_LIMITED, false],
  ["write 422", "channel", failure(422, "invalid_request"), INVALID, false],
  [
    "read invitations other",
    "read-invitations",
    failure(500, "internal_error"),
    "Your invitations could not be loaded, and the server gave no reason. Try again.",
    false,
  ],
  [
    "read engagements other",
    "read-engagements",
    failure(503, "unknown_error"),
    "Your engagements could not be loaded, and the server gave no reason. Try again.",
    false,
  ],
  [
    "read availability other",
    "read-availability",
    failure(500, "internal_error"),
    "Your availability could not be loaded, and the server gave no reason. Try again.",
    false,
  ],
  [
    "read addresses other",
    "read-addresses",
    failure(500, "internal_error"),
    "Your addresses could not be loaded, and the server gave no reason. Try again.",
    false,
  ],
  ["write other", "answer", failure(500, "internal_error"), WRITE_FALLBACK, false],
  [
    "answer not found",
    "answer",
    failure(404, "speaker_invitation_not_found"),
    "This invitation is no longer open to you. The list has been refreshed.",
    true,
  ],
  [
    "answer already answered",
    "answer",
    failure(409, "speaker_invitation_already_answered"),
    "This invitation already has a different answer, and the first answer is final. To change it, contact your Speaker Connector.",
    true,
  ],
  [
    "answer response conflict",
    "answer",
    failure(409, "speaker_invitation_response_conflict"),
    "Your answer could not be recorded just now. The list has been refreshed; try again.",
    true,
  ],
  [
    "channel not found",
    "channel",
    failure(404, "speaker_contact_channel_not_found"),
    "This address is no longer on your record. The list has been refreshed.",
    true,
  ],
  [
    "channel not liftable (connector)",
    "channel",
    failure(409, "speaker_contact_channel_suppression_not_liftable", { reason: "connector" }),
    "Your Speaker Connector stopped messages to this address, so it cannot be turned back on here. Ask your Speaker Connector.",
    true,
  ],
  [
    "channel not liftable (delivery)",
    "channel",
    failure(409, "speaker_contact_channel_suppression_not_liftable", { reason: "delivery" }),
    "Messages to this address could not be delivered, so it cannot be turned back on. Ask your Speaker Connector to add a different address.",
    true,
  ],
  [
    "channel address unverified",
    "channel",
    failure(409, "speaker_contact_channel_address_unverified"),
    "This address was unsubscribed and is not the one you sign in with. Ask your Speaker Connector.",
    true,
  ],
  [
    "channel opt-in unavailable",
    "channel",
    failure(409, "speaker_contact_channel_opt_in_unavailable", { contact_state: "stale" }),
    "This address has not been confirmed for invitations yet, so you cannot opt in here. Ask your Speaker Connector.",
    true,
  ],
  [
    "channel transition conflict",
    "channel",
    failure(409, "speaker_contact_channel_transition_conflict"),
    "Something changed while you were opting in. The list has been refreshed; try again.",
    true,
  ],
];

describe("speakerPortalError", () => {
  it.each(ROWS)("%s maps to its message and refetch flag", (_, context, cause, message, refetch) => {
    expect(speakerPortalError(context, cause)).toEqual({ message, refetch });
  });

  it("suppression_not_liftable picks the message by details.reason; absent reason reads as delivery", () => {
    const absent = speakerPortalError(
      "channel",
      failure(409, "speaker_contact_channel_suppression_not_liftable"),
    );
    expect(absent.message).toBe(
      "Messages to this address could not be delivered, so it cannot be turned back on. Ask your Speaker Connector to add a different address.",
    );
    expect(absent.refetch).toBe(true);
  });

  it("no message contains the server's message text", () => {
    for (const [, context, cause] of ROWS) {
      expect(speakerPortalError(context, cause).message).not.toContain(SENTINEL);
    }
    expect(speakerPortalError("availability", failure(422, "invalid_request")).message).not.toContain(
      SENTINEL,
    );
  });

  it("a non-ApiRequestError reads as the no-reason fallback", () => {
    expect(speakerPortalError("read-addresses", new TypeError("Failed to fetch"))).toEqual({
      message: "Your addresses could not be loaded, and the server gave no reason. Try again.",
      refetch: false,
    });
    expect(speakerPortalError("channel", "boom")).toEqual({
      message: WRITE_FALLBACK,
      refetch: false,
    });
  });

  it("a refetch code from another context does not re-read this one", () => {
    expect(speakerPortalError("channel", failure(404, "speaker_invitation_not_found"))).toEqual({
      message: WRITE_FALLBACK,
      refetch: false,
    });
  });
});

describe("selfNoticeKind", () => {
  it("names the page-level notice for not linked, 403 and 401, and nothing else", () => {
    expect(selfNoticeKind(failure(404, "speaker_profile_not_linked"))).toBe("not_linked");
    expect(selfNoticeKind(failure(403, "forbidden"))).toBe("denied");
    expect(selfNoticeKind(failure(401, "unauthenticated"))).toBe("signed_out");
    expect(selfNoticeKind(failure(404, "not_found"))).toBeNull();
    expect(selfNoticeKind(failure(500, "internal_error"))).toBeNull();
    expect(selfNoticeKind(new TypeError("Failed to fetch"))).toBeNull();
  });
});
