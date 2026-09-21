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
  readEvents,
  refreshAllWorkspaces,
  unlockResults,
  type RefreshAllView,
} from "../../../lib/exerciseClient";
import { ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { InstructorDatasets } from "./InstructorDatasets";
import { InstructorTeams } from "./InstructorTeams";
import { INSTRUCTOR_SESSION_REQUIRED } from "./refusals";

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-5 py-3 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

export function ExerciseInstructor(): React.JSX.Element {
  const [signedIn, setSignedIn] = React.useState(false);

  return (
    <ExerciseScreen
      title="Instructor"
      intro="Load a data file, open results for an event, and see what each team has done."
    >
      {signedIn ? (
        <SignedIn onSignedOut={() => setSignedIn(false)} />
      ) : (
        <PasscodeForm onSignedIn={() => setSignedIn(true)} />
      )}
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

      <InstructorDatasets />
      <UnlockPanel onRefusal={setRefusal} />
      <RefreshAllPanel />
      <InstructorTeams />
    </div>
  );
}

/** Open results for one event. Idempotent: a second press says the same thing. */
function UnlockPanel({
  onRefusal,
}: {
  readonly onRefusal: (message: string | null) => void;
}): React.JSX.Element {
  const [events, setEvents] = React.useState<{ key: string; name: string }[]>([]);
  const [unlocked, setUnlocked] = React.useState<readonly string[]>([]);
  const [pending, setPending] = React.useState(false);

  React.useEffect(() => {
    const controller = new AbortController();
    readEvents(controller.signal)
      .then((view) =>
        setEvents(
          view.events
            .filter((event) => event.is_exercise_event)
            .sort((a, b) => a.sequence - b.sequence)
            .map((event) => ({ key: event.event_key, name: event.name })),
        ),
      )
      .catch(() => {
        // The instructor's own event list comes from a team route, which needs
        // a workspace cookie this browser may not have. An empty list and the
        // sentence below is the honest state, not an error worth shouting.
        setEvents([]);
      });
    return () => controller.abort();
  }, []);

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
        Open results for an event
      </h2>
      {events.length === 0 ? (
        <p className="text-xl text-slate-700 dark:text-slate-200">
          The events cannot be listed from this browser. Enter a team number in another tab, or open
          results by pressing a team's event once it appears here.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {events.map((event) => (
            <li key={event.key} className="flex flex-wrap items-center gap-3 text-xl">
              <span className="font-semibold">{event.name}</span>
              <button
                type="button"
                disabled={pending}
                className={BUTTON}
                onClick={() => {
                  setPending(true);
                  onRefusal(null);
                  unlockResults(event.key)
                    .then((view) => setUnlocked((open) => [...open, view.event_key]))
                    .catch((error: unknown) =>
                      onRefusal(
                        isRefusal(error)
                          ? error.message
                          : "The exercise could not be reached. Check the connection and try again.",
                      ),
                    )
                    .finally(() => setPending(false));
                }}
              >
                Open results
              </button>
              {unlocked.includes(event.key) ? (
                <span className="text-slate-700 dark:text-slate-200">Results are open.</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

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
