/**
 * Asking for more: the once-only refresh — when it is shut and why, what it
 * says after it is done, and that a press the server confirmed stays shut.
 *
 * Moved, unchanged, out of `ExerciseAskingForMore.test.tsx` (PR #346 review:
 * that file was past the 800-line limit). The helpers above the tests are the
 * same ones, repeated here so each file stands on its own.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONFIRM_GUARD_MS } from "./desk";
import { ExerciseAskingForMore } from "./ExerciseAskingForMore";

// The status line makes three reads of its own and has its own tests
// (`TeamStatusBand.test.tsx`, `TeamStatusBand.pages.test.tsx`). It is left out
// here, so these tests count only the requests this page makes.
vi.mock("./TeamStatusBand", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./TeamStatusBand")>()),
  TeamStatusBand: () => null,
}));

let calls: { url: string; init: RequestInit }[] = [];

const ASKING = "/v1/exercise/workspaces/current/asking-choice";
const REFRESH = "/v1/exercise/workspaces/current/refresh";

/** A local wall-clock time with no zone, so it reads "10:42 AM" in any zone. */
const AT = "2026-10-16T10:42:00";

/**
 * The asking response's facts about the first round and the refresh, as the
 * server sends them for a team that has run round one and not refreshed. A
 * test's own body wins, so each test states only what it is about.
 */
const ASKING_DEFAULTS = {
  refreshed_at: null,
  refresh_counts: null,
  first_round_results: true,
  first_round_event_name: "Northline Career Fair",
};

/** An asking body with the defaults filled in; refusals pass through. */
function asking(body: unknown): unknown {
  if (typeof body !== "object" || body === null || "error" in body) {
    return body;
  }
  return { ...ASKING_DEFAULTS, ...body };
}

/** The full counts shape, from the three a test cares about. */
function counts(three: { cards_completed: number; non_responding: number; topics_added: number }) {
  return {
    ...three,
    invited_without_card: 22,
    marker_counts_before: { major_only: 166, major_plus_events: 64, completed_card: 70 },
    marker_counts_after: {
      major_only: 166 - three.topics_added,
      major_plus_events: 64 + three.topics_added - three.cards_completed,
      completed_card: 70 + three.cards_completed,
    },
  };
}

/** `POST …/refresh`'s answer for three counts. */
function refreshView(three: { cards_completed: number; non_responding: number; topics_added: number }) {
  return { choice: "required", ...three, refreshed_at: AT, refresh_counts: counts(three) };
}

/** The body the fake server sends for one request: asking bodies get the defaults. */
function sent(url: string, body: unknown): string {
  return JSON.stringify(url === ASKING ? asking(body) : body);
}

/** Answer the routes a test names; anything else is a 404. */
function stub(named: Record<string, { body: unknown; status?: number }>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const key = `${init.method ?? "GET"} ${url}`;
      const answer = named[key] ??
        named[url] ?? {
          body: { error: { code: "test_unstubbed", message: key } },
          status: 404,
        };
      return Promise.resolve(new Response(sent(url, answer.body), { status: answer.status ?? 200 }));
    }),
  );
}

function renderAsking() {
  const router = createMemoryRouter(
    [
      { path: "/exercise/asking", element: <ExerciseAskingForMore /> },
      { path: "/exercise/events", element: <p>events</p> },
      { path: "/exercise", element: <p>entry</p> },
    ],
    { initialEntries: ["/exercise/asking"] },
  );
  return render(<RouterProvider router={router} />);
}

/** The "Choose this way" button on the card for one choice (§6.18). */
function chooseButton(label: RegExp): Promise<HTMLElement> {
  return screen.findByRole("button", {
    name: new RegExp(`^choose this way: ${label.source}`, "i"),
  });
}

/**
 * Arm, then confirm: two presses on the same button, the second after the
 * guard that treats a double-click as one press (`CONFIRM_GUARD_MS`).
 */
async function pressTwice(button: HTMLElement): Promise<void> {
  fireEvent.click(button);
  await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
  fireEvent.click(button);
}

