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
import { RoundJourneyArt } from "./exerciseArt";
import { useIsNarrow } from "./exerciseUi";
import { SeatReveal } from "./SeatReveal";

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
  /**
   * Play the seat fill (`ce-seat-fill`). Only the first render after "Run
   * results for this event" succeeds passes `true`; every later visit shows
   * the final state (DESIGN.md §5.1).
   */
  readonly reveal?: boolean;
}

export function ResultPanels({
  results,
  names,
  reveal = false,
}: ResultPanelsProps): React.JSX.Element {
  const narrow = useIsNarrow();
  const roundOne = results.round_one;
  return (
    <div className="flex flex-col gap-8 md:gap-12">
      {roundOne === null ? null : (
        // §7.10: the round strip at the top of round two's results.
        <p className="ce-label flex items-center gap-3 text-ce-ink">
          <RoundJourneyArt className="h-8 w-16 shrink-0 text-ce-primary" />
          Round 1 → Round 2 · {results.event_name}
        </p>
      )}

      <SeatReveal
        reveal={reveal}
        counts={{
          seats: results.event_seats,
          alreadyComing: results.existing_signups,
          added: results.team.attended_count,
          open: results.seats_empty,
        }}
        sentences={seatsSentence(
          {
            alreadyComing: results.existing_signups,
            added: results.team.attended_count,
            open: results.seats_empty,
          },
          "now",
        )}
        footnote={
          roundOne === null
            ? undefined
            : `In round one your team's list left ${roundOne.seats_empty} ${
                roundOne.seats_empty === 1 ? "seat" : "seats"
              } empty.`
        }
      />

      <div className="ce-card p-4 md:p-6">
        <ExerciseResultsChart
          variant="exercise"
          horizontal={narrow}
          series={resultsSeries(results)}
          title={`What happened for ${results.event_name}`}
          caption={
            roundOne === null
              ? "Your team's list beside contacting all 300."
              : "Your team's list, contacting all 300, and your team's first round."
          }
        />
      </div>

      {roundOne === null ? null : (
        <section data-slot="exercise-round-one" className="ce-card flex flex-col gap-2 p-5 md:p-6">
          <h2 className="ce-h3 text-ce-ink">Your team's first round</h2>
          <p className="ce-body text-ce-ink">
            {roundOne.setting_name === null
              ? "Built without a saved setting."
              : `Built from your team's setting “${roundOne.setting_name}”.`}{" "}
            {seatsSentence(
              {
                // Round one carries no `existing_signups` of its own: the case's
                // existing sign-ups are the same number for both events.
                alreadyComing: results.existing_signups,
                added: roundOne.team.attended_count,
                open: roundOne.seats_empty,
              },
              "then",
            )}
          </p>
        </section>
      )}

      <section className="ce-card flex flex-col gap-5 p-5 md:p-6" data-slot="exercise-team-people">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-ce-line pb-4">
          <h2 className="ce-h2 text-ce-ink">The people on your team's list</h2>
          <p className="ce-meta text-ce-muted">Contacting all 300 is shown as counts only.</p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          <PeopleList heading="Invited" profileNos={results.team.invited_profile_nos} names={names} />
          <PeopleList
            heading="Signed up"
            profileNos={results.team.signed_up_profile_nos}
            names={names}
          />
          <PeopleList
            heading="Attended"
            profileNos={results.team.attended_profile_nos}
            names={names}
            tint
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

/** One group of people as name chips (DESIGN.md §6.17). The heading carries the count. */
function PeopleList({
  heading,
  profileNos,
  names,
  tint = false,
}: {
  readonly heading: string;
  readonly profileNos: readonly number[];
  readonly names: NamesByProfileNo;
  readonly tint?: boolean;
}): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h3 className="ce-label text-ce-ink">
        {heading} <span className="ce-num font-normal text-ce-muted">({profileNos.length})</span>
      </h3>
      {profileNos.length === 0 ? (
        <p className="ce-body text-ce-muted">Nobody.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {profileNos.map((profileNo) => (
            <li
              key={profileNo}
              className={`ce-chip py-1 ${tint ? "bg-ce-primary-tint text-ce-primary-tint-ink" : "bg-ce-sunk text-ce-ink"}`}
            >
              {/* The number itself when the list on screen does not name it. */}
              {names.get(profileNo) ?? `Profile ${profileNo}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
