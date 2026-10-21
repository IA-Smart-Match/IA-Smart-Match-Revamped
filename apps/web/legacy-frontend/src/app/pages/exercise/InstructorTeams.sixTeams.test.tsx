/** The Teams panel always lists Team 1 to 6, and says which file the teams are on. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InstructorTeams } from "./InstructorTeams";

const OLD = "11111111-1111-1111-1111-111111111111";

function row(teamNumber: number, label = "Oct2-Ann-300", datasetId = OLD) {
  return {
    team_number: teamNumber,
    dataset_id: datasetId,
    dataset_label: label,
    created_at: "2026-10-20T10:00:00Z",
    saved_setting_count: 1,
    result_run_count: 0,
    asking_choice: null,
    refreshed_at: null,
  };
}

function stub(teams: ReturnType<typeof row>[], active: string | null, detail = false): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = url.startsWith("/v1/exercise/instructor/workspaces?") || url === "/v1/exercise/instructor/workspaces"
        ? { teams, active_dataset_label: active }
        : { error: { code: "test_unstubbed", message: url } };
      const status = detail || "teams" in body ? 200 : 404;
      return Promise.resolve(new Response(JSON.stringify(body), { status }));
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("InstructorTeams, six teams", () => {
  it("shows Team 2 as not entered when only 1, 3, 4, 5, 6 have rows", async () => {
    stub([1, 3, 4, 5, 6].map((n) => row(n)), "Oct2-Ann-300");
    render(<InstructorTeams />);
    await screen.findByText("Team 2 has not entered its number on this server yet.");
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "Team 1",
      "Team 3",
      "Team 4",
      "Team 5",
      "Team 6",
    ]);
    expect(screen.getAllByRole("button", { name: "Open this team's work" })).toHaveLength(5);
    expect(screen.getByText("Teams are using: Oct2-Ann-300.")).toBeDefined();
  });

  it("says the newest upload is not in use when teams are on an older file", async () => {
    stub([row(1)], "Newer file");
    render(<InstructorTeams />);
    await screen.findByText(
      "Teams are using: Oct2-Ann-300. The newest upload, Newer file, is not in use yet. Teams stay on Oct2-Ann-300 until you move them.",
    );
  });

  it("shows both rows when a team is on two files", async () => {
    stub([row(1), row(1, "Newer file", "22222222-2222-2222-2222-222222222222")], "Newer file");
    render(<InstructorTeams />);
    await waitFor(() => expect(screen.getAllByRole("heading", { level: 3, name: "Team 1" })).toHaveLength(2));
  });

  it("does not touch the clipboard when opening a team's work", async () => {
    stub([row(1)], "Oct2-Ann-300");
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const copied = vi.fn();
    document.addEventListener("copy", copied);
    render(<InstructorTeams />);
    fireEvent.click(await screen.findByRole("button", { name: "Open this team's work" }));
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));
    document.removeEventListener("copy", copied);
    expect(writeText).not.toHaveBeenCalled();
    expect(copied).not.toHaveBeenCalled();
  });
});

describe("InstructorTeams, a failed poll", () => {
  it("keeps the last teams on screen, says it is reconnecting, then recovers", async () => {
    let fail = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        fail
          ? Promise.reject(new TypeError("offline"))
          : Promise.resolve(
              new Response(JSON.stringify({ teams: [row(1)], active_dataset_label: "Oct2-Ann-300" }), { status: 200 }),
            ),
      ),
    );
    render(<InstructorTeams />);
    await screen.findByText("Teams are using: Oct2-Ann-300.");

    fail = true;
    fireEvent.click(screen.getByRole("button", { name: "Check the teams again" }));
    await screen.findByText("Reconnecting…");
    expect(screen.getByText("Teams are using: Oct2-Ann-300.")).toBeDefined();

    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Check the teams again" }));
    await waitFor(() => expect(screen.queryByText("Reconnecting…")).toBeNull());
    expect(screen.getByText("Teams are using: Oct2-Ann-300.")).toBeDefined();
  });
});
