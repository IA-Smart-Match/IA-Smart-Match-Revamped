/**
 * One redemption ticket, drawn twice: a card below `md`, a table row at `md`
 * and up. Both are built from the same `RedemptionQueueItem` and the same
 * three pieces (state chip, request time, actions), so the two presentations
 * cannot disagree about a ticket.
 *
 * The actions a ticket offers come from its `state` and nothing else —
 * `requested -> approved -> fulfilled | denied | expired` — and `expired` is
 * never offered because an expiry has no author. A ticket at a terminal state
 * renders a sentence rather than an empty cell.
 *
 * Deny is the one destructive move, so it confirms inline: the first press
 * swaps the buttons for a confirm row inside the same card or cell. No modal;
 * a coordinator working twenty tickets should never lose their place.
 */
import { useEffect, useRef, useState } from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { Check, CheckCheck, Clock, Hourglass, X } from "lucide-react";

import type {
  RedemptionDecision,
  RedemptionQueueItem,
  RedemptionState,
} from "../../../lib/api";

const BUTTON =
  "min-h-11 rounded-lg border px-3 py-1.5 text-xs font-medium motion-safe:transition-colors " +
  "disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
  "focus-visible:ring-offset-2";
const BUTTON_QUIET = `${BUTTON} border-border/70 text-foreground hover:bg-muted`;
const BUTTON_DESTRUCTIVE = `${BUTTON} border-destructive/60 text-destructive hover:bg-destructive/5`;

const STATE_LABEL: Readonly<Record<RedemptionState, string>> = {
  requested: "Requested",
  approved: "Approved",
  fulfilled: "Fulfilled",
  denied: "Denied",
  expired: "Expired",
};

const STATE_CHIP: Readonly<Record<RedemptionState, string>> = {
  requested: "bg-muted text-foreground",
  approved: "bg-primary-container text-on-primary-container",
  fulfilled: "bg-accent text-accent-foreground",
  denied: "bg-destructive/10 text-foreground",
  expired: "bg-muted text-muted-foreground",
};

const STATE_ICON: Readonly<Record<RedemptionState, typeof Clock>> = {
  requested: Clock,
  approved: Check,
  fulfilled: CheckCheck,
  denied: X,
  expired: Hourglass,
};

/** The chip: an icon and a word, so colour is never the only signal. */
export function TicketStateChip({ state }: { state: RedemptionState }) {
  const Icon = STATE_ICON[state];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${STATE_CHIP[state]}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {STATE_LABEL[state]}
    </span>
  );
}

/** The absolute time and, beneath it, the relative one; both from the API timestamp. */
export function RequestedAt({ iso }: { iso: string }) {
  const at = new Date(iso);
  // A timestamp this browser cannot parse is a sentence, not a crash:
  // `formatDistanceToNowStrict` throws on an invalid date, and nothing above
  // this route would catch it.
  if (Number.isNaN(at.getTime())) {
    return <span className="block text-xs text-muted-foreground">Request time not readable</span>;
  }
  return (
    <time dateTime={iso} className="block text-xs text-muted-foreground">
      <span className="block text-foreground">{at.toLocaleString()}</span>
      <span className="block">{formatDistanceToNowStrict(at, { addSuffix: true })}</span>
    </time>
  );
}

/** The moves the machine allows from this state, in the order a coordinator makes them. */
function permittedMoves(
  state: RedemptionState,
): readonly { decision: RedemptionDecision; label: string; name: (item: string) => string }[] {
  switch (state) {
    case "requested":
      return [
        { decision: "approved", label: "Approve", name: (item) => `Approve ${item}` },
        { decision: "denied", label: "Deny", name: (item) => `Deny ${item}` },
      ];
    case "approved":
      return [
        {
          decision: "fulfilled",
          label: "Mark fulfilled",
          name: (item) => `Mark ${item} fulfilled`,
        },
        // No Deny: the domain allows approved -> fulfilled | expired only
        // (smartmatch_domain.rewards.REDEMPTION_TRANSITIONS).
      ];
    default:
      return [];
  }
}

