/**
 * Source scan for the events page's month view — the successor to the
 * retired `/calendar` page, which redirects to `/coordinator-portal/events`.
 *
 * What this pins, and why at the source level: the grid is a *view* of the
 * `GET /v1/units/{unit_id}/events` response the page already holds — no new
 * endpoint, no `from`/`to` window the route does not accept, no coverage or
 * assignment overlay the response does not carry. Placement is decided by
 * `lib/eventCalendarDays.ts` (unit-tested in `eventCalendarDays.test.ts`);
 * these assertions check that the wiring exists and that the dishonest
 * shortcuts stay out.
 *
 * `routes.tsx` gains no route: the month view is a view state on the events
 * page, so the RouteMap accounting and the redirect table are unchanged —
 * `legacyRedirects.test.ts` and `test_frontend_manual_events_contract.py`
 * continue to pin both.
 */
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../src/app/pages/coordinator/CoordinatorEvents.tsx");
const calendar = read("../src/app/pages/coordinator/CoordinatorEventsCalendar.tsx");
const days = read("../src/lib/eventCalendarDays.ts");
const api = read("../src/lib/api.ts");
const routes = read("../src/app/routes.tsx");
const shell = read("../src/app/components/CoordinatorPortalLayout.tsx");

test("the events page offers a List/Month toggle and mounts the grid", () => {
  assert.match(page, /import \{ CoordinatorEventsCalendar \}/);
  assert.match(page, /<CoordinatorEventsCalendar/);
  // The two view choices, with their pressed state announced.
  assert.match(page, /value: "list"/);
  assert.match(page, /value: "month"/);
  assert.match(page, /aria-pressed/);
  // The grid reads the same array the list draws — not a second fetch.
  assert.match(page, /events=\{listing\.events\}/);
});

test("the month view is a real grid and keyboard-operable", () => {
  for (const role of ['role="grid"', 'role="row"', 'role="columnheader"', 'role="gridcell"']) {
    assert.ok(calendar.includes(role), `calendar is missing ${role}`);
  }
  // Roving tab stop plus the arrow/Home/End/PageUp/PageDown moves.
  assert.match(calendar, /tabIndex=\{tabbable \? 0 : -1\}/);
  for (const key of ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]) {
    assert.ok(calendar.includes(key), `calendar does not handle ${key}`);
  }
  // Month paging and a return to the current month.
  assert.match(calendar, /aria-label="Previous month"/);
  assert.match(calendar, /aria-label="Next month"/);
  assert.match(calendar, /This month/);
});

test("events that resolve to no day are named, not placed", () => {
  assert.match(calendar, /partitionEventsByDay/);
  assert.match(calendar, /unplacedReason/);
  assert.match(calendar, /Not placed on a day/);
  assert.match(days, /eventDayKey/);
  // An instant is zoned by the event's own IANA zone, never silently the
  // viewer's: a null `time_zone` yields no day.
  assert.match(days, /timeZone: event\.time\.time_zone/);
  assert.doesNotMatch(days, /timeZone: event\.time\.time_zone \?\? undefined/);
});

test("the month view invents no endpoint and no overlay data", () => {
  for (const source of [page, calendar, days]) {
    assert.doesNotMatch(source, /\bfetch\(/, "pages do not fetch directly");
    assert.doesNotMatch(source, /\/api\/calendar/, "the retired calendar feeds stay retired");
  }
  // The route takes no date window; none may be sent.
  assert.doesNotMatch(api, /\/events\?from=/);
  assert.doesNotMatch(api, /\/events\?to=/);
  // None of the retired feed's overlay field names: that domain does not
  // exist in /v1. (Field names, not the words — prose explaining that the
  // overlay is absent is the honest part.)
  assert.doesNotMatch(calendar, /coverage_status|coverage_label|assignment_count|volunteer_fatigue|recovery_status/);
});

test("selecting a day opens events through the page's own edit path", () => {
  // The day detail uses the same refreshSelected path a list row's edit
  // button does — one way to open an event, not a calendar-only copy.
  assert.match(page, /onOpenEvent=\{\(event\) => void refreshSelected\(event\.id\)\}/);
  assert.match(calendar, /Edit this event/);
});

test("the route table and nav are unchanged by the view", () => {
  // No `/coordinator-portal/calendar` route was added — the retired
  // `/calendar` redirect still lands on the events page, which now carries
  // the month view itself.
  assert.doesNotMatch(routes, /path: "calendar"/);
  assert.match(shell, /name: "Events", href: "\/coordinator-portal\/events"/);
});
