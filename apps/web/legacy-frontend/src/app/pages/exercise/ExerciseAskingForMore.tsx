/**
 * Asking for more: one choice, once, and then one refresh.
 *
 * Requirements, "Asking for more" row: *"Before the refresh, a team picks one
 * of three ways to ask the profiles it invited to complete a card."* The
 * choice is stored on the workspace and it is what unlocks the refresh, so the
 * two live on one screen in that order — choose, then ask.
 *
 * **The three come from the server.** `choices` is on the asking response and
 * is what this screen maps over; only the wording of each is local, and an
 * unrecognised value renders as itself. The same discipline as `max_settings`
 * on the settings response: a vocabulary written into a screen is a second
 * source of truth.
 *
 * **A second choice is refused, and that refusal is the answer.** So is a
 * refresh before a round-one run, and a second refresh. Each arrives as a 409
 * with one plain sentence, and each is rendered as a calm state — these are
 * the product working, not failures. The choice controls stay on screen after
 * a choice is made, showing which one the team took, rather than vanishing: a
 * class arguing about the choice needs to see what was chosen.
 *
 * **The refresh waits for a first-round run.** The server refuses a refresh
 * before one, and did so cleanly, but the button used to be offered anyway.
 * The asking response does not say whether that run exists, so the screen
 * reads it the way the results screen does: the first round is the first
 * exercise event by `sequence` (never by name), and its stored results either
 * come back or are refused as not run. The server stays the judge; this only
 * stops the screen offering a press it already knows will be refused.
 *
 * The refresh reports counts — cards completed, non-responding, topics added.
 * Counts are what ADR-0025 D8 allows and what the requirements ask for; there
 * is no percentage on this screen, and the illustrative shares in Ann's build
 * table (OQ-CE-04, confirmed 2026-09-25) are not returned by the API.
 */
import * as React from "react";
import { Link } from "react-router";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  chooseAsking,
  readAskingChoice,
  readEvents,
  readResults,
  refreshProfiles,
  type AskingStateView,
  type RefreshCountsView,
  type RefreshView,
} from "../../../lib/exerciseClient";
import { askingChoiceLabel } from "./askingChoices";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

/** The refusal `GET …/events/{key}/results` gives for an event not yet run. */
const RESULTS_NOT_RUN = "exercise_results_not_run";

/** What this screen reads: the asking state, and whether round one has run. */
interface AskingScreenView {
  readonly asking: AskingStateView;
  /** Whether this team has stored results for its first round. */
  readonly roundOneRun: boolean;
  /** The first round's event name, or `null` when the file has no rounds. */
  readonly roundOneName: string | null;
}

/**
 * The asking state, plus whether this team's first round has results.
 *
 * Skipped once the team has refreshed: a refresh is only ever allowed after a
 * first-round run, so the answer is already known. Any refusal other than
 * "not run yet" (the workspace cookie gone, say) is the screen's refusal.
 */
async function readAskingScreen(signal: AbortSignal): Promise<AskingScreenView> {
  const asking = await readAskingChoice(signal);
  if (asking.refreshed) {
    return { asking, roundOneRun: true, roundOneName: null };
  }
  const { events } = await readEvents(signal);
  const roundOne = events
    .filter((event) => event.is_exercise_event)
    .sort((a, b) => a.sequence - b.sequence)[0];
  if (roundOne === undefined) {
    return { asking, roundOneRun: false, roundOneName: null };
  }
  try {
    await readResults(roundOne.event_key, signal);
    return { asking, roundOneRun: true, roundOneName: roundOne.name };
  } catch (error) {
    if (isRefusal(error) && error.code === RESULTS_NOT_RUN) {
      return { asking, roundOneRun: false, roundOneName: roundOne.name };
    }
    throw error;
  }
}

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-5 py-3 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

export function ExerciseAskingForMore(): React.JSX.Element {
  const { state, reload } = useExerciseResource(readAskingScreen, []);

  /**
   * What this browser's own refresh press reported, held by the screen.
   *
   * `GET …/asking-choice` now carries `refresh_counts` whenever the team has
   * been refreshed (M2 B4), read back from the team's view, so a reload, a
   * second browser and the instructor's refresh-all all show them. This copy
   * only bridges the moment between the POST answering and the reload after
   * it landing; the stored counts win once they arrive.
   */
  const [refreshed, setRefreshed] = React.useState<RefreshView | null>(null);

  return (
    <ExerciseScreen
      title="Asking for more"
      intro="Pick one way to ask the people your team invited to fill in a card. Your team picks once."
      aside={
        <Link to="/exercise/events" className={BUTTON}>
          Back to the events
        </Link>
      }
    >
      {state.status === "loading" ? <ExerciseLoading what="your team's choice" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={BUTTON}>
            Try again
          </button>
        </ExerciseNotice>
      ) : null}
      {state.status === "ready" ? (
        <AskingPanels
          asking={state.data.asking}
          roundOneRun={state.data.roundOneRun}
          roundOneName={state.data.roundOneName}
          onChanged={reload}
          refreshed={refreshed}
          onRefreshed={setRefreshed}
        />
      ) : null}
    </ExerciseScreen>
  );
}

