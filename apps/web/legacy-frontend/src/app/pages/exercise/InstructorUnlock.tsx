/**
 * The instructor's two class-wide actions: open or close results for an event,
 * and refresh every team at once. Moved out of `ExerciseInstructor.tsx` unchanged in
 * behaviour for the invitation-desk layout (DESIGN.md §6.24, §7.11).
 */
import * as React from "react";
import { Lock, LockOpen } from "lucide-react";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  listInstructorEvents,
  lockResults,
  refreshAllWorkspaces,
  unlockResults,
  type InstructorEventView,
  type RefreshAllView,
} from "../../../lib/exerciseClient";
import { refreshAllHeadline, refreshAllTeamLine } from "./refreshWording";
import { cn } from "../../components/ui/utils";
import { Button, Notice } from "./desk";
import { EventDescription } from "./EventDescription";
import { ExerciseNotice } from "./ExerciseScreen";
import { clockTime } from "./exerciseTime";
import { useSignOutOnExpiredRead } from "./instructorSession";
import { INSTRUCTOR_WELL, PanelCard, PanelSkeleton } from "./instructorUi";
import { INSTRUCTOR_SESSION_REQUIRED, TEAMS_SPAN_DATASETS } from "./refusals";
import { useExerciseResource } from "./useExerciseResource";

/** The page's sentence for a request that never landed. */
const UNREACHABLE = "The exercise could not be reached. Check the connection and try again.";

/** What a row's confirm is asking about. */
type LockAction = "open" | "close";

/**
 * Open results for one event, or close them again (Ann, 2026-10-02: "results
 * can be closed again"). Idempotent: a second press says the same thing.
 *
 * **Closing asks first too, in the row**: "Close results for {event}? …" with
 * "Close results now" and "Keep them open". Closing deletes nothing — a team
 * that already ran keeps its results — and the sentence says so. Each row
 * shows the time its state was last changed ("Opened at 10:42 AM.").
 *
 * The list is `GET …/instructor/events`, behind the passcode session alone. It
 * used to be the team route, which needs a workspace cookie, so an instructor
 * who had not entered as a team saw no events at all. "Results open" is
 * the server's `unlocked` flag rather than local state, so it survives a
 * reload, and the list is re-read after every unlock.
 *
 * The server resolves the list exactly as it resolves the unlock — the file
 * the teams are on — and its `dataset_id` is passed back on every press, so
 * the list and the button cannot address two different files. When no file
 * can be resolved the server's own sentence is shown, with "Check again": the
 * instructor usually signs in before any team has entered, and nothing else
 * on the page would re-read this list once one has. A refused unlock re-reads
 * too, because the likeliest cause is a re-point made somewhere else, and once
 * that re-read lands the page-top sentence about the refused press is cleared:
 * it described the list as it was, and the list on screen is now the new one.
 *
 * **Teams split across two files get this panel's own sentence.** The server's
 * asks the instructor to "choose which one this applies to", which is right on
 * routes that take a file, but this panel has nothing to choose with: the
 * unlock is meant for the file the whole class is on (D11), and a picker would
 * open results for half a class. The fix is a re-point, so the sentence says
 * where that button is. Branching on the stable `code`, as the refusal rule
 * allows; the server's wording stays untouched everywhere else.
 *
 * **Opening asks first, inline** (DESIGN.md §11.1): "Open results" becomes
 * "Open results for {event}? Every team can then run results once for this
 * event." with "Open results now" and "Not yet". Only "Open results now" sends
 * the unlock; "Not yet" and Escape put the row back and send nothing. No
 * pop-up: the question sits in the row it is about.
 *
 * **An expired session signs the page out**, from the list read or from an
 * unlock, as every instructor panel does (`instructorSession.ts`).
 */
