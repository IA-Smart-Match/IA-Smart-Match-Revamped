/**
 * One team's whole work, opened on the instructor page (issue #319).
 *
 * Ann's revisions of 2026-10-02, area 2: the instructor leads the discussion
 * from this page, and "Open this team's work" showed only the names of a
 * team's saved settings. So, for the team:
 *
 * - the way of asking it chose, and whether it has asked, with the time;
 * - each saved setting with its four numbers, in Ann's words for the four
 *   factors (`factor_labels`), and the list of names that setting builds;
 * - each results run: the setting it was built from, the four numbers it
 *   used, and who was invited, who signed up and who attended.
 *
 * **A saved setting's list is live; a run's list is the run's own record.**
 * The run stores the names its list showed when it ran, so they stay as they
 * were after the team edits or deletes that setting — and this view says so
 * when the setting has been deleted since. A run stored before names were kept
 * shows its counts and says the names were not kept; nothing is filled in.
 *
 * The four numbers are the team's own stated weights, never a score. Markers
 * are in words (`markerLabel`), never colour alone. Lists are real lists and
 * the numbers a `dl`, so the view reads at projector size and to a screen
 * reader (DESIGN.md §8). Every name is fictional.
 *
 * Sits in a sunk well inside the Teams card, not in a second card (§10).
 */
import * as React from "react";

import {
  EXERCISE_FACTOR_KEYS,
  type InstructorSavedSettingView,
  type InvitedProfileView,
  type ResultRunView,
  type TeamDetailView,
} from "../../../lib/exerciseClient";
import { cn } from "../../components/ui/utils";
import { askingChoiceLabel } from "./askingChoices";
import { formatWeight } from "./desk";
import { clockTime } from "./exerciseTime";
import { INSTRUCTOR_WELL } from "./instructorUi";
import { markerLabel } from "./markers";

/** Ann's words for each factor key, as the server sent them. */
type FactorLabels = Readonly<Record<string, string>>;

