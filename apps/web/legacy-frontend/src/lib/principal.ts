/**
 * Display helpers over `GET /v1/me`.
 *
 * Every value a portal shell shows about the person using it is derived here,
 * from the server's answer alone. There is no default name, no default
 * school, and no default role: where `/v1/me` says nothing, these functions
 * say nothing too ("No active membership"), because a placeholder identity is
 * the defect Fix #7 exists to remove.
 */
import type {
  MeResponse,
  MembershipResponse,
  MyPortalsResponse,
  PortalDescriptor,
} from "@/lib/api";
import { visibleRoleLabel } from "@/lib/roleLabels";

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

/**
 * The server-assigned role(s) in force, named as CBA personas.
 *
 * The roles themselves still come from `GET /v1/me` and nowhere else — this
 * only translates the stored string into what customer §2 calls that person.
 * The translation is `lib/roleLabels.ts`, the frontend mirror of the single
 * role-presentation map, so this file holds no role table of its own and no
 * second copy can drift from it.
 *
 * A role the map does not name is shown **as the server spelled it**, not
 * dropped and not rounded to the nearest persona: the honest answer to "what
 * did the server assign you" is the string it assigned, and hiding an
 * unrecognised role would leave a reader unable to see why a portal is closed
 * to them.
 */
export function principalRoleLabel(me: MeResponse): string {
  const roles = Array.from(new Set(activeMemberships(me).map((m) => m.role)));
  const labels = Array.from(new Set(roles.map((role) => visibleRoleLabel(role) ?? role)));
  return labels.length > 0 ? labels.join(", ") : "No active role";
}

export type PortalKind = "student" | "coordinator" | "volunteer" | "admin";

/**
 * The portal the server granted this account, or `null` when it granted none.
 *
 * This is the account-to-portal mapping the shells used to render a banner
 * about. `portalSubjectId()` stood here and returned `null` unconditionally,
 * because the only mapping available was one the browser would have had to
 * invent — and the honest answer to "which legacy record is this account" was
 * that nothing knew. `GET /v1/me/portals` now answers a better question, so
 * this is a *lookup into the server's answer* rather than a derivation: the
 * `mapping` argument is whatever that route returned, and this function only
 * finds the requested kind inside it.
 *
 * Deliberately **not** recomputed from `me.memberships` here. The browser
 * could read a role off `/v1/me` and decide for itself which portal that
 * opens, and it would usually get the same answer — which is exactly what
 * makes it dangerous. Two independent copies of a role-to-portal rule drift,
 * and when they drift the browser's copy is the one that is wrong and the one
 * nobody checks. Asking the server keeps one rule in one place
 * (`services/api/smartmatch_api/routers/portals.py`).
 *
 * `null` is a real answer and is rendered as one: the account holds no active,
 * role-bearing membership that opens this portal. No fallback, no default
 * portal, no "probably a student".
 */
export function portalGrant(
  mapping: MyPortalsResponse,
  portal: PortalKind,
): PortalDescriptor | null {
  return mapping.portals.find((granted) => granted.portal === portal) ?? null;
}

/**
 * Whether the server granted this account the named portal.
 *
 * A convenience over {@link portalGrant} for the shells, which gate on the
 * boolean and render the descriptor only when they have one. Route guarding is
 * UX only — every `/v1` request is still authorized server-side, so a portal
 * shown in error would be a shell whose every fetch is refused rather than an
 * access someone gained.
 */
export function hasPortalGrant(mapping: MyPortalsResponse, portal: PortalKind): boolean {
  return portalGrant(mapping, portal) !== null;
}
