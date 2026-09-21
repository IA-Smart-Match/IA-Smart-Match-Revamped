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
 * - **`unlisted_class_years`** — every year in the file that has nobody on the
 *   list. PR #188 notes that class-year ordering is withdrawn
 *   (`PLACEHOLDER_CLASS_YEAR_RANK` is empty), so this list is currently every
 *   year in the file. It is shown as what the server said, without a claim
 *   about why.
 *
 * No vocabulary is written here. Majors and years are keys of the maps the
 * server sent, rendered as the file spells them (OQ-CE-01 is open).
 */
import * as React from "react";

import type { GroupCountsView, ListCompositionView } from "../../../lib/exerciseClient";
// The extension is explicit: `ListCoverageNotice.tsx` and its helper
// `listCoverageNotice.ts` differ only in casing, which an extensionless
// specifier cannot tell apart on a case-insensitive filesystem (TS1149).
import { ListCoverageNotice } from "./ListCoverageNotice.tsx";
import { dimensionLabel, markerLabel } from "./markers";

export interface ListCompositionTableProps {
  readonly composition: ListCompositionView;
  readonly unrankableProfileCount: number;
  readonly unlistedClassYears: readonly string[];
}

export function ListCompositionTable({
  composition,
  unrankableProfileCount,
  unlistedClassYears,
}: ListCompositionTableProps): React.JSX.Element {
  return (
    <section data-slot="exercise-list-composition" className="flex flex-col gap-4">
      <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
        Who is on the list
      </h2>

      {/* PR #161's one-line notice, wired to the coverage the list route reports. */}
      <ListCoverageNotice
        missingMajors={composition.coverage.missing_majors}
        missingClassYears={composition.coverage.missing_class_years}
      />

      <div className="flex flex-col gap-6">
        <GroupTable counts={composition.by_major} />
        <GroupTable counts={composition.by_class_year} />
        <GroupTable counts={composition.by_marker} label={markerLabel} />
      </div>

      <p className="text-xl text-slate-700 dark:text-slate-200" data-slot="exercise-unrankable">
        {unrankableProfileCount === 0
          ? "Everyone in this data file could be ranked for this event."
          : `${unrankableProfileCount} ${
              unrankableProfileCount === 1 ? "profile" : "profiles"
            } in this data file could not be ranked for this event, so nobody among them can be on the list.`}
      </p>

      <p className="text-xl text-slate-700 dark:text-slate-200" data-slot="exercise-unlisted-years">
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
 */
function GroupTable({
  counts,
  label = (value: string) => value,
}: {
  readonly counts: GroupCountsView;
  readonly label?: (value: string) => string;
}): React.JSX.Element {
  const groups = [
    ...new Set([...Object.keys(counts.all_profiles), ...Object.keys(counts.on_list)]),
  ].sort((a, b) => a.localeCompare(b));

  return (
    <table className="w-full border-collapse text-left text-xl">
      <caption className="pb-2 text-left text-2xl font-semibold text-slate-900 dark:text-slate-50">
        By {dimensionLabel(counts.dimension)}
      </caption>
      <thead>
        <tr className="border-b-2 border-slate-400 text-lg tracking-wide uppercase">
          <th scope="col" className="py-2 pr-4">
            {dimensionLabel(counts.dimension)}
          </th>
          <th scope="col" className="py-2 pr-4">
            On this list
          </th>
          <th scope="col" className="py-2">
            In the whole data file
          </th>
        </tr>
      </thead>
      <tbody>
        {groups.map((group) => (
          <tr key={group} className="border-b border-slate-200 dark:border-slate-700">
            <th scope="row" className="py-2 pr-4 font-normal">
              {label(group)}
            </th>
            <td className="py-2 pr-4">{counts.on_list[group] ?? 0}</td>
            <td className="py-2">{counts.all_profiles[group] ?? 0}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
