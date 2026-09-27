/**
 * `ce-seat-fill`, the results moment (DESIGN.md §5.1), and its reduced-motion
 * path.
 *
 * It plays only when asked to (the first render after a run), steps through
 * taken → added → open, counts the figures up once, and announces the three
 * sentences once at the end. Under `prefers-reduced-motion: reduce` it shows
 * the final state at once, with the same words.
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SeatReveal } from "./SeatReveal";

const COUNTS = { seats: 60, alreadyComing: 8, added: 6, open: 46 };
const SENTENCES = "8 were already coming. Your invitations added 6. 46 seats are still open.";

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

function slot(name: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-slot="${name}"]`);
  if (element === null) {
    throw new Error(`no ${name}`);
  }
  return element;
}

function seatClasses(): string[] {
  return [...slot("exercise-room").querySelectorAll(".grid-cols-10 > span")].map(
    (seat) => seat.className,
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("<SeatReveal />", () => {
  it("shows the final state on a later visit, with nothing to play", () => {
    mockReducedMotion(false);
    render(<SeatReveal counts={COUNTS} sentences={SENTENCES} reveal={false} />);
    expect(slot("exercise-seats-sentence").getAttribute("data-phase")).toBe("4");
    expect(slot("exercise-seats-sentence").textContent).toBe(SENTENCES);
    expect(slot("exercise-seats").textContent).toContain("Seats in the room60");
    expect(slot("exercise-seats-announce").textContent).toBe(SENTENCES);
    const seats = seatClasses();
    expect(seats).toHaveLength(60);
    expect(seats.filter((seat) => seat.includes("bg-ce-seat-taken"))).toHaveLength(8);
    expect(seats.filter((seat) => seat.includes("bg-ce-primary"))).toHaveLength(6);
  });

  it("fills the seats in order after a run, and announces once at the end", () => {
    mockReducedMotion(false);
    render(<SeatReveal counts={COUNTS} sentences={SENTENCES} reveal />);

    // Step 0: nothing announced, figures start from 0.
    expect(slot("exercise-seats-sentence").getAttribute("data-phase")).toBe("0");
    expect(slot("exercise-seats-announce").textContent).toBe("");
    expect(slot("exercise-seats").textContent).toContain("Seats in the room0");

    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(slot("exercise-seats-sentence").getAttribute("data-phase")).toBe("2");
    expect(seatClasses().filter((seat) => seat.includes("bg-ce-seat-taken"))).toHaveLength(8);
    expect(seatClasses().filter((seat) => seat.includes("bg-ce-primary"))).toHaveLength(0);

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(slot("exercise-seats-sentence").getAttribute("data-phase")).toBe("3");
    expect(seatClasses().filter((seat) => seat.includes("bg-ce-primary"))).toHaveLength(6);
    expect(slot("exercise-seats-announce").textContent).toBe("");

    act(() => {
      vi.advanceTimersByTime(1200);
    });
    expect(slot("exercise-seats-sentence").getAttribute("data-phase")).toBe("4");
    expect(slot("exercise-seats-announce").textContent).toBe(SENTENCES);
    expect(slot("exercise-seats").textContent).toContain("Seats in the room60");
    expect(slot("exercise-seats").textContent).toContain("Still open46");
  });

  it("skips the animation under reduced motion and shows everything at once", () => {
    mockReducedMotion(true);
    render(<SeatReveal counts={COUNTS} sentences={SENTENCES} reveal />);
    expect(slot("exercise-seats-sentence").getAttribute("data-phase")).toBe("4");
    expect(slot("exercise-seats-announce").textContent).toBe(SENTENCES);
    // No count-up: the final figures are there on the first frame.
    expect(slot("exercise-seats").textContent).toContain("Seats in the room60");
    expect(slot("exercise-seats").textContent).toContain("Already coming8");
    expect(seatClasses().filter((seat) => seat.includes("bg-ce-primary"))).toHaveLength(6);
    expect(seatClasses().some((seat) => seat.includes("ce-seat-pop"))).toBe(false);
  });

  it("keeps the chart out of the accessibility tree; the words carry it", () => {
    mockReducedMotion(false);
    render(<SeatReveal counts={COUNTS} sentences={SENTENCES} reveal={false} />);
    const grid = slot("exercise-room").querySelector(".grid-cols-10")?.parentElement;
    expect(grid?.getAttribute("aria-hidden")).toBe("true");
    expect(slot("exercise-room").textContent).toContain("Your invitations (6)");
  });
});
