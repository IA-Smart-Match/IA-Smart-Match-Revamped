/**
 * One of the Speaker's addresses (B26 T6b-4 §5.5 C3–C7, §8.3).
 *
 * Shows the one button the server allows (`can_opt_in` / `can_opt_out`), or
 * neither with the reason in text: a hidden button rather than a disabled one,
 * because a natively disabled button cannot take focus and its reason would
 * be unreachable by keyboard.
 *
 * Opting out confirms inline (not a modal); opting in does not (owner ruling
 * OQ-5). Opening the confirm row moves focus to Confirm opt out; Keep
 * receiving closes it and hands focus back to Opt out.
 *
 * While this row's request is pending, the pressed button keeps focus with
 * `aria-disabled="true"` and reads "Saving…"; every other button on the page
 * is natively `disabled` (the page decides which is which, §4.2 G2).
 */
import { useEffect, useRef, type ReactNode, type Ref } from "react";
import { AlertCircle, BellOff, CheckCircle2, CircleDashed } from "lucide-react";

import type { MyContactChannel } from "@/lib/api";
import type { ChannelChoice } from "@/app/hooks/useSpeakerSelf";

import { channelStatusSentence, domId, lastSetByLabel } from "./speakerPortalFormat";

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
const BUTTON_QUIET = `inline-flex min-h-11 items-center rounded-lg border border-border/70 bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50 aria-disabled:opacity-70 ${FOCUS_RING}`;
const BUTTON_PRIMARY = `inline-flex min-h-11 items-center rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50 aria-disabled:opacity-70 ${FOCUS_RING}`;
const BUTTON_DESTRUCTIVE = `inline-flex min-h-11 items-center rounded-lg bg-destructive px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 aria-disabled:opacity-70 ${FOCUS_RING}`;

export function channelHeadingId(channelId: string): string {
  return `${domId("channel", channelId)}-heading`;
}

export interface ContactChannelRowProps {
  readonly channel: MyContactChannel;
  /** The inline opt-out confirmation is open for this row. */
  readonly confirming: boolean;
  /** The choice this row is saving, when the page's one request is this row's. */
  readonly pressed: ChannelChoice | null;
  /** Some request is in flight on the page, or nothing may be sent yet. */
  readonly blocked: boolean;
  /** This row's last failure, in fixed words. */
  readonly error: string | null;
  readonly onOptIn: () => void;
  readonly onAskOptOut: () => void;
  readonly onConfirmOptOut: () => void;
  readonly onKeep: () => void;
}

function StatusIcon({ channel }: { channel: MyContactChannel }) {
  const className = "mt-0.5 h-4 w-4 shrink-0";
  if (channel.send_eligible) {
    return <CheckCircle2 className={`${className} text-primary`} aria-hidden="true" />;
  }
  if (channel.suppressed) {
    return <BellOff className={`${className} text-muted-foreground`} aria-hidden="true" />;
  }
  return <CircleDashed className={`${className} text-muted-foreground`} aria-hidden="true" />;
}

/**
 * A button whose name is its visible label followed by an sr-only suffix, so
 * the name contains and starts with what is on screen (WCAG 2.5.3). The
 * pressed state is `aria-disabled` plus a click guard, never `disabled`.
 */
function ChoiceButton({
  label,
  suffix,
  savingSuffix,
  pressed,
  blocked,
  describedBy,
  className,
  buttonRef,
  onClick,
}: {
  label: string;
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
      {pressed ? "Saving…" : label}
      <span className="sr-only">{pressed ? savingSuffix : suffix}</span>
    </button>
  );
}

export function ContactChannelRow({
  channel,
  confirming,
  pressed,
  blocked,
  error,
  onOptIn,
  onAskOptOut,
  onConfirmOptOut,
  onKeep,
}: ContactChannelRowProps) {
  const { address, contact_channel_id: id } = channel;
  const headingId = channelHeadingId(id);
  const errorId = `${domId("channel", id)}-error`;
  const describedBy = error !== null ? errorId : undefined;

  const confirmRef = useRef<HTMLButtonElement>(null);
  const optOutRef = useRef<HTMLButtonElement>(null);
  // Set only by Keep receiving: closing the confirm row after a save sends
  // focus to the row's heading instead (the page does that).
  const returnFocusRef = useRef(false);
  const showConfirm = confirming && channel.can_opt_out;

  useEffect(() => {
    if (showConfirm) {
      confirmRef.current?.focus();
    } else if (returnFocusRef.current) {
      returnFocusRef.current = false;
      optOutRef.current?.focus();
    }
  }, [showConfirm]);

  let actions: ReactNode;
  if (showConfirm) {
    actions = (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-foreground">
          Stop invitations to <span className="break-all">{address}</span>? An invitation already
          being sent at this moment may still arrive.
        </p>
        <div className="flex flex-wrap gap-2">
          <ChoiceButton
            buttonRef={confirmRef}
            label="Confirm opt out"
            suffix={` of invitations at ${address}`}
            savingSuffix={`, opting out of invitations at ${address}`}
            pressed={pressed === "opt_out"}
            blocked={blocked}
            describedBy={describedBy}
            className={BUTTON_DESTRUCTIVE}
            onClick={onConfirmOptOut}
          />
          <ChoiceButton
            label="Keep receiving"
            suffix={` invitations at ${address}`}
            savingSuffix={` invitations at ${address}`}
            pressed={false}
            blocked={blocked}
            describedBy={undefined}
            className={BUTTON_QUIET}
            onClick={() => {
              returnFocusRef.current = true;
              onKeep();
            }}
          />
        </div>
      </div>
    );
  } else if (channel.can_opt_in) {
    actions = (
      <ChoiceButton
        label="Opt in"
        suffix={` to invitations at ${address}`}
        savingSuffix={`, opting in to invitations at ${address}`}
        pressed={pressed === "opt_in"}
        blocked={blocked}
        describedBy={describedBy}
        className={BUTTON_PRIMARY}
        onClick={onOptIn}
      />
    );
  } else if (channel.can_opt_out) {
    actions = (
      <ChoiceButton
        buttonRef={optOutRef}
        label="Opt out"
        suffix={` of invitations at ${address}`}
        savingSuffix={` of invitations at ${address}`}
        pressed={false}
        blocked={blocked}
        describedBy={describedBy}
        className={BUTTON_QUIET}
        onClick={onAskOptOut}
      />
    );
  } else {
    actions = (
      <p className="text-sm text-muted-foreground">To change this, ask your Speaker Connector.</p>
    );
  }

  return (
    <li className="grid gap-3 rounded-xl border border-border/70 bg-card p-4 sm:grid-cols-[1fr_auto] sm:items-start">
      <div className="min-w-0 space-y-1">
        <h3
          id={headingId}
          tabIndex={-1}
          className="scroll-mt-20 break-all text-base font-semibold text-foreground focus:outline-none"
        >
          {address}
        </h3>
        <p className="flex items-start gap-1.5 text-sm text-foreground">
          <StatusIcon channel={channel} />
          <span>{channelStatusSentence(channel)}</span>
        </p>
        <p className="text-xs text-muted-foreground">{lastSetByLabel(channel.last_set_by)}</p>
      </div>
      <div className="sm:justify-self-end">{actions}</div>
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
