/**
 * Connect — student portal.
 *
 * The one student page with **no** `/v1` source, and the only one that still
 * carries a named-absence panel after the rest of the portal was repointed.
 *
 * This is a gap in the API rather than in this page. Every route that turns an
 * event into the people at it is `admin`/`coordinator` server-side —
 * `GET .../cba/confirmed-speakers` (`cba_handoff.py::_HANDOFF_ROLES`),
 * `GET .../speaker-contacts` (`cba_contacts.py::_SPEAKER_CONTACT_ROLES`),
 * `GET .../meetings` (`meetings.py::_MEETING_ROLES`) — and there is no
 * student-scoped counterpart of any of them at any path. Calling one from here
 * would earn a `403` and teach a reader that a student surface may be built on
 * a route the server refuses; the only other ways to populate this page would
 * be to invent a list of people or to ask a student to type an identifier,
 * which is MM-A01's caller-selected identity in a new spelling.
 *
 * So the page says what is missing, names the capability that would have to
 * exist, and points at the two surfaces that *are* real. It never says
 * "loading", and it never renders an empty list a reader would take for "no
 * one here matches you".
 *
 * What *is* real on this page comes from two `/v1` routes and nothing else:
 * `GET /v1/me` for who the caller is, and `GET /v1/me/portals` for the portal
 * the server granted them and the role and unit behind it. Neither is derived
 * in the browser, and no identifier on this page is chosen by it.
 */

import { Link } from "react-router";

import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { MissingCapability } from "./studentPanels";

export function StudentConnect() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "student");

  // `StudentLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is
  // still resolving. Render nothing rather than a header about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Connect</h1>
        <p className="text-sm text-muted-foreground">
          People to meet, based on what you have attended.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <div className="space-y-4">
        <MissingCapability
          dataset="People to connect with"
          endpoints={[
            "/api/portals/student-connections",
            "/api/portals/students/{id}/connection-suggestions",
          ]}
          capability={
            "Missing backend capability: a student-scoped read of the professionals at an " +
            "event. SmartMatch keeps speaker contacts, confirmed speakers and meetings, but " +
            "every route that reads them is restricted to Speaker Connectors and Event Hosts, " +
            "and no student-facing equivalent exists at any path. Until one does there is " +
            "nobody this page is allowed to name, and naming somebody anyway would be an " +
            "invention rather than a suggestion. This is not a fault of your account and not " +
            "an outage."
          }
        />

        <section className="rounded-2xl border border-border/70 bg-card p-6">
          <h2 className="font-semibold text-foreground">What you can do meanwhile</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Your department records who spoke at each event. Turning up is how you meet them, and
            both of those surfaces are live.
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            <li>
              <Link
                to="/events"
                className="rounded text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Browse events and register
              </Link>
            </li>
            <li>
              <Link
                to="/speaker-feedback"
                className="rounded text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Change or withdraw a rating you left a speaker
              </Link>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
