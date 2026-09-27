/**
 * The ranked row with its reason line (DESIGN.md §6.7), the marker chip
 * (§6.8), and the 390 card view (§8.7).
 *
 * `RankedList.test.tsx` and `RankedList.undecidedLabel.test.tsx` pin the
 * words; this file pins where they sit: the reason under the name with no
 * "Why" column, the chip's icon and words, the overlap wash and chip, a
 * name new to the list, and the `<ol>` of cards on a phone.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ListEntryView } from "../../../lib/exerciseClient";
import { RankedList } from "./RankedList";

const LABELS = { same_major: "same major", career_goal_fit: "career goal fits this event" };

function entry(rank: number, profileNo: number, name: string): ListEntryView {
  return {
    rank,
    profile_no: profileNo,
    display_name: name,
    major: "Accounting",
    class_year: "Senior",
    marker: rank === 1 ? "completed_card" : "major_only",
    reason: `What counted: same major (${name}).`,
    contributing_factor_keys: ["same_major"],
    undecided_goal_half: false,
  };
}

const ENTRIES = [entry(1, 7, "Maya Tran"), entry(2, 9, "Daniel Okafor")];

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

describe("<RankedList /> on desktop (§6.7)", () => {
  it("puts the reason line under the name and has no Why column", () => {
    render(<RankedList entries={ENTRIES} factorLabels={LABELS} caption="List" />);
    const heads = screen.getAllByRole("columnheader").map((head) => head.textContent);
    expect(heads).toEqual(["Rank", "Name", "Major", "Year", "How much we know"]);
    const nameCell = screen.getByText("Maya Tran").closest("td") as HTMLElement;
    expect(within(nameCell).getByText("What counted: same major (Maya Tran).")).toBeDefined();
  });

  it("shows how much we know as a chip with icon and words", () => {
    render(<RankedList entries={ENTRIES} factorLabels={LABELS} caption="List" />);
    const chips = document.querySelectorAll('[data-slot="ce-marker-chip"]');
    expect(chips).toHaveLength(2);
    expect(chips[0].textContent).toBe("completed card");
    expect(chips[0].querySelector("svg")).not.toBeNull();
  });

  it("marks a name on both lists with a wash and a chip", () => {
    render(
      <RankedList
        entries={ENTRIES}
        factorLabels={LABELS}
        caption="List"
        highlightProfileNos={[9]}
      />,
    );
    const row = screen.getByText("Daniel Okafor").closest("tr") as HTMLElement;
    expect(row.getAttribute("data-on-both")).toBe("true");
    expect(within(row).getByText("on both lists")).toBeDefined();
    const other = screen.getByText("Maya Tran").closest("tr") as HTMLElement;
    expect(within(other).queryByText("on both lists")).toBeNull();
  });

  it("washes a name that has just joined the list, and not on first load", () => {
    const { rerender } = render(
      <RankedList entries={ENTRIES} factorLabels={LABELS} caption="List" />,
    );
    expect(document.querySelector(".ce-row-join")).toBeNull();

    rerender(
      <RankedList
        entries={[ENTRIES[0], entry(2, 11, "Priya Patel")]}
        factorLabels={LABELS}
        caption="List"
      />,
    );
    const joined = screen.getByText("Priya Patel").closest("tr") as HTMLElement;
    expect(joined.className).toContain("ce-row-join");
    const stayed = screen.getByText("Maya Tran").closest("tr") as HTMLElement;
    expect(stayed.className).not.toContain("ce-row-join");
  });

  it("gives the marker chip the widest data column so it wraps to two lines at most", () => {
    render(<RankedList entries={ENTRIES} factorLabels={LABELS} caption="List" />);
    const heads = screen.getAllByRole("columnheader");
    const width = (index: number) => Number(/w-\[(\d+)%\]/.exec(heads[index].className)?.[1]);
    // Major and How much we know take shares; the marker is the wider one.
    expect(width(4)).toBeGreaterThanOrEqual(27);
    expect(width(4)).toBeGreaterThan(width(2));
  });

  it("gives Name the room left over: Year a fixed width, Major 20% (#251 review)", () => {
    render(<RankedList entries={ENTRIES} factorLabels={LABELS} caption="List" />);
    const heads = screen.getAllByRole("columnheader");
    // Name takes no width class, so it gets everything the others leave.
    expect(heads[1].className).not.toMatch(/\bw-/);
    // 20%, not the review's 18%: at 1280 "International" is 127px and 18%
    // leaves it 114px, so it ran into the Year column.
    expect(heads[2].className).toContain("w-[20%]");
    // Year holds one short word ("Sophomore"): a fixed width, not a share.
    expect(heads[3].className).toMatch(/w-\[[\d.]+rem\]/);
  });

  it("says so when nobody is on the list", () => {
    render(<RankedList entries={[]} factorLabels={LABELS} caption="List" />);
    expect(
      screen.getByText(
        "Nobody is on this list. Nobody in this data file can be ranked for this event with these weights.",
      ),
    ).toBeDefined();
  });
});

describe("<RankedList /> on 390 (§8.7)", () => {
  it("becomes an ordered list of cards with the same content", () => {
    stubNarrow(true);
    render(<RankedList entries={ENTRIES} factorLabels={LABELS} caption="List" />);
    expect(document.querySelector("table")).toBeNull();
    const list = screen.getByRole("list", { name: "List" });
    expect(list.tagName).toBe("OL");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const first = items[0];
    expect(within(first).getByText("Maya Tran")).toBeDefined();
    expect(within(first).getByText("What counted: same major (Maya Tran).")).toBeDefined();
    expect(first.textContent).toContain("Accounting");
    expect(first.textContent).toContain("Senior");
    expect(first.querySelector('[data-slot="ce-marker-chip"]')).not.toBeNull();
  });

  it("keeps a two-digit rank apart from the name", () => {
    stubNarrow(true);
    render(<RankedList entries={[entry(10, 40, "Nina Vasquez")]} factorLabels={LABELS} caption="List" />);
    const rank = document.querySelector('[data-slot="exercise-rank"]') as HTMLElement;
    expect(rank.textContent).toBe("10");
    // Wide enough for "10" in the rank face, never shrunk, plus the row gap.
    expect(rank.className).toContain("min-w-12");
    expect(rank.className).toContain("shrink-0");
    expect(rank.parentElement?.className).toContain("gap-ce-3");
  });
});
