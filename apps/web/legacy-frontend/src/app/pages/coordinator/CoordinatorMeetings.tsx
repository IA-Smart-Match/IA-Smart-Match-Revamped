/**
 * Meetings — coordinator portal.
 *
 * This page used to load meeting bookings from the legacy `/api/portals/*` backend.
 * That backend is not part of this repository, so there is no request here
 * that could succeed and no data to render. Rather than a red failure banner
 * blaming an outage for a capability that was never present, each section
 * says plainly what it would have shown and where that would have come from
 * (`PortalDatasetUnavailable`).
 *
 * What *is* real on this page comes from two `/v1` routes and nothing else:
 * `GET /v1/me` for who the caller is, and `GET /v1/me/portals` for the portal
 * the server granted them and the role and unit behind it. Neither is derived
 * in the browser, and no identifier on this page is chosen by it.
 */

import { PortalDatasetUnavailable } from "../../components/PortalContent";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

export function CoordinatorMeetings() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is
  // still resolving. Render nothing rather than a header about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Meetings</h1>
        <p className="text-sm text-muted-foreground">Meetings booked with the IA West team.</p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <div className="space-y-4">
        <PortalDatasetUnavailable
          dataset="Meeting bookings"
          endpoints={["/api/portals/event-coordinators/{id}/meetings"]}
        />
      </div>
    </div>
  );
}
