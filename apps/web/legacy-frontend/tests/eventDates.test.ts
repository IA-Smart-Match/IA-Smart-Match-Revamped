/**
 * ADR-0010 date-honesty tests for the legacy calendar surface.
 *
 * The defect these lock down is specific and was live in `Calendar.tsx`: an
 * event whose `event_date` was empty or unparseable was passed through
 * `new Date()` and landed in *today's* cell of the month grid. A viewer
 * could not tell "happening today" from "nobody knows when", which is the
 * shape DESIGN.md §1.8 rules out — an unresolved event "renders as
 * unresolved, not as a guess".
 *
 * Runs under `node --test tests/`.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  calendarDateKey,
  parseCalendarDate,
  partitionByResolvedDate,
} from "../src/lib/eventDates.ts";

test("a well-formed date parses to that calendar day, not a shifted one", () => {
  const parsed = parseCalendarDate("2026-09-14");
  assert.ok(parsed);
  assert.equal(parsed.getFullYear(), 2026);
  assert.equal(parsed.getMonth(), 8); // September, zero-indexed
  assert.equal(parsed.getDate(), 14);
  assert.equal(calendarDateKey(parsed), "2026-09-14");
});

test("an empty or blank date is unresolved, never today", () => {
  // The regression: `new Date()` for "" filed undated rows under today.
  for (const value of ["", "   ", "\t"]) {
    assert.equal(parseCalendarDate(value), null, `"${value}" should not resolve`);
  }
});

test("null and undefined are unresolved", () => {
  assert.equal(parseCalendarDate(null), null);
  assert.equal(parseCalendarDate(undefined), null);
});

test("free text that is not a date is unresolved, never coerced", () => {
  // H21 in the migration plan: crawler rows carried prose like this in the
  // date field. None of it may become a calendar position.
  for (const value of ["See link for details", "TBD", "Fall 2026", "next Thursday", "2026"]) {
    assert.equal(parseCalendarDate(value), null, `"${value}" should not resolve`);
  }
});

test("an impossible calendar date is refused, not rolled forward", () => {
  // `new Date(2026, 1, 30)` silently becomes 2 March. That is a fabricated
  // date, so the parser rejects the input instead.
  assert.equal(parseCalendarDate("2026-02-30"), null);
  assert.equal(parseCalendarDate("2026-13-01"), null);
  assert.equal(parseCalendarDate("2026-00-10"), null);
});

test("unresolved rows are partitioned out of the grid, not placed in it", () => {
  const rows = [
    { id: "a", date: "2026-09-14" },
    { id: "b", date: "" },
    { id: "c", date: "See link for details" },
    { id: "d", date: "2026-09-14" },
  ];

  const { byDateKey, unresolved } = partitionByResolvedDate(rows, (row) => row.date);

  assert.deepEqual(
    unresolved.map((row) => row.id),
    ["b", "c"],
  );
  assert.deepEqual(
    (byDateKey.get("2026-09-14") ?? []).map((row) => row.id),
    ["a", "d"],
  );
  // Nothing landed on today by default.
  const todayKey = calendarDateKey(new Date());
  if (todayKey !== "2026-09-14") {
    assert.equal(byDateKey.get(todayKey), undefined);
  }
});

test("every row is accounted for exactly once", () => {
  const rows = [
    { date: "2026-01-01" },
    { date: "nope" },
    { date: "2026-01-01" },
    { date: "2026-02-02" },
    { date: "" },
  ];
  const { byDateKey, unresolved } = partitionByResolvedDate(rows, (row) => row.date);
  const placed = Array.from(byDateKey.values()).reduce((sum, bucket) => sum + bucket.length, 0);
  assert.equal(placed + unresolved.length, rows.length);
});
