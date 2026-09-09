/**
 * Review queue — coordinator portal.
 *
 * The dashboard has counted `pending_review_items` for a unit since before any
 * route listed them, so the screen contradicted itself: a badge saying seven
 * pending, and nowhere to see the seven. This page is the other half of that
 * sentence. `GET /v1/units/{unit_id}/review-items` and the metric derive a
 * row's owning unit through the same join — `review_item` has no owning unit
 * column of its own — so the length of this list and the value of that badge
 * are the same number by construction, and the contract test asserts it.
 *
 * ## What this page is careful not to do
 *
 * It computes nothing. It does not total the queue, does not subtract a decided
 * row from a remembered count, and does not render its own version of the
 * pending number anywhere. Every one of those would be a second copy of a
 * published figure, and ADR-0011 rule 4 is that a number with an owning query
 * is read from that query. After a decision this page **re-reads the list**
 * rather than splicing the decided row out of the array it already had: the
 * server is the thing that knows what happened, and an optimistic removal would
 * be this page inventing a result it was not told.
 *
 * `truncated` is rendered rather than swallowed. A full page is not a complete
 * one, and a queue that silently showed its first two hundred rows as though
 * they were all of them is the silent-zero failure ADR-0011 rule 1 forbids —
 * the reader would have no way to know they were looking at a fragment.
 *
 * A `409` is surfaced as what it is. The decision route's `UPDATE` is guarded
 * by `status = 'pending'`, so deciding a row someone else already decided
 * refuses cleanly instead of double-applying. That is a disagreement about the
 * state of the world, and the honest response is to say so and re-read — not to
 * retry, and certainly not to report success.
 *
 * ## Not authorization
 *
 * The route is `admin`/`coordinator`, decided per request against the loaded
 * unit, and a unit in another tenant is a `404` rather than a `403`. This page
 * renders its controls and shows the server's refusal as the answer it is,
 * rather than hiding them and implying the capability is absent — the posture
 * every other page in this shell takes.
 */

import { useCallback, useEffect, useState } from "react";
import { Info } from "lucide-react";

import {
  ApiRequestError,
  decideReviewItem,
  fetchReviewItems,
  type ReviewDecision,
  type ReviewItem,
  type ReviewItemStatus,
} from "../../../lib/api";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/*
 * TODO(integrator): track T1 is building a shared
 * `components/PagedList.tsx`. It did not exist in this worktree, so the list
 * below is a plain bounded render — deliberately *not* a second paging
 * component competing with T1's. When PagedList lands, swap the `<ul>` in
 * `CoordinatorReviewQueue` for it and hand it `items` and `truncated`; nothing
 * else on this page needs to change, and no paging state is kept here to
 * migrate. Do not generalise this file into a reusable list in the meantime.
 */

/** The three tabs, in the order a coordinator works them. */
const STATUS_TABS: readonly { value: ReviewItemStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Rejected" },
];

/**
 * Render one submitted record without pretending to know its columns.
 *
 * `row_data` is whatever the import carried, and it varies by dataset, so the
 * fields are enumerated from the object rather than read by name. A component
 * that reached for `full_name` would render an empty card for the first import
 * that called it something else — and an empty card is indistinguishable from
 * an empty row, which is exactly the confusion a review queue must not create.
 */
