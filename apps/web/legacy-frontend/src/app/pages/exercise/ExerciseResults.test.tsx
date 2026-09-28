import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseResults } from "./ExerciseResults";

const RESULTS_PATH = "/v1/exercise/workspaces/current/events/northline/results";
const LIST_PATH = "/v1/exercise/workspaces/current/events/northline/list";
const ASKING_PATH = "/v1/exercise/workspaces/current/asking-choice";
const REFRESH_PATH = "/v1/exercise/workspaces/current/refresh";

const RESULTS = {
  event_key: "northline",
  event_name: "Northline Analytics",
  round: 1,
  setting_name: null,
  team: {
    invited_profile_nos: [7],
    signed_up_profile_nos: [7],
    attended_profile_nos: [7],
    invited_count: 1,
    signed_up_count: 1,
    attended_count: 1,
  },
  email_everyone: {
    invited_profile_nos: [],
    signed_up_profile_nos: [],
    attended_profile_nos: [],
    invited_count: 300,
    signed_up_count: 30,
    attended_count: 20,
  },
  seats_empty: 9,
  event_seats: 30,
  existing_signups: 20,
  round_one: null,
  created_at: "2026-09-21T10:00:00Z",
};

const LIST = {
  event_key: "northline",
  event_name: "Northline Analytics",
  invite_limit: 30,
  setting_name: null,
  weights: {},
  factor_labels: {},
  entries: [
    {
      rank: 1,
      profile_no: 7,
      display_name: "Rosa Villalobos",
      major: "Marketing",
      class_year: "third",
      marker: "completed_card",
      reason: "Same major.",
      contributing_factor_keys: [],
    },
  ],
  composition: {
    by_major: { dimension: "major", on_list: {}, all_profiles: {} },
    by_class_year: { dimension: "class_year", on_list: {}, all_profiles: {} },
    by_marker: { dimension: "marker", on_list: {}, all_profiles: {} },
    coverage: { missing_majors: [], missing_class_years: [], has_uncovered_group: false },
  },
  unlisted_class_years: [],
  unrankable_profile_count: 0,
};

let calls: { url: string; init: RequestInit }[] = [];

function renderResults() {
  const router = createMemoryRouter(
    [
      { path: "/exercise/events/:eventKey/results", element: <ExerciseResults /> },
      { path: "/exercise", element: <p>entry</p> },
      { path: "/exercise/events/:eventKey", element: <p>matching</p> },
    ],
    { initialEntries: ["/exercise/events/northline/results"] },
  );
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseResults />", () => {
  it("keeps an accepted result run closed and visible when its reload fails", async () => {
    let resultsGets = 0;
    let failReload: (() => void) | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        calls.push({ url, init });
        const method = init.method ?? "GET";
        if (url === RESULTS_PATH && method === "GET") {
          resultsGets += 1;
          if (resultsGets === 1) {
            return Promise.resolve(
              new Response(
                JSON.stringify({
                  error: { code: "exercise_results_not_run", message: "Not run yet." },
                }),
                { status: 404 },
              ),
            );
          }
          return new Promise<Response>((_resolve, reject) => {
            failReload = () => reject(new TypeError("offline"));
          });
        }
        if (url === RESULTS_PATH && method === "POST") {
          return Promise.resolve(new Response(JSON.stringify(RESULTS), { status: 201 }));
        }
        if (url === LIST_PATH) {
          return Promise.resolve(new Response(JSON.stringify(LIST), { status: 200 }));
        }
        if (url === ASKING_PATH) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ choice: null, choices: ["required"], refreshed: false }),
              { status: 200 },
            ),
          );
        }
        return Promise.reject(new Error(`unstubbed ${method} ${url}`));
      }),
    );

    renderResults();
    const run = await screen.findByRole("button", { name: /run results for this event/i });
    fireEvent.click(run);

    await screen.findByText("Rosa Villalobos");
    await waitFor(() => expect(resultsGets).toBe(2));
    expect(screen.queryByRole("button", { name: /run results for this event/i })).toBeNull();
    fireEvent.click(run);
    expect(
      calls.filter((call) => call.url === RESULTS_PATH && call.init.method === "POST"),
    ).toHaveLength(1);

    failReload?.();
    await waitFor(() => expect(screen.getByText(/could not be reached/i)).toBeDefined());
    expect(screen.queryByRole("button", { name: /run results for this event/i })).toBeNull();
  });

  it("keeps an accepted profile refresh closed and its counts visible after reload failure", async () => {
    let resultsGets = 0;
    let failReload: (() => void) | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        calls.push({ url, init });
        const method = init.method ?? "GET";
        if (url === RESULTS_PATH && method === "GET") {
          resultsGets += 1;
          if (resultsGets === 1) {
            return Promise.resolve(new Response(JSON.stringify(RESULTS), { status: 200 }));
          }
          return new Promise<Response>((_resolve, reject) => {
            failReload = () => reject(new TypeError("offline"));
          });
        }
        if (url === LIST_PATH) {
          return Promise.resolve(new Response(JSON.stringify(LIST), { status: 200 }));
        }
        if (url === ASKING_PATH) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ choice: "required", choices: ["required"], refreshed: false }),
              { status: 200 },
            ),
          );
        }
        if (url === REFRESH_PATH && method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                choice: "required",
                cards_completed: 6,
                non_responding: 2,
                topics_added: 4,
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.reject(new Error(`unstubbed ${method} ${url}`));
      }),
    );

    renderResults();
    const ask = await screen.findByRole("button", { name: /ask them now/i });
    fireEvent.click(ask);

    await waitFor(() => expect(resultsGets).toBe(2));
    expect(await screen.findByText(/cards filled in: 6/i)).toBeDefined();
    expect((screen.getByRole("button", { name: /already asked/i }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(ask);
    expect(calls.filter((call) => call.url === REFRESH_PATH)).toHaveLength(1);
    failReload?.();
    await waitFor(() => expect(screen.getByText(/could not be reached/i)).toBeDefined());
    expect(screen.getByText(/cards filled in: 6/i)).toBeDefined();
  });

  it("treats a 401 from the name-list child read as workspace loss", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        calls.push({ url, init });
        if (url === RESULTS_PATH) {
          return Promise.resolve(new Response(JSON.stringify(RESULTS), { status: 200 }));
        }
        if (url === LIST_PATH) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                error: {
                  code: "exercise_workspace_required",
                  message: "Enter your team number to continue.",
                },
              }),
              { status: 401 },
            ),
          );
        }
        return Promise.reject(new Error(`unstubbed ${url}`));
      }),
    );

    renderResults();
    await screen.findByText("Enter your team number to continue.");
    expect(screen.getByRole("link", { name: /enter your team number/i })).toBeDefined();
    expect(screen.queryByText("Rosa Villalobos")).toBeNull();
  });
});
