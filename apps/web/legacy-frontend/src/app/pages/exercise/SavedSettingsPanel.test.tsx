/**
 * The saved-setting cards (DESIGN.md §6.11): a quiet "Delete" that asks first,
 * inline, and a "Compare" tick box on each card that stops at two.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SavedSettingsView } from "../../../lib/exerciseClient";
import { SavedSettingsPanel } from "./SavedSettingsPanel";

const LABELS = {
  same_major: "same major",
  stated_interest_overlap: "said they are interested in this topic",
  career_goal_fit: "career goal fits this event",
  past_event_topic_overlap: "went to similar events before",
};

const WEIGHTS = {
  same_major: 0.6,
  stated_interest_overlap: 0.15,
  career_goal_fit: 0.15,
  past_event_topic_overlap: 0.1,
};

function saved(names: readonly string[], max = 3): SavedSettingsView {
  return {
    event_key: "northline",
    settings: names.map((name) => ({ name, weights: WEIGHTS, created_at: "2026-09-25T10:00:00Z" })),
    max_settings: max,
  };
}

function renderPanel(names: readonly string[], overrides: { onDelete?: () => Promise<boolean> } = {}) {
  const onDelete = vi.fn(overrides.onDelete ?? (() => Promise.resolve(true)));
  const onCompare = vi.fn();
  render(
    <SavedSettingsPanel
      saved={saved(names)}
      weights={WEIGHTS}
      factorLabels={LABELS}
      onSave={vi.fn(() => Promise.resolve(true))}
      onDelete={onDelete}
      onOpen={vi.fn()}
      onCompare={onCompare}
    />,
  );
  return { onDelete, onCompare };
}

afterEach(cleanup);

describe("<SavedSettingsPanel />", () => {
  it("shows each card's four weights as numbers, in Ann's words", () => {
    renderPanel(["Major first"]);
    const card = document.querySelector('[data-slot="exercise-setting-card"]');
    expect(card?.textContent).toContain("same major0.60");
    expect(card?.textContent).toContain("went to similar events before0.10");
  });

  it("offers the free slots in words", () => {
    renderPanel(["Major first"]);
    expect(
      screen.getByText("Slot 2 of 3 is free. Save the weights on screen to fill it."),
    ).toBeDefined();
    expect(
      screen.getByText("Slot 3 of 3 is free. Save the weights on screen to fill it."),
    ).toBeDefined();
  });

  it("asks before deleting, and 'Keep it' takes the question back", () => {
    const { onDelete } = renderPanel(["Balanced"]);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByText("Delete Balanced? It cannot be brought back.")).toBeDefined();
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(screen.queryByText("Delete Balanced? It cannot be brought back.")).toBeNull();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("deletes on the red confirm, the only red on the card", async () => {
    const { onDelete } = renderPanel(["Balanced"]);
    // The first "Delete" is quiet green text, never red.
    const quiet = screen.getByRole("button", { name: "Delete" });
    expect(quiet.className).toContain("ce-btn-quiet");
    expect(quiet.className).not.toContain("ce-btn-danger");
    fireEvent.click(quiet);
    const confirm = screen.getByRole("button", { name: "Delete it" });
    expect(confirm.className).toContain("ce-btn-danger");
    fireEvent.click(confirm);
    await waitFor(() => expect(onDelete).toHaveBeenCalledTimes(1));
  });

  it("stops at two ticked cards and says how to swap", () => {
    const { onCompare } = renderPanel(["Major first", "Interests first", "Balanced"]);
    const [first, second, third] = screen.getAllByRole("checkbox", { name: "Compare" }) as HTMLInputElement[];
    const show = screen.getByRole("button", { name: /show them side by side/i }) as HTMLButtonElement;
    expect(show.disabled).toBe(true);

    fireEvent.click(first);
    fireEvent.click(second);
    expect(third.disabled).toBe(true);
    expect(screen.getByText("Two are chosen. Untick one to swap.")).toBeDefined();
    expect(screen.getAllByText("Comparing")).toHaveLength(2);

    fireEvent.click(show);
    expect(onCompare).toHaveBeenCalledWith("Major first", "Interests first");

    fireEvent.click(first);
    expect(third.disabled).toBe(false);
  });

  it("asks for two settings before comparing when fewer are saved", () => {
    renderPanel(["Major first"]);
    expect(screen.getByText("Save two settings to see them side by side.")).toBeDefined();
    expect(screen.queryByRole("button", { name: /show them side by side/i })).toBeNull();
  });
});
