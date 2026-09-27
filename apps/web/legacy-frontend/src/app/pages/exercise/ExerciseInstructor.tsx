/**
 * The instructor page: passcode, data files, unlocking, teams.
 *
 * Design spec §14 lists the powers exactly: *"list workspaces and open any
 * team's saved settings and results; unlock results per event; set the invite
 * limit; upload a data file; refresh all; reset one team."* All six are here,
 * and the per-team reset is here and nowhere else.
 *
 * **Signing out clears this browser's copy of the session, and nothing more.**
 * Design spec §14's "As shipped" note: the session is a signed cookie with no
 * server-side row and no revocation before its twelve-hour expiry. So the
 * button says what it does. Promising "signed out everywhere" would be a
 * promise the product cannot keep.
 *
 * **Refresh all is all-or-nothing, and says so in the server's words when it
 * has them.** It refreshes every team that has chosen a way of asking and has
 * not yet asked, skipping the rest, and reports both counts.
 *
 * There is no portal shell here either. The passcode gates the *API*; this
 * page renders whatever the server answers, including its refusals, rather
 * than hiding controls and implying a capability is absent — the same rule the
 * CBA portal's pages follow for a different reason.
 */
import * as React from "react";
import { Eye, EyeOff, KeyRound, Lock, LockOpen, LogOut } from "lucide-react";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  instructorLogin,
  instructorLogout,
  listInstructorEvents,
  listTeamWorkspaces,
  refreshAllWorkspaces,
  unlockResults,
  type InstructorEventView,
  type RefreshAllView,
} from "../../../lib/exerciseClient";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ceButton, Chip, Spinner } from "./exerciseUi";
import { InstructorDatasets } from "./InstructorDatasets";
import { InstructorTeams } from "./InstructorTeams";
import { INSTRUCTOR_SESSION_REQUIRED, TEAMS_SPAN_DATASETS } from "./refusals";
import { useExerciseResource } from "./useExerciseResource";

/** Whether this browser's instructor cookie is still good. */
type SessionProbe = "checking" | "signed-in" | "signed-out";

