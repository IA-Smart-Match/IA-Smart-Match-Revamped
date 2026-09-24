/**
 * `/speaker-portal/contact-preferences` — which of the Speaker's own addresses
 * may receive invitations (B26 T6b-4 §5.5).
 *
 * Reads `GET /v1/me/contact-channels`; writes `POST …/{id}/opt-in` and
 * `…/opt-out`. Nothing here names a Speaker, a unit or a user: the server
 * resolves the Speaker from the bearer token.
 *
 * ## One request at a time, and focus that never drops
 *
 * While a choice is saving, the pressed button keeps keyboard focus with
 * `aria-disabled` and reads "Saving…", and every other choice button is
 * `disabled`. Both clear only after the list has been re-read, so a row never
 * shows its old button once the server has changed it. On success the outcome
 * is announced in the page's one `role="status"` region and focus moves to
 * the row's heading; on failure the row's own `role="alert"` says why and
 * focus stays on the button that was pressed. An address that vanished on the
 * re-read keeps its message at page level, with focus on the page heading.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router";

import type { MyContactChannel, MyContactChannelChange } from "@/lib/api";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import {
  useMyChannelChoice,
  useMyContactChannels,
  type ChannelChoice,
} from "@/app/hooks/useSpeakerSelf";

import { ContactChannelRow, channelHeadingId } from "./ContactChannelRow";
import { SpeakerReadError, SpeakerSelfNotice, SpeakerStaleReadAlert } from "./SpeakerSelfNotice";
import { selfNoticeKind, speakerPortalError } from "./speakerPortalErrors";
import { channelStatusSentence } from "./speakerPortalFormat";
import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

const HEADING = "Contact preferences";
const HEADING_ID = "contact-preferences-heading";
const LINK_CLASS =
  "font-medium text-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

function lowerFirst(sentence: string): string {
  return sentence.charAt(0).toLowerCase() + sentence.slice(1);
}

/** The C6 outcome sentence, from the response the server returned. */
function choiceSentence(choice: ChannelChoice, result: MyContactChannelChange): string {
  const { address } = result.channel;
  if (choice === "opt_out") {
    return result.changed
      ? `You opted out of invitations to ${address}.`
      : `${address} was already opted out. Nothing changed.`;
  }
  if (!result.changed) return `${address} was already opted in. Nothing changed.`;
  if (result.channel.send_eligible) return `Invitations can be emailed to ${address} again.`;
  return `Your choice is saved. ${address} still cannot receive invitations: ${lowerFirst(
    channelStatusSentence(result.channel),
  )}`;
}

interface RowError {
  readonly channelId: string;
  readonly message: string;
}

export function SpeakerContactPreferences() {
  useSpeakerPageTitle(HEADING);
  const principalKey = usePrincipalKey();
  const channels = useMyContactChannels();
  const choice = useMyChannelChoice();

  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [rowError, setRowError] = useState<RowError | null>(null);
  const [focusTarget, setFocusTarget] = useState<string | null>(null);

  const list: readonly MyContactChannel[] | undefined = channels.data?.channels;
  const orphanError =
    rowError !== null &&
    list !== undefined &&
    !list.some((channel) => channel.contact_channel_id === rowError.channelId)
      ? rowError.message
      : null;

  // Focus follows the outcome once the element it names is on screen: a row's
  // heading after a save (it exists once the re-read has rendered), or the
  // page heading when the row the reader was on is gone.
  useEffect(() => {
    if (focusTarget === null) return;
    const target = document.getElementById(focusTarget);
    if (target !== null) {
      target.focus();
      setFocusTarget(null);
    }
  });

  useEffect(() => {
    if (orphanError !== null) setFocusTarget(HEADING_ID);
  }, [orphanError]);

  const pending = choice.isPending ? choice.variables : undefined;
  const blocked = choice.isPending || principalKey === null;

  function submit(channelId: string, next: ChannelChoice): void {
    if (blocked) return;
    setStatus("");
    setRowError(null);
    choice.mutate(
      { channelId, choice: next },
      {
        onSuccess: (result) => {
          setConfirmingId(null);
          setStatus(choiceSentence(next, result));
          setFocusTarget(channelHeadingId(channelId));
        },
        onError: (cause) => {
          setRowError({ channelId, message: speakerPortalError("channel", cause).message });
        },
      },
    );
  }

  let content;
  if (channels.data === undefined) {
    if (channels.isError) {
      const kind = selfNoticeKind(channels.error);
      content =
        kind !== null ? (
          <SpeakerSelfNotice kind={kind} />
        ) : (
          <SpeakerReadError
            message={speakerPortalError("read-addresses", channels.error).message}
            subject="your addresses"
            onRetry={() => void channels.refetch()}
          />
        );
    } else {
      content = <p className="text-sm text-muted-foreground">Loading your addresses…</p>;
    }
  } else if (channels.data.channels.length === 0) {
    content = (
      <p className="text-sm text-muted-foreground">
        No addresses are on file for you. Your Speaker Connector adds them.
      </p>
    );
  } else {
    content = (
      <div className="space-y-3">
        {channels.isError ? (
          <SpeakerStaleReadAlert
            message={speakerPortalError("read-addresses", channels.error).message}
          />
        ) : null}
        <ul className="space-y-3">
          {channels.data.channels.map((channel) => {
            const id = channel.contact_channel_id;
            return (
              <ContactChannelRow
                key={id}
                channel={channel}
                confirming={confirmingId === id}
                pressed={pending?.channelId === id ? pending.choice : null}
                blocked={blocked}
                error={rowError?.channelId === id ? rowError.message : null}
                onOptIn={() => submit(id, "opt_in")}
                onAskOptOut={() => {
                  setRowError(null);
                  setConfirmingId(id);
                }}
                onConfirmOptOut={() => submit(id, "opt_out")}
                onKeep={() => setConfirmingId(null)}
              />
            );
          })}
        </ul>
        {channels.data.truncated ? (
          <p className="text-xs text-muted-foreground">Showing the first 50 addresses.</p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2">
        <h1
          id={HEADING_ID}
          tabIndex={-1}
          className="scroll-mt-20 text-2xl font-semibold text-foreground focus:outline-none"
        >
          {HEADING}
        </h1>
        <p className="text-sm text-muted-foreground">
          Choose which of your addresses may receive invitations. Opting out is immediate. To stop
          invitations for a while instead, set a pause on the{" "}
          <Link to="/speaker-portal/availability" className={LINK_CLASS}>
            Availability page
          </Link>
          .
        </p>
      </header>

      <p role="status" aria-live="polite" className={status ? "text-sm text-foreground" : "sr-only"}>
        {status}
      </p>

      {orphanError !== null ? <SpeakerStaleReadAlert message={orphanError} /> : null}

      <section
        aria-labelledby="your-addresses-heading"
        aria-busy={channels.data === undefined && !channels.isError ? true : undefined}
        className="space-y-3"
      >
        <h2 id="your-addresses-heading" className="text-lg font-semibold text-foreground">
          Your addresses
        </h2>
        {content}
      </section>
    </div>
  );
}
