/**
 * Empty seats, said as both groups (wave-2 decision D8, Chau approved).
 *
 * The class case has 60 seats and 8 existing sign-ups. A bare "46 seats still
 * empty" hides what the team's list changed, so the screen says it in words:
 * "8 were already coming. Your invitations added 6. 46 seats are still open."
 * Every number comes from the API response — `existing_signups`, the team
 * panel's `attended_count`, `seats_empty` — never from a constant here.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ResultPanelView, ResultsView } from "../../../lib/exerciseClient";
import { ResultPanels, seatsSentence } from "./ResultPanels";

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

function slotText(slot: string): string {
  return document.querySelector(`[data-slot="${slot}"]`)?.textContent ?? "";
}

afterEach(cleanup);

describe("seatsSentence", () => {
  it("says D8's example sentence for the class case", () => {
    expect(seatsSentence({ alreadyComing: 8, added: 6, open: 46 }, "now")).toBe(
      "8 were already coming. Your invitations added 6. 46 seats are still open.",
    );
  });

  it("speaks of a finished round in the past tense", () => {
    expect(seatsSentence({ alreadyComing: 8, added: 1, open: 51 }, "then")).toBe(
      "8 were already coming. Your invitations added 1. 51 seats were still open.",
    );
  });

  it("uses the singular for one person and one seat", () => {
    expect(seatsSentence({ alreadyComing: 1, added: 1, open: 1 }, "now")).toBe(
      "1 was already coming. Your invitations added 1. 1 seat is still open.",
    );
  });

  it("says plainly when nobody was already coming", () => {
    expect(seatsSentence({ alreadyComing: 0, added: 6, open: 54 }, "now")).toBe(
      "Nobody was already coming. Your invitations added 6. 54 seats are still open.",
    );
  });

  it("says plainly when the invitations added nobody", () => {
    expect(seatsSentence({ alreadyComing: 8, added: 0, open: 52 }, "now")).toBe(
      "8 were already coming. Your invitations added nobody. 52 seats are still open.",
    );
  });

  it("says the room is full rather than 0 seats open", () => {
    expect(seatsSentence({ alreadyComing: 8, added: 52, open: 0 }, "now")).toBe(
      "8 were already coming. Your invitations added 52. Every seat is taken.",
    );
    expect(seatsSentence({ alreadyComing: 8, added: 52, open: 0 }, "then")).toBe(
      "8 were already coming. Your invitations added 52. Every seat was taken.",
    );
  });
});

describe("ResultPanels", () => {
  it("states both groups in words, from the response's own numbers", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    expect(slotText("exercise-seats-sentence")).toBe(
      "8 were already coming. Your invitations added 6. 46 seats are still open.",
    );
  });

  it("reads each number from the API rather than from the case", () => {
    render(
      <ResultPanels
        results={results({ existing_signups: 5, team: panel(30, 4, 3), seats_empty: 52 })}
        names={new Map()}
      />,
    );

    expect(slotText("exercise-seats-sentence")).toBe(
      "5 were already coming. Your invitations added 3. 52 seats are still open.",
    );
  });

  it("keeps the figures, split into the two groups", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    const figures = slotText("exercise-seats");
    expect(figures).toContain("Seats in the room60");
    expect(figures).toContain("Already coming8");
    expect(figures).toContain("Added by your invitations6");
    expect(figures).toContain("Seats still open46");
  });

  it("says round one's seats the same way, in the past tense", () => {
    render(
      <ResultPanels
        results={results({
          round: 2,
          round_one: {
            event_key: "E11",
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

    expect(slotText("exercise-round-one")).toContain(
      "Built from your team's setting “First try”. 8 were already coming. " +
        "Your invitations added 1. 51 seats were still open.",
    );
  });
});
