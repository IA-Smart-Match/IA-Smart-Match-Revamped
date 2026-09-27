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
import { ArrowLeft } from "lucide-react";

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
import { ChoiceCard, ConfirmLiveRegion, useConfirmWindow } from "./AskingChoiceCards";
import { PartlyKnownCardArt } from "./exerciseArt";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ceButton, FiguresBand, Spinner } from "./exerciseUi";
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
        <div className="flex flex-col items-start gap-6 md:items-end">
          <Link to="/exercise/events" className={ceButton("secondary")}>
            <ArrowLeft aria-hidden="true" className="size-5" />
            Back to the events
          </Link>
          {/* §7.9: the half-filled card, right of the lead, desktop only. */}
          <PartlyKnownCardArt className="hidden h-20 w-24 text-ce-primary md:block" />
        </div>
      }
    >
      {state.status === "loading" ? <ExerciseLoading what="your team's choice" shape="cards" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={ceButton("primary")}>
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
  const confirm = useConfirmWindow(asking.choice);

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

  const choose = (choice: string): void =>
    void run(async () => {
      await chooseAsking(choice);
      await onChanged();
    });

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      <section className="flex flex-col gap-4" data-slot="exercise-asking-choices">
        <h2 className="ce-h2 text-ce-ink">How will your team ask?</h2>
        <ul className="grid gap-4 lg:grid-cols-3 lg:gap-6">
          {asking.choices.map((choice) => (
            <li key={choice}>
              <ChoiceCard
                choice={choice}
                chosen={asking.choice === choice}
                faded={asking.choice !== null && asking.choice !== choice}
                locked={asking.choice !== null}
                armed={confirm.armed === choice}
                pending={pending}
                reduced={confirm.reduced}
                hint={confirm.armed === choice ? confirm.hint : ""}
                onPress={() => confirm.press(choice, choose)}
                onEscape={confirm.disarm}
              />
            </li>
          ))}
        </ul>
        <ConfirmLiveRegion hint={confirm.hint} />
        {asking.choice === null ? null : (
          <p className="ce-meta text-ce-muted">A team picks once, so these are now fixed.</p>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="ce-h2 text-ce-ink">Ask the people your team invited</h2>
        <p className="ce-body max-w-[72ch] text-ce-ink">
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
            className={ceButton("primary", "ce-btn-lg w-full sm:w-auto")}
          >
            {pending && asking.choice !== null && !asking.refreshed ? <Spinner /> : null}
            {asking.refreshed ? "Your team has already asked" : "Ask them now"}
          </button>
        </div>
        {asking.choice === null ? (
          <p className="ce-meta text-ce-muted">Pick a way of asking first.</p>
        ) : null}
        {roundOneRun ? null : (
          <p className="ce-meta text-ce-muted">
            {`Run your team's results for ${roundOneName ?? "the first event"} before asking.`}
          </p>
        )}
        {/* Only while the server says the team has asked: a reset clears them. */}
        <RefreshCounts
          counts={asking.refreshed ? (asking.refresh_counts ?? refreshed) : null}
          countUp={refreshed !== null}
        />
      </section>
    </div>
  );
}

/**
 * The three counts, as the same ruled band as the results (DESIGN.md §6.19).
 * `topics_added` counts the *people* who picked up the first event's topics,
 * so the label says that rather than "topics added". They count up once, only
 * right after this browser's own press.
 */
function RefreshCounts({
  counts,
  countUp,
}: {
  readonly counts: RefreshCountsView | RefreshView | null;
  readonly countUp: boolean;
}): React.JSX.Element | null {
  if (counts === null) {
    return null;
  }
  return (
    <div className="mt-4">
      <FiguresBand
        slot="exercise-refresh-counts"
        countUp={countUp}
        figures={[
          { label: "Cards filled in", value: counts.cards_completed },
          { label: "Stopped opening messages", value: counts.non_responding },
          { label: "Picked up the first event's topics", value: counts.topics_added },
        ]}
      />
    </div>
  );
}
