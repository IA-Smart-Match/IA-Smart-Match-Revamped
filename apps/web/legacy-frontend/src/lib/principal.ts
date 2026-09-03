/**
 * Display helpers over `GET /v1/me`.
 *
 * Every value a portal shell shows about the person using it is derived here,
 * from the server's answer alone. There is no default name, no default
 * school, and no default role: where `/v1/me` says nothing, these functions
 * say nothing too ("No active membership"), because a placeholder identity is
 * the defect Fix #7 exists to remove.
 */
import type { MeResponse, MembershipResponse } from "@/lib/api";

/** The memberships the server currently counts as in force. */
export function activeMemberships(me: MeResponse): MembershipResponse[] {
  return me.memberships.filter((membership) => membership.is_active);
}

/**
 * What to call the signed-in person.
 *
 * Their email address, because that is the only human-readable identifier
 * `/v1/me` returns. A prettier display name would have to be invented here,
 * and inventing identity in the browser is the whole archived pattern.
 */
export function principalDisplayName(me: MeResponse): string {
  return me.email;
}

/** Up to two letters for the avatar chip, taken from the email's local part. */
export function principalInitials(me: MeResponse): string {
  const localPart = me.email.split("@")[0] ?? "";
  const letters = localPart.split(/[^a-zA-Z0-9]+/u).filter(Boolean);
  const initials = letters.length > 1
    ? `${letters[0][0]}${letters[1][0]}`
    : localPart.slice(0, 2);
  return initials.toUpperCase() || "?";
}

/**
 * The org unit the signed-in person holds an active membership in, as the
 * server spells it, or a truthful blank when they hold none.
 */
export function principalOrgUnitLabel(me: MeResponse): string {
  const active = activeMemberships(me);
  if (active.length === 0) {
    return "No active membership";
  }
  if (active.length === 1) {
    return active[0].org_unit_path;
  }
  return `${active[0].org_unit_path} +${active.length - 1}`;
}

/** The server-assigned role(s) in force, or a truthful blank. */
export function principalRoleLabel(me: MeResponse): string {
  const roles = Array.from(new Set(activeMemberships(me).map((m) => m.role)));
  return roles.length > 0 ? roles.join(", ") : "No active role";
}

/**
 * The id the legacy `/api/portals/*` routes are called with.
 *
 * `GET /v1/me` carries no legacy portal id. The per-portal ids this code used
 * to fall back to were browser-side fixtures, not identifiers the server ever
 * issued, which is precisely why they are gone (the literals themselves live
 * only in `tests/unit/test_frontend_auth_contract.py`, which asserts they
 * appear nowhere in `src/`). The only subject the server hands the browser is
 * `user_id`, so that is what these routes are called with. Where the legacy
 * backend holds no record under it, the page surfaces that failure — it does
 * not substitute a canned id to make the screen fill in.
 */
export function portalSubjectId(me: MeResponse): string {
  return me.user_id;
}
