/**
 * "Ask them now": the team's one refresh, which asks before it is spent
 * (issue #321; DESIGN.md §6.19).
 *
 * The refresh happens once per team and cannot be undone, like the results
 * run and the choice of how to ask. Those two already ask on the button
 * itself (`ce-confirm-window`, §5); this one sent on the first press. Now the
 * first press arms the button and sends nothing: it reads as the question,
 * and a second press inside five seconds asks. Escape or waiting puts it
 * back. A held Enter or Space never confirms. No pop-up.
 *
 * Used on both screens that offer the refresh (Asking for more, and Results),
 * so the question is the same words in both places.
 *
 * Once asked, the button is grey and says so itself: "Already refreshed at
 * 10:42 AM" (`aria-disabled`, never `disabled`, so it stays focusable).
 */
import * as React from "react";

import {
  Button,
  ConfirmWindowUnderline,
  useConfirmWindow,
  usePrefersReducedMotion,
  type ButtonVariant,
} from "./desk";
import { alreadyRefreshedLabel } from "./refreshWording";

/** The button before it is pressed. */
export const ASK_LABEL = "Ask them now";

/** The button while it waits for the second press. */
export const ASK_QUESTION = "Ask them now? Your team can ask only once";

/** Shown and spoken while the question is up. */
export const ASK_HINT = "Press again to ask. Your team cannot ask a second time, and it cannot be undone.";

export interface AskOnceButtonProps {
  readonly variant?: ButtonVariant;
  /** The team has already been refreshed, by itself or by the instructor. */
  readonly asked: boolean;
  /** When, as the server sent it; `null` when it is not known. */
  readonly askedAt: string | null;
  /** Shut for another reason (nothing chosen yet, another action in flight). */
  readonly disabled: boolean;
  /** The refresh is on its way. */
  readonly pending: boolean;
  /** Ids of the lines that say why it is shut. */
  readonly describedBy?: string;
  /** Called on the second press only. */
  readonly onAsk: () => void;
  readonly className?: string;
}

export function AskOnceButton({
  variant = "primary",
  asked,
  askedAt,
  disabled,
  pending,
  describedBy,
  onAsk,
  className,
}: AskOnceButtonProps): React.JSX.Element {
  const reduced = usePrefersReducedMotion();
  const confirm = useConfirmWindow({ onConfirm: onAsk });
  const { cancel } = confirm;
  const shut = asked || disabled || pending;
  // A question about a press that can no longer be made is taken down.
  React.useEffect(() => {
    if (shut) {
      cancel();
    }
  }, [cancel, shut]);
  const armed = confirm.armed && !shut;

  return (
    <div className="flex flex-col items-start gap-ce-2">
      <Button
        variant={variant}
        pending={pending}
        disabled={asked || disabled}
        describedBy={describedBy}
        className={className}
        onClick={confirm.press}
        onKeyDown={(event) => {
          if (event.repeat && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            return;
          }
          confirm.onKeyDown(event);
        }}
      >
        <span className="inline-flex flex-col items-stretch">
          <span>{asked ? alreadyRefreshedLabel(askedAt) : armed ? ASK_QUESTION : ASK_LABEL}</span>
          <ConfirmWindowUnderline active={armed && !reduced} reduced={false} />
        </span>
      </Button>
      <ConfirmWindowUnderline active={armed && reduced} reduced className="text-ce-ink-muted" />
      {/* Always present, so the hint is announced when the button arms. */}
      <p aria-live="polite" data-slot="exercise-ask-confirm" className="ce-type-meta text-ce-ink-muted">
        {armed ? ASK_HINT : ""}
      </p>
    </div>
  );
}
