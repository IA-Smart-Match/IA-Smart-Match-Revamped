/**
 * The entry screen: the marker, the literal path, and a browser that refuses
 * to remember anything.
 *
 * The last one is not a hypothetical. A classroom machine with site data
 * blocked throws on the `localStorage` *accessor*, not just on the read, and
 * the one thing this screen must never do is fail to let a team in.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EXERCISE_LICENSE_LINE, ExerciseEntry } from "./ExerciseEntry";
import { WORKSPACE_POINTER_KEY } from "./workspacePointer";

interface Recorded {
  readonly url: string;
  readonly init: RequestInit;
}

let calls: Recorded[] = [];

/** Answer by matching the tail of the URL; everything else 404s loudly. */
function stubFetch(answers: Record<string, { body: unknown; status?: number }>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const key = Object.keys(answers).find((candidate) => url === candidate);
      if (key === undefined) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: "test_unstubbed", message: url } }), {
            status: 404,
          }),
        );
      }
      const answer = answers[key];
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function renderEntry() {
  const router = createMemoryRouter(
    [
      { path: "/exercise", element: <ExerciseEntry /> },
      { path: "/exercise/events", element: <p>events</p> },
    ],
    { initialEntries: ["/exercise"] },
  );
  return render(<RouterProvider router={router} />);
}

const SCOPE = { scope: "class_exercise", team_numbers: [1, 2, 3, 4, 5, 6], synthetic_data: true };

beforeEach(() => {
  calls = [];
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseEntry />", () => {
  it("shows the license line on the opening screen (OQ-CE-09)", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
    });
    renderEntry();
    await waitFor(() => expect(screen.getByRole("radio", { name: /team 1/i })).toBeDefined());
    const sentence =
      "For California State Polytechnic University, Pomona — College of Business Administration instructional use only.";
    expect(screen.getByText(sentence)).toBeDefined();
    expect(EXERCISE_LICENSE_LINE).toBe(sentence);
  });

  it("shows the license line even when the exercise cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("offline"))),
    );
    renderEntry();
    expect(screen.getByText(EXERCISE_LICENSE_LINE)).toBeDefined();
  });

  it("marks the screen as synthetic, as every exercise screen must", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
    });
    renderEntry();
    await waitFor(() => expect(screen.getByRole("radio", { name: /team 1/i })).toBeDefined());
    expect(document.querySelector('[data-slot="synthetic-data-banner"]')).not.toBeNull();
  });

  it("asks the literal /v1/exercise paths, never an /api prefix", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
    });
    renderEntry();
    await waitFor(() => expect(calls.length).toBeGreaterThan(1));
    expect(calls.map((call) => call.url)).toEqual([
      "/v1/exercise",
      "/v1/exercise/workspaces/current",
    ]);
    for (const call of calls) {
      expect(call.url.startsWith("/api")).toBe(false);
    }
  });

  it("names each radio for a screen reader as just the team", async () => {
    // L4. Fails on the merged code: the input took its name from the label's
    // text, which holds both the big projected numeral and a hidden word, so
    // the accessible name was "4 Team 4". An exact-string match catches it;
    // the regex the other tests use would not.
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
    });
    renderEntry();
    await waitFor(() => expect(screen.getAllByRole("radio").length).toBe(6));
    expect(screen.getByRole("radio", { name: "Team 4" })).toBeDefined();
  });

  it("offers the team numbers the server named, and no others", async () => {
    stubFetch({
      "/v1/exercise": { body: { ...SCOPE, team_numbers: [1, 2, 3] } },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
    });
    renderEntry();
    await waitFor(() => expect(screen.getAllByRole("radio").length).toBe(3));
  });

  it("shows the data file its workspace is in, even when it is not the newest", async () => {
    // PR #186's ruling: an existing workspace wins over a newer upload, so an
    // older label here is correct and carries no warning.
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { team_number: 4, dataset_label: "Autumn draft", invite_limit: 30 },
      },
    });
    renderEntry();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-entry-current"]')?.textContent).toContain(
        "Autumn draft",
      ),
    );
  });

  it("sends X-Exercise-Request when a team enters", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
      "/v1/exercise/workspaces": {
        body: { team_number: 2, dataset_label: "Autumn draft", invite_limit: 30 },
      },
    });
    renderEntry();
    const radio = await screen.findByRole("radio", { name: /team 2/i });
    fireEvent.click(radio);
    fireEvent.click(screen.getByRole("button", { name: /open this team/i }));

    await waitFor(() => {
      const entry = calls.find((call) => call.url === "/v1/exercise/workspaces");
      expect(entry).toBeDefined();
      expect(new Headers(entry?.init.headers).get("X-Exercise-Request")).toBe("1");
      expect(entry?.init.method).toBe("POST");
    });
  });

  it("mirrors the team number so a reload does not ask for it again", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
      "/v1/exercise/workspaces": {
        body: { team_number: 5, dataset_label: "Autumn draft", invite_limit: 30 },
      },
    });
    renderEntry();
    const radio = await screen.findByRole("radio", { name: /team 5/i });
    fireEvent.click(radio);
    fireEvent.click(screen.getByRole("button", { name: /open this team/i }));
    await waitFor(() => expect(window.localStorage.getItem(WORKSPACE_POINTER_KEY)).toBe("5"));
  });

  it("still lets a team in when the browser refuses to store anything", async () => {
    // A private window with site data blocked throws on the accessor itself,
    // which is why every access is wrapped rather than every read.
    const exploding = {
      getItem: () => {
        throw new Error("The operation is insecure.");
      },
      setItem: () => {
        throw new Error("The operation is insecure.");
      },
      removeItem: () => {
        throw new Error("The operation is insecure.");
      },
    };
    vi.stubGlobal("localStorage", exploding);
    Object.defineProperty(window, "localStorage", { value: exploding, configurable: true });

    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
      "/v1/exercise/workspaces": {
        body: { team_number: 1, dataset_label: "Autumn draft", invite_limit: 30 },
      },
    });
    renderEntry();
    const radio = await screen.findByRole("radio", { name: /team 1/i });
    fireEvent.click(radio);
    fireEvent.click(screen.getByRole("button", { name: /open this team/i }));
    await waitFor(() =>
      expect(calls.some((call) => call.url === "/v1/exercise/workspaces")).toBe(true),
    );
  });

  it("shows a refusal's own sentence, unchanged", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
        status: 401,
      },
      "/v1/exercise/workspaces": {
        body: {
          error: {
            code: "exercise_no_dataset",
            message: "There is no data file loaded yet. Ask your instructor to load one.",
          },
        },
        status: 409,
      },
    });
    renderEntry();
    const radio = await screen.findByRole("radio", { name: /team 3/i });
    fireEvent.click(radio);
    fireEvent.click(screen.getByRole("button", { name: /open this team/i }));
    await waitFor(() =>
      expect(
        screen.getByText("There is no data file loaded yet. Ask your instructor to load one."),
      ).toBeDefined(),
    );
  });
});
