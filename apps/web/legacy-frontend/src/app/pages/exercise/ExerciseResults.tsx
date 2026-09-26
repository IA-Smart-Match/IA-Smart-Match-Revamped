/**
 * The results screen: what your team's list actually did.
 *
 * **A refusal here is a state, not an error.** The results rule runs on the
 * coefficients Chau approved (wave-2 decision D7), so a run normally succeeds.
 * `POST …/events/{event_key}/results` answers 409
 * `exercise_results_rule_not_confirmed` only if that coefficient set is ever
 * removed. It renders as a calm state carrying the server's own sentence, not
 * as an error toast, and the same is true of the other two states a team meets
 * here:
 *
 * - `exercise_results_locked` — the instructor has not opened this event yet.
 * - `exercise_results_already_run` — design spec §9's one run per team per
 *   event, and its sentence is the spec's own.
 *
 * Each is one plain sentence written for a projector, shown as-is. A screen
 * that re-worded them, or that hid the button and implied the capability did
 * not exist, would be answering for the server.
 *
 * `exercise_results_not_run` (404) on the read is not a refusal to display at
 * all — it simply means this team has not run yet, which is the screen's
 * ordinary first state.
 *
 * **The team runs its final setting, and nothing else** (Ann to Chau, Discord,
 * 2026-09-24): set weights, save up to three settings and compare two, choose
 * one final setting, then run once the instructor unlocks the event. So the run
 * button stays off until one of this event's saved settings is chosen, and a
 * team with none saved is told to save one first. The server refuses a run
 * without a final setting too; this screen only makes the step visible.
 *
 * Names for the team's own panels are joined from the ranked list by
 * `profile_no` (owner decision, 2026-09-21): the results routes carry numbers
 * and counts, and nothing here asks the backend for names. The list asked is
 * the one the run's final setting built, so the names match who was invited.
 */
import * as React from "react";
import { Link, useParams } from "react-router";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  readAskingChoice,
  readRankedList,
  readResults,
  readSavedSettings,
  refreshProfiles,
  runResults,
  type AskingStateView,
  type ListWeighting,
  type ResultsView,
  type SavedSettingsView,
} from "../../../lib/exerciseClient";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ResultPanels, type NamesByProfileNo } from "./ResultPanels";
import { SettingPicker } from "./SavedSettingsPanel";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-5 py-3 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

/** The read's 404, which means "not run yet" rather than "something is wrong". */
const NOT_RUN = "exercise_results_not_run";

/** The run's 404 for a final setting this team no longer has (deleted in another tab). */
const SETTING_UNKNOWN = "exercise_setting_unknown";

/** Says why the run button is off; the button points at it with `aria-describedby`. */
const FINAL_SETTING_HINT = "exercise-final-setting-hint";

interface ResultsData {
  /** `null` until this team has run results for this event. */
  readonly results: ResultsView | null;
  readonly names: NamesByProfileNo;
  readonly asking: AskingStateView;
  /** This event's saved settings, to choose the final one from; `null` once run. */
  readonly saved: SavedSettingsView | null;
}

export function ExerciseResults(): React.JSX.Element {
  const { eventKey = "" } = useParams();

  const load = React.useCallback(
    async (signal: AbortSignal): Promise<ResultsData> => {
      let results: ResultsView | null = null;
      try {
        results = await readResults(eventKey, signal);
      } catch (error) {
        if (!(isRefusal(error) && error.code === NOT_RUN)) {
          throw error;
        }
      }
      // Independent reads, so they go together. The saved settings are only
      // needed before the run: afterwards there is nothing left to choose.
      const [names, asking, saved] = await Promise.all([
        namesForEvent(eventKey, results?.setting_name ?? null, signal),
        readAskingChoice(signal),
        results === null ? readSavedSettings(eventKey, signal) : Promise.resolve(null),
      ]);
      return { results, names, asking, saved };
    },
    [eventKey],
  );
  const { state, reload } = useExerciseResource(load, [eventKey]);

  return (
    <ExerciseScreen
      title="Results"
      intro="What your team's list did, next to what emailing all 300 would have done."
      aside={
        <Link to={`/exercise/events/${encodeURIComponent(eventKey)}`} className={BUTTON}>
          Back to your team's list
        </Link>
      }
    >
      {state.status === "loading" ? <ExerciseLoading what="your team's results" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={BUTTON}>
            Try again
          </button>
        </ExerciseNotice>
      ) : null}
      {state.status === "ready" ? (
        <ResultsBody eventKey={eventKey} data={state.data} onChanged={reload} />
      ) : null}
    </ExerciseScreen>
  );
}

/**
 * The names the ranked list gives this event's profile numbers.
 *
 * Asked of the list the run's final setting built, when there is a run, so the
 * team's own panel is named from the list it actually invited. A setting
 * deleted since the run is refused by the list route and falls back below.
 *
 * A failure here is not a failure of the results screen: the counts and the
 * comparison are the lesson, and the names are the illustration. So a refusal
 * on the list leaves the map empty and the panels fall back to profile
 * numbers, rather than taking the whole screen down.
 */
