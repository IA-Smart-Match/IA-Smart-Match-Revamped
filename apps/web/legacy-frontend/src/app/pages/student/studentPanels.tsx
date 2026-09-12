/**
 * The pieces `StudentHome` and `StudentHistory` both render.
 *
 * One event card, one points panel, one named-absence panel, and the date
 * formatting all three share. Kept together so the two pages cannot drift into
 * describing the same server value two different ways — which is the failure
 * mode that produces a portal claiming a dataset is missing on one page while
 * rendering it on another.
 *
 * Every string below is about a field the server sent. There is no branch here
 * that turns an absence into a number, a zero, or a success.
 */
import { Database, Info } from "lucide-react";

import { PortalDatasetUnavailable } from "../../components/PortalContent";
import { agendaLinkText, agendaWhen, type PointsSummary } from "./studentTimeline";
import type { StudentEvent } from "../../../lib/api";

/** Points are counts, so they get the reader's own digit grouping. */
const POINTS = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

/**
 * When this event happens, at the precision the server stated and no finer.
 *
 * A `date_only` event is formatted in UTC deliberately: `on_date` is a calendar
 * date with no instant behind it, and letting the viewer's zone shift it would
 * move an event dated the 4th to the 3rd for a reader far enough west. An
 * `exact` event is rendered in the event's **own** zone, which is the zone it
 * happens in — never the browser's.
 */
export function whenLabel(event: StudentEvent): string {
  const when = agendaWhen(event);
  if (when.kind === "instant") {
    const rendered = when.startsAt.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: when.timeZone ?? "UTC",
    });
    return when.timeZone === null ? rendered : `${rendered} (${when.timeZone})`;
  }
  if (when.kind === "date") {
    const rendered = new Date(`${when.onDate}T00:00:00Z`).toLocaleDateString(undefined, {
      dateStyle: "medium",
      timeZone: "UTC",
    });
    return `${rendered} · time not yet announced`;
  }
  return "Date not yet announced";
}

/** Where it happens, when the server said. Absence is absence, not "TBD". */
function whereLabel(event: StudentEvent): string | null {
  if (event.is_virtual) return "Online";
  return event.location_city;
}

/**
 * One agenda event.
 *
 * The title and the date are the server's. So is the sentence about *why* the
 * event is on this list, which comes from {@link agendaLinkText} and describes
 * the registration row rather than asserting attendance the response does not
 * carry.
 *
 * There is no speaker on this card, and that is the API rather than the
 * layout: `StudentEventSummary` has no speaker field, and both roster reads
 * (`GET .../speaker-contacts`, `GET .../cba/confirmed-speakers`) are
 * `admin`/`coordinator` server-side. `StudentSpeakerFeedback` records the same
 * gap. Naming a speaker here would mean inventing one.
 */
export function AgendaEventCard({ event }: { event: StudentEvent }) {
  const where = whereLabel(event);
  return (
    <li className="rounded-xl border border-border/70 p-4">
      <h3 className="font-semibold text-foreground text-pretty break-words">{event.title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {whenLabel(event)}
        {where === null ? null : ` · ${where}`}
      </p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{agendaLinkText(event)}</p>
      {event.tags.length === 0 ? null : (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Event topics">
          {event.tags.map((tag) => (
            <li
              key={tag}
              className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
            >
              {tag}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * The points balance, and the honest limit of what backs it.
 *
 * Four renders, and they are four different facts: the read was refused (the
 * server's own words), nothing has been read yet, the balance is `unknown` (no
 * number, and the reason if the server gave one), or the balance is measured
 * (the number, plus the ledger entry count that makes a measured zero legible
 * as "nothing credited yet" rather than "we could not tell").
 *
 * The per-entry ledger is not rendered because there is no route that returns
 * it: `GET /v1/units/{unit_id}/rewards` folds `point_ledger_entry` into a
 * single balance and exposes only `ledger_entry_count`. The panel says so
 * rather than leaving a reader to assume the list is empty.
 */
export function PointsPanel({
  summary,
  pointsPerAttendance,
  earnPolicyRatified,
  error,
}: {
  summary: PointsSummary | null;
  pointsPerAttendance: number | null;
  earnPolicyRatified: boolean;
  error: string | null;
}) {
  return (
    <section
      className="rounded-2xl border border-border/70 bg-card p-6"
      aria-labelledby="student-points-heading"
    >
      <h2 id="student-points-heading" className="font-semibold text-foreground">
        Your points
      </h2>

      {error !== null ? (
        <p role="alert" className="mt-2 text-sm leading-6 text-foreground">
          {error}
        </p>
      ) : summary === null ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Your balance has not been read yet.
        </p>
      ) : summary.state === "unknown" ? (
        <div className="mt-2 space-y-1">
          <p className="text-sm leading-6 text-foreground">
            Your balance is not known — this is not a balance of zero.
          </p>
          <p className="text-xs leading-5 text-muted-foreground">
            {summary.reason ??
              "The server folded no ledger it could vouch for and did not say why."}
          </p>
        </div>
      ) : (
        <div className="mt-2 space-y-1">
          <p className="text-3xl font-semibold tabular-nums text-foreground">
            {POINTS.format(summary.points)}
          </p>
          <p className="text-xs leading-5 text-muted-foreground">
            Folded from {POINTS.format(summary.ledgerEntryCount)}{" "}
            {summary.ledgerEntryCount === 1 ? "ledger entry" : "ledger entries"}.
            {summary.ledgerEntryCount === 0
              ? " Nothing has been credited to you yet, which is why this is zero."
              : null}
          </p>
        </div>
      )}

      {pointsPerAttendance === null ? null : (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          Each attendance your department verifies is worth {POINTS.format(pointsPerAttendance)}{" "}
          points.
          {earnPolicyRatified ? null : " That rate is still provisional and may change."}
        </p>
      )}

      <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-muted-foreground">
        <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
        <span>
          The individual entries behind this number are not shown. SmartMatch has no
          student-visible read of{" "}
          <code className="rounded bg-muted px-1 py-0.5" translate="no">
            point_ledger_entry
          </code>{" "}
          — the rewards route returns the folded balance and a count, and nothing that lists what
          each credit was for. Until that read exists, this page can show you the total and how
          many entries produced it, and not which events they came from.
        </span>
      </p>
    </section>
  );
}

/**
 * A dataset this deployment genuinely does not carry, named rather than hidden.
 *
 * `PortalDatasetUnavailable` states the absence; `capability` states what
 * specifically is missing on the server side, so a reader is told which
 * backend capability has to exist before the section can be filled and is not
 * left to read "not available here" as "still loading" or as a fault of their
 * own account.
 */
export function MissingCapability({
  dataset,
  endpoints,
  capability,
}: {
  dataset: string;
  endpoints: string[];
  capability: string;
}) {
  return (
    <div className="space-y-2">
      <PortalDatasetUnavailable dataset={dataset} endpoints={endpoints} />
      <p className="flex items-start gap-2 px-1 text-xs leading-5 text-muted-foreground">
        <Database className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
        <span>{capability}</span>
      </p>
    </div>
  );
}
