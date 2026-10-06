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
 * **Both wait for a first-round run** (Ann, 2026-10-02: "the choice appears
 * only after the team has its round-one results"). The asking response says
 * whether that run exists (`first_round_results`) and names the event, so the
 * three cards are not drawn until it does; one line says why. The server
 * stays the judge: it refuses a choice or a refresh that comes early.
 *
 * **The refresh says that it happened, when, and what it changed**
 * (`RefreshSummary.tsx`): a timestamped summary in plain words, the three
 * counts, and the "how much we know" counts for every profile before and
 * after. All of it is on the asking response, so a reload, a second browser
 * and a team the instructor refreshed see the same thing. The shut button
 * reads "Already refreshed at 10:42 AM". Counts are what ADR-0025 D8 allows;
 * there is no percentage on this screen, and the shares in Ann's build table
 * (OQ-CE-04, confirmed 2026-09-25) are not returned by the API.
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

import { ExerciseUnreachable, isRefusal, type ExerciseRefusal } from "../../../lib/exerciseApi";
import {
  chooseAsking,
  readAskingChoice,
  refreshProfiles,
  type AskingStateView,
  type RefreshCountsView,
  type RefreshView,
} from "../../../lib/exerciseClient";
import { askingChoiceConfirmHint, askingChoiceLabel } from "./askingChoices";
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
import { RefreshSummary } from "./RefreshSummary";
import { alreadyRefreshedLabel, refreshSummaryText } from "./refreshWording";
import { isAccessRefusal, useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

/** The refusal a second refresh gets. The screen answers it with the time. */
const ALREADY_REFRESHED = "exercise_already_refreshed";

/** `sending` while the refresh is in flight (never a choice value). */
const REFRESH_ACTION = "refresh";

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
  // A reload that cannot reach the server keeps the screen: after a once-only
  // press, taking the panels down would also take down what the server just
  // confirmed. Every refusal still replaces it, and a 401/403 always does.
  const { state, reload } = useExerciseResource(readAskingChoice, [], {
    keepDataOnError: (error) => error instanceof ExerciseUnreachable,
  });

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
  /** The choice this browser's own POST was answered with. */
  const [confirmedChoice, setConfirmedChoice] = React.useState<string | null>(null);
  /** A choice or refresh refused because this browser lost access. */
  const [accessRefusal, setAccessRefusal] = React.useState<ExerciseRefusal | null>(null);

  // Access gone on a read: nothing this browser was told may stay in memory.
  const readRefused = state.status === "refused" && isAccessRefusal(state.refusal);
  React.useEffect(() => {
    if (readRefused) {
      setRefreshed(null);
      setConfirmedChoice(null);
    }
  }, [readRefused]);

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
      {accessRefusal === null ? null : workspaceRequiredNotice(accessRefusal)}
      {state.status === "ready" && accessRefusal === null ? (
        <>
          {state.unreachable === null ? null : (
            <ExerciseNotice message={state.unreachable} tone="problem">
              <Button variant="secondary" onClick={() => void reload()}>
                Try again
              </Button>
            </ExerciseNotice>
          )}
          <AskingPanels
            asking={state.data}
            onChanged={reload}
            refreshed={refreshed}
            onRefreshed={setRefreshed}
            confirmedChoice={confirmedChoice}
            onChoiceConfirmed={setConfirmedChoice}
            // The read on screen may predate this browser's own confirmed
            // press: its reload is still running, or could not be reached.
            trustConfirmed={state.refreshing || state.unreachable !== null}
            onAccessLost={(refusal) => {
              setRefreshed(null);
              setConfirmedChoice(null);
              setAccessRefusal(refusal);
            }}
          />
        </>
      ) : null}
    </ExerciseScreen>
  );
}

