/**
 * The results chart's `variant="exercise"` (DESIGN.md §6.16, ruling 5).
 *
 * A variant, not a copy: the same component, the same data, the same fixed
 * 880×460 chart in the same scroll box. The question to Ann about whether the
 * team's bars should share a scale with the 300 bars is still open, so the
 * variant changes only the look: §3.3 series (open / hatched / solid), token
 * colours, desk type, and the table behind a "Show these counts as a table"
 * disclosure that is open by default on a phone.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseResultsChart } from "./ExerciseResultsChart";

const series = [
  { label: "Your team's list", invited: 30, signedUp: 6, attended: 4 },
  { label: "If you emailed everyone", invited: 300, signedUp: 41, attended: 27 },
];

function stubWidth(narrow: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: narrow && query.includes("max-width"),
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

describe('<ExerciseResultsChart variant="exercise" />', () => {
  it("marks itself as the exercise variant and keeps the default untouched", () => {
    const { unmount } = render(<ExerciseResultsChart title="Northline" series={series} />);
    expect(screen.getByTestId("exercise-results-chart").getAttribute("data-variant")).toBe(
      "default",
    );
    expect(document.querySelector("details")).toBeNull();
    unmount();

    render(<ExerciseResultsChart title="Northline" series={series} variant="exercise" />);
    expect(screen.getByTestId("exercise-results-chart").getAttribute("data-variant")).toBe(
      "exercise",
    );
  });

  it("keeps the chart at the same fixed size inside the same scroll box", () => {
    render(<ExerciseResultsChart title="Northline" series={series} variant="exercise" />);

    const scroller = screen.getByTestId("exercise-results-chart-scroll");
    const chart = screen.getByRole("img", { name: "Northline" });
    expect(scroller.contains(chart)).toBe(true);
    expect(scroller.className).toContain("overflow-x-auto");
    expect(scroller.getAttribute("tabindex")).toBe("0");
    const svg = scroller.querySelector("svg.recharts-surface");
    expect(svg?.getAttribute("width")).toBe("880");
    expect(svg?.getAttribute("height")).toBe("460");
  });

  it("draws the three series from the desk's chart tokens, not the old hues", () => {
    const { container } = render(
      <ExerciseResultsChart title="Northline" series={series} variant="exercise" />,
    );

    const html = container.innerHTML;
    expect(html).toContain("var(--ce-series-invited-fill)");
    expect(html).toContain("var(--ce-series-signed-fill)");
    expect(html).toContain("var(--ce-series-attended-fill)");
    for (const oldHue of ["#1f3a93", "#0b6b53", "#8a3b00"]) {
      expect(html).not.toContain(oldHue);
    }
  });

  it("puts the table under a 'Show these counts as a table' disclosure, closed on desktop", () => {
    stubWidth(false);
    render(<ExerciseResultsChart title="Northline" series={series} variant="exercise" />);

    const table = screen.getByTestId("exercise-results-table");
    const details = table.closest("details");
    expect(details).not.toBeNull();
    expect(within(details as HTMLElement).getByText("Show these counts as a table").tagName).toBe(
      "SUMMARY",
    );
    expect((details as HTMLDetailsElement).open).toBe(false);
  });

  it("opens the table disclosure by default on a phone", () => {
    stubWidth(true);
    render(<ExerciseResultsChart title="Northline" series={series} variant="exercise" />);

    const details = screen.getByTestId("exercise-results-table").closest("details");
    expect((details as HTMLDetailsElement).open).toBe(true);
  });

  it("still carries every count in the table", () => {
    render(<ExerciseResultsChart title="Northline" series={series} variant="exercise" />);

    const row = within(screen.getByTestId("exercise-results-table")).getByRole("row", {
      name: /emailed everyone/,
    });
    expect(within(row).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "300",
      "41",
      "27",
    ]);
  });

  it("styles the empty state in the desk's type too, with the title once", () => {
    render(<ExerciseResultsChart title="Northline" series={[]} variant="exercise" />);

    const heading = screen.getByRole("heading", { name: "Northline" });
    expect(heading.className).toContain("ce-type-h2");
  });
});
