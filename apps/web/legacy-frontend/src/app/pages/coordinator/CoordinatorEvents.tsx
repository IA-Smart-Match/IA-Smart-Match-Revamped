/**
 * Events — Connector Dashboard. **One page, merged from two.**
 *
 * ## Why there were two, and why that was a defect rather than a layout
 *
 * A Speaker Connector's events lived on two screens in two shells. This one,
 * in the coordinator portal, *listed* the unit's events from
 * `GET /v1/units/{unit_id}/events` with their provenance and an honest account
 * of what the route withheld. A second, `pages/Events.tsx` in the retired
 * admin shell, *created, edited and published* them and configured each
 * event's feedback QR.
 *
 * Neither surface was role-restricted in a way that justified the split. Every
 * route behind both — the listing, `POST`/`PATCH /v1/units/{unit_id}/events`,
 * `POST .../events/{id}/publish`, and the feedback-QR pair — is
 * `admin`/`coordinator` server-side. The two pages were separated by which
 * *shell* happened to host them, and since `admin` and `coordinator` are one
 * persona the shells merged, so the pages do too.
 *
 * What was lost by having two: a coordinator could see their unit's events and
 * not edit them, and an administrator could edit an event without the
 * withheld-row counts that say whether the list they were looking at was the
 * whole list. Both halves are here now, reading one query.
 *
 * ## Everything the listing half kept
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
 * Both counts are rendered, and both are the server's own. Without them an
 * empty list means two different things — "this unit has no events" and "this
 * unit has seven events the pipeline could not finish" — and ADR-0011's rule
 * that an unknown is never a zero has the corollary that an omission is never
 * an absence. `truncated` is rendered too, and says something different from
 * the pager's range line: the notice is about rows the browser never received,
 * the range line about how much of what arrived is drawn.
 *
 * Provenance stays its own field and is never folded into a title (ADR-0012).
 * A `coordinator_entry` event carries an origin and no source URL, because a
 * human typing an event fetched nothing.
 *
 * ## Everything the editor half kept
 *
 * **No fake success.** Every notice on this page is set in a mutation's
 * `onSuccess`, after the server's response. Nothing is marked saved,
 * published, or QR-configured optimistically, and no list is spliced by hand —
 * the query is invalidated and re-read, because the server is the thing that
 * knows what happened.
 *
 * **The publish refusal is surfaced, not swallowed.** `publishManualEvent`
 * answers a `422` naming the fields still missing; `eventErrorMessage` renders
 * them and the form keeps every value the reader typed. A publish that failed
 * must never look like one that worked, and a reader must never have to retype
 * a form to find out why.
 *
 * **Duplicate submits are blocked** while a mutation is pending, and creation
 * carries an `Idempotency-Key` held in a ref for the life of one draft, so a
 * double-click cannot mint two events.
 *
 * **The QR is generated locally and reports opens only.** `QRCodeCard` renders
 * the asset with the `qrcode` package in this bundle; the destination is never
 * sent to a third-party QR service. A `404` from `fetchFeedbackQr` is a real
 * answer — this event has no QR yet — and is mapped to `null` rather than an
 * error, because "not configured" and "could not be read" are different things
 * to tell a reader.
 *
 * ## The session-local `recent` list, and what it is not
 *
 * `GET /v1/units/{unit_id}/events` returns only *presentable* events, so a
 * brand-new draft with an unresolved schedule does not appear in it at all.
 * There is no "my drafts" route. So this page keeps a session-local list of
 * the events **this tab itself successfully wrote**, seeded only from server
 * responses, and merges it with the catalog for display (`mergeEventListings`,
 * unit-tested in `../eventListings.ts`).
 *
 * It is not a substitute catalog. It is never populated by anything but this
 * tab's own writes, it is lost on reload, and it is merged with — never
 * substituted for — what the server sent. Rendering `recent` alone would show
 * a reader only their own writes and hide every event the unit already holds,
 * which is why the drafts panel says on screen what it is holding and why.
 *
 * ## Scope and authorization
 *
 * The unit is the one the server granted this account,
 * `PortalDescriptor.default_unit_id` out of `GET /v1/me/portals` — never the
 * `VITE_SMARTMATCH_UNIT_ID` build variable, which on a multi-unit pilot is a
 * different unit and would show one unit's events under another unit's name.
 * The retired page asked for the `admin` portal's unit; there is no `admin`
 * portal any more, and `coordinator` is the grant both stored roles resolve to.
 *
 * Route guarding is UX only. Every route here is authorized server-side per
 * request against the loaded unit, and this page renders the server's refusal
 * as the answer it is rather than hiding the controls and implying the
 * capability is absent.
 *
 * ## The month view
 *
 * The hosted-events section draws the same `listing.events` two ways — a
 * list, or a month grid (`CoordinatorEventsCalendar`). It is a *view*, not a
 * second fetch: the route accepts no `from`/`to` window and caps at 200
 * rows, so paging the grid re-buckets the response already held and the
 * `truncated` notice stays on screen in both views. The retired `/calendar`
 * address redirects to this page, and this view is the successor to what it
 * served — minus the coverage and volunteer overlays, which the API has no
 * domain for and nothing here fakes. Placement obeys ADR-0010: an event that
 * resolves to no calendar day is named under the grid, not guessed onto one.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { CalendarDays, List, Plus, Save } from "lucide-react";

import { QRCodeCard } from "@/components/QRCodeCard";
import { CoordinatorEventsCalendar } from "./CoordinatorEventsCalendar";
import {
  ApiRequestError,
  createManualEvent,
  fetchFeedbackQr,
  fetchManualEvent,
  fetchUnitEvents,
  publishManualEvent,
  saveFeedbackQr,
  updateManualEvent,
  type ManualEvent,
  type ManualEventInput,
  type UnitEventSummary,
} from "@/lib/api";
import {
  blankEventForm,
  categoryOptions,
  EventFormFields,
  formFromManualEvent,
  inputFromEventForm,
  type EventFormState,
} from "../EventsSections";
import { mergeEventListings, type EventListing } from "../eventListings";
import { PagedList } from "../../components/PagedList";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * When an event happens, at the precision the server actually resolved
 * (ADR-0010).
 *
 * `precision` is read rather than inferred from which field is null, and the
 * two real precisions are formatted differently on purpose:
 *
 *  - `exact` has an instant, formatted **in the event's own zone**.
 *    `time_zone` is documented as "never the viewer's and never the server's";
 *    rendering a Los Angeles event in a reader's browser zone would move it.
 *  - `date_only` has a calendar date and no instant. It is printed as the
 *    server sent it and never passed through `Date`, because parsing a bare
 *    date and formatting it back is how a 14 March event becomes a 13 March
 *    one for a reader west of the source — the invented midnight ADR-0010
 *    exists to stop.
 *
 * A third value, `unresolved`, cannot reach the listing: the route excludes
 * those events and counts them instead. It is handled anyway, by reporting the
 * server's own word rather than guessing a date, because a value this build
 * does not expect is not thereby a date.
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
  return `The server reported the time as “${time.precision}”.`;
}

/** One catalog event, with its provenance shown rather than folded into its title. */
function EventRow({
  event,
  selected,
  onOpen,
}: {
  event: UnitEventSummary;
  selected: boolean;
  onOpen: () => void;
}) {
  return (
    <li
      className={`rounded-xl border p-4 ${
        selected ? "border-primary bg-primary/5" : "border-border/70"
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-medium text-foreground">{event.title}</h3>
        <button
          type="button"
          onClick={onOpen}
          className="min-h-[40px] shrink-0 rounded-xl border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          Edit this event
        </button>
      </div>
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

/** The server's own words where it gave any, including the refusal a 403 explains. */
function describeFailure(cause: unknown): string {
  return cause instanceof ApiRequestError
    ? cause.message
    : "The unit's events could not be read and the server gave no reason.";
}

/**
 * The publish refusal, rendered as the list of fields it names.
 *
 * `publishManualEvent` answers a `422` whose `details.fields` enumerates what
 * is still missing. Printing "could not publish" over that would throw away
 * the only part a reader can act on.
 */
function eventErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const fields = error.details?.fields;
    if (Array.isArray(fields) && fields.every((field) => typeof field === "string")) {
      return `Complete these fields before publishing: ${fields
        .map((field) => String(field).replace(/_/g, " "))
        .join(", ")}.`;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "The event could not be saved.";
}

export function CoordinatorEvents() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them,
  // and of the unit every read and write below is scoped to.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const principalKey = usePrincipalKey();
  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<ManualEvent | null>(null);
  const [form, setForm] = useState<EventFormState>(blankEventForm);
  const [notice, setNotice] = useState("");
  const [recent, setRecent] = useState<ManualEvent[]>([]);
  // How the hosted-events section draws the response: the list, or the month
  // grid. One response, two views — see this file's header.
  const [eventsView, setEventsView] = useState<"list" | "month">("list");
  // A failure to *open* an event, which is neither a list failure nor a save
  // failure and so has nowhere else to be reported. Never swallowed: a click
  // that silently does nothing is indistinguishable from a broken button.
  const [openError, setOpenError] = useState("");
  const createKey = useRef(crypto.randomUUID());

  const listQuery = useQuery({
    queryKey: [principalKey, "unit-events", unitId] as const,
    queryFn: () => fetchUnitEvents(unitId as string),
    enabled: Boolean(principalKey && unitId),
  });

  const qrQuery = useQuery({
    queryKey: [principalKey, "feedback-qr", unitId, selected?.id] as const,
    queryFn: async () => {
      try {
        return await fetchFeedbackQr(unitId as string, (selected as ManualEvent).id);
      } catch (error) {
        // A `404` is a real answer — this event has no QR yet — and is not the
        // same statement as "the read failed".
        if (error instanceof ApiRequestError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
    enabled: Boolean(principalKey && unitId && selected?.id),
  });

  useEffect(() => {
    if (selected) setForm(formFromManualEvent(selected));
  }, [selected]);

  const invalidateList = async () => {
    await queryClient.invalidateQueries({ queryKey: [principalKey, "unit-events", unitId] });
  };
  const invalidateQr = async () => {
    await queryClient.invalidateQueries({
      queryKey: [principalKey, "feedback-qr", unitId, selected?.id],
    });
  };

  const rememberRecent = (event: ManualEvent) => {
    setRecent((current) => [event, ...current.filter((item) => item.id !== event.id)]);
  };

  const saveMutation = useMutation({
    mutationFn: async () =>
      selected
        ? updateManualEvent(
            unitId as string,
            selected.id,
            selected.version,
            inputFromEventForm(form),
          )
        : createManualEvent(
            unitId as string,
            inputFromEventForm(form) as ManualEventInput,
            createKey.current,
          ),
    // Only after the server said so. Nothing here is optimistic.
    onSuccess: async (event) => {
      setSelected(event);
      rememberRecent(event);
      setNotice(selected ? "Event updated." : "Draft saved.");
      await invalidateList();
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => publishManualEvent(unitId as string, (selected as ManualEvent).id),
    onSuccess: async (event) => {
      setSelected(event);
      rememberRecent(event);
      setNotice("Event published. Event Hosts can now see it.");
      await invalidateList();
    },
  });

  const qrMutation = useMutation({
    mutationFn: (destinationUrl: string) =>
      saveFeedbackQr(unitId as string, (selected as ManualEvent).id, destinationUrl),
    onSuccess: async () => {
      await invalidateQr();
    },
  });

  const refreshSelected = async (eventId: string) => {
    if (unitId === null) return;
    try {
      const event = await fetchManualEvent(unitId, eventId);
      setOpenError("");
      setSelected(event);
      rememberRecent(event);
    } catch (error) {
      setOpenError(error instanceof Error ? error.message : "That event could not be opened.");
    }
  };

  /**
   * Open a row from the merged list.
   *
   * A row backed by this tab's own write already *is* the full record, so it
   * opens with no round trip. A row that came only from the unit's catalog is
   * a summary — it has no version token and no form fields — so the manual
   * record is fetched before the editor is shown, rather than the summary
   * being cast into a shape it does not have.
   */
  const openListing = (listing: EventListing) => {
    setNotice("");
    if (listing.manual) {
      setOpenError("");
      setSelected(listing.manual);
      return;
    }
    void refreshSelected(listing.id);
  };

  const listing = listQuery.data ?? null;
  const listedEvents = listing?.events;
  const listings = useMemo(
    () => mergeEventListings(listedEvents ?? [], recent),
    [listedEvents, recent],
  );
  const draftListings = useMemo(
    () => listings.filter((entry) => entry.status === "draft"),
    [listings],
  );

  const mutationError = saveMutation.error ?? publishMutation.error;

  // The shell renders `PortalGate` when the server granted no such portal, so
  // reaching here without a grant means the mapping is still resolving. Render
  // nothing rather than a header about a portal that may turn out not to be
  // assigned.
  if (grant === null) {
    return null;
  }

  const field = (name: keyof EventFormState, value: string) =>
    setForm((current) => ({ ...current, [name]: value }));

  if (unitId === null) {
    return (
      <div className="space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold text-foreground">Events</h1>
        </header>
        <section
          className="rounded-2xl border border-dashed border-border bg-muted/30 p-6"
          aria-label="No unit assigned"
        >
          <h2 className="font-semibold text-foreground">No unit to list or file events for</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            The server granted this account no default unit, and both the listing and the create
            form are scoped to one. Nothing is shown rather than some other unit&apos;s events,
            and nothing can be filed against a unit this account was not granted.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-foreground">Events</h1>
          <p className="text-sm text-muted-foreground">
            The events your unit hosts. Create them, publish them for Event Hosts, and prepare an
            external feedback QR.
          </p>
          <p className="text-xs text-muted-foreground">
            Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setSelected(null);
            setForm(blankEventForm());
            setNotice("");
            setOpenError("");
            // A fresh idempotency key per draft: the previous one belongs to
            // the event it created, and replaying it would return that event
            // rather than making this one.
            createKey.current = crypto.randomUUID();
          }}
          className="inline-flex min-h-[40px] items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Create event
        </button>
      </header>

      {openError ? (
        <p
          role="alert"
          className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground"
        >
          {openError}
        </p>
      ) : null}

      {/* The month grid needs seven columns of room: in `month` view the
          section spans the page and the editor column drops below it. In
          `list` view the two sit side by side as before. */}
      <div className={eventsView === "month" ? "space-y-6" : "grid gap-6 xl:grid-cols-2"}>
        <section className="rounded-2xl border border-border p-6" aria-label="Hosted events">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              <CalendarDays
                className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <div>
                <h2 className="font-semibold text-foreground">Events your unit hosts</h2>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                  Listed by the server from the events this unit owns, as a list or a month. An
                  event with no resolved date, or with a tag value still awaiting human review, is
                  not listed — and is counted below rather than quietly dropped.
                </p>
              </div>
            </div>
            <div
              role="group"
              aria-label="Choose how to view the hosted events"
              className="flex items-center gap-1 rounded-xl border border-border p-1"
            >
              {(
                [
                  { value: "list", label: "List", Icon: List },
                  { value: "month", label: "Month", Icon: CalendarDays },
                ] as const
              ).map(({ value, label, Icon }) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={eventsView === value}
                  onClick={() => setEventsView(value)}
                  className={`inline-flex min-h-[40px] items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                    eventsView === value
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {listQuery.error ? (
            <p
              role="alert"
              className="mt-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
            >
              {/* Named as a partial view rather than an empty one: anything
                  this tab wrote is still listed below, and reading the short
                  list as "the unit has two events" would be the
                  silent-omission failure ADR-0011 forbids. */}
              {`The unit's event list could not be loaded, so only this session's own events are shown. ${describeFailure(
                listQuery.error,
              )}`}
            </p>
          ) : null}

          {listQuery.isLoading ? (
            <p className="mt-4 text-sm text-muted-foreground" role="status">
              Loading your unit&apos;s events…
            </p>
          ) : listing !== null && listing.events.length === 0 ? (
            // Safe to say here, and only here: the server answered, and its
            // answer was none. The withheld counts below are what say whether
            // "none" means the unit has no events or that none of the events
            // it has could be listed.
            <p className="mt-4 text-sm leading-6 text-muted-foreground">
              The server listed no presentable events for this unit. A draft you save in this
              session still appears in the editor on this page, because a draft with an
              unsettled schedule is not presentable and this route will not carry it.
            </p>
          ) : listing !== null ? (
            eventsView === "month" ? (
              /* The same `listing.events`, drawn on a month grid. Placement is
                 decided by the event's own precision and zone inside
                 `CoordinatorEventsCalendar`; the withheld counts and the
                 `truncated` notice below describe this response and stay on
                 screen in this view on purpose. */
              <CoordinatorEventsCalendar
                events={listing.events}
                selectedId={selected?.id ?? null}
                onOpenEvent={(event) => void refreshSelected(event.id)}
              />
            ) : (
              <div className="mt-4">
                {/* A window over the events this response carried, not a server
                    page: the route takes no page parameter, so the array handed
                    over here is the whole of what arrived. */}
                <PagedList items={listing.events} label="events" idPrefix="unit-hosted-events">
                  {(visibleEvents) => (
                    <ul className="space-y-3">
                      {visibleEvents.map((event) => (
                        <EventRow
                          key={event.id}
                          event={event}
                          selected={selected?.id === event.id}
                          onOpen={() => void refreshSelected(event.id)}
                        />
                      ))}
                    </ul>
                  )}
                </PagedList>
              </div>
            )
          ) : null}

          {listing !== null && (
            <>
              <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-border/70 p-3">
                  <dt className="text-xs text-muted-foreground">Not listed — no resolved date</dt>
                  <dd className="text-sm tabular-nums text-foreground">
                    {listing.withheld_unresolved_date}
                  </dd>
                </div>
                <div className="rounded-xl border border-border/70 p-3">
                  <dt className="text-xs text-muted-foreground">
                    Not listed — tag awaiting review
                  </dt>
                  <dd className="text-sm tabular-nums text-foreground">
                    {listing.withheld_quarantined_tags}
                  </dd>
                </div>
              </dl>

              {listing.truncated && (
                <p className="mt-3 text-xs leading-5 text-muted-foreground">
                  The server stopped sending before the end of this unit&apos;s presentable
                  events, so more exist than were loaded here. That is a different shortfall from
                  the one the pager describes: the pager windows the events that did arrive, and
                  no control on this page can ask the route for the rest.
                </p>
              )}
            </>
          )}

          {draftListings.length > 0 && (
            <div className="mt-4 rounded-xl border border-dashed border-border bg-muted/30 p-4">
              <h3 className="text-sm font-semibold text-foreground">
                Drafts saved in this session
              </h3>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Held by this browser tab only, from its own successful writes, because there is no
                route that lists a unit&apos;s drafts. They are gone on reload; the server still
                has them.
              </p>
              <ul className="mt-2 space-y-2">
                {draftListings.map((entry) => (
                  <li key={entry.id}>
                    <button
                      type="button"
                      onClick={() => openListing(entry)}
                      className={`flex min-h-[40px] w-full flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xl border p-3 text-left transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                        selected?.id === entry.id
                          ? "border-primary bg-primary/5"
                          : "border-border hover:bg-muted/50"
                      }`}
                    >
                      <span className="font-medium text-foreground">{entry.title}</span>
                      <span className="text-sm text-muted-foreground">{entry.when}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <div className="space-y-6">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setNotice("");
              saveMutation.mutate();
            }}
            className="rounded-2xl border border-border p-6"
          >
            <h2 className="font-semibold text-foreground">
              {selected ? "Edit event" : "New event"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Only the title is required for a draft. Complete every field before publishing.
            </p>

            <EventFormFields form={form} onChange={field} categories={categoryOptions} />

            {mutationError ? (
              <p
                role="alert"
                className="mt-4 rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
              >
                {eventErrorMessage(mutationError)}
              </p>
            ) : null}
            {notice ? (
              <p
                role="status"
                aria-live="polite"
                className="mt-4 rounded-xl border border-border bg-muted/50 p-3 text-sm text-foreground"
              >
                {notice}
              </p>
            ) : null}

            <div className="mt-5 flex flex-wrap gap-3">
              {/* Disabled only while the request is in flight, never before it
                  starts, and re-enabled whether it succeeded or failed. */}
              <button
                type="submit"
                disabled={saveMutation.isPending}
                className="inline-flex min-h-[40px] items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors duration-150 motion-reduce:transition-none disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <Save className="h-4 w-4" aria-hidden="true" />
                {saveMutation.isPending ? "Saving…" : "Save draft"}
              </button>
              {selected?.status === "draft" ? (
                <button
                  type="button"
                  disabled={publishMutation.isPending}
                  onClick={() => publishMutation.mutate()}
                  className="min-h-[40px] rounded-xl border border-primary px-4 py-2.5 text-sm font-semibold text-primary transition-colors duration-150 motion-reduce:transition-none disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  {publishMutation.isPending ? "Publishing…" : "Publish event"}
                </button>
              ) : null}
              {selected ? (
                <button
                  type="button"
                  onClick={() => void refreshSelected(selected.id)}
                  className="min-h-[40px] rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  Refresh
                </button>
              ) : null}
            </div>
          </form>

          {selected ? (
            <QRCodeCard
              variant="feedback"
              asset={qrQuery.data ?? null}
              loading={qrMutation.isPending || qrQuery.isLoading}
              error={qrMutation.error instanceof Error ? qrMutation.error.message : null}
              onSave={async (destinationUrl) => {
                await qrMutation.mutateAsync(destinationUrl);
              }}
            />
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground">
              <CalendarDays className="mb-2 h-5 w-5" aria-hidden="true" />
              Save or select an event to configure its feedback QR code.
            </div>
          )}
        </div>
      </div>

      <section className="rounded-2xl border border-border/70 bg-muted/30 p-6" aria-label="Staffing">
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
            are tracked on the contact channels page. That is a record of who was invited and what
            they said, which is a narrower fact than an event&apos;s staffing — the two are linked
            here rather than merged.
          </span>
        </p>
      </section>
    </div>
  );
}
