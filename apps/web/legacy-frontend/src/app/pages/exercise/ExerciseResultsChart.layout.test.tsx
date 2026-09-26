/**
 * The results chart on a phone, and the table beside it (M2 B2 and B6).
 *
 * B2: the chart is drawn at a fixed 880px, which made the whole page 904px
 * wide on a 390px phone. The chart now sits in its own horizontal scroller, so
 * the page keeps the phone's width and only the chart scrolls; the table below
 * repeats every count for anyone who does not.
 *
 * B6: the fallback table had no cell padding, so its numbers ran together.
 * Every header and cell now has `px-3 py-1` and is left-aligned.
 *
 * jsdom does no layout, so these pin the classes that do the work rather than
 * measured widths.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ExerciseResultsChart } from "./ExerciseResultsChart";

const series = [
  { label: "Your team's list", invited: 30, signedUp: 8, attended: 6 },
  { label: "If you emailed everyone", invited: 300, signedUp: 46, attended: 30 },
];

afterEach(cleanup);

describe("<ExerciseResultsChart /> on a narrow screen", () => {
  it("puts the fixed-width chart in its own horizontal scroller", () => {
    render(<ExerciseResultsChart title="Northline results" series={series} />);

    const chart = screen.getByRole("img", { name: "Northline results" });
    const scroller = screen.getByTestId("exercise-results-chart-scroll");
    expect(scroller.contains(chart)).toBe(true);
    expect(scroller.className).toContain("overflow-x-auto");
    expect(scroller.className).toContain("max-w-full");
  });

  it("keeps the section itself from growing past its container", () => {
    render(<ExerciseResultsChart title="Northline results" series={series} />);

    const section = screen.getByTestId("exercise-results-chart");
    expect(section.className).toContain("min-w-0");
    expect(section.className).toContain("max-w-full");
  });

  it("gives the table its own scroller too, so a long label cannot widen the page", () => {
    render(<ExerciseResultsChart title="Northline results" series={series} />);

    const table = screen.getByTestId("exercise-results-table");
    expect(table.parentElement?.className).toContain("overflow-x-auto");
  });
});

describe("<ExerciseResultsChart /> fallback table", () => {
  it("pads and left-aligns every header and cell", () => {
    render(<ExerciseResultsChart title="Northline results" series={series} />);

    const table = screen.getByTestId("exercise-results-table");
    const cells = Array.from(table.querySelectorAll("th, td"));
    expect(cells.length).toBe(3 * 4);
    for (const cell of cells) {
      expect(cell.className).toContain("px-3");
      expect(cell.className).toContain("py-1");
      expect(cell.className).toContain("text-left");
    }
  });

  it("still carries every count", () => {
    render(<ExerciseResultsChart title="Northline results" series={series} />);

    const row = within(screen.getByTestId("exercise-results-table")).getByRole("row", {
      name: /emailed everyone/,
    });
    expect(row.textContent).toContain("300");
    expect(row.textContent).toContain("46");
    expect(row.textContent).toContain("30");
  });
});
