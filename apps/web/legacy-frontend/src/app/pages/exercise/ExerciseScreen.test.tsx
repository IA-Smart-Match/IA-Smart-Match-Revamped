import { cleanup, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import {
  EXERCISE_RIBBON_LABEL,
  EXERCISE_SYNTHETIC_REASON,
  ExerciseLoading,
  ExerciseNotice,
  ExerciseScreen,
} from "./ExerciseScreen";

afterEach(cleanup);

describe("ExerciseScreen (§6.1)", () => {
  it("wraps the screen in the exercise token scope", () => {
    const { container } = render(<ExerciseScreen title="Choose an event">body</ExerciseScreen>);
    expect(container.querySelector(".ce-root")).not.toBeNull();
  });

  it("shows the quiet fictional-data ribbon with the owner's prefix (ruling 1)", () => {
    render(<ExerciseScreen title="Choose an event">body</ExerciseScreen>);
    expect(EXERCISE_RIBBON_LABEL).toBe("Fictional data —");
    const ribbon = document.querySelector('[data-slot="synthetic-data-banner"]') as HTMLElement;
    expect(ribbon.dataset.tone).toBe("quiet");
    expect(ribbon.textContent).toBe(`Fictional data — ${EXERCISE_SYNTHETIC_REASON}`);
  });

  it("has exactly one h1, the lead line and the aside", () => {
    render(
      <ExerciseScreen title="Results" intro="What happened for this event." aside="Team 4">
        body
      </ExerciseScreen>,
    );
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Results");
    expect(screen.getByText("What happened for this event.")).toBeDefined();
    expect(screen.getByText("Team 4")).toBeDefined();
  });

  it("shows the CPP logo in the header", () => {
    render(<ExerciseScreen title="Results">body</ExerciseScreen>);
    expect(screen.getByRole("img", { name: "Cal Poly Pomona" })).toBeDefined();
  });

  it("moves focus to the h1 when nothing else holds it (route change, §8.5)", () => {
    render(<ExerciseScreen title="Results">body</ExerciseScreen>);
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 }));
  });

  it("never describes the data as real students or respondents", () => {
    const { container } = render(<ExerciseScreen title="Results">body</ExerciseScreen>);
    expect(container.textContent).not.toMatch(/real student|respondent|OQ-CE-/i);
  });
});

describe("ExerciseNotice", () => {
  it("renders the server sentence verbatim as a status, with its action", () => {
    render(
      <ExerciseNotice message="The instructor has not opened results for this event yet.">
        <button type="button">Check again</button>
      </ExerciseNotice>,
    );
    const notice = screen.getByRole("status");
    expect(notice.dataset.slot).toBe("exercise-notice");
    expect(notice.textContent).toContain("The instructor has not opened results for this event yet.");
    expect(screen.getByRole("button", { name: "Check again" })).toBeDefined();
  });

  it("keeps the problem tone for transport failures", () => {
    render(<ExerciseNotice tone="problem" message="The exercise could not be reached." />);
    expect(screen.getByRole("status").dataset.tone).toBe("problem");
  });
});

describe("ExerciseLoading", () => {
  it("states what is loading", () => {
    render(<ExerciseLoading what="the list" />);
    expect(screen.getByRole("status").textContent).toBe("Loading the list…");
  });
});
