/**
 * Asking `GET /v1/me` whether the signed-in account holds a stored role.
 *
 * ## What this is for, and the one thing it is not for
 *
 * The Connector Dashboard is **one shell for two stored roles**. An account
 * with `coordinator` and an account with `admin` both land on
 * `/coordinator-portal`, see the same brand, and walk the same Inbox →
 * Coordinate → People navigation. The single difference is that the
 * Administration group is drawn only for an account that actually holds
 * `admin`, because those pages are `admin`-reaching surfaces and advertising
 * them to a coordinator would be offering a door that answers 403.
 *
 * That is a *visibility* decision and nothing more. It is emphatically **not**
 * authorization:
 *
 *  - Every `/v1` request is authorized server-side, per route, deny-by-default
 *    and tenant-scoped (`smartmatch_authz`), against the stored
 *    `membership.role`. Hiding a link removes a claim, never an access path.
 *  - It is also **not** the portal grant. Which shell an account may open is
 *    `GET /v1/me/portals`'s answer alone — `grantedPortal(access,
 *    "coordinator")` — for the reason `lib/principal.ts`'s `portalGrant()`
 *    spells out at length: two independent copies of a role-to-portal rule
 *    drift, and the browser's copy is the one nobody checks. Nothing here
 *    decides which portal exists; it only decides which *group inside one
 *    already-granted portal* is worth drawing.
 *
 * ## Why `is_active` is honoured rather than assumed
 *
 * `MembershipResponse` carries `is_active`, and a lapsed membership is a row
 * the server still returns and still counts as not in force. Reading `role`
 * without it would show an expired administrator the Administration group and
 * then refuse every page inside it — a worse experience than not offering it,
 * because the reader would have no way to tell a lapsed grant from an outage.
 *
 * ## Exact match, no normalisation
 *
 * `"Admin"`, `"admin "` and `"ADMIN"` are not the stored string and answer
 * `false`, matching `lib/roleLabels.ts`'s `presentation()`. Trimming or
 * lowercasing here would make a malformed membership row read as a correct
 * one, and the row is the server's to fix.
 */
import type { MeResponse } from "@/lib/api";

/**
 * Whether `me` holds an **active** membership carrying the stored `role`.
 *
 * `null`/`undefined` — the `GET /v1/me` round trip has not resolved — answers
 * `false`, which is the safe and honest reading: an unanswered question is not
 * a grant. Callers that need to distinguish "still loading" from "does not
 * hold it" have `useSession().status` for exactly that, and must not infer it
 * from this boolean.
 */
export function hasActiveRole(me: MeResponse | null | undefined, role: string): boolean {
  if (!me) {
    return false;
  }
  return me.memberships.some(
    (membership) => membership.is_active && membership.role === role,
  );
}
