/**
 * The soft-studio tour opens by itself only on a browser's first visit, and
 * after that only from the Tour button. Every deck step is a full page load,
 * so "first visit" has to survive one.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SoftStudioTour } from "./SoftStudioTour";

const KEY = "smartmatch-exercise-tour-v1";

beforeEach(() => {
  window.localStorage.clear();
  vi.useFakeTimers();
  // The tour stays shut under the test mode; these tests are about the real one.
  vi.stubEnv("MODE", "production");
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  window.localStorage.clear();
});

function settle(): void {
  act(() => {
    vi.advanceTimersByTime(1000);
  });
}

describe("SoftStudioTour", () => {
  it("opens by itself on the first visit and marks itself seen", () => {
    render(<SoftStudioTour />);
    settle();
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(window.localStorage.getItem(KEY)).not.toBeNull();
  });

  it("does not open by itself on the next page, even if the first was never closed", () => {
    const first = render(<SoftStudioTour />);
    settle();
    first.unmount();

    render(<SoftStudioTour />);
    settle();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens from the Tour button whenever it is pressed", () => {
    window.localStorage.setItem(KEY, "seen");
    render(<SoftStudioTour />);
    settle();
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Replay the exercise tour" }));
    expect(screen.getByRole("dialog")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Replay the exercise tour" }));
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it("has no \"Don't show this again\" box: it never needs one", () => {
    render(<SoftStudioTour />);
    settle();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("walks six steps with no mascot picture in the card", () => {
    render(<SoftStudioTour />);
    settle();
    const dialog = screen.getByRole("dialog");
    expect(dialog.querySelector("img")).toBeNull();
    expect(screen.getByText("1 of 6")).toBeDefined();

    const seen: string[] = [];
    for (let i = 0; i < 6; i += 1) {
      seen.push(screen.getByRole("heading", { level: 2 }).textContent ?? "");
      if (i < 5) fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    expect(seen).not.toContain("Try it together");
    expect(seen[5]).toBe("You're ready");
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
