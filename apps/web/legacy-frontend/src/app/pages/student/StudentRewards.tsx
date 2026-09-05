/**
 * The student rewards page, rendered entirely from server values.
 *
 * What this page used to do, and no longer does:
 *
 * - computed a balance in the browser (`getStudentTotalPoints`, deleted);
 * - held its own seven-item catalog with invented point costs
 *   (`STUDENT_REWARD_CATALOG`, deleted — Fix #15);
 * - rendered an unloaded profile as `0 points`;
 * - drew a progress bar toward whichever item happened to be next in a
 *   client-side sort, with no way to know whether that item was funded;
 * - "sent" a redemption by adding an id to a local `Set` and calling it
 *   `Request sent (demo)`.
 *
 * Every one of those is now a server fact: the balance is a fold over the point
 * ledger, the items are the rows with a named budget owner and a funded balance,
 * the progress numbers come with a `progress_state` saying whether they are
 * numbers at all, and the request is `POST /v1/units/{unit_id}/redemptions`
 * whose response is a durable ticket in state `requested`.
 */
import { Link } from "react-router";
import { AlertTriangle, ArrowLeft, Check, Lock } from "lucide-react";

import { Skeleton } from "../../components/ui/skeleton";
import { AppIcon } from "../../../components/AppIcon";
import { Button } from "../../components/ui/button";
import { Progress } from "../../components/ui/progress";
import { useRewards } from "../../hooks/useRewards";
import type { Redemption, RewardCatalogItem } from "../../../lib/api";
import { ROLE_PRESENTATION } from "../../../lib/roleLabels";

/**
 * Who reviews a redemption, in the vocabulary the rest of CBA uses.
 *
 * The decision roles are the stored `coordinator` and `admin`
 * (`routers/rewards.py::_REDEMPTION_DECISION_ROLES`), and both present as the
 * Speaker Connector persona — so this reads the label out of the one map
 * (`docs/product/cba-role-presentation.md`) instead of spelling a persona a
 * fourth time. Nothing stored changes; only what a student is told.
 */
const REVIEWER_LABEL = ROLE_PRESENTATION.coordinator.roleLabel;

/** How a ticket's state reads to the student who owns it. */
const REDEMPTION_STATE_LABELS: Record<Redemption["state"], string> = {
  requested: `Requested — awaiting ${REVIEWER_LABEL} review`,
  approved: "Approved — awaiting fulfilment",
  fulfilled: "Fulfilled",
  denied: `Declined by your ${REVIEWER_LABEL}`,
  expired: "Expired",
};

/** Ticket states that still hold a claim on this item, so it cannot be re-requested. */
const OPEN_REDEMPTION_STATES: ReadonlySet<Redemption["state"]> = new Set<Redemption["state"]>([
  "requested",
  "approved",
]);

/**
 * The balance, or an honest dash.
 *
 * Never `?? 0`. `points` is null exactly when the server said the balance is
 * unknown, and a zero there would be the ADR-0011 defect this page was rewritten
 * to remove.
 */
function PointsBadge({ points }: { points: number | null }) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-4 py-2 text-primary">
      <AppIcon name="points" className="h-4 w-4 text-primary" aria-hidden />
      <span className="text-sm font-semibold text-primary">
        {points === null ? "Points not established" : `${points.toLocaleString()} points`}
      </span>
    </div>
  );
}

/**
 * One reward card.
 *
 * The progress bar is rendered only when `progress_state === "measured"` *and*
 * the item is not already affordable — a bar toward something you can have now
 * says nothing, and a bar toward something whose distance the server declined to
 * compute would be the implication ("it's coming") the card fence forbids.
 */
