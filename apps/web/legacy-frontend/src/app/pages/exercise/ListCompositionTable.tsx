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
 * - **`unlisted_class_years`** — years in the file that the server's class-year
 *   order does not name. With Ann's four years (2026-09-24) this is empty for
 *   her file; a dataset stored earlier may still carry one. It is shown as what
 *   the server said, without a claim about why.
 *
 * No vocabulary is written here. Majors and years are keys of the maps the
 * server sent, rendered as the file spells them. The vocabularies are closed
 * by Ann's workbook of 2026-09-24, but the server owns them, not this screen.
 */
import * as React from "react";

import type { GroupCountsView, ListCompositionView } from "../../../lib/exerciseClient";
// The extension is explicit: `ListCoverageNotice.tsx` and its helper
// `listCoverageNotice.ts` differ only in casing, which an extensionless
// specifier cannot tell apart on a case-insensitive filesystem (TS1149).
import { ListCoverageNotice } from "./ListCoverageNotice.tsx";
import { useIsNarrow } from "./exerciseUi";
import { dimensionLabel, markerLabel } from "./markers";

export interface ListCompositionTableProps {
  readonly composition: ListCompositionView;
  readonly unrankableProfileCount: number;
  readonly unlistedClassYears: readonly string[];
  /**
   * The matching screen shows the coverage notice at the top of the list
   * card, where the Stitch mock-up puts it, so it asks this section not to
   * repeat it. Standalone use keeps it here.
   */
  readonly showCoverageNotice?: boolean;
}

export function ListCompositionTable({
  composition,
  unrankableProfileCount,
  unlistedClassYears,
  showCoverageNotice = true,
}: ListCompositionTableProps): React.JSX.Element {
  const narrow = useIsNarrow();
  const groups = [
    { counts: composition.by_major, label: undefined },
    { counts: composition.by_class_year, label: undefined },
    { counts: composition.by_marker, label: markerLabel },
  ];
  return (
    <section data-slot="exercise-list-composition" className="flex flex-col gap-4">
      <h2 className="ce-h2 text-ce-ink">Who is on the list</h2>

      {/* PR #161's one-line notice, wired to the coverage the list route reports. */}
      {showCoverageNotice ? (
        <ListCoverageNotice
          missingMajors={composition.coverage.missing_majors}
          missingClassYears={composition.coverage.missing_class_years}
        />
      ) : null}

      {/*
        Three small tables in a row on desktop (DESIGN.md §6.9), each its own
        card. On a phone each folds behind a disclosure named for its table.
      */}
      <div className="grid items-start gap-4 lg:grid-cols-3 lg:gap-6">
        {groups.map(({ counts, label }) =>
          narrow ? (
            <details key={counts.dimension} className="ce-card p-4">
              <summary className="ce-h3 cursor-pointer text-ce-ink">
                By {dimensionLabel(counts.dimension)}
              </summary>
              <GroupTable counts={counts} label={label} captionHidden />
            </details>
          ) : (
            <div key={counts.dimension} className="ce-card min-w-0 p-5 md:p-6">
              <GroupTable counts={counts} label={label} />
            </div>
          ),
        )}
      </div>

      <p className="ce-body text-ce-ink" data-slot="exercise-unrankable">
        {unrankableProfileCount === 0
          ? "Everyone in this data file could be ranked for this event."
          : `${unrankableProfileCount} ${
              unrankableProfileCount === 1 ? "profile" : "profiles"
            } in this data file could not be ranked for this event, so nobody among them can be on the list.`}
      </p>

      <p className="ce-body text-ce-ink" data-slot="exercise-unlisted-years">
        {unlistedClassYears.length === 0
          ? "Every year in this data file has somebody on the list."
          : `Years with nobody on the list: ${unlistedClassYears.join(", ")}.`}
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
 *
 * Plain tabular numerals, right-aligned; no paired bars, which would read as a
 * share (§6.9). A 0 on the list is in ink like any other count, not muted.
 */
function GroupTable({
  counts,
  label = (value: string) => value,
  captionHidden = false,
}: {
  readonly counts: GroupCountsView;
  readonly label?: (value: string) => string;
  readonly captionHidden?: boolean;
}): React.JSX.Element {
  const groups = [
    ...new Set([...Object.keys(counts.all_profiles), ...Object.keys(counts.on_list)]),
  ].sort((a, b) => a.localeCompare(b));
  const name = dimensionLabel(counts.dimension);

  return (
    <div className="ce-scroll overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className={captionHidden ? "sr-only" : "ce-h3 pb-3 text-left text-ce-ink"}>
          By {name}
        </caption>
        <thead>
          <tr className="ce-label bg-ce-sunk text-ce-ink">
            <th scope="col" className="rounded-l-[10px] px-3 py-2">
              {name.charAt(0).toUpperCase() + name.slice(1)}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              On this list
            </th>
            <th scope="col" className="rounded-r-[10px] px-3 py-2 text-right">
              In the whole data file
            </th>
          </tr>
        </thead>
        <tbody className="ce-body ce-num">
          {groups.map((group) => (
            <tr key={group} className="border-b border-ce-line">
              <th scope="row" className="px-3 py-2 font-normal text-ce-ink">
                {label(group)}
              </th>
              <td className="px-3 py-2 text-right text-ce-ink">{counts.on_list[group] ?? 0}</td>
              <td className="px-3 py-2 text-right text-ce-ink">{counts.all_profiles[group] ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
