/**
 * The results, as three panels and the people behind the team's own.
 *
 * Design spec §10: the response always carries the team's list and "email
 * everyone", and in round two the team's stored round one as well. The chart
 * (PR #162's `ExerciseResultsChart`) takes them in that left-to-right order,
 * which is the order the comparison is meant to be read in: what your list
 * did, what contacting all 300 did, what you did last time.
 *
 * **Names appear for the team's own panel only**, and they are the run's own
 * record (issue #271). The run stores the names its list showed when it was
 * made (`ResultsView.invited_profiles`), and this screen reads them from
 * there — see {@link namesFromRun}. It used to join the panel's numbers
 * against the ranked list the run's saved setting builds (owner decision,
 * 2026-09-21), which named nobody once that setting was deleted, and named
 * the wrong people once it was saved again. The "email everyone" panel stays
 * counts only. So a team can see who its own decision reached; the 300-person
 * comparison stays a number, which is the point of it.
 *
 * A number the run's record does not name — a run stored before names were
 * kept with the run — renders as the profile number rather than being dropped
 * or shown as blank. Design spec §7's rule about absent information is the
 * same rule: say what is missing, do not fill it in.
 */
import * as React from "react";

import {
  ExerciseResultsChart,
  type ExerciseResultsSeries,
} from "./ExerciseResultsChart";
import type { ResultPanelView, ResultsView } from "../../../lib/exerciseClient";
import { RoundJourneyArt } from "./resultsArt";
import { ResultsReveal } from "./ResultsReveal";

/** `profile_no` → the name the run stored for it. */
export type NamesByProfileNo = ReadonlyMap<number, string>;

/**
 * The names a run kept of the people it invited, by profile number.
 *
 * Signed-up and attended are subsets of invited, so this one map names all
 * three of the team's lists. Empty for a run stored before names were kept.
 */
export function namesFromRun(results: ResultsView): NamesByProfileNo {
  return new Map(
    (results.invited_profiles ?? []).map((entry) => [entry.profile_no, entry.display_name]),
  );
}

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
  /**
   * Names for the team's own profile numbers. Left out, they are read from
   * the run's own record ({@link namesFromRun}), which is what a screen wants.
   */
  readonly names?: NamesByProfileNo;
  /**
   * Play the seat fill (`ce-seat-fill`, DESIGN.md §5.1). True only on the first
   * render after this screen's own run succeeded; a later visit shows the
   * final state.
   */
  readonly reveal?: boolean;
}

/**
 * DESIGN.md §7.8 / §7.10 order: (round two's journey strip), the room and the
 * sentence, the chart, (round one's line), the people.
 */
export function ResultPanels({
  results,
  names: given,
  reveal = false,
}: ResultPanelsProps): React.JSX.Element {
  const names = React.useMemo(() => given ?? namesFromRun(results), [given, results]);
  return (
    <div className="flex flex-col gap-ce-6 md:gap-ce-7">
      {results.round_one === null ? null : (
        <div data-slot="exercise-round-journey" className="text-ce-primary">
          <RoundJourneyArt className="h-auto w-[120px] md:w-[160px]" />
        </div>
      )}

      <ResultsReveal
        eventSeats={results.event_seats}
        alreadyComing={results.existing_signups}
        added={results.team.attended_count}
        open={results.seats_empty}
        reveal={reveal}
        sentence={seatsSentence(
          {
            alreadyComing: results.existing_signups,
            added: results.team.attended_count,
            open: results.seats_empty,
          },
          "now",
        )}
      />

      <ExerciseResultsChart
        variant="exercise"
        series={resultsSeries(results)}
        title={`What happened for ${results.event_name}`}
        caption={
          results.round_one === null
            ? "Your team's list beside contacting all 300."
            : "Your team's list, contacting all 300, and your team's first round."
        }
      />

      {results.round_one === null ? null : (
        <section
          data-slot="exercise-round-one"
          className="flex flex-col gap-ce-2 border-t border-ce-line pt-ce-5"
        >
          <h2 className="ce-type-h2 text-ce-ink">Your team's first round</h2>
          <p className="ce-type-body ce-measure text-ce-ink-muted">
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

      <section
        className="ce-card flex flex-col gap-ce-5 p-ce-4 md:p-ce-6"
        data-slot="exercise-team-people"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-x-ce-5 gap-y-ce-2 border-b border-ce-line pb-ce-4">
          <h2 className="ce-type-h2 text-ce-ink">The people on your team's list</h2>
          <p className="ce-type-meta text-ce-ink-muted">
            Contacting all 300 is shown as counts only.
          </p>
        </div>
        <div className="grid gap-ce-5 md:grid-cols-3">
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
        </div>
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

function PeopleList({
  heading,
  profileNos,
  names,
}: {
  readonly heading: string;
  readonly profileNos: readonly number[];
  readonly names: NamesByProfileNo;
}): React.JSX.Element {
  // Issue #269: read top-down like the ranked list. `names` is in the run's
  // rank order; numbers it does not name (older runs) follow, by number.
  const place = new Map([...names.keys()].map((no, index) => [no, index]));
  const ordered = [...profileNos].sort(
    (a, b) => (place.get(a) ?? Infinity) - (place.get(b) ?? Infinity) || a - b,
  );
  return (
    <div className="flex min-w-0 flex-col gap-ce-3">
      <h3 className="ce-type-label text-ce-ink">
        {heading} <span className="ce-tabular text-ce-ink-muted">({profileNos.length})</span>
      </h3>
      {profileNos.length === 0 ? (
        <p className="ce-type-body text-ce-ink-muted">Nobody.</p>
      ) : (
        <ul className="flex flex-wrap gap-ce-2">
          {ordered.map((profileNo) => (
            <li
              key={profileNo}
              data-slot="exercise-person-chip"
              className="ce-type-meta rounded-ce-pill bg-ce-surface-sunk px-ce-3 py-ce-1 text-ce-ink"
            >
              {/* The number itself when the run's record does not name it. */}
              {names.get(profileNo) ?? `Profile ${profileNo}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
