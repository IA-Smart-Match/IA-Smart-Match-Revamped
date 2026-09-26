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

import type { ListEntryView } from "../../../lib/exerciseClient";
import { markerLabel } from "./markers";

export interface RankedListProps {
  readonly entries: readonly ListEntryView[];
  /** Ann's plain words per factor key, from the same response. */
  readonly factorLabels: Readonly<Record<string, string>>;
  /** Profile numbers to mark, used by the side-by-side view. */
  readonly highlightProfileNos?: readonly number[];
  /** An accessible name, e.g. the setting this list was built from. */
  readonly caption: string;
}

export function RankedList({
  entries,
  factorLabels,
  highlightProfileNos,
  caption,
}: RankedListProps): React.JSX.Element {
  const highlighted = new Set(highlightProfileNos ?? []);

  if (entries.length === 0) {
    return (
      <p className="text-xl text-slate-700 dark:text-slate-200">
        Nobody is on this list. Nobody in this data file can be ranked for this event with these
        weights.
      </p>
    );
  }

  // The table scrolls inside its own box. Six columns do not fit a phone, and
  // a table wider than the page pushed "Why" off-screen with no way to reach it.
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-xl" data-slot="exercise-ranked-list">
        <caption className="pb-2 text-left text-xl text-slate-600 dark:text-slate-300">
          {caption}
        </caption>
        <thead>
          <tr className="border-b-2 border-slate-400 text-lg tracking-wide uppercase">
            <th scope="col" className="py-2 pr-4">
              Rank
            </th>
            <th scope="col" className="py-2 pr-4">
              Name
            </th>
            <th scope="col" className="py-2 pr-4">
              Major
            </th>
            <th scope="col" className="py-2 pr-4">
              Year
            </th>
            <th scope="col" className="py-2 pr-4">
              How much we know
            </th>
            <th scope="col" className="py-2">
              Why
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const onBoth = highlighted.has(entry.profile_no);
            return (
              <tr
                key={entry.profile_no}
                data-on-both={onBoth ? "true" : undefined}
                className={`border-b border-slate-200 dark:border-slate-700 ${
                  onBoth ? "bg-amber-100 dark:bg-amber-950" : ""
                }`}
              >
                <td className="py-2 pr-4 font-bold">{entry.rank}</td>
                <td className="py-2 pr-4">
                  {entry.display_name}
                  {onBoth ? (
                    <span className="ml-2 rounded bg-amber-300 px-2 py-0.5 text-base font-semibold text-amber-950">
                      on both lists
                    </span>
                  ) : null}
                </td>
                <td className="py-2 pr-4">{entry.major}</td>
                <td className="py-2 pr-4">{entry.class_year}</td>
                <td className="py-2 pr-4">{markerLabel(entry.marker)}</td>
                <td className="py-2">
                  {/* The server's sentence, verbatim (OQ-CE-12). */}
                  {entry.reason}
                  <FactorNames keys={entry.contributing_factor_keys} labels={factorLabels} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * What counted, in Ann's words.
 *
 * A key with no label in `factor_labels` is dropped rather than printed raw:
 * showing `past_event_topic_overlap` to a marketing class would be showing a
 * column name, which is the thing §16 is asking not to happen.
 */
function FactorNames({
  keys,
  labels,
}: {
  readonly keys: readonly string[];
  readonly labels: Readonly<Record<string, string>>;
}): React.JSX.Element | null {
  const named = keys.map((key) => labels[key]).filter((label): label is string => label !== undefined);
  if (named.length === 0) {
    return null;
  }
  return (
    <span className="block text-lg text-slate-600 dark:text-slate-300">{named.join("; ")}</span>
  );
}
