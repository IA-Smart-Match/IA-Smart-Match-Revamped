/**
 * An event's description, on the three screens that show it (#318).
 *
 * Ann, 2026-10-02: "Show a short description at the top of the Northline and
 * Harbor pages, above the sliders, and next to each event on the instructor
 * page. The text is in the new event_description column of the attached Excel
 * file. Take it from the file, so I can change it later by uploading a new
 * file." And her checklist §3a: "readable on the projector (no smaller than
 * the list text)".
 *
 * So each test hands the screen a made-up sentence through the server's
 * response and asserts that sentence is what appears: there is no description
 * text in the frontend to fall back on, and a `null` shows nothing at all.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseEventPicker } from "./ExerciseEventPicker";
import { ExerciseMatching } from "./ExerciseMatching";
import { UnlockPanel } from "./InstructorUnlock";

const SLOT = '[data-slot="exercise-event-description"]';
const NORTHLINE_TEXT = "A made-up sixty-minute talk by two made-up managers. Snacks provided.";
const HARBOR_TEXT = "A made-up product launch, told by the made-up people who ran it.";

const TEAM = "/v1/exercise/workspaces/current";

function stub(answers: Record<string, unknown>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = answers[url.split("?")[0]];
      return Promise.resolve(
        body === undefined
          ? new Response(JSON.stringify({ error: { code: "test_unstubbed", message: url } }), {
              status: 404,
            })
          : new Response(JSON.stringify(body), { status: 200 }),
      );
    }),
  );
}

function descriptions(): string[] {
  return [...document.querySelectorAll(SLOT)].map((node) => node.textContent ?? "");
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// The matching page: at the top, above the sliders
// ---------------------------------------------------------------------------

function listView(eventDescription: string | null | undefined) {
  return {
    event_key: "northline",
    event_name: "Northline Analytics",
    ...(eventDescription === undefined ? {} : { event_description: eventDescription }),
    invite_limit: 30,
    setting_name: null,
    weights: {
      same_major: 0.25,
      stated_interest_overlap: 0.25,
      career_goal_fit: 0.25,
      past_event_topic_overlap: 0.25,
    },
    factor_labels: {
      same_major: "same major",
      stated_interest_overlap: "said they are interested in this topic",
      career_goal_fit: "career goal fits this event",
      past_event_topic_overlap: "went to similar events before",
    },
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
    unlisted_class_years: [],
    unrankable_profile_count: 0,
  };
}

function renderMatching(eventDescription: string | null | undefined) {
  stub({
    [`${TEAM}/events/northline/list`]: listView(eventDescription),
    [`${TEAM}/events/northline/settings`]: {
      event_key: "northline",
      settings: [],
      max_settings: 3,
    },
  });
  const router = createMemoryRouter(
    [{ path: "/exercise/events/:eventKey", element: <ExerciseMatching /> }],
    { initialEntries: ["/exercise/events/northline"] },
  );
  return render(<RouterProvider router={router} />);
}

/** Whether `first` comes before `second` in the document. */
function precedes(first: Element, second: Element): boolean {
  return (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

describe("the matching page", () => {
  it("shows the event's description above the sliders and above the list", async () => {
    renderMatching(NORTHLINE_TEXT);

    const description = await screen.findByText(NORTHLINE_TEXT);
    const sliders = screen.getAllByRole("slider");
    const listHeading = screen.getByRole("heading", { name: "The list" });

    expect(sliders.length).toBeGreaterThan(0);
    expect(sliders.every((slider) => precedes(description, slider))).toBe(true);
    expect(precedes(description, listHeading)).toBe(true);
    // Below the page title, which is the event's name.
    expect(precedes(screen.getByRole("heading", { level: 1 }), description)).toBe(true);
  });

  it("sets it in the size the list's own names are set in", async () => {
    renderMatching(NORTHLINE_TEXT);

    const description = await screen.findByText(NORTHLINE_TEXT);
    const name = screen.getByText("Rosa Villalobos");

    expect(description.classList.contains("ce-type-body")).toBe(true);
    // The list sets the class on the name itself (cards) or on the table body.
    expect(name.closest(".ce-type-body")).not.toBeNull();
  });

  it.each([null, undefined, "   "])("shows nothing when the file gave none (%j)", async (value) => {
    renderMatching(value);

    await screen.findByRole("heading", { name: "The list" });
    expect(descriptions()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// The event picker: on each round's card
// ---------------------------------------------------------------------------

function pickerEvent(key: string, name: string, sequence: number, description: string | null) {
  return {
    event_key: key,
    name,
    topic_tags: ["analytics"],
    target_majors: ["Marketing"],
    is_exercise_event: sequence > 10,
    sequence,
    description,
  };
}

function renderPicker(events: readonly unknown[]) {
  stub({ [`${TEAM}/events`]: { events } });
  const router = createMemoryRouter([{ path: "/exercise/events", element: <ExerciseEventPicker /> }], {
    initialEntries: ["/exercise/events"],
  });
  return render(<RouterProvider router={router} />);
}

describe("the event picker", () => {
  it("shows each round's own description on its card", async () => {
    renderPicker([
      pickerEvent("past-one", "A past event", 1, null),
      pickerEvent("northline", "Northline Analytics", 11, NORTHLINE_TEXT),
      pickerEvent("harbor", "Harbor Consumer Brands", 12, HARBOR_TEXT),
    ]);

    await waitFor(() => expect(screen.getAllByRole("link").length).toBe(2));
    const [first, second] = screen.getAllByRole("link");

    expect(first.textContent).toContain(NORTHLINE_TEXT);
    expect(first.textContent).not.toContain(HARBOR_TEXT);
    expect(second.textContent).toContain(HARBOR_TEXT);
    expect(descriptions()).toEqual([NORTHLINE_TEXT, HARBOR_TEXT]);
  });

  it("keeps the card's name short: the round and the event, with the rest as its description", async () => {
    renderPicker([pickerEvent("northline", "Northline Analytics", 11, NORTHLINE_TEXT)]);

    const link = await screen.findByRole("link", { name: "Round 1 Northline Analytics" });

    const describedBy = (link.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
    const described = describedBy.map((id) => document.getElementById(id)?.textContent ?? "");
    expect(described.join(" ")).toContain(NORTHLINE_TEXT);
    expect(described.join(" ")).toContain("Topics: analytics");
  });

  it("shows no description on a card whose event has none", async () => {
    renderPicker([pickerEvent("northline", "Northline Analytics", 11, null)]);

    await screen.findByRole("link", { name: "Round 1 Northline Analytics" });
    expect(descriptions()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// The instructor page: beside each event
// ---------------------------------------------------------------------------

function renderUnlock(northline: string | null, harbor: string | null) {
  stub({
    "/v1/exercise/instructor/events": {
      dataset_id: "11111111-1111-1111-1111-111111111111",
      dataset_label: "Ann's file, 2 October",
      events: [
        { event_key: "northline", name: "Northline Analytics", unlocked: true, description: northline },
        { event_key: "harbor", name: "Harbor Consumer Brands", unlocked: false, description: harbor },
      ],
    },
  });
  return render(
    <UnlockPanel onRefusal={vi.fn()} onUnlocked={vi.fn()} onSignedOut={vi.fn()} reloadKey={0} />,
  );
}

describe("the instructor's event list", () => {
  it("shows the same description beside each event", async () => {
    renderUnlock(NORTHLINE_TEXT, HARBOR_TEXT);

    const northline = (await screen.findByText("Northline Analytics")).closest("li");
    const harbor = screen.getByText("Harbor Consumer Brands").closest("li");

    expect(northline?.querySelector(SLOT)?.textContent).toBe(NORTHLINE_TEXT);
    expect(harbor?.querySelector(SLOT)?.textContent).toBe(HARBOR_TEXT);
    expect(northline?.querySelector(SLOT)?.classList.contains("ce-type-body")).toBe(true);
  });

  it("shows nothing beside an event whose file gave none", async () => {
    renderUnlock(null, null);

    await screen.findByText("Harbor Consumer Brands");
    expect(descriptions()).toEqual([]);
    // The row is otherwise as it was.
    expect(screen.getByRole("button", { name: /^open results$/i })).toBeDefined();
  });
});
