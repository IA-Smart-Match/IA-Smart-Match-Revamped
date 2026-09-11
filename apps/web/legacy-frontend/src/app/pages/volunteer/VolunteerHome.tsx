/**
 * Home — Event Host portal (the HostHome artboard).
 *
 * The page used to render two `PortalDatasetUnavailable` panels and nothing
 * else, because the legacy `/api/portals/*` backend that fed it is not part of
 * this repository. Two of its sections now have real `/v1` answers and are
 * rendered from them:
 *
 *  - **Your speaker requests** — `GET /v1/units/{unit_id}/host/speaker-requests`
 *    (OQ-CBA-014, `volunteer`-only): what this account filed, soonest first,
 *    with the status the request row itself carries. It never calls the
 *    Connector's queue — that route is `admin`/`coordinator` only and would be
 *    a 403 dressed as an empty home page.
 *  - **Your organization** — `GET /v1/units/{unit_id}/host/organization`
 *    (migration `0036`): the group the host files on behalf of, or the
 *    `host_organization_not_found` 404, which is a state with a next action,
 *    not an error.
 *
 * What still has no answer stays said so: there is no host-assignment domain
 * in this deployment at all — no table, no route — so that panel remains a
 * `PortalDatasetUnavailable` rather than becoming a fabricated list or a
 * red failure banner.
 *
 * Order follows `DESIGN.md`: the things that need doing (describe your
 * organization, file a request, watch one move) come before the identity card.
 *
 * ## No identifier on this page is chosen by the browser
 *
 * `GET /v1/me` says who the caller is; `GET /v1/me/portals` says which portal
 * the server granted them and which unit it covers. That grant's
 * `default_unit_id` is the only unit read — never composed, never from a
 * query string.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Building2, ClipboardList, ShieldAlert } from "lucide-react";

import {
  ApiRequestError,
  fetchMySpeakerRequests,
  fetchOwnHostOrganization,
  type HostOwnOrganization,
  type SpeakerRequest,
} from "../../../lib/api";
import { PortalDatasetUnavailable, PortalIdentityCard } from "../../components/PortalContent";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/** The home page shows the first few; the full list is one click away. */
const RECENT_REQUEST_LIMIT = 5;

/** `settled` keeps "has not come back" and "came back with nothing" apart. */
type Loaded<T> = { data: T | null; error: string | null; settled: boolean };

const REQUESTS_PENDING: Loaded<{ requests: SpeakerRequest[]; truncated: boolean }> = {
  data: null,
  error: null,
  settled: false,
};
const ORGANIZATION_PENDING: Loaded<HostOwnOrganization | "none"> = {
  data: null,
  error: null,
  settled: false,
};

function describeFailure(cause: unknown, fallback: string): string {
  return cause instanceof ApiRequestError ? cause.message : fallback;
}

/**
 * When a request's event happens, at the precision the server resolved.
 * `date_only` is printed exactly as sent and never parsed through `Date` —
 * parsing a bare date is how a 14 March event becomes 13 March for a reader
 * west of the source (ADR-0010's invented midnight).
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
    return time.time_zone === null ? time.on_date : `${time.on_date} (${time.time_zone})`;
  }
  return `The server reported the time as “${time.precision}”.`;
}

/** The organization summary — the three outcomes the route can answer. */
function OrganizationSummary({ state }: { state: Loaded<HostOwnOrganization | "none"> }) {
  if (state.error !== null) {
    return (
      <p
        className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        role="alert"
      >
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{state.error}</span>
      </p>
    );
  }
  if (!state.settled) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        Loading your organization…
      </p>
    );
  }
  if (state.data === "none") {
    return (
      <div className="space-y-3">
        <p className="text-sm leading-6 text-muted-foreground">
          You have not described an organization yet. You can file requests without one; describing
          it stamps each new request with the group behind it.
        </p>
        <Link
          to="/volunteer-portal/organization"
          className="inline-flex items-center rounded-lg border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
        >
          Describe your organization
        </Link>
      </div>
    );
  }
  if (state.data === null) {
    // `settled` with neither an answer nor an error is impossible by
    // construction; the guard keeps the type honest rather than asserting.
    return null;
  }
  const organization = state.data.organization;
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-3">
        <Building2 className="mt-1 h-5 w-5 text-primary" aria-hidden="true" />
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-foreground">{organization.name}</h3>
          <p className="text-sm text-muted-foreground">
            {[
              organization.department,
              organization.member_count === 1
                ? "1 account belongs — yours"
                : `${organization.member_count} accounts belong`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {state.data.self_asserted ? (
            <p className="text-xs text-muted-foreground">
              Described by you; membership is self-asserted until a Speaker Connector can grant it.
            </p>
          ) : null}
        </div>
      </div>
      <Link
        to="/volunteer-portal/organization"
        className="inline-flex items-center text-sm font-semibold text-primary underline"
      >
        View or edit your organization
      </Link>
    </div>
  );
}

