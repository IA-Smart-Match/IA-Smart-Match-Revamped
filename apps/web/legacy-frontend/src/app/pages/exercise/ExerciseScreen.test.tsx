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
  it("names the tab '<title> · Smart Match' and restores it on unmount (#267)", () => {
    document.title = "before";
    const { unmount } = render(<ExerciseScreen title="Results">body</ExerciseScreen>);
    expect(document.title).toBe("Results · Smart Match");
    unmount();
    expect(document.title).toBe("before");
  });

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

  it("wraps the shared logo in the exercise's own plate, so dark mode can light it", () => {
    render(<ExerciseScreen title="Results">body</ExerciseScreen>);
    const logo = screen.getByRole("img", { name: "Cal Poly Pomona" });
    const plate = logo.closest('[data-slot="ce-logo"]');
    expect(plate).not.toBeNull();
    expect(plate?.className).toContain("ce-logo");
    // The shared BrandLogo is untouched: the plate is the shell's wrapper.
    expect(plate?.contains(logo)).toBe(true);
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
      <ExerciseNotice message="Results for Harbor are not open yet. Ask your instructor.">
        <button type="button">Check again</button>
      </ExerciseNotice>,
    );
    const notice = screen.getByRole("status");
    expect(notice.dataset.slot).toBe("exercise-notice");
    expect(notice.textContent).toContain("Results for Harbor are not open yet. Ask your instructor.");
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

describe("ExerciseScreen soft-studio header", () => {
  function at(path: string) {
    window.history.pushState({}, "", path);
  }

  afterEach(() => {
    at("/");
  });

  it.each(["/exercise", "/exercise/events", "/exercise/events/northline", "/exercise/events/northline/results", "/exercise/asking"])(
    "gives the student screen %s the step deck, the tour button and the band's logo",
    (path) => {
      at(path);
      render(<ExerciseScreen title="Results">body</ExerciseScreen>);
      expect(screen.getByRole("navigation", { name: "Exercise steps" })).toBeDefined();
      expect(screen.getByRole("button", { name: "Replay the exercise tour" })).toBeDefined();
      expect(screen.getAllByRole("img", { name: "Cal Poly Pomona" })).toHaveLength(1);
    },
  );

  it.each(["/exercise/instructor", "/exercise/profile-card"])(
    "keeps %s, which the instructor projects, free of the deck and tour but with the logo",
    (path) => {
      at(path);
      render(<ExerciseScreen title="Results">body</ExerciseScreen>);
      expect(screen.queryByRole("navigation", { name: "Exercise steps" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Replay the exercise tour" })).toBeNull();
      expect(screen.getAllByRole("img", { name: "Cal Poly Pomona" })).toHaveLength(1);
    },
  );

  it("puts the walking mascot inside the active step, so it stands over it", () => {
    at("/exercise/events");
    render(<ExerciseScreen title="Choose an event">body</ExerciseScreen>);
    const active = document.querySelector('[aria-current="step"]') as HTMLElement;
    expect(active.textContent).toContain("Event");
    expect(active.querySelector(".soft-studio-walker")).not.toBeNull();
    expect(document.querySelectorAll(".soft-studio-walker")).toHaveLength(1);
  });
});
