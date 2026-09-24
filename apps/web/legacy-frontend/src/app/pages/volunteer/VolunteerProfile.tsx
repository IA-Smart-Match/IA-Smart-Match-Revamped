/**
 * Profile — Event Host portal.
 *
 * The Host's own record, and nothing more. Everything on this page comes from
 * two `/v1` routes the portal layout has already resolved: `GET /v1/me` for who
 * the caller is, and `GET /v1/me/portals` for the portal the server granted
 * them and the role and units behind it. The page issues no request of its
 * own; it reads the gated session and portal-access contexts and renders the
 * shared identity card. Neither value is derived in the browser, and no
 * identifier on this page is chosen by it.
 *
 * The organization is described on its own page, so this one only links to it.
 */

import { Link } from "react-router";

import { PortalIdentityCard } from "../../components/PortalContent";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

export function VolunteerProfile() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "volunteer");

  // `VolunteerPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is
  // still resolving. Render nothing rather than a header about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Profile
        </p>
        <p className="text-sm text-muted-foreground">Your Event Host record.</p>
      </header>

      {/* The card's `h1` (the display name) is the page's only `h1`. */}
      <PortalIdentityCard me={principal} grant={grant} />

      <section
        aria-labelledby="host-profile-organization"
        className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
      >
        <h2 id="host-profile-organization" className="text-lg font-semibold text-foreground">
          Your organization
        </h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          Your organization is described on its own page.
        </p>
        <Link
          to="/volunteer-portal/organization"
          className="mt-4 inline-flex items-center rounded-lg border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          Go to Organization
        </Link>
      </section>
    </div>
  );
}
