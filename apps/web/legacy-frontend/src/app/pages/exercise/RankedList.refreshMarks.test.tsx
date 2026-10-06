/**
 * The ranked list marks the profiles a team's refresh changed.
 *
 * Ann's checklist of 2026-10-02, section 6: "The changed profiles are marked
 * in the list (for example 'new card' or 'new: went to Northline'), so a team
 * can see who changed." And section 7: profiles marked "stopped responding"
 * are "either left off the list or clearly marked on it" — they are marked.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ListEntryView } from "../../../lib/exerciseClient";
import { RankedList } from "./RankedList";

function entry(profileNo: number, name: string, marks?: readonly string[]): ListEntryView {
  return {
    rank: profileNo,
    profile_no: profileNo,
    display_name: name,
    major: "Accounting",
    class_year: "Senior",
    marker: "completed_card",
    reason: "Same major.",
    contributing_factor_keys: ["same_major"],
    undecided_goal_half: false,
    ...(marks === undefined ? {} : { refresh_marks: marks }),
  };
}

function marksIn(row: Element | null): string[] {
  return [...(row?.querySelectorAll('[data-slot="exercise-refresh-mark"]') ?? [])].map(
    (chip) => chip.textContent ?? "",
  );
}

function rowFor(name: string): Element | null {
  const cell = [...document.querySelectorAll('[data-slot="exercise-ranked-name"]')].find((found) =>
    found.textContent?.includes(name),
  );
  return cell ?? null;
}

afterEach(cleanup);

describe("<RankedList /> refresh marks", () => {
  const ENTRIES = [
    entry(1, "Brandon Soto", ["new_card"]),
    entry(2, "Mei Tanaka", ["new_event"]),
    entry(3, "Luis Ortega", ["stopped_responding"]),
    entry(4, "Priya Nair", ["new_card", "new_event"]),
    entry(5, "Dana Whitfield", []),
    entry(6, "Sam Okafor"),
  ];

  it("marks each changed profile beside its name, in words", () => {
    render(
      <RankedList
        entries={ENTRIES}
        factorLabels={{ same_major: "same major" }}
        caption="List"
        firstRoundEventName="Northline"
      />,
    );
    expect(marksIn(rowFor("Brandon Soto"))).toEqual(["New card"]);
    expect(marksIn(rowFor("Mei Tanaka"))).toEqual(["New: went to Northline"]);
    expect(marksIn(rowFor("Luis Ortega"))).toEqual(["Stopped responding"]);
  });

  it("shows every mark a profile carries, not just one", () => {
    render(
      <RankedList
        entries={ENTRIES}
        factorLabels={{}}
        caption="List"
        firstRoundEventName="Northline"
      />,
    );
    expect(marksIn(rowFor("Priya Nair"))).toEqual(["New card", "New: went to Northline"]);
  });

  it("draws nothing for a profile the refresh did not change, or before any refresh", () => {
    render(<RankedList entries={ENTRIES} factorLabels={{}} caption="List" />);
    expect(marksIn(rowFor("Dana Whitfield"))).toEqual([]);
    expect(marksIn(rowFor("Sam Okafor"))).toEqual([]);
  });

  it("names no event it was not given", () => {
    render(<RankedList entries={ENTRIES} factorLabels={{}} caption="List" />);
    expect(marksIn(rowFor("Mei Tanaka"))).toEqual(["New: went to the first event"]);
  });

  it("marks them in the card layout too", () => {
    render(
      <RankedList
        entries={ENTRIES}
        factorLabels={{}}
        caption="List"
        layout="cards"
        firstRoundEventName="Northline"
      />,
    );
    const chips = [...document.querySelectorAll('[data-slot="exercise-refresh-mark"]')];
    expect(chips.map((chip) => chip.getAttribute("data-mark"))).toEqual([
      "new_card",
      "new_event",
      "stopped_responding",
      "new_card",
      "new_event",
    ]);
  });
});
