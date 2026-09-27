/**
 * The room: a seating chart that fills in, and the same numbers in words.
 *
 * DESIGN.md §6.15 and §5.1 (`ce-seat-fill`, the flow's one authored moment).
 * The chart is a grid of `event_seats` squares, ten to a row, front row
 * first: the seats that were already coming, then the ones the team's
 * invitations added, then the open ones. It is `aria-hidden`: the headline
 * sentences and the ruled figures band are the accessible content, and the
 * legend repeats the counts beside each swatch, so no seat relies on colour.
 *
 * **The fill plays once, only on the first render after a run.** A later
 * visit, a reload or reduced motion shows the final state at once, and the
 * three sentences are announced once through a polite live region after the
 * last step (or straight away when there is no animation).
 *
 * Every number is the server's. The client never subtracts: "already coming"
 * is `existing_signups`, "added" is the team panel's `attended_count` (the
 * figure `seats_empty` is computed from on the server), and "still open" is
 * `seats_empty`.
 */
import * as React from "react";
import { Check } from "lucide-react";

import { FiguresBand, usePrefersReducedMotion } from "./exerciseUi";

/** Seats per row (§6.15). */
const ROW = 10;

/** §5.1 step boundaries, in ms. */
const STEP_TAKEN = 240;
const STEP_ADDED = 700;
/** Step 4 starts here and its outline brighten runs to 1800ms. */
const STEP_OPEN = 1400;

/** 0 before anything, 1 outlines in, 2 taken seats, 3 added seats, 4 settled. */
type Phase = 0 | 1 | 2 | 3 | 4;

export interface SeatCountsView {
  readonly seats: number;
  readonly alreadyComing: number;
  readonly added: number;
  readonly open: number;
}

