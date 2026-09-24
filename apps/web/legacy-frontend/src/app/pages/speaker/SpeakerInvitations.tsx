/**
 * `/speaker-portal/invitations` — the one place a Speaker answers an
 * invitation (B26 T6b-4 §5.2).
 *
 * Reads `GET /v1/me/invitations`; writes `POST /v1/me/invitations/{id}/response`.
 * "Waiting for your answer" is the action list and is never paged; "Answered"
 * pages through the shared `PagedList`.
 *
 * ## After an answer
 *
 * The list is re-read (never spliced) before anything else happens, and every
 * answer button stays blocked until it lands: the pressed Confirm button keeps
 * focus with `aria-disabled`, the rest are `disabled`. Then the outcome is
 * announced in the page's one `role="status"` region and focus moves to the
 * row's heading under "Answered" — `revealIndex` turns that list to the page
 * holding it first. A failure is said in the row's own `role="alert"`, with
 * focus left on the Confirm button; if the re-read moved the row to Answered,
 * focus follows it there, and if the row is gone, the message stays at page
 * level with focus on the page heading.
 */
import { useEffect, useState } from "react";

import type { MyInvitation, MyInvitationAnswerResult } from "@/lib/api";
import { PagedList } from "@/app/components/PagedList";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import { useAnswerMyInvitation, useMyInvitations } from "@/app/hooks/useSpeakerSelf";

import { InvitationRow, invitationHeadingId, type InvitationResponse } from "./InvitationRow";
import { SpeakerReadError, SpeakerSelfNotice, SpeakerStaleReadAlert } from "./SpeakerSelfNotice";
import { selfNoticeKind, speakerPortalError } from "./speakerPortalErrors";
import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

const HEADING = "Invitations";
const HEADING_ID = "invitations-heading";

function answerStatus(response: InvitationResponse, result: MyInvitationAnswerResult): string {
  const title = result.invitation.event.title;
  if (!result.recorded) return `Your answer to ${title} was already recorded. Nothing changed.`;
  return response === "accept" ? `You accepted ${title}.` : `You declined ${title}.`;
}

interface RowError {
  readonly invitationId: string;
  readonly message: string;
}

