/**
 * The Speaker Portal's formatters (B26 T6b-4 §5, §6.3). Pure: server fields
 * in, words out.
 *
 * Nothing here re-derives a fact the server computed. `send_eligible` is shown
 * as it arrived (the `api.ts` rule for contact channels): a sentence built from
 * `contact_state` would be this browser's opinion of who may be emailed.
 */
import type {
  MyContactChannel,
  MyEngagementEvent,
  MyEngagementState,
  MyInvitation,
  MyInvitationStatus,
} from "@/lib/api";
import { formatCalendarDate } from "@/lib/speakerAvailabilityDraft";

/** An instant in the viewer's own zone, e.g. "Oct 6, 2026, 5:00 AM". */
export function formatInstant(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

/** One sentence for a channel's status, from the server's fields only (§5.5). */
export function channelStatusSentence(view: MyContactChannel): string {
  if (view.send_eligible) return "Invitations can be emailed here.";
  switch (view.suppression_reason) {
    case "your_opt_out":
      return "You opted out.";
    case "unsubscribed":
      return "Unsubscribed through an email link.";
    case "connector":
      return "Your Speaker Connector stopped messages to this address.";
    case "delivery":
      return "Messages to this address could not be delivered.";
    default:
      return "Not yet confirmed for invitations.";
  }
}

/** Who last set a channel. Never a user id. */
export function lastSetByLabel(lastSetBy: MyContactChannel["last_set_by"]): string {
  return lastSetBy === "speaker" ? "Last set by you" : "Last set by your Speaker Connector";
}

/** A time of day in the event's own zone; `withZone` adds "PDT"-style names. */
function timeInZone(iso: string, timeZone: string, withZone: boolean): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
    ...(withZone ? { timeZoneName: "short" } : {}),
  }).format(new Date(iso));
}

/**
 * When an engagement is, from the server's event fields (§6.3).
 *
 * The calendar date is the event's own `local_date`, never shifted by the
 * viewer's zone. An exact time is shown in the event's zone and names it, so a
 * Speaker reading from another zone is not misled about when to arrive.
 */
export function formatEventWhen(event: MyEngagementEvent | null): string {
  if (event === null) return "Event details are no longer available.";
  if (event.local_date === null || event.time_precision === "unresolved") {
    return "Date not set yet";
  }
  const date = formatCalendarDate(event.local_date);
  if (event.time_precision === "date_only") return `${date} · Time not set`;
  if (event.starts_at === null || event.time_zone === null) return date;
  if (event.ends_at === null) {
    return `${date}, ${timeInZone(event.starts_at, event.time_zone, true)}`;
  }
  return `${date}, ${timeInZone(event.starts_at, event.time_zone, false)} – ${timeInZone(
    event.ends_at,
    event.time_zone,
    true,
  )}`;
}

const ENGAGEMENT_STATE_LABEL: Record<MyEngagementState, string> = {
  confirmed: "Confirmed",
  attended: "Attended",
  cancelled: "Cancelled",
};

export function engagementStateLabel(state: MyEngagementState): string {
  return ENGAGEMENT_STATE_LABEL[state];
}

const INVITATION_STATUS_LABEL: Record<MyInvitationStatus, string> = {
  awaiting_response: "Waiting for your answer",
  accepted_invitation: "Accepted",
  declined_invitation: "Declined",
};

export function invitationStatusLabel(status: MyInvitationStatus): string {
  return INVITATION_STATUS_LABEL[status];
}

/** Who answered, in words (§5.2 I3). Never a user id. */
export function answerSentence(invitation: MyInvitation): string {
  if (invitation.response === null || invitation.status === "awaiting_response") {
    return invitationStatusLabel("awaiting_response");
  }
  const verb = invitation.status === "accepted_invitation" ? "accepted" : "declined";
  return invitation.response.recorded_by === "speaker"
    ? `You ${verb}`
    : `Your Speaker Connector recorded that you ${verb}`;
}

/**
 * An element id built from a server id, safe inside `id` and inside the
 * space-separated `aria-describedby`, whatever characters the server id holds.
 */
export function domId(prefix: string, id: string): string {
  return `${prefix}-${id.replace(/[^A-Za-z0-9_-]/g, (c) => `_${c.charCodeAt(0).toString(16)}`)}`;
}
