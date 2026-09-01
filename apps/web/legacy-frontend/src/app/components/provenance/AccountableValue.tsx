/**
 * `AccountableValue` — the single primitive a page needs for one accountable
 * number.
 *
 * Implements ADR-0011 in full for one metric
 * (`docs/architecture/decisions/ADR-0011-accountable-numbers.md`): it wires
 * `MetricValueDisplay` (rule 1 — unknown is not zero) together with
 * `ProvenanceDisclosure` (rules 2 and 4 — named definition and drill-down)
 * so a later page pass has one component to render an `AccountableMetric`,
 * rather than remembering to pair the two primitives correctly every time a
 * number appears. `MetricValueDisplay` and `ProvenanceDisclosure` stay
 * exported on their own for the layouts that need to place the numeral and
 * the disclosure in different parts of the page (e.g. a dense table cell
 * with the disclosure in a shared column header).
 */
import * as React from "react";

import { cn } from "../ui/utils";
import { MetricValueDisplay } from "./MetricValueDisplay";
import { ProvenanceDisclosure } from "./ProvenanceDisclosure";
import type { AccountableMetric } from "./types";

export interface AccountableValueProps {
  metric: AccountableMetric;
  className?: string;
  /** Passed through to `MetricValueDisplay`; see its docs. */
  formatNumber?: (numericValue: number) => string;
}

/**
 * Renders one `AccountableMetric` end to end: the value (never a fabricated
 * zero for `unknown`), and beside it the provenance badge and drill-down
 * trigger that make the value accountable rather than just displayed.
 */
export function AccountableValue({
  metric,
  className,
  formatNumber,
}: AccountableValueProps): React.JSX.Element {
  return (
    <span
      data-slot="accountable-value"
      className={cn("inline-flex flex-wrap items-center gap-2", className)}
    >
      <MetricValueDisplay value={metric.value} formatNumber={formatNumber} />
      <ProvenanceDisclosure metric={metric} />
    </span>
  );
}
