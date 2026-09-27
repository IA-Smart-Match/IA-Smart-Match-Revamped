/**
 * Weight slider (DESIGN.md §6.6, owner ruling 2): a Radix slider 0–1, step
 * 0.05, paired with an 88px number box that holds the exact value.
 *
 * - Both controls are named by the server's factor label, verbatim.
 * - Dragging or typing moves the other control live; the weight is committed
 *   (`onCommit`) only on pointer-up, a key step, Enter, or leaving the box —
 *   never per drag tick.
 * - Keyboard: arrows ±0.05, Page Up/Down ±0.25, Home/End (§8.4).
 * - The box keeps the strict-decimal rule; anything else is a field alert.
 *   A typed number outside 0–1 is committed as typed — the server refuses a
 *   negative weight in its own sentence and accepts one above 1 ("refuse,
 *   never repair") — and only the thumb's position is held on 0–1. Weights
 *   the slider itself produces (drag, keys) always stay on 0–1.
 * - `refusal` is the server's refusal for the latest commit — a fresh object
 *   per failed attempt, like `useExerciseResource`'s `ExerciseRefusal` — so
 *   the controls revert to `value` (the last accepted weight) on every
 *   refusal, even when the sentence repeats. It is shown as `role="status"`
 *   (§8.6); only the box's own field error is `role="alert"`.
 * - The thumb is drawn at 28px inside a 44px hit area (§8.9).
 * - `ce-slider-settle` glides the thumb to a clicked point (180ms); reduced
 *   motion jumps.
 * - Never disabled during a refetch: `pending` only shows a spinner.
 */
import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { LoaderCircle } from "lucide-react";

import { cn } from "../../../components/ui/utils";
import { usePrefersReducedMotion } from "./motion";
import {
  WEIGHT_MAX,
  WEIGHT_MIN,
  WEIGHT_PAGE_STEP,
  WEIGHT_STEP,
  clampWeight,
  formatWeight,
  strictDecimal,
  tidyWeight,
  weightFieldMessage,
} from "./weightValue";

/**
 * A server refusal. Anything with the sentence works, `ExerciseRefusal`
 * included. Identity is the trigger: pass a new object per refused attempt.
 */
export interface WeightRefusal {
  readonly message: string;
}

export interface WeightSliderProps {
  /** Unique within the page; prefixes the element ids. */
  readonly id: string;
  /** The server's `factor_labels` phrase, verbatim. */
  readonly label: string;
  /** The last accepted weight. */
  readonly value: number;
  /**
   * Called once per commit with the new weight: a typed number as typed
   * (never clamped), or a slider value on 0–1.
   */
  readonly onCommit: (value: number) => void;
  /** The latest commit's refusal (new object per attempt); its sentence is shown verbatim. */
  readonly refusal?: WeightRefusal | null;
  /** A committed change is rebuilding the list: show a spinner, stay live. */
  readonly pending?: boolean;
  readonly disabled?: boolean;
  /** Form field name for the number box. */
  readonly name?: string;
  readonly className?: string;
}

