/**
 * The results lock and the one-run rule, visible to a team (issue #328).
 *
 * Ann's checklist of 2026-10-02, section 5, line by line:
 *
 * - Before the instructor opens results, the button is grey and says
 *   "Results not open yet."
 * - After the instructor opens results, the button becomes active (after a
 *   page reload at most).
 * - The screen asks "Send this list? You get one results run for Northline"
 *   before running.
 * - After the run, the button turns grey and reads "Results already run for
 *   this event."
 * - A second run — by pressing, by reloading, from a second tab — does not
 *   happen, and a message says why.
 *
 * Grey means `aria-disabled` with the reason wired through `aria-describedby`
 * (DESIGN.md §6.3): the button stays focusable, so the reason stays reachable.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONFIRM_GUARD_MS } from "./desk";
import { ExerciseResults } from "./ExerciseResults";

const BASE = "/v1/exercise/workspaces/current";
const EVENTS = `${BASE}/events`;
const RESULTS = `${BASE}/events/northline/results`;
const LIST = `${BASE}/events/northline/list`;
const ASKING = `${BASE}/asking-choice`;
const SETTINGS = `${BASE}/events/northline/settings`;

const EVENT_NAME = "Northline Analytics: Behind the Business";
const NOT_OPEN = `Results for ${EVENT_NAME} are not open yet. Ask your instructor.`;
const QUESTION = `Send this list? You get one results run for ${EVENT_NAME}`;
const ALREADY_RUN = "This team has already run results for this event.";

type Answer = { body: unknown; status?: number };

let calls: { url: string; method: string }[] = [];

/** Answer by `METHOD path`; a function is asked on every call. */
function stub(answers: Record<string, Answer | (() => Answer)>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ url, method });
      const found = answers[`${method} ${url.split("?")[0]}`];
      const answer =
        typeof found === "function"
          ? found()
          : (found ?? { body: { error: { code: "test_unstubbed", message: url } }, status: 404 });
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function events(resultsOpen: boolean, resultsRun: boolean): Answer {
  return {
    body: {
      events: [
        {
          event_key: "past-one",
          name: "A past event",
          topic_tags: [],
          target_majors: [],
          is_exercise_event: false,
          sequence: 1,
          results_open: false,
          results_run: false,
        },
        {
          event_key: "northline",
          name: EVENT_NAME,
          topic_tags: ["technology"],
          target_majors: ["Computer Information Systems"],
          is_exercise_event: true,
          sequence: 11,
          results_open: resultsOpen,
          results_run: resultsRun,
        },
      ],
    },
  };
}

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

const RUN_VIEW = {
  event_key: "northline",
  event_name: EVENT_NAME,
  round: 1,
  setting_name: "Wide net",
  team: panel(6, 3, 2),
  email_everyone: panel(300, 40, 30),
  seats_empty: 50,
  event_seats: 60,
  existing_signups: 8,
  round_one: null,
  invited_profiles: [],
  created_at: "2026-10-16T17:42:00Z",
};

const NOT_RUN: Answer = {
  body: { error: { code: "exercise_results_not_run", message: "No results yet." } },
  status: 404,
};
const NO_CHOICE: Answer = { body: { choice: null, choices: ["required"], refreshed: false } };
const SAVED: Answer = {
  body: {
    event_key: "northline",
    settings: [{ name: "Wide net", weights: {}, created_at: "2026-10-16T17:00:00Z" }],
    max_settings: 3,
  },
};
const NO_LIST: Answer = {
  body: { error: { code: "exercise_setting_unknown", message: "No such setting." } },
  status: 404,
};

