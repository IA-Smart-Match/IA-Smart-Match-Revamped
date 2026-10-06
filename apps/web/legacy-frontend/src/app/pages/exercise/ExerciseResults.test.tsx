/**
 * Results: the server's refusals as calm states, in its own words.
 *
 * The results rule's coefficients are now set (D7), so a run normally
 * succeeds. `POST …/results` still answers `exercise_results_rule_not_confirmed`
 * if the coefficients are ever removed, and the first test below keeps that
 * sentence reaching the projector as a state rather than an error.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseResults } from "./ExerciseResults";

let calls: { url: string; init: RequestInit }[] = [];

function stub(answers: Record<string, { body: unknown; status?: number }>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const path = url.split("?")[0];
      const answer = answers[`${init.method ?? "GET"} ${path}`] ??
        answers[path] ?? {
          body: { error: { code: "test_unstubbed", message: path } },
          status: 404,
        };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

const RESULTS = "/v1/exercise/workspaces/current/events/northline/results";
const LIST = "/v1/exercise/workspaces/current/events/northline/list";
const ASKING = "/v1/exercise/workspaces/current/asking-choice";
const SETTINGS = "/v1/exercise/workspaces/current/events/northline/settings";

/** Ann to Chau, Discord, 2026-09-24: the team chooses one final setting. */
const TWO_SAVED = {
  body: {
    event_key: "northline",
    settings: [
      { name: "Wide net", weights: {}, created_at: "2026-09-20T10:00:00Z" },
      { name: "Only majors", weights: {}, created_at: "2026-09-20T10:05:00Z" },
    ],
    max_settings: 3,
  },
};

const NONE_SAVED = { body: { event_key: "northline", settings: [], max_settings: 3 } };

/**
 * Pick the final setting, then press run — the one path to a run now. The
 * picker is radio cards (DESIGN.md §6.13), so picking is a click on the card.
 */
async function runWith(name: string): Promise<void> {
  fireEvent.click(await screen.findByRole("radio", { name }));
  fireEvent.click(screen.getByRole("button", { name: /run results/i }));
}

/**
 * The desk's Button stays focusable when off, so the reason stays reachable
 * (DESIGN.md §6.3): "off" is `aria-disabled`, not the `disabled` attribute.
 */
function isOff(button: HTMLElement): boolean {
  return button.getAttribute("aria-disabled") === "true";
}

const NOT_RUN = {
  body: { error: { code: "exercise_results_not_run", message: "No results yet." } },
  status: 404,
};

const NO_LIST = {
  body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
  status: 401,
};

const NO_CHOICE = { body: { choice: null, choices: ["required"], refreshed: false } };

function panel(invited: number, signedUp: number, attended: number) {
  return {
    invited_profile_nos: Array.from({ length: invited }, (_, index) => index + 1),
    signed_up_profile_nos: Array.from({ length: signedUp }, (_, index) => index + 1),
    attended_profile_nos: Array.from({ length: attended }, (_, index) => index + 1),
    invited_count: invited,
    signed_up_count: signedUp,
    attended_count: attended,
  };
}

function renderResults() {
  const router = createMemoryRouter(
    [
      { path: "/exercise/events/:eventKey/results", element: <ExerciseResults /> },
      { path: "/exercise/events/:eventKey", element: <p>list</p> },
      { path: "/exercise/asking", element: <p>asking</p> },
      { path: "/exercise", element: <p>entry</p> },
    ],
    { initialEntries: ["/exercise/events/northline/results"] },
  );
  return render(<RouterProvider router={router} />);
}

/** A stored round-one run, as the run POST and the results GET both answer it. */
const RUN_VIEW = {
  event_key: "northline",
  event_name: "Northline Analytics",
  round: 1,
  setting_name: "Wide net",
  team: panel(6, 3, 2),
  email_everyone: panel(300, 40, 30),
  seats_empty: 50,
  event_seats: 60,
  existing_signups: 8,
  round_one: null,
  created_at: "2026-09-21T10:00:00Z",
};