export function WeightSlider({
  id,
  label,
  value,
  onCommit,
  refusal = null,
  pending = false,
  disabled = false,
  name,
  className,
}: WeightSliderProps): React.JSX.Element {
  const reduced = usePrefersReducedMotion();
  const labelId = `${id}-label`;
  const fieldId = `${id}-value`;
  const errorId = `${id}-error`;

  const [draft, setDraft] = React.useState(() => formatWeight(value));
  const [live, setLive] = React.useState(() => clampWeight(value));
  const [dragging, setDragging] = React.useState(false);
  const [fieldError, setFieldError] = React.useState<string | null>(null);
  const fieldFocused = React.useRef(false);
  /**
   * The last weight this control sent, or the last accepted one — whichever
   * is newer. A commit equal to it is not re-sent. Compared against this, not
   * `value`: while a commit is in flight `value` still holds the old weight,
   * and moving back to it must still be sent.
   */
  const lastSent = React.useRef(value);

  const showValue = React.useCallback((next: number): void => {
    setDraft(formatWeight(next));
    setLive(clampWeight(next));
  }, []);

  // A newly accepted weight, or a refusal, resets both controls to `value` —
  // except the box while someone is still typing in it.
  React.useEffect(() => {
    lastSent.current = value;
    if (!fieldFocused.current) {
      showValue(value);
    }
  }, [value, showValue]);

  React.useEffect(() => {
    if (refusal !== null) {
      lastSent.current = value;
      showValue(value);
    }
    // `value` is read for its current value, not watched: the trigger is a new
    // refusal object, which changes identity on every refused attempt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refusal]);

  /** Send a weight. Callers clamp slider-driven values; typed ones pass as typed. */
  function commit(next: number): void {
    const settled = tidyWeight(next);
    showValue(settled);
    setFieldError(null);
    if (settled !== lastSent.current) {
      lastSent.current = settled;
      onCommit(settled);
    }
  }

  function commitField(): void {
    const parsed = strictDecimal(draft);
    if (parsed === null) {
      setFieldError(weightFieldMessage(draft));
      return;
    }
    commit(parsed);
  }

  const refusalMessage = refusal?.message ?? null;
  const shownError = fieldError ?? refusalMessage;

  return (
    <div
      data-slot="ce-weight-slider"
      className={cn(
        "grid grid-cols-[minmax(0,1fr)_88px] items-center gap-x-ce-4 gap-y-ce-2",
        disabled && "opacity-45",
        className,
      )}
    >
      <div className="col-start-1 row-start-1 flex items-center gap-ce-2 md:col-span-2">
        <label id={labelId} htmlFor={fieldId} className="ce-type-label text-ce-ink">
          {label}
        </label>
        {pending ? (
          <LoaderCircle
            aria-hidden="true"
            data-slot="ce-weight-pending"
            className="ce-spin size-4 shrink-0 animate-spin text-ce-primary motion-reduce:animate-none"
          />
        ) : null}
      </div>

      <SliderPrimitive.Root
        min={WEIGHT_MIN}
        max={WEIGHT_MAX}
        step={WEIGHT_STEP}
        value={[live]}
        disabled={disabled}
        data-dragging={dragging ? "true" : "false"}
        data-reduced-motion={reduced ? "true" : "false"}
        onPointerDown={() => setDragging(true)}
        // Radix fires `onValueCommit` only when the value changed, so a press
        // and release without a move would leave `dragging` stuck on. The
        // pointer ending is what ends a drag.
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
        onLostPointerCapture={() => setDragging(false)}
        onValueChange={([next]) => {
          showValue(next);
          setFieldError(null);
        }}
        onValueCommit={([next]) => {
          commit(clampWeight(next));
        }}
        onKeyDown={(event) => {
          // Radix pages by 10 steps (0.5); §8.4 asks for ±0.25.
          if (disabled || (event.key !== "PageUp" && event.key !== "PageDown")) {
            return;
          }
          event.preventDefault();
          commit(clampWeight(live + (event.key === "PageUp" ? WEIGHT_PAGE_STEP : -WEIGHT_PAGE_STEP)));
        }}
        className={cn(
          "group/slider relative col-span-2 row-start-2 flex h-ce-target touch-none items-center select-none md:col-span-1 md:col-start-1",
          !reduced && "ce-slider-settle",
          disabled ? "cursor-not-allowed" : "cursor-pointer",
        )}
      >
        <SliderPrimitive.Track className="relative h-[6px] grow rounded-ce-pill bg-ce-surface-sunk outline-2 outline-ce-line-strong">
          <SliderPrimitive.Range
            data-slot="ce-slider-range"
            className="absolute h-full rounded-ce-pill bg-ce-primary"
          />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb
          data-slot="ce-slider-thumb"
          aria-labelledby={labelId}
          aria-valuetext={formatWeight(live)}
          className="group/thumb relative flex size-11 items-center justify-center rounded-full"
        >
          <span
            aria-hidden="true"
            className="block size-7 rounded-full border-2 border-ce-primary bg-white shadow-ce-1 transition-[width,height,box-shadow] duration-150 group-hover/thumb:size-8 group-hover/thumb:shadow-ce-2 group-data-[dragging=true]/slider:size-8"
          />
          {dragging ? (
            <span
              aria-hidden="true"
              className="ce-type-meta ce-tabular absolute bottom-full mb-ce-1 rounded-ce-control bg-ce-primary px-ce-2 text-ce-on-primary"
            >
              {formatWeight(live)}
            </span>
          ) : null}
        </SliderPrimitive.Thumb>
      </SliderPrimitive.Root>

      <input
        id={fieldId}
        name={name}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={draft}
        disabled={disabled}
        aria-invalid={shownError !== null}
        aria-describedby={shownError === null ? undefined : errorId}
        onFocus={() => {
          fieldFocused.current = true;
        }}
        onChange={(event) => {
          const typed = event.target.value;
          setDraft(typed);
          setFieldError(null);
          const parsed = strictDecimal(typed);
          if (parsed !== null) {
            setLive(clampWeight(parsed));
          }
        }}
        onBlur={() => {
          fieldFocused.current = false;
          commitField();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commitField();
          }
        }}
        className={cn(
          "ce-type-value col-start-2 row-start-1 h-ce-target w-[88px] rounded-ce-control border-2 bg-ce-surface px-ce-3 text-right text-ce-ink md:row-start-2",
          shownError === null ? "border-ce-line-strong" : "border-ce-danger",
        )}
      />

      {shownError === null ? null : (
        <p
          id={errorId}
          // §8.6: the box's own field error is an alert; a server refusal is a status.
          role={fieldError !== null ? "alert" : "status"}
          data-slot="exercise-weight-error"
          className="ce-type-meta col-span-2 text-ce-danger"
        >
          {shownError}
        </p>
      )}
    </div>
  );
}
