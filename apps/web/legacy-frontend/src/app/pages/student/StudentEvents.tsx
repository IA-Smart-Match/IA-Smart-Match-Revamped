/**
 * Events — student portal (customer §15).
 *
 * Three sections, in this order, and the order is the requirement:
 *
 *   1. **Browse events** — the unit's published catalog.
 *   2. **Your agenda** — the events this student is recorded at.
 *   3. **Month calendar** — last, at the bottom of the page.
 *
 * §15's "Events page requirement" is one sentence: *keep the month calendar at
 * the bottom of the Events page*. It is kept, and it is kept **below** the two
 * lists rather than in place of them. `docs/architecture/engagement-model.md`
 * §5 (D-11) argues a month grid is the wrong primary surface for this — a
 * student wants a time-ordered list of what is next, not a wall of mostly-empty
 * cells — and the customer wants the grid on the page. Both are satisfied by
 * ordering rather than by choosing: the lists answer "what is next", the grid
 * answers "how does the month look", and neither pretends to be the other.
 * `tests/unit/test_student_events_layout_contract.py` pins the order, because a
 * requirement about *placement* is exactly the kind a later refactor reorders
 * without noticing.
 *
 * ## Everything here is a server response
 *
 * `GET /v1/me` says who the caller is, `GET /v1/me/portals` says which unit the
 * server granted them, and the two `/v1/units/{unit_id}/student/*` reads supply
 * every event. No identifier on this page is composed by the browser and no
 * event is invented: there is no fixture list, no mock calendar, and no
 * placeholder row. The month grid is built from the same events the two lists
 * render, so a cell is populated only where the server returned something.
 *
 * ## B07 — "Add to Calendar", finally with something to point at
 *
 * The legacy page carried a `handleAddToCalendar` that set a three-second
 * "Calendar event added" toast and did nothing else. It was removed, the .ics
 * route was shipped, and the remaining blocker was recorded plainly: no
 * student-scoped event read existed, so the page had no `event_id` to link
 * with. That read now exists.
 *
 * The download control is **not** rendered from a rule this page evaluates. The
 * server sends a `calendar` object per event holding either the path or the
 * reason there is none, and this page renders whichever it was given. So a link
 * appears only where the download works — the opposite of B07, whose whole
 * defect was a control that reported success it had not observed.
 *
 * ## B06 — "Register" is a label this page does not use
 *
 * `docs/plans/frontend-broken-buttons.md` B06 records a **Register** button
 * that navigated to this page and created nothing, and its instruction: a real
 * idempotent registration command, "or the label must say 'View events'". There
 * is no registration command, because there is no registration table and this
 * card added no migration — `attendance_record` is attendance, and ADR-0013
 * makes it the only input to points, so a row written when somebody registers
 * would credit them for an event they never attended.
 *
 * So this page has no Register button, no "Save my place", and no client-side
 * set of chosen events. It says **"You are recorded at"** where a mock would
 * have said "registered", because that is what an `attendance_record` means.
 * The gap is OQ-CBA-018, and `tests/integration/test_event_registration.py`
 * fails the day a registration surface appears without it being answered.
 *
 * ## B09 — the grid is real, and still inert
 *
 * The old month grid was `MockStudentCalendar`: fabricated cells, no data, no
 * behaviour. This one is drawn from the events above it and marks the days that
 * have one. Its cells remain non-interactive, and deliberately: the action a
 * cell would offer is registration, which does not exist. A day that opened a
 * dialog with a disabled button would be a worse answer than a day that opens
 * nothing.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, CalendarX2, Download, Info, MapPin, Video } from "lucide-react";

import {
  ApiRequestError,
  fetchStudentAgenda,
  fetchStudentEvents,
  type StudentEvent,
} from "../../../lib/api";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/** The server's refusal codes, in the words a student reads. */
const CALENDAR_REASON_TEXT: Record<string, string> = {
  event_time_unresolved:
    "No start time is recorded for this event yet, so there is nothing to put in a calendar. " +
    "SmartMatch does not guess one.",
  event_end_unknown:
    "No end time is recorded for this event, and a calendar entry needs one. " +
    "SmartMatch does not guess a length.",
  event_not_on_your_agenda: "Calendar files are available for events you are recorded at.",
};

/**
 * The day an event falls on, as `YYYY-MM-DD` in the event's **own** zone.
 *
 * Never the browser's zone. An event at 17:00 in `America/Los_Angeles` is on
 * that day for the people attending it, wherever the reader happens to be, and
 * rendering it a day early for a student on a trip would be the same class of
 * error as inventing the time in the first place. Returns `null` when the event
 * has no date at all, which the caller treats as "not on the grid".
 */
