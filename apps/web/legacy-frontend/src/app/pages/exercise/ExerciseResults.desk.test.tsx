/**
 * The results screen on the invitation desk (DESIGN.md §6.13, §6.14, §7.8).
 *
 * - §6.13: the final setting is chosen from radio cards, each naming the
 *   setting and its four weights in Ann's words (`factor_labels` from the list
 *   the screen already reads), never from a `<select>`.
 * - §6.14: a locked event is the lock panel — "Results are closed" and the
 *   server's sentence, in the seating chart's place. It has no action: teams
 *   have no read of the lock, and the Run button stays the only retry.
 *   Nothing is red.
 * - The server's 422 `exercise_final_setting_required` is shown in its words.
 * - §5.1: the seats fill only on the first render after a run succeeds.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { stubReducedMotion } from "./desk/testMatchMedia";
import { CONFIRM_GUARD_MS } from "./desk";
import { ExerciseResults } from "./ExerciseResults";

/**
 * Send the run: the first press arms the button ("Send this list? You get one
 * results run for …"), the second sends it. The pause clears the guard that
 * treats a double-click as one press (`CONFIRM_GUARD_MS`).
 */
async function pressRun(): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: /run results/i }));
  await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
  fireEvent.click(screen.getByRole("button", { name: /send this list/i }));
}

let calls: { url: string; init: RequestInit }[] = [];

type Answer = { body: unknown; status?: number };

