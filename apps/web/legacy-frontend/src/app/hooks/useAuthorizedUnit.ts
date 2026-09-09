import { grantedPortal } from "../components/PortalGate";
import type { PortalKind } from "../../lib/principal";
import { usePortalAccess } from "./usePortalAccess";
import { useAuthenticatedPrincipal } from "./useSession";

/** Return only the unit the server granted for this portal. */
export function useAuthorizedUnitId(portal: PortalKind): string | null {
  useAuthenticatedPrincipal();
  const access = usePortalAccess();
  if (access.status !== "ready") return null;
  return grantedPortal(access, portal)?.default_unit_id ?? null;
}