/** Whether a desk Button is shut (it stays focusable: `aria-disabled`). */
function isShut(button: HTMLElement): boolean {
  return button.getAttribute("aria-disabled") === "true";
}

/**
 * Answer by `METHOD url` and call count: `"offline"` stands for a request that
 * never reached the server, and `null` falls through to a 404.
 */
function stubBy(
  answer: (key: string, count: number) => { body: unknown; status?: number } | "offline" | null,
): void {
  const counts = new Map<string, number>();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const key = `${init.method ?? "GET"} ${url}`;
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
      return Promise.resolve(new Response(sent(url, body), { status: status ?? 200 }));
    }),
  );
}

function postsTo(url: string): number {
  return calls.filter((call) => call.url === url && call.init.method === "POST").length;
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseAskingForMore /> — the refresh", () => {
  it("keeps the refresh shut until a team has chosen", async () => {
    stub({
      [`GET ${ASKING}`]: { body: { choice: null, choices: ["required"], refreshed: false } },
    });
    renderAsking();
    const ask = await screen.findByRole("button", { name: /ask them now/i });
    expect(isShut(ask)).toBe(true);
    const reason = screen.getByText(/pick a way of asking first/i);
    expect(ask.getAttribute("aria-describedby")).toContain(reason.id);
  });

  it("keeps the once-only refresh counts on screen after the reload settles", async () => {
    // F3. The counts were once held by `AskingPanels`: the refresh called
    // `onChanged()`, the reload dropped the hook to `loading`, and the panel
    // unmounted, taking them with it. Asserting *after* the reload's own
    // request has landed is what catches it.
    //
    // The reload here says `refreshed: true` with no `refresh_counts`, so this
    // browser's copy of its own press is the only one and must stay.
    let refreshedOnServer = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        calls.push({ url, init });
        const method = init.method ?? "GET";
        const json = (body: unknown) =>
          Promise.resolve(new Response(sent(url, body), { status: 200 }));
        if (url === ASKING && method === "GET") {
          return json({ choice: "required", choices: ["required"], refreshed: refreshedOnServer });
        }
        if (url === REFRESH && method === "POST") {
          refreshedOnServer = true;
          return json(refreshView({ cards_completed: 14, non_responding: 3, topics_added: 22 }));
        }
        return Promise.resolve(new Response("{}", { status: 404 }));
      }),
    );
    renderAsking();
    await pressTwice(await screen.findByRole("button", { name: /ask them now/i }));

    // The POST, then the reload's GET, have both been issued.
    await waitFor(() => expect(calls.filter((call) => call.url === REFRESH).length).toBe(1));
    await waitFor(() => expect(calls.filter((call) => call.url === ASKING).length).toBe(2));
    // Let the reload's answer settle before looking.
    await new Promise((resolve) => setTimeout(resolve, 50));

    const band = document.querySelector('[data-slot="exercise-refresh-counts"]');
    expect(band).not.toBeNull();
    expect(band?.textContent).toContain("14");
    expect(band?.textContent).toContain("3");
    expect(band?.textContent).toContain("22");
    expect(document.body.textContent).not.toContain("%");
  });

  it("keeps the once-only button disabled until the reload after it settles", async () => {
    // G3. Fails on the merged code: `run` cleared `pending` in its `finally`
    // as soon as the refresh's own POST resolved, without waiting for the
    // reload it triggers. `asking.refreshed` is still `false` — the stale
    // value from before the refresh — until that reload's GET lands, so
    // there was a real window where the button read enabled and a second
    // click could fire a second, illegal refresh. This test holds that GET
    // open and looks at the button while it is still in flight.
    let releaseSecondGet: (() => void) | null = null;
    let getCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        calls.push({ url, init });
        const method = init.method ?? "GET";
        if (url === ASKING && method === "GET") {
          getCount += 1;
          if (getCount === 1) {
            return Promise.resolve(
              new Response(
                sent(url, { choice: "required", choices: ["required"], refreshed: false }),
                { status: 200 },
              ),
            );
          }
          // The reload triggered by the refresh: held open on purpose.
          return new Promise<Response>((resolve) => {
            releaseSecondGet = () =>
              resolve(
                new Response(
                  sent(url, {
                    choice: "required",
                    choices: ["required"],
                    refreshed: true,
                    refreshed_at: AT,
                  }),
                  { status: 200 },
                ),
              );
          });
        }
        if (url === REFRESH && method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify(
                refreshView({ cards_completed: 1, non_responding: 0, topics_added: 0 }),
              ),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: "test_unstubbed", message: url } }), {
            status: 404,
          }),
        );
      }),
    );

    renderAsking();
    const ask = (await screen.findByRole("button", {
      name: /ask them now/i,
    })) as HTMLButtonElement;
    await pressTwice(ask);

    // The refresh POST has landed and the reload's GET is in flight, held
    // open by `releaseSecondGet`.
    await waitFor(() => expect(calls.some((call) => call.url === REFRESH)).toBe(true));
    await waitFor(() => expect(getCount).toBe(2));

    expect(isShut(ask)).toBe(true);

    releaseSecondGet?.();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Already refreshed at 10:42 AM" })).toBeDefined(),
    );
    expect(calls.filter((call) => call.url === REFRESH).length).toBe(1);
  });

  it("renders a refresh refused before a first round as a state, not an error", async () => {
    stub({
      [`GET ${ASKING}`]: { body: { choice: "required", choices: ["required"], refreshed: false } },
      [`POST ${REFRESH}`]: {
        body: {
          error: {
            code: "exercise_no_first_round_results",
            message: "Run the first event's results before asking anyone for more.",
          },
        },
        status: 409,
      },
      // The read said round one has run; the server disagrees by the time
      // the press lands. Its sentence is still the answer.
    });
    renderAsking();
    await pressTwice(await screen.findByRole("button", { name: /ask them now/i }));
    await waitFor(() =>
      expect(
        screen.getByText("Run the first event's results before asking anyone for more."),
      ).toBeDefined(),
    );
  });

  it("keeps the refresh shut until the team has run its first round, and says why", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: "required",
          choices: ["required"],
          refreshed: false,
          first_round_results: false,
        },
      },
    });
    renderAsking();
    const ask = (await screen.findByRole("button", {
      name: /ask them now/i,
    })) as HTMLButtonElement;
    await waitFor(() =>
      expect(
        screen.getByText("Run your team's results for Northline Career Fair before asking."),
      ).toBeDefined(),
    );
    expect(isShut(ask)).toBe(true);
    // The asking response says it; the screen asks for nothing else.
    expect(calls.map((call) => call.url)).toEqual([ASKING]);
  });

  it("opens the refresh once the first round's results exist", async () => {
    stub({
      [`GET ${ASKING}`]: { body: { choice: "required", choices: ["required"], refreshed: false } },
    });
    renderAsking();
    const ask = (await screen.findByRole("button", {
      name: /ask them now/i,
    })) as HTMLButtonElement;
    await waitFor(() => expect(isShut(ask)).toBe(false));
    expect(screen.queryByText(/before asking\./i)).toBeNull();
    // Which event is round one is the server's answer; no event is read here.
    expect(calls.map((call) => call.url)).toEqual([ASKING]);
  });

  it("names no event when the file has no rounds, and keeps the refresh shut", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: "required",
          choices: ["required"],
          refreshed: false,
          first_round_results: false,
          first_round_event_name: null,
        },
      },
    });
    renderAsking();
    const ask = (await screen.findByRole("button", {
      name: /ask them now/i,
    })) as HTMLButtonElement;
    expect(isShut(ask)).toBe(true);
    expect(
      screen.getByText("Run your team's results for the first event before asking."),
    ).toBeDefined();
  });

  it("shows the stored counts whenever the team has asked, after any reload (B4)", async () => {
    // M2 B4: the counts used to live only in the POST's answer, so a reload, a
    // second browser, or the instructor's every-team button left a team with
    // a shut button and no idea what happened. The asking GET now carries them.
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: "small_reward",
          choices: ["small_reward"],
          refreshed: true,
          refreshed_at: AT,
          refresh_counts: counts({ cards_completed: 9, non_responding: 0, topics_added: 17 }),
        },
      },
    });
    renderAsking();
    const band = await waitFor(() => {
      const found = document.querySelector('[data-slot="exercise-refresh-counts"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    expect(band.textContent).toContain("Cards filled in9");
    expect(band.textContent).toContain("Stopped opening messages0");
    // `topics_added` counts people who gained topics, not topics.
    expect(band.textContent).toContain("Picked up the first event's topics17");
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
  });

  it("says in plain words when the refresh happened and what it changed, after any reload", async () => {
    // Ann, 2026-10-02, checklist section 6, word for word.
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: "small_reward",
          choices: ["small_reward"],
          refreshed: true,
          refreshed_at: AT,
          first_round_event_name: "Northline",
          refresh_counts: counts({ cards_completed: 12, non_responding: 0, topics_added: 9 }),
        },
      },
    });
    renderAsking();
    const summary = await waitFor(() => {
      const found = document.querySelector('[data-slot="exercise-refresh-summary"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    expect(summary.textContent).toContain(
      "Refresh done at 10:42 AM. 9 people who came to Northline now count as having gone to a similar event. 12 of the 22 invited people with no card completed one. 0 people stopped responding.",
    );
    expect(document.body.textContent).not.toContain("%");
  });

  it("shows the how-much-we-know counts for every profile, before and after", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: "small_reward",
          choices: ["small_reward"],
          refreshed: true,
          refreshed_at: AT,
          refresh_counts: counts({ cards_completed: 12, non_responding: 0, topics_added: 9 }),
        },
      },
    });
    renderAsking();
    const strip = await waitFor(() => {
      const found = document.querySelector('[data-slot="exercise-refresh-before-after"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    expect(strip.textContent).toContain("How much we know, all 300 profiles, before and after");
    const lines = [...strip.querySelectorAll("li")];
    expect(lines.map((line) => line.getAttribute("data-marker"))).toEqual([
      "completed_card",
      "major_plus_events",
      "major_only",
    ]);
    // What is drawn, and what a screen reader hears instead of the arrow.
    expect(lines[0].textContent).toBe("Completed card: 70 → 8270 before, 82 after");
    expect(lines[0].querySelector("[aria-hidden='true']")?.textContent).toBe("70 → 82");
    expect(lines[0].querySelector(".sr-only")?.textContent).toBe("70 before, 82 after");
  });

  it("announces the summary once, in a live region that was there before the press", async () => {
    // A notice that mounts already filled is often not read out; a line that
    // is there first and then filled is. The notice itself is not a second one.
    const said =
      "Refresh done at 10:42 AM. 6 people who came to Northline now count as having gone to a similar event. 4 of the 22 invited people with no card completed one. 1 person stopped responding.";
    const view = refreshView({ cards_completed: 4, non_responding: 1, topics_added: 6 });
    const before = {
      choice: "required",
      choices: ["required"],
      refreshed: false,
      first_round_event_name: "Northline",
    };
    let pressed = false;
    stubBy((key) => {
      if (key === `GET ${ASKING}`) {
        return {
          body: pressed
            ? { ...before, refreshed: true, refreshed_at: AT, refresh_counts: view.refresh_counts }
            : before,
        };
      }
      if (key === `POST ${REFRESH}`) {
        pressed = true;
        return { body: view };
      }
      return null;
    });
    renderAsking();
    const ask = await screen.findByRole("button", { name: /ask them now/i });
    const live = document.querySelector('[data-slot="exercise-refresh-announce"]');
    expect(live?.getAttribute("aria-live")).toBe("polite");
    expect(live?.className).toContain("sr-only");
    expect(live?.textContent).toBe("");

    await pressTwice(ask);

    await waitFor(() => expect(live?.textContent).toBe(said));
    expect(document.querySelector('[data-slot="exercise-refresh-announce"]')).toBe(live);
    const summary = document.querySelector('[data-slot="exercise-refresh-summary"]') as HTMLElement;
    expect(summary.textContent).toContain(said);
    expect(within(summary).queryByRole("status")).toBeNull();
    expect(summary.querySelector("[aria-live]")).toBeNull();
  });

  it("answers a second press from another tab with the time, not an error", async () => {
    // Ann: "Pressing refresh a second time does nothing and says 'Already
    // refreshed at 10:42 AM.'" This tab's read predates the other tab's press.
    stubBy((key, count) => {
      if (key === `GET ${ASKING}`) {
        return count === 1
          ? { body: { choice: "required", choices: ["required"], refreshed: false } }
          : {
              body: {
                choice: "required",
                choices: ["required"],
                refreshed: true,
                refreshed_at: AT,
                refresh_counts: counts({ cards_completed: 4, non_responding: 1, topics_added: 6 }),
              },
            };
      }
      if (key === `POST ${REFRESH}`) {
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
    renderAsking();
    await pressTwice(await screen.findByRole("button", { name: /ask them now/i }));
    const shut = await screen.findByRole("button", { name: "Already refreshed at 10:42 AM" });
    expect(isShut(shut)).toBe(true);
    expect(screen.queryByText("Your team has already asked the people it invited.")).toBeNull();
    fireEvent.click(shut);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(postsTo(REFRESH)).toBe(1);
  });

  it("drops this browser's counts once the server says the team has not asked", async () => {
    // An instructor reset after this browser's press: the next read says
    // `refreshed: false`, and the counts from the old press must go with it.
    let refreshedOnServer = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        calls.push({ url, init });
        const method = init.method ?? "GET";
        const json = (body: unknown) =>
          Promise.resolve(new Response(sent(url, body), { status: 200 }));
        if (url === ASKING && method === "GET") {
          return json({
            choice: "required",
            choices: ["required"],
            refreshed: refreshedOnServer,
            refresh_counts: null,
          });
        }
        if (url === REFRESH && method === "POST") {
          return json(refreshView({ cards_completed: 4, non_responding: 1, topics_added: 6 }));
        }
        return Promise.resolve(new Response("{}", { status: 404 }));
      }),
    );
    renderAsking();
    await pressTwice(await screen.findByRole("button", { name: /ask them now/i }));
    // The reload after the press still says "not refreshed": a reset landed.
    await waitFor(() => expect(calls.filter((call) => call.url === ASKING).length).toBe(2));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(document.querySelector('[data-slot="exercise-refresh-counts"]')).toBeNull();
    expect(document.querySelector('[data-slot="exercise-refresh-summary"]')).toBeNull();
    expect(screen.getByRole("button", { name: /ask them now/i })).toBeDefined();
    expect(refreshedOnServer).toBe(false);
  });

  it("shows no counts for a team that has not asked", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: { choice: "required", choices: ["required"], refreshed: false, refresh_counts: null },
      },
    });
    renderAsking();
    await screen.findByRole("button", { name: /ask them now/i });
    expect(document.querySelector('[data-slot="exercise-refresh-counts"]')).toBeNull();
    expect(document.querySelector('[data-slot="exercise-refresh-summary"]')).toBeNull();
  });

  it("says so on the shut button itself, with the time, and reads nothing else", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: { choice: "required", choices: ["required"], refreshed: true, refreshed_at: AT },
      },
    });
    renderAsking();
    const shut = await screen.findByRole("button", { name: "Already refreshed at 10:42 AM" });
    expect(isShut(shut)).toBe(true);
    expect(calls.map((call) => call.url)).toEqual([ASKING]);
  });
});

