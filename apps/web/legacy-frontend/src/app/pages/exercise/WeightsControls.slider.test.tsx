/**
 * The weight slider and its number box (owner ruling 2026-09-26, DESIGN.md
 * §6.6): a slider 0–1 in steps of 0.05 beside an 88px box. The list is
 * rebuilt when a team lets go of the slider, presses Enter, or leaves the box
 * — never once per drag tick, which would fire a request for every pixel.
 *
 * `fireEvent.input` is a drag tick (the browser's `input` event); a
 * `fireEvent.change` on the range is the release (the browser's own `change`
 * event, fired once when the pointer lets go and once per key step).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WeightsControls } from "./WeightsControls";

const LABELS = {
  same_major: "same major",
  stated_interest_overlap: "said they are interested in this topic",
  career_goal_fit: "career goal fits this event",
  past_event_topic_overlap: "went to similar events before",
};

const WEIGHTS = {
  same_major: 0.25,
  stated_interest_overlap: 0.25,
  career_goal_fit: 0.25,
  past_event_topic_overlap: 0.25,
};

afterEach(cleanup);

function setup() {
  const onChange = vi.fn();
  render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);
  const box = screen.getByLabelText("same major") as HTMLInputElement;
  const slider = screen.getByRole("slider", { name: "Slider for same major" }) as HTMLInputElement;
  return { onChange, box, slider };
}

describe("<WeightsControls /> slider and number box", () => {
  it("draws one slider per weight, 0 to 1 in steps of 0.05, named apart from its box", () => {
    const { box, slider } = setup();
    expect(screen.getAllByRole("slider")).toHaveLength(4);
    expect(slider.min).toBe("0");
    expect(slider.max).toBe("1");
    expect(slider.step).toBe("0.05");
    // The factor's words label the box; the slider has its own name, so a
    // query for the words finds exactly one control.
    expect(box.type).toBe("text");
    expect(slider.getAttribute("aria-valuetext")).toBe("0.25");
  });

  it("moves the number box while dragging, and sends nothing per tick", () => {
    const { onChange, box, slider } = setup();
    fireEvent.pointerDown(slider);
    fireEvent.input(slider, { target: { value: "0.3" } });
    fireEvent.input(slider, { target: { value: "0.35" } });
    fireEvent.input(slider, { target: { value: "0.4" } });
    expect(box.value).toBe("0.4");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("commits once, on release, with the released value", () => {
    const { onChange, slider } = setup();
    fireEvent.pointerDown(slider);
    fireEvent.input(slider, { target: { value: "0.35" } });
    fireEvent.input(slider, { target: { value: "0.4" } });
    fireEvent.change(slider, { target: { value: "0.4" } });
    fireEvent.pointerUp(slider);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: 0.4 });
  });

  it("moves a quarter on Page Up and commits it", () => {
    const { onChange, box, slider } = setup();
    fireEvent.keyDown(slider, { key: "PageUp" });
    expect(box.value).toBe("0.5");
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: 0.5 });
  });

  it("commits a typed value on Enter and puts the slider there", () => {
    const { onChange, box, slider } = setup();
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.6" } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: 0.6 });
    expect(slider.value).toBe("0.6");
  });

  it("commits a typed value on blur, and not again when nothing changed", () => {
    const { onChange, box } = setup();
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.7" } });
    fireEvent.blur(box);
    expect(onChange).toHaveBeenCalledTimes(1);
    fireEvent.focus(box);
    fireEvent.blur(box);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("does not send a release that lands where the weight already is", () => {
    const { onChange, slider } = setup();
    fireEvent.change(slider, { target: { value: "0.25" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("says when the list is rebuilt, in the owner-approved words", () => {
    setup();
    expect(
      screen.getByText("The list is rebuilt when you let go of a slider or press Enter."),
    ).toBeDefined();
  });
});
