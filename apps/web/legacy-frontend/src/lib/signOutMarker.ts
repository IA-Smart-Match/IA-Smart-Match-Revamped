/**
 * The record that a person **deliberately signed out** of this browser.
 *
 * A sign-out has to be remembered, not just acted on. Dropping the stored
 * credential is not enough on a compose/dev bundle: `VITE_SMARTMATCH_BEARER_TOKEN`
 * is baked into the bundle, so the moment `sessionStorage` is empty the fixture
 * becomes the only remaining credential and the next `GET /v1/me` succeeds
 * again — as whoever the fixture maps to. On the pilot appliance that is the
 * seeded **coordinator**, so a student who pressed "Sign out" in
 * `/student-portal` was handed `/coordinator-portal` with the full coordinator
 * navigation. The sign-out button escalated privileges.
 *
 * The marker is what tells `resolveBearerToken()` (see `lib/bearerToken.ts`)
 * that this browser has asked for something, and so is no longer the
 * "visitor who has not asked for anything" the fixture exists for.
 *
 * It is stored in `sessionStorage`, alongside the credential it overrides and
 * with the same lifetime:
 *
 *  - it survives reloads and in-app navigation, which is what makes the
 *    signed-out state stick rather than flicker back to a portal;
 *  - it dies with the tab, so a *fresh* local session — the one case the
 *    fixture convenience is actually for, a developer opening the appliance
 *    having never signed in — still gets the fixture token;
 *  - it is cleared by signing in again (`storeSmartmatchBearerToken()`), which
 *    is the only thing that should undo it.
 *
 * These functions take the storage explicitly so they are pure in their input
 * and testable without a DOM (`tests/signOutEscalation.test.ts`); `lib/api.ts`
 * is the one place that passes the real `sessionStorage`.
 */

/** The `sessionStorage` key the deliberate-sign-out marker is held under. */
export const SMARTMATCH_SIGNED_OUT_STORAGE_KEY = "smartmatch_signed_out";

/**
 * The subset of `Storage` this module needs.
 *
 * Narrow on purpose: nothing here may read or write any other key, and a test
 * double should not have to implement `length` or `key()`.
 */
export type MarkerStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** Records that the person asked to be signed out of this browser. */
export function markSignedOut(storage: MarkerStorage | null | undefined): void {
  // A browser with no usable storage cannot remember anything; the caller
  // still moves the UI to a signed-out state, which is the part the person
  // asked for. Swallowing nothing: there is no failure here to report.
  storage?.setItem(SMARTMATCH_SIGNED_OUT_STORAGE_KEY, "1");
}

/** Forgets the marker, because a new sign-in has superseded it. */
export function clearSignedOut(storage: MarkerStorage | null | undefined): void {
  storage?.removeItem(SMARTMATCH_SIGNED_OUT_STORAGE_KEY);
}

/** Whether this browser signed out since it last signed in. */
export function hasSignedOut(storage: MarkerStorage | null | undefined): boolean {
  // Any stored value counts. The key's presence is the whole signal; its
  // contents are never interpreted, so no future value can weaken it.
  return typeof storage?.getItem(SMARTMATCH_SIGNED_OUT_STORAGE_KEY) === "string";
}
