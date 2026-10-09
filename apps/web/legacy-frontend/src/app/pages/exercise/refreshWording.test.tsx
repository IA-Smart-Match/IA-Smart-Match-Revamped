/**
 * The refresh's sentences, composed in the browser from the server's facts.
 *
 * Ann's checklist of 2026-10-02 (section 6) gives the words; these tests hold
 * them. Timestamps are written without a zone so they read as the same wall
 * clock time wherever the tests run; the one case that carries an offset, as
 * the server's do, pins the room's time zone first.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RefreshAllTeamView, RefreshCountsView } from "../../../lib/exerciseClient";
import { clockTime } from "./exerciseTime";
import {
  alreadyRefreshedLabel,
  markerCountLines,
  markerCountTotal,
  refreshAllHeadline,
  refreshAllTeamLine,
  refreshChangeSentences,
  refreshDoneLine,
  refreshMarkLabel,
  refreshSummaryText,
} from "./refreshWording";

const AT = "2026-10-16T10:42:00";

const COUNTS: RefreshCountsView = {
  cards_completed: 12,
  non_responding: 0,
  topics_added: 9,
  invited_without_card: 22,
  marker_counts_before: { major_only: 166, major_plus_events: 64, completed_card: 70 },
  marker_counts_after: { major_only: 160, major_plus_events: 58, completed_card: 82 },
};

describe("clockTime", () => {
  it("reads as the time on the room's clock, with a plain space", () => {
    expect(clockTime(AT)).toBe("10:42 AM");
    expect(clockTime("2026-10-16T14:05:00")).toBe("2:05 PM");
  });

  it("is null when there is no time to show", () => {
    expect(clockTime(null)).toBeNull();
    expect(clockTime(undefined)).toBeNull();
    expect(clockTime("not a time")).toBeNull();
  });

  it("shows the seconds only when asked: a press read off this browser's own clock", () => {
    // Two presses in one minute must not read as the same line (PR #346 review).
    expect(clockTime("2026-10-16T10:43:07", { seconds: true })).toBe("10:43:07 AM");
    expect(clockTime("2026-10-16T14:05:59", { seconds: true })).toBe("2:05:59 PM");
    // A time the server recorded stays to the minute.
    expect(clockTime("2026-10-16T10:43:07")).toBe("10:43 AM");
    expect(clockTime(null, { seconds: true })).toBeNull();
  });
});

describe("a server timestamp, which carries its offset", () => {
  const realFormat = Intl.DateTimeFormat;

  afterEach(() => {
    Intl.DateTimeFormat = realFormat;
    vi.resetModules();
  });

  /** The module as a browser in `timeZone` loads it, whatever zone the tests run in. */
  async function inRoom(
    timeZone: string,
  ): Promise<typeof import("./refreshWording") & typeof import("./exerciseTime")> {
    class RoomClock extends realFormat {
      constructor(locales?: string | string[], options?: Intl.DateTimeFormatOptions) {
        super(locales, { ...options, timeZone });
      }
    }
    Intl.DateTimeFormat = RoomClock as typeof Intl.DateTimeFormat;
    vi.resetModules();
    return { ...(await import("./exerciseTime")), ...(await import("./refreshWording")) };
  }

  it("reads as the room's clock, not as the hour written in the value", async () => {
    const utc = "2026-10-16T17:42:00+00:00";
    const pacific = await inRoom("America/Los_Angeles");
    expect(pacific.clockTime(utc)).toBe("10:42 AM");
    expect(pacific.alreadyRefreshedLabel(utc)).toBe("Already refreshed at 10:42 AM");
    expect(pacific.refreshDoneLine(utc)).toBe("Refresh done at 10:42 AM.");

    const eastern = await inRoom("America/New_York");
    expect(eastern.clockTime(utc)).toBe("1:42 PM");
  });
});

describe("the refresh summary", () => {
  it("is Ann's example, word for word", () => {
    expect(refreshSummaryText(AT, COUNTS, "Northline")).toBe(
      "Refresh done at 10:42 AM. 9 people who came to Northline now count as having gone to a similar event. 12 of the 22 invited people with no card completed one. 0 people stopped responding.",
    );
  });

  it("uses the singular for one person", () => {
    const one = { ...COUNTS, topics_added: 1, non_responding: 1, invited_without_card: 1, cards_completed: 1 };
    expect(refreshChangeSentences(one, "Northline")).toEqual([
      "1 person who came to Northline now counts as having gone to a similar event.",
      "1 of the 1 invited person with no card completed one.",
      "1 person stopped responding.",
    ]);
  });

  it("says so when nobody the team invited was without a card", () => {
    const none = { ...COUNTS, invited_without_card: 0, cards_completed: 0 };
    expect(refreshChangeSentences(none, "Northline")[1]).toBe(
      "Everyone your team invited already had a card.",
    );
  });

  it("names no event it was not given, and leaves out a time it does not have", () => {
    expect(refreshChangeSentences(COUNTS, null)[0]).toBe(
      "9 people who came to the first event now count as having gone to a similar event.",
    );
    expect(refreshDoneLine(null)).toBe("Refresh done.");
    expect(refreshSummaryText(null, null, null)).toBe("Refresh done.");
  });

  it("never writes a percentage", () => {
    expect(refreshSummaryText(AT, COUNTS, "Northline")).not.toContain("%");
  });
});

