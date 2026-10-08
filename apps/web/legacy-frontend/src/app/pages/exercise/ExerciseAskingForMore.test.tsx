/**
 * Asking for more: the server's three choices, and its refusals as states.
 *
 * The set of choices is the server's — a fourth one appears on screen the day
 * the API offers it. Only the wording of each is local, because the asking
 * response carries no label per choice the way the list response carries
 * `factor_labels`.
 *
 * The once-only refresh has its own file, `ExerciseAskingForMore.refresh.test.tsx`.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONFIRM_GUARD_MS } from "./desk";
import { stubReducedMotion } from "./desk/testMatchMedia";
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
    await pressTwice(await screen.findByRole("button", { name: /ask them now/i }));
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
