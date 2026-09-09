/**
 * My events — coordinator portal.
 *
 * This page used to render nothing but an unavailable panel: hosted events came
 * from the legacy `/api/portals/*` backend, which is not part of this
 * repository. That statement was true about the legacy route and false about
 * this deployment. `GET /v1/units/{unit_id}/events` has existed since the
 * discovery slice (`routers/events.py`) and no portal page was calling it, so
 * a Connector was told their unit's events were unavailable while the server
 * was in a position to list them.
 *
 * Everything on this page comes from three `/v1` routes and nothing else:
 * `GET /v1/me` for who the caller is, `GET /v1/me/portals` for the portal the
 * server granted them and the unit behind it, and
 * `GET /v1/units/{unit_id}/events` for the unit's presentable events. No
 * identifier here is chosen by the browser: the unit is the one the grant
 * carries (`default_unit_id`), never the `VITE_SMARTMATCH_UNIT_ID` build
 * variable, which on a multi-unit pilot is a different unit and would show one
 * unit's events under another unit's name.
 *
 * ## What "presentable" leaves out, and why it is counted rather than hidden
 *
 * The route excludes two kinds of event and reports how many of each it
 * excluded:
 *
 *  - **no resolved date** (ADR-0010 rule 2) — an event that cannot say when it
 *    happens has no place in a listing whose purpose is saying when things
 *    happen, and the legacy `date: "See link for details"` is exactly the
 *    defect that produces;
 *  - **a quarantined tag** (ADR-0012) — a value the closed vocabulary did not
 *    recognise is kept for a human and never rendered, so an event still
 *    carrying one is not finished being extracted.
 *
 * Both counts are rendered. Without them an empty list means two different
 * things — "this unit has no events" and "this unit has seven events the
 * pipeline could not finish" — and ADR-0011's rule that an unknown is never a
 * zero has the corollary that an omission is never an absence.
 *
 * ## Staffing is not on this page, and this page does not imply it is
 *
 * The legacy panel was labelled "Hosted events and staffing". The `/v1`
 * listing answers the first half: it returns events, their resolved time, their
 * mapped tags, their publication and review status, and where each came from.
 * It carries **no staffing** — no assignment, no roster, no open-slot count —
 * and nothing here invents one. Renaming this surface to keep the old label
 * would be the fabricated-equivalence defect the unavailable panels exist to
 * prevent, so the label went instead of the honesty.
 *
 * The nearest real thing is the speaker-invitation tracking on the CBA contact
 * page: who was invited to an event and what they answered. That is a record of
 * invitations and answers, not an event's staffing, and this page links to it
 * as what it is rather than folding it in here.
 *
 * ## Not authorization
 *
 * The listing is authorized server-side per request against the loaded unit —
 * `admin` and `coordinator` only. This page renders the server's `403` as the
 * answer it is rather than hiding the section, which would tell a Connector the
 * capability does not exist.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { CalendarDays } from "lucide-react";

import {
  ApiRequestError,
  fetchUnitEvents,
  type UnitEventList,
  type UnitEventSummary,
} from "../../../lib/api";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * What the listing returned, or why it returned nothing.
 *
 * `settled` distinguishes "the read has not come back" from "the read came back
 * with nothing", which are two different things to say to a reader and which a
 * bare `null` would collapse into one.
 */
type Loaded<T> = { data: T | null; error: string | null; settled: boolean };

const PENDING = { data: null, error: null, settled: false } as const;

function describeFailure(cause: unknown): string {
  // The server's own words where it gave any. `ApiRequestError.message` carries
  // the API's error text, including the refusal a `403` explains, and a
  // rephrasing here would be this page's opinion about someone else's decision.
  return cause instanceof ApiRequestError
    ? cause.message
    : "The unit's events could not be read and the server gave no reason.";
}

/**
 * When an event happens, at the precision the server actually resolved (ADR-0010).
 *
 * `precision` is read rather than inferred from which field is null, and the
 * two real precisions are formatted differently on purpose:
 *
 *  - `exact` has an instant, and it is formatted **in the event's own zone**.
 *    `time_zone` is documented as "never the viewer's and never the server's";
 *    rendering a Los Angeles event in a reader's browser zone would move it.
 *  - `date_only` has a calendar date and no instant. It is printed as the
 *    server sent it and never passed through `Date`, because parsing a bare
 *    date and formatting it back is how a 14 March event becomes a 13 March one
 *    for a reader west of the source — the invented-midnight fabrication
 *    ADR-0010 exists to stop.
 *
 * A third value, `unresolved`, cannot reach this page: the route excludes those
 * events and counts them instead. It is handled anyway, and handled by
 * reporting the server's own word rather than by guessing a date, because a
 * value this build does not expect is not thereby a date.
 */
function describeEventTime(time: UnitEventSummary["time"]): string {
  if (time.precision === "exact" && time.starts_at !== null) {
    return new Date(time.starts_at).toLocaleString(undefined, {
      timeZone: time.time_zone ?? undefined,
      timeZoneName: "short",
    });
  }
  if (time.precision === "date_only" && time.on_date !== null) {
    return time.time_zone === null ? time.on_date : `${time.on_date} (${time.time_zone})`;
  }
  return `The server reported the time as "${time.precision}".`;
}