export function SeatReveal({
  counts,
  sentences,
  reveal,
  footnote,
}: {
  readonly counts: SeatCountsView;
  /** The three seat sentences, already worded (see `seatsSentence`). */
  readonly sentences: string;
  /** Play `ce-seat-fill`. Only the first render after a run passes `true`. */
  readonly reveal: boolean;
  /** A quiet line under the band, e.g. round one's empty seats. */
  readonly footnote?: React.ReactNode;
}): React.JSX.Element {
  const reduced = usePrefersReducedMotion();
  const animate = React.useRef(reveal && !reduced);
  const [phase, setPhase] = React.useState<Phase>(animate.current ? 0 : 4);

  React.useEffect(() => {
    if (!animate.current) {
      setPhase(4);
      return undefined;
    }
    animate.current = false;
    const timers = [
      window.setTimeout(() => setPhase(1), 0),
      window.setTimeout(() => setPhase(2), STEP_TAKEN),
      window.setTimeout(() => setPhase(3), STEP_ADDED),
      window.setTimeout(() => setPhase(4), STEP_OPEN),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, []);

  const lines = splitSentences(sentences);

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-10">
      <SeatingChart counts={counts} phase={phase} />
      <div className="flex flex-col gap-6">
        <p
          className="ce-headline text-ce-ink"
          data-slot="exercise-seats-sentence"
          data-phase={phase}
        >
          {lines.map((line, index) => (
            <span
              key={line}
              className="block transition-opacity duration-300 motion-reduce:duration-150"
              style={{ opacity: phase >= index + 2 ? 1 : 0 }}
            >
              <Numerals text={line} />
              {index < lines.length - 1 ? " " : ""}
            </span>
          ))}
        </p>
        {/* Announced once, after the last step (§5.1). */}
        <p aria-live="polite" className="sr-only" data-slot="exercise-seats-announce">
          {phase === 4 ? sentences : ""}
        </p>
        {footnote === undefined ? null : <p className="ce-body text-ce-muted">{footnote}</p>}
        <FiguresBand
          slot="exercise-seats"
          countUp={reveal && !reduced}
          figures={[
            { label: "Seats in the room", value: counts.seats },
            { label: "Already coming", value: counts.alreadyComing },
            { label: "Still open", value: counts.open },
          ]}
        />
        <p className="ce-meta text-ce-muted">A team runs results once per event.</p>
      </div>
    </div>
  );
}

/** Each sentence on its own line, numerals in CPP Green (§6.15). */
function splitSentences(text: string): string[] {
  return text.split(/(?<=\.) /);
}

function Numerals({ text }: { readonly text: string }): React.JSX.Element {
  const parts = text.split(/(\d+)/);
  return (
    <>
      {parts.map((part, index) =>
        /^\d+$/.test(part) ? (
          <span key={index} className="ce-num text-ce-primary">
            {part}
          </span>
        ) : (
          <React.Fragment key={index}>{part}</React.Fragment>
        ),
      )}
    </>
  );
}

function SeatingChart({
  counts,
  phase,
}: {
  readonly counts: SeatCountsView;
  readonly phase: Phase;
}): React.JSX.Element {
  const seats = Array.from({ length: Math.max(0, counts.seats) }, (_, index) =>
    index < counts.alreadyComing
      ? "taken"
      : index < counts.alreadyComing + counts.added
        ? "added"
        : "open",
  );
  return (
    <div className="ce-card flex min-w-0 flex-col gap-4 p-4 md:p-6" data-slot="exercise-room">
      <div className="flex items-baseline justify-between gap-3 border-b border-ce-line pb-3">
        <h2 className="ce-h3 text-ce-ink">The room</h2>
        <span className="ce-meta ce-num text-ce-muted">{counts.seats} seats</span>
      </div>
      <div
        aria-hidden="true"
        className="flex flex-col gap-3 transition-opacity duration-200"
        style={{ opacity: phase >= 1 ? 1 : 0 }}
      >
        <div className="ce-meta rounded-[8px] bg-ce-sunk py-2 text-center text-ce-muted">
          Front of the room
        </div>
        <div className="grid grid-cols-10 gap-1.5 sm:gap-2 md:gap-3">
          {seats.map((kind, index) => (
            <Seat key={index} kind={kind} index={index} counts={counts} phase={phase} />
          ))}
        </div>
      </div>
      <ul className="ce-meta flex flex-wrap gap-x-5 gap-y-2 border-t border-ce-line pt-3 text-ce-ink">
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="size-4 rounded-[4px] bg-ce-seat-taken" />
          Already coming ({counts.alreadyComing})
        </li>
        <li className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="flex size-4 items-center justify-center rounded-[4px] bg-ce-primary text-ce-on-primary"
          >
            <Check className="size-3" strokeWidth={3} />
          </span>
          Your invitations ({counts.added})
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="size-4 rounded-[4px] border-2 border-ce-line-strong" />
          Still open ({counts.open})
        </li>
      </ul>
    </div>
  );
}

function Seat({
  kind,
  index,
  counts,
  phase,
}: {
  readonly kind: "taken" | "added" | "open";
  readonly index: number;
  readonly counts: SeatCountsView;
  readonly phase: Phase;
}): React.JSX.Element {
  const base =
    "flex aspect-square items-center justify-center rounded-[4px] border-2 transition-[background-color,border-color,transform] ease-[var(--ce-ease-out)]";
  if (kind === "taken") {
    const on = phase >= 2;
    return (
      <span
        className={`${base} duration-200 ${on ? "border-ce-seat-taken bg-ce-seat-taken" : "border-ce-line-strong"}`}
        style={{ transitionDelay: phase === 2 ? `${index * 12}ms` : "0ms" }}
      />
    );
  }
  if (kind === "added") {
    const on = phase >= 3;
    const order = index - counts.alreadyComing;
    return (
      <span
        className={`${base} duration-300 ${
          on ? "border-ce-primary bg-ce-primary text-ce-on-primary" : "border-ce-line-strong"
        } ${phase === 3 ? "ce-seat-pop" : ""}`}
        style={{ transitionDelay: phase === 3 ? `${order * 60}ms` : "0ms", animationDelay: `${order * 60}ms` }}
      >
        {on ? <Check className="size-3/5" strokeWidth={3} /> : null}
      </span>
    );
  }
  return (
    <span
      className={`${base} duration-300 border-ce-line-strong ${phase === 4 ? "ce-seat-brighten" : ""}`}
    />
  );
}
