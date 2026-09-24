/**
 * The Speaker portal's formatters (T6b-4 §5.5, §6.3). Pure: server fields in,
 * words out. Nothing here re-derives what the server computed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MyContactChannel, MyEngagementEvent, MyInvitation } from "@/lib/api";

import {
  answerSentence,
  channelStatusSentence,
  engagementStateLabel,
  formatEventWhen,
  formatInstant,
  invitationStatusLabel,
  lastSetByLabel,
} from "./speakerPortalFormat";

/** ICU may put a narrow no-break space before AM/PM; compare on plain spaces. */
function plain(text: string): string {
  return text.replace(/\s/g, " ");
}

function event(overrides: Partial<MyEngagementEvent>): MyEngagementEvent {
  return {
    title: "ACCT 4100 guest lecture",
    local_date: "2026-10-14",
    time_zone: "America/Los_Angeles",
    time_precision: "exact",
    starts_at: "2026-10-14T17:00:00Z",
    ends_at: "2026-10-14T18:15:00Z",
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("formatEventWhen", () => {
  it("exact engagement formats in the event's zone", () => {
    expect(plain(formatEventWhen(event({})))).toBe("October 14, 2026, 10:00 AM – 11:15 AM PDT");
  });

  it("an exact start with no end shows the start in the event's zone", () => {
    expect(plain(formatEventWhen(event({ ends_at: null })))).toBe("October 14, 2026, 10:00 AM PDT");
  });

  it("date_only says Time not set; unresolved says Date not set yet; null event says details unavailable", () => {
    expect(
      formatEventWhen(event({ time_precision: "date_only", starts_at: null, ends_at: null })),
    ).toBe("October 14, 2026 · Time not set");
    expect(
      formatEventWhen(
        event({ time_precision: "unresolved", local_date: null, starts_at: null, ends_at: null }),
      ),
    ).toBe("Date not set yet");
    expect(formatEventWhen(null)).toBe("Event details are no longer available.");
  });

  it("an instant with no time zone shows the date only", () => {
    expect(formatEventWhen(event({ time_zone: null }))).toBe("October 14, 2026");
  });

  it("calendar dates never shift a day", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-02T03:00:00Z"));
    expect(
      formatEventWhen(
        event({ local_date: "2026-11-02", time_precision: "date_only", starts_at: null, ends_at: null }),
      ),
    ).toBe("November 2, 2026 · Time not set");
  });
});

describe("state and status labels", () => {
  it("engagementStateLabel and invitationStatusLabel cover every enum value", () => {
    expect(engagementStateLabel("confirmed")).toBe("Confirmed");
    expect(engagementStateLabel("attended")).toBe("Attended");
    expect(engagementStateLabel("cancelled")).toBe("Cancelled");
    expect(invitationStatusLabel("awaiting_response")).toBe("Waiting for your answer");
    expect(invitationStatusLabel("accepted_invitation")).toBe("Accepted");
    expect(invitationStatusLabel("declined_invitation")).toBe("Declined");
  });
});

describe("answerSentence", () => {
  const base: MyInvitation = {
    invitation_id: "inv-1",
    event: { title: "Spring Mixer", date_text: "Thursday 12 March 2027", local_date: null, time_zone: null },
    dispatched_at: "2026-10-01T12:00:00Z",
    status: "accepted_invitation",
    response: { recorded_at: "2026-10-02T12:00:00Z", recorded_by: "speaker" },
    answerable: false,
  };

  it("says who recorded the answer and never an id", () => {
    expect(answerSentence(base)).toBe("You accepted");
    expect(answerSentence({ ...base, status: "declined_invitation" })).toBe("You declined");
    expect(
      answerSentence({
        ...base,
        response: { recorded_at: "2026-10-02T12:00:00Z", recorded_by: "speaker_connector" },
      }),
    ).toBe("Your Speaker Connector recorded that you accepted");
    expect(answerSentence({ ...base, status: "awaiting_response", response: null })).toBe(
      "Waiting for your answer",
    );
  });
});

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
