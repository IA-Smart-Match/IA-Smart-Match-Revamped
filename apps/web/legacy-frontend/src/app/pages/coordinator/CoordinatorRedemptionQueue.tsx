/**
 * Redemption queue — coordinator portal.
 *
 * The reward tickets students have requested under this unit, one state at a
 * time, and the decision on each: approve, then mark fulfilled when the reward
 * is handed over; or deny. `GET /v1/units/{unit_id}/redemptions/queue` lists
 * them and `POST …/redemptions/{id}/decision` moves one; both are the routes
 * PR #200 shipped, gated on the same `admin`/`coordinator` roles, and this
 * page uses no other.
 *
 * ## What a row does not carry
 *
 * No student. The queue discloses a ticket's id, the item's name and cost
 * snapshots, its state and when it was opened — and by owner decision
 * (2026-09-21) nothing that names who opened it. So there is no student
 * column, no blank where one would go, and no second read to fill one in. The
 * copy says tickets are anonymous by design, because a coordinator meeting an
 * anonymous queue for the first time should be told that it is on purpose.
 *
 * ## What this page is careful not to do
 *
 * It computes nothing and remembers nothing the server did not just say. The
 * only number it shows is the length of the response it is drawing, in the
 * selected tab's label, and only once that response has loaded — an unloaded
 * tab has no number (ADR-0011 rule 1). `truncated` is read off the response
 * and rendered. After a decision the list is re-read; a `409` is shown as the
 * disagreement it is and the re-read is how the screen catches up. A `403` or
 * `429` is the server's sentence, and the filter stays usable under it: this
 * page renders its controls and shows the refusal as the answer, the posture
 * every other page in this shell takes.
 *
 * Design doc: `docs/design/coordinator-redemption-queue.md`.
 */
import { useEffect, useRef } from "react";
import { Info } from "lucide-react";

import type { RedemptionQueueStatus } from "../../../lib/api";
import { visibleRoleLabel } from "../../../lib/roleLabels";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useRedemptionQueue } from "../../hooks/useRedemptionQueue";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { TicketCard, TicketTableRow } from "./RedemptionTicketRow";

/** The five states, in state-machine order. */
const STATUS_TABS: readonly { value: RedemptionQueueStatus; label: string }[] = [
  { value: "requested", label: "Requested" },
  { value: "approved", label: "Approved" },
  { value: "fulfilled", label: "Fulfilled" },
  { value: "denied", label: "Denied" },
  { value: "expired", label: "Expired" },
];

/** One sentence per empty status; a blank list would not say which kind of nothing this is. */
const EMPTY_COPY: Readonly<Record<RedemptionQueueStatus, string>> = {
  requested:
    "No tickets waiting. Students have not requested a reward, or every request has been " +
    "decided. Tickets are anonymous by design.",
  approved:
    "No approved tickets. Approve a requested ticket and it appears here until you mark it " +
    "fulfilled.",
  fulfilled: "No fulfilled tickets. Mark an approved ticket fulfilled and it is recorded here.",
  denied: "No denied tickets. A ticket you deny is recorded here.",
  expired: "No expired tickets. A ticket the system closed unanswered is recorded here.",
};

const TAB_SELECTED =
  "min-h-11 rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-semibold " +
  "text-foreground motion-safe:transition-colors focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2";
const TAB_IDLE =
  "min-h-11 rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium " +
  "text-muted-foreground hover:bg-muted/60 motion-safe:transition-colors focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
const NOTICE = "rounded-xl border border-border/70 p-4 text-sm text-muted-foreground";
const ALERT = "rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground";

