/** Issue #413: the instructor page shows the six team codes behind a toggle. */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InstructorTeamCodes } from "./InstructorTeamCodes";

const CODES = { teams: [1, 2, 3, 4, 5, 6].map((n) => ({ team_number: n, code: `0${n}0${n}` })) };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<InstructorTeamCodes />", () => {
  it("reads nothing and shows no code until asked, then shows all six", async () => {
    const fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify(CODES), { status: 200 })));
    vi.stubGlobal("fetch", fetch);
    render(<InstructorTeamCodes />);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText("0101")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show team codes" }));
    expect(await screen.findByText("0606")).toBeDefined();
    expect(fetch).toHaveBeenCalledWith("/v1/exercise/instructor/team-codes", expect.anything());
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(
      CODES.teams.map((t) => `Team ${t.team_number}: ${t.code}`),
    );

    fireEvent.click(screen.getByRole("button", { name: "Hide team codes" }));
    expect(screen.queryByText("0101")).toBeNull();
  });
});
