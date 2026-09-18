/**
 * Tests for the class exercise's projector-readable results chart.
 *
 * The rules asserted here are the ones a projector makes unarguable: only head
 * counts appear, an unavailable count says so instead of drawing a zero, and
 * nothing at all is drawn from placeholder numbers.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  ExerciseResultsChart,
  type ExerciseResultsSeries,
  formatHeadCount,
  hasDrawableCounts,
} from "./ExerciseResultsChart";

afterEach(cleanup);

const teamPanel: ExerciseResultsSeries = {
  label: "Your list",
  invited: 40,
  signedUp: 18,
  attended: 12,
};

const everyonePanel: ExerciseResultsSeries = {
  label: "Email everyone",
  invited: 300,
  signedUp: 25,
  attended: 15,
};

describe("hasDrawableCounts", () => {
  it("is false for no panels at all", () => {
    expect(hasDrawableCounts([])).toBe(false);
  });

  it("is false when every count in every panel is unavailable", () => {
    expect(
      hasDrawableCounts([
        { label: "Your list", invited: null, signedUp: null, attended: null },
        { label: "Email everyone", invited: null, signedUp: null, attended: null },
      ]),
    ).toBe(false);
  });

  it("is true for a counted zero, which is not the same as no data", () => {
    expect(
      hasDrawableCounts([{ label: "Your list", invited: 0, signedUp: 0, attended: 0 }]),
    ).toBe(true);
  });
});

describe("formatHeadCount", () => {
  it("prints a counted zero as 0", () => {
    expect(formatHeadCount(0)).toBe("0");
  });

  it("prints an absent count in words, never as a number", () => {
    expect(formatHeadCount(null)).toBe("not available");
  });
});

describe("<ExerciseResultsChart /> with nothing to draw", () => {
  it("shows an honest empty state instead of a chart when there are no panels", () => {
    render(<ExerciseResultsChart title="Results" series={[]} />);

    expect(screen.getByTestId("exercise-results-chart-empty")).toBeTruthy();
    expect(screen.queryByTestId("exercise-results-chart")).toBeNull();
    expect(document.querySelector("svg")).toBeNull();
  });

  it("draws nothing when every count is unavailable, rather than inventing bars", () => {
    render(
      <ExerciseResultsChart
        title="Results"
        series={[{ label: "Your list", invited: null, signedUp: null, attended: null }]}
      />,
    );

    expect(screen.getByTestId("exercise-results-chart-empty")).toBeTruthy();
    expect(screen.queryByTestId("exercise-results-table")).toBeNull();
  });

  it("uses the caller's empty message when it has one", () => {
    render(
      <ExerciseResultsChart
        title="Results"
        series={[]}
        emptyMessage="The instructor has not unlocked results for this event."
      />,
    );

    expect(
      screen.getByText("The instructor has not unlocked results for this event."),
    ).toBeTruthy();
  });
});

/**
 * Every place the title could reach a screen reader.
 *
 * An accessible name arrives either as an `aria-label`, as the text of a node
 * that names something else (a heading referenced through `aria-labelledby`),
 * or as the text of a naming element — an SVG `<title>`, a `<figcaption>`, a
 * table `<caption>`. Counting all three is how a test notices the title being
 * announced more than once; counting only roles would miss a duplicate that
 * merely repeats the words.
 */
function titleAnnouncements(container: HTMLElement, title: string): readonly string[] {
  const labels = Array.from(container.querySelectorAll("[aria-label]"))
    .filter((node) => node.getAttribute("aria-label") === title)
    .map((node) => `aria-label on <${node.tagName.toLowerCase()}>`);

  const namingElements = Array.from(container.querySelectorAll("caption, figcaption, title"))
    .filter((node) => (node.textContent ?? "").includes(title))
    .map((node) => `<${node.tagName.toLowerCase()}> text`);

  const textNodes = Array.from(container.querySelectorAll("h1, h2, h3, h4, h5, h6, p, span"))
    .filter((node) => (node.textContent ?? "").trim() === title)
    .map((node) => `<${node.tagName.toLowerCase()}> text`);

  return [...labels, ...namingElements, ...textNodes];
}

