/**
 * `/speaker-portal/engagements` — the Speaker's confirmed engagements, Upcoming
 * or Past (B26 T6b-4 §5.3).
 *
 * The period is the URL's `?when=`, as two links, so Back works and each
 * period has its own address; any value but `past` reads as `upcoming`, the
 * server's default. Each period is its own cached read. The list pages through
 * the shared `PagedList`, keyed on the period so a switch starts at page 1.
 * Read-only: no row has a button (OQ-CBA-044).
 */
import { Link, useSearchParams } from "react-router";

import type { EngagementWhen } from "@/lib/api";
import { PagedList } from "@/app/components/PagedList";
import { useMyEngagements } from "@/app/hooks/useSpeakerSelf";

import { EngagementRow } from "./EngagementRow";
import { SpeakerReadError, SpeakerSelfNotice, SpeakerStaleReadAlert } from "./SpeakerSelfNotice";
import { selfNoticeKind, speakerPortalError } from "./speakerPortalErrors";
import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

const HEADING = "Engagements";

const PERIODS: readonly { when: EngagementWhen; label: string }[] = [
  { when: "upcoming", label: "Upcoming" },
  { when: "past", label: "Past" },
];

const EMPTY: Record<EngagementWhen, string> = {
  upcoming: "No upcoming engagements.",
  past: "No past engagements yet.",
};

export function SpeakerEngagements() {
  useSpeakerPageTitle(HEADING);
  const [searchParams] = useSearchParams();
  const when: EngagementWhen = searchParams.get("when") === "past" ? "past" : "upcoming";
  const query = useMyEngagements(when);

  let content;
  if (query.data === undefined) {
    if (query.isError) {
      const kind = selfNoticeKind(query.error);
      content =
        kind !== null ? (
          <SpeakerSelfNotice kind={kind} />
        ) : (
          <SpeakerReadError
            message={speakerPortalError("read-engagements", query.error).message}
            subject="your engagements"
            onRetry={() => void query.refetch()}
          />
        );
    } else {
      content = <p className="text-sm text-muted-foreground">Loading engagements…</p>;
    }
  } else if (query.data.engagements.length === 0) {
    content = <p className="text-sm text-muted-foreground">{EMPTY[when]}</p>;
  } else {
    const engagements = query.data.engagements;
    content = (
      <div className="space-y-3">
        {query.isError ? (
          <SpeakerStaleReadAlert
            message={speakerPortalError("read-engagements", query.error).message}
          />
        ) : null}
        <PagedList
          key={when}
          items={engagements}
          label="engagements"
          idPrefix={`engagements-${when}`}
        >
          {(visibleEngagements) => (
            <ol className="space-y-3">
              {visibleEngagements.map((engagement) => (
                <EngagementRow key={engagement.engagement_id} engagement={engagement} />
              ))}
            </ol>
          )}
        </PagedList>
        {query.data.truncated ? (
          <p className="text-xs text-muted-foreground">Showing the first 200.</p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1
        tabIndex={-1}
        className="scroll-mt-20 text-2xl font-semibold text-foreground focus:outline-none"
      >
        {HEADING}
      </h1>

      <nav aria-label="Engagement period">
        <ul className="flex flex-wrap gap-2">
          {PERIODS.map((period) => {
            const current = period.when === when;
            return (
              <li key={period.when}>
                <Link
                  to={`/speaker-portal/engagements?when=${period.when}`}
                  aria-current={current ? "page" : undefined}
                  className={`inline-flex min-h-11 items-center rounded-lg border px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                    current
                      ? "border-primary/30 bg-primary/10 text-primary"
                      : "border-border/70 text-foreground hover:bg-muted"
                  }`}
                >
                  {period.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <section
        aria-labelledby="engagements-list-heading"
        aria-busy={query.data === undefined && !query.isError ? true : undefined}
        className="space-y-3"
      >
        <h2 id="engagements-list-heading" className="text-lg font-semibold text-foreground">
          {when === "past" ? "Past engagements" : "Upcoming engagements"}
        </h2>
        {content}
      </section>
    </div>
  );
}
