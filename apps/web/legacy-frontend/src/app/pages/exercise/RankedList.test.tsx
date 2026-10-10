/**
 * The ranked list's reason line: one concise line per profile (the server's
 * reason, verbatim). The separate "what counted" factor-names line is gone.
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

afterEach(cleanup);

describe("<RankedList /> reason line", () => {
  it("shows one reason line per entry and no factor-names line", () => {
    render(
      <RankedList
        entries={[entry(["career_goal_fit", "same_major"])]}
        factorLabels={FACTOR_LABELS}
        caption="List"
      />,
    );
    expect(document.querySelectorAll(".ce-type-reason")).toHaveLength(1);
    expect(document.querySelector('[data-slot="exercise-factor-names"]')).toBeNull();
  });
});