function AskingPanels({
  asking,
  roundOneRun,
  roundOneName,
  onChanged,
  refreshed,
  onRefreshed,
}: {
  readonly asking: AskingStateView;
  /** Whether this team has results for its first round (see the module note). */
  readonly roundOneRun: boolean;
  readonly roundOneName: string | null;
  readonly onChanged: () => Promise<void>;
  /** The once-only refresh result, owned by the screen. */
  readonly refreshed: RefreshView | null;
  readonly onRefreshed: (view: RefreshView) => void;
}): React.JSX.Element {
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  /**
   * Run one action and stay disabled until the screen actually reflects it.
   *
   * `onChanged` (the hook's `reload`) resolves once the *refreshed* state has
   * landed, not once the network call it started has. Clearing `pending`
   * right after the mutation's own request settled — and before that reload
   * resolved — left a window where `asking.choice` / `asking.refreshed` were
   * still the old, unlocked values and the button was clickable again: a
   * once-only action could be fired twice inside that window.
   */
  async function run(action: () => Promise<void>): Promise<void> {
    if (pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      await action();
    } catch (error) {
      setRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      <section className="flex flex-col gap-4" data-slot="exercise-asking-choices">
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
          How will your team ask?
        </h2>
        <ul className="flex flex-col gap-3">
          {asking.choices.map((choice) => {
            const chosen = asking.choice === choice;
            return (
              <li key={choice} className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  disabled={pending || asking.choice !== null}
                  aria-pressed={chosen}
                  onClick={() =>
                    void run(async () => {
                      await chooseAsking(choice);
                      await onChanged();
                    })
                  }
                  className={`${BUTTON} ${
                    chosen
                      ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                      : ""
                  }`}
                >
                  {askingChoiceLabel(choice)}
                </button>
                {chosen ? (
                  <span className="text-xl text-slate-700 dark:text-slate-200">
                    Your team chose this.
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
        {asking.choice === null ? null : (
          <p className="text-xl text-slate-600 dark:text-slate-300">
            A team picks once, so these are now fixed.
          </p>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
          Ask the people your team invited
        </h2>
        <p className="text-xl text-slate-700 dark:text-slate-200">
          This happens once. Everyone who attended the first event picks up its topics, and some of
          the people your team invited fill in a card.
        </p>
        <div>
          <button
            type="button"
            disabled={pending || asking.choice === null || asking.refreshed || !roundOneRun}
            onClick={() =>
              void run(async () => {
                onRefreshed(await refreshProfiles());
                await onChanged();
              })
            }
            className={BUTTON}
          >
            {asking.refreshed ? "Your team has already asked" : "Ask them now"}
          </button>
        </div>
        {asking.choice === null ? (
          <p className="text-xl text-slate-600 dark:text-slate-300">
            Pick a way of asking first.
          </p>
        ) : null}
        {roundOneRun ? null : (
          <p className="text-xl text-slate-600 dark:text-slate-300">
            {`Run your team's results for ${roundOneName ?? "the first event"} before asking.`}
          </p>
        )}
        <RefreshCounts counts={asking.refresh_counts ?? refreshed} />
      </section>
    </div>
  );
}

/**
 * The three counts. `topics_added` counts the *people* who picked up the first
 * event's topics, so the label says that rather than "topics added".
 */
function RefreshCounts({
  counts,
}: {
  readonly counts: RefreshCountsView | RefreshView | null;
}): React.JSX.Element | null {
  if (counts === null) {
    return null;
  }
  return (
    <dl className="grid gap-3 text-xl sm:grid-cols-3" data-slot="exercise-refresh-counts">
      <Count label="Cards filled in" value={counts.cards_completed} />
      <Count label="Stopped opening messages" value={counts.non_responding} />
      <Count label="Picked up the first event's topics" value={counts.topics_added} />
    </dl>
  );
}

function Count({
  label,
  value,
}: {
  readonly label: string;
  readonly value: number;
}): React.JSX.Element {
  return (
    <div className="rounded-lg border-2 border-slate-300 px-4 py-3 dark:border-slate-600">
      <dt className="text-lg text-slate-600 dark:text-slate-300">{label}</dt>
      <dd className="text-3xl font-bold text-slate-900 dark:text-slate-50">{value}</dd>
    </div>
  );
}
