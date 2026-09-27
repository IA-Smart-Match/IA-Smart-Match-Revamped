/**
 * `ce-seat-fill` — the focal moment (DESIGN.md §5.1, §6.15).
 *
 * Three parts, so the results page owns layout and words and this module
 * owns the choreography:
 *
 * - `seatFillPlan` — which seat is which kind and when it fills.
 * - `useSeatFill` — the step clock (0–240 chart in, 240–600 taken, 700–1300
 *   the team's, 1400–1800 open seats and figures) and when to announce.
 * - `Seat` — one square, styled by `.ce-seat` in `exercise-motion.css`.
 *
 * Counts come from the server (`team.attended_count` for "added"); the plan
 * never subtracts to find one.
 */
import * as React from "react";

export type SeatKind = "taken" | "added" | "open";

export interface PlannedSeat {
  readonly index: number;
  readonly kind: SeatKind;
  /** When this seat's fill starts, from the moment the chart mounts. */
  readonly delayMs: number;
}

export interface SeatFillPlan {
  readonly seats: readonly PlannedSeat[];
}

/** Step start times from §5.1, index = step number; step 4 ends at `SEAT_FILL_DONE_MS`. */
export const SEAT_FILL_STEP_MS = [0, 0, 240, 700, 1400] as const;
export const SEAT_FILL_DONE_MS = 1800;

const TAKEN_WINDOW_MS = 600 - 240;
const ADDED_WINDOW_MS = 1300 - 700;
const TAKEN_STAGGER_MS = 12;
const ADDED_STAGGER_MS = 60;

function wholeNonNegative(n: number): number {
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

/** The stagger, shrunk when needed so the step's last seat starts inside its window. */
function stagger(preferred: number, count: number, window: number): number {
  return count <= 1 ? preferred : Math.min(preferred, window / (count - 1));
}

/**
 * Seats in reading order (front row first, left to right): the already-coming
 * seats, then the team's, then the open ones. Filled counts are capped at the
 * room size, taken first.
 */
export function seatFillPlan({
  total,
  taken,
  added,
}: {
  readonly total: number;
  readonly taken: number;
  readonly added: number;
}): SeatFillPlan {
  const size = wholeNonNegative(total);
  const takenCount = Math.min(wholeNonNegative(taken), size);
  const addedCount = Math.min(wholeNonNegative(added), size - takenCount);
  const takenStep = stagger(TAKEN_STAGGER_MS, takenCount, TAKEN_WINDOW_MS);
  const addedStep = stagger(ADDED_STAGGER_MS, addedCount, ADDED_WINDOW_MS);

  const seats: PlannedSeat[] = [];
  for (let index = 0; index < size; index += 1) {
    if (index < takenCount) {
      seats.push({ index, kind: "taken", delayMs: Math.round(SEAT_FILL_STEP_MS[2] + index * takenStep) });
    } else if (index < takenCount + addedCount) {
      const i = index - takenCount;
      seats.push({ index, kind: "added", delayMs: Math.round(SEAT_FILL_STEP_MS[3] + i * addedStep) });
    } else {
      seats.push({ index, kind: "open", delayMs: SEAT_FILL_STEP_MS[4] });
    }
  }
  return { seats };
}

export interface SeatFillState {
  /** 1 chart in · 2 taken + line 1 · 3 team's + line 2 · 4 open + line 3 + figures. */
  readonly step: 1 | 2 | 3 | 4;
  /** True once the fill is over: render the `aria-live` sentences now, once. */
  readonly announce: boolean;
  /** Whether seats should animate (false = render the final state). */
  readonly animating: boolean;
  /** Jump to the final state. */
  readonly skip: () => void;
}

/**
 * The §5.1 clock. `play` is true only on the first render after a successful
 * run; later visits pass false and get the final state. Reduced motion also
 * gets the final state at once and announces immediately.
 */
export function useSeatFill({
  play,
  reduced,
}: {
  readonly play: boolean;
  readonly reduced: boolean;
}): SeatFillState {
  const instant = !play || reduced;
  const [step, setStep] = React.useState<1 | 2 | 3 | 4>(instant ? 4 : 1);
  const [done, setDone] = React.useState(instant);
  const timers = React.useRef<Array<ReturnType<typeof setTimeout>>>([]);

  const clearAll = React.useCallback((): void => {
    for (const id of timers.current) {
      clearTimeout(id);
    }
    timers.current = [];
  }, []);

  const skip = React.useCallback((): void => {
    clearAll();
    setStep(4);
    setDone(true);
  }, [clearAll]);

  React.useEffect(() => {
    if (instant) {
      skip();
      return undefined;
    }
    // `play` can flip false → true on a mounted chart (a run lands while the
    // final state is showing): start over from step 1.
    setStep(1);
    setDone(false);
    timers.current = [
      setTimeout(() => setStep(2), SEAT_FILL_STEP_MS[2]),
      setTimeout(() => setStep(3), SEAT_FILL_STEP_MS[3]),
      setTimeout(() => setStep(4), SEAT_FILL_STEP_MS[4]),
      setTimeout(() => setDone(true), SEAT_FILL_DONE_MS),
    ];
    return clearAll;
  }, [instant, skip, clearAll]);

  return { step, announce: done, animating: !instant && !done, skip };
}

export interface SeatProps {
  readonly kind: SeatKind;
  /** From `seatFillPlan`; ignored when `animate` is false. */
  readonly delayMs?: number;
  readonly animate: boolean;
  readonly className?: string;
}

/**
 * One seat square. Decorative: the seating chart is `aria-hidden` and the
 * sentences carry the numbers (§6.15). Kind is shown by fill, mark and
 * outline (§3.3), never by colour alone.
 */
export function Seat({ kind, delayMs = 0, animate, className }: SeatProps): React.JSX.Element {
  return (
    <span
      aria-hidden="true"
      data-slot="ce-seat"
      data-kind={kind}
      data-animate={animate ? "true" : undefined}
      className={`ce-seat ${className ?? ""}`}
      style={animate ? ({ "--ce-delay": `${delayMs}ms` } as React.CSSProperties) : undefined}
    />
  );
}
