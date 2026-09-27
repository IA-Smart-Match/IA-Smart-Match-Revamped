/**
 * The event picker as the invitation desk lays it out (DESIGN.md §7.3,
 * §6.5): round cards with a numbered seal, a shaped loading state, and the
 * past events folded behind a disclosure on a phone.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseEventPicker } from "./ExerciseEventPicker";

function answer(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))),
  );
}

function renderPicker() {
  const router = createMemoryRouter(
    [
      { path: "/exercise/events", element: <ExerciseEventPicker /> },
      { path: "/exercise/events/:eventKey", element: <p>list</p> },
      { path: "/exercise", element: <p>entry</p> },
    ],
    { initialEntries: ["/exercise/events"] },
  );
  return render(<RouterProvider router={router} />);
}

function event(key: string, name: string, isExercise: boolean, sequence: number) {
  return {
    event_key: key,
    name,
    topic_tags: ["analytics"],
    target_majors: ["Marketing"],
    is_exercise_event: isExercise,
    sequence,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseEventPicker /> layout", () => {
  it("shows two card skeletons, four line skeletons and a stated loading line", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    renderPicker();

    expect(screen.getByText("Loading the events…").getAttribute("role")).toBe("status");
    expect(document.querySelectorAll('[data-slot="ce-skeleton-card"]').length).toBe(2);
    expect(document.querySelectorAll('[data-slot="exercise-past-event-skeleton"]').length).toBe(4);
  });

  it("names each round card by its round, then the event", async () => {
    answer({
      events: [
        event("harbor", "Harbor Consumer Brands", true, 12),
        event("northline", "Northline Analytics", true, 11),
      ],
    });
    renderPicker();
    await waitFor(() => expect(screen.getAllByRole("link").length).toBe(2));

    const first = screen.getByRole("link", { name: /^Round 1 Northline Analytics/ });
    expect(first.getAttribute("href")).toBe("/exercise/events/northline");
    expect(first.textContent).toContain("Topics: analytics");
    expect(first.textContent).toContain("Aimed at: Marketing");
    expect(screen.getByRole("link", { name: /^Round 2 Harbor Consumer Brands/ })).toBeDefined();
  });

  it("folds the past events behind a disclosure that counts them", async () => {
    answer({
      events: [
        event("northline", "Northline Analytics", true, 11),
        event("past-one", "Fall Career Fair", false, 1),
        event("past-two", "Resume Lab Workshop", false, 2),
      ],
    });
    renderPicker();

    const toggle = await screen.findByRole("button", { name: "Show the 2 past events" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    const list = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    expect(list?.textContent).toContain("Fall Career Fair");
    expect(list?.getAttribute("data-expanded")).toBe("false");

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(list?.getAttribute("data-expanded")).toBe("true");
  });

  it("counts a single past event in the singular", async () => {
    answer({
      events: [
        event("northline", "Northline Analytics", true, 11),
        event("past-one", "Fall Career Fair", false, 1),
      ],
    });
    renderPicker();
    expect(await screen.findByRole("button", { name: "Show the 1 past event" })).toBeDefined();
  });

  it("offers no disclosure when there are no past events", async () => {
    answer({ events: [event("northline", "Northline Analytics", true, 11)] });
    renderPicker();
    await screen.findByText("This data file carries no past events.");
    expect(screen.queryByRole("button", { name: /past event/ })).toBeNull();
  });
});