export function UnlockPanel({
  onRefusal,
  onUnlocked,
  onSignedOut,
  reloadKey,
}: {
  readonly onRefusal: (message: string | null) => void;
  /** Called after an unlock or a close lands, so the page can re-read the teams. */
  readonly onUnlocked: () => void;
  /** Called when the instructor session has expired; the page shows the passcode form. */
  readonly onSignedOut: () => void;
  readonly reloadKey: number;
}): React.JSX.Element {
  const { state, reload } = useExerciseResource(listInstructorEvents, [reloadKey]);
  useSignOutOnExpiredRead(state, onSignedOut);
  const [pending, setPending] = React.useState(false);
  /** Guards the unlock itself, so a second press in the same tick sends nothing. */
  const inFlight = React.useRef(false);
  /**
   * The confirm that is open, keyed on the data file, the event *and* whether
   * it asks to open or to close.
   *
   * It belongs to the list it was opened on. A re-read onto another file (an
   * upload or re-point landed) would otherwise leave "Open results now" on
   * screen addressing a file the instructor never saw asked about, and a
   * refused list followed by "Check again" would bring the confirm back with
   * focus on it, one Enter from an unlock.
   */
  const [confirming, setConfirming] = React.useState<string | null>(null);
  const listFile = state.status === "ready" ? state.data.dataset_id : null;
  React.useEffect(() => {
    if (listFile === null) {
      setConfirming(null);
    } else {
      setConfirming((open) =>
        open !== null && !open.startsWith(`${listFile}\n`) ? null : open,
      );
    }
  }, [listFile]);
  const busy =
    pending || state.status === "loading" || (state.status === "ready" && state.refreshing);

  /**
   * Set when an unlock is refused and the list is being re-read because of it.
   * The page-top sentence is cleared when that re-read lands with a list, and
   * kept when it does not: then the sentence is still the latest thing known.
   */
  const refusedUnlockPending = React.useRef(false);
  React.useEffect(() => {
    if (!refusedUnlockPending.current) {
      return;
    }
    if (state.status === "ready" && !state.refreshing) {
      refusedUnlockPending.current = false;
      onRefusal(null);
    } else if (state.status === "refused" || state.status === "unreachable") {
      refusedUnlockPending.current = false;
    }
  }, [state, onRefusal]);

  function change(action: LockAction, eventKey: string, datasetId: string): void {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(true);
    onRefusal(null);
    const sent: Promise<unknown> =
      action === "open" ? unlockResults(eventKey, datasetId) : lockResults(eventKey, datasetId);
    sent
      .then(() => {
        setConfirming(null);
        onUnlocked();
        return reload();
      })
      .catch((error: unknown) => {
        setConfirming(null);
        onRefusal(isRefusal(error) ? error.message : UNREACHABLE);
        if (isRefusal(error) && error.code === INSTRUCTOR_SESSION_REQUIRED) {
          onSignedOut();
          return undefined;
        }
        refusedUnlockPending.current = true;
        return reload();
      })
      .finally(() => {
        inFlight.current = false;
        setPending(false);
      });
  }

  const checkAgain = (
    <div>
      <Button variant="secondary" disabled={busy} onClick={() => void reload()}>
        Check again
      </Button>
    </div>
  );

  return (
    <PanelCard title="Open results for an event" slot="exercise-instructor-unlock">
      {state.status === "loading" ? <PanelSkeleton what="the events" /> : null}
      {state.status === "refused" ? (
        <>
          <ExerciseNotice
            message={
              state.refusal.code === TEAMS_SPAN_DATASETS
                ? SPLIT_ACROSS_FILES
                : state.refusal.message
            }
          />
          {checkAgain}
        </>
      ) : null}
      {state.status === "unreachable" ? (
        <>
          <ExerciseNotice message={state.message} tone="problem" />
          {checkAgain}
        </>
      ) : null}
      {state.status === "ready" && state.data.events.length === 0 ? (
        <>
          <p className="ce-type-body text-ce-ink-muted">
            {state.data.dataset_label} has no events for the teams to run.
          </p>
          {checkAgain}
        </>
      ) : null}
      {state.status === "ready" && state.data.events.length > 0 ? (
        <ul className="flex flex-col divide-y divide-ce-line">
          {state.data.events.map((event) => {
            const action = confirmedAction(confirming, state.data.dataset_id, event.event_key);
            return (
              <UnlockRow
                key={event.event_key}
                event={event}
                // A refresh in flight may be about to change `dataset_id`
                // (an upload or re-point just landed), so wait for it.
                disabled={pending || state.refreshing}
                pending={pending && action !== null}
                confirming={action}
                onAsk={(asked) =>
                  setConfirming(confirmKey(state.data.dataset_id, event.event_key, asked))
                }
                onCancel={() => setConfirming(null)}
                onConfirm={(asked) => change(asked, event.event_key, state.data.dataset_id)}
              />
            );
          })}
        </ul>
      ) : null}
    </PanelCard>
  );
}