describe("the shut button", () => {
  it("says when the refresh happened", () => {
    expect(alreadyRefreshedLabel(AT)).toBe("Already refreshed at 10:42 AM");
    expect(alreadyRefreshedLabel(null)).toBe("Already refreshed");
  });
});

describe("the before-and-after counts", () => {
  it("lists the three groups, most on file first, in Ann's words", () => {
    expect(markerCountLines(COUNTS)).toEqual([
      { marker: "completed_card", label: "Completed card", before: 70, after: 82 },
      { marker: "major_plus_events", label: "Major plus events attended", before: 64, after: 58 },
      { marker: "major_only", label: "Major only", before: 166, after: 160 },
    ]);
    expect(markerCountTotal(COUNTS)).toBe(300);
  });

  it("lists a group it does not know under its own name, after the three", () => {
    const lines = markerCountLines({
      ...COUNTS,
      marker_counts_before: { ...COUNTS.marker_counts_before, a_fourth: 1 },
      marker_counts_after: { ...COUNTS.marker_counts_after, a_fourth: 2 },
    });
    expect(lines[3]).toEqual({ marker: "a_fourth", label: "A_fourth", before: 1, after: 2 });
  });
});

describe("the marks on a list entry", () => {
  it("uses Ann's words and names the first round's event", () => {
    expect(refreshMarkLabel("new_card", "Northline")).toBe("New card");
    expect(refreshMarkLabel("new_event", "Northline")).toBe("New: went to Northline");
    expect(refreshMarkLabel("stopped_responding", "Northline")).toBe("Stopped responding");
  });

  it("falls back to plain words without an event name, and to the value for an unknown mark", () => {
    expect(refreshMarkLabel("new_event", null)).toBe("New: went to the first event");
    expect(refreshMarkLabel("a_fourth_mark", "Northline")).toBe("a_fourth_mark");
  });
});

describe("the instructor's every-team report", () => {
  const SKIPPED: RefreshAllTeamView = {
    team_number: 4,
    dataset_label: "October file",
    outcome: "skipped",
    reason_code: "no_asking_choice",
    refreshed_at: null,
    refresh_counts: null,
    first_round_event_name: null,
  };
  const REFRESHED: RefreshAllTeamView = {
    ...SKIPPED,
    team_number: 2,
    outcome: "refreshed",
    reason_code: null,
    refreshed_at: AT,
    refresh_counts: COUNTS,
    first_round_event_name: "Northline",
  };

  it("gives a refreshed team the summary that team reads itself", () => {
    expect(refreshAllTeamLine(REFRESHED, { nameFile: false })).toEqual({
      team: "Team 2:",
      what: "Refreshed at 10:42 AM. 9 people who came to Northline now count as having gone to a similar event. 12 of the 22 invited people with no card completed one. 0 people stopped responding. Completed card: 70 → 82.",
    });
  });

  it("says why a team was skipped, from the server's code", () => {
    const why = (reason: string, at: string | null = null) =>
      refreshAllTeamLine({ ...SKIPPED, reason_code: reason, refreshed_at: at }, { nameFile: false })
        .what;
    expect(why("no_asking_choice")).toBe("Skipped: it has not chosen a way of asking.");
    expect(why("no_round_one_run")).toBe("Skipped: it has not run results for its first event.");
    expect(why("already_refreshed", "2026-10-16T10:31:00")).toBe(
      "Skipped: it was already refreshed at 10:31 AM.",
    );
    expect(why("already_refreshed")).toBe("Skipped: it was already refreshed.");
  });

  it("invents no reason for a code it does not know", () => {
    expect(
      refreshAllTeamLine({ ...SKIPPED, reason_code: "a_new_reason" }, { nameFile: false }).what,
    ).toBe("Skipped.");
  });

  it("names the file only when asked to", () => {
    expect(refreshAllTeamLine(SKIPPED, { nameFile: true }).team).toBe("Team 4 (October file):");
  });

  it("counts both outcomes in the headline, and says when there was no team", () => {
    const view = { refreshed_team_numbers: [2], refreshed: 1, skipped: 0 };
    expect(refreshAllHeadline({ ...view, teams: [REFRESHED, SKIPPED] })).toBe(
      "Refreshed 1 team. Skipped 1 team.",
    );
    expect(refreshAllHeadline({ ...view, refreshed: 0, refreshed_team_numbers: [], teams: [] })).toBe(
      "No team has entered a number yet, so there was nothing to refresh.",
    );
  });
});
