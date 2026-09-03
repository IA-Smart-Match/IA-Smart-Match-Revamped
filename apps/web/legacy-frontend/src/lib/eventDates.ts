/**
 * Honest calendar-date handling for the legacy events surface.
 *
 * ADR-0010 and `apps/web/DESIGN.md` §1.8: an event carries an instant, an
 * IANA zone, and a precision, and "an event at `unresolved` cannot be
 * matched or published, so it should not reach a list at all; if one does,
 * it renders as unresolved, not as a guess."
 *
 * The legacy `/api/calendar/*` rows carry a bare `event_date` string with no
 * zone and no precision, so the strongest honest statement this module can
 * make is the negative one: it refuses to invent a date for a record that
 * does not have one. That refusal is the whole point — the previous parser
 * returned `new Date()` for an empty string, which quietly filed every
 * undated record under *today* and made "we don't know when" render
 * identically to "it is happening now".
 *
 * Pure module, no React and no `@/` alias imports, so `node --test` can
 * exercise it directly.
 */

/**
 * Parses a `YYYY-MM-DD` calendar date, or returns `null` when the value does
 * not resolve to one.
 *
 * Read as parts rather than through `new Date(iso)` on purpose:
 * `new Date("2026-09-14")` is specified to parse as *UTC* midnight, so for
 * any viewer west of Greenwich it renders as 13 September. That one-day
 * slide is the same class of defect as the "events at 3 AM" finding ADR-0010
 * records (Fix #6).
 */
export function parseCalendarDate(iso: string | null | undefined): Date | null {
  if (typeof iso !== "string" || !iso.trim()) {
    return null;
  }
  const parts = iso.trim().split("-");
  if (parts.length !== 3) {
    return null;
  }
  const [year, month, day] = parts.map(Number);
  if (![year, month, day].every((part) => Number.isInteger(part))) {
    return null;
  }
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return null;
  }
  const parsed = new Date(year, month - 1, day);
  // Rejects overflow dates such as 2026-02-30, which the Date constructor
  // would silently roll forward into March rather than refuse.
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    return null;
  }
  return parsed;
}

/** Stable `YYYY-MM-DD` key for a parsed local date. */
export function calendarDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

/**
 * Splits rows into those a day cell can honestly claim and those it cannot.
 *
 * A record in `unresolved` never reaches the grid; callers list it by name
 * instead. Keeping the split here rather than in the page means the grid
 * cannot accidentally regain a "just put it somewhere" fallback.
 */
export function partitionByResolvedDate<T>(
  rows: readonly T[],
  dateOf: (row: T) => string,
): { byDateKey: Map<string, T[]>; unresolved: T[] } {
  const byDateKey = new Map<string, T[]>();
  const unresolved: T[] = [];

  for (const row of rows) {
    const parsed = parseCalendarDate(dateOf(row));
    if (!parsed) {
      unresolved.push(row);
      continue;
    }
    const key = calendarDateKey(parsed);
    const bucket = byDateKey.get(key) ?? [];
    bucket.push(row);
    byDateKey.set(key, bucket);
  }

  return { byDateKey, unresolved };
}

/**
 * The IANA zone this surface is drawing in.
 *
 * DESIGN.md §1.8 requires a named zone beside every time. The retired feed
 * supplies no per-event zone, so naming the viewer's own is the honest
 * disclosure of the frame actually in use until unit-scoped event records
 * (S3-S5) carry `event_time` with its zone.
 */
export function viewerTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "your local time zone";
  } catch {
    return "your local time zone";
  }
}