/** The three choices, nothing chosen, round one run. */
const OPEN_CHOICES = {
  [`GET ${ASKING}`]: {
    body: {
      choice: null,
      choices: ["better_recommendations", "small_reward", "required"],
      refreshed: false,
    },
  },
};

describe("<ExerciseAskingForMore /> — once-only presses the server confirmed", () => {
  const CHOSEN = { choice: "required", choices: ["required"], refreshed: false };
  const COUNTS = refreshView({ cards_completed: 8, non_responding: 2, topics_added: 5 });

  it("sends one refresh POST for two presses in the same tick", async () => {
    stubBy((key) => {
      if (key === `GET ${ASKING}`) return { body: CHOSEN };
      if (key === `POST ${REFRESH}`) return { body: COUNTS };
      return null;
    });
    renderAsking();
    const ask = await screen.findByRole("button", { name: /ask them now/i });
    // The first press asks (issue #321); a double-click is one press and
    // sends nothing.
    act(() => {
      ask.click();
      ask.click();
    });
    expect(postsTo(REFRESH)).toBe(0);
    await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
    act(() => {
      ask.click();
      ask.click();
    });
    await waitFor(() => expect(postsTo(REFRESH)).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(postsTo(REFRESH)).toBe(1);
  });

  it("keeps a confirmed refresh shut, its counts on screen, when the re-read cannot be reached", async () => {
    stubBy((key, count) => {
      if (key === `GET ${ASKING}`) return count === 1 ? { body: CHOSEN } : "offline";
      if (key === `POST ${REFRESH}`) return { body: COUNTS };
      return null;
    });
    renderAsking();
    await pressTwice(await screen.findByRole("button", { name: /ask them now/i }));

    await waitFor(() => expect(screen.getByText(/could not be reached/i)).toBeDefined());
    const shut = screen.getByRole("button", { name: "Already refreshed at 10:42 AM" });
    expect(isShut(shut)).toBe(true);
    fireEvent.click(shut);
    expect(postsTo(REFRESH)).toBe(1);

    const band = document.querySelector('[data-slot="exercise-refresh-counts"]');
    expect(band?.textContent).toContain("Cards filled in8");
    const summary = document.querySelector('[data-slot="exercise-refresh-summary"]') as HTMLElement;
    expect(summary.textContent).toContain(
      "Refresh done at 10:42 AM. 5 people who came to Northline Career Fair now count as having gone to a similar event. 8 of the 22 invited people with no card completed one. 2 people stopped responding.",
    );

    // "Try again" is the only way back to the server, and the server's word wins.
    expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
  });

  it("keeps a confirmed choice fixed when the re-read cannot be reached", async () => {
    stubBy((key, count) => {
      if (key === `GET ${ASKING}`) return count === 1 ? OPEN_CHOICES[`GET ${ASKING}`] : "offline";
      if (key === `POST ${ASKING}`) {
        return {
          body: { choice: "small_reward", choices: OPEN_CHOICES[`GET ${ASKING}`].body.choices, refreshed: false },
        };
      }
      return null;
    });
    renderAsking();
    await pressTwice(await chooseButton(/a small reward/));

    await waitFor(() => expect(screen.getByText(/could not be reached/i)).toBeDefined());
    expect(screen.queryByRole("button", { name: /choose this way/i })).toBeNull();
    expect((screen.getByRole("radio", { name: /a small reward/i }) as HTMLInputElement).checked).toBe(
      true,
    );
    expect(screen.getByText("A team picks once, so these are now fixed.")).toBeDefined();
    expect(postsTo(ASKING)).toBe(1);
    expect(document.querySelector('[data-slot="exercise-asking-confirm-live"]')?.textContent).toBe(
      "Your team chose this: A small reward.",
    );
  });

  it("takes the screen down when a refresh is refused for access", async () => {
    stubBy((key) => {
      if (key === `GET ${ASKING}`) return { body: CHOSEN };
      if (key === `POST ${REFRESH}`) {
        return {
          body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
          status: 401,
        };
      }
      return null;
    });
    renderAsking();
    await pressTwice(await screen.findByRole("button", { name: /ask them now/i }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Enter your team number" })).toBeDefined(),
    );
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByRole("button", { name: /ask them now/i })).toBeNull();
  });
});
