/**
 * The portal a two-portal login last chose (B26 T6b-5 §6.2).
 *
 * One login can hold the Event Host and the Speaker roles. The portal switcher
 * remembers which of the two the person last opened, so `/` lands there next
 * time rather than always on the server's `default_portal`.
 *
 * Three rules, all enforced here rather than trusted to each caller:
 *
 * 1. **A portal id only** (`"volunteer"`, `"speaker"`). Never a user id, a
 *    credential or a principal key: nothing here identifies the person.
 * 2. **Validated, never trusted.** A stored value is returned only if it is one
 *    of the portals the server granted (`GET /v1/me/portals`); anything else
 *    reads as `null`. Writing a portal id by hand grants nothing.
 * 3. **Every access is wrapped.** `localStorage` throws in a private window or
 *    with site data blocked, and the accessor itself is what throws. A failure
 *    is silent and the app behaves as on a first visit.
 *
 * Sign-out forgets the choice (`useSession`), so the next person on a shared
 * browser starts at `default_portal`.
 */

/** The storage key. */
export const PORTAL_CHOICE_KEY = "smartmatch.portal.lastChoice";

/** The remembered portal id if the server granted it, else `null`. */
export function readRememberedPortal(granted: readonly string[]): string | null {
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(PORTAL_CHOICE_KEY);
  } catch {
    return null;
  }
  return stored !== null && granted.includes(stored) ? stored : null;
}

/** Remember the portal just chosen. Failure is not an error. */
export function rememberPortal(portal: string): void {
  try {
    window.localStorage.setItem(PORTAL_CHOICE_KEY, portal);
  } catch {
    // Storage blocked: the next visit lands on `default_portal`, which is fine.
  }
}

/** Forget the choice (sign-out). Failure is not an error. */
export function forgetRememberedPortal(): void {
  try {
    window.localStorage.removeItem(PORTAL_CHOICE_KEY);
  } catch {
    // Storage blocked: there is nothing stored to forget.
  }
}
