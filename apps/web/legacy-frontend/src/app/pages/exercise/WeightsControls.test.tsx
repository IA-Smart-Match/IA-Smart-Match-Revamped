/**
 * A team has to be able to type a number.
 *
 * The inputs were driven straight from the server's echo, with every keystroke
 * sent upstream as a new weighting — which refetched the list, re-rendered the
 * panel, and took the box away mid-decimal. `0.75` could not be entered at
 * all. These tests pin the two halves of the fix: the text is local while a
 * team is typing, and the server hears about it once.
 *
 * How each fails on the merged code is stated per test. They are unit tests on
 * the component, so they hold whatever the matching screen later does with the
 * value; `ExerciseMatching.test.tsx` covers the screen's half.
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

describe("<WeightsControls />", () => {
  it("lets a decimal be typed one character at a time", () => {
    // Fails on the merged code: `onChange` fired on the `0`, and in the screen
    // that re-rendered the panel from the server's echo, so the box never held
    // "0." and the "75" had nowhere to land.
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

    const box = screen.getByLabelText("same major") as HTMLInputElement;
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0" } });
    fireEvent.change(box, { target: { value: "0." } });
    fireEvent.change(box, { target: { value: "0.7" } });
    fireEvent.change(box, { target: { value: "0.75" } });

    expect(box.value).toBe("0.75");
    // Nothing has been sent yet: the team is still in the box.
    expect(onChange).not.toHaveBeenCalled();
  });

  it("sends the weighting once, when the team leaves the box", () => {
    // Fails on the merged code: four keystrokes meant four `onChange` calls
    // and four list requests, so `toHaveBeenCalledTimes(1)` saw 4.
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

    const box = screen.getByLabelText("same major");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.75" } });
    fireEvent.blur(box);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: 0.75 });
  });

  it("treats Enter as finishing with the box", () => {
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

    const box = screen.getByLabelText("career goal fits this event");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "1.5" } });
    fireEvent.keyDown(box, { key: "Enter" });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, career_goal_fit: 1.5 });
  });

  it("does not spend a request when the number did not change", () => {
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

    const box = screen.getByLabelText("same major");
    fireEvent.focus(box);
    fireEvent.blur(box);

    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps a half-typed number when the server's echo arrives", () => {
    // The committed weighting comes back on the response. Adopting it into the
    // box the team is still typing in would overwrite them mid-number.
    const { rerender } = render(
      <WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />,
    );

    const box = screen.getByLabelText("same major") as HTMLInputElement;
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0." } });

    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={{ ...WEIGHTS, career_goal_fit: 0.9 }}
        onChange={vi.fn()}
      />,
    );

    expect(box.value).toBe("0.");
    // A box nobody is in does take the server's number.
    expect((screen.getByLabelText("career goal fits this event") as HTMLInputElement).value).toBe(
      "0.9",
    );
  });

  it("carries a first commit into a second one made before the response lands", () => {
    // G1. Fails on the merged code: the second `commit` built its payload
    // from the `weights` prop, which had not advanced yet because no
    // response had come back for the first edit — so the second `onChange`
    // silently dropped the first box's change instead of carrying it
    // forward. The prop only updates on rerender, which stands in for "the
    // round trip has not resolved yet".
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

    const first = screen.getByLabelText("same major");
    fireEvent.focus(first);
    fireEvent.change(first, { target: { value: "0.6" } });
    fireEvent.blur(first);

    // The prop the server would eventually confirm has not arrived — this
    // component is still rendering with the original `weights`.
    const second = screen.getByLabelText("career goal fits this event");
    fireEvent.focus(second);
    fireEvent.change(second, { target: { value: "0.4" } });
    fireEvent.blur(second);

    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenNthCalledWith(1, { ...WEIGHTS, same_major: 0.6 });
    // The second call must still carry the first edit, not just its own.
    expect(onChange).toHaveBeenNthCalledWith(2, {
      ...WEIGHTS,
      same_major: 0.6,
      career_goal_fit: 0.4,
    });
  });

  it("never renders a rulebook key as a label", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    const panel = document.querySelector('[data-slot="exercise-weights"]');
    expect(panel?.textContent).not.toContain("stated_interest_overlap");
    expect(panel?.textContent).not.toContain("past_event_topic_overlap");
  });
});
