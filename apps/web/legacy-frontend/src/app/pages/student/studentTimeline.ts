/**
 * The student portal's shared reading of two server responses.
 *
 * `GET /v1/units/{unit_id}/student/agenda` and
 * `GET /v1/units/{unit_id}/rewards` are read by more than one page —
 * `StudentHome` wants what is next, `StudentHistory` wants what has happened —
 * and the interesting part of both is the same: what the response does *not*
 * say. This module is where that is decided once, in pure functions a test can
 * hold, rather than twice inside two render trees.
 *
 * Nothing here fetches, and nothing here invents. Every function takes a server
 * value and returns a narrower server value or an explicit "cannot tell".
 *
 * `app/pages/eventListings.ts` holds the coordinator equivalent. It is not
 * reused: it reads `EventSchedule` off the unit catalog, which carries review
 * status and extraction provenance a student surface never receives, and its
 * `eventWhen` returns a formatted string rather than the structured answer the
 * grouping below needs.
 *
 * ## Why "attended" is not a word this module uses
 *
 * The agenda route returns the **union** of two tables: `attendance_record`
 * rows naming the caller, and *active* `event_registration` rows naming them
 * (`routers/student_events.py::list_student_agenda`). The response carries the
 * registration and nothing about the attendance, so "you attended this" is not
 * a fact the browser is holding for most rows and must not be printed as one.
 *
 * Two rows are the exception, and they are deductions from the union rather
 * than guesses about it:
 *
 * - `registration === null` — there has never been a registration row, so the
 *   only remaining way onto the union is an attendance record.
 * - `registration.status === "cancelled"` — a cancelled registration is
 *   excluded from the registered half of the union by the server's own
 *   `WHERE`, so again the attendance half is what put the row here.
 *
 * An event with an active registration is genuinely ambiguous: the student may
 * or may not have turned up, and only a coordinator's attendance entry would
 * say. {@link agendaLink} returns `"ambiguous"` there and the pages print the
 * registration rather than a claim about attendance.
 *
 * ## Why time is a three-way answer
 *
 * `time.precision` is `exact` or `date_only` on a student surface, never
 * `unresolved` — the route excludes unresolved rows and counts them in
 * `withheld_unresolved_date` instead. `date_only` has no instant, so an event
 * dated today is neither over nor still to come at any particular hour, and
 * saying either would be a made-up time. It is reported as such.
 */
import type { RewardBalance, StudentEvent } from "../../../lib/api";

/** `event_registration.status` — the server's two values, mirrored. */
const REGISTERED = "registered";

/** `time.precision` values a student surface can actually receive. */
const EXACT = "exact";
const DATE_ONLY = "date_only";

/**
 * When an event happens, at the precision the server actually stated.
 *
 * `unknown` is not defensive padding: an event can reach a student list with a
 * precision this code does not know, and the honest render for that is the
 * absence rather than a guessed instant.
 */
export type AgendaWhen =
  | { kind: "instant"; startsAt: Date; timeZone: string | null }
  | { kind: "date"; onDate: string }
  | { kind: "unknown" };

/** Read `event.time` without deciding anything it does not say. */
export function agendaWhen(event: StudentEvent): AgendaWhen {
  const { precision, starts_at: startsAt, on_date: onDate, time_zone: timeZone } = event.time;
  if (precision === EXACT && startsAt !== null) {
    const parsed = new Date(startsAt);
    // An instant the browser could not parse is not an instant. Carrying it
    // forward would print the string "Invalid Date" to a student; reporting it
    // as unknown says the true thing.
    if (!Number.isNaN(parsed.getTime())) {
      return { kind: "instant", startsAt: parsed, timeZone };
    }
    return { kind: "unknown" };
  }
  if (precision === DATE_ONLY && onDate !== null) {
    return { kind: "date", onDate };
  }
  return { kind: "unknown" };
}

/** The `YYYY-MM-DD` the given instant falls on, in the viewer's own zone. */
function localDate(at: Date): string {
  const year = at.getFullYear();
  const month = `${at.getMonth() + 1}`.padStart(2, "0");
  const day = `${at.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** The agenda in the three groups a reader actually asks about. */
export interface AgendaGroups {
  past: StudentEvent[];
  upcoming: StudentEvent[];
  undated: StudentEvent[];
}

/**
 * Split the agenda, losing nothing.
 *
 * Server order is preserved inside `upcoming` (the route sorts soonest first,
 * which is the order a "what is next" list wants) and reversed inside `past`,
 * so the most recent thing a student did is the first thing they read. Every
 * input event lands in exactly one group.
 *
 * A `date_only` event dated **today** is `upcoming`, not `past`. There is no
 * start time on the row, so "it is over" is not knowable at 9am, and the
 * cheaper of the two mistakes is to leave it on the list of things to come.
 */
export function splitAgenda(events: readonly StudentEvent[], now: Date): AgendaGroups {
  const past: StudentEvent[] = [];
  const upcoming: StudentEvent[] = [];
  const undated: StudentEvent[] = [];
  const today = localDate(now);

  for (const event of events) {
    const when = agendaWhen(event);
    if (when.kind === "instant") {
      (when.startsAt.getTime() < now.getTime() ? past : upcoming).push(event);
    } else if (when.kind === "date") {
      (when.onDate < today ? past : upcoming).push(event);
    } else {
      undated.push(event);
    }
  }

  past.reverse();
  return { past, upcoming, undated };
}

/**
 * Which of the agenda's two halves put this event on the list.
 *
 * See the module docstring: two of the three answers are deductions from the
 * server's `UNION`, and the third says plainly that the response does not
 * distinguish them.
 */
export type AgendaLink = "attendance_only" | "ambiguous";

export function agendaLink(event: StudentEvent): AgendaLink {
  const registration = event.registration;
  if (registration === null || registration.status !== REGISTERED) {
    return "attendance_only";
  }
  return "ambiguous";
}

/**
 * One sentence about why this event is on this student's list.
 *
 * Every branch describes a row the server sent. None of them says "you
 * attended" for a row where the response does not establish it.
 */
export function agendaLinkText(event: StudentEvent): string {
  const registration = event.registration;
  if (registration === null) {
    return "Your department recorded you at this event. You never registered for it here.";
  }
  if (registration.status !== REGISTERED) {
    return (
      "You cancelled your place, and your department still recorded you at this event — " +
      "a cancelled registration does not keep an event on this list on its own."
    );
  }
  return (
    "You hold a place at this event. Whether your attendance was recorded is not part of " +
    "this answer."
  );
}

/**
 * The points balance, as one of the two things it can be.
 *
 * `unknown` is never folded into a number. `ledgerEntryCount` is carried
 * through both branches because it is the evidence that separates a measured
 * zero — nothing credited yet — from a balance that could not be read, which is
 * the distinction ADR-0011 exists for.
 */
export type PointsSummary =
  | { state: "measured"; points: number; ledgerEntryCount: number }
  | { state: "unknown"; reason: string | null; ledgerEntryCount: number };

export function pointsSummary(balance: RewardBalance): PointsSummary {
  if (balance.state === "measured" && balance.points !== null) {
    return {
      state: "measured",
      points: balance.points,
      ledgerEntryCount: balance.ledger_entry_count,
    };
  }
  return {
    state: "unknown",
    reason: balance.unknown_reason ?? null,
    ledgerEntryCount: balance.ledger_entry_count,
  };
}