/**
 * Answer by `METHOD path` and call count: `null` falls through to a 404, a
 * thrown `TypeError` stands for a request that never reached the server.
 */
function stubBy(
  answer: (key: string, count: number) => { body: unknown; status?: number } | "offline" | null,
): void {
  const counts = new Map<string, number>();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const key = `${init.method ?? "GET"} ${url.split("?")[0]}`;
      const count = (counts.get(key) ?? 0) + 1;
      counts.set(key, count);
      const found = answer(key, count);
      if (found === "offline") {
        return Promise.reject(new TypeError("offline"));
      }
      const { body, status } = found ?? {
        body: { error: { code: "test_unstubbed", message: key } },
        status: 404,
      };
      return Promise.resolve(new Response(JSON.stringify(body), { status: status ?? 200 }));
    }),
  );
}

function posts(path: string): number {
  return calls.filter((call) => call.init.method === "POST" && call.url === path).length;
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseResults />", () => {
  it("renders the rule-not-confirmed 409 as a state, in the server's words", async () => {
    const sentence =
      "The results rule has not been confirmed for this course yet, so results cannot be run.";
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_rule_not_confirmed", message: sentence } },
        status: 409,
      },
    });
    renderResults();
    await runWith("Wide net");
    await waitFor(() => expect(screen.getByText(sentence)).toBeDefined());
    // A state, not an alert: the calm notice, and the screen still stands.
    expect(document.querySelectorAll('[data-slot="exercise-notice"]').length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /run results/i })).toBeDefined();
  });

  it("renders a locked event as a state too", async () => {
    const sentence = "Your instructor has not opened results for this event yet.";
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: sentence } },
        status: 409,
      },
    });
    renderResults();
    await runWith("Wide net");
    await waitFor(() => expect(screen.getByText(sentence)).toBeDefined());
  });

  it("renders an already-run event as a state, with the spec's own sentence", async () => {
    const sentence = "This team has already run results for this event.";
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_already_run", message: sentence } },
        status: 409,
      },
    });
    renderResults();
    await runWith("Wide net");
    await waitFor(() => expect(screen.getByText(sentence)).toBeDefined());
  });

  it("marks the screen as synthetic and asks the literal paths", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
    });
    renderResults();
    await waitFor(() => expect(screen.getByRole("button", { name: /run results/i })).toBeDefined());
    expect(document.querySelector('[data-slot="synthetic-data-banner"]')).not.toBeNull();
    for (const call of calls) {
      expect(call.url.startsWith("/v1/exercise/")).toBe(true);
      expect(call.url.includes("/api/")).toBe(false);
    }
  });

  it("shows the three panels and the empty seats once a run exists", async () => {
    stub({
      [`GET ${RESULTS}`]: {
        body: {
          event_key: "northline",
          event_name: "Northline Analytics",
          round: 2,
          setting_name: "Wide net",
          team: panel(6, 3, 2),
          email_everyone: panel(300, 40, 30),
          seats_empty: 50,
          event_seats: 60,
          existing_signups: 8,
          round_one: {
            event_key: "northline",
            round: 1,
            setting_name: "First try",
            team: panel(5, 2, 1),
            seats_empty: 51,
            created_at: "2026-09-20T10:00:00Z",
          },
          created_at: "2026-09-21T10:00:00Z",
        },
      },
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
    });
    renderResults();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-seats"]')?.textContent).toContain("50"),
    );
    expect(document.querySelector('[data-slot="exercise-round-one"]')).not.toBeNull();
    // Twice on purpose: the chart's axis label and the accessible table's row
    // header, which is how a projector screen and a screen reader each get it.
    expect(screen.getAllByText(/if you emailed everyone/i).length).toBe(2);
  });

  it("falls back to profile numbers when the list cannot name someone", async () => {
    stub({
      [`GET ${RESULTS}`]: {
        body: {
          event_key: "northline",
          event_name: "Northline Analytics",
          round: 1,
          setting_name: null,
          team: panel(2, 1, 1),
          email_everyone: panel(300, 40, 30),
          seats_empty: 51,
          event_seats: 60,
          existing_signups: 8,
          round_one: null,
          created_at: "2026-09-21T10:00:00Z",
        },
      },
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
    });
    renderResults();
    await waitFor(() =>
      expect(
        document.querySelector('[data-slot="exercise-team-people"]')?.textContent,
      ).toContain("Profile 1"),
    );
  });

  it("offers no way to clear this team's work", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
    });
    renderResults();
    await waitFor(() => expect(screen.getByRole("button", { name: /run results/i })).toBeDefined());
    expect(document.body.textContent?.toLowerCase()).not.toContain("reset");
  });

  it("keeps the run button off until the team chooses its final setting", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: "Not open yet." } },
        status: 409,
      },
    });
    renderResults();
    const run = await screen.findByRole("button", { name: /run results/i });
    expect(isOff(run)).toBe(true);
    // Off means off: a press before choosing sends nothing.
    fireEvent.click(run);
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
    // Every saved setting is offered, and nothing is chosen for the team.
    const picker = screen.getByRole("radiogroup", { name: /final setting/i });
    const radios = within(picker).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((radio) => radio.value)).toEqual(["Wide net", "Only majors"]);
    expect(radios.some((radio) => radio.checked)).toBe(false);

    await runWith("Only majors");

    await waitFor(() => expect(screen.getByText("Not open yet.")).toBeDefined());
    const posted = calls.find((call) => call.init.method === "POST");
    expect(JSON.parse(String(posted?.init.body))).toEqual({ setting_name: "Only majors" });
  });

  it("with no saved settings, tells the team to save one first", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: NONE_SAVED,
    });
    renderResults();
    await waitFor(() =>
      expect(
        document.querySelector('[data-slot="exercise-final-setting"]')?.textContent,
      ).toMatch(/save one on your team's list first, then choose it here/i),
    );
    expect(screen.getByRole("link", { name: "your team's list" })).toBeDefined();
    expect(isOff(screen.getByRole("button", { name: /run results/i }))).toBe(true);
    expect(screen.queryByRole("radiogroup", { name: /final setting/i })).toBeNull();
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
  });

  it("tells a screen reader why the run button is off", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
    });
    renderResults();
    const run = await screen.findByRole("button", { name: /run results/i });
    const hintId = run.getAttribute("aria-describedby");
    expect(hintId).not.toBeNull();
    expect(document.getElementById(String(hintId))?.textContent).toMatch(
      /choose one to run results/i,
    );
  });

  it("clears a final setting deleted elsewhere and reads the settings again", async () => {
    const sentence = "Your team has no saved settings with that name.";
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_setting_unknown", message: sentence } },
        status: 404,
      },
    });
    renderResults();
    await runWith("Wide net");
    await waitFor(() => expect(screen.getByText(sentence)).toBeDefined());
    await waitFor(() =>
      expect(calls.filter((call) => call.url === SETTINGS).length).toBeGreaterThan(1),
    );
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.some((radio) => radio.checked)).toBe(false);
    expect(isOff(screen.getByRole("button", { name: /run results/i }))).toBe(true);
  });

  it("reads no saved settings once the team has run", async () => {
    stub({
      [`GET ${RESULTS}`]: {
        body: {
          event_key: "northline",
          event_name: "Northline Analytics",
          round: 1,
          setting_name: "Wide net",
          team: panel(2, 1, 1),
          email_everyone: panel(300, 40, 30),
          seats_empty: 51,
          event_seats: 60,
          existing_signups: 8,
          round_one: null,
          created_at: "2026-09-21T10:00:00Z",
        },
      },
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: TWO_SAVED,
    });
    renderResults();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-seats"]')).not.toBeNull(),
    );
    expect(calls.some((call) => call.url === SETTINGS)).toBe(false);
    expect(screen.queryByRole("radiogroup", { name: /final setting/i })).toBeNull();
  });

  it("names the people from the list the final setting built", async () => {
    stub({
      [`GET ${RESULTS}`]: {
        body: {
          event_key: "northline",
          event_name: "Northline Analytics",
          round: 1,
          setting_name: "Wide net",
          team: panel(2, 1, 1),
          email_everyone: panel(300, 40, 30),
          seats_empty: 51,
          event_seats: 60,
          existing_signups: 8,
          round_one: null,
          created_at: "2026-09-21T10:00:00Z",
        },
      },
      [LIST]: {
        body: {
          entries: [
            { profile_no: 1, display_name: "Avery Example" },
            { profile_no: 2, display_name: "Blake Example" },
          ],
        },
      },
      [ASKING]: NO_CHOICE,
    });
    renderResults();
    await waitFor(() =>
      expect(
        document.querySelector('[data-slot="exercise-team-people"]')?.textContent,
      ).toContain("Avery Example"),
    );
    const listCall = calls.find((call) => call.url.startsWith(LIST));
    expect(listCall?.url).toBe(`${LIST}?setting=Wide+net`);
  });
});

