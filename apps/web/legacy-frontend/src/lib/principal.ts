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

export type PortalKind = "student" | "coordinator" | "volunteer";

/**
 * The server-owned legacy record id for a portal, when one exists.
 *
 * `GET /v1/me` currently returns an account UUID, not the distinct
 * `student_id`, `coordinator_id`, or `volunteer_id` consumed by the legacy
 * `/api/portals/*` routes. Reusing `me.user_id` would silently change one id
 * namespace into another and would still leave the browser choosing the path
 * subject sent to an unauthenticated legacy route.
 *
 * Until the API exposes an authenticated self-service portal route or an
 * authoritative account-to-portal mapping, the only truthful answer is that
 * no portal subject is available. Callers convert this to an empty transport
 * value; the API client rejects it locally before any legacy request is sent.
 * Keeping the principal and portal kind in this seam makes the eventual
 * server-owned mapping explicit without inventing one in the browser today.
 */
export function portalSubjectId(_me: MeResponse, _portal: PortalKind): string | null {
  return null;
}
