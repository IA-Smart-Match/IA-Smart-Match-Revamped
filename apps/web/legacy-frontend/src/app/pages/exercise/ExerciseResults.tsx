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
 * **The run button has three states, read before anybody presses** (issue
 * #328; Ann's checklist of 2026-10-02, section 5). The events read says
 * whether results are open for this event and whether this team has already
 * run them (`EventView.results_open` / `results_run`):
 *
 * - not open: grey, "Results not open yet.", with the lock panel saying why;
 * - open: live. The first press asks, on the button itself — "Send this list?
 *   You get one results run for {event}" — and a second press inside five
 *   seconds sends it. Escape or waiting puts it back. No pop-up;
 * - run: grey, "Results already run for this event.", above the stored
 *   results. Run wins over open: results closed again after a run still read
 *   as run.
 *
 * Grey is what the team is shown, never what is allowed: the server refuses a
 * second run whatever this screen believes. A tab that was open before the
 * run still has a live button; its press is answered 409, the sentence says
 * why, and the screen reads again and lands on the right state.
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

import { ExerciseUnreachable, isRefusal, type ExerciseRefusal } from "../../../lib/exerciseApi";
import {
  EXERCISE_FACTOR_KEYS,
  readAskingChoice,
  readEvents,
  readRankedList,
  readResults,
  readSavedSettings,
  refreshProfiles,
  runResults,
  type AskingStateView,
  type ListWeighting,
  type RefreshCountsView,
  type RefreshView,
  type ResultsView,
  type SavedSettingView,
  type SavedSettingsView,
} from "../../../lib/exerciseClient";
import { cn } from "../../components/ui/utils";
import {
  Button,
  ConfirmWindowUnderline,
  formatWeight,
  useConfirmWindow,
  usePrefersReducedMotion,
} from "./desk";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ResultPanels, type NamesByProfileNo } from "./ResultPanels";
import { ProfileCardArt } from "./resultsArt";
import { ResultsLockPanel } from "./ResultsLockPanel";
import { isAccessRefusal, useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

/** A link that looks like the desk's secondary button (§6.3). */
const LINK_BUTTON =
  "ce-press ce-type-label inline-flex min-h-ce-control items-center justify-center rounded-ce-control border-2 border-ce-line-strong bg-ce-surface px-ce-5 text-ce-ink hover:border-ce-primary hover:bg-ce-primary-tint";

/** The read's 404, which means "not run yet" rather than "something is wrong". */
const NOT_RUN = "exercise_results_not_run";

/** The run's 404 for a final setting this team no longer has (deleted in another tab). */
const SETTING_UNKNOWN = "exercise_setting_unknown";

/** The run's 409 while results for this event are not open: the lock panel (§6.14). */
const LOCKED = "exercise_results_locked";

/** The run's 409 for a second run: the team has had its one. */
const ALREADY_RUN = "exercise_results_already_run";

/** Says why the grey "Results not open yet." button is off. */
const NOT_OPEN_REASON = "exercise-results-not-open-reason";

/** Says why the grey "Results already run for this event." button is off. */
const ALREADY_RUN_REASON = "exercise-results-already-run-reason";

/** What this team's events read says about one event's results. */
interface EventResultsState {
  /** The event's label, for the sentences that name it. */
  readonly name: string;
  readonly open: boolean;
  readonly run: boolean;
}

/** Ann's sentence for a press that cannot do anything yet (2026-10-02). */
function notOpenSentence(eventName: string): string {
  return `Results for ${eventName} are not open yet. Ask your instructor.`;
}

/** The question the run button asks before the one run (Ann's checklist, section 5). */
function sendListQuestion(eventName: string | null): string {
  return `Send this list? You get one results run for ${eventName ?? "this event"}`;
}

/** Says why the run button is off; the button points at it with `aria-describedby`. */
const FINAL_SETTING_HINT = "exercise-final-setting-hint";

/** Names the final-setting radio group. */
const FINAL_SETTING_HEADING = "exercise-final-setting-heading";

/** Ann's words for each factor key, from the ranked list; empty when it is not loaded. */
type FactorLabels = Readonly<Record<string, string>>;

interface ResultsData {
  /** `null` until this team has run results for this event. */
  readonly results: ResultsView | null;
  readonly names: NamesByProfileNo;
  readonly labels: FactorLabels;
  readonly asking: AskingStateView;
  /** This event's saved settings, to choose the final one from; `null` once run. */
  readonly saved: SavedSettingsView | null;
  /**
   * Whether results are open and already run, from the events read; `null`
   * when that read could not say. Unknown is shown as open, so the run route
   * answers instead of this screen guessing.
   */
  readonly event: EventResultsState | null;
}

export function ExerciseResults(): React.JSX.Element {
  const { eventKey = "" } = useParams();
  // Keyed by event: the chosen final setting, a refusal and a just-run reveal
  // belong to one event and must not carry over to the next.
  return <EventResults key={eventKey} eventKey={eventKey} />;
}

function EventResults({ eventKey }: { readonly eventKey: string }): React.JSX.Element {
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
      const [list, asking, saved, event] = await Promise.all([
        listForEvent(eventKey, results?.setting_name ?? null, signal),
        readAskingChoice(signal),
        results === null ? readSavedSettings(eventKey, signal) : Promise.resolve(null),
        eventResultsState(eventKey, signal),
      ]);
      return { results, names: list.names, labels: list.labels, asking, saved, event };
    },
    [eventKey],
  );
  // A reload that cannot reach the server keeps the screen, so a run or a
  // refresh the server just confirmed stays shut and on screen. Every refusal
  // still replaces it, and a 401/403 always does.
  const { state, reload } = useExerciseResource(load, [eventKey], {
    keepDataOnError: (error) => error instanceof ExerciseUnreachable,
  });
  /** What this browser's own run and refresh were answered with. */
  const [confirmedResults, setConfirmedResults] = React.useState<ResultsView | null>(null);
  const [confirmedRefresh, setConfirmedRefresh] = React.useState<RefreshView | null>(null);
  /** A run or refresh refused because this browser lost access. */
  const [accessRefusal, setAccessRefusal] = React.useState<ExerciseRefusal | null>(null);

  // Access gone on a read: nothing this browser was told may stay in memory.
  const readRefused = state.status === "refused" && isAccessRefusal(state.refusal);
  React.useEffect(() => {
    if (readRefused) {
      setConfirmedResults(null);
      setConfirmedRefresh(null);
    }
  }, [readRefused]);

  return (
    <ExerciseScreen
      title="Results"
      intro="What your team's list did, next to what emailing all 300 would have done."
      aside={
        <Link to={`/exercise/events/${encodeURIComponent(eventKey)}`} className={LINK_BUTTON}>
          Back to your team's list
        </Link>
      }
    >
      {state.status === "loading" ? <ExerciseLoading what="your team's results" /> : null}
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
          <ResultsBody
            eventKey={eventKey}
            data={state.data}
            onChanged={reload}
            confirmedResults={confirmedResults}
            onResultsConfirmed={setConfirmedResults}
            confirmedRefresh={confirmedRefresh}
            onRefreshConfirmed={setConfirmedRefresh}
            // The read on screen may predate this browser's own confirmed
            // press: its reload is still running, or could not be reached.
            trustConfirmed={state.refreshing || state.unreachable !== null}
            onAccessLost={(refusal) => {
              setConfirmedResults(null);
              setConfirmedRefresh(null);
              setAccessRefusal(refusal);
            }}
          />
        </>
      ) : null}
    </ExerciseScreen>
  );
}

