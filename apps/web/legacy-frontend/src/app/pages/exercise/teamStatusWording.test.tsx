/**
 * The status line's words (issue #321; Ann's revisions of 2026-10-02, §1).
 * Timestamps carry no zone, so they read the same wherever the tests run.
 */
import { describe, expect, it } from "vitest";

import type { EventView } from "../../../lib/exerciseClient";
import {
  askingWords,
  refreshWords,
  resultsWords,
  roundsOf,
  teamLine,
  teamStatusItems,
  teamStatusSentence,
} from "./teamStatusWording";

function event(over: Partial<EventView>): EventView {
  return {
    event_key: "e",
    name: "An event",
    topic_tags: [],
    target_majors: [],
    is_exercise_event: false,
    sequence: 1,
    description: null,
    results_open: false,
    results_run: false,
    ...over,
  };
}

const NORTHLINE = event({
  event_key: "northline",
  name: "Northline Analytics: Behind the Business",
  is_exercise_event: true,
  sequence: 11,
});
const HARBOR = event({
  event_key: "harbor",
  name: "Harbor Consumer Brands: Behind the Business",
  is_exercise_event: true,
  sequence: 12,
});
const PAST = event({ event_key: "past", name: "Resume night", sequence: 1 });

const WORKSPACE = { team_number: 3, dataset_label: "October file", invite_limit: 30 };
const NOT_ASKED = { choice: null, refreshed: false, refreshed_at: null };

describe("roundsOf", () => {
  it("numbers the exercise events by their order in the file, never by name", () => {
    const rounds = roundsOf([HARBOR, PAST, NORTHLINE]);
    expect(rounds.map((round) => [round.round, round.eventKey])).toEqual([
      [1, "northline"],
      [2, "harbor"],
    ]);
  });

  it("reads a server without the two results fields as closed and not run", () => {
    const old = { ...NORTHLINE, results_open: undefined, results_run: undefined } as unknown as EventView;
    expect(roundsOf([old])[0]).toMatchObject({ open: false, run: false });
  });
});

describe("the words for each fact", () => {
  it("says which team this is, in Ann's words", () => {
    expect(teamLine(3)).toBe("You are Team 3");
  });

  it("says whether results were used, and whether they could be", () => {
    expect(resultsWords({ open: false, run: false })).toBe("Results not used yet (not open yet)");
    expect(resultsWords({ open: true, run: false })).toBe("Results not used yet (open now)");
    expect(resultsWords({ open: true, run: true })).toBe("Results used");
  });

  it("lets a run win over a lock closed again afterwards", () => {
    expect(resultsWords({ open: false, run: true })).toBe("Results used");
  });

  it("names the way of asking, or says none is chosen", () => {
    expect(askingWords(null)).toBe("Not chosen yet");
    expect(askingWords("small_reward")).toBe("A small reward");
    // A way of asking the server adds later is shown as it is sent.
    expect(askingWords("something_new")).toBe("something_new");
  });

  it("says whether the refresh is done, with its time", () => {
    expect(refreshWords(false, null)).toBe("Not done yet");
    expect(refreshWords(true, "2026-10-16T10:42:00")).toBe("Done at 10:42 AM");
    expect(refreshWords(true, null)).toBe("Done");
    // A time without the flag is not a refresh.
    expect(refreshWords(false, "2026-10-16T10:42:00")).toBe("Not done yet");
  });
});

describe("teamStatusItems", () => {
  it("lists both rounds, the way of asking, the refresh and the data file", () => {
    const items = teamStatusItems(WORKSPACE, [PAST, NORTHLINE, HARBOR], NOT_ASKED);
    expect(items).toEqual([
      {
        key: "round-1",
        label: "Round 1 · Northline Analytics: Behind the Business",
        value: "Results not used yet (not open yet)",
      },
      {
        key: "round-2",
        label: "Round 2 · Harbor Consumer Brands: Behind the Business",
        value: "Results not used yet (not open yet)",
      },
      { key: "asking", label: "Way of asking", value: "Not chosen yet" },
      { key: "refresh", label: "Refresh", value: "Not done yet" },
      { key: "file", label: "Data file", value: "October file" },
    ]);
  });

  it("marks the event the page is about, in words", () => {
    const items = teamStatusItems(WORKSPACE, [NORTHLINE, HARBOR], NOT_ASKED, "harbor");
    expect(items[0].label).toBe("Round 1 · Northline Analytics: Behind the Business");
    expect(items[1].label).toBe("Round 2 · Harbor Consumer Brands: Behind the Business (this page)");
  });

  it("shows a team that is through round one and refreshed", () => {
    const items = teamStatusItems(
      WORKSPACE,
      [{ ...NORTHLINE, results_open: true, results_run: true }, { ...HARBOR, results_open: true }],
      { choice: "required", refreshed: true, refreshed_at: "2026-10-16T10:42:00" },
    );
    expect(items.map((item) => item.value)).toEqual([
      "Results used",
      "Results not used yet (open now)",
      "Required",
      "Done at 10:42 AM",
      "October file",
    ]);
  });

  it("still says the rest when the file has no exercise events", () => {
    const items = teamStatusItems(WORKSPACE, [PAST], NOT_ASKED);
    expect(items.map((item) => item.key)).toEqual(["asking", "refresh", "file"]);
  });
});

describe("teamStatusSentence", () => {
  it("reads the whole line as sentences", () => {
    const items = teamStatusItems(WORKSPACE, [NORTHLINE], NOT_ASKED);
    expect(teamStatusSentence(3, items)).toBe(
      "You are Team 3. Round 1 · Northline Analytics: Behind the Business: Results not used yet (not open yet). " +
        "Way of asking: Not chosen yet. Refresh: Not done yet. Data file: October file.",
    );
  });
});
