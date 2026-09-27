import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmWindowUnderline, useConfirmWindow } from "./confirmWindow";
import { CE_MOTION_MS, ceMotion, useCountUp, usePrefersReducedMotion } from "./motion";
import { seatFillPlan, useSeatFill, SEAT_FILL_STEP_MS } from "./seatFill";
import { stubReducedMotion } from "./testMatchMedia";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("usePrefersReducedMotion", () => {
  it("is true when the OS asks for reduced motion", () => {
    stubReducedMotion(true);
    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(true);
  });

  it("is false when it does not, and when matchMedia is missing", () => {
    stubReducedMotion(false);
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(false);
    vi.unstubAllGlobals();
    vi.stubGlobal("matchMedia", undefined);
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(false);
  });
});

describe("ceMotion", () => {
  it("fade-rise moves 8px in 240ms, and only fades in 150ms when reduced", () => {
    const full = ceMotion("fade-rise", false);
    expect(full.initial).toEqual({ opacity: 0, y: 8 });
    expect(full.transition).toMatchObject({ duration: 0.24 });
    const reduced = ceMotion("fade-rise", true);
    expect(reduced.initial).toEqual({ opacity: 0 });
    expect(reduced.transition).toMatchObject({ duration: 0.15 });
  });

  it("row-reorder springs at stiffness 500 / damping 40, and moves instantly when reduced", () => {
    expect(ceMotion("row-reorder", false).transition).toMatchObject({
      layout: { type: "spring", stiffness: 500, damping: 40 },
    });
    expect(ceMotion("row-reorder", true).transition).toMatchObject({ layout: { duration: 0 } });
  });

  it("keeps the confirm window at five seconds", () => {
    expect(CE_MOTION_MS.confirmWindow).toBe(5000);
  });
});

describe("useCountUp", () => {
  it("shows the final number at once under reduced motion", () => {
    const { result } = renderHook(() => useCountUp(46, { reduced: true }));
    expect(result.current).toBe(46);
  });

  it("counts from 0 to the value, once per mount", async () => {
    const { result, rerender } = renderHook(({ n }) => useCountUp(n, { reduced: false }), {
      initialProps: { n: 8 },
    });
    expect(result.current).toBe(0);
    await waitFor(() => expect(result.current).toBe(8), { timeout: 2000 });
    rerender({ n: 8 });
    expect(result.current).toBe(8);
  });
});

describe("useConfirmWindow", () => {
  it("arms on the first press and confirms on the second", () => {
    const onConfirm = vi.fn();
    const { result } = renderHook(() => useConfirmWindow({ onConfirm }));
    act(() => result.current.press());
    expect(result.current.armed).toBe(true);
    expect(onConfirm).not.toHaveBeenCalled();
    act(() => result.current.press());
    expect(result.current.armed).toBe(false);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("reverts when the five-second window lapses", () => {
    vi.useFakeTimers();
    const onConfirm = vi.fn();
    const { result } = renderHook(() => useConfirmWindow({ onConfirm }));
    act(() => result.current.press());
    act(() => {
      vi.advanceTimersByTime(4999);
    });
    expect(result.current.armed).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.armed).toBe(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("reverts on Escape", () => {
    const onConfirm = vi.fn();
    const { result } = renderHook(() => useConfirmWindow({ onConfirm }));
    act(() => result.current.press());
    act(() => result.current.onKeyDown({ key: "Escape" } as React.KeyboardEvent));
    expect(result.current.armed).toBe(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("ConfirmWindowUnderline", () => {
  it("draws a shrinking underline for the window", () => {
    render(<ConfirmWindowUnderline active reduced={false} />);
    const line = document.querySelector('[data-slot="ce-confirm-underline"]') as HTMLElement;
    expect(line).not.toBeNull();
    expect(line.getAttribute("aria-hidden")).toBe("true");
    expect(line.style.animationDuration).toBe("5000ms");
    expect(screen.queryByText("5 seconds")).toBeNull();
  });

  it("swaps the underline for a static helper under reduced motion", () => {
    render(<ConfirmWindowUnderline active reduced />);
    expect(document.querySelector('[data-slot="ce-confirm-underline"]')).toBeNull();
    expect(screen.getByText("5 seconds")).toBeDefined();
  });

  it("renders nothing when the window is closed", () => {
    const { container } = render(<ConfirmWindowUnderline active={false} reduced={false} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("seatFillPlan", () => {
  it("fills taken seats first, front row first, then the team's, then leaves the rest open", () => {
    const plan = seatFillPlan({ total: 60, taken: 8, added: 6 });
    expect(plan.seats).toHaveLength(60);
    expect(plan.seats.slice(0, 8).every((seat) => seat.kind === "taken")).toBe(true);
    expect(plan.seats.slice(8, 14).every((seat) => seat.kind === "added")).toBe(true);
    expect(plan.seats.slice(14).every((seat) => seat.kind === "open")).toBe(true);
    expect(plan.seats[0].delayMs).toBe(240);
    expect(plan.seats[1].delayMs).toBe(252);
    expect(plan.seats[8].delayMs).toBe(700);
    expect(plan.seats[9].delayMs).toBe(760);
    expect(plan.seats[20].delayMs).toBe(1400);
  });

  it("compresses the stagger so a big step still ends inside its window", () => {
    const plan = seatFillPlan({ total: 60, taken: 40, added: 20 });
    const lastTaken = plan.seats[39].delayMs;
    const lastAdded = plan.seats[59].delayMs;
    expect(lastTaken).toBeLessThanOrEqual(600);
    expect(lastAdded).toBeLessThanOrEqual(1300);
  });

  it("never plans more filled seats than the room holds, nor negative counts", () => {
    const plan = seatFillPlan({ total: 10, taken: 8, added: 6 });
    expect(plan.seats.filter((seat) => seat.kind === "added")).toHaveLength(2);
    expect(seatFillPlan({ total: 10, taken: -1, added: 0 }).seats.every((s) => s.kind === "open")).toBe(true);
  });
});

describe("useSeatFill", () => {
  it("lands on the final state at once under reduced motion and announces", () => {
    const { result } = renderHook(() => useSeatFill({ play: true, reduced: true }));
    expect(result.current.step).toBe(4);
    expect(result.current.announce).toBe(true);
  });

  it("shows the final state at once on a later visit (play=false)", () => {
    const { result } = renderHook(() => useSeatFill({ play: false, reduced: false }));
    expect(result.current.step).toBe(4);
    expect(result.current.announce).toBe(true);
  });

  it("walks the four steps and announces only once the fill is done", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useSeatFill({ play: true, reduced: false }));
    expect(result.current.step).toBe(1);
    act(() => {
      vi.advanceTimersByTime(SEAT_FILL_STEP_MS[2]);
    });
    expect(result.current.step).toBe(2);
    act(() => {
      vi.advanceTimersByTime(SEAT_FILL_STEP_MS[3] - SEAT_FILL_STEP_MS[2]);
    });
    expect(result.current.step).toBe(3);
    act(() => {
      vi.advanceTimersByTime(SEAT_FILL_STEP_MS[4] - SEAT_FILL_STEP_MS[3]);
    });
    expect(result.current.step).toBe(4);
    expect(result.current.announce).toBe(false);
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(result.current.announce).toBe(true);
  });

  it("skip jumps to the end", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useSeatFill({ play: true, reduced: false }));
    act(() => result.current.skip());
    expect(result.current.step).toBe(4);
    expect(result.current.announce).toBe(true);
  });
});