function AskingPanels({
  asking,
  onChanged,
  refreshed,
  onRefreshed,
  confirmedChoice,
  onChoiceConfirmed,
  trustConfirmed,
  onAccessLost,
}: {
  readonly asking: AskingStateView;
  readonly onChanged: () => Promise<void>;
  /** The once-only refresh result, owned by the screen. */
  readonly refreshed: RefreshView | null;
  readonly onRefreshed: (view: RefreshView) => void;
  /** The choice this browser's POST was answered with, owned by the screen. */
  readonly confirmedChoice: string | null;
  readonly onChoiceConfirmed: (choice: string) => void;
  /**
   * `asking` may be older than this browser's own confirmed press, so the
   * confirmed answers above stand in for it. Once a later read lands, the
   * server's word wins again — including a reset that cleared both.
   */
  readonly trustConfirmed: boolean;
  readonly onAccessLost: (refusal: ExerciseRefusal) => void;
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
   * Set synchronously, before any render: two presses in one tick both read
   * `pending` as `false`, so the state alone cannot keep a once-only POST
   * from going out twice.
   */
  const inFlight = React.useRef(false);

  /** What the team has chosen and asked, by the server's latest word or this browser's own. */
  const choice = asking.choice ?? (trustConfirmed ? confirmedChoice : null);
  const hasAsked = asking.refreshed || (trustConfirmed && refreshed !== null);
  /** This browser's own press stands in only while it is newer than the read. */
  const own = asking.refreshed || trustConfirmed ? refreshed : null;
  const counts: RefreshCountsView | null = asking.refreshed
    ? (asking.refresh_counts ?? own?.refresh_counts ?? null)
    : (own?.refresh_counts ?? null);
  const refreshedAt = asking.refreshed
    ? (asking.refreshed_at ?? own?.refreshed_at ?? null)
    : (own?.refreshed_at ?? null);
  /** Whether round one has results. A team that has asked always has them. */
  const roundOneRun = asking.first_round_results === true || hasAsked;
  const roundOneName = asking.first_round_event_name ?? null;

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
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(true);
    setSending(what);
    setRefusal(null);
    try {
      await action();
    } catch (error) {
      if (isAccessRefusal(error)) {
        onAccessLost(error);
        return;
      }
      setRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
    } finally {
      inFlight.current = false;
      setPending(false);
      setSending(null);
    }
  }

  const confirm = useConfirmWindow({
    onConfirm: () => {
      if (target === null) {
        return;
      }
      const picked = target;
      void run(picked, async () => {
        onChoiceConfirmed((await chooseAsking(picked)).choice ?? picked);
        await onChanged();
      });
    },
  });
  const armedChoice = confirm.armed ? target : null;

  /** A press on a card's button: arm it, or commit it if it is armed. */
  function press(choice: string): void {
    if (inFlight.current) {
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

  function cardState(card: string): AskingCardState {
    if (choice === null) {
      return "open";
    }
    return choice === card ? "chosen" : "dimmed";
  }

  const askShutReasons = [
    choice === null ? `${ids}-pick-first` : null,
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
        {/*
          The choice appears only after round one's results (Ann, 2026-10-02).
          A team that somehow chose earlier still sees what it chose.
        */}
        {roundOneRun || choice !== null ? (
          <div
            role="radiogroup"
            aria-labelledby={`${ids}-question`}
            className="grid gap-ce-3 lg:grid-cols-3 lg:gap-ce-5"
          >
            {asking.choices.map((card) => (
              <AskingChoiceCard
                key={card}
                choice={card}
                group={`${ids}-choice`}
                state={cardState(card)}
                selected={(choice ?? considered) === card}
                armed={armedChoice === card}
                saving={sending === card}
                busy={pending}
                reduced={reduced}
                onSelect={select}
                onPress={press}
                onKeyDown={confirm.onKeyDown}
              />
            ))}
          </div>
        ) : (
          <p data-slot="exercise-asking-not-yet" className="ce-type-body ce-measure text-ce-ink">
            {`Your team picks a way of asking after it has its results for ${roundOneName ?? "the first event"}.`}
          </p>
        )}
        <p aria-live="polite" data-slot="exercise-asking-confirm-live" className="sr-only">
          {armedChoice !== null
            ? askingChoiceConfirmHint(armedChoice)
            : confirmedChoice !== null && choice === confirmedChoice
              ? `Your team chose this: ${askingChoiceLabel(confirmedChoice)}`
              : ""}
        </p>
        {choice === null ? null : (
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
            disabled={pending || choice === null || hasAsked || !roundOneRun}
            describedBy={
              hasAsked || askShutReasons.length === 0 ? undefined : askShutReasons.join(" ")
            }
            onClick={() =>
              void run(REFRESH_ACTION, async () => {
                try {
                  onRefreshed(await refreshProfiles());
                } catch (error) {
                  // A second press (another tab got there first) changes
                  // nothing. The re-read below brings the time it happened,
                  // and the button then says so.
                  if (!(isRefusal(error) && error.code === ALREADY_REFRESHED)) {
                    throw error;
                  }
                }
                await onChanged();
              })
            }
            className="w-full md:w-auto"
          >
            {hasAsked ? alreadyRefreshedLabel(refreshedAt) : "Ask them now"}
          </Button>
        </div>
        {choice === null ? (
          <p id={`${ids}-pick-first`} className="ce-type-body text-ce-ink-muted">
            Pick a way of asking first.
          </p>
        ) : null}
        {roundOneRun ? null : (
          <p id={`${ids}-run-first`} className="ce-type-body text-ce-ink-muted">
            {`Run your team's results for ${roundOneName ?? "the first event"} before asking.`}
          </p>
        )}
        {/*
          While the server says the team has asked (a reset clears them), or
          while this browser's own confirmed refresh is newer than the read.
        */}
        {hasAsked ? (
          <RefreshSummary at={refreshedAt} counts={counts} eventName={roundOneName} />
        ) : null}
        <RefreshCounts counts={counts} reduced={reduced} />
        {/* Always present, so the summary is announced when it arrives. */}
        <p aria-live="polite" data-slot="exercise-refresh-announce" className="sr-only">
          {hasAsked ? refreshSummaryText(refreshedAt, counts, roundOneName) : ""}
        </p>
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
  readonly counts: RefreshCountsView | null;
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
