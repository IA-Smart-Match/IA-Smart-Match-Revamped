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
 *
 * **The invitation desk (DESIGN.md §6.18, §6.19, §7.9).** The choices are
 * radio cards (`ExerciseAskingChoiceCard.tsx`) with an inline confirm, owner
 * ruling 3: the first press on "Choose this way" arms that same button as
 * "Confirm: A small reward?" for about five seconds (`useConfirmWindow`); a
 * second press sends the choice; Escape, the window lapsing, or another card
 * reverts it. No pop-up. The counts are a ruled figures band that counts up
 * once; a screen reader hears only the final number.
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
import { askingChoiceConfirmHint } from "./askingChoices";
import {
  Button,
  SkeletonCard,
  SkeletonRegion,
  useConfirmWindow,
  useCountUp,
  usePrefersReducedMotion,
} from "./desk";
import { AskingChoiceCard, type AskingCardState } from "./ExerciseAskingChoiceCard";
import { ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

/** The refusal `GET …/events/{key}/results` gives for an event not yet run. */
const RESULTS_NOT_RUN = "exercise_results_not_run";

/** `sending` while the refresh is in flight (never a choice value). */
const REFRESH_ACTION = "refresh";

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

/** "Back to the events", drawn as a secondary button (§6.3). */
const BACK_LINK =
  "ce-press ce-type-label inline-flex min-h-ce-control no-underline items-center justify-center rounded-ce-control border-2 border-ce-line-strong bg-ce-surface px-ce-5 text-ce-ink hover:border-ce-primary hover:bg-ce-primary-tint";

/**
 * `partly-known-card.svg` (DESIGN.md §4, §7.9): a card half filled in, at the
 * right of the choices' heading from 768 up (the asking-choice-cards prompt's
 * placement; the shell's header has no slot beside the lead) and hidden on a
 * phone. Decorative, so hidden from readers.
 */
function PartlyKnownCard(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 100 80"
      fill="none"
      aria-hidden="true"
      focusable="false"
      data-slot="exercise-asking-art"
      className="hidden h-auto w-24 text-ce-primary md:block"
    >
      <rect
        x="8"
        y="10"
        width="84"
        height="60"
        rx="8"
        fill="currentColor"
        opacity="0.1"
        stroke="currentColor"
        strokeWidth="3"
      />
      <rect x="8" y="10" width="42" height="60" rx="8" fill="currentColor" opacity="0.35" />
      <path d="M50 10 V70" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" />
      <circle cx="29" cy="34" r="8" fill="currentColor" opacity="0.7" />
      <rect x="19" y="48" width="20" height="4" rx="2" fill="currentColor" opacity="0.6" />
      <circle
        cx="71"
        cy="34"
        r="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="3 3"
      />
      <rect x="61" y="48" width="20" height="4" rx="2" fill="currentColor" opacity="0.25" />
    </svg>
  );
}

