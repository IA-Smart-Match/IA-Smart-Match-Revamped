/**
 * The Speaker Portal's formatters (B26 T6b-4 §5, §6.3). Pure: server fields
 * in, words out.
 *
 * Nothing here re-derives a fact the server computed. `send_eligible` is shown
 * as it arrived (the `api.ts` rule for contact channels): a sentence built from
 * `contact_state` would be this browser's opinion of who may be emailed.
 */
import type { MyContactChannel } from "@/lib/api";

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