export function CoordinatorRedemptionQueue() {
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` is the only source of the unit id this page reads.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const queue = useRedemptionQueue(unitId);

  // After a decision the row leaves this status on the re-read, and the
  // button that had focus with it. Focus moves to the sentence that says what
  // happened, so a keyboard user reads the result and continues from the
  // top of the list rather than from `<body>`.
  const statusRef = useRef<HTMLParagraphElement>(null);
  const decidedSentence = queue.outcome?.kind === "decided" ? queue.outcome.sentence : null;
  useEffect(() => {
    if (decidedSentence !== null && queue.busyId === null) {
      statusRef.current?.focus();
    }
  }, [decidedSentence, queue.busyId]);

  // `CoordinatorPortalLayout` renders `PortalGate` when no portal was granted,
  // so reaching here without a grant means the mapping is still resolving.
  if (grant === null) {
    return null;
  }

  const rows = queue.redemptions;
  const busyItem = rows?.find((item) => item.redemption_id === queue.busyId) ?? null;
  // Loading is a sentence, not a spinner alone (design doc §5, row 1). What
  // is happening now outranks what happened last.
  const statusSentence =
    busyItem !== null
      ? `Recording your decision on ${busyItem.item_name}…`
      : queue.loading && unitId !== null
        ? `Loading ${queue.status} tickets…`
        : (decidedSentence ?? "");
  // The user-facing persona, never the stored role key (DESIGN.md, role names).
  const roleLabel = visibleRoleLabel(grant.role) ?? "role not recognised";

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Redemption queue</h1>
        <p className="text-sm text-muted-foreground">
          Reward tickets students have requested under your unit. Approve a request, then mark it
          fulfilled when the reward is handed over; deny a request that should not go through.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {roleLabel} · {grant.org_unit_path}
        </p>
      </header>

      <div className="space-y-2 rounded-xl border border-border/70 p-4 text-sm leading-6 text-muted-foreground">
        <p className="flex items-start gap-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            Tickets are anonymous by design: a ticket names the reward and its cost, not the
            student. Points leave a balance only when a ticket is marked fulfilled, and a decision
            is recorded once.
          </span>
        </p>
      </div>

      <nav className="flex flex-wrap gap-2" aria-label="Ticket status">
        {STATUS_TABS.map((tab) => {
          const selected = tab.value === queue.status;
          // The count is the loaded response's own length, on the selected tab
          // only, and never before it has loaded. Unknown is not zero.
          // `+` when the server said more exist: the length is what arrived,
          // not the total, and a bare number would claim to be the total.
          const count =
            selected && rows !== null ? ` (${rows.length}${queue.truncated ? "+" : ""})` : "";
          return (
            <button
              key={tab.value}
              type="button"
              aria-current={selected ? "page" : undefined}
              onClick={() => queue.setStatus(tab.value)}
              className={selected ? TAB_SELECTED : TAB_IDLE}
            >
              {tab.label}
              {count}
            </button>
          );
        })}
      </nav>

      {/* One polite region for progress and decision outcomes; refusals below use role="alert". */}
      <p
        ref={statusRef}
        tabIndex={-1}
        role="status"
        aria-live="polite"
        className={
          statusSentence === ""
            ? "sr-only"
            : `${NOTICE} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`
        }
      >
        {statusSentence}
      </p>

      {queue.outcome !== null && queue.outcome.kind !== "decided" ? (
        <p role="alert" className={ALERT}>
          {queue.outcome.sentence}
        </p>
      ) : null}

      {queue.loadFailure !== null ? (
        <div className={`${ALERT} space-y-3`} role="alert">
          <p>{queue.loadFailure.sentence}</p>
          {/* Retry only where a retry can change the answer: not a 4xx. */}
          {queue.loadFailure.kind === "unreachable" || queue.loadFailure.kind === "server_error" ? (
            <button
              type="button"
              onClick={() => {
                void queue.reload();
              }}
              className="min-h-11 rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              Try again
            </button>
          ) : null}
        </div>
      ) : null}

      {queue.truncated && rows !== null ? (
        <p className="rounded-xl border border-border/70 p-4 text-xs text-muted-foreground">
          Showing the oldest {rows.length} {rows.length === 1 ? "ticket" : "tickets"}; more exist
          at this status. Decide these to see the rest.
        </p>
      ) : null}

      {unitId === null ? (
        <p className={NOTICE}>
          The server has not assigned this account a unit, so there is no redemption queue to
          show.
        </p>
      ) : rows === null ? null : rows.length === 0 ? (
        <p className={NOTICE}>{EMPTY_COPY[queue.status]}</p>
      ) : (
        <>
          <h2 className="sr-only">Tickets</h2>
          {/* Cards below `md`; the table above. The hidden one is display:none, so
              assistive technology reads one presentation, not two. */}
          <ul className="space-y-3 md:hidden" aria-label="Tickets">
            {rows.map((item) => (
              <TicketCard
                key={item.redemption_id}
                item={item}
                busy={queue.busyId !== null}
                onDecide={queue.decide}
              />
            ))}
          </ul>
          <div className="hidden md:block">
            <table className="w-full border-collapse">
              <caption className="sr-only">Tickets at status {queue.status}, oldest first</caption>
              <thead>
                <tr className="text-left text-xs font-medium text-muted-foreground">
                  <th scope="col" className="pb-2 pr-4">Item</th>
                  <th scope="col" className="pb-2 pr-4">Points</th>
                  <th scope="col" className="pb-2 pr-4">Requested</th>
                  <th scope="col" className="pb-2 pr-4">State</th>
                  <th scope="col" className="pb-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <TicketTableRow
                    key={item.redemption_id}
                    item={item}
                    busy={queue.busyId !== null}
                    onDecide={queue.decide}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
