/**
 * Meetings — coordinator portal.
 *
 * This page used to render a `PortalDatasetUnavailable` placeholder naming the
 * legacy `/api/portals/event-coordinators/{id}/meetings` dataset, because that
 * backend is not part of this repository and there was no request here that
 * could succeed. Migration `0034` and `smartmatch_api.routers.meetings` are what
 * replaced it: the page now reads `GET /v1/units/{unit_id}/meetings` and writes
 * through `POST` to the same path, and nothing else.
 *
 * ## An internal record, said out loud
 *
 * A meeting recorded here is **the unit's own note.** Nothing in this system
 * tells the other party that it exists — no invitation is composed, queued or
 * sent, and no address is read anywhere on this path. The page says so on
 * screen rather than leaving a coordinator to assume, because the assumption is
 * the dangerous one: somebody who believed this booked a meeting would stop
 * emailing the person they are meeting.
 *
 * G5 (Calendar API) remains deferred, and there is no calendar integration
 * behind this form: no client, no OAuth scope, no credential. There is also no
 * per-meeting `.ics` download — the router's docstring records why, and it is a
 * G5 allowlist decision rather than an oversight.
 *
 * ## A time is asked for, never assumed
 *
 * The form sends `scheduled_at` as an ISO-8601 instant **with an offset**, built
 * by the browser from the local `datetime-local` reading plus the browser's own
 * zone, and it sends that zone alongside as `time_zone`. If the browser cannot
 * name a zone, the page **refuses to submit and says so** rather than picking
 * one — which is the same refusal the server makes, made one layer earlier so
 * the person sees it beside the field.
 *
 * That is ADR-0010 rule 2 and migration finding F-003: the legacy turned an
 * unparsed date into "30 days from now" and rendered a meeting slot nobody had
 * chosen. Nothing on this page supplies a time or a zone the person did not
 * give, and a `422` from the server is rendered as the refusal it is rather than
 * retried with a guess.
 *
 * ## Rendering a time honestly
 *
 * Every row shows the instant in the zone it was *agreed in*, and names that
 * zone. Formatting it in the reader's own zone without saying so is how a 5pm
 * meeting reads as 8pm to somebody travelling — the same instant, silently
 * relabelled. Where the browser cannot format in that zone, the raw stored value
 * is shown instead of a plausible-looking local one.
 *
 * ## Cancelled meetings are shown, not hidden
 *
 * "Called off" and "never arranged" are different facts and the server returns
 * both, so this page renders the distinction rather than filtering it away.
 *
 * ## One page at a time, over the meetings that arrived
 *
 * The list renders through the shared `PagedList`, which windows the array this
 * browser already holds. Two different shortfalls are reported on this screen
 * and neither stands for the other: the pager's range line counts the rows in
 * hand ("of N loaded"), while the server's notice below the list says the
 * server stopped sending — it compares the measured `total` the response
 * carried against how many rows came with it, and appears only when they
 * differ. Nothing here computes either figure. The total is the server's, and
 * the loaded count is the length of the array.
 *
 * A unit with fewer meetings than the pager's own minimum gets its rows back
 * whole with no control chrome; that is `PagedList`'s decision, not re-made
 * here with a length test of this page's own.
 *
 * ## Not authorization
 *
 * Both routes are `admin`/`coordinator`, decided per request against the loaded
 * unit. This page renders its controls and shows the server's `403` as the
 * answer it is, rather than hiding them and implying the capability is absent.
 */

import { useCallback, useEffect, useState } from "react";
import { CalendarClock, Info } from "lucide-react";

import {
  ApiRequestError,
  createMeeting,
  fetchMeetings,
  type Meeting,
  type MeetingList,
} from "../../../lib/api";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/** The server's own bound, asked for explicitly so the page states what it requested. */
const PAGE_LIMIT = 50;

/**
 * The browser's IANA zone, or `null` when it cannot name one.
 *
 * `null` is a real answer and is treated as one: the form refuses to submit
 * rather than defaulting to UTC or to anything else. A guessed zone is a
 * wall-clock reading relabelled, which is exactly the fabrication the server
 * refuses — and a page that guessed it would simply move the defect to where the
 * server cannot see it.
 */
