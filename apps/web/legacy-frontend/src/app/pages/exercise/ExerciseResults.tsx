/**
 * The results screen: what your team's list actually did.
 *
 * **Most of what this screen shows today is a refusal, and that is correct.**
 * `POST …/events/{event_key}/results` answers 409
 * `exercise_results_rule_not_confirmed` on this deployment, because OQ-CE-03 —
 * the coefficients of the simulated-results rule — is open and
 * `EXERCISE_SIMULATION_COEFFICIENTS` is `None`. PR #190 is explicit that this
 * is the route working. So it renders as a calm state carrying the server's
 * own sentence, not as an error toast, and the same is true of the other two
 * states a team meets here:
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
 * Names for the team's own panels are joined from the ranked list by
 * `profile_no` (owner decision, 2026-09-21): the results routes carry numbers
 * and counts, and nothing here asks the backend for names.
 */
import * as React from "react";
import { Link, useParams } from "react-router";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  readAskingChoice,
  readRankedList,
  readResults,
  refreshProfiles,
  runResults,
  type AskingStateView,
  type ResultsView,
} from "../../../lib/exerciseClient";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ResultPanels, type NamesByProfileNo } from "./ResultPanels";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-5 py-3 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

/** The read's 404, which means "not run yet" rather than "something is wrong". */
const NOT_RUN = "exercise_results_not_run";

interface ResultsData {
  /** `null` until this team has run results for this event. */
  readonly results: ResultsView | null;
  readonly names: NamesByProfileNo;
  readonly asking: AskingStateView;
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
      const names = await namesForEvent(eventKey, signal);
      return { results, names, asking: await readAskingChoice(signal) };
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
 * A failure here is not a failure of the results screen: the counts and the
 * comparison are the lesson, and the names are the illustration. So a refusal
 * on the list leaves the map empty and the panels fall back to profile
 * numbers, rather than taking the whole screen down.
 */
async function namesForEvent(eventKey: string, signal: AbortSignal): Promise<NamesByProfileNo> {
  try {
    const list = await readRankedList(eventKey, { kind: "default" }, signal);
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
          <div>
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                void run(async () => {
                  await runResults(eventKey, null);
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
