/** Invited names list in rank order, whatever order the numbers arrive in (#269). */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { InvitedProfileView, ResultsView } from "../../../lib/exerciseClient";
import { inRankOrder, ResultPanels } from "./ResultPanels";

const person = (profile_no: number, rank: number | null, display_name: string): InvitedProfileView => ({
  rank, profile_no, display_name, major: null, class_year: null, marker: null, reason: null,
});

const panel = (nos: number[]) => ({
  invited_profile_nos: nos, signed_up_profile_nos: [], attended_profile_nos: [],
  invited_count: nos.length, signed_up_count: 0, attended_count: 0,
});

const run = {
  event_key: "E11", event_name: "Northline", round: 1, setting_name: "x",
  team: panel([3, 1, 2, 4]), email_everyone: panel([]), seats_empty: 0, event_seats: 10,
  existing_signups: 0,
  existing_attended: 0, round_one: null, created_at: "2026-09-25T10:00:00Z",
  invited_profiles: [person(1, 3, "Cara"), person(2, 1, "Ann"), person(3, 2, "Bo"), person(4, null, "Dee")],
} as unknown as ResultsView;

afterEach(cleanup);

describe("invited rank order", () => {
  it("renders invited names by ascending rank, unranked last", () => {
    const { container } = render(<ResultPanels results={run} />);
    const first = container.querySelectorAll('[data-slot="exercise-team-people"] ul')[0];
    const names = Array.from(first.querySelectorAll("li")).map((li) => li.textContent);
    expect(names).toEqual(["Ann", "Bo", "Cara", "Dee"]);
  });

  it("does not mutate its input and keeps order among unranked", () => {
    const input = [9, 8, 1];
    expect(inRankOrder(run, input)).toEqual([1, 9, 8]);
    expect(input).toEqual([9, 8, 1]);
  });
});