function eventDayKey(event: StudentEvent): string | null {
  const { precision, starts_at: startsAt, on_date: onDate, time_zone: zone } = event.time;
  if (precision !== "exact") return onDate;
  if (startsAt === null) return null;
  try {
    // `en-CA` renders ISO-shaped `YYYY-MM-DD`, which is what the grid keys on.
    return new Date(startsAt).toLocaleDateString("en-CA", { timeZone: zone ?? "UTC" });
  } catch {
    // An unknown zone is the server's to reject, not this page's to substitute a
    // default for. Leaving the event off the grid is the honest fallback; it
    // still appears in both lists above.
    return null;
  }
}

/** When the event happens, in words, at whatever precision is actually known. */
function whenText(event: StudentEvent): string {
  const { precision, starts_at: startsAt, on_date: onDate, time_zone: zone } = event.time;
  if (precision === "exact" && startsAt !== null) {
    const rendered = new Date(startsAt).toLocaleString("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: zone ?? "UTC",
    });
    return zone === null ? rendered : `${rendered} (${zone})`;
  }
  if (onDate !== null) {
    // Rendered as the plain date the server sent. A date-only event has no clock
    // time, and constructing one here — midnight, in some zone — is the
    // fabrication ADR-0010 exists to stop.
    return `${onDate} · time not yet announced`;
  }
  return "Date not yet announced";
}