/**
 * The names the ranked list gives this event's profile numbers, and Ann's
 * words for the four weights (for the final-setting cards).
 *
 * Asked of the list the run's final setting built, when there is a run, so the
 * team's own panel is named from the list it actually invited. A setting
 * deleted since the run is refused by the list route and falls back below.
 *
 * A failure here is not a failure of the results screen: the counts and the
 * comparison are the lesson, and the names are the illustration. So a refusal
 * on the list leaves both maps empty and the panels fall back to profile
 * numbers (and the setting cards to their names alone), rather than taking the
 * whole screen down.
 */
async function listForEvent(
  eventKey: string,
  settingName: string | null,
  signal: AbortSignal,
): Promise<{ readonly names: NamesByProfileNo; readonly labels: FactorLabels }> {
  const weighting: ListWeighting =
    settingName === null ? { kind: "default" } : { kind: "setting", name: settingName };
  try {
    const list = await readRankedList(eventKey, weighting, signal);
    return {
      names: new Map(list.entries.map((entry) => [entry.profile_no, entry.display_name])),
      labels: list.factor_labels ?? {},
    };
  } catch (error) {
    // An abort is not a missing list — it is this load being replaced. It has
    // to propagate, or a superseded load resolves with an empty map and the
    // hook settles a stale answer over the live one.
    if (signal.aborted) {
      throw error;
    }
    return { names: new Map(), labels: {} };
  }
}

