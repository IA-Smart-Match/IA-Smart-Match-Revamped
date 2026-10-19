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
 * the wrong people once it was saved again. The "mass email alone" panel stays
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

/**
 * Profile numbers in the run's rank order (issue #269). A number with no
 * stored rank goes last, keeping its original order (Array sort is stable).
 */
export function inRankOrder(results: ResultsView, profileNos: readonly number[]): number[] {
  const rankOf = new Map(
    (results.invited_profiles ?? []).map((entry) => [entry.profile_no, entry.rank]),
  );
  const key = (no: number): number => rankOf.get(no) ?? Number.POSITIVE_INFINITY;
  return [...profileNos].sort((a, b) => (key(a) === key(b) ? 0 : key(a) - key(b)));
}

/** The three panels, in §10's reading order, for the chart. */
export function resultsSeries(
  results: ResultsView,
  roundOneName: string | null = null,
): ExerciseResultsSeries[] {
  const series: ExerciseResultsSeries[] = [
    panelSeries("Mass email alone", results.email_everyone),
    unionSeries(`Mass email plus your ${results.team.invited_count} CBACH emails`, results),
  ];
  if (results.round_one !== null) {
    series.push(panelSeries(
        roundOneName === null || roundOneName === ""
          ? "Your team, round one"
          : `Your team, ${roundOneName} (round one)`,
        results.round_one.email_everyone === undefined
          ? results.round_one.team
          : unionPanel({ team: results.round_one.team, email_everyone: results.round_one.email_everyone, existing_signups: results.existing_signups }),
      ));
  }
  return series;
}

/** Mass email plus the list: what the dark bar shows, never the list's own panel alone. */
function unionPanel(round: RoundPanels): ResultPanelView {
  const { withList } = liftCounts(round);
  const attended = round.email_everyone.attended_profile_nos.length + seatCountsFor(round).added;
  return {
    ...round.team,
    signed_up_count: withList,
    attended_count: attended,
  };
}

function unionSeries(label: string, round: RoundPanels): ExerciseResultsSeries {
  return panelSeries(label, unionPanel(round));
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
  /** The first round's event name, for the chart's round-one label. */
  readonly roundOneName?: string | null;
}

/**
 * DESIGN.md §7.8 / §7.10 order: (round two's journey strip), the room and the
 * sentence, the chart, (round one's line), the people.
 */
