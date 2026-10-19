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

function stub(asking: Record<string, unknown>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = url.endsWith("/events")
        ? EVENTS
        : url.endsWith("/asking-choice")
          ? { choices: [], marker_counts_before: BEFORE, ...asking }
          : { team_number: 1, dataset_label: "x", invite_limit: 60 };
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
      screen.getByText("How much we know, all 300 profiles"),
    ).toBeDefined();
  });
});
