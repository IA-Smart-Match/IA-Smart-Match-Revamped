/**
 * The instructor page's one rule for an expired session.
 *
 * The instructor cookie lasts twelve hours and nothing announces its end, so
 * the first read or action after that is refused with
 * `exercise_instructor_session_required`. Every panel on the page hands that
 * refusal to `onSignedOut`, which returns the page to the passcode form rather
 * than leaving controls on screen that will all fail the same way. Any other
 * refusal stays in the panel as the server's sentence.
 */
import * as React from "react";

import { INSTRUCTOR_SESSION_REQUIRED } from "./refusals";
import type { ExerciseResourceState } from "./useExerciseResource";

/** Calls `onSignedOut` once when a panel's own read is refused for the session. */
export function useSignOutOnExpiredRead<T>(
  state: ExerciseResourceState<T>,
  onSignedOut: (() => void) | undefined,
): void {
  const expired = state.status === "refused" && state.refusal.code === INSTRUCTOR_SESSION_REQUIRED;
  React.useEffect(() => {
    if (expired) {
      onSignedOut?.();
    }
  }, [expired, onSignedOut]);
}
