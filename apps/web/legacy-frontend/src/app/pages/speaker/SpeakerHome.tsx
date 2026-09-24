/**
 * `/speaker-portal` — the Speaker's home (B26 T6b-4 §5.1).
 *
 * Open invitations first, then upcoming engagements: DESIGN.md's "action queue
 * before summary". Two independent reads (`GET /v1/me/invitations`, `GET
 * /v1/me/engagements?when=upcoming`), so one failing leaves the other working.
 * A not-linked, denied or signed-out answer from either replaces both
 * sections with one notice, because it is a fact about the account.
 *
 * No answer buttons here: the Invitations page is the one place an answer is
 * given, with its one confirm flow and one status region.
 */
import { Link } from "react-router";

import type { MyInvitation } from "@/lib/api";
import { formatCalendarDate } from "@/lib/speakerAvailabilityDraft";
import { useMyEngagements, useMyInvitations } from "@/app/hooks/useSpeakerSelf";

import { EngagementRow } from "./EngagementRow";
import { SpeakerReadError, SpeakerSelfNotice, SpeakerStaleReadAlert } from "./SpeakerSelfNotice";
import { selfNoticeKind, speakerPortalError } from "./speakerPortalErrors";
import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

const HEADING = "Home";
const SHOWN = 5;
const LINK_CLASS =
  "inline-flex min-h-11 items-center text-sm font-medium text-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

function waitingSentence(count: number, truncated: boolean): string {
  const noun = count === 1 ? "invitation" : "invitations";
  return truncated
    ? `At least ${count} ${noun} waiting for your answer`
    : `${count} ${noun} waiting for your answer`;
}

function OpenInvitation({ invitation }: { invitation: MyInvitation }) {
  const { event } = invitation;
  return (
    <li className="rounded-xl border border-border/70 bg-card p-4">
      <h3 className="break-words text-base font-semibold text-foreground">{event.title}</h3>
      <p className="text-sm text-muted-foreground">Date in the invitation: {event.date_text}</p>
      {event.local_date !== null ? (
        <p className="text-sm text-foreground">
          Event date: <time dateTime={event.local_date}>{formatCalendarDate(event.local_date)}</time>
        </p>
      ) : null}
    </li>
  );
}

export function SpeakerHome() {
  useSpeakerPageTitle(HEADING);
  const invitations = useMyInvitations();
  const upcoming = useMyEngagements("upcoming");

  const noticeKind =
    (invitations.data === undefined && invitations.isError
      ? selfNoticeKind(invitations.error)
      : null) ??
    (upcoming.data === undefined && upcoming.isError ? selfNoticeKind(upcoming.error) : null);

  let invitationsContent;
  if (invitations.data === undefined) {
    invitationsContent = invitations.isError ? (
      <SpeakerReadError
        message={speakerPortalError("read-invitations", invitations.error).message}
        subject="your invitations"
        onRetry={() => void invitations.refetch()}
      />
    ) : (
      <p className="text-sm text-muted-foreground">Loading invitations…</p>
    );
  } else {
    const open = invitations.data.invitations.filter((invitation) => invitation.answerable);
    invitationsContent =
      open.length === 0 ? (
        <p className="text-sm text-muted-foreground">No invitations are waiting for your answer.</p>
      ) : (
        <div className="space-y-3">
          {invitations.isError ? (
            <SpeakerStaleReadAlert
              message={speakerPortalError("read-invitations", invitations.error).message}
            />
          ) : null}
          <p className="text-sm font-medium text-foreground">
            {waitingSentence(open.length, invitations.data.truncated)}
          </p>
          <ul className="space-y-3">
            {open.slice(0, SHOWN).map((invitation) => (
              <OpenInvitation key={invitation.invitation_id} invitation={invitation} />
            ))}
          </ul>
          <Link to="/speaker-portal/invitations" className={LINK_CLASS}>
            Answer on the Invitations page
          </Link>
        </div>
      );
  }

  let engagementsContent;
  if (upcoming.data === undefined) {
    engagementsContent = upcoming.isError ? (
      <SpeakerReadError
        message={speakerPortalError("read-engagements", upcoming.error).message}
        subject="your engagements"
        onRetry={() => void upcoming.refetch()}
      />
    ) : (
      <p className="text-sm text-muted-foreground">Loading engagements…</p>
    );
  } else if (upcoming.data.engagements.length === 0) {
    engagementsContent = (
      <p className="text-sm text-muted-foreground">
        No upcoming engagements. An engagement appears here once a Speaker Connector confirms you
        for an event.
      </p>
    );
  } else {
    engagementsContent = (
      <div className="space-y-3">
        {upcoming.isError ? (
          <SpeakerStaleReadAlert
            message={speakerPortalError("read-engagements", upcoming.error).message}
          />
        ) : null}
        <ul className="space-y-3">
          {upcoming.data.engagements.slice(0, SHOWN).map((engagement) => (
            <EngagementRow key={engagement.engagement_id} engagement={engagement} />
          ))}
        </ul>
        <Link to="/speaker-portal/engagements" className={LINK_CLASS}>
          See all engagements
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <h1
        tabIndex={-1}
        className="scroll-mt-20 text-2xl font-semibold text-foreground focus:outline-none"
      >
        {HEADING}
      </h1>

      {noticeKind !== null ? (
        <SpeakerSelfNotice kind={noticeKind} />
      ) : (
        <>
          <section
            aria-labelledby="home-invitations-heading"
            aria-busy={invitations.data === undefined && !invitations.isError ? true : undefined}
            className="space-y-3"
          >
            <h2 id="home-invitations-heading" className="text-lg font-semibold text-foreground">
              Invitations waiting for your answer
            </h2>
            {invitationsContent}
          </section>

          <section
            aria-labelledby="home-engagements-heading"
            aria-busy={upcoming.data === undefined && !upcoming.isError ? true : undefined}
            className="space-y-3"
          >
            <h2 id="home-engagements-heading" className="text-lg font-semibold text-foreground">
              Your upcoming engagements
            </h2>
            {engagementsContent}
          </section>
        </>
      )}
    </div>
  );
}
