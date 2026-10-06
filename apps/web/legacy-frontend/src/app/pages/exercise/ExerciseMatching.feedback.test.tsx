/**
 * Matching: every press says what it did, beside the button, and the sentence
 * stays until the next press (issue #321; Ann's checklist of 2026-10-02,
 * sections 1 and 4).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseMatching } from "./ExerciseMatching";
import {
  comparingSentence,
  deletedSentence,
  openedSentence,
  savedSentence,
} from "./matchingWording";

// The status line has its own tests; here only this page's requests matter.
vi.mock("./TeamStatusBand", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./TeamStatusBand")>()),
  TeamStatusBand: () => null,
}));

const BASE = "/v1/exercise/workspaces/current/events/northline";

const WEIGHTS = {
  same_major: 0.25,
  stated_interest_overlap: 0.25,
  career_goal_fit: 0.25,
  past_event_topic_overlap: 0.25,
};

const LIST = {
  event_key: "northline",
  event_name: "Northline",
  event_description: null,
  invite_limit: 30,
  setting_name: null,
  weights: WEIGHTS,
  factor_labels: {
    same_major: "same major",
    stated_interest_overlap: "said they are interested in this topic",
    career_goal_fit: "career goal fits this event",
    past_event_topic_overlap: "went to similar events before",
  },
  entries: [],
  composition: {
    by_major: { dimension: "major", on_list: {}, all_profiles: {} },
    by_class_year: { dimension: "class_year", on_list: {}, all_profiles: {} },
    by_marker: { dimension: "marker", on_list: {}, all_profiles: {} },
    coverage: { missing_majors: [], missing_class_years: [], has_uncovered_group: false },
  },
  unlisted_class_years: [],
  unrankable_profile_count: 0,
};

function setting(name: string): object {
  return { name, weights: WEIGHTS, created_at: "2026-10-16T10:00:00" };
}

function settings(...names: string[]): object {
  return { event_key: "northline", settings: names.map(setting), max_settings: 3 };
}

type Answer = { body: unknown; status?: number };

/** Answers by "METHOD path"; the saved list is whatever `saved` holds at the time. */
function stub(saved: { current: object }, named: Record<string, Answer> = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const path = url.split("?")[0];
      const key = `${init.method ?? "GET"} ${path}`;
      const answer: Answer =
        named[key] ??
        (key === `GET ${BASE}/list`
          ? // A list asked for by a setting's name says which setting built it.
            { body: { ...LIST, setting_name: new URLSearchParams(url.split("?")[1]).get("setting") } }
          : key === `GET ${BASE}/settings`
            ? { body: saved.current }
            : { body: { error: { code: "test_unstubbed", message: key } }, status: 404 });
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
      { path: "/exercise", element: <p>entry</p> },
    ],
    { initialEntries: ["/exercise/events/northline"] },
  );
  return render(<RouterProvider router={router} />);
}

function panel(): HTMLElement {
  return document.querySelector('[data-slot="exercise-saved-settings"]') as HTMLElement;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the sentences", () => {
  it("are Ann's example, with the slots from the server's own answer", () => {
    const after = { event_key: "northline", settings: [setting("Setting A")], max_settings: 3 };
    expect(savedSentence("Setting A", "Northline", after as never)).toBe(
      "Saved “Setting A” for Northline. You have 2 of 3 slots left.",
    );
    expect(deletedSentence("Setting A", { ...after, settings: [] } as never)).toBe(
      "Deleted “Setting A”. You have 3 of 3 slots left.",
    );
  });

  it("leave the count out rather than invent one when the answer does not carry it", () => {
    expect(savedSentence("Setting A", "Northline", null)).toBe("Saved “Setting A” for Northline.");
    expect(deletedSentence("Setting A", {} as never)).toBe("Deleted “Setting A”.");
  });

  it("name what was opened and what is being compared", () => {
    expect(openedSentence("Wide net")).toBe("Opened “Wide net”. The list above is built from it.");
    expect(comparingSentence("A", "B")).toBe("Showing “A” and “B” side by side, below.");
  });
});

