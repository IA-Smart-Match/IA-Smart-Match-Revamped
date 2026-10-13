/**
 * The status line on the team's four pages, with the pages' own presses
 * (issue #321).
 *
 * Ann's checklist of 2026-10-02: "Each team page has a status line at the
 * top, always visible, showing: team number, which event, round one or round
 * two, results used or not, way of asking chosen or not, refresh done or
 * not." Section 6: "After choosing, a message says “You chose: small reward,”
 * and the status line shows it."
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONFIRM_GUARD_MS } from "./desk";
import { ExerciseAskingForMore } from "./ExerciseAskingForMore";
import { ExerciseEventPicker } from "./ExerciseEventPicker";
import { ExerciseMatching } from "./ExerciseMatching";
import { ExerciseResults } from "./ExerciseResults";

const BASE = "/v1/exercise/workspaces/current";
const EVENTS = `${BASE}/events`;
const ASKING = `${BASE}/asking-choice`;
const RESULTS = `${BASE}/events/northline/results`;
const SETTINGS = `${BASE}/events/northline/settings`;

/** A local wall-clock time with no zone, so it reads "10:42 AM" in any zone. */
const AT = "2026-10-16T10:42:00";

type Answer = { body: unknown; status?: number };

/** What the fake server holds; a test changes it as its presses land. */
interface Server {
  open: boolean;
  run: boolean;
  choice: string | null;
  refreshed: boolean;
}

let server: Server;
let extra: Record<string, Answer | (() => Answer)>;
/** While true, no request lands: the network is down. */
let offline: boolean;

function round(key: string, name: string, sequence: number, open: boolean, run: boolean): object {
  return {
    event_key: key,
    name,
    topic_tags: [],
    target_majors: [],
    is_exercise_event: true,
    sequence,
    description: null,
    results_open: open,
    results_run: run,
  };
}

function panel(count: number): object {
  const nos = Array.from({ length: count }, (_, index) => index + 1);
  return {
    invited_profile_nos: nos,
    signed_up_profile_nos: nos,
    attended_profile_nos: nos,
    invited_count: count,
    signed_up_count: count,
    attended_count: count,
  };
}

const RUN_VIEW = {
  event_key: "northline",
  event_name: "Northline",
  round: 1,
  setting_name: "Wide net",
  team: panel(3),
  email_everyone: panel(30),
  seats_empty: 49,
  event_seats: 60,
  existing_signups: 8,
  round_one: null,
  invited_profiles: [],
  created_at: AT,
};

function answer(key: string): Answer {
  const named = extra[key];
  if (named !== undefined) {
    return typeof named === "function" ? named() : named;
  }
  if (key === `GET ${BASE}`) {
    return { body: { team_number: 3, dataset_label: "October file", invite_limit: 30 } };
  }
  if (key === `GET ${EVENTS}`) {
    return {
      body: {
        events: [
          round("northline", "Northline", 11, server.open, server.run),
          round("harbor", "Harbor", 12, false, false),
        ],
      },
    };
  }
  if (key === `GET ${ASKING}`) {
    return {
      body: {
        choice: server.choice,
        choices: ["better_recommendations", "small_reward", "required"],
        refreshed: server.refreshed,
        refreshed_at: server.refreshed ? AT : null,
        refresh_counts: null,
        first_round_results: true,
        first_round_event_name: "Northline",
      },
    };
  }
  if (key === `GET ${RESULTS}`) {
    return server.run
      ? { body: RUN_VIEW }
      : { body: null };
  }
  if (key === `GET ${SETTINGS}`) {
    return {
      body: {
        event_key: "northline",
        settings: [{ name: "Wide net", weights: {}, created_at: AT }],
        max_settings: 3,
      },
    };
  }
  return { body: { error: { code: "test_unstubbed", message: key } }, status: 404 };
}

