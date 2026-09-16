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
 * ## One address, two states
 *
 * `?request={id}` selects one request out of the loaded list into a detail
 * view — the same pattern `?run=` uses on the Connector's match-runs
 * address. The parameter names a row the server already returned; the detail
 * re-reads nothing, because `SpeakerRequestResponse` is the whole of what
 * the host route discloses. An id that names nothing in the list — a stale
 * bookmark, a request another account filed, a row past the server's cap —
 * gets the honest "not in what the server returned" state, not a guess.
 *
 * ## The host's view of a match is the request's own status
 *
 * A Speaker Connector scores the request against the unit's roster, invites
 * a shortlist, and records a confirmation. **No route in this release
 * reports any of that to an Event Host account**, and the detail view says
 * so in words rather than leaving a gap where a match card could be
 * invented: who was asked and who declined stays with the Connector
 * (OQ-CBA-042), the confirmed-speaker hand-off read is `admin`/`coordinator`
 * only, and the row this page renders carries no invitation, batch, count or
 * match field to compute from. What a host watches is `review_status` and
 * `publication_status` — the request's own state — and the detail presents
 * those plainly rather than implying a progress bar the contract cannot
 * fill.
 *
 * ## Nothing here reports what it did not observe
 *
 * The list is a server response, rendered exactly as it came back — the
 * same fields `VolunteerSpeakerRequest.tsx` already showed this host on
 * submission: title, description, time, virtual flag, location, industries,
 * roles, `publication_status`, `review_status`, and the two timestamps.
 *
 * ## No identifier on this page is chosen by the browser
 *
 * `GET /v1/me` says who the caller is; `GET /v1/me/portals` says which
 * portal the server granted them and which unit it covers. That grant's
 * `default_unit_id` is the only unit read here — never composed, never read
 * from a query string. The `request` parameter selects *which already
 * returned row* to look at; it is never sent back to the server.
 */

import { useCallback } from "react";
import { useSearchParams } from "react-router";
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
import { useScopedQuery } from "../../hooks/useScopedQuery";

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

/**
 * When a request's event happens, at the precision the server resolved.
 * `date_only` is printed exactly as sent and never parsed through `Date`:
 * parsing a bare date and formatting it back is how a 14 March event becomes
 * 13 March for a reader west of the source (ADR-0010's invented midnight).
 */
function describeRequestTime(request: SpeakerRequest): string {
  const time = request.time;
  if (time.precision === "exact" && time.starts_at !== null) {
    return new Date(time.starts_at).toLocaleString(undefined, {
      timeZone: time.time_zone ?? undefined,
      timeZoneName: "short",
    });
  }
  if (time.precision === "date_only" && time.on_date !== null) {
    return time.time_zone === null
      ? `${time.on_date} — day only, no time stated`
      : `${time.on_date} — day only, no time stated (${time.time_zone})`;
  }
  return `The server reported the time as “${time.precision}”.`;
}

/** One filed request in the list, with the door into its detail state. */
function RequestCard({
  request,
  onOpen,
}: {
  request: SpeakerRequest;
  onOpen: (requestId: string) => void;
}) {
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
        <dt className="text-muted-foreground">When</dt>
        <dd className="text-foreground">{describeRequestTime(request)}</dd>
        <dt className="text-muted-foreground">Format</dt>
        <dd className="text-foreground">
          {request.is_virtual
            ? "Virtual — proximity is not considered"
            : [request.location_city, request.location_postal_code].filter(Boolean).join(" ") ||
              "In person"}
        </dd>
        <dt className="text-muted-foreground">Status</dt>
        <dd className="text-foreground">
          {request.publication_status} · review {request.review_status}
        </dd>
      </dl>
      <div>
        <button
          type="button"
          onClick={() => onOpen(request.request_id)}
          className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
        >
          Open this request
        </button>
      </div>
    </li>
  );
}

/**
 * One request in full — the row the list already held, laid out completely,
 * plus the honest answer to "has it been matched yet".
 */
