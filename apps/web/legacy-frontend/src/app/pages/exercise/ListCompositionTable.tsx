/**
 * "Who is on the list" — the list's shape beside the whole file's.
 *
 * Requirements, "Who is on the list" row: *"For the current list, a small
 * table: count by major, by year, and by 'how much we know' group, next to the
 * same counts for all 300."* Both columns are always shown, because the
 * comparison is the whole point: a count of 4 marketing majors means nothing
 * until you can see there are 90 of them.
 *
 * Two honest numbers sit beside the table rather than being folded into it:
 *
 * - **`unrankable_profile_count`** — profiles in the file that could not be
 *   ranked for this event at all. They are in the "all profiles" column and
 *   can never be in the "on this list" one, and saying so is the difference
 *   between a table that adds up and one that seems to have lost people.
 *
 * No vocabulary is written here. Majors and years are keys of the maps the
 * server sent, rendered as the file spells them. The vocabularies are closed
 * by Ann's workbook of 2026-09-24, but the server owns them, not this screen.
 *
 * **Layout (DESIGN.md §6.9, §7.4).** Three small tables in one row on
 * desktop, each in a white card; on the 390 layout each folds into a
 * disclosure. Counts are plain tabular numerals, right-aligned; paired count
 * bars are not used because they read like a share. A 0 is ink, not muted.
 * Every table scrolls in its own box, so a long major never widens the page.
 */
import * as React from "react";
import { ChevronDown } from "lucide-react";

import type { GroupCountsView, ListCompositionView } from "../../../lib/exerciseClient";
// The extension is explicit: `ListCoverageNotice.tsx` and its helper
// `listCoverageNotice.ts` differ only in casing, which an extensionless
// specifier cannot tell apart on a case-insensitive filesystem (TS1149).
import { ListCoverageNotice } from "./ListCoverageNotice.tsx";
import { dimensionLabel, markerLabel } from "./markers";
import { useNarrowViewport } from "./useNarrowViewport";

export interface ListCompositionTableProps {
  readonly composition: ListCompositionView;
  readonly unrankableProfileCount: number;
}

export function ListCompositionTable({
  composition,
  unrankableProfileCount,
}: ListCompositionTableProps): React.JSX.Element {
  const narrow = useNarrowViewport();
  const groups: readonly { counts: GroupCountsView; label?: (value: string) => string }[] = [
    { counts: composition.by_major },
    { counts: composition.by_class_year },
    { counts: composition.by_marker, label: markerLabel },
  ];

  return (
    <section data-slot="exercise-list-composition" className="flex flex-col gap-ce-4">
      <h2 className="ce-type-h2 text-ce-ink">Who is on the list</h2>

      {/* PR #161's one-line notice, wired to the coverage the list route reports. */}
      <ListCoverageNotice
        missingMajors={composition.coverage.missing_majors}
        missingClassYears={composition.coverage.missing_class_years}
      />

      <div
        data-slot="exercise-composition-grid"
        className="grid items-start gap-ce-4 md:gap-ce-5 lg:grid-cols-3"
      >
        {groups.map(({ counts, label }) =>
          narrow ? (
            <details key={counts.dimension} className="ce-card group min-w-0">
              <summary className="ce-type-label flex min-h-ce-target cursor-pointer list-none items-center justify-between gap-ce-3 px-ce-4 py-ce-2 text-ce-ink [&::-webkit-details-marker]:hidden">
                By {dimensionLabel(counts.dimension)}
                <ChevronDown
                  aria-hidden="true"
                  className="size-5 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none"
                />
              </summary>
              <div className="px-ce-4 pb-ce-4">
                <GroupTable counts={counts} label={label} captionHidden />
              </div>
            </details>
          ) : (
            <div key={counts.dimension} className="ce-card min-w-0 p-ce-4 md:p-ce-5">
              <GroupTable counts={counts} label={label} />
            </div>
          ),
        )}
      </div>

      <p className="ce-type-body ce-measure text-ce-ink" data-slot="exercise-unrankable">
        {unrankableProfileCount === 0
          ? "Everyone in this data file could be ranked for this event."
          : `${unrankableProfileCount} ${
              unrankableProfileCount === 1 ? "profile" : "profiles"
            } in this data file could not be ranked for this event, so nobody among them can be on the list.`}
      </p>

    </section>
  );
}

/**
 * One dimension's counts.
 *
 * Rows are the union of both maps' keys so a group that exists in the file and
 * has nobody on the list still has a row, showing a real 0 rather than
 * vanishing. A group with nobody in the file at all cannot occur — the server
 * builds `all_profiles` from the file — but the union is taken anyway rather
 * than assuming it.
 */
function GroupTable({
  counts,
  label = (value: string) => value,
  captionHidden = false,
}: {
  readonly counts: GroupCountsView;
  readonly label?: (value: string) => string;
  /** In a disclosure the summary already says "By major": keep the caption for screen readers only. */
  readonly captionHidden?: boolean;
}): React.JSX.Element {
  const groups = [
    ...new Set([...Object.keys(counts.all_profiles), ...Object.keys(counts.on_list)]),
  ];
  // The server sends class years in class order (Freshman to Senior); only majors are alphabetical.
  if (counts.dimension !== "class_year") groups.sort((a, b) => a.localeCompare(b));
  const dimension = dimensionLabel(counts.dimension);

  return (
    <div className="ce-scroll-x overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption
          className={
            captionHidden ? "sr-only" : "ce-type-h3 pb-ce-3 text-left text-ce-ink"
          }
        >
          By {dimension}
        </caption>
        <thead>
          <tr className="ce-type-meta bg-ce-surface-sunk font-semibold text-ce-ink">
            <th scope="col" className="rounded-l-ce-control px-ce-3 py-ce-2 first-letter:uppercase">
              {dimension}
            </th>
            <th scope="col" className="px-ce-3 py-ce-2 text-right">
              On this list
            </th>
            <th scope="col" className="rounded-r-ce-control px-ce-3 py-ce-2 text-right">
              In the whole data file
            </th>
          </tr>
        </thead>
        <tbody className="ce-type-body text-ce-ink">
          {groups.map((group) => (
            <tr key={group} className="border-b border-ce-line last:border-b-0">
              <th scope="row" className="px-ce-3 py-ce-2 font-normal">
                {label(group)}
              </th>
              <td className="ce-tabular px-ce-3 py-ce-2 text-right">
                {counts.on_list[group] ?? 0}
              </td>
              <td className="ce-tabular px-ce-3 py-ce-2 text-right">
                {counts.all_profiles[group] ?? 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