function browserTimeZone(): string | null {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return typeof zone === "string" && zone.length > 0 ? zone : null;
  } catch {
    return null;
  }
}

/**
 * Render one stored instant in the zone it was agreed in, naming that zone.
 *
 * Falls back to the raw ISO value when the browser cannot format in that zone —
 * an unfamiliar zone name is a real possibility, and a silently-local rendering
 * would be a different time presented as the same one.
 */
function formatInAgreedZone(isoInstant: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone,
    }).format(new Date(isoInstant));
  } catch {
    return isoInstant;
  }
}

/** One meeting, with its status and the zone its time is stated in. */
function MeetingRow({ meeting }: { meeting: Meeting }) {
  const cancelled = meeting.status === "cancelled";

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3
          className={
            cancelled
              ? "font-semibold text-muted-foreground line-through"
              : "font-semibold text-foreground"
          }
        >
          {meeting.title}
        </h3>
        {/*
          The status is rendered for every row, including the ordinary one. A
          badge that appeared only on cancellations would leave a reader unsure
          whether an unbadged row was scheduled or merely unlabelled.
        */}
        <span className="text-xs text-muted-foreground">
          {cancelled ? "Cancelled" : "Scheduled"}
        </span>
      </div>

      <p className="mt-2 text-sm text-foreground">
        {formatInAgreedZone(meeting.scheduled_at, meeting.time_zone)}{" "}
        <span className="text-xs text-muted-foreground">({meeting.time_zone})</span>
      </p>

      {/*
        `null` means nobody has said where yet — a real state the server keeps
        distinct from a blank string. It is rendered as a sentence rather than as
        an empty line, so the absence reads as an absence.
      */}
      <p className="mt-1 text-xs text-muted-foreground">
        {meeting.location_or_link === null
          ? "No location or link recorded yet."
          : meeting.location_or_link}
      </p>
    </li>
  );
}

