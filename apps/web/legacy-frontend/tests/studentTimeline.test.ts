/**
 * The student portal's reading of `GET .../student/agenda` and `GET .../rewards`.
 *
 * The regressions these guard are the ones the student portal was rebuilt to
 * end. `StudentHome` and `StudentHistory` rendered nothing but
 * `PortalDatasetUnavailable` panels naming `/api/portals/students/*`, a backend
 * this repository does not contain, while two `/v1` routes held the answers.
 * Repointing them introduces the opposite risk: a page that now *has* data and
 * describes it more confidently than the response allows.
 *
 * Three properties are therefore pinned here rather than left to the render
 * tree. First, the agenda splits without losing or duplicating a row, and a
 * date-only event happening today is not declared over. Second, no row is
 * described as attended unless the union semantics actually establish it — an
 * active registration is ambiguous and must read as one. Third, an `unknown`
 * balance never becomes a number, which is ADR-0011 and the exact defect the
 * deleted `getStudentTotalPoints` had when it rendered an unloaded profile as
 * `0 points`.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  agendaLink,
  agendaLinkText,
  agendaWhen,
  pointsSummary,
  splitAgenda,
} from "../src/app/pages/student/studentTimeline.ts";
import type { RewardBalance, StudentEvent } from "../src/lib/api.ts";

function event(over: Partial<StudentEvent> & { id: string }): StudentEvent {
  return {
    title: "Careers in structural engineering",
    description: null,
    time: {
      precision: "date_only",
      starts_at: null,
      ends_at: null,
      on_date: "2026-03-04",
      time_zone: "America/Los_Angeles",
    },
    is_virtual: false,
    location_city: "Pomona",
    location_postal_code: null,
    tags: [],
    on_my_agenda: true,
    registration: null,
    calendar: { available: false, download_path: null, unavailable_reason: "event_end_unknown" },
    ...over,
  };
}

function balance(over: Partial<RewardBalance>): RewardBalance {
  return { state: "measured", points: 0, ledger_entry_count: 0, ...over };
}

// ---------------------------------------------------------------------------
// agendaWhen
// ---------------------------------------------------------------------------

test("an exact event reports the instant and the event's own zone", () => {
  const when = agendaWhen(
    event({
      id: "e1",
      time: {
        precision: "exact",
        starts_at: "2026-03-04T18:00:00Z",
        ends_at: null,
        on_date: null,
        time_zone: "America/Los_Angeles",
      },
    }),
  );
  assert.equal(when.kind, "instant");
  assert.equal(
    when.kind === "instant" ? when.startsAt.toISOString() : null,
    "2026-03-04T18:00:00.000Z",
  );
  assert.equal(when.kind === "instant" ? when.timeZone : null, "America/Los_Angeles");
});

test("a date-only event reports the calendar date and no invented instant", () => {
  const when = agendaWhen(event({ id: "e1" }));
  assert.deepEqual(when, { kind: "date", onDate: "2026-03-04" });
});

test("an unparseable instant is unknown rather than an Invalid Date", () => {
  const when = agendaWhen(
    event({
      id: "e1",
      time: {
        precision: "exact",
        starts_at: "not-a-timestamp",
        ends_at: null,
        on_date: null,
        time_zone: null,
      },
    }),
  );
  assert.deepEqual(when, { kind: "unknown" });
});

test("an exact precision with no instant is unknown, not silently date-only", () => {
  const when = agendaWhen(
    event({
      id: "e1",
      time: {
        precision: "exact",
        starts_at: null,
        ends_at: null,
        on_date: "2026-03-04",
        time_zone: null,
      },
    }),
  );
  assert.deepEqual(when, { kind: "unknown" });
});

// ---------------------------------------------------------------------------
// splitAgenda
// ---------------------------------------------------------------------------

const NOW = new Date("2026-03-04T12:00:00Z");

test("every event lands in exactly one group", () => {
  const events = [
    event({
      id: "past",
      time: {
        precision: "exact",
        starts_at: "2026-01-10T18:00:00Z",
        ends_at: null,
        on_date: null,
        time_zone: "UTC",
      },
    }),
    event({
      id: "future",
      time: {
        precision: "exact",
        starts_at: "2026-06-10T18:00:00Z",
        ends_at: null,
        on_date: null,
        time_zone: "UTC",
      },
    }),
    event({
      id: "undated",
      time: {
        precision: "unresolved",
        starts_at: null,
        ends_at: null,
        on_date: null,
        time_zone: null,
      },
    }),
  ];
  const groups = splitAgenda(events, NOW);
  assert.deepEqual(
    groups.past.map((entry) => entry.id),
    ["past"],
  );
  assert.deepEqual(
    groups.upcoming.map((entry) => entry.id),
    ["future"],
  );
  assert.deepEqual(
    groups.undated.map((entry) => entry.id),
    ["undated"],
  );
  assert.equal(
    groups.past.length + groups.upcoming.length + groups.undated.length,
    events.length,
    "the split dropped or duplicated a row",
  );
});

test("a date-only event dated today is still to come, never declared over", () => {
  // The row carries no start time, so "it is over" is not knowable at noon.
  const groups = splitAgenda([event({ id: "today" })], NOW);
  assert.deepEqual(
    groups.upcoming.map((entry) => entry.id),
    ["today"],
  );
  assert.equal(groups.past.length, 0);
});

test("past is reversed so the most recent thing a student did reads first", () => {
  // The route returns soonest-first; a history list wants the opposite.
  const events = ["2026-01-01", "2026-02-01", "2026-03-01"].map((onDate) =>
    event({
      id: onDate,
      time: {
        precision: "date_only",
        starts_at: null,
        ends_at: null,
        on_date: onDate,
        time_zone: null,
      },
    }),
  );
  const groups = splitAgenda(events, NOW);
  assert.deepEqual(
    groups.past.map((entry) => entry.id),
    ["2026-03-01", "2026-02-01", "2026-01-01"],
  );
});

test("upcoming keeps the server's soonest-first order untouched", () => {
  const events = ["2026-04-01", "2026-05-01"].map((onDate) =>
    event({
      id: onDate,
      time: {
        precision: "date_only",
        starts_at: null,
        ends_at: null,
        on_date: onDate,
        time_zone: null,
      },
    }),
  );
  assert.deepEqual(
    splitAgenda(events, NOW).upcoming.map((entry) => entry.id),
    ["2026-04-01", "2026-05-01"],
  );
});

// ---------------------------------------------------------------------------
// agendaLink — the union, read honestly
// ---------------------------------------------------------------------------

test("no registration at all can only be attendance", () => {
  // The route UNIONs attendance_record with *active* event_registration. With
  // no registration row, the attendance half is the only way onto the list.
  const row = event({ id: "e1", registration: null });
  assert.equal(agendaLink(row), "attendance_only");
  assert.match(agendaLinkText(row), /recorded you at this event/);
});

test("a cancelled registration can only be attendance", () => {
  // A cancelled row is excluded from the registered half by the server's WHERE.
  const row = event({
    id: "e1",
    registration: {
      status: "cancelled",
      registered_at: "2026-02-01T00:00:00Z",
      updated_at: "2026-02-02T00:00:00Z",
    },
  });
  assert.equal(agendaLink(row), "attendance_only");
  assert.match(agendaLinkText(row), /cancelled your place/);
});

test("an active registration is ambiguous and never claims attendance", () => {
  const row = event({
    id: "e1",
    registration: {
      status: "registered",
      registered_at: "2026-02-01T00:00:00Z",
      updated_at: "2026-02-01T00:00:00Z",
    },
  });
  assert.equal(agendaLink(row), "ambiguous");
  const text = agendaLinkText(row);
  assert.match(text, /hold a place/);
  assert.doesNotMatch(
    text,
    /recorded you at this event/,
    "an active registration does not establish attendance and must not say it did",
  );
});

// ---------------------------------------------------------------------------
// pointsSummary — unknown is never a number
// ---------------------------------------------------------------------------

test("a measured balance keeps its number and its evidence", () => {
  assert.deepEqual(pointsSummary(balance({ points: 125, ledger_entry_count: 5 })), {
    state: "measured",
    points: 125,
    ledgerEntryCount: 5,
  });
});

test("a measured zero stays measured — it is not the same as unknown", () => {
  const summary = pointsSummary(balance({ points: 0, ledger_entry_count: 0 }));
  assert.equal(summary.state, "measured");
  assert.equal(summary.state === "measured" ? summary.points : null, 0);
});

test("an unknown balance yields no number and carries the server's reason", () => {
  const summary = pointsSummary(
    balance({
      state: "unknown",
      points: null,
      ledger_entry_count: 0,
      unknown_reason: "earn policy not ratified",
    }),
  );
  assert.deepEqual(summary, {
    state: "unknown",
    reason: "earn policy not ratified",
    ledgerEntryCount: 0,
  });
});

test("a measured state with a null points value is treated as unknown, not zero", () => {
  // Defence against the exact ADR-0011 defect: the old client rendered an
  // unloaded profile as "0 points".
  const summary = pointsSummary(balance({ state: "measured", points: null }));
  assert.equal(summary.state, "unknown");
});

test("an unknown balance with no stated reason reports null rather than inventing one", () => {
  const summary = pointsSummary(balance({ state: "unknown", points: null }));
  assert.equal(summary.state === "unknown" ? summary.reason : "unreached", null);
});