/**
 * Whether results are open for this event and whether this team has run them,
 * from the events read (issue #328).
 *
 * Like the names, this is not what the screen stands on: a read that fails, or
 * a file that does not list the event, answers `null` and the run button
 * behaves as it did before this read existed — live, with the server deciding.
 * Losing access is different: that is the screen's refusal, and it propagates.
 */
async function eventResultsState(
  eventKey: string,
  signal: AbortSignal,
): Promise<EventResultsState | null> {
  try {
    const { events } = await readEvents(signal);
    const found = events.find((event) => event.event_key === eventKey);
    if (found === undefined) {
      return null;
    }
    // Compared with `false`/`true` so a server that predates the two fields
    // reads as "open, not run", which is how the screen behaved then.
    return { name: found.name, open: found.results_open !== false, run: found.results_run === true };
  } catch (error) {
    if (signal.aborted || isAccessRefusal(error)) {
      throw error;
    }
    return null;
  }
}

/** Which of the screen's actions is in flight; one at a time. */
type Pending = "run" | "ask" | null;

interface ShownRefusal {
  /** The refusal's code, or `null` for a transport failure. */
  readonly code: string | null;
  readonly message: string;
}

/** The three refresh counts as one sentence, in the asking screen's words. */
function refreshCountsSentence(counts: RefreshCountsView): string {
  return `Your team asked. Cards filled in: ${counts.cards_completed}. Stopped opening messages: ${counts.non_responding}. Picked up the first event's topics: ${counts.topics_added}.`;
}

