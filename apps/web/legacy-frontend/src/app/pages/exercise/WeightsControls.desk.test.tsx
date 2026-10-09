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
};

const WEIGHTS = {
  same_major: 3,
  stated_interest_overlap: 3,
  career_goal_fit: 2,
  past_event_topic_overlap: 2,
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
  it("draws one slider per weight, named in the server's words", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(4);
    expect(screen.getByRole("slider", { name: "same major" }).getAttribute("aria-valuenow")).toBe(
      "3",
    );
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
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: 4 });
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
        refusal={new ExerciseRefusal(400, "exercise_weights_invalid", "Those weights were not accepted.")}
      />,
    );

    // A server refusal is a status, not an alert (§8.6).
    const shown = document.querySelectorAll('[data-slot="exercise-weight-error"]');
    expect(shown).toHaveLength(1);
    expect(shown[0].textContent).toBe("Those weights were not accepted.");
    expect(shown[0].getAttribute("role")).toBe("status");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(slider.getAttribute("aria-valuenow")).toBe("3");
    const box = screen.getByRole("textbox", { name: "same major" }) as HTMLInputElement;
    expect(box.value).toBe("3");
  });

  it("shows a refusal of a several-weight commit once, and reverts every weight it changed", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />,
    );
    const major = screen.getByRole("slider", { name: "same major" });
    const interest = screen.getByRole("slider", { name: LABELS.stated_interest_overlap });
    const goal = screen.getByRole("slider", { name: LABELS.career_goal_fit });

    // One in flight, two queued behind it.
    fireEvent.keyDown(major, { key: "ArrowRight" });
    fireEvent.keyDown(interest, { key: "ArrowRight" });
    fireEvent.keyDown(goal, { key: "ArrowRight" });
    const accepted = { ...WEIGHTS, same_major: 4 };
    rerender(<WeightsControls factorLabels={LABELS} weights={accepted} onChange={onChange} />);
    expect(onChange).toHaveBeenLastCalledWith({
      ...accepted,
      stated_interest_overlap: 4,
      career_goal_fit: 3,
    });

    // The merged commit is refused.
    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={accepted}
        onChange={onChange}
        refusal={new ExerciseRefusal(400, "exercise_weights_invalid", "Those weights were not accepted.")}
      />,
    );

    expect(document.querySelectorAll('[data-slot="exercise-weight-error"]')).toHaveLength(1);
    expect(screen.getAllByText("Those weights were not accepted.")).toHaveLength(1);
    const after = (name: string) =>
      screen.getByRole("slider", { name }).getAttribute("aria-valuenow");
    expect(after(LABELS.stated_interest_overlap)).toBe("3");
    expect(after(LABELS.career_goal_fit)).toBe("2");
    expect((screen.getByRole("textbox", { name: LABELS.career_goal_fit }) as HTMLInputElement).value).toBe(
      "2",
    );
    expect(after("same major")).toBe("4");
  });

  it("reverts an Enter commit refused while the team is still in the box, once they leave it", () => {
    // #251 review H1: the refusal landed while focus was in the box, so the
    // slider never heard it — box -0.50, thumb 0, confirmed 0.25, and
    // leaving the box sent nothing.
    const onChange = vi.fn();
    const { rerender } = render(
      <WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />,
    );
    const box = screen.getByRole("textbox", { name: "same major" }) as HTMLInputElement;
    const slider = screen.getByRole("slider", { name: "same major" });
    box.focus();
    fireEvent.change(box, { target: { value: "-1" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: -1 });

    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={WEIGHTS}
        onChange={onChange}
        refusal={new ExerciseRefusal(422, "exercise_weights_invalid", "Those weights were not accepted.")}
      />,
    );

    // Still in the box: its text stays, and the box names the sentence.
    expect(box.value).toBe("-1");
    const whileIn = document.querySelectorAll('[data-slot="exercise-weight-error"]');
    expect(whileIn).toHaveLength(1);
    expect(whileIn[0].id).not.toBe("");
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(box.getAttribute("aria-describedby")).toBe(whileIn[0].id);

    act(() => box.blur());

    expect(box.value).toBe("3");
    expect(slider.getAttribute("aria-valuenow")).toBe("3");
    const after = document.querySelectorAll('[data-slot="exercise-weight-error"]');
    expect(after).toHaveLength(1);
    expect(after[0].textContent).toBe("Those weights were not accepted.");
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(box.getAttribute("aria-describedby")).toBe(after[0].id);
    // Leaving the box does not resend the refused number.
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("sends one weights request for a whole pointer drag, not one per move", () => {
    // #251 review M5: a drag that commits on every tick must fail here. The
    // queue would hide a per-tick commit behind the first request, so the
    // first request is also settled and must not be followed by another.
    const proto = Element.prototype as unknown as Record<string, unknown>;
    const saved = {
      set: proto.setPointerCapture,
      release: proto.releasePointerCapture,
      has: proto.hasPointerCapture,
      rect: proto.getBoundingClientRect,
    };
    proto.setPointerCapture = vi.fn();
    proto.releasePointerCapture = vi.fn();
    proto.hasPointerCapture = vi.fn(() => true);
    // jsdom has no PointerEvent, so `clientX` would be dropped from the init.
    class TestPointerEvent extends MouseEvent {
      readonly pointerId: number;
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 0;
      }
    }
    vi.stubGlobal("PointerEvent", TestPointerEvent);
    proto.getBoundingClientRect = () =>
      ({ left: 0, top: 0, right: 100, bottom: 44, width: 100, height: 44, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    try {
      const onChange = vi.fn();
      const { rerender } = render(
        <WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />,
      );
      const root = screen
        .getByRole("textbox", { name: "same major" })
        .closest('[data-slot="ce-weight-slider"]')
        ?.querySelector("[data-dragging]") as HTMLElement;

      fireEvent.pointerDown(root, { pointerId: 1, button: 0, clientX: 50 });
      for (const clientX of [55, 60, 65, 70]) {
        fireEvent.pointerMove(root, { pointerId: 1, clientX });
      }
      expect(onChange).not.toHaveBeenCalled();
      fireEvent.pointerUp(root, { pointerId: 1, clientX: 70 });

      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenLastCalledWith({ ...WEIGHTS, same_major: 7 });

      rerender(
        <WeightsControls
          factorLabels={LABELS}
          weights={{ ...WEIGHTS, same_major: 7 }}
          onChange={onChange}
        />,
      );
      expect(onChange).toHaveBeenCalledTimes(1);
    } finally {
      proto.setPointerCapture = saved.set;
      proto.releasePointerCapture = saved.release;
      proto.hasPointerCapture = saved.has;
      proto.getBoundingClientRect = saved.rect;
      vi.unstubAllGlobals();
    }
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

describe("<WeightsControls /> total weight (§6.6, owner ruling 2026-09-28)", () => {
  const totalText = (): string | null | undefined =>
    document.querySelector('[data-slot="exercise-weight-total"]')?.textContent;

  it("shows the total and what it means, and no percentage anywhere in the weights", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    expect(totalText()).toContain("Total weight: 10");
    expect(
      screen.getByText(
        "What matters is how the weights compare: a factor set to 6 counts twice as much as one set to 3.",
      ),
    ).toBeDefined();
    const section = document.querySelector('[data-slot="exercise-weights"]');
    expect(section?.textContent).not.toContain("%");
    expect(screen.queryByText("At least one number must be above 0.")).toBeNull();
  });

  it("updates the total after a key step", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "same major" }), { key: "ArrowRight" });
    expect(totalText()).toContain("Total weight: 11");
    expect(document.querySelector('[data-slot="exercise-weights"]')?.textContent).not.toContain("%");
  });

  it("follows typing before anything is committed, and is not capped at 10", () => {
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);
    fireEvent.change(screen.getByRole("textbox", { name: "same major" }), { target: { value: "9" } });
    expect(totalText()).toContain("Total weight: 16");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("says a zero total cannot be used, as a status", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    for (const box of screen.getAllByRole("textbox")) {
      fireEvent.change(box, { target: { value: "0" } });
    }
    expect(totalText()).toContain("Total weight: 0");
    const notice = screen.getByText("At least one number must be above 0.");
    expect(notice.getAttribute("role")).toBe("status");
  });

  it("does not repeat the zero sentence while the server's refusal is shown", () => {
    const zero = { same_major: 0, stated_interest_overlap: 0, career_goal_fit: 0, past_event_topic_overlap: 0 };
    const start = { ...zero, same_major: 3 };
    const onChange = vi.fn();
    const { rerender } = render(
      <WeightsControls factorLabels={LABELS} weights={start} onChange={onChange} />,
    );
    // Typed and sent from the box, which keeps its "0" while the team is in it,
    // so the total on screen stays 0 when the refusal lands.
    const box = screen.getByRole("textbox", { name: "same major" }) as HTMLInputElement;
    box.focus();
    fireEvent.change(box, { target: { value: "0" } });
    expect(screen.getAllByText("At least one number must be above 0.")).toHaveLength(1);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onChange).toHaveBeenLastCalledWith(zero);
    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={start}
        onChange={onChange}
        refusal={new ExerciseRefusal(422, "exercise_weights_invalid", "At least one number must be above 0.")}
      />,
    );
    expect(totalText()).toContain("Total weight: 0");
    const shown = screen.getAllByText("At least one number must be above 0.");
    expect(shown).toHaveLength(1);
    expect(shown[0].getAttribute("data-slot")).toBe("exercise-weight-error");
  });
});

describe("<WeightsControls /> compact bar on 390 (§7.4)", () => {
  it("appears once the sliders scroll out of view, with the four values", () => {
    stubViewport(true);
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    expect(document.querySelector('[data-slot="exercise-weights-bar"]')).toBeNull();

    act(() => observed?.([{ isIntersecting: false }]));

    const bar = document.querySelector('[data-slot="exercise-weights-bar"]');
    expect(bar?.textContent).toContain("Weights 3 · 3 · 2 · 2");
    expect(bar?.textContent).toContain("Total 10");
    expect(bar?.textContent).not.toContain("%");
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
