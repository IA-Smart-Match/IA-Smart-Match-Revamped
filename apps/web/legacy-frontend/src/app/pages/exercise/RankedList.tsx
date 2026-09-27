/**
 * The ranked list: the names, in order, with one reason each.
 *
 * Design spec §8 and ADR-0025 D8 between them fix the columns: rank, name,
 * major, year, marker, reason — and *no number named like a score*. `rank` is
 * a position, and the only other numerals on this table are the profile
 * numbers, which are identifiers. There is no percentage, no confidence, no
 * bar and no "match strength", and there is deliberately no column that could
 * quietly become one.
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
import { Circle, CircleDot, IdCard, Link2 } from "lucide-react";
import { motion } from "motion/react";

import { type ListEntryView, UNDECIDED_GOAL_HALF_LABEL_KEY } from "../../../lib/exerciseClient";
import { EmptySlotArt } from "./exerciseArt";
import { Chip, type ChipTone, useIsNarrow } from "./exerciseUi";
import { markerLabel } from "./markers";

/** The rulebook key for "career goal fits this event". Never rendered. */
const CAREER_GOAL_FIT = "career_goal_fit";

/** `ce-row-reorder`: spring, stiffness 500, damping 40 (≈280ms settle). */
const ROW_SPRING = { type: "spring", stiffness: 500, damping: 40 } as const;

export interface RankedListProps {
  readonly entries: readonly ListEntryView[];
  /** Ann's plain words per factor key, from the same response. */
  readonly factorLabels: Readonly<Record<string, string>>;
  /** Profile numbers to mark, used by the side-by-side view. */
  readonly highlightProfileNos?: readonly number[];
  /** An accessible name, e.g. the setting this list was built from. */
  readonly caption: string;
  /**
   * `"full"` is the matching screen's five columns. `"compact"` is the
   * compare view's: rank and the name with its reason line, so two lists fit
   * side by side (DESIGN.md §6.12).
   */
  readonly variant?: "full" | "compact";
  /** Pulse each "on both lists" row once, as a comparison opens (`ce-overlap-pulse`). */
  readonly pulseOverlap?: boolean;
  /** Show the caption to sighted readers too (the compare view's list titles do). */
  readonly showCaption?: boolean;
}

