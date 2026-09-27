/**
 * The Undecided half's words come from the server's `factor_labels`.
 *
 * The web used to keep its own copy of "undecided goal suits a broad event".
 * The list response now sends it under `undecided_goal_half`, so the ranked
 * list prints the server's words, and the weights panel — which draws one box
 * per `factor_labels` key — must not grow a box for a label that is not a
 * weight.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ListEntryView } from "../../../lib/exerciseClient";
import { RankedList } from "./RankedList";
import { WeightsControls } from "./WeightsControls";

const SERVER_WORDS = "the server's words for an undecided half";

const LABELS = {
  same_major: "same major",
  stated_interest_overlap: "said they are interested in this topic",
  career_goal_fit: "career goal fits this event",
  past_event_topic_overlap: "went to similar events before",
  undecided_goal_half: SERVER_WORDS,
};

const WEIGHTS = {
  same_major: 0.25,
  stated_interest_overlap: 0.25,
  career_goal_fit: 0.25,
  past_event_topic_overlap: 0.25,
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
  // The "what counted" line sits under the name (DESIGN.md §6.7).
  return document.querySelector('[data-slot="exercise-factor-names"]')?.textContent ?? "";
}

afterEach(cleanup);

describe("the Undecided half's label", () => {
  it("is read from factor_labels, not a copy in the web", () => {
    render(<RankedList entries={[entry(true)]} factorLabels={LABELS} caption="List" />);
    expect(factorLine()).toBe(`${SERVER_WORDS}; same major`);
  });

  it("is dropped, not replaced by the goal-fit label, when the server sends none", () => {
    const { undecided_goal_half: _unused, ...withoutIt } = LABELS;
    render(<RankedList entries={[entry(true)]} factorLabels={withoutIt} caption="List" />);
    expect(factorLine()).toBe("same major");
  });

  it("gets no weight box", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    expect(screen.queryByLabelText(SERVER_WORDS)).toBeNull();
    expect(document.querySelectorAll('[data-slot="exercise-weights"] input')).toHaveLength(4);
  });
});
