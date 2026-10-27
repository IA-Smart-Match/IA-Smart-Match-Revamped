/**
 * The instructor's presses say what they did, and the one that changes every
 * team asks first (issue #321; Ann's revisions of 2026-10-02, §1: buttons
 * that wipe or change work "ask “Are you sure?” first and say what will
 * change").
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InstructorDatasets } from "./InstructorDatasets";
import { InstructorTeams, teamClearedSentence } from "./InstructorTeams";
import { REFRESH_ALL_LABEL, REFRESH_ALL_QUESTION, RefreshAllPanel } from "./InstructorUnlock";
import { pastTheConfirmGuard } from "./inlineConfirmGuard.testkit";

const DATASETS = "/v1/exercise/instructor/datasets";
const WORKSPACES = "/v1/exercise/instructor/workspaces";
const REFRESH_ALL = "/v1/exercise/instructor/refresh-all";
const FILE = "11111111-1111-1111-1111-111111111111";

interface Answer {
  readonly body: unknown;
  readonly status?: number;
}

let calls: { key: string; body: unknown }[] = [];

function stub(answers: Record<string, Answer>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const key = `${init.method ?? "GET"} ${url.split("?")[0]}`;
      calls.push({ key, body: typeof init.body === "string" ? JSON.parse(init.body) : null });
      const answer = answers[key] ?? {
        body: { error: { code: "test_unstubbed", message: key } },
        status: 404,
      };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function sent(key: string): number {
  return calls.filter((call) => call.key === key).length;
}

function team(teamNumber: number): object {
  return {
    team_number: teamNumber,
    dataset_id: FILE,
    dataset_label: "October file",
    created_at: "2026-10-16T09:00:00",
    saved_setting_count: 2,
    result_run_count: 1,
    asking_choice: null,
    refreshed_at: null,
  };
}

const REPORT = { refreshed_team_numbers: [], refreshed: 0, skipped: 0, teams: [] };

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("refresh every team at once asks first", () => {
  function renderPanel(): { onDone: ReturnType<typeof vi.fn> } {
    const onDone = vi.fn();
    render(<RefreshAllPanel onDone={onDone} onSignedOut={vi.fn()} />);
    return { onDone };
  }

  function question(): HTMLElement | null {
    return document.querySelector('[data-slot="exercise-refresh-all-confirm"]');
  }

  it("sends nothing on the first press and says exactly what will change", () => {
    stub({ [`POST ${REFRESH_ALL}`]: { body: REPORT } });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));

    expect(sent(`POST ${REFRESH_ALL}`)).toBe(0);
    expect(question()?.textContent).toContain(REFRESH_ALL_QUESTION);
    expect(REFRESH_ALL_QUESTION).toBe(
      "Refresh every team that has chosen how to ask? Each of those teams is refreshed once, " +
        "and that cannot be undone or done again. Teams that have not chosen, and teams already " +
        "refreshed, are not changed.",
    );
    // The question is in the panel, not a pop-up, and focus is on the answer.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Refresh them now" }));
  });

  it("sends once when the instructor says yes, then shows the report", async () => {
    stub({ [`POST ${REFRESH_ALL}`]: { body: REPORT } });
    const { onDone } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));
    await pastTheConfirmGuard();
    fireEvent.click(screen.getByRole("button", { name: "Refresh them now" }));

    await screen.findByText("No team has entered a number yet, so there was no one to ask.");
    expect(sent(`POST ${REFRESH_ALL}`)).toBe(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(question()).toBeNull();
    // The button is back, and nothing asks again on its own.
    expect(screen.getByRole("button", { name: REFRESH_ALL_LABEL })).toBeDefined();
  });

  it("sends nothing on “Not yet”, and puts the button and focus back", async () => {
    stub({ [`POST ${REFRESH_ALL}`]: { body: REPORT } });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));
    fireEvent.click(screen.getByRole("button", { name: "Not yet" }));

    expect(question()).toBeNull();
    const button = screen.getByRole("button", { name: REFRESH_ALL_LABEL });
    await waitFor(() => expect(document.activeElement).toBe(button));
    expect(sent(`POST ${REFRESH_ALL}`)).toBe(0);
  });

  it("sends nothing on Escape", () => {
    stub({ [`POST ${REFRESH_ALL}`]: { body: REPORT } });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Refresh them now" }), { key: "Escape" });

    expect(question()).toBeNull();
    expect(sent(`POST ${REFRESH_ALL}`)).toBe(0);
  });

  it("asks again for a second run: one yes never covers two requests", async () => {
    stub({ [`POST ${REFRESH_ALL}`]: { body: REPORT } });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));
    await pastTheConfirmGuard();
    fireEvent.click(screen.getByRole("button", { name: "Refresh them now" }));
    await screen.findByText("No team has entered a number yet, so there was no one to ask.");

    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));
    expect(question()).not.toBeNull();
    expect(sent(`POST ${REFRESH_ALL}`)).toBe(1);
  });
});

describe("clearing a team says it was cleared", () => {
  it("writes the sentence with the team and the time", () => {
    expect(teamClearedSentence(3, "10:42 AM")).toBe(
      "Team 3 cleared at 10:42 AM. It is back at the start. No other team was changed.",
    );
    expect(teamClearedSentence(3, null)).toBe(
      "Team 3 cleared. It is back at the start. No other team was changed.",
    );
  });

  it("asks first, then shows “Team 3 cleared …” in the Teams panel and keeps it there", async () => {
    stub({
      [`GET ${WORKSPACES}`]: { body: { teams: [team(3), team(4)], active_dataset_label: "October file" } },
      [`POST ${WORKSPACES}/3/reset`]: { body: team(3) },
    });
    render(<InstructorTeams />);
    fireEvent.click(await screen.findByRole("button", { name: "Clear team 3's work" }));
    // The question names the scope, and nothing is sent yet.
    expect(
      screen.getByText(/This clears team 3's saved settings, result runs, way of asking\s+and refresh, including the topics the refresh added\..*No other team is touched\./s),
    ).toBeDefined();
    expect(sent(`POST ${WORKSPACES}/3/reset`)).toBe(0);
    expect(screen.queryByText(/^Team 3 cleared/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Yes, clear team 3" }));
    const said = await screen.findByText(
      /^Team 3 cleared at \d{1,2}:\d{2}:\d{2} (AM|PM)\. It is back at the start\. No other team was changed\.$/,
    );
    const notice = said.closest('[data-slot="exercise-notice"]') as HTMLElement;
    expect(notice.dataset.tone).toBe("done");
    expect(notice.closest('[data-slot="exercise-instructor-teams"]')).not.toBeNull();
    expect(sent(`POST ${WORKSPACES}/3/reset`)).toBe(1);

    await new Promise((resolve) => setTimeout(resolve, 1100));
    expect(screen.getByText(/^Team 3 cleared at/)).toBeDefined();
  });

  it("says the server's sentence, and no “Team 3 cleared”, when the clear is refused", async () => {
    stub({
      [`GET ${WORKSPACES}`]: { body: { teams: [team(3), team(4)], active_dataset_label: "October file" } },
      [`POST ${WORKSPACES}/3/reset`]: {
        body: {
          error: { code: "exercise_team_unknown", message: "No team with that number is in this data file." },
        },
        status: 404,
      },
    });
    render(<InstructorTeams />);
    fireEvent.click(await screen.findByRole("button", { name: "Clear team 3's work" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, clear team 3" }));

    const said = await screen.findByText("No team with that number is in this data file.");
    expect(said.closest('[data-slot="exercise-instructor-teams"]')).not.toBeNull();
    expect(sent(`POST ${WORKSPACES}/3/reset`)).toBe(1);
    expect(screen.queryByText(/^Team 3 cleared/)).toBeNull();
    // The team is still listed: nothing was cleared.
    expect(screen.getByRole("heading", { name: "Team 3" })).toBeDefined();
  });

  it("says when the teams were last read, so “Check the teams again” shows it did something", async () => {
    stub({
      [`GET ${WORKSPACES}`]: { body: { teams: [team(3)], active_dataset_label: "October file" } },
    });
    render(<InstructorTeams />);
    // To the second, so a second press in the same minute shows it was read again.
    await screen.findByText(/^Teams last read at \d{1,2}:\d{2}:\d{2} (AM|PM)\.$/);
    fireEvent.click(screen.getByRole("button", { name: "Check the teams again" }));
    await waitFor(() => expect(sent(`GET ${WORKSPACES}`)).toBe(2));
    expect(screen.getByText(/^Teams last read at/)).toBeDefined();
  });
});

describe("the list size is fixed at 60", () => {
  it("offers no control to change it", async () => {
    stub({
      [`GET ${DATASETS}`]: {
        body: [
          {
            dataset_id: FILE,
            label: "October file",
            source_filename: "SmartMatch_Student_Body_300.xlsx",
            row_count: 300,
            event_count: 12,
            invite_limit: 60,
            license_line: null,
            created_at: "2026-10-16T09:00:00",
          },
        ],
      },
    });
    render(<InstructorDatasets />);
    await screen.findByText("October file");
    expect(screen.queryByLabelText("How many names a list may hold")).toBeNull();
    expect(screen.queryByRole("button", { name: "Set the limit" })).toBeNull();
  });
});