function RewardCard({
  item,
  openTicket,
  pending,
  onRequest,
}: {
  item: RewardCatalogItem;
  openTicket: Redemption | undefined;
  pending: boolean;
  onRequest: () => void;
}) {
  const measured = item.progress_state === "measured";
  const showProgress =
    measured && !item.affordable && item.points_still_needed !== null && item.points_cost > 0;

  return (
    <div
      className={`flex flex-col rounded-2xl border p-6 shadow-sm transition ${
        item.affordable
          ? "border-primary/25 bg-[linear-gradient(180deg,hsl(var(--card))_0%,hsl(var(--primary)/0.06)_100%)]"
          : "border-border/70 bg-card"
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-foreground">{item.name}</h3>
          {!item.affordable && measured ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
              <Lock className="h-3 w-3" aria-hidden />
              Locked
            </span>
          ) : null}
        </div>
        <p className="mt-3 text-sm font-semibold text-primary">
          {item.points_cost.toLocaleString()} points
        </p>

        {showProgress ? (
          <div className="mt-4">
            <Progress
              className="h-2 bg-primary/15"
              value={Math.min(
                100,
                Math.round(
                  ((item.points_cost - (item.points_still_needed as number)) / item.points_cost) *
                    100,
                ),
              )}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              {(item.points_still_needed as number).toLocaleString()} more points
              {item.events_still_needed !== null
                ? ` — about ${item.events_still_needed} more verified ${
                    item.events_still_needed === 1 ? "event" : "events"
                  }`
                : ""}
            </p>
          </div>
        ) : null}

        {!measured ? (
          <p className="mt-4 text-xs text-muted-foreground">
            Your distance to this reward has not been established, so no progress is shown.
          </p>
        ) : null}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-border/60 pt-4">
        {openTicket ? (
          <span className="inline-flex items-center gap-2 text-sm font-medium text-foreground">
            <Check className="h-4 w-4 text-primary" aria-hidden />
            {REDEMPTION_STATE_LABELS[openTicket.state]}
          </span>
        ) : (
          <Button
            type="button"
            className="rounded-xl"
            disabled={!item.affordable || pending}
            onClick={onRequest}
          >
            {pending ? "Requesting…" : item.affordable ? "Request redemption" : "Not enough points"}
          </Button>
        )}
      </div>
    </div>
  );
}

export function StudentRewards() {
  const { status, catalog, redemptions, loadError, pendingItemIds, requestError, requestItem } =
    useRewards();

  if (status === "loading" || status === "idle") {
    return (
      <div className="space-y-6">
        <Skeleton className="h-40 w-full rounded-2xl" />
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-48 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  if (status === "unavailable" || catalog === null) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8 text-center">
        <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" />
        <p className="font-medium text-destructive">
          {loadError ?? "The rewards catalog could not be loaded."}
        </p>
        <Link
          to="/student-portal"
          className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to home
        </Link>
      </div>
    );
  }

  const balance = catalog.balance;
  // The open ticket per item, so a card shows the state of a request already
  // made instead of offering to make it again. `POST` is idempotent per item
  // server-side either way; this is what the student is told, not what enforces
  // it.
  const openTicketsByItem = new Map<string, Redemption>();
  for (const ticket of redemptions) {
    if (OPEN_REDEMPTION_STATES.has(ticket.state) && !openTicketsByItem.has(ticket.item_id)) {
      openTicketsByItem.set(ticket.item_id, ticket);
    }
  }

  const affordableCount = catalog.items.filter((item) => item.affordable).length;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Link
          to="/student-portal"
          className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to home
        </Link>
      </div>

      <div className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">
              Rewards &amp; professional development
            </h1>
            {/* What the server actually checked, said in those words: a named
                `budget_owner_id` and `funded IS TRUE` on the row. D6 §3 records
                the programme's ceiling as a $5,000 placeholder "explicitly not
                a ratified figure", so "confirmed funding" would promise an
                institutional fact this page cannot see. */}
            <p className="mt-1 max-w-2xl text-muted-foreground">
              Every reward below has a named budget owner and is recorded as funded. Redemptions are
              reviewed by a {REVIEWER_LABEL} before anything is handed over.
            </p>
            {balance.state === "unknown" ? (
              <p className="mt-3 text-sm text-foreground">
                {balance.unknown_reason ??
                  "Your point balance has not been established yet. It is not zero."}
              </p>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">
                Folded from {balance.ledger_entry_count.toLocaleString()} point ledger{" "}
                {balance.ledger_entry_count === 1 ? "entry" : "entries"}
                {affordableCount > 0
                  ? ` — you qualify for ${affordableCount} of ${catalog.items.length} rewards.`
                  : "."}
              </p>
            )}
            {!catalog.earn_policy_ratified ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Earn rate: {catalog.points_per_verified_attendance} points per verified attendance.
                This rate is a tentative working figure and has not been ratified.
              </p>
            ) : null}
          </div>
          <PointsBadge points={balance.points} />
        </div>
      </div>

      {requestError ? (
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {requestError}
        </div>
      ) : null}

      {catalog.items.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-8 text-center text-sm text-muted-foreground">
          No reward currently has both a named budget owner and a funded record, so there is nothing
          to show. This is the catalog being honest, not empty by accident.
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {catalog.items.map((item) => (
            <RewardCard
              key={item.item_id}
              item={item}
              openTicket={openTicketsByItem.get(item.item_id)}
              pending={pendingItemIds.has(item.item_id)}
              onRequest={() => void requestItem(item.item_id)}
            />
          ))}
        </div>
      )}

      {redemptions.length > 0 ? (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-foreground">Your redemptions</h2>
          <ul className="divide-y divide-border/60 rounded-2xl border border-border/70 bg-card">
            {redemptions.map((ticket) => (
              <li
                key={ticket.redemption_id}
                className="flex flex-wrap items-center justify-between gap-2 px-5 py-4"
              >
                <div className="min-w-0">
                  {/* The name and cost the ticket snapshotted, not today's — a
                      reward repriced or withdrawn since still reads correctly. */}
                  <p className="text-sm font-medium text-foreground">{ticket.item_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {ticket.points_cost.toLocaleString()} points at request
                  </p>
                </div>
                <span className="text-sm text-muted-foreground">
                  {REDEMPTION_STATE_LABELS[ticket.state]}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
