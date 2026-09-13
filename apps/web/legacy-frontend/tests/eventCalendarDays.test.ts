/**
 * Unit tests for `src/lib/eventCalendarDays.ts` — the month view's placement
 * rules.
 *
 * The defect class this pins is the one `eventDates.test.ts` names: a record
 * whose date does not resolve must never land on *today* by accident, and a
 * `date_only` string must never be parsed through `Date` and shifted a day
 * for a reader west of the source. Added to that here: an `exact` instant's
 * day is computed in the *event's* zone, and an instant whose zone the server
 * did not record places nowhere.
 *
 * Runs under `node --test tests/`.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import type { UnitEventSummary, UnitEventTime } from "../src/lib/api.ts";
import {
  dayLabel,
  eventCellTime,
  eventDayKey,
  monthGridWeeks,
  monthKeyOfDay,
  monthLabel,
  partitionEventsByDay,
  shiftDayKey,
  shiftMonthKey,
  unplacedReason,
  weekEndKey,
  weekStartKey,
  zonedDayKey,
} from "../src/lib/eventCalendarDays.ts";

function time(partial: Partial<UnitEventTime>): UnitEventTime {
  return {
    precision: "unresolved",
    starts_at: null,
    ends_at: null,
    on_date: null,
    time_zone: null,
    ...partial,
  };
}

let counter = 0;
function event(title: string, t: UnitEventTime): UnitEventSummary {
  counter += 1;
  return {
    id: `00000000-0000-4000-8000-${String(counter).padStart(12, "0")}`,
    title,
    description: null,
    time: t,
    tags: [],
    publication_status: "draft",
    review_status: "accepted",
    provenance: { origin: "coordinator_entry", source_url: null, fetched_at: null, extractor_version: null },
  };
}

test("a date_only event lands on its own calendar date, verbatim", () => {
  const key = eventDayKey(time({ precision: "date_only", on_date: "2026-09-14" }));
  assert.equal(key, "2026-09-14");
});

test("a date_only event's date is validated, not trusted", () => {
  // `2026-02-30` is not a real calendar date; a `new Date` roll-forward would
  // file it on 2 March. `2026-9-4` is a real date in a non-padded spelling
  // and normalizes to the same key.
  assert.equal(eventDayKey(time({ precision: "date_only", on_date: "2026-02-30" })), null);
  assert.equal(eventDayKey(time({ precision: "date_only", on_date: "2026-9-4" })), "2026-09-04");
});

test("a date_only event with no on_date places nowhere", () => {
  assert.equal(eventDayKey(time({ precision: "date_only" })), null);
});

test("an exact instant's day is computed in the event's zone, not the viewer's", () => {
  // 2026-03-14T02:30:00Z is still 13 March in Los Angeles (PDT, UTC-7) and
  // already 14 March in UTC. The zone the contract carries is the event's.
  const t = { precision: "exact", starts_at: "2026-03-14T02:30:00Z" };
  assert.equal(eventDayKey(time({ ...t, time_zone: "America/Los_Angeles" })), "2026-03-13");
  assert.equal(eventDayKey(time({ ...t, time_zone: "UTC" })), "2026-03-14");
});

test("an exact instant with no recorded zone places nowhere", () => {
  // Which day it falls on is exactly what the absent zone would have said.
  assert.equal(
    eventDayKey(time({ precision: "exact", starts_at: "2026-03-14T02:30:00Z" })),
    null,
  );
  assert.equal(eventDayKey(time({ precision: "exact", time_zone: "UTC" })), null);
});

test("unresolved and unrecognised precisions place nowhere", () => {
  assert.equal(eventDayKey(time({ precision: "unresolved" })), null);
  assert.equal(eventDayKey(time({ precision: "whenever" })), null);
});

test("an unrecognised zone name places nowhere rather than throwing", () => {
  assert.equal(zonedDayKey("2026-03-14T12:00:00Z", "Not/AZone"), null);
  assert.equal(zonedDayKey("not a date", "UTC"), null);
});

test("partition sorts a day all-day first, then by instant", () => {
  const events = [
    event("evening", time({ precision: "exact", starts_at: "2026-09-14T17:00:00-07:00", time_zone: "America/Los_Angeles" })),
    event("all day", time({ precision: "date_only", on_date: "2026-09-14" })),
    event("morning", time({ precision: "exact", starts_at: "2026-09-14T09:00:00-07:00", time_zone: "America/Los_Angeles" })),
    event("no day", time({ precision: "unresolved" })),
  ];

  const { byDay, unplaced } = partitionEventsByDay(events);

  assert.deepEqual(
    (byDay.get("2026-09-14") ?? []).map((entry) => entry.title),
    ["all day", "morning", "evening"],
  );
  assert.deepEqual(unplaced.map((entry) => entry.title), ["no day"]);
  // Every event accounted for exactly once.
  const placed = Array.from(byDay.values()).reduce((sum, bucket) => sum + bucket.length, 0);
  assert.equal(placed + unplaced.length, events.length);
});

test("September 2026's grid is five Sunday-first weeks", () => {
  // 1 September 2026 is a Tuesday; the month has 30 days.
  const weeks = monthGridWeeks("2026-09");
  assert.equal(weeks.length, 5);
  assert.deepEqual(weeks[0], [
    null,
    null,
    "2026-09-01",
    "2026-09-02",
    "2026-09-03",
    "2026-09-04",
    "2026-09-05",
  ]);
  const last = weeks[4];
  assert.equal(last[3], "2026-09-30");
  assert.deepEqual(last.slice(4), [null, null, null]);
  // No day appears twice and every day of the month appears once.
  const days = weeks.flat().filter((key): key is string => key !== null);
  assert.equal(days.length, 30);
  assert.equal(new Set(days).size, 30);
});

test("month helpers label and navigate honestly", () => {
  assert.equal(monthLabel("2026-09"), "September 2026");
  assert.equal(dayLabel("2026-09-14"), "Monday, September 14, 2026");
  assert.equal(monthKeyOfDay("2026-09-14"), "2026-09");
});

test("day and week shifts cross boundaries without rolling oddly", () => {
  assert.equal(shiftDayKey("2026-09-01", -1), "2026-08-31");
  assert.equal(shiftDayKey("2026-12-31", 1), "2027-01-01");
  // 2026-09-14 is a Monday; its week runs Sunday 13th to Saturday 19th.
  assert.equal(weekStartKey("2026-09-14"), "2026-09-13");
  assert.equal(weekEndKey("2026-09-14"), "2026-09-19");
});

test("month shift clamps the day rather than rolling into the next month", () => {
  // 31 January + 1 month must not become 3 March.
  assert.equal(shiftMonthKey("2026-01-31", 1), "2026-02-28");
  assert.equal(shiftMonthKey("2026-03-31", -1), "2026-02-28");
  assert.equal(shiftMonthKey("2026-09-14", 1), "2026-10-14");
});

test("cell time says All day for date_only and the zoned time for exact", () => {
  assert.equal(
    eventCellTime(event("d", time({ precision: "date_only", on_date: "2026-09-14" }))),
    "All day",
  );
  const label = eventCellTime(
    event("t", time({ precision: "exact", starts_at: "2026-09-14T17:00:00-07:00", time_zone: "America/Los_Angeles" })),
  );
  // 17:00 with a -07:00 offset is 5 PM on that date in Los Angeles itself.
  assert.equal(label, "5:00 PM");
  assert.equal(
    eventCellTime(event("u", time({ precision: "unresolved" }))),
    null,
  );
});

test("unplaced reasons name the defect rather than a guess", () => {
  assert.match(
    unplacedReason(time({ precision: "unresolved" })),
    /server reported the time as .unresolved./,
  );
  assert.match(
    unplacedReason(time({ precision: "exact", starts_at: "2026-09-14T17:00:00Z" })),
    /no recorded time zone/,
  );
  assert.match(
    unplacedReason(time({ precision: "date_only", on_date: "2026-02-30" })),
    /not a real calendar date/,
  );
});