/** The reads every state shares; a test adds the events and the results. */
function reads(extra: Record<string, Answer | (() => Answer)>): void {
  stub({ [`GET ${LIST}`]: NO_LIST, [`GET ${ASKING}`]: NO_CHOICE, [`GET ${SETTINGS}`]: SAVED, ...extra });
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

function runPosts(): number {
  return calls.filter((call) => call.method === "POST" && call.url === RESULTS).length;
}

function isGrey(button: HTMLElement): boolean {
  return button.getAttribute("aria-disabled") === "true";
}

/** The text of whatever the button is described by. */
function reasonFor(button: HTMLElement): string {
  return (button.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent ?? "")
    .join(" ");
}

const pastTheGuard = () => new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseResults /> before the instructor opens results", () => {
  it("shows a grey button that says “Results not open yet.” and says why", async () => {
    reads({ [`GET ${EVENTS}`]: events(false, false), [`GET ${RESULTS}`]: NOT_RUN });
    renderResults();

    const button = await screen.findByRole("button", { name: "Results not open yet." });
    expect(isGrey(button)).toBe(true);
    expect(button.hasAttribute("disabled")).toBe(false);
    expect(reasonFor(button)).toContain(NOT_OPEN);
    expect(screen.getByText(NOT_OPEN)).toBeDefined();
    expect(screen.queryByRole("button", { name: /run results/i })).toBeNull();
  });

  it("sends no run when the grey button is pressed, with a setting chosen or not", async () => {
    reads({ [`GET ${EVENTS}`]: events(false, false), [`GET ${RESULTS}`]: NOT_RUN });
    renderResults();
    const button = await screen.findByRole("button", { name: "Results not open yet." });

    fireEvent.click(button);
    fireEvent.click(screen.getByRole("radio", { name: "Wide net" }));
    fireEvent.click(button);
    await pastTheGuard();
    fireEvent.click(button);
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(runPosts()).toBe(0);
  });

  it("becomes active on “Check again” once the instructor has opened results", async () => {
    let open = false;
    reads({ [`GET ${EVENTS}`]: () => events(open, false), [`GET ${RESULTS}`]: NOT_RUN });
    renderResults();
    await screen.findByRole("button", { name: "Results not open yet." });

    open = true;
    const lock = document.querySelector('[data-slot="exercise-results-lock"]') as HTMLElement;
    fireEvent.click(within(lock).getByRole("button", { name: "Check again" }));

    const run = await screen.findByRole("button", { name: /run results for this event/i });
    expect(document.querySelector('[data-slot="exercise-results-lock"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "Results not open yet." })).toBeNull();
    // Off only for the reason the picker gives: no final setting chosen yet.
    expect(isGrey(run)).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "Wide net" }));
    expect(isGrey(run)).toBe(false);
    expect(runPosts()).toBe(0);
  });

  it("is active on a fresh load when results are already open", async () => {
    reads({ [`GET ${EVENTS}`]: events(true, false), [`GET ${RESULTS}`]: NOT_RUN });
    renderResults();

    expect(await screen.findByRole("button", { name: /run results for this event/i })).toBeDefined();
    expect(document.querySelector('[data-slot="exercise-results-lock"]')).toBeNull();
  });
});

describe("<ExerciseResults /> asks before the one run", () => {
  function openAndNotRun(): { ran: () => boolean } {
    let ran = false;
    reads({
      [`GET ${EVENTS}`]: () => events(true, ran),
      [`GET ${RESULTS}`]: () => (ran ? { body: RUN_VIEW } : NOT_RUN),
      [`POST ${RESULTS}`]: () => {
        ran = true;
        return { body: RUN_VIEW, status: 201 };
      },
    });
    return { ran: () => ran };
  }

  it("asks “Send this list? You get one results run for {event}” and sends nothing yet", async () => {
    openAndNotRun();
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results for this event/i });

    fireEvent.click(run);

    expect(run.textContent).toContain(QUESTION);
    expect(
      document.querySelector('[data-slot="exercise-results-run-confirm"]')?.textContent,
    ).toBe("Press again to send this list. Your team cannot run this event a second time.");
    await pastTheGuard();
    expect(runPosts()).toBe(0);
  });

  it("sends the run on the second press, then greys the button for good", async () => {
    const state = openAndNotRun();
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results for this event/i });
    fireEvent.click(run);
    await pastTheGuard();
    fireEvent.click(run);

    const used = await screen.findByRole("button", { name: "Results already run for this event." });
    expect(state.ran()).toBe(true);
    expect(runPosts()).toBe(1);
    expect(isGrey(used)).toBe(true);
    expect(reasonFor(used)).toContain("A team runs results once per event.");
    expect(screen.queryByRole("button", { name: /run results for this event/i })).toBeNull();
    fireEvent.click(used);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(runPosts()).toBe(1);
  });

  it("puts the button back on Escape and sends nothing", async () => {
    openAndNotRun();
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results for this event/i });
    fireEvent.click(run);
    expect(run.textContent).toContain(QUESTION);

    fireEvent.keyDown(run, { key: "Escape" });

    expect(run.textContent).toContain("Run results for this event");
    expect(run.textContent).not.toContain("Send this list?");
    await pastTheGuard();
    expect(runPosts()).toBe(0);
  });

  it("never lets a held Enter become the confirming press", async () => {
    openAndNotRun();
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results for this event/i });
    fireEvent.click(run);
    await pastTheGuard();

    const repeat = fireEvent.keyDown(run, { key: "Enter", repeat: true });

    expect(repeat).toBe(false);
    expect(runPosts()).toBe(0);
  });
});