function RowDataTable({ rowData }: { rowData: Record<string, unknown> }) {
  const entries = Object.entries(rowData);

  if (entries.length === 0) {
    // Not a blank space: "this row carried no columns" is a real and alarming
    // fact about an import, and a coordinator deciding it should be told.
    return (
      <p className="text-xs text-muted-foreground">
        This row carried no columns. Rejecting it is usually right, but the import it came from is
        worth checking.
      </p>
    );
  }

  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2 text-xs">
          <dt className="shrink-0 font-medium text-muted-foreground">{key}</dt>
          <dd className="min-w-0 break-words text-foreground">
            {/*
              `null` is rendered as the word rather than as an empty cell. A
              blank would read as "this field is empty", which is a different
              claim from "the import supplied nothing here" — ADR-0011 rule 1
              applied to a table cell.
            */}
            {value === null || value === undefined ? (
              <span className="italic text-muted-foreground">not supplied</span>
            ) : typeof value === "object" ? (
              JSON.stringify(value)
            ) : (
              String(value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** One queued row, with its two decisions when it is still pending. */
function ReviewItemCard({
  item,
  busy,
  onDecide,
}: {
  item: ReviewItem;
  busy: boolean;
  onDecide: (item: ReviewItem, decision: ReviewDecision) => void;
}) {
  return (
    <li className="rounded-xl border border-border/70 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">Row {item.row_index}</h3>
        <p className="text-xs text-muted-foreground">
          Submitted {new Date(item.created_at).toLocaleString()}
          {/*
            `decided_at` is null for exactly the pending rows. Absent rather
            than zeroed: a row nobody has decided must not read as one decided
            at the epoch.
          */}
          {item.decided_at === null
            ? null
            : ` · decided ${new Date(item.decided_at).toLocaleString()}`}
        </p>
      </div>

      <div className="mt-3">
        <RowDataTable rowData={item.row_data} />
      </div>

      {item.status !== "pending" ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Already {item.status}. A decision is recorded once and cannot be recorded twice.
        </p>
      ) : (
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide(item, "accepted")}
            className="rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-50"
          >
            Accept
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide(item, "rejected")}
            className="rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </li>
  );
}

export function CoordinatorReviewQueue() {
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit id this page reads. The
  // browser never chooses which unit's queue to ask for.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const [status, setStatus] = useState<ReviewItemStatus>("pending");
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [decideError, setDecideError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (unitId === null) return;
    try {
      const response = await fetchReviewItems(unitId, status);
      setItems(response.items);
      // Read from the response, never inferred from `items.length === cap`:
      // the server measured it, and a client re-deriving it would be guessing
      // at a cap it does not own.
      setTruncated(response.truncated);
      setLoadError(null);
    } catch (cause) {
      // The list is emptied on failure rather than left showing the previous
      // status's rows under the new tab's heading. Stale rows presented as
      // current are worse than none: a coordinator would decide them believing
      // they were what they asked for.
      setItems([]);
      setTruncated(false);
      setLoadError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The review queue could not be loaded and the server gave no reason.",
      );
    } finally {
      setLoaded(true);
    }
  }, [unitId, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDecide = useCallback(
    async (item: ReviewItem, decision: ReviewDecision) => {
      setBusyId(item.id);
      setDecideError(null);
      try {
        await decideReviewItem(item.id, decision);
      } catch (cause) {
        setDecideError(
          cause instanceof ApiRequestError
            ? cause.message
            : "The decision could not be recorded and the server gave no reason.",
        );
      } finally {
        setBusyId(null);
        // Re-read either way. On success this is how the list and the
        // dashboard's count stay the same number; on failure — a `409` because
        // somebody else decided this row first — it is how the screen stops
        // showing a row that is no longer pending. Splicing the item out
        // locally would be this page inventing a result rather than reading
        // one.
        await load();
      }
    },
    [load],
  );

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the mapping
  // is still resolving.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Review queue</h1>
        <p className="text-sm text-muted-foreground">
          Imported records held for a decision before they enter the dataset.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <div className="space-y-2 rounded-xl border border-border/70 p-4 text-sm leading-6 text-muted-foreground">
        <p className="flex items-start gap-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            An import does not add records; it queues them here. Accepting one admits it to the
            dataset, rejecting one discards it, and either decision is recorded once — a row
            already decided cannot be decided again.
          </span>
        </p>
      </div>

      <nav className="flex gap-2" aria-label="Review item status">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            aria-current={tab.value === status ? "page" : undefined}
            onClick={() => {
              setStatus(tab.value);
              setLoaded(false);
            }}
            className={
              tab.value === status
                ? "rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-semibold text-foreground"
                : "rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium text-muted-foreground"
            }
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {loadError === null ? null : (
        <p
          role="alert"
          className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground"
        >
          {loadError}
        </p>
      )}

      {decideError === null ? null : (
        <p
          role="alert"
          className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground"
        >
          {decideError}
        </p>
      )}

      {truncated ? (
        <p className="rounded-xl border border-border/70 p-4 text-xs text-muted-foreground">
          More items exist at this status than are shown. Decide some of these and reload to see the
          rest — this is a page of the queue, not the whole of it.
        </p>
      ) : null}

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there is no review queue to show.
        </p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          {!loaded ? "Loading…" : `This unit has no ${status} review items.`}
        </p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <ReviewItemCard
              key={item.id}
              item={item}
              busy={busyId === item.id}
              onDecide={handleDecide}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
