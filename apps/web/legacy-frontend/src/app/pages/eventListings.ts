/**
 * How the Speaker Connector's Events page decides what to *show*.
 *
 * Two sources describe the same unit's events, and neither is complete on its
 * own:
 *
 * * **The unit's catalog** — `GET /v1/units/{unit_id}/events`
 *   (`fetchUnitEvents`). Authoritative, survives a reload, and is the same
 *   answer every admin gets. It omits an event whose date is unresolved or
 *   whose tags are quarantined (see `routers/events.py`'s `list_events`), so a
 *   brand-new draft is routinely absent from it.
 * * **This tab's own writes** — the `ManualEvent` bodies returned by
 *   `createManualEvent` / `updateManualEvent` / `publishManualEvent`. Fresher
 *   than any catalog page, and the only place a not-yet-presentable draft
 *   exists at all, but session-local: it is empty on the next page load and
 *   empty for every other admin.
 *
 * Showing either alone is a lie in one direction: the catalog alone hides the
 * draft that was just saved, and the local writes alone hide every event that
 * already existed on the server. So they are **merged**, keyed by event id.
 *
 * Two rules govern a collision:
 *
 * 1. **The local write supplies the display fields.** It is the fresher of the
 *    two for title and schedule — it is a server response to an edit the
 *    catalog page may predate.
 * 2. **Publication is the union, not the local snapshot.** An event counts as
 *    published when *either* source says so. Publication is one-way (there is
 *    no unpublish route), so "published" can only ever be a fact the other
 *    source has not caught up with — never a contradiction. This is what the
 *    original `published` predicate was reaching for when it OR-ed in "the id
 *    appears in the unit catalog": it refused to let a stale local `status`
 *    hide a publication the server already knows about. The union preserves
 *    that intent while reading the catalog's actual `publication_status`
 *    instead of treating mere presence in the catalog as proof of publication
 *    — the catalog lists unpublished events too.
 *
 * Only `coordinator_entry` events are taken from the catalog. Every action on
 * this page (edit, publish, feedback QR) is a manual-event route; an event
 * produced by extraction has no manual record to open, so listing it would
 * offer a control that cannot work.
 */
import type { ManualEvent, ManualEventStatus, UnitEventSummary } from "@/lib/api";

/** The minimum an event must carry to be described as happening at a time. */
export interface EventSchedule {
  readonly time_precision: string;
  readonly starts_at: string | null;
  readonly on_date: string | null;
  readonly time_zone: string | null;
}

/**
 * One row of the "Saved events" list.
 *
 * `manual` is the full record when this tab holds one and `null` for a row
 * that exists only in the unit's catalog. The page uses it to decide whether
 * selecting the row can open the editor immediately or has to fetch the
 * manual record first — a catalog summary is not a `ManualEvent` and must not
 * be passed off as one.
 */
export interface EventListing {
  readonly id: string;
  readonly title: string;
  readonly when: string;
  readonly status: ManualEventStatus;
  readonly manual: ManualEvent | null;
}

/** A catalog summary's schedule, in the shape {@link eventWhen} reads. */
export function scheduleOfSummary(summary: UnitEventSummary): EventSchedule {
  return {
    time_precision: summary.time.precision,
    starts_at: summary.time.starts_at,
    on_date: summary.time.on_date,
    time_zone: summary.time.time_zone,
  };
}

/**
 * The event's time, in its own zone, or an explicit "not set".
 *
 * Never falls back to the viewer's zone or to today's date: an event whose
 * schedule the server has not resolved is rendered as unresolved rather than
 * as a time nobody entered.
 */
export function eventWhen(event: EventSchedule): string {
  if (event.time_precision === "date_only" && event.on_date) {
    return `${event.on_date} · All day · ${event.time_zone}`;
  }
  if (event.time_precision === "exact" && event.starts_at) {
    return (
      new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: event.time_zone ?? undefined,
      }).format(new Date(event.starts_at)) + ` · ${event.time_zone}`
    );
  }
  return "Schedule not set";
}

/** The unit catalog's publication verdict, in the manual-event vocabulary. */
function catalogStatus(summary: UnitEventSummary): ManualEventStatus {
  return summary.publication_status === "published" ? "published" : "draft";
}

/**
 * Merge the unit's catalog with this tab's writes into one display list.
 *
 * De-duplicated by id; this tab's writes come first (newest write first, as
 * `recent` is kept), then whatever else the catalog holds in the server's own
 * order. See this module's header for the collision rules.
 */
export function mergeEventListings(
  listed: readonly UnitEventSummary[],
  recent: readonly ManualEvent[],
): EventListing[] {
  const catalog = new Map<string, UnitEventSummary>(
    listed
      .filter((event) => event.provenance.origin === "coordinator_entry")
      .map((event) => [event.id, event]),
  );

  const rows: EventListing[] = [];
  const taken = new Set<string>();

  for (const event of recent) {
    if (taken.has(event.id)) continue;
    taken.add(event.id);
    const listedTwin = catalog.get(event.id);
    rows.push({
      id: event.id,
      title: event.title,
      when: eventWhen(event),
      status:
        event.status === "published" || listedTwin?.publication_status === "published"
          ? "published"
          : "draft",
      manual: event,
    });
  }

  for (const [id, event] of catalog) {
    if (taken.has(id)) continue;
    taken.add(id);
    rows.push({
      id,
      title: event.title,
      when: eventWhen(scheduleOfSummary(event)),
      status: catalogStatus(event),
      manual: null,
    });
  }

  return rows;
}
