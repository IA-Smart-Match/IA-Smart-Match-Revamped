/**
 * The results reveal (DESIGN.md §6.15, §5.1 `ce-seat-fill`, §7.8, §7.10).
 *
 * The seating chart is decoration (`aria-hidden`); the D8 sentence and the
 * figures band carry the numbers. Seat kinds come straight from the response:
 * `existing_signups` taken, the team panel's `attended_count` added (the same
 * number D8's sentence says, and the one `seats_empty` is computed from), the
 * rest open. The client never subtracts.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ResultPanelView, ResultsView } from "../../../lib/exerciseClient";
import { stubReducedMotion } from "./desk/testMatchMedia";
import { ResultPanels } from "./ResultPanels";

function panel(invited: number, signedUp: number, attended: number): ResultPanelView {
  return {
    invited_profile_nos: Array.from({ length: invited }, (_, index) => index + 1),
    signed_up_profile_nos: Array.from({ length: signedUp }, (_, index) => index + 1),
    attended_profile_nos: Array.from({ length: attended }, (_, index) => index + 1),
    invited_count: invited,
    signed_up_count: signedUp,
    attended_count: attended,
  };
}

function results(overrides: Partial<ResultsView> = {}): ResultsView {
  return {
    event_key: "E11",
    event_name: "Northline Analytics",
    round: 1,
    setting_name: "Wide net",
    team: panel(30, 8, 6),
    email_everyone: panel(300, 40, 30),
    seats_empty: 46,
    event_seats: 60,
    existing_signups: 8,
    round_one: null,
    created_at: "2026-09-25T10:00:00Z",
    ...overrides,
  };
}

function seats(kind: string): number {
  return document.querySelectorAll(`[data-slot="ce-seat"][data-kind="${kind}"]`).length;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ResultPanels seating chart", () => {
  it("draws one seat per seat in the room, split as the response says", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    expect(seats("taken")).toBe(8);
    expect(seats("added")).toBe(6);
    expect(seats("open")).toBe(46);
  });

  it("hides the chart from assistive tech and keeps the sentence readable", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    const room = document.querySelector('[data-slot="exercise-room"]');
    expect(room?.getAttribute("aria-hidden")).toBe("true");
    const sentence = document.querySelector('[data-slot="exercise-seats-sentence"]');
    expect(sentence?.closest("[aria-hidden='true']")).toBeNull();
  });

  it("labels the room and its legend in §11.1's words", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    const room = document.querySelector('[data-slot="exercise-room"]')?.textContent ?? "";
    for (const words of ["The room", "Front of the room", "Already coming", "Your invitations", "Still open"]) {
      expect(room).toContain(words);
    }
  });

  it("sets the sentence's numerals apart without changing its words", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    const sentence = document.querySelector('[data-slot="exercise-seats-sentence"]');
    expect(sentence?.textContent).toBe(
      "8 were already coming. Your invitations added 6. 46 seats are still open.",
    );
    const numerals = Array.from(sentence?.querySelectorAll("[data-numeral]") ?? []).map(
      (node) => node.textContent,
    );
    expect(numerals).toEqual(["8", "6", "46"]);
  });

  it("shows the ruled figures band with §11.1's three labels", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    const band = document.querySelector('[data-slot="exercise-seats"]');
    const labels = Array.from(band?.querySelectorAll("dt") ?? []).map((node) => node.textContent);
    expect(labels).toEqual(["Seats in the room", "Already coming", "Still open"]);
    const values = Array.from(band?.querySelectorAll("dd") ?? []).map((node) => node.textContent);
    expect(values).toEqual(["60", "8", "46"]);
  });

  it("shows the final state at once on a later visit, with nothing animating", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    expect(document.querySelectorAll('[data-slot="ce-seat"][data-animate="true"]').length).toBe(0);
    expect(document.querySelector('[data-slot="exercise-seats-announce"]')).toBeNull();
  });
});

describe("ResultPanels reveal after a run", () => {
  it("fills the seats in order and announces the sentence once, at the end", () => {
    stubReducedMotion(false);
    vi.useFakeTimers();
    render(<ResultPanels results={results()} names={new Map()} reveal />);

    expect(document.querySelectorAll('[data-slot="ce-seat"][data-animate="true"]').length).toBe(60);
    const live = document.querySelector('[data-slot="exercise-seats-announce"]');
    expect(live?.getAttribute("aria-live")).toBe("polite");
    expect(live?.textContent).toBe("");

    act(() => {
      vi.advanceTimersByTime(1800);
    });

    expect(live?.textContent).toBe(
      "8 were already coming. Your invitations added 6. 46 seats are still open.",
    );
  });

  it("with reduced motion, shows the final state and announces at once", () => {
    stubReducedMotion(true);
    render(<ResultPanels results={results()} names={new Map()} reveal />);

    expect(document.querySelectorAll('[data-slot="ce-seat"][data-animate="true"]').length).toBe(0);
    expect(
      document.querySelector('[data-slot="exercise-seats-announce"]')?.textContent,
    ).toBe("8 were already coming. Your invitations added 6. 46 seats are still open.");
    expect(document.querySelector('[data-slot="exercise-seats"]')?.textContent).toContain("46");
  });
});

describe("ResultPanels chart and people", () => {
  it("draws the chart as the exercise variant", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    expect(screen.getByTestId("exercise-results-chart").getAttribute("data-variant")).toBe(
      "exercise",
    );
  });

  it("shows each group of people as chips, and 'Nobody.' when a group is empty", () => {
    render(
      <ResultPanels
        results={results({ team: panel(2, 0, 0) })}
        names={new Map([[1, "Avery Example"]])}
      />,
    );

    const people = document.querySelector('[data-slot="exercise-team-people"]');
    const chips = Array.from(people?.querySelectorAll('[data-slot="exercise-person-chip"]') ?? []);
    expect(chips.map((chip) => chip.textContent)).toEqual(["Avery Example", "Profile 2"]);
    expect(people?.textContent).toContain("Signed up (0)");
    expect(people?.textContent).toContain("Nobody.");
  });

  it("marks round two with the round-journey strip", () => {
    render(
      <ResultPanels
        results={results({
          round: 2,
          round_one: {
            event_key: "E10",
            round: 1,
            setting_name: "First try",
            team: panel(30, 2, 1),
            seats_empty: 51,
            created_at: "2026-09-25T09:00:00Z",
          },
        })}
        names={new Map()}
      />,
    );

    expect(document.querySelector('[data-slot="exercise-round-journey"]')).not.toBeNull();
  });

  it("draws no round-journey strip in round one", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    expect(document.querySelector('[data-slot="exercise-round-journey"]')).toBeNull();
  });
});
