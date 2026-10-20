/**
 * Empty seats, said as both groups (wave-2 decision D8, Chau approved).
 *
 * The class case has 60 seats and 8 existing sign-ups. A bare "46 seats still
 * empty" hides what the team's list changed, so the screen says it in words:
 * "8 were already coming. 6 came because of your list. 46 seats are still open."
 * Every number comes from the API response — `existing_signups`, the team
 * panel's `attended_count`, `seats_empty` — never from a constant here.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ResultPanelView, ResultsView } from "../../../lib/exerciseClient";
import { liftCounts, liftSentence, listSignupsSentence, ResultPanels, resultsSeries, runRecordLine, seatCountsFor, seatsSentence } from "./ResultPanels";

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
    email_everyone: panel(300, 40, 0),
    seats_empty: 46,
    event_seats: 60,
    existing_signups: 8,
    existing_attended: 8,
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
      "8 were already coming. 6 came because of your list. 46 seats are still open.",
    );
  });

  it("speaks of a finished round in the past tense", () => {
    expect(seatsSentence({ alreadyComing: 8, added: 1, open: 51 }, "then")).toBe(
      "8 were already coming. 1 came because of your list. 51 seats were still open.",
    );
  });

  it("uses the singular for one person and one seat", () => {
    expect(seatsSentence({ alreadyComing: 1, added: 1, open: 1 }, "now")).toBe(
      "1 was already coming. 1 came because of your list. 1 seat is still open.",
    );
  });

  it("says plainly when nobody was already coming", () => {
    expect(seatsSentence({ alreadyComing: 0, added: 6, open: 54 }, "now")).toBe(
      "Nobody was already coming. 6 came because of your list. 54 seats are still open.",
    );
  });

  it("says plainly when the invitations added nobody", () => {
    expect(seatsSentence({ alreadyComing: 8, added: 0, open: 52 }, "now")).toBe(
      "8 were already coming. Nobody came because of your list. 52 seats are still open.",
    );
  });

  it("omits 'more attended' when nobody attended", () => {
    expect(seatsSentence({ alreadyComing: 8, attended: 0, open: 52 }, "then")).toBe(
      "8 were already coming. 52 seats were still open.",
    );
  });

  it("leaves the invitations clause out when added is not given", () => {
    expect(seatsSentence({ alreadyComing: 8, open: 51 }, "then")).toBe(
      "8 were already coming. 51 seats were still open.",
    );
  });

  it("says the room is full rather than 0 seats open", () => {
    expect(seatsSentence({ alreadyComing: 8, added: 52, open: 0 }, "now")).toBe(
      "8 were already coming. 52 came because of your list. Every seat is taken.",
    );
    expect(seatsSentence({ alreadyComing: 8, added: 52, open: 0 }, "then")).toBe(
      "8 were already coming. 52 came because of your list. Every seat was taken.",
    );
  });
});

describe("ResultPanels", () => {
  it("states both groups in words, from the response's own numbers", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    expect(slotText("exercise-seats-sentence")).toBe(
      "8 were already coming. 6 came because of your list. 46 seats are still open.",
    );
  });

  it("reads each number from the API rather than from the case", () => {
    render(
      <ResultPanels
        results={results({ existing_signups: 5, existing_attended: 5, team: panel(30, 4, 3), seats_empty: 52 })}
        names={new Map()}
      />,
    );

    expect(slotText("exercise-seats-sentence")).toBe(
      "5 were already coming. 3 came because of your list. 52 seats are still open.",
    );
  });

  it("keeps the figures, split into the two groups", () => {
    render(<ResultPanels results={results()} names={new Map()} />);

    // DESIGN.md §6.15 / §11.1: the ruled band is "Seats in the room",
    // "Already coming", "Still open"; the team's 6 is said by the sentence
    // above it and the room's legend, "Came because of your list (6)".
    const figures = slotText("exercise-seats");
    expect(figures).toContain("Seats in the room60");
    expect(figures).toContain("Already coming8");
    expect(figures).toContain("Still open46");
    expect(slotText("exercise-room")).toContain("Came because of your list (6)");
  });

  it("recaps round one's seats in the past tense without the overstated 'invitations added' line", () => {
    render(
      <ResultPanels
        results={results({
          round: 2,
          round_one: {
            event_key: "E11",
            round: 1,
            setting_name: "First try",
            team: panel(30, 2, 1),
            email_everyone: panel(300, 2, 1),
            seats_empty: 51,
            existing_attended: 8,
            attended_in_room: 1,
            created_at: "2026-09-25T09:00:00Z",
          },
        })}
        names={new Map()}
      />,
    );

    const recap = slotText("exercise-round-one");
    // B4 item 3: same helpers, same wording as the round-one screen.
    expect(recap).toContain("Built from your team's setting “First try”.");
    expect(recap).toContain("Your list brought 0 extra sign-ups; 0 of them came.");
    expect(recap).toContain("Nobody came because of your list.");
    expect(recap).toContain("51 seats were still open.");
  });
});

describe("liftCounts", () => {
  const withSignups = (team: number[], mass: number[]): ResultsView =>
    results({
      team: { ...panel(30, 0, 0), signed_up_profile_nos: team, signed_up_count: team.length },
      email_everyone: {
        ...panel(300, 0, 0),
        signed_up_profile_nos: mass,
        signed_up_count: mass.length,
      },
    });

  it("counts only team sign-ups the mass email missed", () => {
    expect(liftCounts(withSignups([1, 2, 9, 10], [1, 2, 3]))).toEqual({
      mass: 3,
      withList: 5,
      added: 2,
      own: 4,
      anyway: 2,
    });
  });

  it("adds nothing when the list only overlaps the mass email", () => {
    expect(liftCounts(withSignups([1, 2], [1, 2, 3])).added).toBe(0);
  });

  it("handles empty panels", () => {
    expect(liftCounts(withSignups([], []))).toEqual({ mass: 0, withList: 0, added: 0, own: 0, anyway: 0 });
  });

  it("renders the lift line and the debrief sentence", () => {
    const r = withSignups([1, 2, 9, 10], [1, 2, 3]);
    expect(liftSentence(r)).toBe("Your list brought 2 extra sign-ups; 0 of them came.");
    expect(listSignupsSentence(r)).toBe(
      "4 people on your list signed up. 2 of them would have signed up from the mass email anyway, so your list added 2.",
    );
    render(<ResultPanels results={r} />);
    expect(slotText("exercise-lift")).toContain("Look at your gap over the mass email");
  });
});

describe("seat counts when only some of the 8 pre-registered students came", () => {
  it("counts the ones who came, so the parts still add to the room", () => {
    const r = results({ existing_attended: 5, team: panel(30, 4, 3), seats_empty: 52 });
    const { alreadyComing, added } = seatCountsFor(r);
    expect(alreadyComing + added + r.seats_empty).toBe(r.event_seats);
    expect(seatsSentence({ alreadyComing, added, open: r.seats_empty }, "now")).toMatch(
      /^\d+ were already coming\./,
    );
  });
});

describe("round-one recap sums to the room", () => {
  it.each([
    [8, 1, 51],
    [5, 12, 43],
    [2, 18, 40],
  ])("%i of the 8 + %i in the room + %i open = 60", (came, inRoom, open) => {
    const r = results({
      round: 2,
      round_one: {
        event_key: "E11",
        round: 1,
        setting_name: null,
        team: panel(30, 2, 1),
        email_everyone: panel(300, 2, 1),
        seats_empty: open,
        existing_attended: came,
        attended_in_room: inRoom,
        created_at: "2026-09-25T09:00:00Z",
      },
    });
    render(<ResultPanels results={r} />);
    expect(slotText("exercise-round-one")).toContain(
      `${came + 1} were already coming. Nobody came because of your list. ${open} seats were still open.`,
    );
  });
});

describe("round-one recap parity (B4 item 3)", () => {
  it("says what the round-one screen said, from the same stored panels", () => {
    const team = { ...panel(30, 11, 7), signed_up_profile_nos: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], attended_profile_nos: [1, 2, 3, 4, 5, 9, 10] };
    const mass = { ...panel(300, 8, 5), signed_up_profile_nos: [1, 2, 3, 4, 5, 6, 7, 8], attended_profile_nos: [1, 2, 3, 4, 5] };
    const roundOne = results({ team, email_everyone: mass, existing_attended: 8, seats_empty: 38 });
    const screen = render(<ResultPanels results={roundOne} />);
    const lift = slotText("exercise-lift");
    const seats = slotText("exercise-seats-sentence");
    screen.unmount();
    render(
      <ResultPanels
        results={results({
          round: 2,
          round_one: { event_key: "northline", round: 1, setting_name: null, team, email_everyone: mass, seats_empty: 38, existing_attended: 8, created_at: "2026-10-16T14:00:00Z" },
        })}
      />,
    );
    const recap = slotText("exercise-round-one");
    expect(lift).toContain("11 people on your list signed up. 8 of them would have signed up from the mass email anyway, so your list added 3.");
    for (const sentence of [
      "Your list brought 3 extra sign-ups; 2 of them came.",
      "11 people on your list signed up. 8 of them would have signed up from the mass email anyway, so your list added 3.",
      "13 were already coming. 2 came because of your list. 38 seats were still open.",
    ]) {
      expect(recap).toContain(sentence);
    }
    expect(seats).toContain("13 were already coming. 2 came because of your list.");
  });
});

describe("chart caption (B4 item 5)", () => {
  it("says Ann's light/dark sentence and orders the series mass first", () => {
    render(<ResultPanels results={results()} names={new Map()} />);
    expect(screen.getByTestId("exercise-results-chart").textContent).toContain(
      "Light bar: mass email alone. Dark bar: mass email plus your CBACH emails.",
    );
    expect(resultsSeries(results())[0]?.label).toBe("Mass email alone");
  });
});

describe("chart dark bar is mass plus list (review fix)", () => {
  it("never draws the dark bar below the light one", () => {
    // Harbor-like: list's own sign-ups (11) are fewer than the mass email's (19).
    const r = results({
      team: { ...panel(30, 11, 9), signed_up_profile_nos: Array.from({ length: 11 }, (_, i) => i + 1), attended_profile_nos: [1, 2, 3, 4, 5, 6, 7, 8, 9] },
      email_everyone: { ...panel(300, 19, 12), signed_up_profile_nos: Array.from({ length: 19 }, (_, i) => i + 1), attended_profile_nos: Array.from({ length: 12 }, (_, i) => i + 1) },
    });
    const [light, dark] = resultsSeries(r);
    expect(dark?.signedUp).toBe(19);
    expect(dark?.attended).toBe(12);
    expect(dark!.signedUp as number).toBeGreaterThanOrEqual(light!.signedUp as number);
    expect(dark!.attended as number).toBeGreaterThanOrEqual(light!.attended as number);
  });
});

describe("seatCountsFor", () => {
  it("counts the mass email's attendees as already coming and only the rest as added", () => {
    const r = results({
      team: { ...panel(30, 12, 9), attended_profile_nos: [1, 2, 3, 4, 5, 6, 7, 8, 9] },
      email_everyone: { ...panel(300, 40, 4), attended_profile_nos: [1, 2, 3, 4] },
      existing_signups: 8,
      existing_attended: 8,
    });
    expect(seatCountsFor(r)).toEqual({ alreadyComing: 12, added: 5 });
  });
});

describe("resultsSeries round-one label (A85)", () => {
  const roundTwo = results({
    round_one: { event_key: "northline", round: 1, setting_name: null, team: panel(30, 10, 5), seats_empty: 1, existing_attended: 8, created_at: "2026-10-16T14:00:00Z" },
  });
  it("names the round-one event when known", () => {
    expect(resultsSeries(roundTwo, "Northline")[2]?.label).toBe("Your team, Northline (Round 1)");
  });
  it("keeps the old label as the fallback", () => {
    expect(resultsSeries(roundTwo)[2]?.label).toBe("Your team, Round 1");
    expect(resultsSeries(roundTwo, null)[2]?.label).toBe("Your team, Round 1");
  });
});

describe("results from an API older than #410 (B1)", () => {
  const { existing_attended: _a, ...legacy } = results({ existing_signups: 8 });
  const old = legacy as unknown as ResultsView;

  it("falls back to existing_signups for already coming", () => {
    expect(seatCountsFor(old).alreadyComing).toBe(8 + 0);
  });

  it("renders no NaN, including a round-one recap without the new fields", () => {
    const twoRound = {
      ...old,
      round: 2,
      round_one: { event_key: "northline", round: 1, setting_name: null, team: panel(30, 10, 5), seats_empty: 1, created_at: "2026-10-16T14:00:00Z" },
    } as unknown as ResultsView;
    const { container } = render(<ResultPanels results={twoRound} />);
    expect(container.textContent).not.toMatch(/NaN/i);
    expect(slotText("exercise-round-one")).toContain("8 were already coming");
  });
});

describe("runRecordLine (B2)", () => {
  it("names the setting", () => {
    expect(runRecordLine(results({ setting_name: "Wide net", team: panel(5, 1, 1) }))).toBe(
      "These results are saved from your setting “Wide net”, with 5 invited. Changing your setting or the name limit now will not change them.",
    );
  });
  it("falls back when there is no setting", () => {
    expect(runRecordLine(results({ setting_name: null, team: panel(30, 1, 1) }))).toBe(
      "These results are saved from a list built without a saved setting, with 30 invited. Changing your setting or the name limit now will not change them.",
    );
  });
  it("renders the line in the team section", () => {
    render(<ResultPanels results={results({ team: panel(5, 1, 1) })} />);
    expect(slotText("exercise-run-record")).toContain("5 invited");
  });
});

describe("liftSentence singular", () => {
  it("avoids '1 of them' after one extra sign-up", () => {
    const base = results({});
    const mk = (att: number[]) => ({
      ...base,
      team: { ...base.team, signed_up_profile_nos: [1, 9], attended_profile_nos: att },
      email_everyone: { ...base.email_everyone, signed_up_profile_nos: [1], attended_profile_nos: [1] },
    });
    expect(liftSentence(mk([1, 9]))).toBe("Your list brought 1 extra sign-up; they came.");
    expect(liftSentence(mk([1]))).toBe("Your list brought 1 extra sign-up; they did not come.");
  });
});
