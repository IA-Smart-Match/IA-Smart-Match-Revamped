/**
 * Presents the rows behind one accountable metric without surfacing row payloads.
 *
 * Enforces ADR-0011 rule 4 on the client: the rows shown here must reconcile
 * with the aggregate the sheet was opened from — clicked N lists exactly N
 * rows, and an unknown aggregate corresponds to an empty row set. The check is
 * `assertDrilldownMatchesAggregate`, which until P8 card O4 fix round 3 was an
 * exported helper nothing called: the sheet rendered whatever rows came back
 * and the invariant was enforced only server-side in
 * `tests/contract/test_metrics.py`. A dead helper that looks like enforcement
 * is the same class of defect as a fabricated number.
 *
 * On mismatch the sheet refuses to render the rows and says so. A visible
 * failure is deliberate: silently showing a row set that disagrees with the
 * number the user clicked is the wrong answer delivered confidently.
 */
import * as React from "react";

import type { MetricDrillDownResponse } from "@/lib/api";
import { assertDrilldownMatchesAggregate, drilldownRowPreview } from "@/lib/metrics";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import { MetricValueDisplay } from "./MetricValueDisplay";
import { knownValue, unknownValue } from "./types";

export interface MetricDrilldownSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  loading: boolean;
  drilldown: MetricDrillDownResponse | null;
  error?: string | null;
}

export function MetricDrilldownSheet({
  open,
  onOpenChange,
  loading,
  drilldown,
  error,
}: MetricDrilldownSheetProps): React.JSX.Element {
  const aggregateIsUnknown =
    drilldown === null || drilldown.aggregate_value === null;
  const aggregateValue =
    drilldown === null || drilldown.aggregate_value === null
      ? unknownValue(drilldown?.unknown_reason ?? "This metric has no measured rows.")
      : knownValue(drilldown.aggregate_value);

  // ADR-0011 rule 4. Only meaningful once a payload has actually arrived, so
  // it is not evaluated while loading or when the request already failed.
  const reconciles =
    !loading && drilldown && !error ? assertDrilldownMatchesAggregate(drilldown) : true;
  const rowsAreShowable = !loading && drilldown !== null && !error && reconciles;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{drilldown?.name ?? "Metric drill-down"}</SheetTitle>
          <SheetDescription>
            {drilldown?.definition ?? "The exact rows this aggregate was computed from."}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4 px-4 pb-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Aggregate
            </p>
            <p className="mt-1 text-2xl">
              <MetricValueDisplay value={aggregateValue} />
            </p>
          </div>

          {loading ? (
            <p className="text-sm text-muted-foreground">Loading constituent rows…</p>
          ) : null}

          {error ? (
            <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </p>
          ) : null}

          {!loading && drilldown && !error && !reconciles ? (
            <div
              role="alert"
              className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900"
            >
              <p className="font-semibold">
                This drill-down does not reconcile with its aggregate
              </p>
              <p className="mt-1">
                {aggregateIsUnknown
                  ? `The aggregate is unknown, which under ADR-0011 rule 4 must correspond to an empty row set, but ${drilldown.rows.length} row${drilldown.rows.length === 1 ? " was" : "s were"} returned.`
                  : `The aggregate is ${drilldown.aggregate_value}, but ${drilldown.rows.length} row${drilldown.rows.length === 1 ? "" : "s"} came back.`}
              </p>
              <p className="mt-2">
                The rows are withheld rather than shown, because a row set that
                disagrees with the number you clicked cannot both be right. Report
                this — the aggregate and its drill-down are meant to be the same
                query.
              </p>
            </div>
          ) : null}

          {rowsAreShowable && drilldown.rows.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              {aggregateIsUnknown
                ? "This metric is unknown, so there is no row set to list. An unknown aggregate is not a measured zero."
                : "No rows: this metric measured zero."}
            </p>
          ) : null}

          {rowsAreShowable && drilldown.rows.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50 text-left">
                    <th className="px-3 py-2 font-medium">Row</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Id</th>
                  </tr>
                </thead>
                <tbody>
                  {drilldown.rows.map((row, index) => {
                    const preview = drilldownRowPreview(row);
                    return (
                      <tr key={`${preview.id}-${index}`} className="border-b border-border/60">
                        <td className="px-3 py-2 tabular-nums">{preview.row_index}</td>
                        <td className="px-3 py-2">{preview.status}</td>
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                          {preview.id}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
                Row payloads are omitted here; only structural fields are shown.
              </p>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