beforeEach(() => {
  server = { open: false, run: false, choice: null, refreshed: false };
  extra = {};
  offline = false;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      if (offline) {
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      const found = answer(`${init.method ?? "GET"} ${url.split("?")[0]}`);
      return Promise.resolve(new Response(JSON.stringify(found.body), { status: found.status ?? 200 }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      { path: "/exercise/events", element: <ExerciseEventPicker /> },
      { path: "/exercise/events/:eventKey", element: <ExerciseMatching /> },
      { path: "/exercise/events/:eventKey/results", element: <ExerciseResults /> },
      { path: "/exercise/asking", element: <ExerciseAskingForMore /> },
      { path: "/exercise", element: <p>entry</p> },
    ],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

function value(key: string): string | null {
  return document.querySelector(`[data-status="${key}"]`)?.textContent ?? null;
}

/** The status line sits above the page's own body, under the one `h1`. */
function bandIsUnderTheHeading(): boolean {
  const heading = screen.getByRole("heading", { level: 1 });
  const band = document.querySelector('[data-slot="exercise-team-status"]') as HTMLElement;
  return Boolean(heading.compareDocumentPosition(band) & Node.DOCUMENT_POSITION_FOLLOWING);
}

async function pressTwice(button: HTMLElement): Promise<void> {
  fireEvent.click(button);
  await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
  fireEvent.click(button);
}

describe("every team page carries the status line", () => {
  it.each([
    ["/exercise/events", null],
    ["/exercise/events/northline", "Round 1 · Northline (this page):"],
    ["/exercise/events/northline/results", "Round 1 · Northline (this page):"],
    ["/exercise/asking", null],
  ])("%s", async (path, marked) => {
    renderAt(path);
    await screen.findByText("You are Team 3");
    expect(bandIsUnderTheHeading()).toBe(true);
    expect(value("round-1")).toBe("Results not used yet (not open yet)");
    expect(value("round-2")).toBe("Results not used yet (not open yet)");
    expect(value("asking")).toBe("Not chosen yet");
    expect(value("refresh")).toBe("Not done yet");
    expect(screen.getByText(marked ?? "Round 1 · Northline:")).toBeDefined();
    // Round two is never the page here, so it is never marked.
    expect(screen.getByText("Round 2 · Harbor:")).toBeDefined();
  });

  it("shows where the team is after a reload in the middle of round two", async () => {
    server = { open: true, run: true, choice: "required", refreshed: true };
    const first = renderAt("/exercise/events");
    await screen.findByText("You are Team 3");
    first.unmount();

    renderAt("/exercise/events");
    await screen.findByText("You are Team 3");
    expect(value("round-1")).toBe("Results used");
    expect(value("asking")).toBe("Required");
    expect(value("refresh")).toBe("Done at 10:42 AM");
  });
});

describe("the status line follows the page's own presses", () => {
  it("shows the way of asking once it is chosen, beside “You chose: …”", async () => {
    extra[`POST ${ASKING}`] = () => {
      server.choice = "small_reward";
      return { body: { choice: "small_reward" } };
    };
    renderAt("/exercise/asking");
    await screen.findByText("You are Team 3");
    expect(document.querySelector('[data-slot="exercise-asking-chosen"]')).toBeNull();

    await pressTwice(
      await screen.findByRole("button", { name: /^choose this way: a small reward/i }),
    );

    await waitFor(() => expect(value("asking")).toBe("A small reward"));
    const chosen = document.querySelector('[data-slot="exercise-asking-chosen"]');
    expect(chosen?.textContent).toBe(
      "You chose: A small reward. A team picks once, so these are now fixed.",
    );
  });

  it("still says what was chosen after a reload", async () => {
    server.choice = "small_reward";
    renderAt("/exercise/asking");
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-asking-chosen"]')?.textContent).toContain(
        "You chose: A small reward.",
      ),
    );
  });

  it("shows the refresh as done, with its time, once the team has asked", async () => {
    server.choice = "required";
    extra[`POST ${BASE}/refresh`] = () => {
      server.refreshed = true;
      return {
        body: {
          choice: "required",
          cards_completed: 1,
          non_responding: 0,
          topics_added: 1,
          refreshed_at: AT,
          refresh_counts: {
            cards_completed: 1,
            non_responding: 0,
            topics_added: 1,
            invited_without_card: 2,
            marker_counts_before: {},
            marker_counts_after: {},
          },
        },
      };
    };
    renderAt("/exercise/asking");
    await screen.findByText("You are Team 3");
    expect(value("refresh")).toBe("Not done yet");

    await pressTwice(await screen.findByRole("button", { name: "Ask them now" }));
    await waitFor(() => expect(value("refresh")).toBe("Done at 10:42 AM"));
  });

  it("shows results as used after the run, and the page says when it ran", async () => {
    server.open = true;
    extra[`POST ${RESULTS}`] = () => {
      server.run = true;
      return { body: RUN_VIEW, status: 201 };
    };
    renderAt("/exercise/events/northline/results");
    await screen.findByText("You are Team 3");
    expect(value("round-1")).toBe("Results not used yet (open now)");

    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results/i });
    await pressTwice(run);

    await waitFor(() => expect(value("round-1")).toBe("Results used"));
    const shut = screen.getByRole("button", { name: "Results already run for this event." });
    expect(shut.getAttribute("aria-disabled")).toBe("true");
    expect(document.querySelector('[data-slot="exercise-results-run-at"]')?.textContent).toBe(
      "Run at 10:42 AM. ",
    );
  });
});

describe("“Check again” says what it found", () => {
  it("says results are still not open, with the time it checked", async () => {
    renderAt("/exercise/events/northline/results");
    const check = await screen.findByRole("button", { name: "Check again" });
    const said = (): string =>
      document.querySelector('[data-slot="exercise-results-checked"]')?.textContent ?? "";
    expect(said()).toBe("");

    fireEvent.click(check);
    // To the second: a second press in the same minute must not read the same.
    await waitFor(() =>
      expect(said()).toMatch(
        /^Checked at \d{1,2}:\d{2}:\d{2} (AM|PM)\. Results are still not open\.$/,
      ),
    );
  });

  it("does not say it checked when the read could not be made: it says that instead", async () => {
    renderAt("/exercise/events/northline/results");
    const check = await screen.findByRole("button", { name: "Check again" });
    const said = (): string =>
      document.querySelector('[data-slot="exercise-results-checked"]')?.textContent ?? "";

    offline = true;
    fireEvent.click(check);
    await waitFor(() =>
      expect(said()).toBe("The exercise could not be reached. Check the connection and try again."),
    );
    // Nothing was read, so nothing is known about the lock.
    expect(said()).not.toContain("Checked at");
    expect(said()).not.toContain("still not open");

    // The next check that lands says what it found.
    offline = false;
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() =>
      expect(said()).toMatch(
        /^Checked at \d{1,2}:\d{2}:\d{2} (AM|PM)\. Results are still not open\.$/,
      ),
    );
  });

  it("says nothing of the kind once results have opened: the button is live instead", async () => {
    renderAt("/exercise/events/northline/results");
    const check = await screen.findByRole("button", { name: "Check again" });
    server.open = true;
    fireEvent.click(check);

    await waitFor(() => expect(screen.queryByRole("button", { name: "Check again" })).toBeNull());
    expect(document.querySelector('[data-slot="exercise-results-checked"]')).toBeNull();
    await waitFor(() => expect(value("round-1")).toBe("Results not used yet (open now)"));
  });
});
