/**
 * The refresh's sentences, composed in the browser from the server's facts.
 *
 * Ann's checklist of 2026-10-02 (section 6) gives the words; these tests hold
 * them. Timestamps are written without a zone so they read as the same wall
 * clock time wherever the tests run.
 */
import { describe, expect, it } from "vitest";

import type { RefreshCountsView } from "../../../lib/exerciseClient";
import {
  alreadyRefreshedLabel,
  formatClockTime,
  markerCountLines,
  markerCountTotal,
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

describe("formatClockTime", () => {
  it("reads as the time on the room's clock, with a plain space", () => {
    expect(formatClockTime(AT)).toBe("10:42 AM");
    expect(formatClockTime("2026-10-16T14:05:00")).toBe("2:05 PM");
  });

  it("is null when there is no time to show", () => {
    expect(formatClockTime(null)).toBeNull();
    expect(formatClockTime(undefined)).toBeNull();
    expect(formatClockTime("not a time")).toBeNull();
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