export function CoordinatorMeetings() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit id this page reads.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const [listing, setListing] = useState<MeetingList | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const [title, setTitle] = useState("");
  const [localTime, setLocalTime] = useState("");
  const [locationOrLink, setLocationOrLink] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const timeZone = browserTimeZone();

  const load = useCallback(async () => {
    if (unitId === null) return;
    try {
      setListing(await fetchMeetings(unitId, PAGE_LIMIT));
      setLoadError(null);
    } catch (cause) {
      setLoadError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The meetings could not be loaded and the server gave no reason.",
      );
    } finally {
      setLoaded(true);
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (unitId === null) return;

    // The refusal, made here so the person sees it beside the field. The server
    // makes the same one; neither is a licence for the other to guess.
    if (timeZone === null) {
      setSubmitError(
        "This browser cannot say which time zone you are in, so the meeting time " +
          "cannot be recorded unambiguously. Nothing has been saved, and no zone " +
          "has been assumed on your behalf.",
      );
      return;
    }
    if (localTime === "") {
      setSubmitError("A meeting needs a date and time. Nothing is scheduled without one.");
      return;
    }

    // `datetime-local` yields a wall-clock reading with no offset. `new Date`
    // interprets it in the browser's own zone — the zone reported above and sent
    // alongside — and `toISOString` turns it into the instant the server
    // requires. The pairing is the point: the instant and the zone it was chosen
    // in travel together, and neither is inferred from the other.
    const instant = new Date(localTime);
    if (Number.isNaN(instant.getTime())) {
      setSubmitError("That date and time could not be read. Nothing has been saved.");
      return;
    }

    setSubmitting(true);
    try {
      await createMeeting(unitId, {
        title: title.trim(),
        scheduled_at: instant.toISOString(),
        time_zone: timeZone,
        location_or_link: locationOrLink.trim() === "" ? null : locationOrLink.trim(),
      });
      setTitle("");
      setLocalTime("");
      setLocationOrLink("");
      setSubmitError(null);
      await load();
    } catch (cause) {
      // A 422 naming an unresolved time is rendered as the refusal it is. It is
      // never retried with a substituted time or zone — that substitution is
      // finding F-003, and a client is exactly where it crept in last time.
      setSubmitError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The meeting could not be recorded and the server gave no reason.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is still
  // resolving. Render nothing rather than a header about a portal that may turn
  // out not to be assigned.
  if (grant === null) {
    return null;
  }

  const meetings = listing?.meetings ?? [];
  const total = listing?.total ?? 0;
  const truncated = listing !== null && total > meetings.length;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Meetings</h1>
        <p className="text-sm text-muted-foreground">Meetings booked with the CBA team.</p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <div className="space-y-2 rounded-xl border border-border/70 p-4 text-sm leading-6 text-muted-foreground">
        <p className="flex items-start gap-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            These are <strong>your unit&apos;s own records</strong> of meetings it has arranged.
            Recording one here <strong>does not notify anybody</strong> and does not put anything
            in a calendar: no invitation is sent, and the other party is not told this entry
            exists. Arrange the meeting however you normally would, then note it here.
          </span>
        </p>
      </div>

      {loadError === null ? null : (
        <p
          role="alert"
          className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground"
        >
          {loadError}
        </p>
      )}

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there are no meetings to show.
        </p>
      ) : (
        <>
          <form onSubmit={submit} className="space-y-3 rounded-xl border border-border/70 p-4">
            <h2 className="font-semibold text-foreground">Record a meeting</h2>

            <label className="block space-y-1">
              <span className="text-xs text-muted-foreground">What the meeting is</span>
              <input
                required
                maxLength={200}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="w-full rounded-lg border border-border/70 bg-transparent p-2 text-sm text-foreground"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-xs text-muted-foreground">When</span>
              <input
                required
                type="datetime-local"
                value={localTime}
                onChange={(event) => setLocalTime(event.target.value)}
                className="w-full rounded-lg border border-border/70 bg-transparent p-2 text-sm text-foreground"
              />
              {/*
                The zone is shown rather than silently applied, because it is
                what the stored time will mean. A person in a different zone from
                the meeting needs to see which one was used before they submit.
              */}
              <span className="block text-xs text-muted-foreground">
                {timeZone === null
                  ? "This browser cannot name your time zone, so a meeting cannot be recorded from here."
                  : `Recorded in ${timeZone} — the zone this browser reports.`}
              </span>
            </label>

            <label className="block space-y-1">
              <span className="text-xs text-muted-foreground">
                Where, or how to join (optional)
              </span>
              <input
                maxLength={500}
                value={locationOrLink}
                onChange={(event) => setLocationOrLink(event.target.value)}
                className="w-full rounded-lg border border-border/70 bg-transparent p-2 text-sm text-foreground"
              />
            </label>

            {submitError === null ? null : (
              <p
                role="alert"
                className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-xs text-foreground"
              >
                {submitError}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting || timeZone === null}
              className="min-h-11 inline-flex items-center gap-2 rounded-lg border border-border/70 px-3 py-2 text-sm text-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <CalendarClock className="h-4 w-4" aria-hidden="true" />
              {submitting ? "Recording…" : "Record meeting"}
            </button>
          </form>

          {meetings.length === 0 ? (
            <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
              {!loaded
                ? "Loading…"
                : "This unit has recorded no meetings yet. Nothing is hidden — the list is empty."}
            </p>
          ) : (
            <div className="space-y-2">
              {/* A window over the meetings this response carried. The read is
                  bounded once, above, by `PAGE_LIMIT`; turning a page here asks
                  the server for nothing. */}
              <PagedList items={meetings} label="meetings" idPrefix="unit-meetings">
                {(visibleMeetings) => (
                  <ul className="space-y-3">
                    {visibleMeetings.map((meeting) => (
                      <MeetingRow key={meeting.id} meeting={meeting} />
                    ))}
                  </ul>
                )}
              </PagedList>
              {/*
                The server's measured total against how many rows it sent.
                Stated only when they differ, and never computed: a page that
                inferred "there are probably more" would be claiming a number
                nobody counted. This is not the pager's range line above —
                that one is about how much of what arrived is currently drawn,
                and this one is about rows that never arrived at all.
              */}
              {truncated ? (
                <p className="text-xs text-muted-foreground">
                  The server stopped sending at its limit: this unit has recorded {total} meetings
                  and {meetings.length} of them were loaded here.
                </p>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}
