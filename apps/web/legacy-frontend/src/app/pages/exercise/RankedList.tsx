/**
 * The ranked list: the names, in order, with one reason each.
 *
 * Design spec §8 and ADR-0025 D8 between them fix the fields: rank, name,
 * major, year, marker, reason — and *no number named like a score*. `rank` is
 * a position, and the only other numerals on this table are the profile
 * numbers, which are identifiers. There is no percentage, no confidence, no
 * bar and no "match strength", and there is deliberately no column that could
 * quietly become one.
 *
 * **Layout (DESIGN.md §6.7, §8.7).** On desktop a real `<table>`: rank, name
 * with the reason line directly beneath it (so the eye reads name, then why —
 * there is no "Why" column), major, year, and the marker chip. On the 390
 * layout an `<ol>` of cards with the same content. The choice is made in
 * JavaScript, not by hiding one with CSS, so a screen reader never meets
 * every name twice. The table scrolls inside its own box.
 *
 * **The reason is the server's string, rendered as-is.** OQ-CE-12 stores Ann's
 * phrases byte-for-byte (`ANN_MAJOR_ONLY_PHRASE`, `ANN_TIED_ON_YEAR_PHRASE`)
 * and the server frames and punctuates them. Capitalising, truncating or
 * title-casing here would be putting words in her mouth, and composing two
 * reasons would break the server's own rule that a tie line wins over a
 * major-only line.
 *
 * **`contributing_factor_keys` are never printed.** They are rulebook keys;
 * Ann's words for them arrive as `factor_labels` on the same response, and
 * that map is what turns a key into something a projector may show.
 *
 * Not `AIMatching.tsx`'s `CandidateCard`. Design spec §16 asks for its reuse,
 * and two things rule it out: it is a local function in a module that imports
 * the CBA API client, the session hook and the portal gate — an import edge
 * ADR-0025 D1 forbids from an exercise route — and it renders a score through
 * `ScoreValue`/`formatScore`, which D8 forbids here. The shape below follows
 * it; the module boundary does not cross.
 */
import * as React from "react";
import { Link2 } from "lucide-react";
import { motion } from "motion/react";

import { cn } from "../../components/ui/utils";
import { type ListEntryView, UNDECIDED_GOAL_HALF_LABEL_KEY } from "../../../lib/exerciseClient";
import { CE_MOTION_MS, MarkerChip, ceMotion, usePrefersReducedMotion } from "./desk";
import { EmptySlotArt } from "./EmptySlotArt";
import { useNarrowViewport } from "./useNarrowViewport";

/** The rulebook key for "career goal fits this event". Never rendered. */
const CAREER_GOAL_FIT = "career_goal_fit";

export interface RankedListProps {
  readonly entries: readonly ListEntryView[];
  /** Ann's plain words per factor key, from the same response. */
  readonly factorLabels: Readonly<Record<string, string>>;
  /** Profile numbers to mark, used by the side-by-side view. */
  readonly highlightProfileNos?: readonly number[];
  /** An accessible name, e.g. the setting this list was built from. */
  readonly caption: string;
  /**
   * `auto` (default): a table on desktop, cards on 390. `cards`: always
   * cards — the compare view's half-width columns (§6.12).
   */
  readonly layout?: "auto" | "cards";
}

/**
 * Profile numbers that were not on the previous list: the `ce-row-join`
 * wash (§5), cleared after 900ms. Nothing is "new" on the first render.
 */