describe("<ExerciseMatching /> says what each press did", () => {
  it("says a setting was saved, with the slots left, inside the saved-settings panel", async () => {
    const saved = { current: settings() };
    stub(saved, { [`PUT ${BASE}/settings/Setting%20A`]: { body: settings("Setting A") } });
    renderMatching();
    fireEvent.change(await screen.findByLabelText("Name these weights"), {
      target: { value: "Setting A" },
    });
    saved.current = settings("Setting A");
    fireEvent.click(screen.getByRole("button", { name: "Save these weights" }));

    const said = await within(panel()).findByText(
      "Saved “Setting A” for Northline. You have 2 of 3 slots left.",
    );
    const notice = said.closest('[data-slot="exercise-notice"]') as HTMLElement;
    expect(notice.dataset.tone).toBe("done");
    expect(notice.getAttribute("role")).toBe("status");
  });

  it("keeps the sentence on screen: it does not vanish on its own", async () => {
    const saved = { current: settings() };
    stub(saved, { [`PUT ${BASE}/settings/Setting%20A`]: { body: settings("Setting A") } });
    renderMatching();
    fireEvent.change(await screen.findByLabelText("Name these weights"), {
      target: { value: "Setting A" },
    });
    saved.current = settings("Setting A");
    fireEvent.click(screen.getByRole("button", { name: "Save these weights" }));
    await within(panel()).findByText(/^Saved “Setting A”/);

    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(within(panel()).getByText(/^Saved “Setting A”/)).toBeDefined();
  });

  it("says why a save did nothing, in the same place, with the server's own sentence", async () => {
    const saved = { current: settings() };
    stub(saved, {
      [`PUT ${BASE}/settings/compare`]: {
        body: {
          error: { code: "exercise_setting_name_reserved", message: "Choose another name." },
        },
        status: 422,
      },
    });
    renderMatching();
    fireEvent.change(await screen.findByLabelText("Name these weights"), {
      target: { value: "compare" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save these weights" }));

    const said = await within(panel()).findByText("Choose another name.");
    expect((said.closest('[data-slot="exercise-notice"]') as HTMLElement).dataset.tone).toBe("calm");
  });

  it("asks before deleting, then says it was deleted and how many slots are left", async () => {
    const saved = { current: settings("Setting A") };
    stub(saved, { [`DELETE ${BASE}/settings/Setting%20A`]: { body: settings() } });
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Delete Setting A" }));
    expect(screen.getByText("Delete Setting A? It cannot be brought back.")).toBeDefined();
    expect(within(panel()).queryByText(/^Deleted/)).toBeNull();

    saved.current = settings();
    fireEvent.click(screen.getByRole("button", { name: "Delete it" }));
    await within(panel()).findByText("Deleted “Setting A”. You have 3 of 3 slots left.");
  });

  it("replaces the last sentence with the next press's", async () => {
    const saved = { current: settings("Setting A") };
    stub(saved, { [`DELETE ${BASE}/settings/Setting%20A`]: { body: settings() } });
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Open this list" }));
    await within(panel()).findByText("Opened “Setting A”. The list above is built from it.");

    fireEvent.click(screen.getByRole("button", { name: "Delete Setting A" }));
    saved.current = settings();
    fireEvent.click(screen.getByRole("button", { name: "Delete it" }));
    await within(panel()).findByText(/^Deleted “Setting A”/);
    expect(within(panel()).queryByText(/^Opened/)).toBeNull();
  });

  it("says which two settings are side by side, and when that view is closed", async () => {
    const saved = { current: settings("A", "B") };
    stub(saved, {
      [`GET ${BASE}/settings/compare`]: {
        body: {
          a: { ...LIST, setting_name: "A" },
          b: { ...LIST, setting_name: "B" },
          on_both_profile_nos: [],
        },
      },
    });
    renderMatching();
    const boxes = await screen.findAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.click(screen.getByRole("button", { name: "Show them side by side" }));
    await within(panel()).findByText("Showing “A” and “B” side by side, below.");

    fireEvent.click(await screen.findByRole("button", { name: "Close this comparison" }));
    await within(panel()).findByText("Closed the side-by-side view.");
  });

  it("says “List updated.” beside the list once a list the team asked for has landed", async () => {
    const saved = { current: settings("Setting A") };
    stub(saved);
    renderMatching();
    await screen.findByRole("button", { name: "Open this list" });
    // Nothing has been asked for yet.
    expect(document.querySelector('[data-slot="exercise-list-updated"]')).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Open this list" }));
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-list-updated"]')?.textContent).toBe(
        "List updated.",
      ),
    );
    expect(
      document.querySelector('[data-slot="exercise-list-updated"]')?.getAttribute("role"),
    ).toBe("status");
  });
});
