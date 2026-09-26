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

import { isRefusal } from "../../../lib/exerciseApi";
import {
  instructorLogin,
  instructorLogout,
  listInstructorEvents,
  listTeamWorkspaces,
  refreshAllWorkspaces,
  unlockResults,
  type RefreshAllView,
} from "../../../lib/exerciseClient";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { InstructorDatasets } from "./InstructorDatasets";
import { InstructorTeams } from "./InstructorTeams";
import { INSTRUCTOR_SESSION_REQUIRED, TEAMS_SPAN_DATASETS } from "./refusals";
import { useExerciseResource } from "./useExerciseResource";

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-5 py-3 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

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
    >
      {probe === "checking" ? <ExerciseLoading what="the instructor page" /> : null}
      {probe === "signed-in" ? <SignedIn onSignedOut={() => setProbe("signed-out")} /> : null}
      {probe === "signed-out" ? (
        <PasscodeForm onSignedIn={() => setProbe("signed-in")} />
      ) : null}
    </ExerciseScreen>
  );
}

function PasscodeForm({ onSignedIn }: { readonly onSignedIn: () => void }): React.JSX.Element {
  const [passcode, setPasscode] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  return (
    <form
      className="flex flex-col gap-4"
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
      <div className="flex flex-col gap-1">
        <label htmlFor="exercise-passcode" className="text-xl">
          Passcode
        </label>
        <input
          id="exercise-passcode"
          type="password"
          autoComplete="current-password"
          value={passcode}
          onChange={(event) => setPasscode(event.target.value)}
          className="w-96 max-w-full rounded-lg border-2 border-slate-400 px-3 py-2 text-2xl focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-50"
        />
      </div>
      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      <div>
        <button type="submit" disabled={pending || passcode === ""} className={BUTTON}>
          {pending ? "Checking…" : "Open the instructor page"}
        </button>
      </div>
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

  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={BUTTON}
          onClick={() => guard(async () => {
            await instructorLogout();
            onSignedOut();
          })}
        >
          Sign out of this browser
        </button>
        <span className="text-xl text-slate-600 dark:text-slate-300">
          {/* §14 as shipped: no server-side session row, no revocation before expiry. */}
          This clears the passcode from this browser only. It does not sign out anywhere else.
        </span>
      </div>

      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      <InstructorDatasets onDataChanged={dataChanged} />
      <UnlockPanel onRefusal={setRefusal} reloadKey={dataVersion} />
      <RefreshAllPanel />
      <InstructorTeams reloadKey={dataVersion} />
    </div>
  );
}

/**
 * Open results for one event. Idempotent: a second press says the same thing.
 *
 * The list is `GET …/instructor/events`, behind the passcode session alone. It
 * used to be the team route, which needs a workspace cookie, so an instructor
 * who had not entered as a team saw no events at all. "Results are open." is
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
 */
function UnlockPanel({
  onRefusal,
  reloadKey,
}: {
  readonly onRefusal: (message: string | null) => void;
  readonly reloadKey: number;
}): React.JSX.Element {
  const { state, reload } = useExerciseResource(listInstructorEvents, [reloadKey]);
  const [pending, setPending] = React.useState(false);
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
      <button type="button" className={BUTTON} disabled={busy} onClick={() => void reload()}>
        Check again
      </button>
    </div>
  );

  return (
    <section className="flex flex-col gap-3" data-slot="exercise-instructor-unlock">
      <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
        Open results for an event
      </h2>
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
          <p className="text-xl text-slate-700 dark:text-slate-200">
            {state.data.dataset_label} has no events for the teams to run.
          </p>
          {checkAgain}
        </>
      ) : null}
      {state.status === "ready" && state.data.events.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {state.data.events.map((event) => (
            <li key={event.event_key} className="flex flex-wrap items-center gap-3 text-xl">
              <span className="font-semibold">{event.name}</span>
              {event.unlocked ? (
                <span className="text-slate-700 dark:text-slate-200">Results are open.</span>
              ) : (
                <button
                  type="button"
                  // A refresh in flight may be about to change `dataset_id`
                  // (an upload or re-point just landed), so wait for it.
                  disabled={pending || state.refreshing}
                  className={BUTTON}
                  onClick={() => {
                    setPending(true);
                    onRefusal(null);
                    unlockResults(event.event_key, state.data.dataset_id)
                      .then(() => reload())
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
                  }}
                >
                  Open results
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** This panel's sentence for teams split across files (see `UnlockPanel`). */
const SPLIT_ACROSS_FILES =
  "The teams are working in more than one data file. Under Data files, press " +
  "\u201cMove every team to this file\u201d on the file the class should use, then press Check again.";

/** Refresh every team that has chosen and has not yet asked. */
function RefreshAllPanel(): React.JSX.Element {
  const [pending, setPending] = React.useState(false);
  const [done, setDone] = React.useState<RefreshAllView | null>(null);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
        Ask for every team at once
      </h2>
      <p className="text-xl text-slate-700 dark:text-slate-200">
        This runs in one go for every team that has picked a way of asking and has not asked yet. If
        it cannot be done, no team is changed.
      </p>
      <div>
        <button
          type="button"
          disabled={pending}
          className={BUTTON}
          onClick={() => {
            setPending(true);
            setRefusal(null);
            refreshAllWorkspaces()
              .then(setDone)
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
          {pending ? "Asking for every team…" : "Ask for every team"}
        </button>
      </div>
      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      {done === null ? null : (
        <p className="text-xl text-slate-800 dark:text-slate-100">
          Asked for {done.refreshed} {done.refreshed === 1 ? "team" : "teams"}
          {done.refreshed_team_numbers.length === 0
            ? ""
            : ` (${done.refreshed_team_numbers.join(", ")})`}
          . Skipped {done.skipped}.
        </p>
      )}
    </section>
  );
}