function useJoined(entries: readonly ListEntryView[]): ReadonlySet<number> {
  const previous = React.useRef<ReadonlySet<number> | null>(null);
  const [joined, setJoined] = React.useState<ReadonlySet<number>>(() => new Set());
  const ids = entries.map((entry) => entry.profile_no).join(",");

  React.useLayoutEffect(() => {
    const now = new Set(entries.map((entry) => entry.profile_no));
    const before = previous.current;
    previous.current = now;
    if (before === null) {
      return undefined;
    }
    const fresh = new Set([...now].filter((id) => !before.has(id)));
    setJoined(fresh);
    if (fresh.size === 0) {
      return undefined;
    }
    const timer = window.setTimeout(() => setJoined(new Set()), CE_MOTION_MS.rowJoin);
    return () => window.clearTimeout(timer);
    // `ids` is the list's identity; `entries` is read for its current value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids]);

  return joined;
}

export function RankedList({
  entries,
  factorLabels,
  highlightProfileNos,
  caption,
  layout = "auto",
}: RankedListProps): React.JSX.Element {
  const narrow = useNarrowViewport();
  const reduced = usePrefersReducedMotion();
  const joined = useJoined(entries);
  const highlighted = highlightProfileNos ?? [];

  if (entries.length === 0) {
    return (
      <div className="flex items-center gap-ce-4 py-ce-4">
        <EmptySlotArt className="w-24" />
        <p className="ce-type-body ce-measure text-ce-ink">
          Nobody is on this list. Nobody in this data file can be ranked for this event with these
          weights.
        </p>
      </div>
    );
  }

  /** Row styling shared by both layouts: overlap wash, or the join wash. */
  function rowState(entry: ListEntryView): { onBoth: boolean; className: string; style?: React.CSSProperties } {
    const overlapIndex = highlighted.indexOf(entry.profile_no);
    if (overlapIndex >= 0) {
      return {
        onBoth: true,
        className: "ce-overlap-pulse bg-ce-gold-tint",
        style: { "--ce-i": overlapIndex } as React.CSSProperties,
      };
    }
    return { onBoth: false, className: joined.has(entry.profile_no) ? "ce-row-join" : "" };
  }

  if (layout === "cards" || narrow) {
    return (
      <ol aria-label={caption} data-slot="exercise-ranked-list" data-layout="cards" className="flex flex-col">
        {entries.map((entry) => {
          const state = rowState(entry);
          return (
            <motion.li
              key={entry.profile_no}
              {...ceMotion("row-reorder", reduced)}
              data-on-both={state.onBoth ? "true" : undefined}
              className={cn(
                "flex gap-ce-3 border-b border-ce-line px-ce-2 py-ce-4 last:border-b-0",
                state.className,
              )}
              style={state.style}
            >
              <span data-slot="exercise-rank" className="ce-type-rank min-w-12 shrink-0 text-ce-primary">
                {entry.rank}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-ce-1">
                <div className="flex flex-wrap items-center gap-ce-2">
                  <span className="ce-type-body font-semibold text-ce-ink">{entry.display_name}</span>
                  {state.onBoth ? <OnBothChip /> : null}
                </div>
                <ReasonLines entry={entry} labels={factorLabels} />
                <p className="ce-type-meta text-ce-ink-muted">
                  {entry.major} · {entry.class_year}
                </p>
                <MarkerChip marker={entry.marker} className="self-start" />
              </div>
            </motion.li>
          );
        })}
      </ol>
    );
  }

  // The table scrolls inside its own box. Five columns do not fit a narrow
  // window, and a table wider than the page pushed columns off-screen with
  // no way to reach them.
  //
  // Column shares: the marker chip ("major plus events attended") gets the
  // widest data column so it wraps to two lines at most beside the 1280
  // weights card; cells use 8px side padding to leave the words room.
  return (
    <div className="ce-scroll-x overflow-x-auto">
      <table
        className="w-full min-w-[40rem] table-fixed border-collapse text-left"
        data-slot="exercise-ranked-list"
        data-layout="table"
      >
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="ce-type-label bg-ce-surface-sunk text-ce-ink">
            <th scope="col" className="w-[4.5rem] rounded-l-ce-control px-ce-2 py-ce-3">
              Rank
            </th>
            <th scope="col" className="px-ce-2 py-ce-3">
              Name
            </th>
            <th scope="col" className="w-[20%] px-ce-2 py-ce-3">
              Major
            </th>
            <th scope="col" className="w-[18%] px-ce-2 py-ce-3">
              Year
            </th>
            <th scope="col" className="w-[28%] rounded-r-ce-control px-ce-2 py-ce-3">
              How much we know
            </th>
          </tr>
        </thead>
        <tbody className="ce-type-body text-ce-ink">
          {entries.map((entry) => {
            const state = rowState(entry);
            return (
              <motion.tr
                key={entry.profile_no}
                {...ceMotion("row-reorder", reduced)}
                data-on-both={state.onBoth ? "true" : undefined}
                className={cn(
                  "border-b border-ce-line align-top last:border-b-0",
                  state.onBoth ? "" : "hover:bg-ce-surface-sunk",
                  state.className,
                )}
                style={state.style}
              >
                <td className="ce-type-rank px-ce-2 py-ce-4 text-ce-primary">{entry.rank}</td>
                <td className="px-ce-2 py-ce-4 break-words" data-slot="exercise-ranked-name">
                  <div className="flex flex-wrap items-center gap-ce-2">
                    <span className="font-semibold">{entry.display_name}</span>
                    {state.onBoth ? <OnBothChip /> : null}
                  </div>
                  <ReasonLines entry={entry} labels={factorLabels} />
                </td>
                <td className="px-ce-2 py-ce-4">{entry.major}</td>
                <td className="px-ce-2 py-ce-4">{entry.class_year}</td>
                <td className="px-ce-2 py-ce-4">
                  <MarkerChip marker={entry.marker} className="whitespace-normal px-ce-2" />
                </td>
              </motion.tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** "on both lists" (§6.7): `Link2` and words on the gold highlighter, never colour alone. */
function OnBothChip(): React.JSX.Element {
  return (
    <span
      data-slot="exercise-on-both"
      className="ce-type-meta inline-flex items-center gap-ce-1 whitespace-nowrap rounded-ce-pill bg-ce-gold px-ce-2 text-ce-on-gold"
    >
      <Link2 aria-hidden="true" className="size-4 shrink-0" />
      on both lists
    </span>
  );
}

/** The server's reason, verbatim (OQ-CE-12), then what counted in Ann's words. */
function ReasonLines({
  entry,
  labels,
}: {
  readonly entry: ListEntryView;
  readonly labels: Readonly<Record<string, string>>;
}): React.JSX.Element {
  return (
    <>
      <p className="ce-type-reason mt-ce-1 text-ce-ink-muted">{entry.reason}</p>
      <FactorNames
        keys={entry.contributing_factor_keys}
        labels={labels}
        undecidedGoalHalf={entry.undecided_goal_half}
      />
    </>
  );
}

/**
 * What counted, in Ann's words.
 *
 * A key with no label in `factor_labels` is dropped rather than printed raw:
 * showing `past_event_topic_overlap` to a marketing class would be showing a
 * column name, which is the thing §16 is asking not to happen.
 *
 * **The Undecided half (D2).** When `undecided_goal_half` is set, the
 * career-goal factor counted only because an undecided goal suits a broad
 * event. Printing "career goal fits this event" next to an "Undecided" card
 * would say the opposite, so that one factor takes the server's own words for
 * the half instead: the `factor_labels` entry under
 * `UNDECIDED_GOAL_HALF_LABEL_KEY`. Like any key without a label, it is dropped
 * if the server sends none — never replaced by the goal-fit label. The weight
 * slider's label is unchanged: it names the factor, not this person.
 */
function FactorNames({
  keys,
  labels,
  undecidedGoalHalf,
}: {
  readonly keys: readonly string[];
  readonly labels: Readonly<Record<string, string>>;
  readonly undecidedGoalHalf: boolean;
}): React.JSX.Element | null {
  const named = keys
    .map((key) =>
      undecidedGoalHalf && key === CAREER_GOAL_FIT
        ? labels[UNDECIDED_GOAL_HALF_LABEL_KEY]
        : labels[key],
    )
    .filter((label): label is string => label !== undefined);
  if (named.length === 0) {
    return null;
  }
  return (
    <span data-slot="exercise-factor-names" className="ce-type-meta block text-ce-ink-muted">
      {named.join("; ")}
    </span>
  );
}
