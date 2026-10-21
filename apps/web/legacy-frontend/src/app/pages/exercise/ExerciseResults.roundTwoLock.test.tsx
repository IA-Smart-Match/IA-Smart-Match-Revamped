/** The Harbor lock names its real cause: no Round 1 results, or the instructor has not opened it. */
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseResults } from "./ExerciseResults";

const BASE = "/v1/exercise/workspaces/current";
const NO_ROUND_ONE = "Round 2 opens after your team has its Round 1 results.";
const WAIT = "Your instructor has not opened results yet.";

function event(key: string, sequence: number, open: boolean, run: boolean) {
  return {
    event_key: key, name: key, topic_tags: [], target_majors: [], is_exercise_event: true,
    sequence, results_open: open, results_run: run,
  };
}

function stubWith(northlineRun: boolean): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = url.split("?")[0];
      const missing = { error: { code: "exercise_setting_unknown", message: "No such setting." } };
      const answers: Record<string, unknown> = {
        [`${BASE}/events`]: {
          events: [event("northline", 1, true, northlineRun), event("harbor", 2, false, false)],
        },
        [`${BASE}/events/harbor/results`]: null,
        [`${BASE}/asking-choice`]: { choice: null, choices: ["required"], refreshed: false },
        [`${BASE}/events/harbor/settings`]: { event_key: "harbor", settings: [], max_settings: 3 },
      };
      const found = path in answers;
      return Promise.resolve(
        new Response(JSON.stringify(found ? answers[path] : missing), { status: found ? 200 : 404 }),
      );
    }),
  );
}

function renderHarbor() {
  const router = createMemoryRouter(
    [{ path: "/exercise/events/:eventKey/results", element: <ExerciseResults /> }],
    { initialEntries: ["/exercise/events/harbor/results"] },
  );
  return render(<RouterProvider router={router} />);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Harbor results lock", () => {
  it("says Round 1 results are missing when the team has not run Northline", async () => {
    stubWith(false);
    renderHarbor();
    expect(await screen.findByText(NO_ROUND_ONE)).toBeDefined();
    expect(screen.queryByText(new RegExp(WAIT))).toBeNull();
  });

  it("keeps the wait-for-instructor sentence once Round 1 is run", async () => {
    stubWith(true);
    renderHarbor();
    expect(await screen.findByText(new RegExp(WAIT))).toBeDefined();
    expect(screen.queryByText(NO_ROUND_ONE)).toBeNull();
  });
});
