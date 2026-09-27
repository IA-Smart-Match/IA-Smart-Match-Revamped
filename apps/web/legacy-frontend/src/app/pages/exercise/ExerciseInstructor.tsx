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
 * **An expired session signs the page out from any panel.** Every read and
 * action on the page that is refused with `exercise_instructor_session_required`
 * returns to the passcode form (`instructorSession.ts`).
 *
 * There is no portal shell here either. The passcode gates the *API*; this
 * page renders whatever the server answers, including its refusals, rather
 * than hiding controls and implying a capability is absent — the same rule the
 * CBA portal's pages follow for a different reason.
 *
 * Layout (DESIGN.md §7.11, "The invitation desk"): signed out, one centred
 * 480px passcode card. Signed in, two columns 8/4 from 1024px — unlock, teams
 * and ask-for-all on the left; data files and sign out on the right — and one
 * column below in that same order.
 */
import * as React from "react";
import { Eye, EyeOff, KeyRound } from "lucide-react";

import { isRefusal } from "../../../lib/exerciseApi";
import { instructorLogin, instructorLogout, listTeamWorkspaces } from "../../../lib/exerciseClient";
import { Button, SkeletonCard, SkeletonRegion } from "./desk";
import { ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { InstructorDatasets } from "./InstructorDatasets";
import { InstructorTeams } from "./InstructorTeams";
import { RefreshAllPanel, UnlockPanel } from "./InstructorUnlock";
import { INSTRUCTOR_INPUT } from "./instructorUi";
import { INSTRUCTOR_SESSION_REQUIRED } from "./refusals";

/** The page's sentence for a request that never landed. */
const UNREACHABLE = "The exercise could not be reached. Check the connection and try again.";

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
      {probe === "checking" ? (
        <SkeletonRegion label="Loading the instructor page…" className="mx-auto w-full max-w-[480px]">
          <SkeletonCard lines={3} />
        </SkeletonRegion>
      ) : null}
      {probe === "signed-in" ? <SignedIn onSignedOut={() => setProbe("signed-out")} /> : null}
      {probe === "signed-out" ? (
        <PasscodeForm onSignedIn={() => setProbe("signed-in")} />
      ) : null}
    </ExerciseScreen>
  );
}

/**
 * The passcode card. The passcode lives only in the field's value: it is never
 * rendered as text, stored or logged, and it is cleared once it is accepted.
 * The show/hide toggle (DESIGN.md §6.24) switches the field between password
 * and text so a long passcode can be checked before it is sent; it is a
 * `type="button"`, so it never submits.
 */
function PasscodeForm({ onSignedIn }: { readonly onSignedIn: () => void }): React.JSX.Element {
  const [passcode, setPasscode] = React.useState("");
  const [shown, setShown] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  return (
    <form
      className="ce-card mx-auto flex w-full max-w-[480px] flex-col gap-ce-4 p-ce-4 md:p-ce-6"
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
            setRefusal(isRefusal(error) ? error.message : UNREACHABLE);
          })
          .finally(() => setPending(false));
      }}
    >
      <span
        aria-hidden="true"
        className="inline-flex size-12 items-center justify-center rounded-ce-control bg-ce-primary-tint text-ce-primary"
      >
        <KeyRound className="size-7" />
      </span>
      <div className="flex flex-col gap-ce-2">
        <label htmlFor="exercise-passcode" className="ce-type-label text-ce-ink">
          Passcode
        </label>
        <div className="relative">
          <input
            id="exercise-passcode"
            type={shown ? "text" : "password"}
            autoComplete="current-password"
            // A shown passcode is still a secret: no spellcheck or autocorrect
            // sending it anywhere.
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            aria-describedby="exercise-passcode-help"
            value={passcode}
            onChange={(event) => setPasscode(event.target.value)}
            className={`${INSTRUCTOR_INPUT} w-full pr-14`}
          />
          <Button
            variant="quiet"
            aria-pressed={shown}
            // One fixed name; aria-pressed says whether it is on. A name that
            // swapped as well would read "Hide what is typed, pressed".
            // Named without the field's word, so the field keeps its one label.
            aria-label="Show what is typed"
            onClick={() => setShown((value) => !value)}
            className="absolute top-1/2 right-ce-1 -translate-y-1/2 text-ce-ink-muted hover:text-ce-primary"
          >
            {shown ? (
              <EyeOff aria-hidden="true" className="size-5" />
            ) : (
              <Eye aria-hidden="true" className="size-5" />
            )}
          </Button>
        </div>
      </div>
      {refusal === null ? null : <ExerciseNotice message={refusal} />}
      <Button
        type="submit"
        pending={pending}
        pendingLabel="Checking…"
        disabled={passcode === ""}
        className="w-full"
      >
        Open the instructor page
      </Button>
      <p id="exercise-passcode-help" className="ce-type-meta text-center text-ce-ink-muted">
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
   * The Sign out button, with the session's own 401 handled once.
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
      setRefusal(UNREACHABLE);
    });
  }

  return (
    <div className="ce-fade-rise flex flex-col gap-ce-5">
      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      <div className="grid grid-cols-1 gap-ce-5 lg:grid-cols-12 lg:items-start">
        <div className="flex min-w-0 flex-col gap-ce-5 lg:col-span-8">
          <UnlockPanel
            onRefusal={setRefusal}
            onUnlocked={teamsChanged}
            onSignedOut={onSignedOut}
            reloadKey={dataVersion}
          />
          {/* A sum, so a bump to either re-reads the teams. */}
          <InstructorTeams reloadKey={dataVersion + teamsVersion} onSignedOut={onSignedOut} />
          <RefreshAllPanel onDone={teamsChanged} onSignedOut={onSignedOut} />
        </div>

        {/*
          Not sticky, although §7.11 asks for it: with the dropzone, an upload
          report and a data file this column is taller than a laptop window,
          and a sticky column taller than the window hides its own bottom —
          "Move every team" and "Sign out" — until the left column ends. A
          scroll box inside the column was tried and clipped the same controls.
        */}
        <div className="flex min-w-0 flex-col gap-ce-5 lg:col-span-4">
          <InstructorDatasets onDataChanged={dataChanged} onSignedOut={onSignedOut} />
          <div className="ce-card flex flex-col items-start gap-ce-2 p-ce-4 md:p-ce-5">
            <Button
              variant="quiet"
              className="-ml-ce-2"
              aria-describedby="exercise-sign-out-help"
              onClick={() =>
                guard(async () => {
                  await instructorLogout();
                  onSignedOut();
                })
              }
            >
              Sign out of this browser
            </Button>
            <p id="exercise-sign-out-help" className="ce-type-meta text-ce-ink-muted">
              {/* §14 as shipped: no server-side session row, no revocation before expiry. */}
              This clears the passcode from this browser only. It does not sign out anywhere else.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