function ResultsBody({
  eventKey,
  data,
  onChanged,
  confirmedResults,
  onResultsConfirmed,
  confirmedRefresh,
  onRefreshConfirmed,
  trustConfirmed,
  onAccessLost,
}: {
  readonly eventKey: string;
  readonly data: ResultsData;
  /** Re-read the screen; resolves once the new read has landed. */
  readonly onChanged: () => Promise<void>;
  /** The run this browser's POST was answered with, owned by the screen. */
  readonly confirmedResults: ResultsView | null;
  readonly onResultsConfirmed: (view: ResultsView) => void;
  /** The refresh this browser's POST was answered with, owned by the screen. */
  readonly confirmedRefresh: RefreshView | null;
  readonly onRefreshConfirmed: (view: RefreshView) => void;
  /**
   * `data` may be older than this browser's own confirmed press, so the
   * confirmed answers above stand in for it until a later read lands.
   */
  readonly trustConfirmed: boolean;
  readonly onAccessLost: (refusal: ExerciseRefusal) => void;
}): React.JSX.Element {
  const [pending, setPending] = React.useState<Pending>(null);
  const [refusal, setRefusal] = React.useState<ShownRefusal | null>(null);
  const [finalSetting, setFinalSetting] = React.useState("");
  // True once this screen's own run succeeds: the results that arrive next
  // play the seat fill (§5.1). A later visit mounts with it false.
  const [justRan, setJustRan] = React.useState(false);
  /**
   * Set synchronously, before any render: two presses in one tick both read
   * `pending` as `null`, so the state alone cannot keep a once-only POST from
   * going out twice.
   */
  const inFlight = React.useRef(false);

  async function act(which: Exclude<Pending, null>, action: () => Promise<void>): Promise<void> {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(which);
    try {
      await action();
      setRefusal(null);
    } catch (error) {
      if (isAccessRefusal(error)) {
        onAccessLost(error);
        return;
      }
      // Every results refusal is a state, not an error: locked, already run,
      // and the rule not yet confirmed are all the product working. Each is
      // shown as the server's own sentence. The previous one stays on screen
      // until this answer replaces it, so a retry does not blink it away.
      setRefusal(
        isRefusal(error)
          ? { code: error.code, message: error.message }
          : {
              code: null,
              message: "The exercise could not be reached. Check the connection and try again.",
            },
      );
      // "Not open" and "already run" mean this screen was behind: results
      // were closed, or the run was used from another tab. The sentence says
      // why nothing happened; the re-read puts the button in the right state.
      if (isRefusal(error) && (error.code === LOCKED || error.code === ALREADY_RUN)) {
        void onChanged();
      }
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  function runFinalSetting(): void {
    void act("run", async () => {
      let view: ResultsView;
      try {
        view = await runResults(eventKey, finalSetting);
      } catch (error) {
        // The chosen name was deleted since this screen loaded: clear it and
        // re-read the list, so the picker only offers names the run route can
        // still find. The sentence still shows.
        if (isRefusal(error) && error.code === SETTING_UNKNOWN) {
          setFinalSetting("");
          void onChanged();
        }
        throw error;
      }
      onResultsConfirmed(view);
      setJustRan(true);
      // Held until the re-read lands, so the run cannot be pressed again in
      // between; the confirmed run stands in if that read cannot be reached.
      await onChanged();
    });
  }

  /** The run and the refresh, by the server's latest read or this browser's own confirmed press. */
  const results = data.results ?? (trustConfirmed ? confirmedResults : null);
  const hasAsked = data.asking.refreshed || (trustConfirmed && confirmedRefresh !== null);
  const counts: RefreshCountsView | null = data.asking.refreshed
    ? (data.asking.refresh_counts ?? confirmedRefresh)
    : trustConfirmed
      ? confirmedRefresh
      : null;
  const canRefresh = data.asking.choice !== null && !hasAsked;
  // Run wins over open: results closed again after a run still read as run.
  const hasRun = results !== null || data.event?.run === true;
  const refusedAsLocked = refusal?.code === LOCKED;
  const notOpen = !hasRun && (data.event === null ? refusedAsLocked : !data.event.open);
  // The lock panel carries the sentence, so the notice does not repeat it.
  const lockSentence =
    data.event === null ? (refusal?.message ?? "") : notOpenSentence(data.event.name);

  return (
    <div className="flex flex-col gap-ce-6 md:gap-ce-7">
      {refusal === null || (refusedAsLocked && notOpen) ? null : (
        <ExerciseNotice message={refusal.message} />
      )}

      {hasRun ? (
        <div className="flex flex-col items-start gap-ce-2" data-slot="exercise-results-run-used">
          <Button variant="primary" disabled describedBy={ALREADY_RUN_REASON}>
            Results already run for this event.
          </Button>
          <p id={ALREADY_RUN_REASON} className="ce-type-meta text-ce-ink-muted">
            A team runs results once per event.
          </p>
        </div>
      ) : null}

      {results !== null ? (
        <ResultPanels results={results} names={data.names} reveal={justRan} />
      ) : hasRun ? null : (
        <section className="flex flex-col gap-ce-5">
          {/* §7.8: before a run, the lock panel takes the seating chart's
              place. "Check again" is a read of the lock, never the run. */}
          {notOpen ? (
            <ResultsLockPanel message={lockSentence} messageId={NOT_OPEN_REASON}>
              <Button
                variant="secondary"
                disabled={pending !== null}
                onClick={() => {
                  setRefusal(null);
                  void onChanged();
                }}
              >
                Check again
              </Button>
            </ResultsLockPanel>
          ) : null}
          <p className="ce-type-body ce-measure text-ce-ink-muted">
            Your team has not run results for this event yet. A team runs them once.
          </p>
          <FinalSettingChoice
            eventKey={eventKey}
            saved={data.saved}
            labels={data.labels}
            value={finalSetting}
            onChange={setFinalSetting}
          />
          {notOpen ? (
            <div>
              <Button variant="primary" disabled describedBy={NOT_OPEN_REASON}>
                Results not open yet.
              </Button>
            </div>
          ) : (
            <RunButton
              eventName={data.event?.name ?? null}
              finalSetting={finalSetting}
              running={pending === "run"}
              busy={pending !== null && pending !== "run"}
              onRun={runFinalSetting}
            />
          )}
        </section>
      )}

      <section className="ce-card flex flex-col gap-ce-4 p-ce-4 md:p-ce-6">
        <h2 className="ce-type-h2 text-ce-ink">Ask the people your team invited</h2>
        {data.asking.choice === null ? (
          <p className="ce-type-body ce-measure text-ce-ink">
            Your team has not picked a way of asking yet.{" "}
            <Link to="/exercise/asking">Pick one first</Link>.
          </p>
        ) : (
          <div className="flex flex-col items-start gap-ce-2">
            <Button
              variant="secondary"
              disabled={!canRefresh || (pending !== null && pending !== "ask")}
              pending={pending === "ask"}
              onClick={() =>
                void act("ask", async () => {
                  onRefreshConfirmed(await refreshProfiles());
                  await onChanged();
                })
              }
            >
              {hasAsked ? "Your team has already asked" : "Ask them now"}
            </Button>
            <p className="ce-type-meta text-ce-ink-muted">Your team may ask once.</p>
            {/* Always present, so the counts are announced when they arrive. */}
            <p
              role="status"
              data-slot="exercise-results-refresh-counts"
              className="ce-type-body text-ce-ink"
            >
              {counts === null ? "" : refreshCountsSentence(counts)}
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

/**
 * The live run button, with its inline confirm (`ce-confirm-window`, §5).
 *
 * Ann's checklist of 2026-10-02: "The screen asks “Send this list? You get one
 * results run for Northline” before running." The first press arms the button
 * and sends nothing; it then reads as that question, and a second press inside
 * five seconds sends the run. Escape, waiting, or choosing a different final
 * setting puts it back. A held Enter or Space never confirms: the run is once
 * per team, and a key repeat must not spend it.
 *
 * Off until a final setting is chosen, with the picker's line as the reason.
 */
function RunButton({
  eventName,
  finalSetting,
  running,
  busy,
  onRun,
}: {
  /** The event's label for the question, or `null` when the screen does not know it. */
  readonly eventName: string | null;
  readonly finalSetting: string;
  /** The run is in flight. */
  readonly running: boolean;
  /** Another action on the screen is in flight. */
  readonly busy: boolean;
  readonly onRun: () => void;
}): React.JSX.Element {
  const reduced = usePrefersReducedMotion();
  const confirm = useConfirmWindow({ onConfirm: onRun });
  const { cancel } = confirm;
  // The question is about the list on screen: a different setting is a
  // different list, so it has to be asked again.
  React.useEffect(() => cancel, [cancel, finalSetting]);
  // Once the run is on its way the question has been answered; a stray press
  // in the same tick must not leave the button armed for the next one.
  React.useEffect(() => {
    if (running) {
      cancel();
    }
  }, [cancel, running]);
  const armed = confirm.armed && !running;
  const question = sendListQuestion(eventName);

  return (
    <div className="flex flex-col items-start gap-ce-2">
      <Button
        variant="primary"
        disabled={finalSetting === "" || busy}
        pending={running}
        pendingLabel="Running…"
        describedBy={FINAL_SETTING_HINT}
        onClick={confirm.press}
        onKeyDown={(event) => {
          if (event.repeat && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            return;
          }
          confirm.onKeyDown(event);
        }}
      >
        <span className="inline-flex flex-col items-stretch">
          <span>{armed ? question : "Run results for this event"}</span>
          <ConfirmWindowUnderline active={armed && !reduced} reduced={false} />
        </span>
      </Button>
      <ConfirmWindowUnderline active={armed && reduced} reduced className="text-ce-ink-muted" />
      {/* Always present, so the question is announced when the button arms. */}
      <p role="status" data-slot="exercise-results-run-confirm" className="ce-type-meta text-ce-ink-muted">
        {armed ? "Press again to send this list. Your team cannot run this event a second time." : ""}
      </p>
    </div>
  );
}

/**
 * Step three of the owner's flow: the team's one final setting for this event
 * (DESIGN.md §6.13 — radio cards, not a `<select>`).
 *
 * The choices are the team's saved settings, read from the server, so a name
 * here is always one the run route can find. Nothing is chosen for the team,
 * even when it has saved only one: choosing is the step. Each card shows the
 * setting's four weights in Ann's words from `factor_labels`; with no words to
 * hand (the list read failed) it shows the name alone, never a rulebook key.
 */
function FinalSettingChoice({
  eventKey,
  saved,
  labels,
  value,
  onChange,
}: {
  readonly eventKey: string;
  readonly saved: SavedSettingsView | null;
  readonly labels: FactorLabels;
  readonly value: string;
  readonly onChange: (value: string) => void;
}): React.JSX.Element {
  const settings = saved?.settings ?? [];
  if (settings.length === 0) {
    return (
      <div className="flex flex-col gap-ce-4" data-slot="exercise-final-setting">
        <h2 className="ce-type-h2 text-ce-ink">Your team's final setting</h2>
        <div className="ce-card flex flex-col gap-ce-4 p-ce-4 sm:flex-row sm:items-center md:gap-ce-6 md:p-ce-6">
          <ProfileCardArt className="h-auto w-20 shrink-0 text-ce-primary md:w-24" />
          <p id={FINAL_SETTING_HINT} className="ce-type-body ce-measure text-ce-ink">
            Your team has not saved any settings for this event yet. Save one on{" "}
            <Link to={`/exercise/events/${encodeURIComponent(eventKey)}`}>your team's list</Link>{" "}
            first, then choose it here as your final setting.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-ce-4" data-slot="exercise-final-setting">
      <div className="flex flex-col gap-ce-2">
        <h2 id={FINAL_SETTING_HEADING} className="ce-type-h2 text-ce-ink">
          Your team's final setting
        </h2>
        <p id={FINAL_SETTING_HINT} className="ce-type-body ce-measure text-ce-ink-muted">
          Your team's invited list is built from the setting you choose. Choose one to run
          results.
        </p>
      </div>
      <div
        role="radiogroup"
        aria-labelledby={FINAL_SETTING_HEADING}
        className="grid gap-ce-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-ce-5"
      >
        {settings.map((setting, index) => (
          <SettingCard
            key={setting.name}
            id={`exercise-final-setting-${index}`}
            setting={setting}
            labels={labels}
            checked={value === setting.name}
            onChange={onChange}
          />
        ))}
      </div>
    </div>
  );
}

function SettingCard({
  id,
  setting,
  labels,
  checked,
  onChange,
}: {
  readonly id: string;
  readonly setting: SavedSettingView;
  readonly labels: FactorLabels;
  readonly checked: boolean;
  readonly onChange: (value: string) => void;
}): React.JSX.Element {
  const rows = EXERCISE_FACTOR_KEYS.flatMap((key) => {
    const label = labels[key];
    const weight = setting.weights[key];
    return typeof label === "string" && typeof weight === "number" ? [{ key, label, weight }] : [];
  });
  const nameId = `${id}-name`;
  const weightsId = `${id}-weights`;
  return (
    <label
      htmlFor={id}
      className={cn(
        "ce-card ce-lift flex min-w-0 cursor-pointer flex-col gap-ce-3 p-ce-4 md:p-ce-5",
        checked && "bg-ce-primary-tint outline-[3px] outline-offset-0 outline-ce-primary outline-solid",
      )}
    >
      <span className="flex items-start justify-between gap-ce-3">
        <span id={nameId} className="ce-type-h3 min-w-0 break-words text-ce-ink">
          {setting.name}
        </span>
        <input
          type="radio"
          id={id}
          name="exercise-final-setting"
          value={setting.name}
          checked={checked}
          onChange={() => onChange(setting.name)}
          aria-labelledby={nameId}
          aria-describedby={rows.length > 0 ? weightsId : undefined}
          className="mt-1 size-6 shrink-0 cursor-pointer accent-[var(--ce-primary)]"
        />
      </span>
      {rows.length === 0 ? null : (
        <dl id={weightsId} className="flex flex-col gap-ce-2">
          {rows.map((row) => (
            <div key={row.key} className="flex items-baseline justify-between gap-ce-3">
              <dt className="ce-type-body text-ce-ink-muted">{row.label}</dt>
              <dd className="ce-type-value ce-tabular text-ce-ink">{formatWeight(row.weight)}</dd>
            </div>
          ))}
        </dl>
      )}
    </label>
  );
}