export function VolunteerHome() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "volunteer");
  const unitId = grant?.default_unit_id ?? null;

  const [requests, setRequests] =
    useState<Loaded<{ requests: SpeakerRequest[]; truncated: boolean }>>(REQUESTS_PENDING);
  const [organization, setOrganization] =
    useState<Loaded<HostOwnOrganization | "none">>(ORGANIZATION_PENDING);

  const load = useCallback(async () => {
    if (unitId === null) return;

    // Each read settles on its own so one refusal cannot blank the other half
    // of the page.
    try {
      const listing = await fetchMySpeakerRequests(unitId);
      setRequests({
        data: { requests: listing.requests, truncated: listing.truncated },
        error: null,
        settled: true,
      });
    } catch (cause) {
      setRequests({
        data: null,
        error: describeFailure(
          cause,
          "Your speaker requests could not be read and the server gave no reason.",
        ),
        settled: true,
      });
    }

    try {
      const own = await fetchOwnHostOrganization(unitId);
      setOrganization({ data: own, error: null, settled: true });
    } catch (cause) {
      // `host_organization_not_found` is a state — you have described none —
      // branched on the error's code, never its text.
      if (cause instanceof ApiRequestError && cause.code === "host_organization_not_found") {
        setOrganization({ data: "none", error: null, settled: true });
        return;
      }
      setOrganization({
        data: null,
        error: describeFailure(
          cause,
          "Your organization could not be read and the server gave no reason.",
        ),
        settled: true,
      });
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

  // `VolunteerPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is
  // still resolving. Render nothing rather than a header about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  const recent = requests.data === null ? [] : requests.data.requests.slice(0, RECENT_REQUEST_LIMIT);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Home</h1>
        <p className="text-sm text-muted-foreground">
          What you have asked for, and the organization you are asking on behalf of.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
        <p className="text-sm text-muted-foreground">
          <Link to="/volunteer-portal/speaker-request" className="font-semibold text-primary underline">
            Request a speaker
          </Link>{" "}
          for your next event, or{" "}
          <Link to="/volunteer-portal/my-requests" className="font-semibold text-primary underline">
            track the requests you have filed
          </Link>
          .
        </p>
      </header>

      <section
        className="space-y-4 rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
        aria-label="Your speaker requests"
      >
        <h2 className="font-semibold text-foreground">Your speaker requests</h2>

        {requests.error !== null ? (
          <p
            className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
            role="alert"
          >
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{requests.error}</span>
          </p>
        ) : !requests.settled ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading your speaker requests…
          </p>
        ) : recent.length === 0 ? (
          <p className="text-sm leading-6 text-muted-foreground">
            Nothing is listed here yet — the list shows requests this account filed.{" "}
            <Link to="/volunteer-portal/speaker-request" className="font-semibold text-primary underline">
              File your first request
            </Link>
            .
          </p>
        ) : (
          <>
            <ul className="space-y-3">
              {recent.map((request) => (
                <li
                  key={request.request_id}
                  className="flex items-start gap-3 rounded-xl border border-border/70 p-4"
                >
                  <ClipboardList className="mt-1 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
                  <div className="min-w-0 space-y-1">
                    <p className="font-semibold text-foreground">{request.title}</p>
                    <p className="text-sm text-muted-foreground">
                      {describeRequestTime(request)} ·{" "}
                      {request.is_virtual ? "Virtual" : "In person"} ·{" "}
                      {request.publication_status} · review {request.review_status}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="text-sm text-muted-foreground">
              <Link to="/volunteer-portal/my-requests" className="font-semibold text-primary underline">
                See all your requests
              </Link>
              {requests.data !== null && requests.data.truncated
                ? " — the server stopped sending before the end, so more exist than it returned."
                : "."}
            </p>
          </>
        )}
      </section>

      <section
        className="space-y-4 rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
        aria-label="Your organization"
      >
        <h2 className="font-semibold text-foreground">Your organization</h2>
        <OrganizationSummary state={organization} />
      </section>

      <PortalIdentityCard me={principal} grant={grant} />

      {/* Still genuinely absent: there is no assignment domain in this
          deployment — no table, no route — so this stays an honest absence
          rather than a list that could only ever be empty. */}
      <PortalDatasetUnavailable
        dataset="Assignments made for you"
        endpoints={["/api/portals/volunteers/{id}/assignments"]}
      />
    </div>
  );
}
