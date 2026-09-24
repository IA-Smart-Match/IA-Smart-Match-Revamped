/**
 * One invitation (B26 T6b-4 §5.2 I2–I7, §8.3).
 *
 * Shows what the invitation said: its title, its date text verbatim, the
 * event's own date once one is linked, and when it was sent ("Sent", never
 * "delivered": a queued send is not proof of delivery). An answered row says
 * who recorded the answer, never an id.
 *
 * An open row has Accept and Decline. Both are final, so both confirm inline
 * (not a modal; owner ruling OQ-1): opening the confirm row moves focus to
 * the Confirm button; Go back closes it and hands focus back to the button
 * that opened it. While the answer is saving, the pressed Confirm button keeps
 * focus with `aria-disabled` and reads "Saving…"; the page disables the rest.
 */
import { useEffect, useRef, type Ref } from "react";
import { AlertCircle } from "lucide-react";

import type { MyInvitation } from "@/lib/api";
import { formatCalendarDate } from "@/lib/speakerAvailabilityDraft";

import { answerSentence, domId, formatInstant } from "./speakerPortalFormat";

export type InvitationResponse = "accept" | "decline";

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
const BUTTON_QUIET = `inline-flex min-h-11 items-center rounded-lg border border-border/70 bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50 aria-disabled:opacity-70 ${FOCUS_RING}`;
const BUTTON_PRIMARY = `inline-flex min-h-11 items-center rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50 aria-disabled:opacity-70 ${FOCUS_RING}`;

export function invitationHeadingId(invitationId: string): string {
  return `${domId("invitation", invitationId)}-heading`;
}

const VERB: Record<InvitationResponse, { label: string; confirm: string; saving: string }> = {
  accept: { label: "Accept", confirm: "Confirm accept", saving: "accepting" },
  decline: { label: "Decline", confirm: "Confirm decline", saving: "declining" },
};

export interface InvitationRowProps {
  readonly invitation: MyInvitation;
  /** The answer whose confirm row is open, if any. */
  readonly confirming: InvitationResponse | null;
  /** The answer this row is saving, when the page's one request is this row's. */
  readonly pressed: InvitationResponse | null;
  /** Some request is in flight on the page, or nothing may be sent yet. */
  readonly blocked: boolean;
  readonly error: string | null;
  readonly onAsk: (response: InvitationResponse) => void;
  readonly onConfirm: (response: InvitationResponse) => void;
  readonly onGoBack: () => void;
}

function AnswerButton({
  visible,
  suffix,
  savingSuffix,
  pressed,
  blocked,
  describedBy,
  className,
  buttonRef,
  onClick,
}: {
  visible: string;
  suffix: string;
  savingSuffix: string;
  pressed: boolean;
  blocked: boolean;
  describedBy: string | undefined;
  className: string;
  buttonRef?: Ref<HTMLButtonElement>;
  onClick: () => void;
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      className={className}
      disabled={!pressed && blocked}
      aria-disabled={pressed ? "true" : undefined}
      aria-describedby={describedBy}
      onClick={() => {
        if (pressed) return;
        onClick();
      }}
    >
      {pressed ? "Saving…" : visible}
      <span className="sr-only">{pressed ? savingSuffix : suffix}</span>
    </button>
  );
}

export function InvitationRow({
  invitation,
  confirming,
  pressed,
  blocked,
  error,
  onAsk,
  onConfirm,
  onGoBack,
}: InvitationRowProps) {
  const { event, response } = invitation;
  const title = event.title;
  const headingId = invitationHeadingId(invitation.invitation_id);
  const errorId = `${domId("invitation", invitation.invitation_id)}-error`;
  const describedBy = error !== null ? errorId : undefined;

  const confirmRef = useRef<HTMLButtonElement>(null);
  const acceptRef = useRef<HTMLButtonElement>(null);
  const declineRef = useRef<HTMLButtonElement>(null);
  // Which button to hand focus back to; set only by Go back.
  const returnTo = useRef<InvitationResponse | null>(null);
  const openConfirm = invitation.answerable ? confirming : null;

  useEffect(() => {
    if (openConfirm !== null) {
      confirmRef.current?.focus();
    } else if (returnTo.current !== null) {
      (returnTo.current === "accept" ? acceptRef : declineRef).current?.focus();
      returnTo.current = null;
    }
  }, [openConfirm]);

  let actions = null;
  if (invitation.answerable) {
    actions =
      openConfirm !== null ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-foreground">
            {VERB[openConfirm].label} this invitation? Your first answer is final. To change it
            later, contact your Speaker Connector.
          </p>
          <div className="flex flex-wrap gap-2">
            <AnswerButton
              buttonRef={confirmRef}
              visible={VERB[openConfirm].confirm}
              suffix={` invitation to ${title}`}
              savingSuffix={`, ${VERB[openConfirm].saving} invitation to ${title}`}
              pressed={pressed === openConfirm}
              blocked={blocked}
              describedBy={describedBy}
              className={BUTTON_PRIMARY}
              onClick={() => onConfirm(openConfirm)}
            />
            <AnswerButton
              visible="Go back"
              suffix={`, keep invitation to ${title} unanswered`}
              savingSuffix={`, keep invitation to ${title} unanswered`}
              pressed={false}
              blocked={blocked}
              describedBy={undefined}
              className={BUTTON_QUIET}
              onClick={() => {
                returnTo.current = openConfirm;
                onGoBack();
              }}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <AnswerButton
            buttonRef={acceptRef}
            visible="Accept"
            suffix={` invitation to ${title}`}
            savingSuffix={` invitation to ${title}`}
            pressed={false}
            blocked={blocked}
            describedBy={describedBy}
            className={BUTTON_PRIMARY}
            onClick={() => onAsk("accept")}
          />
          <AnswerButton
            buttonRef={declineRef}
            visible="Decline"
            suffix={` invitation to ${title}`}
            savingSuffix={` invitation to ${title}`}
            pressed={false}
            blocked={blocked}
            describedBy={describedBy}
            className={BUTTON_QUIET}
            onClick={() => onAsk("decline")}
          />
        </div>
      );
  }

  return (
    <li className="grid gap-3 rounded-xl border border-border/70 bg-card p-4 sm:grid-cols-[1fr_auto] sm:items-start">
      <div className="min-w-0 space-y-1">
        <h3
          id={headingId}
          tabIndex={-1}
          className="scroll-mt-20 break-words text-base font-semibold text-foreground focus:outline-none"
        >
          {title}
        </h3>
        <p className="text-sm text-muted-foreground">Date in the invitation: {event.date_text}</p>
        {event.local_date !== null ? (
          <p className="text-sm text-foreground">
            Event date:{" "}
            <time dateTime={event.local_date}>{formatCalendarDate(event.local_date)}</time>
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Sent <time dateTime={invitation.dispatched_at}>{formatInstant(invitation.dispatched_at)}</time>
        </p>
        {response !== null && !invitation.answerable ? (
          <p className="text-sm font-medium text-foreground">
            {answerSentence(invitation)} on{" "}
            <time dateTime={response.recorded_at}>{formatInstant(response.recorded_at)}</time>
          </p>
        ) : null}
      </div>
      {actions !== null ? <div className="sm:justify-self-end">{actions}</div> : null}
      {error !== null ? (
        <p
          id={errorId}
          role="alert"
          className="flex items-start gap-1.5 text-sm text-destructive sm:col-span-2"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
    </li>
  );
}