async function namesForEvent(
  eventKey: string,
  settingName: string | null,
  signal: AbortSignal,
): Promise<NamesByProfileNo> {
  const weighting: ListWeighting =
    settingName === null ? { kind: "default" } : { kind: "setting", name: settingName };
  try {
    const list = await readRankedList(eventKey, weighting, signal);
    return new Map(list.entries.map((entry) => [entry.profile_no, entry.display_name]));
  } catch (error) {
    // An abort is not a missing list — it is this load being replaced. It has
    // to propagate, or a superseded load resolves with an empty map and the
    // hook settles a stale answer over the live one.
    if (signal.aborted) {
      throw error;
    }
    return new Map();
  }
}

function ResultsBody({
  eventKey,
  data,
  onChanged,
}: {
  readonly eventKey: string;
  readonly data: ResultsData;
  readonly onChanged: () => void;
}): React.JSX.Element {
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);
  const [finalSetting, setFinalSetting] = React.useState("");

  async function run(action: () => Promise<void>): Promise<void> {
    if (pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      await action();
    } catch (error) {
      // Every results refusal is a state, not an error: locked, already run,
      // and the rule not yet confirmed are all the product working. Each is
      // shown as the server's own sentence.
      setRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  const canRefresh = data.asking.choice !== null && !data.asking.refreshed;

  return (
    <div className="flex flex-col gap-8">
      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      {data.results === null ? (
        <section className="flex flex-col gap-4">
          <p className="text-xl text-slate-700 dark:text-slate-200">
            Your team has not run results for this event yet. A team runs them once.
          </p>
          <FinalSettingChoice
            eventKey={eventKey}
            saved={data.saved}
            value={finalSetting}
            onChange={setFinalSetting}
          />
          <div>
            <button
              type="button"
              disabled={pending || finalSetting === ""}
              aria-describedby={FINAL_SETTING_HINT}
              onClick={() =>
                void run(async () => {
                  try {
                    await runResults(eventKey, finalSetting);
                  } catch (error) {
                    // The chosen name was deleted since this screen loaded:
                    // clear it and re-read the list, so the picker only offers
                    // names the run route can still find. The sentence still shows.
                    if (isRefusal(error) && error.code === SETTING_UNKNOWN) {
                      setFinalSetting("");
                      onChanged();
                    }
                    throw error;
                  }
                  onChanged();
                })
              }
              className={BUTTON}
            >
              {pending ? "Running…" : "Run results for this event"}
            </button>
          </div>
        </section>
      ) : (
        <ResultPanels results={data.results} names={data.names} />
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
          Ask the people your team invited
        </h2>
        {data.asking.choice === null ? (
          <p className="text-xl text-slate-700 dark:text-slate-200">
            Your team has not picked a way of asking yet.{" "}
            <Link to="/exercise/asking" className="underline">
              Pick one first
            </Link>
            .
          </p>
        ) : (
          <div>
            <button
              type="button"
              disabled={pending || !canRefresh}
              onClick={() =>
                void run(async () => {
                  await refreshProfiles();
                  onChanged();
                })
              }
              className={BUTTON}
            >
              {data.asking.refreshed ? "Your team has already asked" : "Ask them now"}
            </button>
            <p className="mt-2 text-xl text-slate-600 dark:text-slate-300">
              Your team may ask once.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

/**
 * Step three of the owner's flow: the team's one final setting for this event.
 *
 * The choices are the team's saved settings, read from the server, so a name
 * here is always one the run route can find. Nothing is chosen for the team,
 * even when it has saved only one: choosing is the step.
 */
function FinalSettingChoice({
  eventKey,
  saved,
  value,
  onChange,
}: {
  readonly eventKey: string;
  readonly saved: SavedSettingsView | null;
  readonly value: string;
  readonly onChange: (value: string) => void;
}): React.JSX.Element {
  const settings = saved?.settings ?? [];
  if (settings.length === 0) {
    return (
      <p
        id={FINAL_SETTING_HINT}
        className="text-xl text-slate-700 dark:text-slate-200"
        data-slot="exercise-final-setting"
      >
        Your team has not saved any settings for this event yet. Save one on{" "}
        <Link to={`/exercise/events/${encodeURIComponent(eventKey)}`} className="underline">
          your team's list
        </Link>{" "}
        first, then choose it here as your final setting.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-slot="exercise-final-setting">
      <SettingPicker
        id="exercise-final-setting"
        label="Your team's final setting"
        value={value}
        onChange={onChange}
        settings={settings}
      />
      <p id={FINAL_SETTING_HINT} className="text-xl text-slate-600 dark:text-slate-300">
        Your team's invited list is built from the setting you choose. Choose one to run
        results.
      </p>
    </div>
  );
}
