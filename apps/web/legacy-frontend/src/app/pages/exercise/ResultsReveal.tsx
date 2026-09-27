/**
 * The results reveal: the room, the D8 sentence as the headline, and the ruled
 * figures band (DESIGN.md §6.15, focal moment `ce-seat-fill` §5.1, §7.8).
 *
 * **The room is decoration; the words carry the numbers.** The seating chart
 * is `aria-hidden`. The sentence (built by `seatsSentence`, passed in whole so
 * its words are never re-made here) and the figures band are the accessible
 * content.
 *
 * **Every count is the server's.** Taken seats are `existing_signups`; the
 * team's seats are the team panel's `attended_count`, the same number D8's
 * sentence says "added", and the one the server computes `seats_empty` from
 * (`60 - 8 - attended`); open seats are what is left of `event_seats`. The
 * client never subtracts to find a figure it shows.
 *
 * **The seats fill once.** `reveal` is true only on the first render after
 * this screen's own run succeeded; a later visit shows the final state. With
 * reduced motion the final state shows at once and the sentence is announced
 * immediately; otherwise the `aria-live` region speaks it once, when the fill
 * ends.
 */
import * as React from "react";

import { Seat, seatFillPlan, useCountUp, usePrefersReducedMotion, useSeatFill } from "./desk";
import type { SeatKind } from "./desk";

export interface ResultsRevealProps {
  readonly eventSeats: number;
  readonly alreadyComing: number;
  /** The team panel's `attended_count`. */
  readonly added: number;
  readonly open: number;
  /** D8's three sentences, from `seatsSentence`, verbatim. */
  readonly sentence: string;
  /** Play `ce-seat-fill`: only on the first render after a run on this screen. */
  readonly reveal: boolean;
}

/** When the band's count-up starts, with the open seats (§5.1 step 4). */
const COUNT_UP_DELAY_MS = 1400;

export function ResultsReveal({
  eventSeats,
  alreadyComing,
  added,
  open,
  sentence,
  reveal,
}: ResultsRevealProps): React.JSX.Element {
  const reduced = usePrefersReducedMotion();
  const fill = useSeatFill({ play: reveal, reduced });
  const plan = React.useMemo(
    () => seatFillPlan({ total: eventSeats, taken: alreadyComing, added }),
    [eventSeats, alreadyComing, added],
  );

  return (
    <section className="grid gap-ce-5 lg:grid-cols-12 lg:gap-ce-6" data-slot="exercise-reveal">
      <Room
        seats={plan.seats}
        animate={fill.animating}
        counts={{ taken: alreadyComing, added, open }}
      />
      <div className="flex min-w-0 flex-col justify-center gap-ce-5 lg:col-span-6">
        <Headline sentence={sentence} step={fill.step} hidden={reveal} />
        {reveal ? (
          <p
            className="sr-only"
            role="status"
            aria-live="polite"
            data-slot="exercise-seats-announce"
          >
            {fill.announce ? sentence : ""}
          </p>
        ) : null}
        <FiguresBand
          animate={reveal && !reduced}
          figures={[
            { label: "Seats in the room", value: eventSeats },
            { label: "Already coming", value: alreadyComing },
            { label: "Still open", value: open },
          ]}
        />
      </div>
    </section>
  );
}

