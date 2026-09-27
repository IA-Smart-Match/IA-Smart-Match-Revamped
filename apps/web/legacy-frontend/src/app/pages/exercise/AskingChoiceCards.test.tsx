/**
 * The asking choice's inline confirm (owner ruling 2026-09-26, DESIGN.md
 * §6.18): the first press arms the same button as "Confirm: A small reward?"
 * for about five seconds; the second press commits; a lapse, Escape, or
 * arming another card puts it back. No modal. Reduced motion keeps the label
 * swap and swaps the moving underline for a static "5 seconds" note.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChoiceCard, CONFIRM_WINDOW_MS, ConfirmLiveRegion, useConfirmWindow } from "./AskingChoiceCards";

const CHOICES = ["better_recommendations", "small_reward", "required"];

/** The screen's own wiring, without the network: map the choices, share one window. */
function Harness({
  onChoose,
  chosen = null,
}: {
  readonly onChoose: (choice: string) => void;
  readonly chosen?: string | null;
}) {
  const confirm = useConfirmWindow(chosen);
  return (
    <>
      <ul>
        {CHOICES.map((choice) => (
          <li key={choice}>
            <ChoiceCard
              choice={choice}
              chosen={chosen === choice}
              faded={chosen !== null && chosen !== choice}
              locked={chosen !== null}
              armed={confirm.armed === choice}
              pending={false}
              reduced={confirm.reduced}
              hint={confirm.armed === choice ? confirm.hint : ""}
              onPress={() => confirm.press(choice, onChoose)}
              onEscape={confirm.disarm}
            />
          </li>
        ))}
      </ul>
      <ConfirmLiveRegion hint={confirm.hint} />
    </>
  );
}

function mockReducedMotion(reduce: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

function live(): string {
  return document.querySelector('[data-slot="exercise-asking-confirm-live"]')?.textContent ?? "";
}

beforeEach(() => {
  vi.useFakeTimers();
  mockReducedMotion(false);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("asking choice inline confirm", () => {
  it("arms on the first press, without choosing, and says so politely", () => {
    const onChoose = vi.fn();
    render(<Harness onChoose={onChoose} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: A small reward." }));

    const armed = screen.getByRole("button", { name: "Confirm: A small reward?" });
    expect(armed.textContent).toContain("Confirm: A small reward?");
    expect(armed.className).toContain("ce-btn-primary");
    expect(armed.querySelector('[data-slot="exercise-confirm-underline"]')).not.toBeNull();
    expect(onChoose).not.toHaveBeenCalled();
    expect(live()).toBe("Press again to confirm A small reward. Your team picks once.");
    // No pop-up of any kind.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("commits on the second press inside the window", () => {
    const onChoose = vi.fn();
    render(<Harness onChoose={onChoose} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: A small reward." }));
    act(() => {
      vi.advanceTimersByTime(CONFIRM_WINDOW_MS - 1000);
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm: A small reward?" }));
    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith("small_reward");
    expect(live()).toBe("");
  });

  it("reverts when the window lapses, so a late press only arms again", () => {
    const onChoose = vi.fn();
    render(<Harness onChoose={onChoose} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: A small reward." }));
    act(() => {
      vi.advanceTimersByTime(CONFIRM_WINDOW_MS);
    });
    expect(screen.queryByRole("button", { name: "Confirm: A small reward?" })).toBeNull();
    expect(live()).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: A small reward." }));
    expect(onChoose).not.toHaveBeenCalled();
  });

  it("reverts on Escape", () => {
    const onChoose = vi.fn();
    render(<Harness onChoose={onChoose} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: Required." }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Confirm: Required?" }), {
      key: "Escape",
    });
    expect(screen.getByRole("button", { name: "Choose this way: Required." })).toBeDefined();
    expect(onChoose).not.toHaveBeenCalled();
  });

  it("reverts the first card when another card is armed", () => {
    const onChoose = vi.fn();
    render(<Harness onChoose={onChoose} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: A small reward." }));
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: Required." }));
    expect(screen.queryByRole("button", { name: "Confirm: A small reward?" })).toBeNull();
    expect(screen.getByRole("button", { name: "Confirm: Required?" })).toBeDefined();
    expect(onChoose).not.toHaveBeenCalled();
  });

  it("under reduced motion keeps the label swap, drops the moving underline, and states the window", () => {
    mockReducedMotion(true);
    render(<Harness onChoose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose this way: A small reward." }));
    const armed = screen.getByRole("button", { name: "Confirm: A small reward?" });
    expect(armed.querySelector('[data-slot="exercise-confirm-underline"]')).toBeNull();
    expect(document.querySelector('[data-slot="exercise-confirm-static"]')?.textContent).toContain(
      "5 seconds",
    );
  });

  it("shows the team's pick with no buttons left to press", () => {
    render(<Harness onChoose={vi.fn()} chosen="small_reward" />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText("Your team chose this.")).toBeDefined();
    const cards = [...document.querySelectorAll('[data-slot="exercise-asking-card"]')];
    expect(cards.map((card) => card.getAttribute("data-state"))).toEqual(["idle", "chosen", "idle"]);
    expect(cards[0].className).toContain("opacity-55");
  });
});
