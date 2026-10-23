/**
 * The status line on the team's four pages, with the pages' own presses
 * (issue #321).
 *
 * Since Janice's revision of 2026-10-23 the line says only the team and the
 * way back, above the title, with the round banner between it and the title.
 * What the team has done is said by the pages themselves: "You chose: …",
 * the asking summary, "Run at …".
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
  existing_attended: 8,
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

function follows(first: Element, second: Element): boolean {
  return Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);
}

function band(): HTMLElement {
  return document.querySelector('[data-slot="exercise-team-status"]') as HTMLElement;
}

async function pressTwice(button: HTMLElement): Promise<void> {
  fireEvent.click(button);
  await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
  fireEvent.click(button);
}

describe("every team page carries the status line", () => {
  it.each(["/exercise/events", "/exercise/events/northline", "/exercise/events/northline/results", "/exercise/asking"])(
    "%s: team and the way back only, above the title",
    async (path) => {
      renderAt(path);
      await screen.findByText("You are Team 3");
      expect(screen.getByRole("link", { name: "Not your team? Pick again" })).toBeDefined();
      expect(band().textContent).not.toMatch(/Round|Results|Way of asking|Asked for more|Data file/);
      expect(follows(band(), screen.getByRole("heading", { level: 1 }))).toBe(true);
    },
  );

  it.each(["/exercise/events/northline", "/exercise/events/northline/results", "/exercise/asking"])(
    "%s: the round banner sits between the team line and the title",
    async (path) => {
      renderAt(path);
      await screen.findByText("You are Team 3");
      const banner = await waitFor(() => {
        const found = document.querySelector('[data-slot="exercise-round-banner"]');
        expect(found).not.toBeNull();
        return found as HTMLElement;
      });
      expect(follows(band(), banner)).toBe(true);
      expect(follows(banner, screen.getByRole("heading", { level: 1 }))).toBe(true);
    },
  );
});

describe("the status line follows the page's own presses", () => {
  it("says “You chose: …” once the way of asking is chosen", async () => {
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

    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-asking-chosen"]')).not.toBeNull(),
    );
    const chosen = document.querySelector('[data-slot="exercise-asking-chosen"]');
    // A8: the time is this browser's own clock, so it is matched, not fixed.
    expect(chosen?.textContent).toMatch(
      /^You chose: A small reward( at \d{1,2}:\d{2}:\d{2} [AP]M)?\. Your team picks once, so this choice is final\.$/,
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

  it("shuts the results button after the run, and the page says when it ran", async () => {
    server.open = true;
    extra[`POST ${RESULTS}`] = () => {
      server.run = true;
      return { body: RUN_VIEW, status: 201 };
    };
    renderAt("/exercise/events/northline/results");
    await screen.findByText("You are Team 3");

    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results/i });
    await pressTwice(run);

    const shut = await screen.findByRole("button", { name: "Results already run for this event." });
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
  });
});
