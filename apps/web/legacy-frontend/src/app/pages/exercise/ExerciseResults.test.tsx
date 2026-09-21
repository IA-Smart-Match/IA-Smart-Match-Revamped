/**
 * Results: the 409 that is the current state of this deployment.
 *
 * `POST …/results` answers `exercise_results_rule_not_confirmed` today,
 * because OQ-CE-03 is open and the simulation coefficients are `None`. PR #190
 * is explicit that this is the route working. The first test below is
 * therefore the most important one on this screen: that sentence has to reach
 * the projector as a calm state, in the server's own words.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_rule_not_confirmed", message: sentence } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("button", { name: /run results/i }));
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
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: sentence } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("button", { name: /run results/i }));
    await waitFor(() => expect(screen.getByText(sentence)).toBeDefined());
  });

  it("renders an already-run event as a state, with the spec's own sentence", async () => {
    const sentence = "This team has already run results for this event.";
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: NO_LIST,
      [ASKING]: NO_CHOICE,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_already_run", message: sentence } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("button", { name: /run results/i }));
    await waitFor(() => expect(screen.getByText(sentence)).toBeDefined());
  });

  it("marks the screen as synthetic and asks the literal paths", async () => {
    stub({ [`GET ${RESULTS}`]: NOT_RUN, [LIST]: NO_LIST, [ASKING]: NO_CHOICE });
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
    stub({ [`GET ${RESULTS}`]: NOT_RUN, [LIST]: NO_LIST, [ASKING]: NO_CHOICE });
    renderResults();
    await waitFor(() => expect(screen.getByRole("button", { name: /run results/i })).toBeDefined());
    expect(document.body.textContent?.toLowerCase()).not.toContain("reset");
  });
});
