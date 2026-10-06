/**
 * The instructor's two class-wide actions: open results for an event, and
 * refresh every team at once. Moved out of `ExerciseInstructor.tsx` unchanged in
 * behaviour for the invitation-desk layout (DESIGN.md §6.24, §7.11).
 */
import * as React from "react";
import { Lock, LockOpen } from "lucide-react";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  listInstructorEvents,
  refreshAllWorkspaces,
  unlockResults,
  type InstructorEventView,
  type RefreshAllView,
} from "../../../lib/exerciseClient";
import { refreshAllHeadline, refreshAllTeamLine } from "./refreshWording";
import { cn } from "../../components/ui/utils";
import { Button, Notice } from "./desk";
import { ExerciseNotice } from "./ExerciseScreen";
import { useSignOutOnExpiredRead } from "./instructorSession";
import { INSTRUCTOR_WELL, PanelCard, PanelSkeleton } from "./instructorUi";
import { INSTRUCTOR_SESSION_REQUIRED, TEAMS_SPAN_DATASETS } from "./refusals";
import { useExerciseResource } from "./useExerciseResource";

/** The page's sentence for a request that never landed. */
const UNREACHABLE = "The exercise could not be reached. Check the connection and try again.";

/**
 * Open results for one event. Idempotent: a second press says the same thing.
 *
 * The list is `GET …/instructor/events`, behind the passcode session alone. It
 * used to be the team route, which needs a workspace cookie, so an instructor
 * who had not entered as a team saw no events at all. "Results are open" is
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
  /** Called after an unlock lands, so the page can re-read the teams. */
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
   * The confirm that is open, keyed on the data file *and* the event.
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

  function unlock(eventKey: string, datasetId: string): void {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(true);
    onRefusal(null);
    unlockResults(eventKey, datasetId)
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
            const key = confirmKey(state.data.dataset_id, event.event_key);
            return (
              <UnlockRow
                key={event.event_key}
                event={event}
                // A refresh in flight may be about to change `dataset_id`
                // (an upload or re-point just landed), so wait for it.
                disabled={pending || state.refreshing}
                pending={pending && confirming === key}
                confirming={confirming === key}
                onAsk={() => setConfirming(key)}
                onCancel={() => setConfirming(null)}
                onUnlock={() => unlock(event.event_key, state.data.dataset_id)}
              />
            );
          })}
        </ul>
      ) : null}
    </PanelCard>
  );
}

/**
 * One event: its name, a lock chip in icon and words, and "Open results" until
 * it is open. Pressing "Open results" asks first, in the row (§11.1).
 *
 * Focus is never dropped (§8.5). It moves to "Open results now" when the
 * question appears. When the question goes away — "Not yet", Escape, a refused
 * unlock, a list that moved on — and the focused button went with it, focus
 * returns to "Open results". When the event opens and that button goes too,
 * focus lands on the event's name, which takes focus only from code.
 */
function UnlockRow({
  event,
  disabled,
  pending,
  confirming,
  onAsk,
  onCancel,
  onUnlock,
}: {
  readonly event: InstructorEventView;
  readonly disabled: boolean;
  /** This row's unlock is in flight. */
  readonly pending: boolean;
  readonly confirming: boolean;
  readonly onAsk: () => void;
  readonly onCancel: () => void;
  readonly onUnlock: () => void;
}): React.JSX.Element {
  const openButton = React.useRef<HTMLButtonElement>(null);
  const confirmButton = React.useRef<HTMLButtonElement>(null);
  const nameAnchor = React.useRef<HTMLSpanElement>(null);
  const was = React.useRef({ confirming, unlocked: event.unlocked });

  React.useEffect(() => {
    const before = was.current;
    was.current = { confirming, unlocked: event.unlocked };
    if (confirming) {
      if (!before.confirming) {
        confirmButton.current?.focus();
      }
      return;
    }
    const closed = before.confirming;
    const opened = !before.unlocked && event.unlocked;
    // Only when this row's own control just left the page with focus on it:
    // a list re-read must never pull focus from somewhere else.
    if ((closed || opened) && focusWasDropped()) {
      (openButton.current ?? nameAnchor.current)?.focus();
    }
  }, [confirming, event.unlocked]);

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
        <span
          className={cn(
            "ce-type-meta inline-flex items-center gap-ce-2 rounded-ce-pill px-ce-3 py-ce-1 text-ce-ink",
            event.unlocked ? "bg-ce-avocado-tint" : "border border-ce-line-strong bg-ce-surface-sunk",
          )}
        >
          {event.unlocked ? (
            <LockOpen aria-hidden="true" className="size-4 shrink-0 text-ce-primary" />
          ) : (
            <Lock aria-hidden="true" className="size-4 shrink-0 text-ce-ink-muted" />
          )}
          {event.unlocked ? "Results are open" : "Results are closed"}
        </span>
        {event.unlocked || confirming ? null : (
          <Button
            ref={openButton}
            variant="secondary"
            disabled={disabled}
            className="w-full sm:w-auto"
            onClick={onAsk}
          >
            Open results
          </Button>
        )}
      </div>
      {confirming && !event.unlocked ? (
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
            Open results for {event.name}? Every team can then run results once for this event.
          </p>
          <div className="flex flex-wrap items-center gap-ce-3">
            <Button
              ref={confirmButton}
              pending={pending}
              pendingLabel="Opening…"
              disabled={disabled && !pending}
              className="w-full sm:w-auto"
              onClick={onUnlock}
            >
              Open results now
            </Button>
            <Button variant="quiet" disabled={pending} onClick={onCancel}>
              Not yet
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

/** Whether the focused element was removed, leaving focus on `<body>`. */
function focusWasDropped(): boolean {
  const active = document.activeElement;
  return active === null || active === document.body || !active.isConnected;
}

/** One open confirm's key: the file and the event, so it cannot outlive its file. */
function confirmKey(datasetId: string, eventKey: string): string {
  return `${datasetId}\n${eventKey}`;
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