/** One event, with whatever calendar control the server said it has. */
function EventCard({ event }: { event: StudentEvent }) {
  const reason = event.calendar.unavailable_reason;
  const place = [event.location_city, event.location_postal_code].filter(Boolean).join(" ");
  return (
    <li className="rounded-xl border border-border/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="font-semibold text-foreground">{event.title}</h3>
          <p className="text-sm text-muted-foreground">{whenText(event)}</p>
          <p className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            {event.is_virtual ? (
              <span className="inline-flex items-center gap-1">
                <Video className="h-3 w-3" aria-hidden="true" /> Virtual
              </span>
            ) : place.length === 0 ? null : (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3 w-3" aria-hidden="true" />
                {place}
              </span>
            )}
            {event.on_my_agenda ? <span>You are recorded at this event</span> : null}
          </p>
        </div>

        {/*
          Rendered from `event.calendar`, which the server evaluated. This page
          does not decide whether a download is possible and does not compose the
          URL — both would be a second opinion about a rule that lives in
          `routers/calendar.py`.
        */}
        {event.calendar.available && event.calendar.download_path !== null ? (
          <a
            href={event.calendar.download_path}
            className="inline-flex items-center gap-2 rounded-lg border border-border/70 px-3 py-2 text-sm font-medium text-foreground"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            Download .ics
          </a>
        ) : (
          <p className="max-w-xs text-xs leading-5 text-muted-foreground">
            {reason === null
              ? "No calendar file is available for this event."
              : (CALENDAR_REASON_TEXT[reason] ?? reason)}
          </p>
        )}
      </div>

      {event.description === null ? null : (
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{event.description}</p>
      )}

      {event.tags.length === 0 ? null : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {event.tags.map((tag) => (
            <li key={tag} className="rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
              {tag}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * The month grid, built from the events already on the page.
 *
 * Last on the page by requirement, and last in this file so the two orders
 * agree. It is a *view* of data rendered above it and never a second fetch: a
 * grid that loaded its own events could disagree with the lists, and a student
 * would have no way to tell which was right.
 *
 * The cells are not buttons. See the module docstring on B09.
 */
function MonthCalendar({ events }: { events: StudentEvent[] }) {
  const [focus, setFocus] = useState(() => new Date());

  const byDay = useMemo(() => {
    const map = new Map<string, StudentEvent[]>();
    for (const event of events) {
      const key = eventDayKey(event);
      if (key === null) continue;
      map.set(key, [...(map.get(key) ?? []), event]);
    }
    return map;
  }, [events]);

  const year = focus.getFullYear();
  const month = focus.getMonth();
  const firstWeekday = new Date(year, month, 1).getDay();
  const dayCount = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: dayCount }, (_, index) => index + 1),
  ];

  const dayKey = (day: number) =>
    `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

  return (
    <section
      className="space-y-3 rounded-2xl border border-border/70 p-5"
      aria-label="Month calendar"
    >
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
          <CalendarDays className="h-4 w-4" aria-hidden="true" />
          {focus.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
        </h2>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setFocus(new Date(year, month - 1, 1))}
            className="rounded-lg border border-border/70 px-3 py-1 text-sm"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setFocus(new Date(year, month + 1, 1))}
            className="rounded-lg border border-border/70 px-3 py-1 text-sm"
          >
            Next
          </button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        The same events as the lists above, laid out by date. Days are marked, not clickable — the
        only action a day could offer is signing up, and this deployment has no sign-up.
      </p>

      <div className="grid grid-cols-7 gap-1 text-center text-xs">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
          <div key={label} className="py-1 font-medium text-muted-foreground">
            {label}
          </div>
        ))}
        {cells.map((day, index) =>
          day === null ? (
            <div key={`blank-${index}`} className="min-h-16 rounded-lg" />
          ) : (
            <div
              key={dayKey(day)}
              className="min-h-16 rounded-lg border border-border/50 p-1 text-left"
            >
              <span className="text-xs text-muted-foreground">{day}</span>
              <ul className="mt-0.5 space-y-0.5">
                {(byDay.get(dayKey(day)) ?? []).map((event) => (
                  <li
                    key={event.id}
                    className="truncate rounded bg-muted px-1 py-0.5 text-[11px] text-foreground"
                    title={event.title}
                  >
                    {event.title}
                  </li>
                ))}
              </ul>
            </div>
          ),
        )}
      </div>
    </section>
  );
}

export function StudentEvents() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit id this page reads.
  // Never composed in the browser.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "student");
  const unitId = grant?.default_unit_id ?? null;

  const [published, setPublished] = useState<StudentEvent[]>([]);
  const [withheldUnpublished, setWithheldUnpublished] = useState(0);
  const [agenda, setAgenda] = useState<StudentEvent[]>([]);
  const [withheldUndated, setWithheldUndated] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (unitId === null) return;
    try {
      const [catalog, mine] = await Promise.all([
        fetchStudentEvents(unitId),
        fetchStudentAgenda(unitId),
      ]);
      setPublished(catalog.events);
      setWithheldUnpublished(catalog.withheld_unpublished);
      setAgenda(mine.events);
      setWithheldUndated(mine.withheld_unresolved_date);
      setLoadError(null);
    } catch (cause) {
      // The server's own message. Nothing is rendered from a guess, and the
      // lists are left as they were rather than replaced by an empty state that
      // would read as "there is nothing".
      setLoadError(
        cause instanceof ApiRequestError
          ? cause.message
          : "Your events could not be loaded and the server gave no reason.",
      );
    } finally {
      setLoaded(true);
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * What the month grid draws: the catalog, plus any agenda event the catalog
   * does not carry — an event you attended that has since been unpublished is on
   * your agenda and not in the catalog, and leaving it off the grid would make
   * the grid disagree with the list directly above it.
   */
  const calendarEvents = useMemo(() => {
    const seen = new Set(published.map((event) => event.id));
    return [...published, ...agenda.filter((event) => !seen.has(event.id))];
  }, [published, agenda]);

  // `StudentLayout` already renders `PortalGate` when the server granted no such
  // portal, so reaching here without a grant means the mapping is still
  // resolving. Render nothing rather than a header about a portal that may turn
  // out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Events</h1>
        <p className="text-sm text-muted-foreground">
          What your department has published, and what you are recorded at.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      {loadError === null ? null : (
        <p className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground">
          {loadError}
        </p>
      )}

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there are no events to show.
        </p>
      ) : (
        <>
          {/* 1. Browse. */}
          <section className="space-y-3" aria-label="Browse events">
            <h2 className="text-lg font-semibold text-foreground">Browse events</h2>
            {published.length === 0 ? (
              <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
                {!loaded
                  ? "Loading…"
                  : withheldUnpublished === 0
                    ? "Your department has not published any events."
                    : // ADR-0011: an omission is never rendered as an absence.
                      `Your department has not published any events yet. ${withheldUnpublished} ` +
                      `${withheldUnpublished === 1 ? "event is" : "events are"} recorded but not ` +
                      "yet published, so they are not shown here."}
              </p>
            ) : (
              <>
                <ul className="space-y-3">
                  {published.map((event) => (
                    <EventCard key={event.id} event={event} />
                  ))}
                </ul>
                {withheldUnpublished === 0 ? null : (
                  <p className="flex items-start gap-2 text-xs text-muted-foreground">
                    <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                    {withheldUnpublished} further{" "}
                    {withheldUnpublished === 1 ? "event is" : "events are"} recorded but not yet
                    published, so {withheldUnpublished === 1 ? "it is" : "they are"} not listed.
                  </p>
                )}
              </>
            )}
          </section>

          {/* 2. Agenda. */}
          <section className="space-y-3" aria-label="Your agenda">
            <h2 className="text-lg font-semibold text-foreground">Your agenda</h2>
            {agenda.length === 0 ? (
              <p className="flex items-start gap-2 rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
                <CalendarX2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  You are not recorded at any events in this department yet. This list shows events
                  your department has recorded you at — signing up for one is not something this
                  deployment can do.
                </span>
              </p>
            ) : (
              <>
                <ul className="space-y-3">
                  {agenda.map((event) => (
                    <EventCard key={event.id} event={event} />
                  ))}
                </ul>
                {withheldUndated === 0 ? null : (
                  <p className="flex items-start gap-2 text-xs text-muted-foreground">
                    <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                    {withheldUndated}{" "}
                    {withheldUndated === 1
                      ? "event you are recorded at has"
                      : "events you are recorded at have"}{" "}
                    no date recorded, so {withheldUndated === 1 ? "it is" : "they are"} not listed
                    here.
                  </p>
                )}
              </>
            )}
          </section>

          {/* 3. Month calendar — last on the page, by customer §15. */}
          <MonthCalendar events={calendarEvents} />
        </>
      )}
    </div>
  );
}
