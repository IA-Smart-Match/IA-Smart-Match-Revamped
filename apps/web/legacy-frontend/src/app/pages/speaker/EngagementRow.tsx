/**
 * One confirmed engagement (B26 T6b-4 §5.3 E3–E4), on Engagements and Home.
 *
 * Read-only: a Speaker cannot cancel a booking or change an answer here
 * (OQ-CBA-044). The state is an icon plus a word, so colour never carries it
 * alone (WCAG 1.4.1). A cancelled engagement says when, never who.
 */
import { CalendarCheck, CheckCircle2, XCircle } from "lucide-react";

import type { MyEngagement, MyEngagementState } from "@/lib/api";

import { engagementStateLabel, formatEventWhen, formatInstant } from "./speakerPortalFormat";

const STATE_ICON: Record<MyEngagementState, typeof CheckCircle2> = {
  confirmed: CalendarCheck,
  attended: CheckCircle2,
  cancelled: XCircle,
};

const STATE_CLASS: Record<MyEngagementState, string> = {
  confirmed: "border-primary/30 bg-primary/10 text-primary",
  attended: "border-border/70 bg-muted text-foreground",
  cancelled: "border-border/70 bg-muted text-muted-foreground",
};

/** The machine-readable value for the when line's `<time>`. */
function whenDateTime(engagement: MyEngagement): string | undefined {
  const event = engagement.event;
  if (event === null || event.local_date === null) return undefined;
  if (event.time_precision === "exact" && event.starts_at !== null && event.time_zone !== null) {
    return event.starts_at;
  }
  return event.local_date;
}

export function EngagementRow({ engagement }: { engagement: MyEngagement }) {
  const Icon = STATE_ICON[engagement.state];
  const when = formatEventWhen(engagement.event);
  const dateTime = whenDateTime(engagement);

  return (
    <li className="grid gap-2 rounded-xl border border-border/70 bg-card p-4 sm:grid-cols-[1fr_auto] sm:items-start">
      <div className="min-w-0 space-y-1">
        <h3 className="break-words text-base font-semibold text-foreground">
          {engagement.event === null ? "Event details are no longer available." : engagement.event.title}
        </h3>
        {engagement.event !== null ? (
          <p className="text-sm text-foreground">
            {dateTime !== undefined ? <time dateTime={dateTime}>{when}</time> : when}
          </p>
        ) : null}
        {engagement.state === "cancelled" && engagement.cancelled_at !== null ? (
          <p className="text-sm text-muted-foreground">
            Cancelled on{" "}
            <time dateTime={engagement.cancelled_at}>{formatInstant(engagement.cancelled_at)}</time>
          </p>
        ) : null}
      </div>
      <p
        className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium sm:justify-self-end ${STATE_CLASS[engagement.state]}`}
      >
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        {engagementStateLabel(engagement.state)}
      </p>
    </li>
  );
}