describe("<ExerciseResults /> once-only presses", () => {
  const REFRESH = "/v1/exercise/workspaces/current/refresh";
  const CHOSEN = {
    body: {
      choice: "required",
      choices: ["required"],
      refreshed: false,
      refreshed_at: null,
      refresh_counts: null,
      first_round_results: true,
      first_round_event_name: "Northline",
    },
  };
  const THREE = { cards_completed: 8, non_responding: 2, topics_added: 5 };
  // A wall-clock time with no zone, so it reads "10:42 AM" wherever this runs.
  const COUNTS = {
    choice: "required",
    ...THREE,
    refreshed_at: "2026-10-16T10:42:00",
    refresh_counts: {
      ...THREE,
      invited_without_card: 22,
      marker_counts_before: { major_only: 166, major_plus_events: 64, completed_card: 70 },
      marker_counts_after: { major_only: 161, major_plus_events: 61, completed_card: 78 },
    },
  };

  it("sends one run for two presses in the same tick", async () => {
    stubBy((key) => {
      if (key === `GET ${RESULTS}`) return NOT_RUN;
      if (key === `POST ${RESULTS}`) return { body: RUN_VIEW };
      if (key === `GET ${LIST}`) return NO_LIST;
      if (key === `GET ${ASKING}`) return NO_CHOICE;
      if (key === `GET ${SETTINGS}`) return TWO_SAVED;
      return null;
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results/i });
    act(() => {
      run.click();
      run.click();
    });
    await waitFor(() => expect(posts(RESULTS)).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(posts(RESULTS)).toBe(1);
  });

  it("shows a confirmed run and keeps Run shut when the re-read cannot be reached", async () => {
    stubBy((key, count) => {
      if (key === `GET ${RESULTS}`) return count === 1 ? NOT_RUN : "offline";
      if (key === `POST ${RESULTS}`) return { body: RUN_VIEW };
      if (key === `GET ${LIST}`) return NO_LIST;
      if (key === `GET ${ASKING}`) return NO_CHOICE;
      if (key === `GET ${SETTINGS}`) return TWO_SAVED;
      return null;
    });
    renderResults();
    await runWith("Wide net");

    await waitFor(() => expect(screen.getByText(/could not be reached/i)).toBeDefined());
    // The run the server confirmed is on screen, and there is no Run to press.
    // Read from D8's sentence, not the figures band: a run made on this screen
    // plays the desk reveal, whose band counts up from 0 after a 1.4s delay,
    // while the sentence carries the server's numbers from the first render.
    expect(
      document.querySelector('[data-slot="exercise-seats-sentence"]')?.textContent,
    ).toContain("50 seats are still open.");
    expect(screen.queryByRole("button", { name: /run results/i })).toBeNull();
    expect(posts(RESULTS)).toBe(1);
  });

  it("keeps a confirmed refresh shut and its counts readable when the re-read cannot be reached", async () => {
    stubBy((key, count) => {
      if (key === `GET ${RESULTS}`) return count === 1 ? { body: RUN_VIEW } : "offline";
      if (key === `POST ${REFRESH}`) return { body: COUNTS };
      if (key === `GET ${LIST}`) return NO_LIST;
      if (key === `GET ${ASKING}`) return CHOSEN;
      return null;
    });
    renderResults();
    const ask = await screen.findByRole("button", { name: /ask them now/i });
    const counts = document.querySelector('[data-slot="exercise-results-refresh-counts"]');
    expect(counts?.getAttribute("role")).toBe("status");
    expect(counts?.textContent).toBe("");

    act(() => {
      ask.click();
      ask.click();
    });

    await waitFor(() => expect(screen.getByText(/could not be reached/i)).toBeDefined());
    expect(posts(REFRESH)).toBe(1);
    // Ann, 2026-10-02: a used-up button says so on itself, with the time.
    const shut = screen.getByRole("button", { name: "Already refreshed at 10:42 AM" });
    expect(isOff(shut)).toBe(true);
    fireEvent.click(shut);
    expect(posts(REFRESH)).toBe(1);
    expect(
      document.querySelector('[data-slot="exercise-results-refresh-counts"]')?.textContent,
    ).toBe(
      "Refresh done at 10:42 AM. 5 people who came to Northline now count as having gone to a similar event. 8 of the 22 invited people with no card completed one. 2 people stopped responding.",
    );
  });

  it("answers a second press from another tab with the time, not an error", async () => {
    // Ann: "Pressing refresh a second time does nothing and says 'Already
    // refreshed at 10:42 AM.'" This tab's read predates the other tab's press.
    let pressed = false;
    stubBy((key) => {
      if (key === `GET ${RESULTS}`) return { body: RUN_VIEW };
      if (key === `GET ${LIST}`) return NO_LIST;
      if (key === `GET ${ASKING}`) {
        return pressed
          ? {
              body: {
                ...CHOSEN.body,
                refreshed: true,
                refreshed_at: COUNTS.refreshed_at,
                refresh_counts: COUNTS.refresh_counts,
              },
            }
          : CHOSEN;
      }
      if (key === `POST ${REFRESH}`) {
        pressed = true;
        return {
          body: {
            error: {
              code: "exercise_already_refreshed",
              message: "Your team has already asked the people it invited.",
            },
          },
          status: 409,
        };
      }
      return null;
    });
    renderResults();
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));
    const shut = await screen.findByRole("button", { name: "Already refreshed at 10:42 AM" });
    expect(isOff(shut)).toBe(true);
    expect(screen.queryByText("Your team has already asked the people it invited.")).toBeNull();
    expect(
      document.querySelector('[data-slot="exercise-results-refresh-counts"]')?.textContent,
    ).toContain("Refresh done at 10:42 AM.");
    fireEvent.click(shut);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(posts(REFRESH)).toBe(1);
  });

  it("takes the screen down when a run is refused for access", async () => {
    stubBy((key) => {
      if (key === `GET ${RESULTS}`) return NOT_RUN;
      if (key === `POST ${RESULTS}`) {
        return {
          body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
          status: 401,
        };
      }
      if (key === `GET ${LIST}`) return NO_LIST;
      if (key === `GET ${ASKING}`) return NO_CHOICE;
      if (key === `GET ${SETTINGS}`) return TWO_SAVED;
      return null;
    });
    renderResults();
    await runWith("Wide net");
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Enter your team number" })).toBeDefined(),
    );
    expect(screen.queryByRole("radiogroup", { name: /final setting/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /run results/i })).toBeNull();
  });
});
