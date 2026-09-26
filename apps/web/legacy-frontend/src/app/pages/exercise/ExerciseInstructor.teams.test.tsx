/**
 * The instructor's Teams panel stays current during a class.
 *
 * M2's browser run on main @9339d5a4 (B1): the panel read the team list once
 * per upload or re-point, so a team that entered its number never appeared,
 * and after "Ask for every team" every row still said "Has not asked yet."
 * It now re-reads after the page's own actions, on a button, when the tab
 * comes back into view, and every 15 seconds while the tab is visible.
 *
 * Kept apart from `ExerciseInstructor.test.tsx`, which is near the 800-line
 * cap. The browser here already holds a live instructor cookie, so the
 * page's session probe signs in on its own.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseInstructor } from "./ExerciseInstructor";
import { InstructorTeams, TEAMS_POLL_MS } from "./InstructorTeams";

interface Answer {
  readonly body: unknown;
  readonly status?: number;
}

let calls: { url: string; init: RequestInit }[] = [];

function stub(answers: Record<string, Answer>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const path = url.split("?")[0];
      const answer = answers[`${init.method ?? "GET"} ${path}`] ?? {
        body: { error: { code: "test_unstubbed", message: path } },
        status: 404,
      };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

const DATASETS = "/v1/exercise/instructor/datasets";
const WORKSPACES = "/v1/exercise/instructor/workspaces";
const INSTRUCTOR_EVENTS = "/v1/exercise/instructor/events";
const REFRESH_ALL = "/v1/exercise/instructor/refresh-all";
const TEAMS_FILE = "11111111-1111-1111-1111-111111111111";

function team(teamNumber: number, refreshedAt: string | null) {
  return {
    team_number: teamNumber,
    dataset_id: TEAMS_FILE,
    dataset_label: "Autumn draft",
    created_at: "2026-09-21T10:00:00Z",
    saved_setting_count: 1,
    result_run_count: 1,
    asking_choice: "small_reward",
    refreshed_at: refreshedAt,
  };
}

function teams(...rows: ReturnType<typeof team>[]) {
  return { body: { teams: rows, active_dataset_label: "Autumn draft" } };
}

function pageStubs(extra: Record<string, Answer> = {}): Record<string, Answer> {
  return {
    [`GET ${DATASETS}`]: { body: [] },
    [`GET ${WORKSPACES}`]: teams(team(1, null)),
    [`GET ${INSTRUCTOR_EVENTS}`]: {
      body: {
        dataset_id: TEAMS_FILE,
        dataset_label: "Autumn draft",
        events: [{ event_key: "round-one", name: "Round one", unlocked: false }],
      },
    },
    ...extra,
  };
}

const teamReads = () => calls.filter((call) => call.url === WORKSPACES).length;

function teamsPanel(): HTMLElement {
  return document.querySelector('[data-slot="exercise-instructor-teams"]') as HTMLElement;
}

function renderPage() {
  const router = createMemoryRouter(
    [{ path: "/exercise/instructor", element: <ExerciseInstructor /> }],
    { initialEntries: ["/exercise/instructor"] },
  );
  return render(<RouterProvider router={router} />);
}

let visibility: DocumentVisibilityState = "visible";

function setVisibility(value: DocumentVisibilityState): void {
  visibility = value;
  document.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  calls = [];
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => visibility,
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  // Back to jsdom's own getter on the prototype.
  delete (document as { visibilityState?: unknown }).visibilityState;
});

describe("the instructor page keeps the Teams panel current", () => {
  it("re-reads the teams after Ask for every team", async () => {
    const answers = pageStubs({
      [`POST ${REFRESH_ALL}`]: {
        body: { refreshed_team_numbers: [1], refreshed: 1, skipped: 0 },
      },
    });
    stub(answers);
    renderPage();
    await waitFor(() => expect(teamsPanel()?.textContent).toContain("Has not asked yet."));

    answers[`GET ${WORKSPACES}`] = teams(team(1, "2026-09-25T10:00:00Z"));
    fireEvent.click(screen.getByRole("button", { name: /^ask for every team$/i }));

    await waitFor(() => expect(teamsPanel().textContent).toContain("Has already asked."));
  });

  it("says why a team was skipped", async () => {
    stub(
      pageStubs({
        [`POST ${REFRESH_ALL}`]: {
          body: { refreshed_team_numbers: [1], refreshed: 1, skipped: 1 },
        },
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^ask for every team$/i }));
    await screen.findByText(/skipped 1/i);
    expect(screen.getByText(/skipped 1/i).textContent).toContain(
      "has not run results for its first event yet",
    );
  });

  it("says why several teams were skipped", async () => {
    stub(
      pageStubs({
        [`POST ${REFRESH_ALL}`]: {
          body: { refreshed_team_numbers: [], refreshed: 0, skipped: 2 },
        },
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^ask for every team$/i }));
    await screen.findByText(/skipped 2/i);
    expect(screen.getByText(/skipped 2/i).textContent).toContain(
      "those teams have not run results for their first event yet",
    );
  });

  it("re-reads the teams after an unlock lands", async () => {
    const answers = pageStubs({
      [`POST ${INSTRUCTOR_EVENTS}/round-one/unlock`]: {
        body: { event_key: "round-one", unlocked: true },
      },
    });
    stub(answers);
    renderPage();
    const roundOne = (await screen.findByText("Round one")).closest("li") as HTMLElement;
    await waitFor(() => expect(teamsPanel()?.textContent).toContain("Team 1"));
    const before = teamReads();

    fireEvent.click(within(roundOne).getByRole("button", { name: /open results/i }));
    await waitFor(() => expect(teamReads()).toBe(before + 1));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(teamReads()).toBe(before + 1);
  });
});

describe("<InstructorTeams />", () => {
  it("shows a team that joins after the page opened, on Check again", async () => {
    const answers = pageStubs();
    stub(answers);
    render(<InstructorTeams />);
    await waitFor(() => expect(teamsPanel().textContent).toContain("Team 1"));

    answers[`GET ${WORKSPACES}`] = teams(team(1, null), team(2, null));
    fireEvent.click(within(teamsPanel()).getByRole("button", { name: /check the teams again/i }));
    await waitFor(() => expect(teamsPanel().textContent).toContain("Team 2"));
  });

  it("re-reads when the tab comes back into view, and not when it is hidden", async () => {
    stub(pageStubs());
    render(<InstructorTeams />);
    await waitFor(() => expect(teamsPanel().textContent).toContain("Team 1"));
    const before = teamReads();

    setVisibility("hidden");
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(teamReads()).toBe(before);

    setVisibility("visible");
    await waitFor(() => expect(teamReads()).toBe(before + 1));
  });

  it(`polls every ${TEAMS_POLL_MS / 1000} seconds while the tab is visible`, async () => {
    // Only the interval is faked: `waitFor` needs real timeouts.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    stub(pageStubs());
    render(<InstructorTeams />);
    await waitFor(() => expect(teamsPanel().textContent).toContain("Team 1"));
    const before = teamReads();

    act(() => {
      vi.advanceTimersByTime(TEAMS_POLL_MS);
    });
    await waitFor(() => expect(teamReads()).toBe(before + 1));

    visibility = "hidden";
    act(() => {
      vi.advanceTimersByTime(TEAMS_POLL_MS * 2);
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(teamReads()).toBe(before + 1);
  });

  it("stops polling once the panel is gone", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const removed = vi.spyOn(document, "removeEventListener");
    stub(pageStubs());
    const { unmount } = render(<InstructorTeams />);
    await waitFor(() => expect(teamsPanel().textContent).toContain("Team 1"));
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    expect(removed.mock.calls.some(([type]) => type === "visibilitychange")).toBe(true);
  });

  it("does not poll a refused list, but still re-reads on the button", async () => {
    // Review finding: after the 12-hour cookie expired, the poll re-sent a
    // refused GET every 15 seconds and flickered "Loading the teams" each time.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    stub({
      [`GET ${WORKSPACES}`]: {
        body: {
          error: {
            code: "exercise_instructor_session_required",
            message: "Enter the instructor passcode to open this page.",
          },
        },
        status: 401,
      },
    });
    render(<InstructorTeams />);
    await screen.findByText("Enter the instructor passcode to open this page.");
    const before = teamReads();

    act(() => {
      vi.advanceTimersByTime(TEAMS_POLL_MS * 3);
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(teamReads()).toBe(before);

    fireEvent.click(within(teamsPanel()).getByRole("button", { name: /check the teams again/i }));
    await waitFor(() => expect(teamReads()).toBe(before + 1));
  });

  it("words a team's result run the D8 way: seats still open", async () => {
    stub(
      pageStubs({
        [`GET ${WORKSPACES}/1`]: {
          body: {
            team_number: 1,
            saved_settings: [],
            result_runs: [
              {
                event_key: "round-one",
                round: 1,
                setting_name: "Majors first",
                invited_count: 30,
                signed_up_count: 14,
                attended_count: 11,
                seats_empty: 46,
                created_at: "2026-09-25T10:00:00Z",
              },
            ],
          },
        },
      }),
    );
    render(<InstructorTeams />);
    fireEvent.click(await screen.findByRole("button", { name: /open this team's work/i }));
    await waitFor(() => expect(teamsPanel().textContent).toContain("46 seats are still open."));
    expect(teamsPanel().textContent).not.toContain("seats empty");
  });
});
