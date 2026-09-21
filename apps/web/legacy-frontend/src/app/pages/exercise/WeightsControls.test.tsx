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

import { ExerciseRefusal } from "../../../lib/exerciseApi";
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
    // G4. This used to focus and blur the box without ever typing in it, so
    // `draft` still held the server's own text and the assertion passed no
    // matter what the "did it change" comparison did — deleting that check
    // entirely would not have failed this test. Retyping the same number the
    // box already shows is what actually exercises the comparison.
    const onChange = vi.fn();
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

    const box = screen.getByLabelText("same major");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: String(WEIGHTS.same_major) } });
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

  describe("rejecting a number that is not strictly a number", () => {
    // G5. `Number.parseFloat` reads a *prefix* of its argument: "0.5abc"
    // parses as 0.5 and "1,5" (a comma-locale team's one-and-a-half, or five
    // tenths) parses as 1 — both would fail on the merged code by sending a
    // value the team never typed, silently, with no message at all.
    it.each([
      ["1,5", "comma-locale"],
      ["0.5abc", "trailing junk"],
      ["", "empty"],
    ])("rejects %s (%s) rather than silently coercing it", (typed) => {
      const onChange = vi.fn();
      render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

      const box = screen.getByLabelText("same major");
      fireEvent.focus(box);
      fireEvent.change(box, { target: { value: typed } });
      fireEvent.blur(box);

      expect(onChange).not.toHaveBeenCalled();
      expect(document.querySelector('[data-slot="exercise-weight-error"]')).not.toBeNull();
    });

    it("clears the message once the team starts fixing the box", () => {
      const onChange = vi.fn();
      render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

      const box = screen.getByLabelText("same major");
      fireEvent.focus(box);
      fireEvent.change(box, { target: { value: "1,5" } });
      fireEvent.blur(box);
      expect(document.querySelector('[data-slot="exercise-weight-error"]')).not.toBeNull();

      fireEvent.focus(box);
      fireEvent.change(box, { target: { value: "0.5" } });

      expect(document.querySelector('[data-slot="exercise-weight-error"]')).toBeNull();
    });

    it("still accepts an ordinary decimal", () => {
      const onChange = vi.fn();
      render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={onChange} />);

      const box = screen.getByLabelText("same major");
      fireEvent.focus(box);
      fireEvent.change(box, { target: { value: "0.6" } });
      fireEvent.blur(box);

      expect(onChange).toHaveBeenCalledWith({ ...WEIGHTS, same_major: 0.6 });
      expect(document.querySelector('[data-slot="exercise-weight-error"]')).toBeNull();
    });
  });

  it("does not let a refused commit become the base of the next one", () => {
    // H1 (round 3). `weights` does not change on a refusal — the screen's
    // hook deliberately keeps the same, previous `data` object — so nothing
    // told `pendingBase` that box A's commit was rejected. The next commit,
    // for box B, kept merging onto A's never-confirmed value instead of onto
    // `weights` (the confirmed truth), so B's request silently carried A's
    // rejected number along with it.
    //
    // Fails on 83cf0a77: the second `onChange` call includes
    // `same_major: 0.9` even though A was refused.
    const onChange = vi.fn();
    const { rerender } = render(
      <WeightsControls
        factorLabels={LABELS}
        weights={WEIGHTS}
        onChange={onChange}
        refusal={null}
      />,
    );

    const boxA = screen.getByLabelText("same major");
    fireEvent.focus(boxA);
    fireEvent.change(boxA, { target: { value: "0.9" } });
    fireEvent.blur(boxA);
    expect(onChange).toHaveBeenCalledTimes(1);

    // The screen reports A was refused. `weights` is unchanged — it is still
    // the last confirmed weighting — but a fresh refusal object arrives.
    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={WEIGHTS}
        onChange={onChange}
        refusal={new ExerciseRefusal(409, "exercise_invalid_weights", "Weights must sum to 1.")}
      />,
    );

    const boxB = screen.getByLabelText("career goal fits this event");
    fireEvent.focus(boxB);
    fireEvent.change(boxB, { target: { value: "0.4" } });
    fireEvent.blur(boxB);

    expect(onChange).toHaveBeenCalledTimes(2);
    // B's request is built on the confirmed WEIGHTS, not on A's rejected 0.9.
    expect(onChange).toHaveBeenNthCalledWith(2, { ...WEIGHTS, career_goal_fit: 0.4 });
  });

  it("shows the confirmed number, not a silently fabricated one, once a commit is refused", () => {
    // A refused commit is answered with the screen's own refusal sentence
    // (rendered above this component), so this box falling back to the last
    // confirmed number — not staying on the rejected 0.9, and not some third
    // value nobody asked for — is an honest state, not a silent one.
    const { rerender } = render(
      <WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} refusal={null} />,
    );

    const box = screen.getByLabelText("same major") as HTMLInputElement;
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.9" } });
    fireEvent.blur(box);

    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={WEIGHTS}
        onChange={vi.fn()}
        refusal={new ExerciseRefusal(409, "exercise_invalid_weights", "Weights must sum to 1.")}
      />,
    );

    expect(box.value).toBe(String(WEIGHTS.same_major));
  });

  it("keeps a still-focused box's own text when the refusal for it arrives", () => {
    // If the team is already back in the box when the refusal lands, wiping
    // what they are mid-typing would be the same mid-keystroke loss F1 fixed
    // — just triggered by a refusal instead of a refetch.
    const { rerender } = render(
      <WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} refusal={null} />,
    );

    const box = screen.getByLabelText("same major") as HTMLInputElement;
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.9" } });
    fireEvent.blur(box);
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "0.6" } });

    rerender(
      <WeightsControls
        factorLabels={LABELS}
        weights={WEIGHTS}
        onChange={vi.fn()}
        refusal={new ExerciseRefusal(409, "exercise_invalid_weights", "Weights must sum to 1.")}
      />,
    );

    expect(box.value).toBe("0.6");
  });

  it("never renders a rulebook key as a label", () => {
    render(<WeightsControls factorLabels={LABELS} weights={WEIGHTS} onChange={vi.fn()} />);
    const panel = document.querySelector('[data-slot="exercise-weights"]');
    expect(panel?.textContent).not.toContain("stated_interest_overlap");
    expect(panel?.textContent).not.toContain("past_event_topic_overlap");
  });
});
