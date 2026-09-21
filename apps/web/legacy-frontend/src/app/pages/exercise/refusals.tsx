/**
 * Refusals that more than one screen has to answer.
 *
 * Two rules hold everywhere and are kept here so they are kept once.
 *
 * **The sentence is the server's.** Every exercise refusal carries one plain
 * sentence written for a class participant to read on a projector
 * (`smartmatch_api/exercise_errors.py`). It is rendered verbatim — not
 * re-worded, not capitalised, not truncated. Screens branch on `code`, which
 * is stable, never on the text, which is Ann's and may change.
 *
 * **A refusal is usually a state, not an error.** "The instructor has not
 * opened this event yet", "your team has already run results for this event",
 * "the course owner has not confirmed the results rule" are all the product
 * working correctly, and all arrive as a 409. They read as calm panels with
 * the server's sentence. Only a genuine transport failure gets the louder
 * treatment.
 */
import * as React from "react";
import { Link } from "react-router";

import type { ExerciseRefusal } from "../../../lib/exerciseApi";
import { ExerciseNotice } from "./ExerciseScreen";

/** The 401 that means this browser has not entered a team number yet. */
export const WORKSPACE_REQUIRED = "exercise_workspace_required";

/** The 401 that means the instructor's passcode session has gone. */
export const INSTRUCTOR_SESSION_REQUIRED = "exercise_instructor_session_required";

/**
 * Any team-screen refusal, with a way back to the entry screen when the
 * refusal is that there is no workspace.
 *
 * The link is offered rather than a redirect fired: a screen that navigates
 * away on its own takes the sentence off the projector before anybody has
 * read it, and in a classroom the sentence is the point.
 */
export function workspaceRequiredNotice(refusal: ExerciseRefusal): React.JSX.Element {
  if (refusal.code !== WORKSPACE_REQUIRED) {
    return <ExerciseNotice message={refusal.message} />;
  }
  return (
    <ExerciseNotice message={refusal.message}>
      <Link
        to="/exercise"
        className="inline-block rounded-lg border-2 border-slate-900 px-5 py-2 text-xl font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-100 dark:text-slate-100"
      >
        Enter your team number
      </Link>
    </ExerciseNotice>
  );
}

/** The instructor equivalent: the passcode session is gone, so sign in again. */
export function instructorSessionNotice(refusal: ExerciseRefusal): React.JSX.Element {
  return <ExerciseNotice message={refusal.message} />;
}
