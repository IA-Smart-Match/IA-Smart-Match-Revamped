/**
 * Coordinator home — coordinator portal.
 *
 * This page used to load your coordinator profile, hosted events and staffing, outreach threads, meeting bookings from the legacy `/api/portals/*` backend.
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

import { PortalDatasetUnavailable, PortalIdentityCard } from "../../components/PortalContent";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * The review queue, and why it is empty rather than absent.
 *
 * This is a *different* gap from the `/api/portals/*` panels above, and it is
 * stated separately because conflating them would hide it. The review workflow
 * genuinely lives in this API — `POST /v1/review-items/{review_item_id}/decision`
 * exists and works — but there is **no list route**. A coordinator can decide
 * a review item only if they already know its id, and no `/v1` path yields
 * one: `scripts/compose_smoke.sh` and the E2E suite both read the id straight
 * out of the database.
 *
 * So this portal cannot render a queue today, and it says so instead of
 * rendering an empty one. An empty list would be a claim that there is nothing
 * to review, which is a statement about the data; the truth is a statement
 * about the API (ADR-0011: unknown is never zero). Fetching the ids from the
 * database to fill it in was explicitly ruled out — a frontend that reaches
 * around a missing endpoint makes the endpoint's absence invisible and
 * un-fixable.
 *
 * Adding `GET /v1/review-items` is the follow-up. It was left out of this PR
 * deliberately: it needs decisions about filtering, pagination, and which
 * statuses are visible to which roles, and those are not decisions to make as
 * a side effect of a login change.
 */
function ReviewQueueUnavailable() {
  return (
    <section
      className="rounded-2xl border border-dashed border-border bg-muted/30 p-6"
      aria-label="Review queue unavailable"
    >
      <h2 className="font-semibold text-foreground">Review queue is not listable yet</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        This API can record a review decision (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
          POST /v1/review-items/&#123;id&#125;/decision
        </code>
        ) but has no route that lists the items awaiting one, so there is no queue to draw. This
        is an empty section because the endpoint is missing — not because your unit has nothing
        pending, which is a question nothing here can currently answer.
      </p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        Needs: <code className="rounded bg-muted px-1.5 py-0.5">GET /v1/review-items</code>{" "}
        (follow-up; deferred because it requires decisions about filtering, pagination, and
        per-role visibility).
      </p>
    </section>
  );
}

export function CoordinatorHome() {
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
      <PortalIdentityCard me={principal} grant={grant} />

      <div className="space-y-4">
        <PortalDatasetUnavailable
          dataset="Your coordinator profile"
          endpoints={["/api/portals/event-coordinators/{id}"]}
        />
        <PortalDatasetUnavailable
          dataset="Hosted events and staffing"
          endpoints={["/api/portals/event-coordinators/{id}/events"]}
        />
        <PortalDatasetUnavailable
          dataset="Outreach threads"
          endpoints={["/api/portals/event-coordinators/{id}/threads"]}
        />
        <PortalDatasetUnavailable
          dataset="Meeting bookings"
          endpoints={["/api/portals/event-coordinators/{id}/meetings"]}
        />
      </div>

      <ReviewQueueUnavailable />
    </div>
  );
}
