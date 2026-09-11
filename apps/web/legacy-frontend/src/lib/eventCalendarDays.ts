/**
 * Placing `GET /v1/units/{unit_id}/events` rows onto a month grid — honestly.
 *
 * The connector events page offers a month view of the same listing the list
 * view draws. This module is the whole of "which day does this event belong
 * on", kept pure (no React, no `@/` alias imports) so `node --test` can
 * exercise it the way `tests/eventDates.test.ts` exercises `eventDates.ts`.
 *
 * ## The rule that matters (ADR-0010)
 *
 * A day cell is a claim: "this event's calendar day is this date". The
 * response carries three precisions and each resolves to a day differently:
 *
 *  - `date_only` carries `on_date`, already a calendar date in the event's
 *    own context. It is used verbatim — validated, never passed through
 *    `Date` arithmetic, so a 14 March event cannot slide to 13 March for a
 *    reader west of the source.
 *  - `exact` carries `starts_at`, an instant. Which calendar day an instant
 *    falls on depends on the zone, and the zone the contract carries is the
 *    *event's* (`time_zone` is "never the viewer's and never the server's").
 *    The day is therefore computed in that zone via `Intl.DateTimeFormat`
 *    parts — the same technique `EventsSections.dateTimeLocal` uses for the
 *    inverse direction.
 *  - `unresolved`, or a row whose fields do not match its precision (an
 *    `exact` with no `starts_at`, a `date_only` with an `on_date` that is not
 *    a real calendar date, an `exact` instant whose `time_zone` the server
 *    never recorded), resolves to **no day**. The listing route already
 *    excludes `unresolved` rows and counts them in `withheld_unresolved_date`;
 *    anything else that still cannot be placed is surfaced outside the grid
 *    rather than guessed onto one — the defect `eventDates.ts` was written to
 *    remove was exactly that guess.
 *
 * The grid itself is zone-free: a cell labelled "September 14" claims the
 * event's *local* calendar date is September 14, computed in the event's own
 * zone before any key is compared. Day-of-week and month structure come from
 * the viewer's locale calendar (`new Date(y, m, d)`), which is the honest
 * frame for "which days exist in September" — calendar dates do not move
 * between zones, only instants do.
 *
 * ## What this module is not
 *
 * Not a paging layer. The route ignores date filters and hard-caps at 200
 * rows; "next month" here re-buckets the response already held, it does not
 * ask the server for a window it does not accept. Not a coverage view: the
 * response carries no assignment or roster data, and none is derived.
 */

import { calendarDateKey, parseCalendarDate } from "./eventDates.ts";
import type { UnitEventSummary, UnitEventTime } from "./api.ts";

/** `YYYY-MM-DD` — the key every day cell and every placed event shares. */
export type DayKey = string;

/** `YYYY-MM` — the key identifying the month a grid is showing. */
export type MonthKey = string;

/**
 * The calendar day `instant` falls on in `timeZone`, or `null` when either
 * cannot be applied (a date-time string `Date` cannot read, or a zone name
 * `Intl` rejects).
 *
 * `formatToParts` rather than `format()`: the parts' values follow the
 * options (`month: "2-digit"` is `09` whatever the locale's field order),
 * so reassembling them cannot produce `9/14/2026` or a locale-swapped
 * day/month pair.
 */
export function zonedDayKey(instant: string, timeZone: string): DayKey | null {
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(date);
    const value = (type: string) => parts.find((part) => part.type === type)?.value;
    const year = value("year");
    const month = value("month");
    const day = value("day");
    if (year === undefined || month === undefined || day === undefined) {
      return null;
    }
    return `${year}-${month}-${day}`;
  } catch {
    // An unrecognised IANA zone throws RangeError. That is a data defect the
    // caller lists beside the grid — not something to silently re-zone.
    return null;
  }
}

/**
 * The day an event can honestly be placed on, or `null` when it cannot.
 *
 * See this module's header for the three cases. `null` is a real answer —
 * the caller renders it as "not placed", never as a guess at a day.
 */