function stub(answers: Record<string, Answer | (() => Answer)>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const path = url.split("?")[0];
      const found = answers[`${init.method ?? "GET"} ${path}`] ?? answers[path];
      const answer = (typeof found === "function" ? found() : found) ?? {
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

const WEIGHTS = {
  same_major: 0.6,
  stated_interest_overlap: 0.15,
  career_goal_fit: 0.15,
  past_event_topic_overlap: 0.1,
};

const SAVED: Answer = {
  body: {
    event_key: "northline",
    settings: [
      { name: "Major first", weights: WEIGHTS, created_at: "2026-09-20T10:00:00Z" },
      { name: "Balanced", weights: WEIGHTS, created_at: "2026-09-20T10:05:00Z" },
    ],
    max_settings: 3,
  },
};

const LABELLED_LIST: Answer = {
  body: {
    entries: [],
    weights: WEIGHTS,
    factor_labels: {
      same_major: "same major",
      stated_interest_overlap: "said they are interested in this topic",
      career_goal_fit: "career goal fits this event",
      past_event_topic_overlap: "went to similar events before",
    },
  },
};

const NOT_RUN: Answer = { body: null };

const NO_CHOICE: Answer = { body: { choice: null, choices: ["required"], refreshed: false } };

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

const RUN_DONE = {
  event_key: "northline",
  event_name: "Northline Analytics",
  round: 1,
  setting_name: "Major first",
  team: panel(30, 8, 6),
  email_everyone: panel(300, 40, 30),
  seats_empty: 46,
  event_seats: 60,
  existing_signups: 8,
  round_one: null,
  created_at: "2026-09-26T10:00:00Z",
};

function renderResults() {
  const router = createMemoryRouter(
    [
      { path: "/exercise/events/:eventKey/results", element: <ExerciseResults /> },
      { path: "/exercise/events/:eventKey", element: <p>list</p> },
      { path: "/exercise/asking", element: <p>asking</p> },
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

describe("<ExerciseResults /> final-setting picker (§6.13)", () => {
  it("offers the saved settings as radio cards, none chosen, each with its weights", async () => {
    stub({ [`GET ${RESULTS}`]: NOT_RUN, [LIST]: LABELLED_LIST, [ASKING]: NO_CHOICE, [SETTINGS]: SAVED });
    renderResults();

    const group = await screen.findByRole("radiogroup", { name: "Your team's final setting" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(within(group).getByRole("radio", { name: "Major first" })).toBeDefined();
    expect(within(group).getByRole("radio", { name: "Balanced" })).toBeDefined();
    for (const radio of radios) {
      expect((radio as HTMLInputElement).checked).toBe(false);
    }
    const card = within(group).getByRole("radio", { name: "Major first" }).closest("label");
    expect(card?.textContent).toContain("same major");
    expect(card?.textContent).toContain("0.60");
    expect(card?.textContent).toContain("went to similar events before");
    expect(card?.textContent).toContain("0.10");
  });

  it("names no weight when the list's words are not available", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: { body: { error: { code: "exercise_workspace_required", message: "x" } }, status: 401 },
      [ASKING]: NO_CHOICE,
      [SETTINGS]: SAVED,
    });
    renderResults();

    const radio = await screen.findByRole("radio", { name: "Major first" });
    expect(radio.closest("label")?.textContent).not.toContain("same_major");
    expect(radio.closest("label")?.textContent).not.toContain("0.60");
  });

  it("shows the server's sentence when the run says no final setting was sent", async () => {
    const sentence = "Choose your team's final setting before running results.";
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: LABELLED_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_final_setting_required", message: sentence } },
        status: 422,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Balanced" }));
    await pressRun();

    await waitFor(() => expect(screen.getByText(sentence)).toBeDefined());
    expect(screen.getByText(sentence).closest('[data-slot="exercise-notice"]')).not.toBeNull();
  });
});

describe("<ExerciseResults /> lock panel (§6.14)", () => {
  const LOCKED = "Your instructor has not opened results for this event yet.";

  it("shows a locked event as the calm lock panel, with a read as its only action", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: LABELLED_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: LOCKED } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Major first" }));
    await pressRun();

    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-results-lock"]')).not.toBeNull(),
    );
    const lock = document.querySelector('[data-slot="exercise-results-lock"]') as HTMLElement;
    expect(lock.textContent).toContain("Results are closed");
    expect(lock.textContent).toContain(LOCKED);
    // The team can read the lock now (§6.14, amended 2026-10-06), so the
    // panel offers "Check again": a read, never the one-time run.
    const actions = within(lock).queryAllByRole("button");
    expect(actions.map((button) => button.textContent)).toEqual(["Check again"]);
    expect(within(lock).queryAllByRole("link")).toHaveLength(0);
    fireEvent.click(actions[0]);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(
      calls.filter((call) => call.init.method === "POST" && call.url === RESULTS),
    ).toHaveLength(1);
  });

  it("announces only the chip and the sentence, not the whole panel", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: LABELLED_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: LOCKED } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Major first" }));
    await pressRun();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-results-lock"]')).not.toBeNull(),
    );

    const lock = document.querySelector('[data-slot="exercise-results-lock"]') as HTMLElement;
    expect(lock.getAttribute("role")).toBeNull();
    const status = within(lock).getByRole("status");
    expect(status.textContent).toBe(`Results are closed${LOCKED}`);
    expect(status.querySelector("svg:not([aria-hidden='true'])")).toBeNull();
  });

  it("leaves the confirmed Run button as the only control that sends the run", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: LABELLED_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: LOCKED } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Major first" }));
    await pressRun();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-results-lock"]')).not.toBeNull(),
    );

    // Press every button now on screen — the grey "Results not open yet." and
    // "Check again" among them: none of them posts the run.
    for (const button of screen.getAllByRole("button")) {
      fireEvent.click(button);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(
      calls.filter((call) => call.init.method === "POST" && call.url === RESULTS),
    ).toHaveLength(1);
  });

  it("puts the lock panel in the seating chart's place, above the picker (§7.8)", async () => {
    stub({
      [`GET ${RESULTS}`]: NOT_RUN,
      [LIST]: LABELLED_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: SAVED,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: LOCKED } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Major first" }));
    await pressRun();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-results-lock"]')).not.toBeNull(),
    );

    const lock = document.querySelector('[data-slot="exercise-results-lock"]') as HTMLElement;
    const picker = document.querySelector('[data-slot="exercise-final-setting"]') as HTMLElement;
    expect(lock.compareDocumentPosition(picker) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows no lock panel before the team has tried to run", async () => {
    stub({ [`GET ${RESULTS}`]: NOT_RUN, [LIST]: LABELLED_LIST, [ASKING]: NO_CHOICE, [SETTINGS]: SAVED });
    renderResults();
    await screen.findByRole("radiogroup");

    expect(document.querySelector('[data-slot="exercise-results-lock"]')).toBeNull();
  });
});

describe("<ExerciseResults /> reveal (§5.1)", () => {
  it("plays the seat fill after a run succeeds on this screen", async () => {
    stubReducedMotion(false);
    let ran = false;
    stub({
      [`GET ${RESULTS}`]: () => (ran ? { body: RUN_DONE } : NOT_RUN),
      [`POST ${RESULTS}`]: () => {
        ran = true;
        return { body: RUN_DONE };
      },
      [LIST]: LABELLED_LIST,
      [ASKING]: NO_CHOICE,
      [SETTINGS]: SAVED,
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Major first" }));
    await pressRun();

    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-room"]')).not.toBeNull(),
    );
    expect(
      document.querySelectorAll('[data-slot="ce-seat"][data-animate="true"]').length,
    ).toBeGreaterThan(0);
  });

  it("shows the final state at once when the run was already there", async () => {
    stubReducedMotion(false);
    stub({ [`GET ${RESULTS}`]: { body: RUN_DONE }, [LIST]: LABELLED_LIST, [ASKING]: NO_CHOICE });
    renderResults();

    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-room"]')).not.toBeNull(),
    );
    expect(document.querySelectorAll('[data-slot="ce-seat"][data-animate="true"]').length).toBe(0);
  });
});