describe("<ExerciseResultsChart /> accessible name", () => {
  it("announces the title exactly once", () => {
    const { container } = render(
      <ExerciseResultsChart title="Northline results" series={[teamPanel]} />,
    );

    expect(titleAnnouncements(container, "Northline results")).toEqual(["<h2> text"]);
  });

  it("gives the chart graphic exactly one accessible name, and it is the title", () => {
    render(<ExerciseResultsChart title="Northline results" series={[teamPanel]} />);

    expect(screen.getAllByRole("img", { name: "Northline results" })).toHaveLength(1);
    expect(screen.queryAllByRole("region", { name: "Northline results" })).toHaveLength(0);
  });

  it("announces the title exactly once in the empty state too", () => {
    const { container } = render(<ExerciseResultsChart title="Northline results" series={[]} />);

    expect(titleAnnouncements(container, "Northline results")).toEqual(["<h2> text"]);
  });

  it("keeps every count reachable, so nothing is hidden from assistive tech", () => {
    render(<ExerciseResultsChart title="Northline results" series={[teamPanel]} />);

    const table = screen.getByTestId("exercise-results-table");
    expect(table.closest("[aria-hidden='true']")).toBeNull();
    expect(within(table).getByRole("row", { name: /Your list/ })).toBeTruthy();
  });
});

describe("<ExerciseResultsChart /> with counts", () => {
  it("names the chart accessibly", () => {
    render(<ExerciseResultsChart title="Northline results" series={[teamPanel]} />);

    expect(screen.getByRole("img", { name: "Northline results" })).toBeTruthy();
  });

  it("repeats every count in a real table, so the chart is not colour-only", () => {
    render(<ExerciseResultsChart title="Results" series={[teamPanel, everyonePanel]} />);

    const table = screen.getByTestId("exercise-results-table");
    const teamRow = within(table).getByRole("row", { name: /Your list/ });
    expect(within(teamRow).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "40",
      "18",
      "12",
    ]);

    const everyoneRow = within(table).getByRole("row", { name: /Email everyone/ });
    expect(within(everyoneRow).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "300",
      "25",
      "15",
    ]);
  });

  it("labels each stage in words as well as by fill", () => {
    render(<ExerciseResultsChart title="Results" series={[teamPanel]} />);

    const table = screen.getByTestId("exercise-results-table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Panel",
      "Invited",
      "Signed up",
      "Attended",
    ]);
  });

  it("says 'not available' for a missing count and never renders it as 0", () => {
    render(
      <ExerciseResultsChart
        title="Results"
        series={[{ label: "Round one", invited: 40, signedUp: null, attended: null }]}
      />,
    );

    const row = within(screen.getByTestId("exercise-results-table")).getByRole("row", {
      name: /Round one/,
    });
    expect(within(row).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "40",
      "not available",
      "not available",
    ]);

    const note = screen.getByTestId("exercise-results-unavailable");
    expect(note.textContent).toContain("Round one: signed up not available");
    expect(note.textContent).toContain("Round one: attended not available");
  });

  it("draws a counted zero as a zero, not as missing data", () => {
    render(
      <ExerciseResultsChart
        title="Results"
        series={[{ label: "Your list", invited: 40, signedUp: 0, attended: 0 }]}
      />,
    );

    const row = within(screen.getByTestId("exercise-results-table")).getByRole("row", {
      name: /Your list/,
    });
    expect(within(row).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "40",
      "0",
      "0",
    ]);
    expect(screen.queryByTestId("exercise-results-unavailable")).toBeNull();
  });

  it("shows no percentage, rate, score, or confidence anywhere on the surface", () => {
    const { container } = render(
      <ExerciseResultsChart
        title="Results"
        series={[teamPanel, everyonePanel]}
        caption="Northline, round one. 37 seats still empty."
      />,
    );

    const text = container.textContent ?? "";
    expect(text).not.toContain("%");
    expect(text).not.toMatch(/percent|rate|score|confidence|match strength/i);
  });

  it("carries the caller's caption", () => {
    render(
      <ExerciseResultsChart
        title="Results"
        series={[teamPanel]}
        caption="Northline, round one. 37 seats still empty."
      />,
    );

    expect(screen.getByText("Northline, round one. 37 seats still empty.")).toBeTruthy();
  });
});