export function eventDayKey(time: UnitEventTime): DayKey | null {
  if (time.precision === "date_only") {
    if (time.on_date === null) {
      return null;
    }
    // `on_date` is already a calendar date. It is validated through the same
    // parser the retired surface used (so `2026-02-30` cannot become a cell)
    // and re-keyed rather than trusted verbatim, so `2026-9-4` and
    // `2026-09-04` name the same day.
    const parsed = parseCalendarDate(time.on_date);
    return parsed === null ? null : calendarDateKey(parsed);
  }
  if (time.precision === "exact") {
    if (time.starts_at === null || time.time_zone === null) {
      // An instant without its event zone has no honest calendar day: which
      // date it falls on is exactly what the zone would have said.
      return null;
    }
    return zonedDayKey(time.starts_at, time.time_zone);
  }
  // `unresolved`, or a precision this build does not recognise: no day.
  return null;
}

/**
 * Why an event got no day, in the server's own terms.
 *
 * Rendered beside each unplaced event under the grid. Never a raw field
 * dump and never a euphemism — the point of listing these is that a reader
 * can tell "nobody knows when it is" from "September 14".
 */
export function unplacedReason(time: UnitEventTime): string {
  if (time.precision === "date_only") {
    return time.on_date === null
      ? "the server reported it as all-day but carried no date"
      : `its date “${time.on_date}” is not a real calendar date`;
  }
  if (time.precision === "exact") {
    if (time.starts_at === null) {
      return "the server reported an exact time but carried no start instant";
    }
    if (time.time_zone === null) {
      return "its start instant has no recorded time zone, so its calendar day is unknown";
    }
    return `its time zone “${time.time_zone}” could not be applied`;
  }
  return `the server reported the time as “${time.precision}”`;
}

/** All-day events first, then timed ones by instant, then title. */
function compareEventsInDay(left: UnitEventSummary, right: UnitEventSummary): number {
  const leftAllDay = left.time.precision === "date_only";
  const rightAllDay = right.time.precision === "date_only";
  if (leftAllDay !== rightAllDay) {
    return leftAllDay ? -1 : 1;
  }
  const leftAt = left.time.starts_at === null ? Number.NaN : Date.parse(left.time.starts_at);
  const rightAt = right.time.starts_at === null ? Number.NaN : Date.parse(right.time.starts_at);
  if (!Number.isNaN(leftAt) && !Number.isNaN(rightAt) && leftAt !== rightAt) {
    return leftAt - rightAt;
  }
  return left.title.localeCompare(right.title);
}

/**
 * Buckets events by the day they honestly fall on.
 *
 * `unplaced` keeps the server's own order; each day's bucket is sorted
 * all-day-first then by start instant, which is the order a reader scans a
 * day in. Every input event appears exactly once across the two outputs.
 */
export function partitionEventsByDay(events: readonly UnitEventSummary[]): {
  byDay: Map<DayKey, UnitEventSummary[]>;
  unplaced: UnitEventSummary[];
} {
  const byDay = new Map<DayKey, UnitEventSummary[]>();
  const unplaced: UnitEventSummary[] = [];
  for (const event of events) {
    const key = eventDayKey(event.time);
    if (key === null) {
      unplaced.push(event);
      continue;
    }
    const bucket = byDay.get(key) ?? [];
    bucket.push(event);
    byDay.set(key, bucket);
  }
  for (const bucket of byDay.values()) {
    bucket.sort(compareEventsInDay);
  }
  return { byDay, unplaced };
}

/** The viewer-local calendar date as a day key — "today" included. */
export function todayDayKey(now: Date = new Date()): DayKey {
  return calendarDateKey(now);
}

/** The `YYYY-MM` a day key belongs to. */
export function monthKeyOfDay(dayKey: DayKey): MonthKey {
  return dayKey.slice(0, 7);
}

/** The `YYYY-MM` the given date falls in, in the viewer's calendar. */
export function monthKeyOfDate(date: Date): MonthKey {
  return calendarDateKey(date).slice(0, 7);
}

