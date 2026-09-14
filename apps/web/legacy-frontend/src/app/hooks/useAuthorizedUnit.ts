/**
 * Return only the unit the server granted this account for one portal.
 *
 * A thin read over `usePortalAccess()` / `grantedPortal()` — see
 * `PortalGate.tsx` for why that mapping, from `GET /v1/me/portals`, is the
 * only source for a granted unit. Never a build-time constant, a route
 * param, or a value the browser composed: a page that needs "the unit this
 * account may act in" asks here, and gets `null` while the mapping is still
 * loading or while the server granted no such unit — both render the same
 * "choose an authorized unit" state, never a fabricated id.
 */
import { grantedPortal } from "../components/PortalGate";
import type { PortalKind } from "@/lib/principal";
import { usePortalAccess } from "./usePortalAccess";
import { useAuthenticatedPrincipal } from "./useSession";

export function useAuthorizedUnitId(portal: PortalKind): string | null {
  useAuthenticatedPrincipal();
  const access = usePortalAccess();
  if (access.status !== "ready") {
    return null;
  }
  return grantedPortal(access, portal)?.default_unit_id ?? null;
}
