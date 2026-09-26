/**
 * The Teams panel returns the page to the passcode form on a 401.
 *
 * The other instructor actions go through the page's `guard`, which calls
 * `onSignedOut` when the twelve-hour cookie has run out. The Teams panel read
 * its own list, reset and team detail without it, so an expired session left
 * the panel's controls on screen, each failing the same way.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseInstructor } from "./ExerciseInstructor";
import { InstructorTeams } from "./InstructorTeams";

interface Answer {
  readonly body: unknown;
  readonly status?: number;
}

const WORKSPACES = "/v1/exercise/instructor/workspaces";
const TEAMS_FILE = "11111111-1111-1111-1111-111111111111";

const EXPIRED: Answer = {
  body: {
    error: {
      code: "exercise_instructor_session_required",
      message: "Enter the instructor passcode to open this page.",
    },
  },
  status: 401,
};

const OTHER_REFUSAL: Answer = {
  body: { error: { code: "exercise_team_not_found", message: "There is no team 1." } },
  status: 404,
};

const TEAM_LIST: Answer = {
  body: {
    teams: [
      {
        team_number: 1,
        dataset_id: TEAMS_FILE,
        dataset_label: "Autumn draft",
        created_at: "2026-09-21T10:00:00Z",
        saved_setting_count: 1,
        result_run_count: 1,
        asking_choice: null,
        refreshed_at: null,
      },
    ],
    active_dataset_label: "Autumn draft",
  },
};

/**
 * Each key answers from its queue in order; the last answer repeats. A queue
 * lets the page's session probe succeed and a later read of the same route
 * find the cookie expired.
 */
function stub(answers: Record<string, Answer[]>): void {
  const served: Record<string, number> = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const key = `${init.method ?? "GET"} ${url.split("?")[0]}`;
      const queue = answers[key];
      const index = served[key] ?? 0;
      served[key] = index + 1;
      const answer = queue?.[Math.min(index, queue.length - 1)] ?? {
        body: { error: { code: "test_unstubbed", message: key } },
        status: 404,
      };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function teamsPanel(): HTMLElement {
  return document.querySelector('[data-slot="exercise-instructor-teams"]') as HTMLElement;
}

beforeEach(() => {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => "visible",
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete (document as { visibilityState?: unknown }).visibilityState;
});

describe("<InstructorTeams /> signs out on an expired session", () => {
  it("when its own list read is refused with a 401", async () => {
    const onSignedOut = vi.fn();
    stub({ [`GET ${WORKSPACES}`]: [EXPIRED] });
    render(<InstructorTeams onSignedOut={onSignedOut} />);
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledTimes(1));
  });

  it("when a team reset is refused with a 401", async () => {
    const onSignedOut = vi.fn();
    stub({
      [`GET ${WORKSPACES}`]: [TEAM_LIST],
      [`POST ${WORKSPACES}/1/reset`]: [EXPIRED],
    });
    render(<InstructorTeams onSignedOut={onSignedOut} />);
    fireEvent.click(await screen.findByRole("button", { name: /clear team 1's work/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, clear team 1/i }));
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledTimes(1));
  });

  it("when opening a team's work is refused with a 401", async () => {
    const onSignedOut = vi.fn();
    stub({
      [`GET ${WORKSPACES}`]: [TEAM_LIST],
      [`GET ${WORKSPACES}/1`]: [EXPIRED],
    });
    render(<InstructorTeams onSignedOut={onSignedOut} />);
    fireEvent.click(await screen.findByRole("button", { name: /open this team's work/i }));
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledTimes(1));
  });

  it("not on any other refusal", async () => {
    const onSignedOut = vi.fn();
    stub({
      [`GET ${WORKSPACES}`]: [TEAM_LIST],
      [`GET ${WORKSPACES}/1`]: [OTHER_REFUSAL],
    });
    render(<InstructorTeams onSignedOut={onSignedOut} />);
    fireEvent.click(await screen.findByRole("button", { name: /open this team's work/i }));
    await screen.findByText("There is no team 1.");
    expect(onSignedOut).not.toHaveBeenCalled();
  });
});

describe("<ExerciseInstructor /> and the Teams panel", () => {
  it("returns to the passcode form when the teams re-read finds the cookie expired", async () => {
    stub({
      [`GET ${WORKSPACES}`]: [TEAM_LIST, TEAM_LIST, EXPIRED],
      "GET /v1/exercise/instructor/datasets": [{ body: [] }],
      "GET /v1/exercise/instructor/events": [
        { body: { dataset_id: TEAMS_FILE, dataset_label: "Autumn draft", events: [] } },
      ],
    });
    const router = createMemoryRouter(
      [{ path: "/exercise/instructor", element: <ExerciseInstructor /> }],
      { initialEntries: ["/exercise/instructor"] },
    );
    render(<RouterProvider router={router} />);
    await waitFor(() => expect(teamsPanel()?.textContent).toContain("Team 1"));
    fireEvent.click(within(teamsPanel()).getByRole("button", { name: /check the teams again/i }));
    await screen.findByRole("button", { name: /open the instructor page/i });
    expect(teamsPanel()).toBeNull();
  });
});
