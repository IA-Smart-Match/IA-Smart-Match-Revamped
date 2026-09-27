import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { stubReducedMotion } from "./testMatchMedia";
import { WeightSlider } from "./WeightSlider";
import { clampWeight, formatWeight, strictDecimal } from "./weightValue";

beforeEach(() => {
  stubReducedMotion(false);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const LABEL = "said they are interested in this topic";

function renderSlider(props: Partial<React.ComponentProps<typeof WeightSlider>> = {}) {
  const onCommit = vi.fn();
  const utils = render(
    <WeightSlider id="interest" label={LABEL} value={0.4} onCommit={onCommit} {...props} />,
  );
  const slider = screen.getByRole("slider", { name: LABEL });
  const field = screen.getByRole("textbox", { name: LABEL }) as HTMLInputElement;
  return { ...utils, onCommit, slider, field };
}

describe("weightValue helpers", () => {
  it("accepts only a plain decimal", () => {
    expect(strictDecimal("0.5")).toBe(0.5);
    expect(strictDecimal(".5")).toBe(0.5);
    expect(strictDecimal("1,5")).toBeNull();
    expect(strictDecimal("0.5abc")).toBeNull();
    expect(strictDecimal("5.")).toBeNull();
    expect(strictDecimal("")).toBeNull();
  });

  it("clamps to 0–1 and formats to two decimals when exact", () => {
    expect(clampWeight(1.5)).toBe(1);
    expect(clampWeight(-0.2)).toBe(0);
    expect(formatWeight(0.4)).toBe("0.40");
    expect(formatWeight(1)).toBe("1.00");
    expect(formatWeight(0.333)).toBe("0.333");
  });
});

describe("WeightSlider (§6.6)", () => {
  it("labels both the slider and the number box with the server's words", () => {
    const { slider, field } = renderSlider();
    expect(slider.getAttribute("aria-valuemin")).toBe("0");
    expect(slider.getAttribute("aria-valuemax")).toBe("1");
    expect(slider.getAttribute("aria-valuenow")).toBe("0.4");
    expect(slider.getAttribute("aria-valuetext")).toBe("0.40");
    expect(field.value).toBe("0.40");
    expect(field.getAttribute("inputmode")).toBe("decimal");
  });

  it("arrow keys step by 0.05, sync the box, and commit once per key", () => {
    const { slider, field, onCommit } = renderSlider();
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(slider.getAttribute("aria-valuenow")).toBe("0.45");
    expect(field.value).toBe("0.45");
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenLastCalledWith(0.45);
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(field.value).toBe("0.35");
    expect(onCommit).toHaveBeenLastCalledWith(0.35);
  });

  it("still sends a move back to the accepted weight while a commit is in flight", () => {
    const { slider, onCommit } = renderSlider();
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    // `value` is still 0.4: the server has not answered the 0.45 yet.
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(onCommit).toHaveBeenCalledTimes(2);
    expect(onCommit).toHaveBeenLastCalledWith(0.4);
  });

  it("Page keys step by 0.25 and Home/End jump to the ends", () => {
    const { slider, field, onCommit } = renderSlider();
    fireEvent.keyDown(slider, { key: "PageUp" });
    expect(field.value).toBe("0.65");
    expect(onCommit).toHaveBeenLastCalledWith(0.65);
    fireEvent.keyDown(slider, { key: "PageUp" });
    fireEvent.keyDown(slider, { key: "PageUp" });
    expect(field.value).toBe("1.00");
    fireEvent.keyDown(slider, { key: "Home" });
    expect(field.value).toBe("0.00");
    expect(onCommit).toHaveBeenLastCalledWith(0);
    fireEvent.keyDown(slider, { key: "End" });
    expect(slider.getAttribute("aria-valuenow")).toBe("1");
    fireEvent.keyDown(slider, { key: "PageDown" });
    expect(field.value).toBe("0.75");
  });

  it("typing moves the slider live but commits only on Enter", () => {
    const { slider, field, onCommit } = renderSlider();
    fireEvent.change(field, { target: { value: "0.7" } });
    expect(slider.getAttribute("aria-valuenow")).toBe("0.7");
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.keyDown(field, { key: "Enter" });
    expect(onCommit).toHaveBeenCalledWith(0.7);
    expect(field.value).toBe("0.70");
  });

  it("commits on blur, keeps an exact value, and does not re-send an unchanged one", () => {
    const { field, onCommit } = renderSlider();
    fireEvent.focus(field);
    fireEvent.blur(field);
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.focus(field);
    fireEvent.change(field, { target: { value: "0.333" } });
    fireEvent.blur(field);
    expect(onCommit).toHaveBeenCalledWith(0.333);
    expect(field.value).toBe("0.333");
  });

  it("commits a typed out-of-range number as typed; only the thumb is clamped", () => {
    // The server refuses a negative weight in its own sentence and accepts
    // one above 1 ("refuse, never repair"); the client never repairs it.
    const { slider, field, onCommit } = renderSlider();
    fireEvent.change(field, { target: { value: "1.5" } });
    expect(slider.getAttribute("aria-valuenow")).toBe("1");
    fireEvent.keyDown(field, { key: "Enter" });
    expect(onCommit).toHaveBeenLastCalledWith(1.5);
    expect(field.value).toBe("1.50");
    expect(slider.getAttribute("aria-valuenow")).toBe("1");
    fireEvent.change(field, { target: { value: "-0.2" } });
    expect(slider.getAttribute("aria-valuenow")).toBe("0");
    fireEvent.keyDown(field, { key: "Enter" });
    expect(onCommit).toHaveBeenLastCalledWith(-0.2);
    expect(field.value).toBe("-0.20");
    expect(slider.getAttribute("aria-valuenow")).toBe("0");
  });

  it("keeps slider-driven commits on the 0–1 range after an out-of-range entry", () => {
    const { slider, field, onCommit } = renderSlider();
    fireEvent.change(field, { target: { value: "1.5" } });
    fireEvent.keyDown(field, { key: "Enter" });
    fireEvent.keyDown(slider, { key: "PageUp" });
    expect(onCommit).toHaveBeenLastCalledWith(1);
  });

  it("rejects a number that is not plain, as a field alert, without committing", () => {
    const { field, onCommit } = renderSlider();
    fireEvent.change(field, { target: { value: "1,5" } });
    fireEvent.keyDown(field, { key: "Enter" });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toBe('"1,5" is not a plain number. Use digits and one decimal point, like 0.5.');
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toBe(alert.id);
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.change(field, { target: { value: "" } });
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.blur(field);
    expect(screen.getByRole("alert").textContent).toBe("Type a number for this weight.");
  });

  it("shows the server's refusal as a status, not an alert, and reverts to the accepted value", () => {
    const onCommit = vi.fn();
    const { rerender } = render(
      <WeightSlider id="interest" label={LABEL} value={0.4} onCommit={onCommit} />,
    );
    const field = screen.getByRole("textbox", { name: LABEL }) as HTMLInputElement;
    fireEvent.change(field, { target: { value: "0.9" } });
    fireEvent.keyDown(field, { key: "Enter" });
    rerender(
      <WeightSlider
        id="interest"
        label={LABEL}
        value={0.4}
        onCommit={onCommit}
        refusal={{ message: "Those weights were not accepted." }}
      />,
    );
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("Those weights were not accepted.");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(field.getAttribute("aria-describedby")).toBe(status.id);
    expect(field.value).toBe("0.40");
  });

  it("reverts on every refusal, even when the sentence repeats", () => {
    const onCommit = vi.fn();
    const sentence = "A weight cannot be negative.";
    const props = { id: "interest", label: LABEL, value: 0.4, onCommit };
    const { rerender } = render(<WeightSlider {...props} />);
    const field = screen.getByRole("textbox", { name: LABEL }) as HTMLInputElement;
    const slider = screen.getByRole("slider", { name: LABEL });

    fireEvent.change(field, { target: { value: "-0.5" } });
    fireEvent.keyDown(field, { key: "Enter" });
    rerender(<WeightSlider {...props} refusal={{ message: sentence }} />);
    expect(field.value).toBe("0.40");

    fireEvent.change(field, { target: { value: "-0.3" } });
    fireEvent.keyDown(field, { key: "Enter" });
    expect(onCommit).toHaveBeenLastCalledWith(-0.3);
    // A fresh refusal object per failed attempt, same words.
    rerender(<WeightSlider {...props} refusal={{ message: sentence }} />);
    expect(field.value).toBe("0.40");
    expect(slider.getAttribute("aria-valuenow")).toBe("0.4");
  });

  it("adopts a newly confirmed value from the server", () => {
    const onCommit = vi.fn();
    const { rerender } = render(
      <WeightSlider id="interest" label={LABEL} value={0.4} onCommit={onCommit} />,
    );
    rerender(<WeightSlider id="interest" label={LABEL} value={0.25} onCommit={onCommit} />);
    expect((screen.getByRole("textbox", { name: LABEL }) as HTMLInputElement).value).toBe("0.25");
    expect(screen.getByRole("slider", { name: LABEL }).getAttribute("aria-valuenow")).toBe("0.25");
  });

  it("gives the thumb a 44px hit area", () => {
    const { slider } = renderSlider();
    expect(slider.className).toContain("size-11");
  });

  it("stays live while rebuilding and shows a small spinner", () => {
    const { slider, onCommit, container } = renderSlider({ pending: true });
    expect(container.querySelector('[data-slot="ce-weight-pending"]')).not.toBeNull();
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(onCommit).toHaveBeenCalledWith(0.45);
  });

  it("glides to a clicked point, unless reduced motion is asked for", () => {
    const { container } = renderSlider();
    expect(container.querySelector(".ce-slider-settle")).not.toBeNull();
    cleanup();
    stubReducedMotion(true);
    const reduced = renderSlider();
    expect(reduced.container.querySelector(".ce-slider-settle")).toBeNull();
  });

  describe("pointer", () => {
    // jsdom has no pointer capture; Radix calls it on the thumb.
    const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
    const saved = {
      set: proto.setPointerCapture,
      release: proto.releasePointerCapture,
      has: proto.hasPointerCapture,
    };
    beforeEach(() => {
      proto.setPointerCapture = vi.fn();
      proto.releasePointerCapture = vi.fn();
      proto.hasPointerCapture = vi.fn(() => false);
    });
    afterEach(() => {
      proto.setPointerCapture = saved.set;
      proto.releasePointerCapture = saved.release;
      proto.hasPointerCapture = saved.has;
    });

    function root(container: HTMLElement): HTMLElement {
      return container.querySelector("[data-dragging]") as HTMLElement;
    }

    it("stops dragging on release even when the value did not change", () => {
      const { slider, container, onCommit } = renderSlider();
      fireEvent.pointerDown(slider, { pointerId: 1 });
      expect(root(container).dataset.dragging).toBe("true");
      fireEvent.pointerUp(slider, { pointerId: 1 });
      expect(root(container).dataset.dragging).toBe("false");
      expect(onCommit).not.toHaveBeenCalled();
    });

    it("stops dragging when the pointer is cancelled or capture is lost", () => {
      const { slider, container } = renderSlider();
      fireEvent.pointerDown(slider, { pointerId: 1 });
      fireEvent.pointerCancel(slider, { pointerId: 1 });
      expect(root(container).dataset.dragging).toBe("false");
      fireEvent.pointerDown(slider, { pointerId: 2 });
      fireEvent.lostPointerCapture(slider, { pointerId: 2 });
      expect(root(container).dataset.dragging).toBe("false");
    });
  });

  it("when disabled, neither control moves", () => {
    const { slider, field, onCommit } = renderSlider({ disabled: true });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(onCommit).not.toHaveBeenCalled();
    expect(field.disabled).toBe(true);
  });
});
