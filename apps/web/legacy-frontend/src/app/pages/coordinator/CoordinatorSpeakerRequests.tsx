/**
 * Speaker requests — Connector Dashboard (the ConnectorRequests artboard).
 *
 * The read side of customer §12's intake: `GET
 * /v1/units/{unit_id}/speaker-requests` (`routers/speaker_requests.py`,
 * `admin`/`coordinator`) returns every request a host has filed with this
 * unit, soonest event first, and this page renders what came back — real
 * titles, real times at the precision the server resolved, real statuses.
 * Nothing is stubbed, nothing is sampled, and no row here is invented.
 *
 * ## One address, two states
 *
 * `?request={id}` selects one row out of the loaded list into a detail view —
 * the same pattern `?run=` uses on the match-runs address. The parameter
 * names a request the server already returned; the detail re-reads nothing,
 * because `SpeakerRequestResponse` is the whole of what the queue route
 * discloses. An id that names nothing in the list gets the honest "not in
 * what the server returned" state rather than a guess.
 *
 * ## Who is asking — and the boundary of what the server says
 *
 * The request row carries **no filer field**: `SpeakerRequestResponse` has no
 * `filed_by`, and the `host_organization_id` stamp the create path writes onto
 * the event is published by no read model. So the detail view cannot say which
 * account or organization filed a given request, and it says so rather than
 * guessing from the directory. What it can show is the directory itself —
 * `GET /v1/units/{unit_id}/host-organizations` (`admin`/`coordinator`), every
 * organization that files into this unit with what each host typed about it —
 * which is the answer to the question the directory exists for: "who asks this
 * unit for speakers".
 *
 * ## Starting a match from a request
 *
 * `POST /v1/units/{unit_id}/match-runs` takes the request's id and a candidate
 * pool — and the pool is a Connector's choice, made from the roster, not
 * something this page may silently fill. So the action hands off to "Run a
 * match" with `?request={id}` naming the request, which pre-selects it in the
 * form the Connector already reviews and submits. This page invents no run id
 * and claims no outcome; the hand-off is a link, not a submission.
 *
 * ## Not authorization
 *
 * The listing and the directory are authorized server-side per request against
 * the loaded unit, and a unit in another tenant answers `404` rather than
 * `403`. This page renders the server's refusal as the answer it is rather
 * than hiding the section — the posture every page in this shell takes.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Building2, Inbox } from "lucide-react";

import {
  ApiRequestError,
  fetchHostOrganizations,
  fetchSpeakerRequests,
  type HostOrganizationDirectory,
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
const DIRECTORY_PENDING: Loaded<HostOrganizationDirectory> = {
  data: null,
  error: null,
  settled: false,
};

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

function RequestRow({
  request,
  onOpen,
}: {
  request: SpeakerRequest;
  onOpen: (requestId: string) => void;
}) {
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
      <div className="mt-3">
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
 * The unit's host-organization directory, shown on the detail for the reason
 * the route exists — a Connector reading an incoming request needs to know who
 * is asking. It is *not* presented as this request's filer: no read model
 * publishes that link, and the section heading says so.
 */
