/**
 * Whether the caller *holds* a server-assigned role, right now.
 *
 * This is a different question from "which shell may I open", and since the
 * CBA pivot merged `coordinator` and `admin` into one persona it is the only
 * way to ask it. `GET /v1/me/portals` now reports **one** descriptor for the
 * connector shell however many of the caller's memberships opened it, so a
 * portal id can no longer tell an administrator apart from a connector — and
 * it should not, because the two land in the same place on purpose.
 *
 * ## Which question to ask, and of what
 *
 * - **"May this browser render the connector shell, and over which unit?"** —
 *   `grantedPortal(access, "coordinator")` in `lib/principal.ts`, over
 *   `GET /v1/me/portals`. That answer carries the `unit_id`s the routes take.
 * - **"Is this person an administrator?"** — {@link hasActiveRole} over
 *   `GET /v1/me`'s membership rows. Use it to reveal the Administration
 *   section inside the connector shell.
 *
 * Reading `me.memberships` for the first question would be the browser
 * re-deriving routing the server already answered (`lib/principal.ts` explains
 * why that is the archived MM-A01 shape). Reading a portal descriptor for the
 * second is now simply impossible, which is the honest outcome of the merge.
 *
 * ## Revealing is not authorizing
 *
 * Nothing here grants anything. Every `/v1` request is authorized server-side,
 * deny-by-default and tenant-scoped, against the stored `membership.role` —
 * never against what this function returned. A browser that forced this to
 * `true` would get a menu whose every request is refused, which is the correct
 * failure mode. So this may decide what to *show*; it may never be the only
 * thing standing between a person and an effect.
 *
 * ## `is_active` is honoured, and that is the point
 *
 * `MembershipResponse.is_active` is computed against the server's own clock
 * for exactly this caller (`routers/me.py`): inclusive start, exclusive end.
 * An expired `admin` row is still *present* on the response — `/v1/me` reports
 * every row rather than silently dropping some — so a naive
 * `memberships.some(m => m.role === "admin")` would show an administration
 * menu to a person whose grant lapsed last month, and every click inside it
 * would 403. Filtering here rather than at each call site is what keeps that
 * from being re-decided per screen.
 */
import type { MeResponse } from "./api";

/**
 * Does the caller hold `role` on a membership that is in force right now?
 *
 * `null`/`undefined` — identity not loaded yet, or the request failed —
 * answers `false`. That is deny-by-default applied to rendering: "we do not
 * know yet" and "no" must look the same to a menu, or a slow response briefly
 * shows an administration surface to everybody.
 *
 * The role is matched exactly against the **stored** string (`admin`,
 * `coordinator`, `volunteer`, `student`), never against a display label —
 * `lib/roleLabels.ts` translates those for a reader and is deliberately not
 * consulted here, so that renaming a persona cannot change who sees what.
 *
 * @example
 * // Administration is a section of the connector shell, not a portal.
 * const showAdministration = hasActiveRole(me, "admin");
 */
export function hasActiveRole(
  me: MeResponse | null | undefined,
  role: string,
): boolean {
  if (!me) {
    return false;
  }
  return me.memberships.some(
    (membership) => membership.is_active && membership.role === role,
  );
}
