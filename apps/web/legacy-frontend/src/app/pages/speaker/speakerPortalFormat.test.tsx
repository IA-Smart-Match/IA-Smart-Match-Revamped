/**
 * The Speaker portal's formatters (T6b-4 §5.5, §6.3). Pure: server fields in,
 * words out. Nothing here re-derives what the server computed.
 */
import { describe, expect, it } from "vitest";

import type { MyContactChannel } from "@/lib/api";

import { channelStatusSentence, formatInstant, lastSetByLabel } from "./speakerPortalFormat";

function channel(overrides: Partial<MyContactChannel>): MyContactChannel {
  return {
    contact_channel_id: "ch-1",
    channel_kind: "email",
    address: "dana@example.edu",
    contact_state: "active_candidate",
    send_eligible: false,
    suppressed: false,
    suppression_reason: null,
    speaker_choice: null,
    last_set_by: "connector",
    can_opt_in: false,
    can_opt_out: true,
    updated_at: "2026-10-01T12:00:00Z",
    ...overrides,
  };
}

describe("channelStatusSentence", () => {
  it.each([
    ["send_eligible", channel({ send_eligible: true }), "Invitations can be emailed here."],
    [
      "your_opt_out",
      channel({ suppressed: true, suppression_reason: "your_opt_out" }),
      "You opted out.",
    ],
    [
      "unsubscribed",
      channel({ suppressed: true, suppression_reason: "unsubscribed" }),
      "Unsubscribed through an email link.",
    ],
    [
      "connector",
      channel({ suppressed: true, suppression_reason: "connector" }),
      "Your Speaker Connector stopped messages to this address.",
    ],
    [
      "delivery",
      channel({ suppressed: true, suppression_reason: "delivery" }),
      "Messages to this address could not be delivered.",
    ],
    ["not suppressed, not eligible", channel({}), "Not yet confirmed for invitations."],
  ])("covers %s", (_, view, sentence) => {
    expect(channelStatusSentence(view)).toBe(sentence);
  });

  it("shows send_eligible as the server said it, never re-derived from the state", () => {
    // A state that would look eligible, with the server saying it is not.
    expect(channelStatusSentence(channel({ contact_state: "active_candidate" }))).toBe(
      "Not yet confirmed for invitations.",
    );
  });
});

describe("lastSetByLabel", () => {
  it("names who last set the channel, never an id", () => {
    expect(lastSetByLabel("speaker")).toBe("Last set by you");
    expect(lastSetByLabel("connector")).toBe("Last set by your Speaker Connector");
  });
});

describe("formatInstant", () => {
  it("formats an instant as a medium date and short time", () => {
    // Midday UTC, so the date part holds in every zone a test runner uses.
    expect(formatInstant("2026-10-06T12:00:00Z")).toMatch(/^Oct 6, 2026, \d{1,2}:\d{2}\s?[AP]M$/);
  });
});