export function ExerciseInstructor(): React.JSX.Element {
  /**
   * Ask the server whether this browser is already signed in.
   *
   * The session is a signed cookie with a twelve-hour life and no server-side
   * row, and it is `httpOnly`, so JavaScript cannot look at it. Seeding this
   * to "signed out" meant a reload — or an instructor reopening the page
   * between classes — was asked for the passcode again, with a live session
   * sitting in the browser the whole time.
   *
   * There is no session-probe route, and this PR adds no backend. So the probe
   * is an ordinary gated read: `GET …/instructor/workspaces` is behind
   * `require_instructor_session` like every other instructor route, so its
   * answer *is* the session's state. 200 means signed in; a 401
   * `exercise_instructor_session_required` means the passcode form. Anything
   * else is left as signed out, because a page that cannot reach the server
   * has nothing to show behind the passcode either.
   */
  const [probe, setProbe] = React.useState<SessionProbe>("checking");

  React.useEffect(() => {
    const controller = new AbortController();
    listTeamWorkspaces(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) {
          setProbe("signed-in");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setProbe("signed-out");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <ExerciseScreen
      title="Instructor"
      intro="Load a data file, open results for an event, and see what each team has done."
      centered={probe === "signed-out"}
    >
      {probe === "checking" ? <ExerciseLoading what="the instructor page" /> : null}
      {probe === "signed-in" ? <SignedIn onSignedOut={() => setProbe("signed-out")} /> : null}
      {probe === "signed-out" ? (
        <PasscodeForm onSignedIn={() => setProbe("signed-in")} />
      ) : null}
    </ExerciseScreen>
  );
}

/**
 * The passcode card (DESIGN.md §7.11, §6.24): centred, 480px, a `KeyRound`,
 * one field with a show/hide toggle, one primary action, and the §11.1 helper
 * saying what the passcode is not.
 */
function PasscodeForm({ onSignedIn }: { readonly onSignedIn: () => void }): React.JSX.Element {
  const [passcode, setPasscode] = React.useState("");
  const [shown, setShown] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  return (
    <form
      className="ce-card mx-auto flex w-full max-w-[480px] flex-col gap-4 p-6 md:p-8"
      onSubmit={(event) => {
        event.preventDefault();
        if (pending || passcode === "") {
          return;
        }
        setPending(true);
        setRefusal(null);
        instructorLogin(passcode)
          .then(() => {
            setPasscode("");
            onSignedIn();
          })
          .catch((error: unknown) => {
            // The server deliberately gives one sentence for every way a
            // passcode can fail, so the answer cannot be used to learn whether
            // this deployment has an instructor page at all. It is shown as-is.
            setRefusal(
              isRefusal(error)
                ? error.message
                : "The exercise could not be reached. Check the connection and try again.",
            );
          })
          .finally(() => setPending(false));
      }}
    >
      <span
        aria-hidden="true"
        className="flex size-12 items-center justify-center rounded-[10px] bg-ce-primary-tint text-ce-primary"
      >
        <KeyRound className="size-6" />
      </span>
      <div className="flex flex-col gap-2">
        <label htmlFor="exercise-passcode" className="ce-label text-ce-ink">
          Passcode
        </label>
        <div className="relative">
          <input
            id="exercise-passcode"
            type={shown ? "text" : "password"}
            autoComplete="current-password"
            value={passcode}
            aria-describedby="exercise-passcode-help"
            onChange={(event) => setPasscode(event.target.value)}
            className="ce-input w-full pr-14"
          />
          <button
            type="button"
            aria-pressed={shown}
            // Named without the field's word, so the field keeps the one label.
            aria-label={shown ? "Hide what is typed" : "Show what is typed"}
            onClick={() => setShown((value) => !value)}
            className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-r-[10px] text-ce-muted hover:text-ce-primary"
          >
            {shown ? (
              <EyeOff aria-hidden="true" className="size-5" />
            ) : (
              <Eye aria-hidden="true" className="size-5" />
            )}
          </button>
        </div>
      </div>
      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      <button
        type="submit"
        disabled={pending || passcode === ""}
        className={ceButton("primary", "ce-btn-lg w-full")}
      >
        {pending ? <Spinner /> : null}
        {pending ? "Checking…" : "Open the instructor page"}
      </button>
      <p id="exercise-passcode-help" className="ce-meta text-center text-ce-muted">
        The passcode is shared by the course team. It is not your university login.
      </p>
    </form>
  );
}

function SignedIn({ onSignedOut }: { readonly onSignedOut: () => void }): React.JSX.Element {
  const [refusal, setRefusal] = React.useState<string | null>(null);
  /**
   * Bumped when an upload or a re-point lands. The teams list and the unlock
   * panel read facts those two change, and each used to keep its first answer
   * until the page was reloaded.
   */
  const [dataVersion, setDataVersion] = React.useState(0);
  const dataChanged = React.useCallback(() => setDataVersion((version) => version + 1), []);
  /**
   * Bumped when an action changes what the Teams panel says but not the data
   * files or the unlock list: "Ask for every team" and a successful unlock.
   * Kept apart from `dataVersion` so an unlock does not re-read its own panel
   * twice.
   */
  const [teamsVersion, setTeamsVersion] = React.useState(0);
  const teamsChanged = React.useCallback(() => setTeamsVersion((version) => version + 1), []);

  /**
   * Any instructor action, with the session's own 401 handled once.
   *
   * A signed cookie expires without telling anybody, so the first call after
   * twelve hours is where the page finds out. It returns to the passcode form
   * and shows the server's sentence rather than leaving controls on screen
   * that will all fail the same way.
   */
  function guard(action: () => Promise<void>): void {
    setRefusal(null);
    action().catch((error: unknown) => {
      if (isRefusal(error)) {
        setRefusal(error.message);
        if (error.code === INSTRUCTOR_SESSION_REQUIRED) {
          onSignedOut();
        }
        return;
      }
      setRefusal("The exercise could not be reached. Check the connection and try again.");
    });
  }

  // §7.11: two columns, 8/4. Left: unlock, teams, ask-for-all. Right, sticky:
  // data files and sign out. On a phone the same order stacks.
  return (
    <div className="grid items-start gap-6 lg:grid-cols-12 lg:gap-8">
      <div className="flex min-w-0 flex-col gap-6 lg:col-span-8 lg:gap-8">
        {refusal === null ? null : <ExerciseNotice message={refusal} />}
        <UnlockPanel onRefusal={setRefusal} onUnlocked={teamsChanged} reloadKey={dataVersion} />
        {/* A sum, so a bump to either re-reads the teams. */}
        <InstructorTeams reloadKey={dataVersion + teamsVersion} onSignedOut={onSignedOut} />
        <RefreshAllPanel onDone={teamsChanged} />
      </div>
      <div className="flex min-w-0 flex-col gap-6 lg:sticky lg:top-6 lg:col-span-4">
        <InstructorDatasets onDataChanged={dataChanged} />
        <section className="ce-card flex flex-col items-start gap-2 p-5 md:p-6">
          <button
            type="button"
            className={ceButton("quiet", "min-h-11 px-0")}
            onClick={() =>
              guard(async () => {
                await instructorLogout();
                onSignedOut();
              })
            }
          >
            <LogOut aria-hidden="true" className="size-5" />
            Sign out of this browser
          </button>
          <p className="ce-meta text-ce-muted">
            {/* §14 as shipped: no server-side session row, no revocation before expiry. */}
            This clears the passcode from this browser only. It does not sign out anywhere else.
          </p>
        </section>
      </div>
    </div>
  );
}

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
 * **Opening asks first, inline** (DESIGN.md §11.1): "Open results" becomes a
 * line "Open results for Harbor Consumer Brands? Every team can then run
 * results once for this event." with "Open results now" and "Not yet". Once
 * open, the row shows a `LockOpen` chip "Results are open" and no button.
 */
function UnlockPanel({
  onRefusal,
  onUnlocked,
  reloadKey,
}: {
  readonly onRefusal: (message: string | null) => void;
  /** Called after an unlock lands, so the page can re-read the teams. */
  readonly onUnlocked: () => void;
  readonly reloadKey: number;
}): React.JSX.Element {
  const { state, reload } = useExerciseResource(listInstructorEvents, [reloadKey]);
  const [pending, setPending] = React.useState(false);
  /** The event whose "Open results" is waiting for its confirm, if any. */
  const [confirming, setConfirming] = React.useState<string | null>(null);
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

  const checkAgain = (
    <div>
      <button type="button" className={ceButton("secondary")} disabled={busy} onClick={() => void reload()}>
        Check again
      </button>
    </div>
  );

  function unlock(event: InstructorEventView, datasetId: string): void {
    setConfirming(null);
    setPending(true);
    onRefusal(null);
    unlockResults(event.event_key, datasetId)
      .then(() => {
        onUnlocked();
        return reload();
      })
      .catch((error: unknown) => {
        onRefusal(
          isRefusal(error)
            ? error.message
            : "The exercise could not be reached. Check the connection and try again.",
        );
        refusedUnlockPending.current = true;
        return reload();
      })
      .finally(() => setPending(false));
  }

  return (
    <section className="ce-card flex flex-col gap-4 p-5 md:p-6" data-slot="exercise-instructor-unlock">
      <h2 className="ce-h2 text-ce-ink">Open results for an event</h2>
      {state.status === "loading" ? <ExerciseLoading what="the events" /> : null}
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
          <p className="ce-body text-ce-ink">
            {state.data.dataset_label} has no events for the teams to run.
          </p>
          {checkAgain}
        </>
      ) : null}
      {state.status === "ready" && state.data.events.length > 0 ? (
        <>
          <ul className="flex flex-col gap-3">
            {state.data.events.map((event) => (
              <li
                key={event.event_key}
                className="ce-well flex flex-col gap-3 px-4 py-3 md:px-5"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="ce-body font-semibold text-ce-ink">{event.name}</span>
                  <span className="flex flex-wrap items-center gap-3">
                    {event.unlocked ? (
                      <Chip tone="primary" icon={<LockOpen aria-hidden="true" className="size-4" />}>
                        Results are open
                      </Chip>
                    ) : (
                      <>
                        {confirming === event.event_key ? null : (
                          <button
                            type="button"
                            // A refresh in flight may be about to change
                            // `dataset_id` (an upload or re-point just
                            // landed), so wait for it.
                            disabled={pending || state.refreshing}
                            className={ceButton("secondary")}
                            onClick={() => setConfirming(event.event_key)}
                          >
                            Open results
                          </button>
                        )}
                        <Chip tone="outline" icon={<Lock aria-hidden="true" className="size-4" />}>
                          Results are closed
                        </Chip>
                      </>
                    )}
                  </span>
                </div>
                {confirming === event.event_key && !event.unlocked ? (
                  <div className="flex flex-col gap-3 border-t border-ce-line pt-3">
                    <p className="ce-body text-ce-ink">
                      Open results for {event.name}? Every team can then run results once for
                      this event.
                    </p>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        disabled={pending || state.refreshing}
                        className={ceButton("primary")}
                        onClick={() => unlock(event, state.data.dataset_id)}
                      >
                        {pending ? "Opening…" : "Open results now"}
                      </button>
                      <button
                        type="button"
                        className={ceButton("quiet", "min-h-11")}
                        onClick={() => setConfirming(null)}
                      >
                        Not yet
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

/** This panel's sentence for teams split across files (see `UnlockPanel`). */
const SPLIT_ACROSS_FILES =
  "The teams are working in more than one data file. Under Data files, press " +
  "“Move every team to this file” on the file the class should use. This list reads again on its own once they move.";

/** Refresh every team that has chosen and has not yet asked. */
function RefreshAllPanel({ onDone }: { readonly onDone: () => void }): React.JSX.Element {
  const [pending, setPending] = React.useState(false);
  const [done, setDone] = React.useState<RefreshAllView | null>(null);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  return (
    <section className="ce-card flex flex-col gap-4 p-5 md:p-6">
      <h2 className="ce-h2 text-ce-ink">Ask for every team at once</h2>
      <p className="ce-body text-ce-ink">
        This runs in one go for every team that has picked a way of asking and has not asked yet. If
        it cannot be done, no team is changed.
      </p>
      <div>
        <button
          type="button"
          disabled={pending}
          className={ceButton("secondary")}
          onClick={() => {
            setPending(true);
            setRefusal(null);
            refreshAllWorkspaces()
              .then((view) => {
                setDone(view);
                onDone();
              })
              .catch((error: unknown) =>
                setRefusal(
                  isRefusal(error)
                    ? error.message
                    : "The exercise could not be reached. Check the connection and try again.",
                ),
              )
              .finally(() => setPending(false));
          }}
        >
          {pending ? <Spinner /> : null}
          {pending ? "Asking for every team…" : "Ask for every team"}
        </button>
      </div>
      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      {done === null ? null : (
        <p className="ce-body rounded-[14px] bg-ce-avocado-tint px-4 py-3 text-ce-ink" role="status">
          Asked for {done.refreshed} {done.refreshed === 1 ? "team" : "teams"}
          {done.refreshed_team_numbers.length === 0
            ? ""
            : ` (${done.refreshed_team_numbers.join(", ")})`}
          . Skipped {done.skipped}
          {/*
            A chosen team with no round-one run is what the server skips. (It
            also skips, rarely, a team that asked by itself in the same moment;
            that team already shows "Has already asked" below.)
          */}
          {done.skipped === 0
            ? "."
            : done.skipped === 1
              ? ": that team has not run results for its first event yet."
              : ": those teams have not run results for their first event yet."}
        </p>
      )}
    </section>
  );
}
