/**
 * The opening screen and team entry as the invitation desk lays them out
 * (DESIGN.md §7.1, §7.2, §6.4): the room's question as the title, the team
 * question as a section, tiles that say which one is chosen, and an open
 * button that says why it cannot be pressed yet.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EXERCISE_LICENSE_LINE, ExerciseEntry } from "./ExerciseEntry";

const SCOPE = { scope: "class_exercise", team_numbers: [1, 2, 3, 4, 5, 6], synthetic_data: true };
const NO_WORKSPACE = {
  body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
  status: 401,
};

/** Answer by exact URL; a URL mapped to `"hang"` never settles. */
function stubFetch(answers: Record<string, { body: unknown; status?: number } | "hang">): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const answer = answers[url];
      if (answer === "hang") {
        return new Promise<Response>(() => undefined);
      }
      if (answer === undefined) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: "test_unstubbed", message: url } }), {
            status: 404,
          }),
        );
      }
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

function tile(number: number): HTMLElement {
  const radio = screen.getByRole("radio", { name: `Team ${number}` });
  const label = radio.closest("label");
  if (label === null) {
    throw new Error(`team ${number} radio has no tile`);
  }
  return label;
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseEntry /> layout", () => {
  it("asks the room's question as the title and the team question as a section", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": NO_WORKSPACE });
    renderEntry();
    await screen.findByRole("radio", { name: "Team 1" });

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Who should we invite?");
    expect(
      screen.getByText(
        "Your team is promoting a campus career event with 60 seats. Choose whom to invite, see what happened, then try again.",
      ),
    ).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Which team are you?" })).toBeDefined();
    expect(
      screen.getByText("Pick your team's number. Your team's saved work is kept under that number."),
    ).toBeDefined();
  });

  it("keeps the radio group named for the team number", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": NO_WORKSPACE });
    renderEntry();
    await screen.findByRole("radio", { name: "Team 1" });
    const group = screen.getByRole("group", { name: "Team number" });
    expect(within(group).getAllByRole("radio").length).toBe(6);
  });

  it("shows six tile skeletons and a stated loading line while the exercise loads", () => {
    stubFetch({ "/v1/exercise": "hang" });
    renderEntry();

    expect(screen.getByText("Loading the exercise…").getAttribute("role")).toBe("status");
    expect(document.querySelectorAll('[data-slot="exercise-team-tile-skeleton"]').length).toBe(6);
    // The license line holds in every state, loading included.
    expect(screen.getByText(EXERCISE_LICENSE_LINE)).toBeDefined();
  });

  it("keeps the open button reachable but unavailable until a tile is chosen, and says why", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": NO_WORKSPACE });
    renderEntry();
    await screen.findByRole("radio", { name: "Team 1" });

    const button = screen.getByRole("button", { name: "Open this team's work" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    const reasonId = button.getAttribute("aria-describedby");
    expect(reasonId).not.toBeNull();
    expect(document.getElementById(reasonId ?? "")?.textContent).toBe(
      "Pick your team's number. Your team's saved work is kept under that number.",
    );

    fireEvent.click(screen.getByRole("radio", { name: "Team 2" }));
    expect(button.getAttribute("aria-disabled")).toBeNull();
  });

  it("marks only the chosen tile as selected", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": NO_WORKSPACE });
    renderEntry();
    await screen.findByRole("radio", { name: "Team 1" });

    fireEvent.click(screen.getByRole("radio", { name: "Team 4" }));
    expect(tile(4).getAttribute("data-selected")).toBe("true");
    expect(tile(3).getAttribute("data-selected")).toBeNull();
  });

  it("pins the open button to the bottom on a phone once a tile is chosen", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": NO_WORKSPACE });
    renderEntry();
    await screen.findByRole("radio", { name: "Team 1" });

    const actions = document.querySelector('[data-slot="exercise-entry-actions"]');
    expect(actions?.getAttribute("data-sticky")).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: "Team 1" }));
    expect(actions?.getAttribute("data-sticky")).toBe("true");
  });

  it("dims the tiles and names the work in progress while the team's work opens", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": NO_WORKSPACE,
      "/v1/exercise/workspaces": "hang",
    });
    renderEntry();
    fireEvent.click(await screen.findByRole("radio", { name: "Team 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Open this team's work" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Opening your team's work…" })).toBeDefined(),
    );
    expect(tile(1).getAttribute("data-pending")).toBe("true");
    expect(tile(3).getAttribute("data-pending")).toBe("true");
  });

  it("puts the team badge beside the line naming this browser's team, hidden from readers", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": {
        body: { team_number: 4, dataset_label: "Autumn draft", invite_limit: 30 },
      },
    });
    renderEntry();
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-entry-current"]')).not.toBeNull(),
    );
    const line = document.querySelector('[data-slot="exercise-entry-current"]');
    expect(line?.textContent).toBe("This browser is already in team 4, working in Autumn draft.");
    const badge = line?.parentElement?.querySelector("svg");
    expect(badge?.getAttribute("aria-hidden")).toBe("true");
  });
});