/** "September 2026" — fixed `en-US` so tests and every reader see the same words. */
export function monthLabel(monthKey: MonthKey): string {
  const [year, month] = monthKey.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(
    new Date(year, month - 1, 1),
  );
}

/** "Monday, September 14, 2026" — a day cell's spoken name. */
export function dayLabel(dayKey: DayKey): string {
  const parsed = parseCalendarDate(dayKey);
  if (parsed === null) {
    return dayKey;
  }
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

/** The day key `days` after `dayKey`, across month and year boundaries. */
export function shiftDayKey(dayKey: DayKey, days: number): DayKey {
  const parsed = parseCalendarDate(dayKey);
  if (parsed === null) {
    return dayKey;
  }
  parsed.setDate(parsed.getDate() + days);
  return calendarDateKey(parsed);
}

/**
 * The same day-of-month `months` later, clamped to the target month's
 * length: 31 January + 1 month is 28 (or 29) February, never 3 March —
 * `Date` would roll the overflow forward and land a month later than asked.
 */
export function shiftMonthKey(dayKey: DayKey, months: number): DayKey {
  const parsed = parseCalendarDate(dayKey);
  if (parsed === null) {
    return dayKey;
  }
  const target = new Date(parsed.getFullYear(), parsed.getMonth() + months, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(parsed.getDate(), lastDay));
  return calendarDateKey(target);
}

/** The Sunday starting `dayKey`'s week — the grid's first column. */
export function weekStartKey(dayKey: DayKey): DayKey {
  const parsed = parseCalendarDate(dayKey);
  if (parsed === null) {
    return dayKey;
  }
  parsed.setDate(parsed.getDate() - parsed.getDay());
  return calendarDateKey(parsed);
}

/** The Saturday ending `dayKey`'s week — the grid's last column. */
export function weekEndKey(dayKey: DayKey): DayKey {
  const parsed = parseCalendarDate(dayKey);
  if (parsed === null) {
    return dayKey;
  }
  parsed.setDate(parsed.getDate() + (6 - parsed.getDay()));
  return calendarDateKey(parsed);
}

/**
 * The weeks of a month, Sunday-first, as day keys with `null` for the
 * leading and trailing cells that belong to neighbouring months.
 *
 * `null` rather than the neighbour's own date: the grid draws one month, and
 * a cell that showed part of the next one would place events on days this
 * view never claimed.
 */
export function monthGridWeeks(monthKey: MonthKey): (DayKey | null)[][] {
  const [year, month] = monthKey.split("-").map(Number);
  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
    return [];
  }
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();

  const cells: (DayKey | null)[] = [];
  for (let index = 0; index < firstWeekday; index += 1) {
    cells.push(null);
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(calendarDateKey(new Date(year, month - 1, day)));
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }

  const weeks: (DayKey | null)[][] = [];
  for (let index = 0; index < cells.length; index += 7) {
    weeks.push(cells.slice(index, index + 7));
  }
  return weeks;
}

/**
 * The chip text a day cell shows under an event's name.
 *
 * `date_only` is "All day" — it has no clock time and inventing one is the
 * fabrication ADR-0010 forbids. `exact` renders the start in the event's own
 * zone (the zone label itself appears in the day-detail list, not on every
 * chip). Anything else is `null` and draws no time, matching the honesty of
 * the unplaced list the event would be in.
 */
export function eventCellTime(event: UnitEventSummary): string | null {
  if (event.time.precision === "date_only") {
    return "All day";
  }
  if (
    event.time.precision === "exact" &&
    event.time.starts_at !== null &&
    event.time.time_zone !== null
  ) {
    const date = new Date(event.time.starts_at);
    if (Number.isNaN(date.getTime())) {
      return null;
    }
    try {
      return new Intl.DateTimeFormat("en-US", {
        hour: "numeric",
        minute: "2-digit",
        timeZone: event.time.time_zone,
      }).format(date);
    } catch {
      return null;
    }
  }
  return null;
}