/** One event, with its provenance shown rather than folded into its title. */
function EventRow({ event }: { event: UnitEventSummary }) {
  return (
    <li className="rounded-xl border border-border/70 p-4">
      <h3 className="font-medium text-foreground">{event.title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{describeEventTime(event.time)}</p>
      {event.description !== null && (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{event.description}</p>
      )}
      {event.tags.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Mapped tags">
          {event.tags.map((tag) => (
            <li
              key={tag}
              className="rounded-full border border-border/70 px-2 py-0.5 text-xs text-muted-foreground"
            >
              {tag}
            </li>
          ))}
        </ul>
      )}
      <dl className="mt-3 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
        <div>
          <dt className="inline font-medium">Publication: </dt>
          <dd className="inline">{event.publication_status}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Review: </dt>
          <dd className="inline">{event.review_status}</dd>
        </div>
        <div>
          {/* ADR-0012: provenance is its own field and never part of a title. A
              `coordinator_entry` event carries an origin and nothing else,
              because a human typing an event fetched nothing. */}
          <dt className="inline font-medium">Origin: </dt>
          <dd className="inline">{event.provenance.origin}</dd>
        </div>
        {event.provenance.source_url !== null && (
          <div className="min-w-0">
            <dt className="inline font-medium">Source: </dt>
            <dd className="inline break-all">{event.provenance.source_url}</dd>
          </div>
        )}
      </dl>
    </li>
  );
}

/**
 * The unit's presentable events, and an honest account of what is not listed.
 *
 * The list is bounded by the server: the route reads one row past its own cap
 * and reports `truncated`, so this renders what the response carried and says
 * when there is more, rather than paging a list it does not hold.
 *
 * TODO(integrator): a shared `src/app/components/PagedList.tsx` is being built
 * on another track and does not exist in this branch. When it lands, swap the
 * `<ul>` below for it and hand it `truncated`. Note that real paging needs
 * `limit`/`offset` query parameters added to `GET /v1/units/{unit_id}/events`
 * first — the route accepts none today, so a pager wired to this response would
 * be a control that cannot fetch a second page. Do not add a second paging
 * component for this page in the meantime.
 */
function HostedEvents({ state }: { state: Loaded<UnitEventList> }) {
  const listing = state.data;

  return (
    <section className="rounded-2xl border border-border p-6" aria-label="Hosted events">
      <div className="flex items-start gap-2">
        <CalendarDays
          className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <div>
          <h2 className="font-semibold text-foreground">Events your unit hosts</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Listed by the server from the events this unit owns. An event with no resolved date,
            or with a tag value still awaiting human review, is not listed — and is counted below
            rather than quietly dropped.
          </p>
        </div>
      </div>

      {state.error !== null ? (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
        >
          {state.error}
        </p>
      ) : listing === null ? (
        <p className="mt-4 text-sm text-muted-foreground" role="status">
          {state.settled ? "The listing returned nothing." : "Loading your unit's events…"}
        </p>
      ) : (
        <>
          {listing.events.length === 0 ? (
            // Safe to say here, and only here: the server answered, and its
            // answer was none. The withheld counts below are what say whether
            // "none" means the unit has no events or that none of the events it
            // has could be listed.
            <p className="mt-4 text-sm text-muted-foreground">
              The server listed no presentable events for this unit.
            </p>
          ) : (
            <ul className="mt-4 space-y-3">
              {listing.events.map((event) => (
                <EventRow key={event.id} event={event} />
              ))}
            </ul>
          )}

          <dl className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-border/70 p-3">
              <dt className="text-xs text-muted-foreground">Not listed — no resolved date</dt>
              <dd className="text-sm tabular-nums text-foreground">
                {listing.withheld_unresolved_date}
              </dd>
            </div>
            <div className="rounded-xl border border-border/70 p-3">
              <dt className="text-xs text-muted-foreground">Not listed — tag awaiting review</dt>
              <dd className="text-sm tabular-nums text-foreground">
                {listing.withheld_quarantined_tags}
              </dd>
            </div>
          </dl>

          {listing.truncated && (
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              This unit holds more presentable events than one response returns, so this is not
              the whole list. The route takes no page parameter yet, and a control here that
              looked like paging would not be.
            </p>
          )}
        </>
      )}
    </section>
  );
}

export function CoordinatorEvents() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them,
  // and of the unit this listing is scoped to.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const [events, setEvents] = useState<Loaded<UnitEventList>>(PENDING);

  const load = useCallback(async () => {
    if (unitId === null) return;

    try {
      const listing = await fetchUnitEvents(unitId);
      setEvents({ data: listing, error: null, settled: true });
    } catch (cause) {
      setEvents({ data: null, error: describeFailure(cause), settled: true });
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

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
        <h1 className="text-2xl font-semibold text-foreground">My events</h1>
        <p className="text-sm text-muted-foreground">
          The events your unit hosts, as the server lists them.
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
          <h2 className="font-semibold text-foreground">No unit to list events for</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            The server granted this account no default unit, and this listing is scoped to one.
            Nothing is shown rather than some other unit&apos;s events.
          </p>
        </section>
      ) : (
        <HostedEvents state={events} />
      )}

      <section
        className="rounded-2xl border border-border/70 bg-muted/30 p-6"
        aria-label="Staffing"
      >
        <h2 className="font-semibold text-foreground">Staffing is not part of this listing</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          This route returns events — when they happen, how they are tagged, whether they are
          published, and where each one came from. It carries no assignment, no roster and no
          open-slot count, and nothing on this page derives one from what it does carry.
        </p>
        <p className="mt-2 text-sm leading-6">
          <Link
            className="font-medium text-foreground underline underline-offset-4"
            to="/coordinator-portal/outreach"
          >
            Speaker invitations and their answers
          </Link>{" "}
          <span className="text-muted-foreground">
            are tracked on the CBA contact page. That is a record of who was invited and what
            they said, which is a narrower fact than an event&apos;s staffing — the two are
            linked here rather than merged.
          </span>
        </p>
      </section>
    </div>
  );
}
