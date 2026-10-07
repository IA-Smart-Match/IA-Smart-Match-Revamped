/**
 * The ranked list's "what counted" line.
 *
 * Under the reason, the factors that counted are named in the server's words,
 * read from `factor_labels`. A key with no label is dropped, never printed raw.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ListEntryView } from "../../../lib/exerciseClient";
import { RankedList } from "./RankedList";

const FACTOR_LABELS = {
  same_major: "same major",
  career_goal_fit: "career goal fits this event",
};

function entry(contributingFactorKeys: string[]): ListEntryView {
  return {
    rank: 1,
    profile_no: 12,
    display_name: "Sam Ortega",
    major: "Accounting",
    class_year: "second",
    marker: "completed_card",
    reason: "What counted: career goal fits this event and same major.",
    contributing_factor_keys: contributingFactorKeys,
  };
}

function factorLine(): string {
  // The "what counted" line sits under the name (DESIGN.md §6.7).
  return document.querySelector('[data-slot="exercise-factor-names"]')?.textContent ?? "";
}

afterEach(cleanup);

describe("<RankedList /> factor names", () => {
  it("names each factor that counted in the server's words", () => {
    render(
      <RankedList
        entries={[entry(["career_goal_fit", "same_major"])]}
        factorLabels={FACTOR_LABELS}
        caption="List"
      />,
    );
    expect(factorLine()).toBe("career goal fits this event; same major");
  });

  it("drops a key the server sent no label for", () => {
    render(
      <RankedList
        entries={[entry(["past_event_topic_overlap", "same_major"])]}
        factorLabels={FACTOR_LABELS}
        caption="List"
      />,
    );
    expect(factorLine()).toBe("same major");
  });
});