function OrganizationDirectory({ state }: { state: Loaded<HostOrganizationDirectory> }) {
  if (state.error !== null) {
    return (
      <p
        role="alert"
        className="mt-3 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
      >
        {state.error}
      </p>
    );
  }
  if (state.data === null) {
    return (
      <p className="mt-3 text-sm text-muted-foreground" role="status">
        {state.settled
          ? "The directory returned nothing."
          : "Loading the unit's host organizations…"}
      </p>
    );
  }
  if (state.data.organizations.length === 0) {
    return (
      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        No host has described an organization in this unit yet — filing a request does not require
        one, so this request&apos;s filer may simply have none on record.
      </p>
    );
  }
  return (
    <>
      <ul className="mt-3 space-y-2">
        {state.data.organizations.map((organization) => (
          <li
            key={organization.organization_id}
            className="rounded-xl border border-border/70 p-4"
          >
            <p className="font-medium text-foreground">{organization.name}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {[
                organization.department,
                organization.default_location,
                organization.member_count === 1
                  ? "1 account belongs"
                  : `${organization.member_count} accounts belong`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            {organization.logistics_contact !== null && (
              <p className="mt-1 text-sm text-muted-foreground">
                Day-of logistics: {organization.logistics_contact}
              </p>
            )}
          </li>
        ))}
      </ul>
      {state.data.truncated && (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          The server stopped sending before the end of the directory, so more organizations exist
          than were loaded here. No control on this page can ask the route for the rest.
        </p>
      )}
    </>
  );
}

/**
 * One request in full, who is asking (to the extent the server says), and the
 * door into a match run that answers it.
 */
function RequestDetail({
  request,
  directory,
  onBack,
  onStartMatch,
}: {
  request: SpeakerRequest;
  directory: Loaded<HostOrganizationDirectory>;
  onBack: () => void;
  onStartMatch: (requestId: string) => void;
}) {
  return (
    <div className="space-y-6">
      <button
        type="button"
        onClick={onBack}
        className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
      >
        Back to the queue
      </button>

      <section
        className="space-y-3 rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
        aria-label="Request detail"
      >
        <h2 className="text-lg font-semibold text-foreground">{request.title}</h2>
        {request.description !== null && (
          <p className="text-sm leading-6 text-muted-foreground">{request.description}</p>
        )}
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[12rem_1fr]">
          <dt className="text-muted-foreground">Reference</dt>
          <dd className="font-mono text-xs text-foreground">{request.request_id}</dd>
          <dt className="text-muted-foreground">When</dt>
          <dd className="text-foreground">{describeRequestTime(request.time)}</dd>
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
          <dt className="text-muted-foreground">Publication status</dt>
          <dd className="text-foreground">{request.publication_status}</dd>
          <dt className="text-muted-foreground">Review status</dt>
          <dd className="text-foreground">{request.review_status}</dd>
          <dt className="text-muted-foreground">Filed</dt>
          <dd className="text-foreground">{new Date(request.created_at).toLocaleString()}</dd>
          <dt className="text-muted-foreground">Last updated</dt>
          <dd className="text-foreground">{new Date(request.updated_at).toLocaleString()}</dd>
        </dl>
      </section>

      <section
        className="space-y-3 rounded-2xl border border-border/70 bg-card p-6"
        aria-label="Who is asking"
      >
        <div className="flex items-start gap-2">
          <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <h2 className="font-semibold text-foreground">Who is asking</h2>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          The request the server returns does not name its filer: the response carries no account
          or organization field, and the organization stamp written when the request was filed is
          published by no read model. Below is the unit&apos;s directory — every organization that
          has described itself to this unit — which is the honest answer this surface can give to
          &quot;who asks us for speakers&quot;.
        </p>
        <OrganizationDirectory state={directory} />
      </section>

      <section
        className="space-y-3 rounded-2xl border border-border/70 bg-card p-6"
        aria-label="Start a match run"
      >
        <h2 className="font-semibold text-foreground">Answer it with a match run</h2>
        <p className="text-sm leading-6 text-muted-foreground">
          A match run scores the contacts you choose against this request. The run starts on{" "}
          <span className="font-medium text-foreground">Run a match</span> with this request
          pre-selected — the candidate pool is still yours to pick there, and the server enforces
          its own rules about the submission.
        </p>
        <button
          type="button"
          onClick={() => onStartMatch(request.request_id)}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
        >
          Start a match from this request
        </button>
      </section>
    </div>
  );
}

export function CoordinatorSpeakerRequests() {
  const principal = useAuthenticatedPrincipal();
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;
  const navigate = useNavigate();

  const [requests, setRequests] = useState<Loaded<SpeakerRequestList>>(PENDING);
  const [directory, setDirectory] = useState<Loaded<HostOrganizationDirectory>>(DIRECTORY_PENDING);

  // `?request={id}` selects the detail state. It names a row the server
  // already returned — never sent back, so a stale or foreign id is a display
  // question, not a permission question.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedRequestId = searchParams.get("request");

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

  // The directory loads only when a detail is open — it answers "who is
  // asking", which is a detail question, not a list one.
  useEffect(() => {
    if (unitId === null || selectedRequestId === null) {
      setDirectory(DIRECTORY_PENDING);
      return;
    }
    let cancelled = false;
    setDirectory(DIRECTORY_PENDING);
    void fetchHostOrganizations(unitId)
      .then((listing) => {
        if (!cancelled) setDirectory({ data: listing, error: null, settled: true });
      })
      .catch((cause) => {
        if (!cancelled) {
          setDirectory({
            data: null,
            error:
              cause instanceof ApiRequestError
                ? cause.message
                : "The unit's host-organization directory could not be read and the server gave no reason.",
            settled: true,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [unitId, selectedRequestId]);

  // The shell renders `PortalGate` when the server granted no such portal, so
  // reaching here without a grant means the mapping is still resolving.
  if (grant === null) {
    return null;
  }

  const listing = requests.data;
  const selected =
    selectedRequestId === null || listing === null
      ? null
      : (listing.requests.find((request) => request.request_id === selectedRequestId) ?? null);

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
      ) : selectedRequestId !== null && requests.settled && requests.error === null ? (
        selected !== null ? (
          <RequestDetail
            request={selected}
            directory={directory}
            onBack={() => setSearchParams({})}
            onStartMatch={(requestId) =>
              navigate(`/coordinator-portal/match-runs?request=${encodeURIComponent(requestId)}`)
            }
          />
        ) : (
          <section
            className="space-y-3 rounded-2xl border border-border/70 bg-card p-6"
            aria-label="Request not in the queue"
          >
            <p className="text-sm leading-6 text-muted-foreground">
              The request this address names is not in the queue the server returned — it may have
              been withdrawn, filed under another unit, or beyond the server&apos;s page cap. Only
              requests in the list can be opened here.
            </p>
            <button
              type="button"
              onClick={() => setSearchParams({})}
              className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
            >
              Back to the queue
            </button>
          </section>
        )
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
                        <RequestRow
                          key={request.request_id}
                          request={request}
                          onOpen={(requestId) => setSearchParams({ request: requestId })}
                        />
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
