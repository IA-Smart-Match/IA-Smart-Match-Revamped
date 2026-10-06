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
/** An answer, or one worked out from the request's query (and held back, if it likes). */
type Named = Answer | ((search: URLSearchParams) => Answer | undefined | Promise<Answer>);

/** A list as the server sends it for this request: built from the setting it names, if any. */
function listFor(search: URLSearchParams): Answer {
  // Weights asked for by number come back as asked, as the server echoes them.
  const weights = Object.fromEntries(
    Object.entries(WEIGHTS).map(([key, value]) => [
      key,
      search.has(key) ? Number(search.get(key)) : value,
    ]),
  );
  return { body: { ...LIST, weights, setting_name: search.get("setting") } };
}

/** Answers by "METHOD path"; the saved list is whatever `saved` holds at the time. */
function stub(saved: { current: object }, named: Record<string, Named> = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const path = url.split("?")[0];
      const search = new URLSearchParams(url.split("?")[1]);
      const key = `${init.method ?? "GET"} ${path}`;
      const found = named[key];
      const answer: Answer =
        (typeof found === "function" ? await found(search) : found) ??
        (key === `GET ${BASE}/list`
          ? listFor(search)
          : key === `GET ${BASE}/settings`
            ? { body: saved.current }
            : { body: { error: { code: "test_unstubbed", message: key } }, status: 404 });
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
    }),
  );
}

function refused(status: number, code: string, message: string): Answer {
  return { body: { error: { code, message } }, status };
}

const aMoment = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 30));

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

  it("says why a delete did nothing, with the server's own sentence and no “Deleted”", async () => {
    const saved = { current: settings("Setting A") };
    stub(saved, {
      [`DELETE ${BASE}/settings/Setting%20A`]: refused(
        404,
        "exercise_setting_unknown",
        "Your team has no saved setting with that name.",
      ),
    });
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Delete Setting A" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete it" }));

    const said = await within(panel()).findByText("Your team has no saved setting with that name.");
    expect((said.closest('[data-slot="exercise-notice"]') as HTMLElement).dataset.tone).toBe("calm");
    expect(within(panel()).queryByText(/^Deleted/)).toBeNull();
  });

  it("says why a comparison was not shown, with the server's own sentence and no “Showing”", async () => {
    const saved = { current: settings("A", "B") };
    stub(saved, {
      [`GET ${BASE}/settings/compare`]: refused(
        404,
        "exercise_setting_unknown",
        "Your team has no saved setting with that name.",
      ),
    });
    renderMatching();
    const boxes = await screen.findAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.click(screen.getByRole("button", { name: "Show them side by side" }));

    const said = await within(panel()).findByText("Your team has no saved setting with that name.");
    expect((said.closest('[data-slot="exercise-notice"]') as HTMLElement).dataset.tone).toBe("calm");
    expect(within(panel()).queryByText(/^Showing/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Close this comparison" })).toBeNull();
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

/**
 * "Opened “A”. The list above is built from it." is a claim about the list
 * on screen, so it is made when that list is on screen and taken down when it
 * stops being true (PR #346 review).
 */
describe("<ExerciseMatching /> says “Opened” only while the list is built from that setting", () => {
  const OPENED = "Opened “Setting A”. The list above is built from it.";

  it("waits for that setting's list to land before it says so", async () => {
    const saved = { current: settings("Setting A") };
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    stub(saved, {
      [`GET ${BASE}/list`]: async (search) => {
        if (search.get("setting") === "Setting A") {
          await held;
        }
        return listFor(search);
      },
    });
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Open this list" }));

    // The read is out and has not answered: the list above is still the old one.
    await aMoment();
    expect(within(panel()).queryByText(/^Opened/)).toBeNull();

    release();
    const said = await within(panel()).findByText(OPENED);
    expect((said.closest('[data-slot="exercise-notice"]') as HTMLElement).dataset.tone).toBe("done");
  });

  it("says the server's refusal instead when the setting is gone, and never “Opened”", async () => {
    // Deleted in another tab since this screen read the saved settings.
    const saved = { current: settings("Setting A") };
    stub(saved, {
      [`GET ${BASE}/list`]: (search) =>
        search.get("setting") === "Setting A"
          ? refused(404, "exercise_setting_unknown", "Your team has no saved setting with that name.")
          : undefined,
    });
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Open this list" }));

    const said = await within(panel()).findByText("Your team has no saved setting with that name.");
    const notice = said.closest('[data-slot="exercise-notice"]') as HTMLElement;
    expect(notice.dataset.tone).toBe("calm");
    expect(within(panel()).queryByText(/^Opened/)).toBeNull();
    // Announced once: the page's own notice about the list is the live one.
    expect(notice.getAttribute("role")).toBeNull();
    expect(document.getElementById("exercise-list-refusal")?.getAttribute("role")).toBe("status");
    await aMoment();
    expect(within(panel()).queryByText(/^Opened/)).toBeNull();
  });

  it("takes it down when the team moves a weight", async () => {
    const saved = { current: settings("Setting A") };
    stub(saved);
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Open this list" }));
    await within(panel()).findByText(OPENED);

    const box = screen.getByRole("textbox", { name: "same major" });
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.5" } });
    fireEvent.blur(box);

    await waitFor(() => expect(within(panel()).queryByText(/^Opened/)).toBeNull());
    // And it does not come back when the new list lands.
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-list-updated"]')).not.toBeNull(),
    );
    expect(within(panel()).queryByText(/^Opened/)).toBeNull();
  });

  it("takes it down when the team goes back to the list's weights", async () => {
    const saved = { current: settings("Setting A") };
    stub(saved);
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Open this list" }));
    await within(panel()).findByText(OPENED);

    // Typed and not sent: the list is no longer the answer to the boxes.
    const box = screen.getByRole("textbox", { name: "same major" });
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.5" } });
    fireEvent.click(await screen.findByRole("button", { name: "Go back to this list's weights" }));

    await waitFor(() => expect(within(panel()).queryByText(/^Opened/)).toBeNull());
  });

  it("keeps another press's sentence when a weight moves: only “Opened” is about the list", async () => {
    const saved = { current: settings("Setting A") };
    stub(saved, { [`DELETE ${BASE}/settings/Setting%20A`]: { body: settings() } });
    renderMatching();
    fireEvent.click(await screen.findByRole("button", { name: "Delete Setting A" }));
    saved.current = settings();
    fireEvent.click(screen.getByRole("button", { name: "Delete it" }));
    await within(panel()).findByText(/^Deleted “Setting A”/);

    const box = screen.getByRole("textbox", { name: "same major" });
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.5" } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-list-updated"]')).not.toBeNull(),
    );
    expect(within(panel()).getByText(/^Deleted “Setting A”/)).toBeDefined();
  });
});