function Room({
  seats,
  animate,
  counts,
}: {
  readonly seats: ReturnType<typeof seatFillPlan>["seats"];
  readonly animate: boolean;
  readonly counts: Readonly<Record<SeatKind, number>>;
}): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      data-slot="exercise-room"
      className="ce-card flex min-w-0 flex-col gap-ce-4 p-ce-4 md:p-ce-5 lg:col-span-6"
    >
      <p className="ce-type-h3 text-ce-ink">The room</p>
      <p className="ce-type-meta rounded-ce-control bg-ce-surface-sunk py-ce-1 text-center text-ce-ink-muted">
        Front of the room
      </p>
      <div
        data-slot="exercise-room-seats"
        className="mx-auto grid w-full max-w-[440px] grid-cols-10 gap-[6px] md:gap-ce-2">
        {seats.map((seat) => (
          <Seat key={seat.index} kind={seat.kind} delayMs={seat.delayMs} animate={animate} />
        ))}
      </div>
      <ul className="ce-type-meta flex flex-wrap gap-x-ce-5 gap-y-ce-2 border-t border-ce-line pt-ce-4 text-ce-ink-muted">
        <LegendItem kind="taken" label="Already coming" count={counts.taken} />
        <LegendItem kind="added" label="Your invitations" count={counts.added} />
        <LegendItem kind="open" label="Still open" count={counts.open} />
      </ul>
    </div>
  );
}

function LegendItem({
  kind,
  label,
  count,
}: {
  readonly kind: SeatKind;
  readonly label: string;
  readonly count: number;
}): React.JSX.Element {
  return (
    <li className="flex items-center gap-ce-2">
      <Seat kind={kind} animate={false} className="size-4 shrink-0" />
      <span>
        {label} <span className="ce-tabular">({count})</span>
      </span>
    </li>
  );
}

/**
 * D8's sentence as the screen's headline, one sentence per line, numerals in
 * primary. The words are the sentence's own; only spans are added.
 */
function Headline({
  sentence,
  step,
  hidden,
}: {
  readonly sentence: string;
  readonly step: 1 | 2 | 3 | 4;
  /** While the reveal owns the announcement, the live region speaks instead. */
  readonly hidden: boolean;
}): React.JSX.Element {
  const lines = sentence.split(/(?<=\.) /);
  return (
    <p
      data-slot="exercise-seats-sentence"
      aria-hidden={hidden ? "true" : undefined}
      className="font-ce-serif text-[28px] leading-[36px] font-semibold text-ce-ink md:text-[40px] md:leading-[48px]"
    >
      {lines.map((line, index) => (
        <React.Fragment key={index}>
          {index === 0 ? null : " "}
          <span
            className="block transition-opacity duration-[240ms] ease-ce-out motion-reduce:transition-none"
            style={{ opacity: step >= index + 2 ? 1 : 0 }}
          >
            {line.split(/(\d+)/).map((part, partIndex) =>
              /^\d+$/.test(part) ? (
                <span key={partIndex} data-numeral="" className="ce-tabular text-ce-primary">
                  {part}
                </span>
              ) : (
                part
              ),
            )}
          </span>
        </React.Fragment>
      ))}
    </p>
  );
}

interface Figure {
  readonly label: string;
  readonly value: number;
}

/** A ruled band, not cards (§6.15): numerals over labels, split by 1px rules. */
function FiguresBand({
  figures,
  animate,
}: {
  readonly figures: readonly Figure[];
  readonly animate: boolean;
}): React.JSX.Element {
  return (
    <dl
      data-slot="exercise-seats"
      className="grid grid-cols-3 border-t border-ce-line-strong pt-ce-5"
    >
      {figures.map((figure, index) => (
        <div
          key={figure.label}
          className={`flex min-w-0 flex-col-reverse gap-ce-1 ${
            index === 0 ? "pr-ce-3" : "border-l border-ce-line-strong px-ce-3 md:px-ce-5"
          }`}
        >
          <dt className="ce-type-label text-ce-ink">{figure.label}</dt>
          <FigureValue value={figure.value} animate={animate} />
        </div>
      ))}
    </dl>
  );
}

function FigureValue({
  value,
  animate,
}: {
  readonly value: number;
  readonly animate: boolean;
}): React.JSX.Element {
  const shown = useCountUp(value, { reduced: !animate, delayMs: COUNT_UP_DELAY_MS });
  return (
    <dd className="ce-type-display text-ce-primary max-md:text-[40px] max-md:leading-[44px]">
      {shown}
    </dd>
  );
}
