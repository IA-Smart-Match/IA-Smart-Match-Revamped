/**
 * The current load band for one Speaker (B26 T8d plan §6.3, §7.2, §7.3, §8).
 *
 * Shown on the Connector availability panel (`audience="connector"`, a `div
 * role="group"` under the panel's `h3`) and on the Speaker's own Availability
 * page (`audience="speaker"`, a named `section` under the page's `h1`). It
 * renders only with data: the read's loading and error states are the page's.
 *
 * A band **word**, the sentences around it, and the engagements without an end
 * time, in the server's order, keyed by index (`engagement_id` is null for
 * another unit's engagement). No number: the only digits are dates inside
 * `<time>` elements (OQ-CBA-005). No live region: a save is already announced
 * by the page, and this re-renders from the saved response.
 */
import { Link } from "react-router";

import type { EngagementWithoutEndTime, SpeakerLoad } from "@/lib/api";
import {
  EVENTS_LINK_TEXT,
  EVENTS_PAGE_PATH,
  currentLoadLines,
  gapItemText,
  type LoadAudience,
} from "@/lib/loadBandCopy";
import { formatCalendarDate } from "@/lib/speakerAvailabilityDraft";

function CalendarDate({ iso }: { iso: string }) {
  return <time dateTime={iso}>{formatCalendarDate(iso)}</time>;
}

function GapItem({ item, audience }: { item: EngagementWithoutEndTime; audience: LoadAudience }) {
  const copy = gapItemText(item, audience);
  if (copy.title === null) {
    return <li className="break-words">{copy.note}</li>;
  }
  const link = audience === "connector" && item.editable_here;
  return (
    <li className="break-words">
      <span className="font-medium text-foreground">{copy.title}</span>
      {copy.date !== null ? (
        <>
          {" · "}
          <CalendarDate iso={copy.date} />
        </>
      ) : null}
      {copy.dateNotSet !== null ? ` · ${copy.dateNotSet}` : null}
      {copy.precision !== null ? ` · ${copy.precision}` : null}
      {link ? (
        <span className="block">
          <Link
            to={EVENTS_PAGE_PATH}
            className="font-medium text-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {EVENTS_LINK_TEXT.before}
            <span className="sr-only"> for {copy.title}</span> {EVENTS_LINK_TEXT.after}
          </Link>
        </span>
      ) : null}
      {copy.note !== null ? <span className="block text-muted-foreground">{copy.note}</span> : null}
    </li>
  );
}

export function LoadBandSummary({
  load,
  audience,
  headingLevel,
  idPrefix,
}: {
  load: SpeakerLoad;
  audience: LoadAudience;
  headingLevel: 2 | 4;
  idPrefix: string;
}) {
  const lines = currentLoadLines(load, audience);
  const headingId = `${idPrefix}-load-heading`;
  const Heading = headingLevel === 2 ? "h2" : "h4";
  const content = (
    <>
      <Heading
        id={headingId}
        className={
          headingLevel === 2
            ? "text-lg font-semibold text-foreground"
            : "text-sm font-semibold text-foreground"
        }
      >
        {lines.heading}
      </Heading>
      <p className="text-sm text-foreground">
        <strong className="font-semibold">{lines.word}</strong>
        <span className="text-muted-foreground">
          {" · "}
          {lines.measuredLabel} <CalendarDate iso={load.as_of} />
        </span>
      </p>
      <p className="text-sm text-muted-foreground">{lines.intro}</p>
      <p className="text-sm text-foreground">{lines.matching}</p>
      {lines.capacity !== null ? <p className="text-sm text-foreground">{lines.capacity}</p> : null}
      {lines.listIntro !== null ? (
        <>
          <p className="text-sm text-foreground">{lines.listIntro}</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-foreground">
            {load.engagements_without_end_time.map((item, index) => (
              // The server's order, never re-sorted; ids can be null (other units).
              <GapItem key={index} item={item} audience={audience} />
            ))}
          </ul>
        </>
      ) : null}
      {lines.truncated !== null ? (
        <p className="text-sm text-muted-foreground">{lines.truncated}</p>
      ) : null}
    </>
  );

  if (audience === "speaker") {
    return (
      <section
        aria-labelledby={headingId}
        className="space-y-2 rounded-xl border border-border/70 p-4"
      >
        {content}
      </section>
    );
  }
  return (
    <div role="group" aria-labelledby={headingId} className="space-y-2">
      {content}
    </div>
  );
}
