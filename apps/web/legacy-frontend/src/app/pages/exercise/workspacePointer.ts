/**
 * The `localStorage` mirror of which team this browser entered.
 *
 * Design spec §15: the workspace token lives in an httpOnly cookie, "mirrored
 * to `localStorage` so a reload restores it. **The server row is the truth;
 * the cookie is a pointer.**" JavaScript cannot read the httpOnly cookie, so
 * what is mirrored here is not the token — it is the team number, and its only
 * job is to let the entry screen say "you were team 4" and re-enter without a
 * participant retyping it after a reload.
 *
 * Three rules follow from "the server row is the truth", and all three are
 * enforced here rather than trusted to each caller:
 *
 * 1. **Nothing is authorised by this value.** A team number read from here is
 *    re-sent to `POST /v1/exercise/workspaces`, which decides. Writing `4` in
 *    a browser's storage by hand gets the same answer as typing `4`, which is
 *    the answer the requirements' "no login" row describes.
 * 2. **Every access is wrapped.** `localStorage` throws on access in a private
 *    window with site data blocked, and the accessor itself — not just the
 *    read — is what throws. A classroom machine with cookies locked down must
 *    still be able to enter a team number, so a failure here is silent and the
 *    screen behaves exactly as it does on a first visit.
 * 3. **A stored value is validated, not trusted.** Anything that is not one of
 *    the team numbers the server offers reads as "nothing stored".
 */

/**
 * The storage key.
 *
 * Prefixed with the scope's own name so it cannot collide with anything the
 * CBA build writes into the same origin's storage. The word is `exercise`
 * throughout, per ADR-0025 D9 and `tools/scan_forbidden.py`.
 */
export const WORKSPACE_POINTER_KEY = "smartmatch.exercise.teamNumber";

/**
 * The team number this browser last entered, or `null`.
 *
 * `teamNumbers` is the set the server offered on `GET /v1/exercise`
 * (`team_numbers`), passed in rather than written here: the requirements fix
 * the numbers at 1-6 and the route reports them, and a screen that hard-coded
 * the range would be a second place to change if that ever moved.
 */
export function readWorkspacePointer(teamNumbers: readonly number[]): number | null {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(WORKSPACE_POINTER_KEY);
  } catch {
    return null;
  }
  if (raw === null) {
    return null;
  }
  const parsed = Number.parseInt(raw, 10);
  return teamNumbers.includes(parsed) ? parsed : null;
}

/** Mirror the team number a successful entry returned. Failure is not an error. */
export function writeWorkspacePointer(teamNumber: number): void {
  try {
    window.localStorage.setItem(WORKSPACE_POINTER_KEY, String(teamNumber));
  } catch {
    // Storage is unavailable or full. The cookie the server just set is the
    // pointer that matters; this mirror only saves retyping, so its absence
    // costs a participant one keystroke and nothing else.
  }
}

/** Forget the mirror — used when the server says there is no workspace. */
export function clearWorkspacePointer(): void {
  try {
    window.localStorage.removeItem(WORKSPACE_POINTER_KEY);
  } catch {
    // Same reasoning as the write.
  }
}
