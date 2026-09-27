/**
 * Saved-setting cards (DESIGN.md §6.11, §7.5).
 *
 * `ExerciseMatching.test.tsx` pins the save flow against the API; this file
 * pins the cards: one slot per `max_settings`, weights in Ann's words as
 * numbers, "Compare" toggles capped at two, and Delete behind an inline
 * confirm.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SavedSettingsView } from "../../../lib/exerciseClient";
import { SavedSettingsPanel } from "./SavedSettingsPanel";

const LABELS = {
  same_major: "same major",
  stated_interest_overlap: "said they are interested in this topic",
  career_goal_fit: "career goal fits this event",
  past_event_topic_overlap: "went to similar events before",
  undecided_goal_half: "undecided goal suits a broad event",
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

function renderPanel(view: SavedSettingsView) {
  const props = {
    onSave: vi.fn(async () => true),
    onDelete: vi.fn(async () => true),
    onOpen: vi.fn(),
    onCompare: vi.fn(),
  };
  render(
    <SavedSettingsPanel saved={view} weights={WEIGHTS} factorLabels={LABELS} {...props} />,
  );
  return props;
}

afterEach(cleanup);

describe("<SavedSettingsPanel /> cards (§6.11)", () => {
  it("draws one slot per max_settings and says which are free", () => {
    renderPanel(saved(["Major first"], 3));
    expect(document.querySelectorAll('[data-slot="exercise-setting-card"]')).toHaveLength(1);
    expect(
      screen.getByText("Slot 2 of 3 is free. Save the weights on screen to fill it."),
    ).toBeDefined();
    expect(
      screen.getByText("Slot 3 of 3 is free. Save the weights on screen to fill it."),
    ).toBeDefined();
  });

  it("lists a card's weights in Ann's words, as numbers, and never a rulebook key", () => {
    renderPanel(saved(["Major first"]));
    const card = document.querySelector('[data-slot="exercise-setting-card"]') as HTMLElement;
    expect(within(card).getByText("same major")).toBeDefined();
    expect(within(card).getByText("0.60")).toBeDefined();
    expect(within(card).getByText("0.10")).toBeDefined();
    expect(card.textContent).not.toContain("same_major");
    expect(card.textContent).not.toContain(LABELS.undecided_goal_half);
  });

  it("labels the name box 'Name these weights'", () => {
    renderPanel(saved([]));
    expect(screen.getByLabelText("Name these weights")).toBeDefined();
  });

  it("caps Compare at two, says why, and compares in the order ticked", () => {
    const { onCompare } = renderPanel(saved(["Major first", "Interests first", "Balanced"]));
    const show = screen.getByRole("button", { name: /show them side by side/i });
    expect(show.getAttribute("aria-disabled")).toBe("true");

    fireEvent.click(screen.getByRole("checkbox", { name: "Compare Interests first" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Compare Major first" }));

    const third = screen.getByRole("checkbox", { name: "Compare Balanced" }) as HTMLInputElement;
    expect(third.disabled).toBe(true);
    const why = screen.getByText("Two are chosen. Untick one to swap.");
    expect(third.getAttribute("aria-describedby")).toBe(why.id);
    expect(screen.getAllByText("Comparing")).toHaveLength(2);

    fireEvent.click(show);
    expect(onCompare).toHaveBeenCalledWith("Interests first", "Major first");
  });

  it("asks before deleting, and 'Keep it' keeps it", async () => {
    const { onDelete } = renderPanel(saved(["Balanced"]));
    fireEvent.click(screen.getByRole("button", { name: "Delete Balanced" }));
    expect(screen.getByText("Delete Balanced? It cannot be brought back.")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByText("Delete Balanced? It cannot be brought back.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Delete Balanced" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete it" }));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith("Balanced"));
  });

  it("does not save a new name at the cap, even from the keyboard", () => {
    const { onSave } = renderPanel(saved(["One", "Two", "Three"]));
    const box = screen.getByLabelText("Name these weights");
    fireEvent.change(box, { target: { value: "Four" } });
    const save = screen.getByRole("button", { name: /save these weights/i });
    expect(save.getAttribute("aria-disabled")).toBe("true");
    fireEvent.submit(box.closest("form") as HTMLFormElement);
    expect(onSave).not.toHaveBeenCalled();
  });
});
