/**
 * The Events page's display list.
 *
 * The regression these guard is not hypothetical: `/events` derived both its
 * "Drafts" and "Published" groups from `recent` — this browser tab's own
 * writes — and used the unit catalog only to build an id filter. Every event
 * that already existed on the server was therefore invisible on a reload and
 * invisible to a second admin, while the page rendered "No events yet".
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { eventWhen, mergeEventListings } from "../src/app/pages/eventListings.ts";
import type { ManualEvent, UnitEventSummary } from "../src/lib/api.ts";

function summary(over: Partial<UnitEventSummary> & { id: string }): UnitEventSummary {
  return {
    title: "Catalog event",
    description: null,
    time: {
      precision: "date_only",
      starts_at: null,
      ends_at: null,
      on_date: "2026-10-01",
      time_zone: "America/Los_Angeles",
    },
    tags: [],
    publication_status: "published",
    review_status: "pending",
    provenance: {
      origin: "coordinator_entry",
      source_url: null,
      fetched_at: null,
      extractor_version: null,
    },
    ...over,
  };
}

function manual(over: Partial<ManualEvent> & { id: string }): ManualEvent {
  return {
    unit_id: "unit-1",
    title: "Local event",
    description: null,
    category: null,
    time_precision: "date_only",
    starts_at: null,
    ends_at: null,
    on_date: "2026-11-02",
    time_zone: "America/Los_Angeles",
    location: null,
    capacity: null,
    volunteer_openings: null,
    volunteer_needs: null,
    audience: null,
    contact_name: null,
    contact_email: null,
    speaker_topics: [],
    region: null,
    status: "draft",
    provenance: "observed",
    created_at: "2026-09-10T00:00:00Z",
    updated_at: "2026-09-10T00:00:00Z",
    version: 1,
    ...over,
  };
}

test("the unit's catalog is a display source, not merely a filter", () => {
  // The defect, stated as a test: no local writes at all, and the server's
  // published event must still be listed.
  const rows = mergeEventListings([summary({ id: "srv-1", title: "PR154 Review Smoke Event" })], []);

  assert.equal(rows.length, 1);
  assert.equal(rows[0].title, "PR154 Review Smoke Event");
  assert.equal(rows[0].status, "published");
  // No `ManualEvent` is held for it, so the page must fetch one before editing
  // rather than passing a catalog summary off as a full record.
  assert.equal(rows[0].manual, null);
});

test("a session-local draft the catalog cannot surface is still listed", () => {
  // The reason `recent` exists at all. Dropping it in favour of the catalog
  // would hide a just-saved draft with an unresolved schedule.
  const rows = mergeEventListings([], [manual({ id: "loc-1", title: "Just saved" })]);

  assert.deepEqual(
    rows.map((row) => [row.id, row.status]),
    [["loc-1", "draft"]],
  );
  assert.equal(rows[0].manual?.id, "loc-1");
});

test("an event in both sources appears once, with the local write's fields", () => {
  const rows = mergeEventListings(
    [summary({ id: "both", title: "Stale catalog title", publication_status: "unpublished" })],
    [manual({ id: "both", title: "Edited just now" })],
  );

  assert.equal(rows.length, 1);
  assert.equal(rows[0].title, "Edited just now");
  assert.equal(rows[0].manual?.id, "both");
});

test("publication is the union of the two sources, never the stale half", () => {
  // What the old `|| listedManualIds.has(event.id)` clause was reaching for:
  // a local snapshot saved before a publish must not hide the publication the
  // server already knows about.
  const rows = mergeEventListings(
    [summary({ id: "both", publication_status: "published" })],
    [manual({ id: "both", status: "draft" })],
  );

  assert.equal(rows[0].status, "published");
});

test("a catalog row that is merely present is not treated as published", () => {
  // The old clause read presence in the catalog as proof of publication. The
  // catalog lists unpublished events too, so that put an unpublished event in
  // *both* groups at once. Bucketing is now exclusive.
  const rows = mergeEventListings(
    [summary({ id: "both", publication_status: "unpublished" })],
    [manual({ id: "both", status: "draft" })],
  );

  assert.equal(rows.length, 1);
  assert.equal(rows[0].status, "draft");
  assert.equal(rows.filter((row) => row.status === "published").length, 0);
});

test("extracted events are left out: this page has no manual record to open for them", () => {
  const rows = mergeEventListings(
    [
      summary({
        id: "crawled",
        provenance: {
          origin: "extraction",
          source_url: "https://example.invalid/events",
          fetched_at: "2026-09-01T00:00:00Z",
          extractor_version: "v1",
        },
      }),
      summary({ id: "typed" }),
    ],
    [],
  );

  assert.deepEqual(
    rows.map((row) => row.id),
    ["typed"],
  );
});

test("a schedule is rendered in the event's own zone, or as unresolved", () => {
  assert.equal(
    eventWhen({
      time_precision: "date_only",
      starts_at: null,
      on_date: "2026-10-01",
      time_zone: "America/Los_Angeles",
    }),
    "2026-10-01 · All day · America/Los_Angeles",
  );
  // Never today's date and never the viewer's zone: an unresolved schedule is
  // reported as unresolved.
  assert.equal(
    eventWhen({ time_precision: "exact", starts_at: null, on_date: null, time_zone: null }),
    "Schedule not set",
  );
});