export function ResultPanels({
  results,
  names: given,
  reveal = false,
  roundOneName = null,
}: ResultPanelsProps): React.JSX.Element {
  const names = React.useMemo(() => given ?? namesFromRun(results), [given, results]);
  const seatGroups = seatCountsFor(results);
  return (
    <div className="flex flex-col gap-ce-6 md:gap-ce-7">
      {results.round_one === null ? null : (
        <div data-slot="exercise-round-journey" className="text-ce-primary">
          <RoundJourneyArt className="h-auto w-[120px] md:w-[160px]" />
        </div>
      )}

      <ResultsReveal
        eventSeats={results.event_seats}
        alreadyComing={seatGroups.alreadyComing}
        added={seatGroups.added}
        open={results.seats_empty}
        reveal={reveal}
        sentence={seatsSentence(
          {
            alreadyComing: seatGroups.alreadyComing,
            added: seatGroups.added,
            open: results.seats_empty,
          },
          "now",
        )}
      />

      <LiftLine results={results} />

      <ExerciseResultsChart
        variant="exercise"
        series={resultsSeries(results, roundOneName)}
        title={`What happened for ${results.event_name}`}
        caption={
          results.round_one === null
            ? "Light bar: mass email alone. Dark bar: mass email plus your CBACH emails."
            : // Wording is ours: Ann wrote the round-one-only caption.
              "Light bar: mass email alone. Dark bar: mass email plus your CBACH emails. Hatched bar: your team's first round."
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
            {recapSentence(results)}
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
            The mass email alone is shown as counts only.
          </p>
        </div>
        <p className="ce-type-meta text-ce-ink-muted" data-slot="exercise-run-record">
          {runRecordLine(results)}
        </p>
        <div className="grid gap-ce-5 md:grid-cols-3">
          <PeopleList
            heading="Invited"
            profileNos={inRankOrder(results, results.team.invited_profile_nos)}
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

/**
 * The round-one recap, from the same helpers and wording as the round-one
 * screen. Falls back to the old counts-only sentence for a server that does
 * not send the round's mass-email panel.
 */
function recapSentence(results: ResultsView): string {
  const one = results.round_one;
  if (one === null) return "";
  if (one.email_everyone === undefined) {
    return seatsSentence(
      { alreadyComing: one.existing_attended ?? results.existing_signups, open: one.seats_empty },
      "then",
    );
  }
  const panels: RoundPanels = {
    team: one.team,
    email_everyone: one.email_everyone,
    existing_signups: results.existing_signups,
    existing_attended: one.existing_attended,
  };
  const seats = seatCountsFor(panels);
  return `${liftSentence(panels)} ${listSignupsSentence(panels)} ${seatsSentence(
    { alreadyComing: seats.alreadyComing, added: seats.added, open: one.seats_empty },
    "then",
  )}`;
}

/** Says which list this stored run used; later setting or limit changes do not re-run it. */
export function runRecordLine(results: ResultsView): string {
  const n = results.team.invited_count;
  const from =
    results.setting_name === null
      ? "a list built without a saved setting"
      : `your setting “${results.setting_name}”`;
  return `These results are saved from ${from}, with ${n} invited. Changing your setting or the name limit now will not change them.`;
}

/**
 * `email_everyone` is the mass email alone; `team` is the mass email plus the
 * team's CBACH emails. K counts team sign-ups the mass email alone did not get.
 */
export function liftCounts(
  results: RoundPanels,
): { mass: number; withList: number; added: number; own: number; anyway: number } {
  const mass = new Set(results.email_everyone.signed_up_profile_nos);
  const own = results.team.signed_up_profile_nos;
  const added = own.filter((n) => !mass.has(n)).length;
  return { mass: mass.size, withList: mass.size + added, added, own: own.length, anyway: own.length - added };
}

/** What both the live screen and the round-one recap read their numbers from. */
export interface RoundPanels {
  readonly team: ResultPanelView;
  readonly email_everyone: ResultPanelView;
  readonly existing_signups: number;
  readonly existing_attended?: number;
}

/**
 * The two seat groups of the current round. The team panel is the mass email
 * plus the CBACH emails, so its attendees include everyone the mass email alone
 * would bring (Ann Wang 2026-10-10, Q2). Those people were coming anyway:
 * "already coming" is the pre-registered students who came plus the mass email's attendees,
 * and "added" is the team's attendees the mass email missed.
 */
export function seatCountsFor(results: RoundPanels): { alreadyComing: number; added: number } {
  const mass = new Set(results.email_everyone.attended_profile_nos);
  const added = results.team.attended_profile_nos.filter((n) => !mass.has(n)).length;
  return { alreadyComing: (results.existing_attended ?? results.existing_signups) + mass.size, added };
}

const plural = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`;

/** Ann Wang 2026-10-16 results item 1: both measures, each labeled. */
export function liftSentence(results: RoundPanels): string {
  const { added } = liftCounts(results);
  const { added: came } = seatCountsFor(results);
  return `Your list brought ${plural(added, "extra sign-up", "extra sign-ups")}; ${came} of them came.`;
}

/** Ann Wang 2026-10-16 results item 2: why the list's own sign-ups differ from "added". */
export function listSignupsSentence(results: RoundPanels): string {
  const { own, anyway, added } = liftCounts(results);
  if (own === 0) {
    return "Nobody on your list signed up, so your list added 0.";
  }
  const who = own === 1 ? "1 person on your list signed up." : `${own} people on your list signed up.`;
  return `${who} ${anyway} of them would have signed up from the mass email anyway, so your list added ${added}.`;
}

function LiftLine({ results }: { readonly results: ResultsView }): React.JSX.Element {
  return (
    <section data-slot="exercise-lift" className="flex flex-col gap-ce-2">
      <p className="ce-type-h2 text-ce-ink">{liftSentence(results)}</p>
      <p className="ce-type-body ce-measure text-ce-ink" data-slot="exercise-list-signups">
        {listSignupsSentence(results)}
      </p>
      <p className="ce-type-body ce-measure text-ce-ink-muted">
        Each team's numbers include its own luck. Look at your gap over the mass email, not just the raw number.
      </p>
    </section>
  );
}

/** The three numbers D8's sentence is built from, all read off the response. */
export interface SeatCounts {
  /** `existing_attended` plus the mass email's attendees: coming before the team's emails. */
  readonly alreadyComing: number;
  /** People the team's list brought on top of the mass email alone (see {@link seatCountsFor}). */
  readonly added?: number;
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
  const added =
    counts.added === undefined
      ? ""
      : `${counts.added === 0 ? "Nobody" : counts.added} came because of your list. `;
  return `${coming} ${added}${openSeats(counts.open, tense)}`;
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
  return (
    <div className="flex min-w-0 flex-col gap-ce-3">
      <h3 className="ce-type-label text-ce-ink">
        {heading} <span className="ce-tabular text-ce-ink-muted">({profileNos.length})</span>
      </h3>
      {profileNos.length === 0 ? (
        <p className="ce-type-body text-ce-ink-muted">Nobody.</p>
      ) : (
        <ul className="flex flex-wrap gap-ce-2">
          {profileNos.map((profileNo) => (
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
