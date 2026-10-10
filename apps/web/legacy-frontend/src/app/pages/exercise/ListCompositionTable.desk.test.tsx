/**
 * "Who is on the list" (DESIGN.md §6.9, §7.4) and its coverage line (§6.10).
 *
 * Three small tables side by side on desktop; three disclosures on 390, each
 * table still scrolling in its own box. A group with nobody on the list shows
 * a real 0 in ink. The coverage line appears only when a group is missing.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ListCompositionView } from "../../../lib/exerciseClient";
import { ListCompositionTable } from "./ListCompositionTable";

const COMPOSITION: ListCompositionView = {
  by_major: {
    dimension: "major",
    on_list: { Accounting: 4 },
    all_profiles: { Accounting: 40, Finance: 30 },
  },
  by_class_year: { dimension: "class_year", on_list: { Senior: 4 }, all_profiles: { Senior: 70 } },
  by_marker: {
    dimension: "marker",
    on_list: { completed_card: 4 },
    all_profiles: { completed_card: 20, major_only: 50 },
  },
  coverage: { missing_majors: ["Finance"], missing_class_years: [], has_uncovered_group: true },
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

function renderTable() {
  return render(
    <ListCompositionTable
      composition={COMPOSITION}
      unrankableProfileCount={0}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ListCompositionTable /> (§6.9)", () => {
  it("lays the three tables side by side on desktop, with no disclosures", () => {
    renderTable();
    expect(screen.getAllByRole("table")).toHaveLength(3);
    expect(document.querySelector("details")).toBeNull();
    const grid = document.querySelector('[data-slot="exercise-composition-grid"]');
    expect(grid?.className).toContain("lg:grid-cols-3");
  });

  it("keeps class years in the order the server sent, not alphabetical", () => {
    const { container } = render(
      <ListCompositionTable
        composition={{
          ...COMPOSITION,
          by_class_year: {
            dimension: "class_year",
            on_list: { Freshman: 1 },
            all_profiles: { Freshman: 5, Sophomore: 4, Junior: 3, Senior: 2 },
          },
        }}
        unrankableProfileCount={0}
      />,
    );
    const table = container.querySelectorAll("table")[1] as HTMLElement;
    expect(within(table).getAllByRole("rowheader").map((r) => r.textContent)).toEqual([
      "Freshman",
      "Sophomore",
      "Junior",
      "Senior",
    ]);
  });

  it("shows a group with nobody on the list as 0, right-aligned in tabular numerals", () => {
    renderTable();
    const row = screen.getByRole("rowheader", { name: "Finance" }).closest("tr") as HTMLElement;
    const cells = within(row).getAllByRole("cell");
    expect(cells.map((cell) => cell.textContent)).toEqual(["0", "30"]);
    for (const cell of cells) {
      expect(cell.className).toContain("text-right");
      expect(cell.className).toContain("ce-tabular");
      expect(cell.className).not.toContain("muted");
    }
  });

  it("folds each table into a disclosure on 390, each still in its own scroll box", () => {
    stubNarrow(true);
    renderTable();
    const summaries = [...document.querySelectorAll("details > summary")].map(
      (summary) => summary.textContent,
    );
    expect(summaries).toEqual(["By major", "By year", "By how much we know"]);
    for (const table of document.querySelectorAll("table")) {
      expect(table.parentElement?.className).toContain("overflow-x-auto");
    }
  });

  it("shows the coverage line with its icon on the gold wash", () => {
    renderTable();
    const notice = document.querySelector('[data-slot="exercise-list-coverage-notice"]');
    expect(notice?.textContent).toBe("Nobody on this list is a Finance major.");
    expect(notice?.className).toContain("bg-ce-gold-tint");
    expect(notice?.querySelector("svg")).not.toBeNull();
  });
});
