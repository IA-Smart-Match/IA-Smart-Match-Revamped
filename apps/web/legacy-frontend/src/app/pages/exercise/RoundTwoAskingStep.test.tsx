import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoundStepsGate } from "./RoundTwoAskingStep";

const EVENTS = {
  events: [
    {
      event_key: "northline",
      name: "Northline",
      is_exercise_event: true,
      sequence: 1,
    },
    {
      event_key: "harbor",
      name: "Harbor",
      is_exercise_event: true,
      sequence: 2,
    },
  ],
};
const BEFORE = { major_only: 166, major_plus_events: 64, completed_card: 70 };

function stub(
  asking: Record<string, unknown>,
  workspace: Record<string, unknown> = {},
): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = url.endsWith("/events")
        ? EVENTS
        : url.endsWith("/asking-choice")
          ? { choices: [], marker_counts_before: BEFORE, ...asking }
          : {
            team_number: 1,
            dataset_label: "x",
            invite_limit: 60,
            ...workspace,
          };
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200 }),
      );
    }),
  );
}

function show(eventKey: string) {
  return render(
    <MemoryRouter>
      <RoundStepsGate eventKey={eventKey}>
        <p>THE LIST</p>
      </RoundStepsGate>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<RoundStepsGate />", () => {
  it("does not show the list while the gate is still loading", () => {
    stub({ refreshed: false, refresh_counts: null });
    show("harbor");
    expect(screen.queryByText("THE LIST")).toBeNull();
  });

  it("hides the Harbor list until the team has asked", async () => {
    stub({ refreshed: false, refresh_counts: null });
    show("harbor");
    await screen.findByText("Step 1: ask students for more information");
    expect(screen.queryByText("THE LIST")).toBeNull();
  });

  it("shows the how-much-we-know table above the round-one list", async () => {
    stub({ refreshed: false, refresh_counts: null });
    show("northline");
    await waitFor(() => expect(screen.getByText("THE LIST")).toBeDefined());
    expect(
      screen.getByText("How much we know about all 300 students"),
    ).toBeDefined();
  });

  it("says round 2 opens after Northline results when it is still locked", async () => {
    stub({ refreshed: false, refresh_counts: null }, { round_two_open: false });
    show("harbor");
    await screen.findByText("Round 2 opens after your Northline results.");
    expect(screen.queryByText("THE LIST")).toBeNull();
  });

  it("lists each how-much-we-know group with its count in round one", async () => {
    stub({ refreshed: false, refresh_counts: null });
    show("northline");
    await screen.findByText("THE LIST");
    const lines = Array.from(
      document.querySelectorAll("[data-slot='exercise-marker-counts-before'] li"),
    ).map((li) => li.textContent ?? "");
    expect(lines).toHaveLength(3);
    expect(lines.join(" ")).toMatch(/166/);
    expect(lines.join(" ")).toMatch(/64/);
    expect(lines.join(" ")).toMatch(/70/);
  });

  it("does not repeat round one's attendance on the round-two asking step", async () => {
    const counts = {
      cards_completed: 12,
      non_responding: 5,
      topics_added: 3,
      asked_without_card: 230,
      marker_counts_before: BEFORE,
      marker_counts_after: { major_only: 150, major_plus_events: 70, completed_card: 80 },
    };
    stub({ refreshed: true, refresh_counts: counts, first_round_event_name: "Northline" });
    show("harbor");
    await screen.findByText("THE LIST");
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/attended/i);
    expect(text).not.toMatch(/signed up/i);
  });
});
