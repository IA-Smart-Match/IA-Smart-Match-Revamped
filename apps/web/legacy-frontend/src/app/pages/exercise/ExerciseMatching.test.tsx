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
});
