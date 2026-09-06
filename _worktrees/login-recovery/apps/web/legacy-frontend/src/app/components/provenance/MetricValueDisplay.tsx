/**
 * Renders a `MetricValue` for exactly the variant it is.
 *
 * Implements ADR-0011 rule 1 ("unknown is not zero"),
 * `docs/architecture/decisions/ADR-0011-accountable-numbers.md`, and the
 * "unknown value" component called for in `docs/ui/pilot-prototype-prompts.md`
 * ("a value with no evidence renders as 'Unknown', never `0`, never `0%`,
 * never an em-dash styled to look like a measurement").
 *
 * The switch below is exhaustive by construction: `assertNeverMetricValue`
 * only type-checks if every `MetricValueKind` has already been handled, so
 * adding a fourth variant to the union without updating this file is a
 * compile error here, not a silent fallthrough to some default rendering.
 */
import * as React from "react";

import { cn } from "../ui/utils";
import type { MetricValue } from "./types";

function assertNeverMetricValue(value: never): never {
  throw new Error(
    `MetricValueDisplay: unhandled MetricValue variant ${JSON.stringify(value)}`,
  );
}

export interface MetricValueDisplayProps {
  /** The value to render — see the three variants in `types.ts`. */
  value: MetricValue;
  className?: string;
  /**
   * Formats the numeral for `known` and `at_least`. Defaults to
   * locale-grouped digits (`1,234`). Never called for `unknown` — there is
   * no numeral to format.
   */
  formatNumber?: (numericValue: number) => string;
}

const defaultFormatNumber = (numericValue: number): string =>
  numericValue.toLocaleString("en-US");

/**
 * Renders one `MetricValue`. Composable with `ProvenanceDisclosure` — this
 * component only ever prints the numeral (or "Unknown"); it does not know
 * where the value came from or how to drill into it.
 */
export function MetricValueDisplay({
  value,
  className,
  formatNumber = defaultFormatNumber,
}: MetricValueDisplayProps): React.JSX.Element {
  switch (value.kind) {
    case "known":
      return (
        <span
          data-slot="metric-value"
          data-metric-kind="known"
          className={cn("tabular-nums font-medium text-foreground", className)}
        >
          {formatNumber(value.value)}
        </span>
      );

    case "at_least":
      // A truncated row set: real evidence, just not the whole count. Shown
      // with a leading "≥" rather than as a bare number, so it cannot be
      // mistaken for an exact count (the shape of the Fix #12 defect, one
      // step earlier: a number presented as more certain than it is).
      return (
        <span
          data-slot="metric-value"
          data-metric-kind="at_least"
          className={cn("tabular-nums font-medium text-foreground", className)}
          title="This count was truncated; the true total may be higher."
        >
          <span aria-hidden="true">&ge;&nbsp;</span>
          <span className="sr-only">At least </span>
          {formatNumber(value.value)}
        </span>
      );

    case "unknown":
      // ADR-0011 rule 1: this branch must never render a numeral, "0", or an
      // em-dash standing in for a measurement. It renders the word
      // "Unknown" and carries the reason in both a hover title and an
      // sr-only span, so the distinction survives for sighted and
      // screen-reader users alike.
      return (
        <span
          data-slot="metric-value"
          data-metric-kind="unknown"
          className={cn("italic text-muted-foreground", className)}
          title={value.reason}
        >
          Unknown
          <span className="sr-only">: {value.reason}</span>
        </span>
      );

    default:
      return assertNeverMetricValue(value);
  }
}
