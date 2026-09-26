/**
 * The results, as three panels and the people behind the team's own.
 *
 * Design spec §10: the response always carries the team's list and "email
 * everyone", and in round two the team's stored round one as well. The chart
 * (PR #162's `ExerciseResultsChart`) takes them in that left-to-right order,
 * which is the order the comparison is meant to be read in: what your list
 * did, what contacting all 300 did, what you did last time.
 *
 * **Names appear for the team's own panel only.** The results routes carry
 * profile *numbers* and counts, never names (PR #190). Owner decision of
 * 2026-09-21: the screen joins those numbers against `display_name` on the
 * ranked list the matching screen already fetches, and the "email everyone"
 * panel stays counts only. So a team can see who its own decision reached; the
 * 300-person comparison stays a number, which is the point of it.
 *
 * A number with no name in the list — possible when the list was rebuilt under
 * different weights since the run — renders as the profile number rather than
 * being dropped or shown as blank. Design spec §7's rule about absent
 * information is the same rule: say what is missing, do not fill it in.
 */
import * as React from "react";

import {
  ExerciseResultsChart,
  type ExerciseResultsSeries,
} from "./ExerciseResultsChart";
import type { ResultPanelView, ResultsView } from "../../../lib/exerciseClient";

/** `profile_no` → the name the ranked list gives it. */
export type NamesByProfileNo = ReadonlyMap<number, string>;

/** The three panels, in §10's reading order, for the chart. */
export function resultsSeries(results: ResultsView): ExerciseResultsSeries[] {
  const series: ExerciseResultsSeries[] = [
    panelSeries("Your team's list", results.team),
    panelSeries("If you emailed everyone", results.email_everyone),
  ];
  if (results.round_one !== null) {
    series.push(panelSeries("Your team, round one", results.round_one.team));
  }
  return series;
}

function panelSeries(label: string, panel: ResultPanelView): ExerciseResultsSeries {
  return {
    label,
    invited: panel.invited_count,
    signedUp: panel.signed_up_count,
    attended: panel.attended_count,
  };
}

export interface ResultPanelsProps {
  readonly results: ResultsView;
  /** Names for the team's own profile numbers; empty when the list is not loaded. */
  readonly names: NamesByProfileNo;
}

export function ResultPanels({ results, names }: ResultPanelsProps): React.JSX.Element {
  return (
    <div className="flex flex-col gap-8">
      <ExerciseResultsChart
        series={resultsSeries(results)}
        title={`What happened for ${results.event_name}`}
        caption={
          results.round_one === null
            ? "Your team's list beside contacting all 300."
            : "Your team's list, contacting all 300, and your team's first round."
        }
      />

      <section className="flex flex-col gap-4">
        <p
          className="text-2xl font-semibold text-slate-900 dark:text-slate-50"
          data-slot="exercise-seats-sentence"
        >
          {seatsSentence(
            {
              alreadyComing: results.existing_signups,
              added: results.team.attended_count,
              open: results.seats_empty,
            },
            "now",
          )}
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-slot="exercise-seats">
          <Figure label="Seats in the room" value={results.event_seats} />
          <Figure label="Already coming" value={results.existing_signups} />
          <Figure label="Added by your invitations" value={results.team.attended_count} />
          <Figure label="Seats still open" value={results.seats_empty} />
        </div>
      </section>

      {results.round_one === null ? null : (
        <section data-slot="exercise-round-one" className="flex flex-col gap-2">
          <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
            Your team's first round
          </h2>
          <p className="text-xl text-slate-700 dark:text-slate-200">
            {results.round_one.setting_name === null
              ? "Built without a saved setting."
              : `Built from your team's setting “${results.round_one.setting_name}”.`}{" "}
            {seatsSentence(
              {
                // Round one carries no `existing_signups` of its own: the case's
                // existing sign-ups are the same number for both events.
                alreadyComing: results.existing_signups,
                added: results.round_one.team.attended_count,
                open: results.round_one.seats_empty,
              },
              "then",
            )}
          </p>
        </section>
      )}

      <section className="flex flex-col gap-4" data-slot="exercise-team-people">
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
          The people on your team's list
        </h2>
        <PeopleList
          heading="Invited"
          profileNos={results.team.invited_profile_nos}
          names={names}
        />
        <PeopleList
          heading="Signed up"
          profileNos={results.team.signed_up_profile_nos}
          names={names}
        />
        <PeopleList
          heading="Attended"
          profileNos={results.team.attended_profile_nos}
          names={names}
        />
        <p className="text-xl text-slate-600 dark:text-slate-300">
          Contacting all 300 is shown as counts only.
        </p>
      </section>
    </div>
  );
}

/** The three numbers D8's sentence is built from, all read off the response. */
export interface SeatCounts {
  /** `existing_signups`: people coming before the team invited anyone. */
  readonly alreadyComing: number;
  /** The team panel's `attended_count`: people the team's list brought. */
  readonly added: number;
  /** `seats_empty`: chairs nobody fills. */
  readonly open: number;
}

/**
 * Empty seats as both groups, in words (wave-2 decision D8, Chau approved).
 *
 * "8 were already coming. Your invitations added 6. 46 seats are still open."
 * Showing both groups makes clear what the team's list changed, which a bare
 * seat count hides. `"then"` is for a round already behind the team.
 */
export function seatsSentence(counts: SeatCounts, tense: "now" | "then"): string {
  const coming = alreadyComing(counts.alreadyComing);
  const added = `Your invitations added ${counts.added === 0 ? "nobody" : counts.added}.`;
  return `${coming} ${added} ${openSeats(counts.open, tense)}`;
}

function alreadyComing(count: number): string {
  if (count === 0) {
    return "Nobody was already coming.";
  }
  return `${count} ${count === 1 ? "was" : "were"} already coming.`;
}

function openSeats(open: number, tense: "now" | "then"): string {
  if (open === 0) {
    return tense === "now" ? "Every seat is taken." : "Every seat was taken.";
  }
  const verbs = tense === "now" ? { one: "is", many: "are" } : { one: "was", many: "were" };
  return open === 1 ? `1 seat ${verbs.one} still open.` : `${open} seats ${verbs.many} still open.`;
}

function Figure({
  label,
  value,
}: {
  readonly label: string;
  readonly value: number;
}): React.JSX.Element {
  return (
    <div className="rounded-lg border-2 border-slate-300 px-4 py-3 dark:border-slate-600">
      <p className="text-lg text-slate-600 dark:text-slate-300">{label}</p>
      <p className="text-4xl font-bold text-slate-900 dark:text-slate-50">{value}</p>
    </div>
  );
}

function PeopleList({
  heading,
  profileNos,
  names,
}: {
  readonly heading: string;
  readonly profileNos: readonly number[];
  readonly names: NamesByProfileNo;
}): React.JSX.Element {
  return (
    <div>
      <h3 className="text-2xl font-semibold text-slate-900 dark:text-slate-50">
        {heading} ({profileNos.length})
      </h3>
      {profileNos.length === 0 ? (
        <p className="text-xl text-slate-600 dark:text-slate-300">Nobody.</p>
      ) : (
        <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xl text-slate-800 dark:text-slate-100">
          {profileNos.map((profileNo) => (
            <li key={profileNo}>
              {/* The number itself when the list on screen does not name it. */}
              {names.get(profileNo) ?? `Profile ${profileNo}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
