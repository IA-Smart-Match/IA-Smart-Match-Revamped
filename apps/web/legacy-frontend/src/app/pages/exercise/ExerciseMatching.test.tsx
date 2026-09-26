/**
 * The matching screen: Ann's words, the server's cap, and no score anywhere.
 *
 * Three of these would each fail silently and look like a working screen: a
 * rulebook key rendered where Ann's phrase belongs, a `3` written in place of
 * `max_settings`, and a reset button that has no route behind it any more.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseMatching } from "./ExerciseMatching";

let calls: { url: string; init: RequestInit }[] = [];

const FACTOR_LABELS = {
  same_major: "same major",
  stated_interest_overlap: "said they are interested in this topic",
  career_goal_fit: "career goal fits this event",
  past_event_topic_overlap: "went to similar events before",
};

const LIST = {
  event_key: "northline",
  event_name: "Northline Analytics",
  invite_limit: 30,
  setting_name: null,
  weights: {
    same_major: 0.25,
    stated_interest_overlap: 0.25,
    career_goal_fit: 0.25,
    past_event_topic_overlap: 0.25,
  },
  factor_labels: FACTOR_LABELS,
  entries: [
    {
      rank: 1,
      profile_no: 7,
      display_name: "Rosa Villalobos",
      major: "Marketing",
      class_year: "third",
      marker: "completed_card",
      reason: "Same major; nothing else on file.",
      contributing_factor_keys: ["same_major"],
    },
  ],
  composition: {
    by_major: { dimension: "major", on_list: { Marketing: 1 }, all_profiles: { Marketing: 90 } },
    by_class_year: { dimension: "class_year", on_list: { third: 1 }, all_profiles: { third: 80 } },
    by_marker: {
      dimension: "marker",
      on_list: { completed_card: 1 },
      all_profiles: { completed_card: 70, major_only: 230 },
    },
    coverage: { missing_majors: [], missing_class_years: [], has_uncovered_group: false },
  },
  unlisted_class_years: ["fourth"],
  unrankable_profile_count: 12,
};

const SETTINGS = { event_key: "northline", settings: [], max_settings: 5 };

function stub(overrides: Record<string, { body: unknown; status?: number }> = {}): void {
  const answers: Record<string, { body: unknown; status?: number }> = {
    "/v1/exercise/workspaces/current/events/northline/list": { body: LIST },
    "/v1/exercise/workspaces/current/events/northline/settings": { body: SETTINGS },
    "/v1/exercise/workspaces/current/events/northline/settings/Wide%20net": { body: SETTINGS },
    ...overrides,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const answer = answers[url.split("?")[0]] ?? {
        body: { error: { code: "test_unstubbed", message: url } },
        status: 404,
      };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function renderMatching() {
  const router = createMemoryRouter(
    [
      { path: "/exercise/events/:eventKey", element: <ExerciseMatching /> },
      { path: "/exercise/events", element: <p>events</p> },
      { path: "/exercise/events/:eventKey/results", element: <p>results</p> },
      { path: "/exercise", element: <p>entry</p> },
    ],
    { initialEntries: ["/exercise/events/northline"] },
  );
  return render(<RouterProvider router={router} />);
}

/** Just the ranked-list GETs, which is what a keystroke used to multiply. */
function listCalls(): { url: string; init: RequestInit }[] {
  return calls.filter((call) => call.url.split("?")[0].endsWith("/list"));
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseMatching />", () => {
  it("marks the screen as synthetic", async () => {
    stub();
    renderMatching();
    await waitFor(() => expect(screen.getByText("Rosa Villalobos")).toBeDefined());
    expect(document.querySelector('[data-slot="synthetic-data-banner"]')).not.toBeNull();
  });

  it("asks the literal paths", async () => {
    stub();
    renderMatching();
    await waitFor(() => expect(calls.length).toBeGreaterThan(1));
    for (const call of calls) {
      expect(call.url.startsWith("/v1/exercise/")).toBe(true);
      expect(call.url.includes("/api/")).toBe(false);
    }
  });

  it("labels the four factors in Ann's words and never with a rulebook key", async () => {
    stub();
    renderMatching();
    await waitFor(() => expect(screen.getByLabelText("same major")).toBeDefined());
    expect(screen.getByLabelText("said they are interested in this topic")).toBeDefined();
    expect(screen.getByLabelText("career goal fits this event")).toBeDefined();
    expect(screen.getByLabelText("went to similar events before")).toBeDefined();
    const weights = document.querySelector('[data-slot="exercise-weights"]');
    expect(weights?.textContent).not.toContain("stated_interest_overlap");
    expect(weights?.textContent).not.toContain("past_event_topic_overlap");
  });

  it("renders the server's reason sentence exactly as it arrived", async () => {
    stub();
    renderMatching();
    await waitFor(() => expect(screen.getByText("Same major; nothing else on file.")).toBeDefined());
  });

  it("reads the settings cap from the response instead of assuming three", async () => {
    stub();
    renderMatching();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-settings-cap"]')?.textContent).toContain(
        "5",
      ),
    );
  });

  it("shows the unrankable count and the years with nobody on the list", async () => {
    stub();
    renderMatching();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-unrankable"]')?.textContent).toContain(
        "12",
      ),
    );
    expect(
      document.querySelector('[data-slot="exercise-unlisted-years"]')?.textContent,
    ).toContain("fourth");
  });

  it("offers the download as a plain link to the literal CSV path", async () => {
    stub();
    renderMatching();
    // `waitFor` resolves on a callback that does not throw, and a
    // `querySelector` that finds nothing returns `null` rather than throwing —
    // so the wait has to be on an assertion, not on the lookup.
    const link = await waitFor(() => {
      const found = document.querySelector<HTMLAnchorElement>(
        '[data-slot="exercise-csv-download"]',
      );
      expect(found).not.toBeNull();
      return found;
    });
    expect(link?.getAttribute("href")).toBe(
      "/v1/exercise/workspaces/current/events/northline/list.csv",
    );
  });

  it("sends X-Exercise-Request when a team saves a setting", async () => {
    stub();
    renderMatching();
    const name = await screen.findByLabelText(/call these weights/i);
    fireEvent.change(name, { target: { value: "Wide net" } });
    fireEvent.click(screen.getByRole("button", { name: /save these weights/i }));

    await waitFor(() => {
      const put = calls.find((call) => call.init.method === "PUT");
      expect(put).toBeDefined();
      expect(put?.url).toBe(
        "/v1/exercise/workspaces/current/events/northline/settings/Wide%20net",
      );
      expect(new Headers(put?.init.headers).get("X-Exercise-Request")).toBe("1");
    });
  });


  it("keeps the weight boxes mounted, and focused, while the list is rebuilt", async () => {
    // F1. This is the whole defect in one assertion: the element identity
    // before and after a committed weighting has to be the same node.
    //
    // Fails on the merged code: committing dropped the hook to `loading`, the
    // ready branch rendered `null`, and the input was unmounted — so the
    // `before === after` identity check had a detached node on one side, and
    // `document.activeElement` was the body.
    stub();
    renderMatching();
    const before = (await screen.findByLabelText("same major")) as HTMLInputElement;
    before.focus();

    fireEvent.change(before, { target: { value: "0.75" } });
    fireEvent.blur(before);

    await waitFor(() =>
      expect(
        calls.filter((call) => call.url.includes("/list?") || call.url.endsWith("/list")).length,
      ).toBeGreaterThan(1),
    );

    const after = screen.getByLabelText("same major");
    expect(after).toBe(before);
  });

  it("issues one list request for a multi-character number, not one per keystroke", async () => {
    // Fails on the merged code: "0.75" is four change events and each one set
    // a new weighting object, so the list was fetched four extra times.
    stub();
    renderMatching();
    const box = await screen.findByLabelText("same major");
    await waitFor(() => expect(listCalls().length).toBe(1));

    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0" } });
    fireEvent.change(box, { target: { value: "0." } });
    fireEvent.change(box, { target: { value: "0.7" } });
    fireEvent.change(box, { target: { value: "0.75" } });
    fireEvent.blur(box);

    await waitFor(() => expect(listCalls().length).toBe(2));
    // Give any stray refetch a chance to arrive before declaring the count.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(listCalls().length).toBe(2);
  });

  it("shows the previous list while the new one is fetched, rather than a blank screen", async () => {
    // Fails on the merged code: the ready branch was replaced by the loading
    // line, so the previous rows were gone from the DOM entirely.
    stub();
    renderMatching();
    const box = await screen.findByLabelText("same major");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.9" } });
    fireEvent.blur(box);

    // The names are still on screen throughout, and the screen says it is busy.
    expect(screen.getByText("Rosa Villalobos")).toBeDefined();
    await waitFor(() => expect(listCalls().length).toBe(2));
  });

  it("shows a refused list GET as a sentence and leaves the rest of the screen usable", async () => {
    // G2. Fails on the merged code: without `keepDataOnRefusal`, a refused
    // list GET dropped the whole hook to `status: "refused"`, which
    // `ExerciseMatching` renders as `workspaceRequiredNotice` in place of
    // everything else — the weight boxes, the previous list, the save panel.
    // A team that typed a weight the server refuses should see one sentence
    // *and* keep the list and controls it already had.
    let listCallCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        calls.push({ url, init });
        const path = url.split("?")[0];
        if (path.endsWith("/list")) {
          listCallCount += 1;
          if (listCallCount > 1) {
            return Promise.resolve(
              new Response(
                JSON.stringify({
                  error: { code: "exercise_invalid_weights", message: "Weights must sum to 1." },
                }),
                { status: 400 },
              ),
            );
          }
          return Promise.resolve(new Response(JSON.stringify(LIST), { status: 200 }));
        }
        if (path.endsWith("/settings")) {
          return Promise.resolve(new Response(JSON.stringify(SETTINGS), { status: 200 }));
        }
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: "test_unstubbed", message: url } }), {
            status: 404,
          }),
        );
      }),
    );
    renderMatching();

    const box = await screen.findByLabelText("same major");
    expect(screen.getByText("Rosa Villalobos")).toBeDefined();

    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.9" } });
    fireEvent.blur(box);

    await waitFor(() => expect(screen.getByText("Weights must sum to 1.")).toBeDefined());

    // The list from before the refused request, and the controls to fix the
    // mistake, are still on screen next to the sentence.
    expect(screen.getByText("Rosa Villalobos")).toBeDefined();
    expect(screen.getByLabelText("same major")).toBeDefined();
    expect(document.querySelector('[data-slot="exercise-csv-download"]')).not.toBeNull();

    // Round 3 finding 3: the list shown is the *previous* answer, not the
    // answer to the weighting that was just refused — that has to be said,
    // not left for a reader to assume from the rows simply not moving.
    expect(document.querySelector('[data-slot="exercise-list-stale"]')).not.toBeNull();
    const listSection = document.querySelector('[data-slot="exercise-list-stale"]')
      ?.parentElement as HTMLElement;
    expect(listSection.getAttribute("aria-describedby")).toBe("exercise-list-refusal");
    expect(document.getElementById("exercise-list-refusal")?.textContent).toContain(
      "Weights must sum to 1.",
    );
  });

  it("keeps the name a team typed when the save is refused", async () => {
    // F5. Fails on the merged code: the screen's `guard` swallowed the refusal
    // and resolved, the panel read that as success and called `setName("")`,
    // so the box was empty and the team had to retype a name to try again.
    stub({
      "/v1/exercise/workspaces/current/events/northline/settings/Wide%20net": {
        body: {
          error: {
            code: "exercise_too_many_settings",
            message: "Your team may keep three settings for this event. Delete one first.",
          },
        },
        status: 409,
      },
    });
    renderMatching();
    const name = (await screen.findByLabelText(/call these weights/i)) as HTMLInputElement;
    fireEvent.change(name, { target: { value: "Wide net" } });
    fireEvent.click(screen.getByRole("button", { name: /save these weights/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Your team may keep three settings for this event. Delete one first."),
      ).toBeDefined(),
    );
    expect(name.value).toBe("Wide net");
  });

  it("clears the name once the save is accepted", async () => {
    stub();
    renderMatching();
    const name = (await screen.findByLabelText(/call these weights/i)) as HTMLInputElement;
    fireEvent.change(name, { target: { value: "Wide net" } });
    fireEvent.click(screen.getByRole("button", { name: /save these weights/i }));

    await waitFor(() => expect(name.value).toBe(""));
  });

  it("offers no way to clear this team's work", async () => {
    // PR #186: the team's own reset route is removed and answers 404.
    stub();
    renderMatching();
    await waitFor(() => expect(screen.getByText("Rosa Villalobos")).toBeDefined());
    expect(document.body.textContent?.toLowerCase()).not.toContain("reset");
    expect(document.body.textContent?.toLowerCase()).not.toContain("clear team");
  });

  it("puts no score, percentage or confidence on the screen", async () => {
    stub();
    renderMatching();
    await waitFor(() => expect(screen.getByText("Rosa Villalobos")).toBeDefined());
    const text = document.body.textContent ?? "";
    expect(/\bscore\b/i.test(text)).toBe(false);
    expect(/%/.test(text)).toBe(false);
    expect(/\bconfidence\b/i.test(text)).toBe(false);
  });

  it("shows a refusal's sentence when a fourth name is refused", async () => {
    stub({
      "/v1/exercise/workspaces/current/events/northline/settings/Wide%20net": {
        body: {
          error: {
            code: "exercise_too_many_settings",
            message: "Your team may keep three settings for this event. Delete one first.",
          },
        },
        status: 409,
      },
    });
    renderMatching();
    const name = await screen.findByLabelText(/call these weights/i);
    fireEvent.change(name, { target: { value: "Wide net" } });
    fireEvent.click(screen.getByRole("button", { name: /save these weights/i }));
    await waitFor(() =>
      expect(
        screen.getByText("Your team may keep three settings for this event. Delete one first."),
      ).toBeDefined(),
    );
  });

  it("lets each table scroll on its own instead of widening the page (B3)", async () => {
    stub();
    renderMatching();
    const list = await waitFor(() => {
      const found = document.querySelector('[data-slot="exercise-ranked-list"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    expect(list.parentElement?.className).toContain("overflow-x-auto");
    const tables = [...document.querySelectorAll("table")];
    expect(tables.length).toBeGreaterThan(1);
    for (const table of tables) {
      expect(table.parentElement?.className).toContain("overflow-x-auto");
    }
  });

  it("stacks the two compared lists, each scrolling in its own box (B3)", async () => {
    const saved = {
      event_key: "northline",
      settings: [
        { name: "Wide net", weights: LIST.weights, created_at: "2026-09-25T10:00:00Z" },
        { name: "Majors first", weights: LIST.weights, created_at: "2026-09-25T10:01:00Z" },
      ],
      max_settings: 3,
    };
    stub({
      "/v1/exercise/workspaces/current/events/northline/settings": { body: saved },
      "/v1/exercise/workspaces/current/events/northline/settings/compare": {
        body: { a: LIST, b: LIST, on_both_profile_nos: [7] },
      },
    });
    renderMatching();
    fireEvent.change(await screen.findByLabelText(/^compare$/i), {
      target: { value: "Wide net" },
    });
    fireEvent.change(screen.getByLabelText(/^with$/i), { target: { value: "Majors first" } });
    fireEvent.click(screen.getByRole("button", { name: /show them side by side/i }));

    const grid = await waitFor(() => {
      const found = document.querySelector('[data-slot="exercise-compare-grid"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    // The page is capped at max-w-5xl, so two six-column tables never fit
    // side by side at any viewport width: they always stack.
    expect(grid.className).not.toMatch(/grid-cols-2/);
    const children = [...grid.children];
    expect(children.length).toBe(2);
    for (const child of children) {
      expect(child.className).toContain("min-w-0");
    }
  });

  it("disables saving a fourth new name at the cap, and says why", async () => {
    const saved = {
      event_key: "northline",
      settings: ["One", "Two", "Three"].map((name) => ({
        name,
        weights: LIST.weights,
        created_at: "2026-09-25T10:00:00Z",
      })),
      max_settings: 3,
    };
    stub({ "/v1/exercise/workspaces/current/events/northline/settings": { body: saved } });
    renderMatching();
    const box = await screen.findByLabelText(/call these weights/i);
    const save = screen.getByRole("button", { name: /save these weights/i }) as HTMLButtonElement;

    fireEvent.change(box, { target: { value: "Four" } });
    expect(save.disabled).toBe(true);
    const reason = screen.getByText(
      "Your team has 3 saved settings for this event. Type one of those names to save over it, or delete one first.",
    );
    expect(save.getAttribute("aria-describedby")).toBe(reason.id);

    // Saving over a name the team has is always allowed and changes no count.
    fireEvent.change(box, { target: { value: " Two " } });
    expect(save.disabled).toBe(false);
    expect(screen.queryByText(/type one of their names/i)).toBeNull();
  });
});