describe("<ExerciseResults /> after the one run", () => {
  it("shows the grey “Results already run for this event.” on a reload, with the results", async () => {
    reads({ [`GET ${EVENTS}`]: events(true, true), [`GET ${RESULTS}`]: { body: RUN_VIEW } });
    renderResults();

    const used = await screen.findByRole("button", { name: "Results already run for this event." });
    expect(isGrey(used)).toBe(true);
    expect(reasonFor(used)).toContain("A team runs results once per event.");
    expect(document.querySelector('[data-slot="exercise-room"]')).not.toBeNull();
    expect(screen.queryByRole("button", { name: /run results for this event/i })).toBeNull();
    expect(runPosts()).toBe(0);
  });

  it("reads as run, not as closed, when results were closed again after the run", async () => {
    reads({ [`GET ${EVENTS}`]: events(false, true), [`GET ${RESULTS}`]: { body: RUN_VIEW } });
    renderResults();

    expect(
      await screen.findByRole("button", { name: "Results already run for this event." }),
    ).toBeDefined();
    expect(screen.queryByRole("button", { name: "Results not open yet." })).toBeNull();
    expect(document.querySelector('[data-slot="exercise-results-lock"]')).toBeNull();
    expect(document.querySelector('[data-slot="exercise-room"]')).not.toBeNull();
  });

  it("answers a second tab's run with the reason, and lands on the grey button", async () => {
    // This tab loaded before the other tab ran: its button is still live.
    let otherTabRan = false;
    reads({
      [`GET ${EVENTS}`]: () => events(true, otherTabRan),
      [`GET ${RESULTS}`]: () => (otherTabRan ? { body: RUN_VIEW } : NOT_RUN),
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_already_run", message: ALREADY_RUN } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results for this event/i });
    otherTabRan = true;

    fireEvent.click(run);
    await pastTheGuard();
    fireEvent.click(run);

    await waitFor(() => expect(screen.getByText(ALREADY_RUN)).toBeDefined());
    const used = await screen.findByRole("button", { name: "Results already run for this event." });
    expect(isGrey(used)).toBe(true);
    expect(screen.getByText(ALREADY_RUN)).toBeDefined();
    expect(document.querySelector('[data-slot="exercise-room"]')).not.toBeNull();
    expect(runPosts()).toBe(1);
  });

  it("lands on the grey not-open button when results were closed under a live tab", async () => {
    let closed = false;
    reads({
      [`GET ${EVENTS}`]: () => events(!closed, false),
      [`GET ${RESULTS}`]: NOT_RUN,
      [`POST ${RESULTS}`]: {
        body: { error: { code: "exercise_results_locked", message: NOT_OPEN } },
        status: 409,
      },
    });
    renderResults();
    fireEvent.click(await screen.findByRole("radio", { name: "Wide net" }));
    const run = screen.getByRole("button", { name: /run results for this event/i });
    closed = true;

    fireEvent.click(run);
    await pastTheGuard();
    fireEvent.click(run);

    const grey = await screen.findByRole("button", { name: "Results not open yet." });
    expect(isGrey(grey)).toBe(true);
    // Said once, in the lock panel, not twice.
    expect(screen.getAllByText(NOT_OPEN)).toHaveLength(1);
    expect(runPosts()).toBe(1);
  });
});