export interface TicketActionsProps {
  readonly item: RedemptionQueueItem;
  readonly busy: boolean;
  readonly onDecide: (item: RedemptionQueueItem, decision: RedemptionDecision) => void;
}

/** The buttons for one ticket, with the inline Deny confirmation. */
export function TicketActions({ item, busy, onDecide }: TicketActionsProps) {
  const [confirmingDeny, setConfirmingDeny] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const denyRef = useRef<HTMLButtonElement>(null);
  // Whether the confirm row was open on the previous render, so closing it
  // (and only closing it) hands focus back to Deny after the buttons remount.
  const wasConfirmingRef = useRef(false);
  const moves = permittedMoves(item.state);

  // Keep focus inside the row: opening the confirm moves it to Confirm deny,
  // closing it with Keep returns to Deny, so a keyboard user never lands on
  // the body. Runs after commit, when the refs point at mounted buttons.
  useEffect(() => {
    if (confirmingDeny) {
      confirmRef.current?.focus();
    } else if (wasConfirmingRef.current) {
      denyRef.current?.focus();
    }
    wasConfirmingRef.current = confirmingDeny;
  }, [confirmingDeny]);

  if (moves.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No further decision is possible. A {STATE_LABEL[item.state].toLowerCase()} ticket is
        recorded once.
      </p>
    );
  }

  if (confirmingDeny) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs text-foreground">
          Deny this ticket? No points are taken; points leave a balance only at fulfillment.
        </p>
        <button
          ref={confirmRef}
          type="button"
          disabled={busy}
          aria-label={`Confirm deny ${item.item_name}`}
          onClick={() => {
            setConfirmingDeny(false);
            onDecide(item, "denied");
          }}
          className={BUTTON_DESTRUCTIVE}
        >
          Confirm deny
        </button>
        <button
          type="button"
          disabled={busy}
          aria-label={`Keep ${item.item_name}`}
          onClick={() => {
            setConfirmingDeny(false);
          }}
          className={BUTTON_QUIET}
        >
          Keep
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {moves.map((move) => (
        <button
          key={move.decision}
          ref={move.decision === "denied" ? denyRef : undefined}
          type="button"
          disabled={busy}
          aria-label={move.name(item.item_name)}
          onClick={() => {
            if (move.decision === "denied") {
              setConfirmingDeny(true);
            } else {
              onDecide(item, move.decision);
            }
          }}
          className={move.decision === "denied" ? BUTTON_DESTRUCTIVE : BUTTON_QUIET}
        >
          {move.label}
        </button>
      ))}
    </div>
  );
}

/** The card presentation, for narrow viewports. */
export function TicketCard(props: TicketActionsProps) {
  const { item } = props;
  return (
    <li className="space-y-2 rounded-xl border border-border/70 p-4">
      <h3 className="break-words text-sm font-semibold text-foreground">{item.item_name}</h3>
      <p className="text-sm tabular-nums text-foreground">{item.points_cost} points</p>
      <RequestedAt iso={item.requested_at} />
      <TicketStateChip state={item.state} />
      <div className="pt-1">
        <TicketActions {...props} />
      </div>
    </li>
  );
}

/** The table-row presentation, for `md` and up. */
export function TicketTableRow(props: TicketActionsProps) {
  const { item } = props;
  return (
    <tr className="border-t border-border/70 align-top motion-safe:transition-colors hover:bg-muted/40">
      <th scope="row" className="break-words py-3 pr-4 text-left text-sm font-semibold text-foreground">
        {item.item_name}
      </th>
      <td className="py-3 pr-4 text-sm tabular-nums text-foreground">{item.points_cost} points</td>
      <td className="py-3 pr-4">
        <RequestedAt iso={item.requested_at} />
      </td>
      <td className="py-3 pr-4">
        <TicketStateChip state={item.state} />
      </td>
      <td className="py-3">
        <TicketActions {...props} />
      </td>
    </tr>
  );
}
