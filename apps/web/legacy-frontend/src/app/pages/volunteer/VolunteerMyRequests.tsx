/**
 * Your Speaker Requests — Event Host portal (customer §12, read side).
 *
 * `VolunteerSpeakerRequest.tsx` files a request; this page reads back the
 * ones this account filed. Between the two sits `GET
 * /v1/units/{unit_id}/host/speaker-requests`, **OQ-CBA-014**, closed 7
 * September 2026: "a host-scoped read is a different query, not a wider
 * permit". This page calls that route and no other. It must not import
 * {@link fetchSpeakerRequests} — that is the Connector's queue, over every
 * host's filings in the unit, and is `admin`/`coordinator` only server-side.
 * A frontend contract test pins the direction.
 *
 * ## A UI gate is not authorization
 *
 * The route is `volunteer`-only server-side; `admin` and `coordinator`
 * already hold the wider queue and are refused this one on purpose, because
 * they hold something wider, not something narrower. Nothing here decides
 * that — the server does, per request, against the verified principal. A
 * refusal renders as the answer it is.
 *
 * ## What "your requests" means, exactly
 *
 * The only predicate the server applies is `filed_by_user_id ==
 * principal.user_id`. A request filed before this column existed carries no
 * recorded filer and is listed by **nobody**, including the host who filed
 * it — that is a true statement about what the server knows, not a bug in
 * this page, and the empty state below says so rather than implying the
 * account has never filed anything.
 *
 * ## Nothing here reports what it did not observe
 *
 * The list is a server response, rendered exactly as it came back — the
 * same fields `VolunteerSpeakerRequest.tsx` already showed this host on
 * submission: title, description, time, virtual flag, location, industries,
 * roles, `publication_status`, `review_status`, and the two timestamps.
 * Nothing about invitations, declines, matches or confirmed speakers is on
 * this row (OQ-CBA-042), and there is nothing here for a later edit to
 * compute from what is not sent.
 *
 * ## No identifier on this page is chosen by the browser
 *
 * `GET /v1/me` says who the caller is; `GET /v1/me/portals` says which
 * portal the server granted them and which unit it covers. That grant's
 * `default_unit_id` is the only unit read here — never composed, never read
 * from a query string.
 */

import { useCallback, useEffect, useState } from "react";
import { ClipboardList, ShieldAlert } from "lucide-react";

import {
  ApiRequestError,
  fetchMySpeakerRequests,
  type SpeakerRequest,
} from "../../../lib/api";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * Turn a refusal into words a Host can act on, the same discipline
 * `VolunteerConfirmedSpeaker.tsx` uses for its own reads.
 */
function refusalMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiRequestError) {
    if (cause.status === 403) {
      return (
        `The server refused this request (403). ${cause.message} ` +
        "Reading back your own filed requests is granted to Event Host accounts here; this " +
        "account was not granted it. Nothing was changed."
      );
    }
    return cause.message;
  }
  return fallback;
}

/** One filed request, rendered from exactly what the server stored. */
function RequestCard({ request }: { request: SpeakerRequest }) {
  const zone = request.time.time_zone ?? "zone unstated";
  const when =
    request.time.precision === "exact" && request.time.starts_at !== null
      ? `${new Date(request.time.starts_at).toLocaleString()} (${zone})`
      : request.time.on_date !== null
        ? `${request.time.on_date} — day only, no time stated (${zone})`
        : "No date on record";

  return (
    <li className="space-y-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <ClipboardList className="mt-1 h-5 w-5 text-primary" aria-hidden="true" />
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-foreground">{request.title}</h3>
          <p className="text-sm text-muted-foreground">
            {request.description ?? "No description on record"}
          </p>
        </div>
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted-foreground">Reference</dt>
        <dd className="font-mono text-xs text-foreground">{request.request_id}</dd>
        <dt className="text-muted-foreground">When</dt>
        <dd className="text-foreground">{when}</dd>
        <dt className="text-muted-foreground">Format</dt>
        <dd className="text-foreground">
          {request.is_virtual
            ? "Virtual — proximity is not considered"
            : [request.location_city, request.location_postal_code].filter(Boolean).join(" ") ||
              "In person"}
        </dd>
        <dt className="text-muted-foreground">Industries</dt>
        <dd className="text-foreground">
          {request.industries.map((item) => item.display_name).join(", ") || "None recorded"}
        </dd>
        <dt className="text-muted-foreground">Roles</dt>
        <dd className="text-foreground">
          {request.roles.map((item) => item.display_name).join(", ") || "None recorded"}
        </dd>
        <dt className="text-muted-foreground">Status</dt>
        <dd className="text-foreground">
          {request.publication_status} · review {request.review_status}
        </dd>
        <dt className="text-muted-foreground">Last updated</dt>
        <dd className="text-foreground">{new Date(request.updated_at).toLocaleString()}</dd>
      </dl>
    </li>
  );
}

export function VolunteerMyRequests() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them,
  // including the unit id this page reads under.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "volunteer");
  const unitId = grant?.default_unit_id ?? null;

  const [requests, setRequests] = useState<SpeakerRequest[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (unitId === null) return;
    try {
      const page = await fetchMySpeakerRequests(unitId);
      setRequests(page.requests);
      setTruncated(page.truncated);
      setLoadError(null);
    } catch (cause) {
      setRequests([]);
      setTruncated(false);
      setLoadError(
        refusalMessage(
          cause,
          "Your filed requests could not be read and the server gave no reason.",
        ),
      );
    } finally {
      setLoaded(true);
    }
  }, [unitId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // `VolunteerPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the
  // mapping is still resolving. Render nothing rather than a page about a
  // portal that may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Your speaker requests</h1>
        <p className="text-sm text-muted-foreground">
          What you have filed for your unit, soonest event first. A Speaker Connector reviews and
          matches these; nothing here reports who was invited or declined.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      {unitId === null ? (
        <div className="rounded-2xl border border-border/70 bg-card p-6 text-sm text-muted-foreground">
          The server granted this portal but named no org unit for it, so there is nothing to read
          a request list under. Unit assignment is an administrator&apos;s decision and is not
          made here.
        </div>
      ) : null}

      {loadError !== null ? (
        <p
          className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          role="alert"
        >
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{loadError}</span>
        </p>
      ) : null}

      {loaded && loadError === null && requests.length === 0 ? (
        <div
          className="rounded-2xl border border-border/70 bg-card p-6 text-sm text-muted-foreground"
          role="status"
        >
          Nothing is listed here yet. This shows only requests filed under an account the server
          can name as the filer — a request filed before 7 September 2026 has no recorded filer
          and is not listed here even if you were the one who filed it. If you filed one recently
          and do not see it, check with whoever files the Connector's queue.
        </div>
      ) : null}

      {requests.length > 0 ? (
        <>
          {/* The requests this host filed, a page at a time. The pager is a
              window over the rows already returned — it fetches nothing, and
              the `truncated` notice below is the separate statement about the
              server having stopped sending. */}
          <PagedList
            items={requests}
            label="Speaker Requests"
            idPrefix="volunteer-my-speaker-requests"
          >
            {(visibleRequests) => (
              <ul className="space-y-4">
                {visibleRequests.map((request) => (
                  <RequestCard key={request.request_id} request={request} />
                ))}
              </ul>
            )}
          </PagedList>
          {truncated ? (
            <p className="text-xs text-muted-foreground" role="status">
              The server stopped sending at its own limit, so it did not return every request you
              have filed. How many were held back is not something it reported.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
