/**
 * The provenance + drill-down affordance for one accountable metric.
 *
 * Implements ADR-0011 rules 2 and 4
 * (`docs/architecture/decisions/ADR-0011-accountable-numbers.md`) and the
 * provenance taxonomy in `apps/web/DESIGN.md` §1.1:
 *
 * - Rule 2 ("one canonical name, one written definition"): the metric's
 *   registered name and one-sentence definition are attached to the value
 *   itself, in a tooltip, rather than living only in a register a viewer
 *   cannot see from the screen.
 * - Rule 4 ("a drill-down returns exactly the rows the number was computed
 *   from"): when a `DrilldownRef` is supplied, this renders the trigger that
 *   opens it. `apps/web/DESIGN.md` §1.10 is explicit that an aggregate
 *   rendered *without* this affordance "cannot be checked by anyone,
 *   reviewer or test" — so the trigger is part of the primitive, not an
 *   optional decoration a page remembers to add.
 *
 * `ProvenanceBadge` is exported separately for the (rarer) case a caller has
 * a bare `Provenance` with no metric name/definition/drilldown to attach.
 */
import * as React from "react";
import { ArrowRight } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../ui/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "../ui/tooltip";
import {
  PROVENANCE_DESCRIPTIONS,
  PROVENANCE_LABELS,
  type AccountableMetric,
  type DrilldownRef,
  type Provenance,
} from "./types";

/**
 * One visual treatment per provenance category. `synthetic` is deliberately
 * the loudest of the five (bold, saturated amber) — DESIGN.md §1.1 requires
 * it be "unmistakable", and the other four are real data that should not
 * compete with it for attention.
 */
const provenanceBadgeVariants = cva("border font-medium", {
  variants: {
    provenance: {
      observed:
        "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
      inferred:
        "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200",
      heuristic:
        "border-violet-200 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-200",
      model:
        "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
      synthetic:
        "border-amber-400 bg-amber-100 text-amber-900 font-semibold dark:border-amber-500 dark:bg-amber-900 dark:text-amber-100",
    } satisfies Record<Provenance, string>,
  },
  defaultVariants: {
    provenance: "observed",
  },
});

export interface ProvenanceBadgeProps
  extends VariantProps<typeof provenanceBadgeVariants> {
  provenance: Provenance;
  className?: string;
}

/** A bare provenance label, for a value with no name/definition to attach. */
export function ProvenanceBadge({
  provenance,
  className,
}: ProvenanceBadgeProps): React.JSX.Element {
  return (
    <Badge
      variant="outline"
      data-slot="provenance-badge"
      data-provenance={provenance}
      className={cn(provenanceBadgeVariants({ provenance }), className)}
    >
      {PROVENANCE_LABELS[provenance]}
    </Badge>
  );
}

export interface MetricDrilldownTriggerProps {
  drilldown: DrilldownRef;
  className?: string;
}

/**
 * Opens exactly the row set a metric was computed from (ADR-0011 rule 4).
 * `drilldown.rowCount`, when present, is surfaced in the accessible label so
 * a reviewer comparing "the number clicked" against "the rows returned" has
 * both numbers in front of them without opening the drill-down first.
 */
export function MetricDrilldownTrigger({
  drilldown,
  className,
}: MetricDrilldownTriggerProps): React.JSX.Element {
  const label = drilldown.label ?? "View rows";
  const accessibleLabel =
    drilldown.rowCount === undefined
      ? label
      : `${label} (${drilldown.rowCount.toLocaleString("en-US")} rows)`;

  return (
    <Button
      type="button"
      variant="link"
      size="sm"
      onClick={drilldown.onOpen}
      className={cn("h-auto gap-1 p-0 text-xs", className)}
      data-slot="metric-drilldown-trigger"
      data-row-set-digest={drilldown.rowSetDigest}
      aria-label={accessibleLabel}
    >
      {label}
      <ArrowRight aria-hidden="true" className="size-3" />
    </Button>
  );
}

export interface ProvenanceDisclosureProps {
  metric: AccountableMetric;
  className?: string;
}

/**
 * The full affordance for one `AccountableMetric`: a provenance badge whose
 * tooltip carries the metric's registered name and definition (rule 2), plus
 * a drill-down trigger when the metric has rows to show (rule 4).
 */
export function ProvenanceDisclosure({
  metric,
  className,
}: ProvenanceDisclosureProps): React.JSX.Element {
  return (
    <span
      data-slot="provenance-disclosure"
      className={cn("inline-flex items-center gap-2", className)}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0}>
            <ProvenanceBadge provenance={metric.provenance} />
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-64">
          <p className="font-semibold">{metric.name}</p>
          <p>{metric.definition}</p>
          <p className="mt-1 opacity-80">
            {PROVENANCE_LABELS[metric.provenance]} —{" "}
            {PROVENANCE_DESCRIPTIONS[metric.provenance]}
          </p>
        </TooltipContent>
      </Tooltip>
      {metric.drilldown ? (
        <MetricDrilldownTrigger drilldown={metric.drilldown} />
      ) : null}
    </span>
  );
}
