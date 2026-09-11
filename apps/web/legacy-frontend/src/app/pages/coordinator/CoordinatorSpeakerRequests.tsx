/**
 * Speaker requests — Connector Dashboard. **Placeholder, and says so.**
 *
 * The finished page — request detail, the match-progress strip, and "run a
 * match from this request" — is the next card in this PR. This file exists so
 * that the route registered for it is not a dead link in the meantime, and it
 * is written to one rule: *show the real rows, promise nothing else*.
 *
 * So it reads the list the server already serves,
 * `GET /v1/units/{unit_id}/speaker-requests` (`routers/speaker_requests.py`,
 * `admin`/`coordinator`), and renders what came back. Every request a host has
 * filed with this unit is on screen with its real title, its real time at the
 * precision the server resolved, and its real statuses. Nothing is stubbed,
 * nothing is sampled, and no row here is invented.
 *
 * What it does **not** do is pretend to be finished. The notice at the top
 * names the two things this page cannot yet do — open one request, and start a
 * match from it — because a list with no way in reads as a broken page rather
 * than an unfinished one, and a reader who is told which is which can get on
 * with their day. It links to "Run a match" so the work is still reachable by
 * the route that does support it today.
 *
 * ## Not authorization
 *
 * The listing is authorized server-side per request against the loaded unit,
 * and a unit in another tenant answers `404` rather than `403`. This page
 * renders the server's refusal as the answer it is rather than hiding the
 * section — the posture every page in this shell takes.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Inbox } from "lucide-react";

import {
  ApiRequestError,
  fetchSpeakerRequests,
  type SpeakerRequest,
  type SpeakerRequestList,
} from "../../../lib/api";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/** `settled` keeps "has not come back" and "came back with nothing" apart. */
type Loaded<T> = { data: T | null; error: string | null; settled: boolean };

const PENDING: Loaded<SpeakerRequestList> = { data: null, error: null, settled: false };

function describeFailure(cause: unknown): string {
  // The server's own words where it gave any, including the refusal a `403`
  // explains. Rephrasing here would be this page's opinion about someone
  // else's decision.
  return cause instanceof ApiRequestError
    ? cause.message
    : "The unit's speaker requests could not be read and the server gave no reason.";
}

/**
 * When a request's event happens, at the precision the server resolved.
 *
 * `date_only` is printed exactly as sent and never parsed through `Date`:
 * parsing a bare date and formatting it back is how a 14 March event becomes
 * 13 March for a reader west of the source (ADR-0010's invented midnight).
 */
function describeRequestTime(time: SpeakerRequest["time"]): string {
  if (time.precision === "exact" && time.starts_at !== null) {
    return new Date(time.starts_at).toLocaleString(undefined, {
      timeZone: time.time_zone ?? undefined,
      timeZoneName: "short",
    });
  }
  if (time.precision === "date_only" && time.on_date !== null) {
    return time.time_zone === null ? time.on_date : `${time.on_date} (${time.time_zone})`;
  }
  return `The server reported the time as “${time.precision}”.`;
}

function RequestRow({ request }: { request: SpeakerRequest }) {
  const classifications = [...request.industries, ...request.roles];

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <h3 className="font-medium text-foreground">{request.title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {describeRequestTime(request.time)} · {request.is_virtual ? "Virtual" : "In person"}
        {request.location_city !== null && !request.is_virtual ? ` · ${request.location_city}` : ""}
      </p>
      {request.description !== null && (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{request.description}</p>
      )}
      {classifications.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Industries and roles requested">
          {classifications.map((entry) => (
            <li
              key={`${entry.taxonomy_version}:${entry.code}`}
              className="rounded-full border border-border/70 px-2 py-0.5 text-xs text-muted-foreground"
            >
              {entry.display_name}
            </li>
          ))}
        </ul>
      )}
      <dl className="mt-3 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
        <div>
          <dt className="inline font-medium">Publication: </dt>
          <dd className="inline">{request.publication_status}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Review: </dt>
          <dd className="inline">{request.review_status}</dd>
        </div>
      </dl>
    </li>
  );
}

export function CoordinatorSpeakerRequests() {
  const principal = useAuthenticatedPrincipal();
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const [requests, setRequests] = useState<Loaded<SpeakerRequestList>>(PENDING);

  const load = useCallback(async () => {
    if (unitId === null) return;
    try {
      const listing = await fetchSpeakerRequests(unitId);
      setRequests({ data: listing, error: null, settled: true });
    } catch (cause) {
      setRequests({ data: null, error: describeFailure(cause), settled: true });
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

  // The shell renders `PortalGate` when the server granted no such portal, so
  // reaching here without a grant means the mapping is still resolving.
  if (grant === null) {
    return null;
  }

  const listing = requests.data;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Speaker requests</h1>
        <p className="text-sm text-muted-foreground">
          Requests event hosts have filed with your unit, as the server lists them.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <section
        className="rounded-2xl border border-dashed border-border bg-muted/30 p-5"
        aria-label="What this page cannot do yet"
      >
        <h2 className="font-semibold text-foreground">
          Speaker requests — the list is real, the detail view is coming in this release
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Every request below came from the server just now. What is not built yet is opening one
          request to see its match progress, and starting a match run from it. Until it is, start a
          run from{" "}
          <Link
            className="font-medium text-foreground underline underline-offset-4"
            to="/coordinator-portal/match-runs"
          >
            Run a match
          </Link>
          , which does support it today.
        </p>
      </section>

      {unitId === null ? (
        <section
          className="rounded-2xl border border-dashed border-border bg-muted/30 p-6"
          aria-label="No unit assigned"
        >
          <h2 className="font-semibold text-foreground">No unit to list requests for</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            The server granted this account no default unit, and this listing is scoped to one.
            Nothing is shown rather than some other unit&apos;s requests.
          </p>
        </section>
      ) : (
        <section
          className="rounded-2xl border border-border p-6"
          aria-label="Filed speaker requests"
        >
          <div className="flex items-start gap-2">
            <Inbox className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <h2 className="font-semibold text-foreground">Filed with your unit</h2>
          </div>

          {requests.error !== null ? (
            <p
              role="alert"
              className="mt-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
            >
              {requests.error}
            </p>
          ) : listing === null ? (
            <p className="mt-4 text-sm text-muted-foreground" role="status">
              {requests.settled
                ? "The listing returned nothing."
                : "Loading your unit's speaker requests…"}
            </p>
          ) : listing.requests.length === 0 ? (
            <p className="mt-4 text-sm leading-6 text-muted-foreground">
              No event host has filed a speaker request with this unit yet. When one does, it
              appears here and in the Inbox count beside this page&apos;s name.
            </p>
          ) : (
            <>
              <div className="mt-4">
                <PagedList
                  items={listing.requests}
                  label="speaker requests"
                  idPrefix="unit-speaker-requests"
                >
                  {(visible) => (
                    <ul className="space-y-3">
                      {visible.map((request) => (
                        <RequestRow key={request.request_id} request={request} />
                      ))}
                    </ul>
                  )}
                </PagedList>
              </div>
              {listing.truncated && (
                <p className="mt-3 text-xs leading-5 text-muted-foreground">
                  The server stopped sending before the end of this unit&apos;s requests, so more
                  exist than were loaded here. No control on this page can ask the route for the
                  rest.
                </p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
