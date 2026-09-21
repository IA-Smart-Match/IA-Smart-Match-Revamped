/**
 * Asking for more: the server's three choices, and its refusals as states.
 *
 * The set of choices is the server's — a fourth one appears on screen the day
 * the API offers it. Only the wording of each is local, because the asking
 * response carries no label per choice the way the list response carries
 * `factor_labels`.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseAskingForMore } from "./ExerciseAskingForMore";

let calls: { url: string; init: RequestInit }[] = [];

function stub(answers: Record<string, { body: unknown; status?: number }>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const key = `${init.method ?? "GET"} ${url}`;
      const answer = answers[key] ??
        answers[url] ?? {
          body: { error: { code: "test_unstubbed", message: key } },
          status: 404,
        };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

const ASKING = "/v1/exercise/workspaces/current/asking-choice";
const REFRESH = "/v1/exercise/workspaces/current/refresh";

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
    await waitFor(() => expect(screen.getByText(/promise better recommendations/i)).toBeDefined());
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
    await waitFor(() => expect(screen.getByRole("button", { name: "a_fourth_way" })).toBeDefined());
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
    const button = await screen.findByRole("button", { name: /a small reward/i });
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
    fireEvent.click(await screen.findByRole("button", { name: /^required\.$/i }));
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
    expect((ask as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/pick a way of asking first/i)).toBeDefined();
  });

  it("keeps the once-only refresh counts on screen after the reload settles", async () => {
    // F3. A team may refresh once, ever, and `GET …/asking-choice` reports only
    // *that* it has — never what happened. So these three numbers exist in
    // exactly one response and nothing can fetch them again.
    //
    // Fails on the merged code: the counts were held by `AskingPanels`, the
    // refresh called `onChanged()`, the reload dropped the hook to `loading`,
    // and the panel unmounted — taking them with it. Asserting *after* the
    // reload's own request has landed is what catches it; the old test looked
    // at a DOM that was about to be thrown away.
    stub({
      [`GET ${ASKING}`]: { body: { choice: "required", choices: ["required"], refreshed: false } },
      [`POST ${REFRESH}`]: {
        body: { choice: "required", cards_completed: 14, non_responding: 3, topics_added: 22 },
      },
    });
    renderAsking();
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));

    // The POST, then the reload's GET, have both been issued.
    await waitFor(() => expect(calls.filter((call) => call.url === REFRESH).length).toBe(1));
    await waitFor(() => expect(calls.filter((call) => call.url === ASKING).length).toBe(2));
    // Let the reload's answer settle before looking.
    await new Promise((resolve) => setTimeout(resolve, 50));

    const counts = document.querySelector('[data-slot="exercise-refresh-counts"]');
    expect(counts).not.toBeNull();
    expect(counts?.textContent).toContain("14");
    expect(counts?.textContent).toContain("3");
    expect(counts?.textContent).toContain("22");
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
                JSON.stringify({ choice: "required", choices: ["required"], refreshed: false }),
                { status: 200 },
              ),
            );
          }
          // The reload triggered by the refresh: held open on purpose.
          return new Promise<Response>((resolve) => {
            releaseSecondGet = () =>
              resolve(
                new Response(
                  JSON.stringify({ choice: "required", choices: ["required"], refreshed: true }),
                  { status: 200 },
                ),
              );
          });
        }
        if (url === REFRESH && method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({ choice: "required", cards_completed: 1, non_responding: 0, topics_added: 0 }),
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

    expect(ask.disabled).toBe(true);

    releaseSecondGet?.();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /your team has already asked/i })).toBeDefined(),
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
    });
    renderAsking();
    fireEvent.click(await screen.findByRole("button", { name: /ask them now/i }));
    await waitFor(() =>
      expect(
        screen.getByText("Run the first event's results before asking anyone for more."),
      ).toBeDefined(),
    );
  });

  it("offers no way to clear this team's work", async () => {
    stub({
      [`GET ${ASKING}`]: { body: { choice: null, choices: ["required"], refreshed: false } },
    });
    renderAsking();
    await waitFor(() => expect(screen.getByRole("button", { name: /^required\.$/i })).toBeDefined());
    expect(document.body.textContent?.toLowerCase()).not.toContain("reset");
  });
});
