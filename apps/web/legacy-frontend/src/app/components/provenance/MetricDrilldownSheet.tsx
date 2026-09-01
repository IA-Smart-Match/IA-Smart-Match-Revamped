/**
 * Presents the rows behind one accountable metric without surfacing row payloads.
 */
import * as React from "react";

import type { MetricDrillDownResponse } from "@/lib/api";
import { drilldownRowPreview } from "@/lib/metrics";
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
  const aggregateValue =
    drilldown?.aggregate_value === null || drilldown?.aggregate_value === undefined
      ? unknownValue(drilldown?.unknown_reason ?? "This metric has no measured rows.")
      : knownValue(drilldown.aggregate_value);

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

          {!loading && drilldown && drilldown.rows.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              No rows are available for this metric yet.
            </p>
          ) : null}

          {!loading && drilldown && drilldown.rows.length > 0 ? (
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
