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
 * The refresh reports counts — cards completed, non-responding, topics added.
 * Counts are what ADR-0025 D8 allows and what the requirements ask for; there
 * is no percentage on this screen, and the illustrative shares in Ann's build
 * table are OQ-CE-04 placeholders the API does not return.
 */
import * as React from "react";
import { Link } from "react-router";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  chooseAsking,
  readAskingChoice,
  refreshProfiles,
  type AskingStateView,
  type RefreshView,
} from "../../../lib/exerciseClient";
import { askingChoiceLabel } from "./askingChoices";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-5 py-3 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

export function ExerciseAskingForMore(): React.JSX.Element {
  const { state, reload } = useExerciseResource(readAskingChoice, []);

  /**
   * What the one refresh reported, held by the screen rather than the panel.
   *
   * A team may refresh once, ever. The counts came back from that single
   * request and the server will not produce them again — `GET …/asking-choice`
   * reports only *that* a team has refreshed, not what happened. So they
   * cannot live in a component that a reload unmounts, which is exactly what
   * used to happen: the refresh resolved, the counts rendered, the reload it
   * triggered dropped the screen to `loading`, the panel unmounted, and the
   * only record of the result was gone for good.
   *
   * `useExerciseResource` no longer unmounts a ready screen while it
   * refetches, so this would survive either way now. It is lifted regardless:
   * a once-only result should not depend on a rendering detail somewhere else
   * to stay on the screen.
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
          asking={state.data}
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
  onChanged,
  refreshed,
  onRefreshed,
}: {
  readonly asking: AskingStateView;
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
            disabled={pending || asking.choice === null || asking.refreshed}
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
        {refreshed === null ? null : (
          <dl
            className="grid gap-3 text-xl sm:grid-cols-3"
            data-slot="exercise-refresh-counts"
          >
            <Count label="Cards filled in" value={refreshed.cards_completed} />
            <Count label="Stopped opening messages" value={refreshed.non_responding} />
            <Count label="Topics added from the first event" value={refreshed.topics_added} />
          </dl>
        )}
      </section>
    </div>
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