export function RankedList({
  entries,
  factorLabels,
  highlightProfileNos,
  caption,
  variant = "full",
  pulseOverlap = false,
  showCaption = false,
}: RankedListProps): React.JSX.Element {
  const narrow = useIsNarrow();
  const highlighted = new Set(highlightProfileNos ?? []);
  const joined = useJoinedNames(entries);

  if (entries.length === 0) {
    return (
      <div className="ce-well flex flex-col items-center gap-4 px-5 py-8 text-center">
        <EmptySlotArt className="h-20 w-24 text-ce-line-strong" />
        <p className="ce-body max-w-[48ch] text-ce-ink">
          Nobody is on this list. Nobody in this data file can be ranked for this event with these
          weights.
        </p>
      </div>
    );
  }

  let overlapIndex = 0;
  const rows = entries.map((entry) => {
    const onBoth = highlighted.has(entry.profile_no);
    const pulseDelay = onBoth && pulseOverlap ? Math.min(overlapIndex++ * 30, 360) : null;
    return { entry, onBoth, pulseDelay, isNew: joined.has(entry.profile_no) };
  });

  // §8.7: a real table at 768 and up; on a phone the same content, in the
  // same order, as an ordered list of cards.
  if (narrow) {
    return (
      <ol aria-label={caption} data-slot="exercise-ranked-list" className="flex flex-col">
        {rows.map(({ entry, onBoth, pulseDelay, isNew }) => (
          <motion.li
            layout="position"
            transition={ROW_SPRING}
            key={entry.profile_no}
            data-on-both={onBoth ? "true" : undefined}
            className={rowWash(onBoth, pulseDelay, isNew, "rounded-[10px] border-b border-ce-line px-3 py-4")}
            style={pulseDelay === null ? undefined : { animationDelay: `${pulseDelay}ms` }}
          >
            <div className="flex gap-3">
              <span className="ce-rank w-9 shrink-0 text-ce-primary">{entry.rank}</span>
              <div className="flex min-w-0 flex-col gap-1">
                <NameLine entry={entry} onBoth={onBoth} />
                <ReasonLines entry={entry} labels={factorLabels} />
                {variant === "full" ? (
                  <>
                    <span className="ce-meta text-ce-muted">
                      {entry.major} · {entry.class_year}
                    </span>
                    <span>
                      <MarkerChip marker={entry.marker} />
                    </span>
                  </>
                ) : (
                  <span className="ce-meta text-ce-muted">
                    {entry.major} · {entry.class_year}
                  </span>
                )}
              </div>
            </div>
          </motion.li>
        ))}
      </ol>
    );
  }

  // The table scrolls inside its own box. Five columns do not fit a narrow
  // window, and a table wider than the page pushed columns off-screen with no
  // way to reach them.
  return (
    <div className="ce-scroll overflow-x-auto">
      <table
        className="w-full border-collapse text-left"
        data-slot="exercise-ranked-list"
        data-variant={variant}
      >
        <caption
          className={
            showCaption ? "ce-h3 pb-3 text-left text-ce-ink" : "sr-only"
          }
        >
          {caption}
        </caption>
        <thead>
          <tr className="ce-label bg-ce-sunk text-ce-ink">
            <th scope="col" className="w-16 rounded-l-[10px] px-4 py-3">
              Rank
            </th>
            <th scope="col" className={`px-4 py-3 ${variant === "compact" ? "rounded-r-[10px]" : ""}`}>
              Name
            </th>
            {variant === "full" ? (
              <>
                <th scope="col" className="px-4 py-3">
                  Major
                </th>
                <th scope="col" className="px-4 py-3">
                  Year
                </th>
                <th scope="col" className="rounded-r-[10px] px-4 py-3">
                  How much we know
                </th>
              </>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ entry, onBoth, pulseDelay, isNew }) => (
            <motion.tr
              layout="position"
              transition={ROW_SPRING}
              key={entry.profile_no}
              data-on-both={onBoth ? "true" : undefined}
              className={rowWash(
                onBoth,
                pulseDelay,
                isNew,
                "border-b border-ce-line align-top hover:bg-ce-sunk/60",
              )}
              style={pulseDelay === null ? undefined : { animationDelay: `${pulseDelay}ms` }}
            >
              <td className="px-4 py-4">
                <span className="ce-rank text-ce-primary">{entry.rank}</span>
              </td>
              <td className="px-4 py-4">
                <div className="flex min-w-[14rem] flex-col gap-1">
                  <NameLine entry={entry} onBoth={onBoth} />
                  <ReasonLines entry={entry} labels={factorLabels} />
                  {variant === "compact" ? (
                    <span className="ce-meta text-ce-muted">
                      {entry.major} · {entry.class_year}
                    </span>
                  ) : null}
                </div>
              </td>
              {variant === "full" ? (
                <>
                  <td className="ce-body px-4 py-4 text-ce-ink">{entry.major}</td>
                  <td className="ce-body px-4 py-4 text-ce-ink">{entry.class_year}</td>
                  <td className="px-4 py-4">
                    <MarkerChip marker={entry.marker} />
                  </td>
                </>
              ) : null}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The row's wash: gold for "on both lists" (a full wash, never a left stripe —
 * DESIGN.md §6.7, §10), a one-off gold fade for a name that just joined.
 */
function rowWash(
  onBoth: boolean,
  pulseDelay: number | null,
  isNew: boolean,
  base: string,
): string {
  if (onBoth) {
    return `${base} bg-ce-gold-tint${pulseDelay === null ? "" : " ce-overlap-pulse"}`;
  }
  return isNew ? `${base} ce-row-join` : base;
}

/**
 * Names that were not on the previous list the component showed.
 *
 * Empty on the first render — a list arriving is not a name joining it — and
 * after that, whatever the latest re-weighting brought in (`ce-row-join`).
 */
function useJoinedNames(entries: readonly ListEntryView[]): ReadonlySet<number> {
  const seen = React.useRef<ReadonlySet<number> | null>(null);
  const current = entries.map((entry) => entry.profile_no);
  const previous = seen.current;
  const joined =
    previous === null ? new Set<number>() : new Set(current.filter((no) => !previous.has(no)));
  React.useEffect(() => {
    seen.current = new Set(entries.map((entry) => entry.profile_no));
  }, [entries]);
  return joined;
}

function NameLine({
  entry,
  onBoth,
}: {
  readonly entry: ListEntryView;
  readonly onBoth: boolean;
}): React.JSX.Element {
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="ce-body font-semibold text-ce-ink">{entry.display_name}</span>
      {onBoth ? (
        <Chip tone="gold" icon={<Link2 aria-hidden="true" className="size-4" />}>
          on both lists
        </Chip>
      ) : null}
    </span>
  );
}

/**
 * The reason, directly under the name (DESIGN.md §6.7: no "Why" column).
 *
 * **The reason is the server's string, rendered as-is** (OQ-CE-12), in
 * Proxima Sera like a margin note. The line under it names what counted, in
 * Ann's words.
 */
function ReasonLines({
  entry,
  labels,
}: {
  readonly entry: ListEntryView;
  readonly labels: Readonly<Record<string, string>>;
}): React.JSX.Element {
  return (
    <>
      {/* The server's sentence, verbatim (OQ-CE-12). */}
      <span className="ce-reason text-ce-muted">{entry.reason}</span>
      <FactorNames
        keys={entry.contributing_factor_keys}
        labels={labels}
        undecidedGoalHalf={entry.undecided_goal_half}
      />
    </>
  );
}

/** How much we know, as icon plus words (DESIGN.md §6.8). Not interactive. */
const MARKER_STYLE: Readonly<Record<string, { tone: ChipTone; Icon: typeof Circle }>> = {
  major_only: { tone: "neutral", Icon: Circle },
  major_plus_events: { tone: "avocado", Icon: CircleDot },
  completed_card: { tone: "primary", Icon: IdCard },
};

export function MarkerChip({ marker }: { readonly marker: string }): React.JSX.Element {
  const style = MARKER_STYLE[marker];
  // An unrecognised marker renders its raw string, in the neutral style.
  if (style === undefined) {
    return <Chip tone="neutral">{markerLabel(marker)}</Chip>;
  }
  const { tone, Icon } = style;
  return (
    <Chip tone={tone} icon={<Icon aria-hidden="true" className="size-4 shrink-0" />}>
      {markerLabel(marker)}
    </Chip>
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
    <span data-slot="exercise-factor-names" className="ce-meta text-ce-muted">
      {named.join("; ")}
    </span>
  );
}