export function TeamDetail({ detail }: { readonly detail: TeamDetailView }): React.JSX.Element {
  const labels: FactorLabels = detail.factor_labels ?? {};
  const settings = detail.saved_settings ?? [];
  const runs = detail.result_runs ?? [];
  return (
    <div
      data-slot="exercise-instructor-team-detail"
      className={cn(INSTRUCTOR_WELL, "ce-fade-rise flex flex-col gap-ce-5")}
    >
      {/* §8.6: the opened view is announced once, by its first line. */}
      <p role="status" className="ce-type-body text-ce-ink">
        {askingSentence(detail)}
      </p>

      <section className="flex flex-col gap-ce-3">
        <h4 className="ce-type-label text-ce-ink">Saved settings</h4>
        {settings.length === 0 ? (
          <p className="ce-type-body text-ce-ink-muted">No saved settings yet.</p>
        ) : (
          <ul className="flex flex-col gap-ce-4">
            {settings.map((setting) => (
              <li key={`${setting.event_key}-${setting.name}`}>
                <SavedSetting setting={setting} labels={labels} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-ce-3">
        <h4 className="ce-type-label text-ce-ink">Results</h4>
        {runs.length === 0 ? (
          <p className="ce-type-body text-ce-ink-muted">No results run yet.</p>
        ) : (
          <ul className="flex flex-col gap-ce-4">
            {runs.map((run) => (
              <li key={`${run.event_key}-${run.round}`}>
                <ResultRun run={run} labels={labels} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * "Way of asking: A small reward. Asked at 10:42 AM." — the page's own words
 * for the refresh ("asked"), with the time it was done.
 */
function askingSentence(detail: TeamDetailView): string {
  const way =
    detail.asking_choice === null || detail.asking_choice === undefined
      ? "Has not picked a way of asking."
      : `Way of asking: ${askingChoiceLabel(detail.asking_choice)}`;
  if (detail.refreshed_at === null || detail.refreshed_at === undefined) {
    return `${way} Has not asked yet.`;
  }
  const at = clockTime(detail.refreshed_at);
  return at === null ? `${way} Has already asked.` : `${way} Asked at ${at}.`;
}

function SavedSetting({
  setting,
  labels,
}: {
  readonly setting: InstructorSavedSettingView;
  readonly labels: FactorLabels;
}): React.JSX.Element {
  const invited = setting.invited ?? [];
  return (
    <article className="flex flex-col gap-ce-2 border-t border-ce-line pt-ce-3">
      <div className="flex flex-col gap-ce-1">
        <h5 className="ce-type-h3 break-words text-ce-ink">{setting.name}</h5>
        <p className="ce-type-meta text-ce-ink-muted">
          {eventLine(setting.round ?? null, setting.event_name ?? setting.event_key)}
        </p>
      </div>
      <FourNumbers weights={setting.weights ?? {}} labels={labels} />
      <NameList
        heading="Its list"
        count={invited.length}
        entries={invited}
        emptySentence="Nobody on this list."
      />
    </article>
  );
}

function ResultRun({
  run,
  labels,
}: {
  readonly run: ResultRunView;
  readonly labels: FactorLabels;
}): React.JSX.Element {
  return (
    <article className="flex flex-col gap-ce-2 border-t border-ce-line pt-ce-3">
      <div className="flex flex-col gap-ce-1">
        <h5 className="ce-type-h3 break-words text-ce-ink">
          {eventLine(run.round, run.event_name ?? run.event_key)}
        </h5>
        <p className="ce-type-meta text-ce-ink-muted">{settingSentence(run)}</p>
      </div>
      {run.setting_weights === null || run.setting_weights === undefined ? null : (
        <FourNumbers weights={run.setting_weights} labels={labels} />
      )}
      {/* D8: open seats in words, not "N seats empty". */}
      <p className="ce-type-body ce-tabular text-ce-ink">
        Invited {run.invited_count}, signed up {run.signed_up_count}, attended{" "}
        {run.attended_count}. {run.seats_empty} {run.seats_empty === 1 ? "seat is" : "seats are"}{" "}
        still open.
      </p>
      <NameList heading="Invited" count={run.invited_count} entries={run.invited ?? []} />
      <NameList heading="Signed up" count={run.signed_up_count} entries={run.signed_up ?? []} />
      <NameList heading="Attended" count={run.attended_count} entries={run.attended ?? []} />
    </article>
  );
}

/** "Round 1 · Northline Analytics", or the event alone when it is not a round. */
function eventLine(round: number | null, eventName: string): string {
  return round === null ? eventName : `Round ${round} · ${eventName}`;
}

/** Which setting a run's list came from, and whether it is still there. */
function settingSentence(run: ResultRunView): string {
  if (run.setting_name === null) {
    return "Built without a saved setting.";
  }
  const from = `Built from the setting “${run.setting_name}”.`;
  return run.setting_deleted === true
    ? `${from} The team has deleted that setting since; this run is unchanged.`
    : from;
}

/** The four weights under Ann's words; a key with no words to hand is left out. */
function FourNumbers({
  weights,
  labels,
}: {
  readonly weights: Readonly<Record<string, number>>;
  readonly labels: FactorLabels;
}): React.JSX.Element | null {
  const rows = EXERCISE_FACTOR_KEYS.flatMap((key) => {
    const label = labels[key];
    const weight = weights[key];
    return typeof label === "string" && typeof weight === "number" ? [{ key, label, weight }] : [];
  });
  if (rows.length === 0) {
    return null;
  }
  return (
    <dl
      data-slot="exercise-instructor-four-numbers"
      className="grid gap-x-ce-5 gap-y-ce-1 sm:grid-cols-2"
    >
      {rows.map((row) => (
        <div key={row.key} className="flex items-baseline justify-between gap-ce-3">
          <dt className="ce-type-body text-ce-ink-muted">{row.label}</dt>
          <dd className="ce-type-value ce-tabular text-ce-ink">{formatWeight(row.weight)}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * One list of names under a heading with its count, open by default.
 *
 * `count` is the stored count and `entries` the names on record. When the
 * count is above zero and no name is on record, the run predates names being
 * kept: the heading still says how many, and one line says the names are not
 * there. Ranked entries are an ordered list; a list with no ranks is not.
 */
function NameList({
  heading,
  count,
  entries,
  emptySentence = "Nobody.",
}: {
  readonly heading: string;
  readonly count: number;
  readonly entries: readonly InvitedProfileView[];
  readonly emptySentence?: string;
}): React.JSX.Element {
  const ranked = entries.length > 0 && entries.every((entry) => entry.rank !== null);
  const List = ranked ? "ol" : "ul";
  return (
    <details open className="flex flex-col gap-ce-2">
      <summary className="ce-type-label cursor-pointer text-ce-ink">
        {heading} <span className="ce-tabular text-ce-ink-muted">({count})</span>
      </summary>
      {count === 0 ? (
        <p className="ce-type-body text-ce-ink-muted">{emptySentence}</p>
      ) : entries.length === 0 ? (
        <p className="ce-type-body text-ce-ink-muted">Names were not kept for this run.</p>
      ) : (
        <List
          className={cn(
            "ce-type-body grid gap-x-ce-5 gap-y-ce-1 pt-ce-1 text-ce-ink md:grid-cols-2",
            ranked ? "list-inside list-decimal" : "list-none",
          )}
        >
          {entries.map((entry) => (
            <li key={entry.profile_no} data-slot="exercise-instructor-name" className="min-w-0">
              <span className="font-semibold">{entry.display_name}</span>
              {facts(entry) === "" ? null : (
                <span className="ce-type-meta text-ce-ink-muted"> — {facts(entry)}</span>
              )}
            </li>
          ))}
        </List>
      )}
    </details>
  );
}

/** "Accounting, Senior, completed card" — whatever of the three is on record. */
function facts(entry: InvitedProfileView): string {
  return [entry.major, entry.class_year, entry.marker === null ? null : markerLabel(entry.marker)]
    .filter((part): part is string => typeof part === "string" && part !== "")
    .join(", ");
}