/** The loading state (§6.21): three card shapes, and the stated line for readers. */
function AskingSkeleton(): React.JSX.Element {
  return (
    <SkeletonRegion
      label="Loading your team's choice…"
      className="grid gap-ce-3 lg:grid-cols-3 lg:gap-ce-5"
    >
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </SkeletonRegion>
  );
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
        <Link to="/exercise/events" className={BACK_LINK}>
          Back to the events
        </Link>
      }
    >
      {state.status === "loading" ? <AskingSkeleton /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <Button variant="secondary" onClick={() => void reload()}>
            Try again
          </Button>
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
  const ids = React.useId();
  const reduced = usePrefersReducedMotion();
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);
  /** Which action is in flight: a choice value, or `REFRESH_ACTION`. */
  const [sending, setSending] = React.useState<string | null>(null);
  /** The radio being considered before a choice is made. */
  const [considered, setConsidered] = React.useState<string | null>(null);
  /** The card the confirm window belongs to. */
  const [target, setTarget] = React.useState<string | null>(null);

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
  async function run(what: string, action: () => Promise<void>): Promise<void> {
    if (pending) {
      return;
    }
    setPending(true);
    setSending(what);
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
      setSending(null);
    }
  }

  const confirm = useConfirmWindow({
    onConfirm: () => {
      if (target === null) {
        return;
      }
      const choice = target;
      void run(choice, async () => {
        await chooseAsking(choice);
        await onChanged();
      });
    },
  });
  const armedChoice = confirm.armed ? target : null;

  /** A press on a card's button: arm it, or commit it if it is armed. */
  function press(choice: string): void {
    if (pending) {
      return;
    }
    setConsidered(choice);
    if (confirm.armed && target !== choice) {
      confirm.cancel();
    }
    setTarget(choice);
    confirm.press();
  }

  /** Picking another card in the radio group reverts an armed confirm. */
  function select(choice: string): void {
    setConsidered(choice);
    if (confirm.armed && target !== choice) {
      confirm.cancel();
    }
  }

  function cardState(choice: string): AskingCardState {
    if (asking.choice === null) {
      return "open";
    }
    return asking.choice === choice ? "chosen" : "dimmed";
  }

  const askShutReasons = [
    asking.choice === null ? `${ids}-pick-first` : null,
    roundOneRun ? null : `${ids}-run-first`,
  ].filter((id): id is string => id !== null);

  return (
    <div className="flex flex-col gap-ce-6 md:gap-ce-7">
      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      <section className="flex flex-col gap-ce-4" data-slot="exercise-asking-choices">
        <div className="flex items-end justify-between gap-ce-4">
          <h2 id={`${ids}-question`} className="ce-type-h2 text-ce-ink">
            How will your team ask?
          </h2>
          <PartlyKnownCard />
        </div>
        <div
          role="radiogroup"
          aria-labelledby={`${ids}-question`}
          className="grid gap-ce-3 lg:grid-cols-3 lg:gap-ce-5"
        >
          {asking.choices.map((choice) => (
            <AskingChoiceCard
              key={choice}
              choice={choice}
              group={`${ids}-choice`}
              state={cardState(choice)}
              selected={(asking.choice ?? considered) === choice}
              armed={armedChoice === choice}
              saving={sending === choice}
              busy={pending}
              reduced={reduced}
              onSelect={select}
              onPress={press}
              onKeyDown={confirm.onKeyDown}
            />
          ))}
        </div>
        <p aria-live="polite" data-slot="exercise-asking-confirm-live" className="sr-only">
          {armedChoice === null ? "" : askingChoiceConfirmHint(armedChoice)}
        </p>
        {asking.choice === null ? null : (
          <p className="ce-type-body text-ce-ink-muted">A team picks once, so these are now fixed.</p>
        )}
      </section>

      <section className="flex flex-col gap-ce-4">
        <h2 className="ce-type-h2 text-ce-ink">Ask the people your team invited</h2>
        <p className="ce-type-body ce-measure text-ce-ink-muted">
          This happens once. Everyone who attended the first event picks up its topics, and some of
          the people your team invited fill in a card.
        </p>
        <div>
          <Button
            variant="primary"
            pending={sending === REFRESH_ACTION}
            disabled={pending || asking.choice === null || asking.refreshed || !roundOneRun}
            describedBy={
              asking.refreshed || askShutReasons.length === 0 ? undefined : askShutReasons.join(" ")
            }
            onClick={() =>
              void run(REFRESH_ACTION, async () => {
                onRefreshed(await refreshProfiles());
                await onChanged();
              })
            }
            className="w-full md:w-auto"
          >
            {asking.refreshed ? "Your team has already asked" : "Ask them now"}
          </Button>
        </div>
        {asking.choice === null ? (
          <p id={`${ids}-pick-first`} className="ce-type-body text-ce-ink-muted">
            Pick a way of asking first.
          </p>
        ) : null}
        {roundOneRun ? null : (
          <p id={`${ids}-run-first`} className="ce-type-body text-ce-ink-muted">
            {`Run your team's results for ${roundOneName ?? "the first event"} before asking.`}
          </p>
        )}
        {/* Only while the server says the team has asked: a reset clears them. */}
        <RefreshCounts
          counts={asking.refreshed ? (asking.refresh_counts ?? refreshed) : null}
          reduced={reduced}
        />
      </section>
    </div>
  );
}

/**
 * The three counts, as a ruled figures band (§6.19, the same band as §6.15).
 * `topics_added` counts the *people* who picked up the first event's topics,
 * so the label says that rather than "topics added".
 */
function RefreshCounts({
  counts,
  reduced,
}: {
  readonly counts: RefreshCountsView | RefreshView | null;
  readonly reduced: boolean;
}): React.JSX.Element | null {
  if (counts === null) {
    return null;
  }
  return (
    <dl
      className="mt-ce-4 grid grid-cols-3 border-y border-ce-line-strong py-ce-4 md:py-ce-5"
      data-slot="exercise-refresh-counts"
    >
      <Count label="Cards filled in" value={counts.cards_completed} reduced={reduced} />
      <Count label="Stopped opening messages" value={counts.non_responding} reduced={reduced} />
      <Count
        label="Picked up the first event's topics"
        value={counts.topics_added}
        reduced={reduced}
      />
    </dl>
  );
}

/**
 * One figure. The label comes first in the source (a reader hears "Cards
 * filled in, 9") and is drawn under the numeral. The numeral counts up once
 * (`ce-count-up`); readers get only the final number.
 */
function Count({
  label,
  value,
  reduced,
}: {
  readonly label: string;
  readonly value: number;
  readonly reduced: boolean;
}): React.JSX.Element {
  const shown = useCountUp(value, { reduced });
  return (
    <div className="flex min-w-0 flex-col-reverse justify-end gap-ce-2 border-l border-ce-line-strong px-ce-3 first:border-l-0 first:pl-0 md:px-ce-5">
      <dt className="ce-type-body text-ce-ink-muted">{label}</dt>
      <dd className="text-ce-primary">
        <span className="sr-only">{value}</span>
        <span aria-hidden="true" className="ce-type-display">
          {shown}
        </span>
      </dd>
    </div>
  );
}
