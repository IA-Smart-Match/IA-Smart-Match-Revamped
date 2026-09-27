/**
 * The compare view (DESIGN.md §6.12, §7.5): two lists side by side on
 * desktop, a segmented control on 390 with ten rows and "Show all".
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CompareView, ListEntryView, RankedListView } from "../../../lib/exerciseClient";
import { MatchingCompareView } from "./MatchingCompareView";

const LABELS = { same_major: "same major" };

function entries(prefix: string, count: number): ListEntryView[] {
  return Array.from({ length: count }, (_, index) => ({
    rank: index + 1,
    profile_no: index === 0 ? 1 : index + (prefix === "A" ? 100 : 200),
    display_name: `${prefix} person ${index + 1}`,
    major: "Accounting",
    class_year: "Senior",
    marker: "major_only",
    reason: "Same major; nothing else on file.",
    contributing_factor_keys: ["same_major"],
    undecided_goal_half: false,
  }));
}

function list(name: string, prefix: string, count: number): RankedListView {
  return {
    event_key: "northline",
    event_name: "Northline Analytics",
    invite_limit: 30,
    setting_name: name,
    weights: { same_major: 0.6, stated_interest_overlap: 0.15, career_goal_fit: 0.15, past_event_topic_overlap: 0.1 },
    factor_labels: LABELS,
    entries: entries(prefix, count),
    composition: {
      by_major: { dimension: "major", on_list: {}, all_profiles: {} },
      by_class_year: { dimension: "class_year", on_list: {}, all_profiles: {} },
      by_marker: { dimension: "marker", on_list: {}, all_profiles: {} },
      coverage: { missing_majors: [], missing_class_years: [], has_uncovered_group: false },
    },
    unlisted_class_years: [],
    unrankable_profile_count: 0,
  };
}

const COMPARISON: CompareView = {
  a: list("Major first", "A", 30),
  b: list("Interests first", "B", 30),
  on_both_profile_nos: [1],
};

function stubNarrow(narrow: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: narrow && query.includes("max-width: 767px"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<MatchingCompareView /> (§6.12)", () => {
  it("shows both lists as tables at 768 and up, overlap marked in each (§8.7)", () => {
    render(<MatchingCompareView comparison={COMPARISON} onClose={vi.fn()} />);
    expect(screen.getByText("1 name is on both lists, highlighted in each.")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Major first" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Interests first" })).toBeDefined();
    const tables = screen.getAllByRole("table");
    expect(tables).toHaveLength(2);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    for (const table of tables) {
      const heads = within(table).getAllByRole("columnheader").map((head) => head.textContent);
      expect(heads).toEqual(["Rank", "Name", "Major", "Year", "How much we know"]);
      expect(within(table).getAllByRole("row")).toHaveLength(31);
    }
    expect(screen.getAllByText("on both lists")).toHaveLength(2);
  });

  it("closes", () => {
    const onClose = vi.fn();
    render(<MatchingCompareView comparison={COMPARISON} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Close this comparison" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("on 390 shows one list at a time, ten rows first, with a way to see all", () => {
    stubNarrow(true);
    render(<MatchingCompareView comparison={COMPARISON} onClose={vi.fn()} />);
    expect(screen.queryByRole("table")).toBeNull();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Major first", "Interests first"]);
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");

    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getAllByRole("listitem")).toHaveLength(10);
    expect(within(panel).getByText("A person 1")).toBeDefined();
    expect(panel.textContent).toContain("Showing 10 of 30.");

    fireEvent.click(within(panel).getByRole("button", { name: "Show all 30" }));
    expect(within(screen.getByRole("tabpanel")).getAllByRole("listitem")).toHaveLength(30);

    fireEvent.click(tabs[1]);
    const second = screen.getByRole("tabpanel");
    expect(within(second).getByText("B person 1")).toBeDefined();
    expect(screen.getByText("1 name is on both lists, highlighted in each.")).toBeDefined();
  });
});
