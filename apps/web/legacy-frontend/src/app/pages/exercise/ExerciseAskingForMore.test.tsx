/**
 * Asking for more: the server's three choices, and its refusals as states.
 *
 * The set of choices is the server's — a fourth one appears on screen the day
 * the API offers it. Only the wording of each is local, because the asking
 * response carries no label per choice the way the list response carries
 * `factor_labels`.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONFIRM_GUARD_MS } from "./desk";
import { stubReducedMotion } from "./desk/testMatchMedia";
import { ExerciseAskingForMore } from "./ExerciseAskingForMore";

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

describe("<ExerciseAskingForMore />", () => {
  it("marks the screen as synthetic", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: { choice: null, choices: ["better_recommendations"], refreshed: false },
      },
    });
    renderAsking();
    await screen.findByRole("radio", { name: /promise better recommendations/i });
    expect(document.querySelector('[data-slot="synthetic-data-banner"]')).not.toBeNull();
  });

  it("offers exactly the choices the server sent, and asks the literal path", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: null,
          choices: ["better_recommendations", "small_reward", "required"],
          refreshed: false,
        },
      },
    });
    renderAsking();
    await waitFor(() =>
      expect(
        document.querySelectorAll('[data-slot="exercise-asking-choices"] button').length,
      ).toBe(3),
    );
    expect(calls[0].url).toBe(ASKING);
    expect(calls[0].url.includes("/api/")).toBe(false);
  });

  it("shows a choice the server invents rather than swallowing it", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: { choice: null, choices: ["a_fourth_way"], refreshed: false },
      },
    });
    renderAsking();
    await waitFor(() => expect(screen.getByRole("radio", { name: /a_fourth_way/ })).toBeDefined());
    expect(await chooseButton(/a_fourth_way/)).toBeDefined();
  });

  it("sends X-Exercise-Request when a team picks", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: { choice: null, choices: ["small_reward"], refreshed: false },
      },
      [`POST ${ASKING}`]: {
        body: { choice: "small_reward", choices: ["small_reward"], refreshed: false },
      },
    });
    renderAsking();
    const button = await chooseButton(/a small reward/);
    // Inline confirm (§6.18): the first press arms, the second commits.
    fireEvent.click(button);
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
    await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
    fireEvent.click(button);
    await waitFor(() => {
      const post = calls.find((call) => call.init.method === "POST");
      expect(post?.url).toBe(ASKING);
      expect(new Headers(post?.init.headers).get("X-Exercise-Request")).toBe("1");
    });
  });

  it("renders a refused second choice as the server's sentence", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: { choice: null, choices: ["required"], refreshed: false },
      },
      [`POST ${ASKING}`]: {
        body: {
          error: {
            code: "exercise_asking_already_chosen",
            message: "Your team has already picked how it will ask.",
          },
        },
        status: 409,
      },
    });
    renderAsking();
    const required = await chooseButton(/required\./);
    await pressTwice(required);
    await waitFor(() =>
      expect(screen.getByText("Your team has already picked how it will ask.")).toBeDefined(),
    );
  });

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
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));

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
    fireEvent.click(ask);

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
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));
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

  it("shows the choice only after the team has its round-one results, and says why", async () => {
    // Ann, 2026-10-02: "The choice appears only after the team has its
    // round-one results."
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: null,
          choices: ["better_recommendations", "small_reward", "required"],
          refreshed: false,
          first_round_results: false,
        },
      },
    });
    renderAsking();
    await screen.findByText(
      "Your team picks a way of asking after it has its results for Northline Career Fair.",
    );
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByRole("button", { name: /choose this way/i })).toBeNull();
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
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
    expect(within(summary).getByRole("status").textContent).toContain(
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
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));
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
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));
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

  it("offers no way to clear this team's work", async () => {
    stub({
      [`GET ${ASKING}`]: { body: { choice: null, choices: ["required"], refreshed: false } },
    });
    renderAsking();
    await chooseButton(/required\./);
    expect(document.body.textContent?.toLowerCase()).not.toContain("reset");
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

describe("<ExerciseAskingForMore /> — the invitation desk (§6.18, §6.19, §7.9)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("offers the choices as a radio group named by its question, with a supporting line", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const group = await screen.findByRole("radiogroup", { name: "How will your team ask?" });
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((radio) => (radio as HTMLInputElement).checked)).toEqual([false, false, false]);
    expect(screen.getByText("Offer something small for a completed card.")).toBeDefined();
    expect(
      screen.getByText("Tell them a card helps us suggest events worth their evening."),
    ).toBeDefined();
    expect(screen.getByText("Make the card a condition of hearing about events.")).toBeDefined();
  });

  it("arms an inline confirm on the first press, with no pop-up and no request", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const button = await chooseButton(/a small reward/);
    fireEvent.click(button);
    expect(button.textContent).toContain("Confirm: A small reward?");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
    const hint = document.querySelector('[data-slot="exercise-asking-confirm-live"]');
    expect(hint?.getAttribute("aria-live")).toBe("polite");
    expect(hint?.textContent).toBe("Press again to confirm A small reward. Your team picks once.");
    // Focus is not moved: the same button is the one that confirms.
    expect(document.querySelector('[data-slot="ce-confirm-underline"]')).not.toBeNull();
  });

  it("reverts to \"Choose this way\" when the five seconds lapse", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const button = await chooseButton(/a small reward/);
    vi.useFakeTimers();
    fireEvent.click(button);
    expect(button.textContent).toContain("Confirm: A small reward?");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(button.textContent).toContain("Choose this way");
    expect(button.textContent).not.toContain("Confirm:");
    fireEvent.click(button);
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
  });

  it("sends exactly one POST with the confirmed choice, however often it is pressed after", async () => {
    stub({
      ...OPEN_CHOICES,
      [`POST ${ASKING}`]: { body: { choice: "small_reward", choices: [], refreshed: false } },
    });
    renderAsking();
    const button = await chooseButton(/a small reward/);
    await pressTwice(button);
    fireEvent.click(button);
    fireEvent.click(button);
    await new Promise((resolve) => setTimeout(resolve, 50));
    const posts = calls.filter((call) => call.init.method === "POST");
    expect(posts.length).toBe(1);
    expect(JSON.parse(String(posts[0].init.body))).toEqual({ choice: "small_reward" });
  });

  it("sends the card the confirm was moved to, not the first one armed", async () => {
    stub({
      ...OPEN_CHOICES,
      [`POST ${ASKING}`]: { body: { choice: "required", choices: [], refreshed: false } },
    });
    renderAsking();
    const reward = await chooseButton(/a small reward/);
    const required = await chooseButton(/required\./);
    fireEvent.click(reward);
    await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
    await pressTwice(required);
    await waitFor(() =>
      expect(calls.filter((call) => call.init.method === "POST").length).toBe(1),
    );
    const post = calls.find((call) => call.init.method === "POST");
    expect(JSON.parse(String(post?.init.body))).toEqual({ choice: "required" });
  });

  it("sends nothing when the shut \"Ask them now\" is clicked", async () => {
    // Shut for want of a choice…
    stub(OPEN_CHOICES);
    const first = renderAsking();
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));
    first.unmount();
    // …and for want of a first-round run.
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
    await screen.findByText(/before asking\./i);
    fireEvent.click(screen.getByRole("button", { name: /ask them now/i }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
  });

  it("lets a card be armed again after the choice is refused", async () => {
    stub({
      ...OPEN_CHOICES,
      [`POST ${ASKING}`]: {
        body: {
          error: {
            code: "exercise_asking_already_chosen",
            message: "Your team has already picked how it will ask.",
          },
        },
        status: 409,
      },
    });
    renderAsking();
    await pressTwice(await chooseButton(/a small reward/));
    await screen.findByText("Your team has already picked how it will ask.");
    const again = await chooseButton(/a small reward/);
    expect(again.textContent).toContain("Choose this way");
    expect(isShut(again)).toBe(false);
    fireEvent.click(again);
    expect(again.textContent).toContain("Confirm: A small reward?");
    expect(calls.filter((call) => call.init.method === "POST").length).toBe(1);
  });

  it("ignores a held Enter or Space: key repeat never confirms a once-only choice", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const button = await chooseButton(/a small reward/);
    fireEvent.click(button);
    await new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
    // `fireEvent` returns false when the handler called `preventDefault()`,
    // which is what stops the browser turning a repeat into a click.
    expect(fireEvent.keyDown(button, { key: "Enter", repeat: true })).toBe(false);
    expect(fireEvent.keyDown(button, { key: " ", repeat: true })).toBe(false);
    // A fresh Enter or Space is left alone, so keyboard users can still press.
    expect(fireEvent.keyDown(button, { key: "Enter" })).toBe(true);
    expect(fireEvent.keyDown(button, { key: " " })).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
    expect(button.textContent).toContain("Confirm: A small reward?");
  });

  it("treats a double-click as one press: armed, not chosen", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const button = await chooseButton(/a small reward/);
    fireEvent.click(button);
    fireEvent.click(button);
    expect(button.textContent).toContain("Confirm: A small reward?");
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
  });

  it("reverts on Escape", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const button = await chooseButton(/required\./);
    fireEvent.click(button);
    expect(button.textContent).toContain("Confirm: Required?");
    fireEvent.keyDown(button, { key: "Escape" });
    expect(button.textContent).not.toContain("Confirm:");
    expect(document.querySelector('[data-slot="exercise-asking-confirm-live"]')?.textContent).toBe(
      "",
    );
  });

  it("moves the confirm when another card is pressed, and chooses nothing", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const reward = await chooseButton(/a small reward/);
    const required = await chooseButton(/required\./);
    fireEvent.click(reward);
    fireEvent.click(required);
    expect(reward.textContent).not.toContain("Confirm:");
    expect(required.textContent).toContain("Confirm: Required?");
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
  });

  it("cancels an armed confirm when another card is picked in the radio group", async () => {
    stub(OPEN_CHOICES);
    renderAsking();
    const reward = await chooseButton(/a small reward/);
    fireEvent.click(reward);
    fireEvent.click(screen.getByRole("radio", { name: /required\./i }));
    expect(reward.textContent).not.toContain("Confirm:");
  });

  it("under reduced motion shows the static helper instead of the underline", async () => {
    stubReducedMotion(true);
    stub(OPEN_CHOICES);
    renderAsking();
    const button = await chooseButton(/a small reward/);
    fireEvent.click(button);
    expect(document.querySelector('[data-slot="ce-confirm-underline"]')).toBeNull();
    expect(document.querySelector('[data-slot="ce-confirm-helper"]')?.textContent).toBe(
      "5 seconds",
    );
  });

  it("shows the chosen card as fixed: checked, sealed, the others shut, no choose buttons", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: "small_reward",
          choices: ["better_recommendations", "small_reward", "required"],
          refreshed: false,
        },
      },
    });
    renderAsking();
    const chosen = await screen.findByRole("radio", { name: /a small reward/i });
    expect((chosen as HTMLInputElement).checked).toBe(true);
    for (const radio of screen.getAllByRole("radio")) {
      expect((radio as HTMLInputElement).disabled).toBe(true);
    }
    expect(screen.getByText("Your team chose this.")).toBeDefined();
    expect(screen.getByText("A team picks once, so these are now fixed.")).toBeDefined();
    expect(screen.queryByRole("button", { name: /choose this way/i })).toBeNull();
    expect(
      document.querySelectorAll('[data-slot="exercise-asking-card"][data-state="dimmed"]').length,
    ).toBe(2);
  });

  it("gives the refresh counts as a ruled band whose numbers are read once, in full", async () => {
    stub({
      [`GET ${ASKING}`]: {
        body: {
          choice: "small_reward",
          choices: ["small_reward"],
          refreshed: true,
          refreshed_at: AT,
          refresh_counts: counts({ cards_completed: 9, non_responding: 0, topics_added: 34 }),
        },
      },
    });
    renderAsking();
    const band = await waitFor(() => {
      const found = document.querySelector('[data-slot="exercise-refresh-counts"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    // The figure a screen reader hears is the final number, never the count-up.
    const spoken = [...band.querySelectorAll("dd .sr-only")].map((node) => node.textContent);
    expect(spoken).toEqual(["9", "0", "34"]);
    for (const ticking of band.querySelectorAll("dd [aria-hidden='true']")) {
      expect(ticking.classList.contains("ce-type-display")).toBe(true);
    }
  });
});

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
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));

    await waitFor(() => expect(screen.getByText(/could not be reached/i)).toBeDefined());
    const shut = screen.getByRole("button", { name: "Already refreshed at 10:42 AM" });
    expect(isShut(shut)).toBe(true);
    fireEvent.click(shut);
    expect(postsTo(REFRESH)).toBe(1);

    const band = document.querySelector('[data-slot="exercise-refresh-counts"]');
    expect(band?.textContent).toContain("Cards filled in8");
    // Said once, in full, in a status region a screen reader announces.
    const summary = document.querySelector('[data-slot="exercise-refresh-summary"]') as HTMLElement;
    expect(within(summary).getByRole("status").textContent).toContain(
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
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Enter your team number" })).toBeDefined(),
    );
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByRole("button", { name: /ask them now/i })).toBeNull();
  });
});
