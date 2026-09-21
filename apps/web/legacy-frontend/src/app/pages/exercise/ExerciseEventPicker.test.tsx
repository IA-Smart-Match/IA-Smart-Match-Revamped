/**
 * The event picker: the marker, the literal path, and the two events that are
 * actually targets.
 *
 * Ten of the twelve events in the data file are past events, there so a
 * profile can have an attendance history. Offering one of them as something to
 * build a list for would be offering the class a decision the exercise does
 * not have.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseEventPicker } from "./ExerciseEventPicker";

let calls: string[] = [];

function answer(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(url);
      return Promise.resolve(new Response(JSON.stringify(body), { status }));
    }),
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

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseEventPicker />", () => {
  it("marks the screen as synthetic", async () => {
    answer({ events: [event("northline", "Northline Analytics", true, 11)] });
    renderPicker();
    await waitFor(() => expect(screen.getByText("Northline Analytics")).toBeDefined());
    expect(document.querySelector('[data-slot="synthetic-data-banner"]')).not.toBeNull();
  });

  it("asks the literal path", async () => {
    answer({ events: [] });
    renderPicker();
    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0]).toBe("/v1/exercise/workspaces/current/events");
    expect(calls[0].startsWith("/api")).toBe(false);
  });

  it("offers only the exercise events as lists to build, in sequence order", async () => {
    answer({
      events: [
        event("harbor", "Harbor Consumer Brands", true, 12),
        event("past-one", "A past event", false, 1),
        event("northline", "Northline Analytics", true, 11),
      ],
    });
    renderPicker();
    await waitFor(() => expect(screen.getAllByRole("link").length).toBe(2));
    const links = screen.getAllByRole("link");
    expect(links[0].textContent).toContain("Northline Analytics");
    expect(links[1].textContent).toContain("Harbor Consumer Brands");
    // The past event is listed for what it is, not as something to pick.
    expect(screen.getByText(/A past event/)).toBeDefined();
    expect(links.some((link) => link.textContent?.includes("A past event"))).toBe(false);
  });

  it("shows the server's sentence and a way back when there is no workspace", async () => {
    answer(
      {
        error: {
          code: "exercise_workspace_required",
          message: "Enter your team number to open your team's work.",
        },
      },
      401,
    );
    renderPicker();
    await waitFor(() =>
      expect(screen.getByText("Enter your team number to open your team's work.")).toBeDefined(),
    );
    expect(screen.getByRole("link", { name: /enter your team number/i })).toBeDefined();
  });

  it("says so honestly when a data file carries no exercise events", async () => {
    answer({ events: [event("past-one", "A past event", false, 1)] });
    renderPicker();
    await waitFor(() => expect(screen.getByText(/no exercise events in it yet/i)).toBeDefined());
  });
});
