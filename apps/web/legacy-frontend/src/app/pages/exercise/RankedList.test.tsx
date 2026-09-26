/**
 * The ranked list's "what counted" line, for the Undecided half (D2).
 *
 * An undecided career goal earns half the career-goal factor on an
 * exploratory event. The server says so in the reason ("undecided goal suits a
 * broad event") and flags it as `undecided_goal_half`. The factor line under
 * the reason must say the same, rather than telling a class that an
 * "Undecided" card's goal fits the event.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ListEntryView } from "../../../lib/exerciseClient";
import { RankedList } from "./RankedList";

const FACTOR_LABELS = {
  same_major: "same major",
  career_goal_fit: "career goal fits this event",
};

function entry(undecidedGoalHalf: boolean): ListEntryView {
  return {
    rank: 1,
    profile_no: 12,
    display_name: "Sam Ortega",
    major: "Accounting",
    class_year: "second",
    marker: "completed_card",
    reason: "Undecided goal suits a broad event; same major.",
    contributing_factor_keys: ["career_goal_fit", "same_major"],
    undecided_goal_half: undecidedGoalHalf,
  };
}

function factorLine(): string {
  const cell = document.querySelector('[data-slot="exercise-ranked-list"] tbody td:last-child');
  return cell?.querySelector("span")?.textContent ?? "";
}

afterEach(cleanup);

describe("<RankedList /> factor names", () => {
  it("names the Undecided half as a broad-event fit, not a goal fit", () => {
    render(<RankedList entries={[entry(true)]} factorLabels={FACTOR_LABELS} caption="List" />);
    expect(factorLine()).toBe("undecided goal suits a broad event; same major");
    expect(factorLine()).not.toContain("career goal fits this event");
  });

  it("keeps the server's label when the goal really fits", () => {
    render(<RankedList entries={[entry(false)]} factorLabels={FACTOR_LABELS} caption="List" />);
    expect(factorLine()).toBe("career goal fits this event; same major");
  });
});
