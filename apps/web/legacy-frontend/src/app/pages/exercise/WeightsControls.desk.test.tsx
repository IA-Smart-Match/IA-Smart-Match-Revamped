/**
 * The weights as four desk sliders (DESIGN.md §6.6, owner ruling 2) and the
 * phone's sticky compact bar (§7.4).
 *
 * `WeightsControls.test.tsx` pins the queue and the strict-decimal rule
 * through the number boxes; this file pins what the slider adds: a slider per
 * factor, a key step that commits once, the refusal sentence under the slider
 * it was about, and a way back to the sliders once they scroll away on 390.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseRefusal } from "../../../lib/exerciseApi";
import { WeightsControls } from "./WeightsControls";

const LABELS = {
  same_major: "same major",
  stated_interest_overlap: "said they are interested in this topic",
  career_goal_fit: "career goal fits this event",
  past_event_topic_overlap: "went to similar events before",
  undecided_goal_half: "undecided goal suits a broad event",
};

const WEIGHTS = {
  same_major: 0.4,
  stated_interest_overlap: 0.25,
  career_goal_fit: 0.25,
  past_event_topic_overlap: 0.1,
};

type ObserverCallback = (entries: { isIntersecting: boolean }[]) => void;
let observed: ObserverCallback | null = null;

function stubViewport(narrow: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: narrow && query.includes("max-width: 767px"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })),
  );
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: ObserverCallback) {
        observed = callback;
      }
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    },
  );
}

beforeEach(() => {
  observed = null;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<WeightsControls /> sliders (§6.6)", () => {
  it("draws one slider per weight, named in the server's words, and none for the Undecided label", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(4);
    expect(screen.getByRole("slider", { name: "same major" }).getAttribute("aria-valuenow")).toBe(
      "0.4",
    );
    expect(screen.queryByRole("slider", { name: LABELS.undecided_goal_half })).toBeNull();
  });

  it("says when the list is rebuilt", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    expect(
      screen.getByText("The list is rebuilt when you let go of a slider or press Enter."),
    ).toBeDefined();
  });

  it("commits a key step once, merged onto the confirmed weights", () => {
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "same major" }), { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: 0.45 });
  });

  it("puts a refused commit's sentence under that slider and returns it to the confirmed weight", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />,
    );
    const slider = screen.getByRole("slider", { name: "same major" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });

    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={WEIGHTS}
        onChange={onChange}
        refusal={new ExerciseRefusal(400, "exercise_invalid_weights", "Those weights were not accepted.")}
      />,
    );

    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0].textContent).toBe("Those weights were not accepted.");
    expect(slider.getAttribute("aria-valuenow")).toBe("0.4");
    const box = screen.getByRole("textbox", { name: "same major" }) as HTMLInputElement;
    expect(box.value).toBe("0.40");
  });

  it("shows a spinner beside the weight being rebuilt, and keeps every control live", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "same major" }), { key: "ArrowRight" });
    expect(document.querySelectorAll('[data-slot="ce-weight-pending"]')).toHaveLength(1);
    for (const box of screen.getAllByRole("textbox")) {
      expect((box as HTMLInputElement).disabled).toBe(false);
    }
  });
});

describe("<WeightsControls /> compact bar on 390 (§7.4)", () => {
  it("appears once the sliders scroll out of view, with the four values", () => {
    stubViewport(true);
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    expect(document.querySelector('[data-slot="exercise-weights-bar"]')).toBeNull();

    act(() => observed?.([{ isIntersecting: false }]));

    const bar = document.querySelector('[data-slot="exercise-weights-bar"]');
    expect(bar?.textContent).toContain("Weights 0.40 · 0.25 · 0.25 · 0.10");
    expect(screen.getByRole("button", { name: "Edit weights" })).toBeDefined();

    act(() => observed?.([{ isIntersecting: true }]));
    expect(document.querySelector('[data-slot="exercise-weights-bar"]')).toBeNull();
  });

  it("scrolls back to the sliders and focuses the first one", () => {
    stubViewport(true);
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    act(() => observed?.([{ isIntersecting: false }]));

    fireEvent.click(screen.getByRole("button", { name: "Edit weights" }));

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(screen.getByRole("slider", { name: "same major" }));
  });

  it("never appears on a desktop width", () => {
    stubViewport(false);
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    act(() => observed?.([{ isIntersecting: false }]));
    expect(document.querySelector('[data-slot="exercise-weights-bar"]')).toBeNull();
  });
});