export function SpeakerInvitations() {
  useSpeakerPageTitle(HEADING);
  const principalKey = usePrincipalKey();
  const query = useMyInvitations();
  const answer = useAnswerMyInvitation();

  const [confirming, setConfirming] = useState<{
    invitationId: string;
    response: InvitationResponse;
  } | null>(null);
  const [status, setStatus] = useState("");
  const [rowError, setRowError] = useState<RowError | null>(null);
  // The answered row to turn to and focus once the re-read has drawn it.
  const [revealId, setRevealId] = useState<string | null>(null);
  const [focusHeading, setFocusHeading] = useState(false);

  const rows: readonly MyInvitation[] | undefined = query.data?.invitations;
  const waiting = rows?.filter((invitation) => invitation.answerable) ?? [];
  const answered = rows?.filter((invitation) => !invitation.answerable) ?? [];
  const revealAt =
    revealId === null ? -1 : answered.findIndex((row) => row.invitation_id === revealId);
  const orphanError =
    rowError !== null &&
    rows !== undefined &&
    !rows.some((row) => row.invitation_id === rowError.invitationId)
      ? rowError.message
      : null;

  // Focus the revealed row once PagedList has drawn its page; a row the
  // re-read no longer lists hands focus to the page heading instead.
  useEffect(() => {
    if (revealId === null || rows === undefined) return;
    if (!rows.some((row) => row.invitation_id === revealId)) {
      setRevealId(null);
      setFocusHeading(true);
      return;
    }
    const heading = document.getElementById(invitationHeadingId(revealId));
    if (heading !== null) {
      heading.focus();
      setRevealId(null);
    }
  });

  useEffect(() => {
    if (!focusHeading) return;
    document.getElementById(HEADING_ID)?.focus();
    setFocusHeading(false);
  }, [focusHeading]);

  // A failure the re-read has already overtaken: the row moved to Answered
  // (follow it) or vanished (say so at page level, focus the page heading).
  useEffect(() => {
    if (rowError === null || rows === undefined) return;
    const row = rows.find((candidate) => candidate.invitation_id === rowError.invitationId);
    if (row === undefined) {
      setFocusHeading(true);
    } else if (!row.answerable) {
      setConfirming(null);
      setRevealId(row.invitation_id);
    }
    // Keyed on the failure alone: it is set after the re-read has landed, so
    // the rows read here are already the fresh ones.
  }, [rowError]);

  const pending = answer.isPending ? answer.variables : undefined;
  const blocked = answer.isPending || principalKey === null;

  function submit(invitationId: string, response: InvitationResponse): void {
    if (blocked) return;
    setStatus("");
    setRowError(null);
    answer.mutate(
      { invitationId, response },
      {
        onSuccess: (result) => {
          setConfirming(null);
          setStatus(answerStatus(response, result));
          setRevealId(invitationId);
        },
        onError: (cause) => {
          setRowError({ invitationId, message: speakerPortalError("answer", cause).message });
        },
      },
    );
  }

  function renderRow(invitation: MyInvitation) {
    const id = invitation.invitation_id;
    return (
      <InvitationRow
        key={id}
        invitation={invitation}
        confirming={confirming?.invitationId === id ? confirming.response : null}
        pressed={pending?.invitationId === id ? pending.response : null}
        blocked={blocked}
        error={rowError?.invitationId === id ? rowError.message : null}
        onAsk={(response) => {
          setRowError(null);
          setConfirming({ invitationId: id, response });
        }}
        onConfirm={(response) => submit(id, response)}
        onGoBack={() => setConfirming(null)}
      />
    );
  }

  let content;
  if (query.data === undefined) {
    if (query.isError) {
      const kind = selfNoticeKind(query.error);
      content =
        kind !== null ? (
          <SpeakerSelfNotice kind={kind} />
        ) : (
          <SpeakerReadError
            message={speakerPortalError("read-invitations", query.error).message}
            subject="your invitations"
            onRetry={() => void query.refetch()}
          />
        );
    } else {
      content = <p className="text-sm text-muted-foreground">Loading invitations…</p>;
    }
  } else if (query.data.invitations.length === 0) {
    content = (
      <p className="text-sm text-muted-foreground">
        No invitations yet. When a Speaker Connector invites you to an event, it appears here.
      </p>
    );
  } else {
    content = (
      <>
        {query.isError ? (
          <SpeakerStaleReadAlert
            message={speakerPortalError("read-invitations", query.error).message}
          />
        ) : null}
        <section aria-labelledby="invitations-waiting-heading" className="space-y-3">
          <h2 id="invitations-waiting-heading" className="text-lg font-semibold text-foreground">
            Waiting for your answer
          </h2>
          {waiting.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No invitations are waiting for your answer.
            </p>
          ) : (
            <ul className="space-y-3">{waiting.map(renderRow)}</ul>
          )}
        </section>
        <section aria-labelledby="invitations-answered-heading" className="space-y-3">
          <h2 id="invitations-answered-heading" className="text-lg font-semibold text-foreground">
            Answered
          </h2>
          {answered.length === 0 ? (
            <p className="text-sm text-muted-foreground">No answered invitations yet.</p>
          ) : (
            <PagedList
              items={answered}
              label="answered invitations"
              idPrefix="answered-invitations"
              revealIndex={revealAt >= 0 ? revealAt : null}
            >
              {(visibleAnswered) => <ul className="space-y-3">{visibleAnswered.map(renderRow)}</ul>}
            </PagedList>
          )}
        </section>
        {query.data.truncated ? (
          <p className="text-xs text-muted-foreground">Showing your 200 most recent invitations.</p>
        ) : null}
      </>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1
        id={HEADING_ID}
        tabIndex={-1}
        className="scroll-mt-20 text-2xl font-semibold text-foreground focus:outline-none"
      >
        {HEADING}
      </h1>

      <p role="status" aria-live="polite" className={status ? "text-sm text-foreground" : "sr-only"}>
        {status}
      </p>

      {orphanError !== null ? <SpeakerStaleReadAlert message={orphanError} /> : null}

      <div
        className="space-y-8"
        aria-busy={query.data === undefined && !query.isError ? true : undefined}
      >
        {content}
      </div>
    </div>
  );
}