function RequestDetail({
  request,
  onBack,
}: {
  request: SpeakerRequest;
  onBack: () => void;
}) {
  return (
    <div className="space-y-6">
      <button
        type="button"
        onClick={onBack}
        className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
      >
        Back to your requests
      </button>

      <section
        className="space-y-3 rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
        aria-label="Request detail"
      >
        <h2 className="text-lg font-semibold text-foreground">{request.title}</h2>
        <p className="text-sm text-muted-foreground">
          {request.description ?? "No description on record"}
        </p>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-muted-foreground">Reference</dt>
          <dd className="font-mono text-xs text-foreground">{request.request_id}</dd>
          <dt className="text-muted-foreground">When</dt>
          <dd className="text-foreground">{describeRequestTime(request)}</dd>
          <dt className="text-muted-foreground">Format</dt>
          <dd className="text-foreground">
            {request.is_virtual
              ? "Virtual — proximity is not considered"
              : [request.location_city, request.location_postal_code]
                  .filter(Boolean)
                  .join(" ") || "In person"}
          </dd>
          <dt className="text-muted-foreground">Industries</dt>
          <dd className="text-foreground">
            {request.industries.map((item) => item.display_name).join(", ") || "None recorded"}
          </dd>
          <dt className="text-muted-foreground">Roles</dt>
          <dd className="text-foreground">
            {request.roles.map((item) => item.display_name).join(", ") || "None recorded"}
          </dd>
          <dt className="text-muted-foreground">Filed</dt>
          <dd className="text-foreground">{new Date(request.created_at).toLocaleString()}</dd>
          <dt className="text-muted-foreground">Last updated</dt>
          <dd className="text-foreground">{new Date(request.updated_at).toLocaleString()}</dd>
        </dl>
      </section>

      <section
        className="space-y-3 rounded-2xl border border-border/70 bg-card p-6"
        aria-label="Where this request stands"
      >
        <h2 className="font-semibold text-foreground">Where this request stands</h2>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-muted-foreground">Review</dt>
          <dd className="text-foreground">{request.review_status}</dd>
          <dt className="text-muted-foreground">Publication</dt>
          <dd className="text-foreground">{request.publication_status}</dd>
        </dl>
        <p className="text-sm leading-6 text-muted-foreground">
          A Speaker Connector scores this request against the unit&apos;s speaker roster, invites a
          shortlist, and records a confirmation. That work is theirs to run and theirs to read: no
          screen in this portal reports who was asked or who was shortlisted, and that is a
          decision about what a host is owed, not an outage. When a speaker is confirmed for your
          event, the Connector tells you directly — the two statuses above are what the request row
          itself publishes until then.
        </p>
      </section>
    </div>
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

  // `?request={id}` selects the detail state. It names a row the server
  // already returned — it is never sent back to the server, so a stale or
  // foreign id is a display question, not a permission question.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedRequestId = searchParams.get("request");

  // The same cache slot `VolunteerHome`'s recent-requests card reads, so the
  // home page's read is this page's warm-up. A failed read shows no rows
  // rather than stale ones — the same rule the hand-rolled version kept.
  const listQuery = useScopedQuery({
    resource: "my-speaker-requests",
    params: [unitId],
    queryFn: () => fetchMySpeakerRequests(unitId as string),
    enabled: unitId !== null,
  });
  const requests: SpeakerRequest[] = listQuery.isSuccess ? listQuery.data.requests : [];
  const truncated = listQuery.isSuccess ? listQuery.data.truncated : false;
  const loaded = !listQuery.isPending;
  const loadError = listQuery.isError
    ? refusalMessage(
        listQuery.error,
        "Your filed requests could not be read and the server gave no reason.",
      )
    : null;

  const reload = useCallback(async () => {
    await listQuery.refetch();
  }, [listQuery]);

  // `VolunteerPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the
  // mapping is still resolving. Render nothing rather than a page about a
  // portal that may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  const selected =
    selectedRequestId === null
      ? null
      : (requests.find((request) => request.request_id === selectedRequestId) ?? null);

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

      {selectedRequestId !== null && loaded && loadError === null ? (
        selected !== null ? (
          <RequestDetail
            request={selected}
            onBack={() => setSearchParams({})}
          />
        ) : (
          <div
            className="space-y-3 rounded-2xl border border-border/70 bg-card p-6"
            role="status"
          >
            <p className="text-sm leading-6 text-muted-foreground">
              The request this address names is not in the list the server returned — it may have
              been filed under a different account, or the list stopped short of it. Only requests
              this account filed can be opened here.
            </p>
            <button
              type="button"
              onClick={() => setSearchParams({})}
              className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
            >
              Back to your requests
            </button>
          </div>
        )
      ) : null}

      {selectedRequestId === null && loaded && loadError === null && requests.length === 0 ? (
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

      {selectedRequestId === null && requests.length > 0 ? (
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
                  <RequestCard
                    key={request.request_id}
                    request={request}
                    onOpen={(requestId) => setSearchParams({ request: requestId })}
                  />
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
