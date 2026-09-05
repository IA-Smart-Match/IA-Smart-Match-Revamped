/**
 * Events — student portal.
 *
 * This page used to load your event registrations from the legacy `/api/portals/*` backend.
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
 *
 * ## B07 — "Add to Calendar"
 *
 * The master plan's B07 records the button this page used to carry: a
 * `handleAddToCalendar` that set a three-second "Calendar event added" toast
 * and did nothing else — no file, no request, no provider. It is gone, removed
 * with the rest of the legacy page body rather than left disabled.
 *
 * A real one now exists to replace it.
 * `GET /v1/units/{unit_id}/events/{event_id}/invite.ics` returns the .ics bytes
 * for a single event; a student may call it for an event they have an
 * attendance record for; and it refuses with a `409` naming the missing fact
 * rather than issuing an invented slot (finding F-003). It needs exactly one
 * input this page cannot obtain: an `event_id`.
 *
 * There is no student-scoped event read in `/v1`. The catalog route
 * (`GET /v1/units/{unit_id}/events`) is gated to `admin` and `coordinator`
 * because it carries extraction provenance and source references, and the
 * legacy registration list this page was built on does not exist here. So the
 * honest state is a working endpoint with nothing on this page to point it at,
 * and the section below says exactly that.
 *
 * What it deliberately does not do is manufacture something to link from. A
 * download button beside a placeholder event would be B07 again with a real URL
 * attached — worse than the toast rather than better, because the toast at
 * least did not hand anybody a file claiming a date. See
 * `docs/plans/open-questions/calendar-deferred.md` OQ-004.
 */

import { PortalDatasetUnavailable } from "../../components/PortalContent";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

export function StudentEvents() {
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
        <h1 className="text-2xl font-semibold text-foreground">Events</h1>
        <p className="text-sm text-muted-foreground">Events you have registered for.</p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <div className="space-y-4">
        <PortalDatasetUnavailable
          dataset="Your event registrations"
          endpoints={["/api/portals/students/{id}/registrations"]}
        />

        {/*
          B07. Stated rather than shown, because there is nothing truthful to
          show: the .ics route is real and callable, and this page has no
          event id to call it with. A button here would need an event to sit
          beside, and inventing one is the defect this whole page was rewritten
          to remove.
        */}
        <section
          className="rounded-2xl border border-dashed border-border bg-muted/30 p-6"
          aria-label="Calendar downloads"
        >
          <h2 className="font-semibold text-foreground">Calendar downloads</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            This page used to offer an <em>Add to Calendar</em> button that showed a success
            message and did nothing. It has been removed. In its place the server now serves a
            real calendar file — an{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">.ics</code> download you
            import into whichever calendar you use — for any event whose start <em>and</em> end
            times are actually recorded. When they are not, it declines and says which one is
            missing, instead of guessing a time and putting it in your calendar.
          </p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Served by{" "}
            <code className="rounded bg-muted px-1.5 py-0.5">
              GET /v1/units/&#123;unit_id&#125;/events/&#123;event_id&#125;/invite.ics
            </code>
            . No link appears here yet because this deployment has no route that lists a
            student&rsquo;s own events, so this page holds no event to offer one for.
          </p>
        </section>
      </div>
    </div>
  );
}