/**
 * One event: its name, a lock chip in icon and words, the time its state last
 * changed, and "Open results" or "Close results". Either press asks first, in
 * the row (§11.1).
 *
 * The chip reads "Results closed" or "Results open" — Ann's checklist of
 * 2026-10-02, word for word — and the line under it says when: "Opened at
 * 10:42 AM." or "Closed at 10:50 AM.". An event never opened has no time.
 *
 * Focus is never dropped (§8.5). It moves to the confirming button when the
 * question appears. When the question goes away — "Not yet", "Keep them open",
 * Escape, a refused press, a list that moved on — and the focused button went
 * with it, focus returns to the row's own button. When the event's state
 * changes, focus lands on the event's name, which takes focus only from code:
 * never on the opposite action, so a repeated Enter cannot undo what was just
 * done.
 */
function UnlockRow({
  event,
  disabled,
  pending,
  confirming,
  onAsk,
  onCancel,
  onConfirm,
}: {
  readonly event: InstructorEventView;
  readonly disabled: boolean;
  /** This row's open or close is in flight. */
  readonly pending: boolean;
  /** Which question this row is asking, or `null`. */
  readonly confirming: LockAction | null;
  readonly onAsk: (action: LockAction) => void;
  readonly onCancel: () => void;
  readonly onConfirm: (action: LockAction) => void;
}): React.JSX.Element {
  const actionButton = React.useRef<HTMLButtonElement>(null);
  const confirmButton = React.useRef<HTMLButtonElement>(null);
  const nameAnchor = React.useRef<HTMLSpanElement>(null);
  // A question about a state the event is no longer in is not asked: opening
  // an event that is already open, or closing one that is already closed.
  const asking: LockAction | null =
    confirming === null ? null : (confirming === "open") === !event.unlocked ? confirming : null;
  const was = React.useRef({ asking, unlocked: event.unlocked });

  React.useEffect(() => {
    const before = was.current;
    was.current = { asking, unlocked: event.unlocked };
    if (asking !== null) {
      if (before.asking === null) {
        confirmButton.current?.focus();
      }
      return;
    }
    const changed = before.unlocked !== event.unlocked;
    if (changed) {
      // The row's button now offers the opposite action. Focus left on it (or
      // dropped with the confirm) goes to the name; focus elsewhere is left.
      if (focusWasDropped() || document.activeElement === actionButton.current) {
        nameAnchor.current?.focus();
      }
      return;
    }
    // Only when this row's own control just left the page with focus on it:
    // a list re-read must never pull focus from somewhere else.
    if (before.asking !== null && focusWasDropped()) {
      (actionButton.current ?? nameAnchor.current)?.focus();
    }
  }, [asking, event.unlocked]);

  const when = lockTimeSentence(event);

  return (
    <li className="flex flex-col gap-ce-3 py-ce-4 first:pt-ce-2 last:pb-ce-2">
      <div className="flex flex-wrap items-center gap-x-ce-4 gap-y-ce-3">
        <span
          ref={nameAnchor}
          tabIndex={-1}
          className="ce-type-body min-w-0 flex-1 basis-48 font-semibold text-ce-ink"
        >
          {event.name}
        </span>
        <span className="flex flex-col items-start gap-ce-1">
          <span
            className={cn(
              "ce-type-meta inline-flex items-center gap-ce-2 rounded-ce-pill px-ce-3 py-ce-1 text-ce-ink",
              event.unlocked
                ? "bg-ce-avocado-tint"
                : "border border-ce-line-strong bg-ce-surface-sunk",
            )}
          >
            {event.unlocked ? (
              <LockOpen aria-hidden="true" className="size-4 shrink-0 text-ce-primary" />
            ) : (
              <Lock aria-hidden="true" className="size-4 shrink-0 text-ce-ink-muted" />
            )}
            {event.unlocked ? "Results open" : "Results closed"}
          </span>
          {/* Always present, so the time is announced when the state changes. */}
          <span
            role="status"
            data-slot="exercise-instructor-lock-time"
            className="ce-type-meta ce-tabular text-ce-ink-muted"
          >
            {when ?? ""}
          </span>
        </span>
        {asking !== null ? null : (
          <Button
            ref={actionButton}
            variant="secondary"
            disabled={disabled}
            className="w-full sm:w-auto"
            onClick={() => onAsk(event.unlocked ? "close" : "open")}
          >
            {event.unlocked ? "Close results" : "Open results"}
          </Button>
        )}
      </div>
      {/* #318: the same description the teams read, beside the event it is about. */}
      <EventDescription text={event.description} />
      {asking === null ? null : (
        <div
          className={cn(INSTRUCTOR_WELL, "ce-fade-rise flex flex-col gap-ce-3")}
          onKeyDown={(keyEvent) => {
            if (keyEvent.key === "Escape" && !pending) {
              keyEvent.preventDefault();
              onCancel();
            }
          }}
        >
          <p className="ce-type-body text-ce-ink">
            {asking === "open"
              ? `Open results for ${event.name}? Every team can then run results once for this event.`
              : `Close results for ${event.name}? Teams that have not run results yet cannot run them until you open results again. Results already run stay on each team's screen.`}
          </p>
          <div className="flex flex-wrap items-center gap-ce-3">
            <Button
              ref={confirmButton}
              pending={pending}
              pendingLabel={asking === "open" ? "Opening…" : "Closing…"}
              disabled={disabled && !pending}
              className="w-full sm:w-auto"
              onClick={() => onConfirm(asking)}
            >
              {asking === "open" ? "Open results now" : "Close results now"}
            </Button>
            <Button variant="quiet" disabled={pending} onClick={onCancel}>
              {asking === "open" ? "Not yet" : "Keep them open"}
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

/**
 * "Opened at 10:42 AM." for an open event, "Closed at 10:50 AM." for one that
 * was closed again, and nothing for one that was never opened.
 */
function lockTimeSentence(event: InstructorEventView): string | null {
  const at = clockTime(event.unlocked ? event.unlocked_at : event.closed_at);
  if (at === null) {
    return null;
  }
  return event.unlocked ? `Opened at ${at}.` : `Closed at ${at}.`;
}

/** Whether the focused element was removed, leaving focus on `<body>`. */
function focusWasDropped(): boolean {
  const active = document.activeElement;
  return active === null || active === document.body || !active.isConnected;
}

/** One open confirm's key: the file, the event and the question, so it cannot outlive its file. */
function confirmKey(datasetId: string, eventKey: string, action: LockAction): string {
  return `${datasetId}\n${eventKey}\n${action}`;
}

/** Which question, if any, the open confirm is asking about this event of this file. */
function confirmedAction(
  confirming: string | null,
  datasetId: string,
  eventKey: string,
): LockAction | null {
  if (confirming === confirmKey(datasetId, eventKey, "open")) {
    return "open";
  }
  return confirming === confirmKey(datasetId, eventKey, "close") ? "close" : null;
}

/** This panel's sentence for teams split across files (see `UnlockPanel`). */
const SPLIT_ACROSS_FILES =
  "The teams are working in more than one data file. Under Data files, press " +
  "“Move every team to this file” on the file the class should use. This list reads again on its own once they move.";

/** What the every-team button does, on the button itself (DESIGN.md §11.1). */
export const REFRESH_ALL_LABEL = "Refresh every team that has chosen how to ask";

/**
 * Refresh every team that has chosen a way of asking and is not refreshed yet.
 *
 * Ann's review of 2026-10-02: the button's label "should say what it does",
 * and after running it "says … which teams were refreshed and which were
 * skipped and why", with "the same kind of summary for each team". So the
 * label names the action, and the answer is one line per team: the team's own
 * refresh summary, or the reason it was skipped. The server sends an outcome,
 * a reason code, a time and counts; `refreshWording.ts` writes the words.
 *
 * It is one request and all or nothing: if it is refused, no team is changed.
 * An expired session signs the page out.
 *
 * No "Are you sure?" step here: that is a separate change. `send` is the one
 * place the request is made, so a confirm can sit in front of it.
 */
export function RefreshAllPanel({
  onDone,
  onSignedOut,
}: {
  readonly onDone: () => void;
  /** Called when the instructor session has expired; the page shows the passcode form. */
  readonly onSignedOut: () => void;
}): React.JSX.Element {
  const [pending, setPending] = React.useState(false);
  const [done, setDone] = React.useState<RefreshAllView | null>(null);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  function send(): void {
    setPending(true);
    setRefusal(null);
    refreshAllWorkspaces()
      .then((view) => {
        setDone(view);
        onDone();
      })
      .catch((error: unknown) => {
        setRefusal(isRefusal(error) ? error.message : UNREACHABLE);
        if (isRefusal(error) && error.code === INSTRUCTOR_SESSION_REQUIRED) {
          onSignedOut();
        }
      })
      .finally(() => setPending(false));
  }

  return (
    <PanelCard title="Refresh every team at once" slot="exercise-instructor-refresh-all">
      <p className="ce-type-body ce-measure text-ce-ink-muted">
        This refreshes, in one go, every team that has chosen a way of asking and has not been
        refreshed yet. Teams that are not ready are skipped, and the list below says why. If it
        cannot be done, no team is changed.
      </p>
      <div>
        <Button
          variant="secondary"
          pending={pending}
          pendingLabel="Refreshing every team…"
          className="w-full sm:w-auto"
          onClick={send}
        >
          {REFRESH_ALL_LABEL}
        </Button>
      </div>
      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      {done === null ? null : <RefreshAllReport done={done} />}
    </PanelCard>
  );
}

/**
 * What the every-team refresh did: a headline, then one line per team in the
 * Teams panel's order. The team's name leads each line in bold so a row can be
 * found by eye; the reason is words, never a colour.
 */
function RefreshAllReport({ done }: { readonly done: RefreshAllView }): React.JSX.Element {
  const teams = done.teams ?? [];
  // A file's label is not unique, so the label says nothing about how many
  // files there are. A repeated team number is what needs telling apart.
  const repeated = new Set(teams.map((team) => team.team_number)).size < teams.length;
  return (
    <Notice tone="done" message={refreshAllHeadline(done)}>
      {teams.length === 0 ? undefined : (
        <ul data-slot="exercise-refresh-all-teams" className="ce-type-body flex flex-col gap-ce-2">
          {teams.map((team, index) => {
            const line = refreshAllTeamLine(team, { nameFile: repeated });
            return (
              <li
                // The report is one fixed answer, so its order is its identity.
                key={index}
                data-outcome={team.outcome}
                data-reason={team.reason_code ?? undefined}
              >
                <span className="font-semibold">{line.team}</span> {line.what}
              </li>
            );
          })}
        </ul>
      )}
    </Notice>
  );
}
