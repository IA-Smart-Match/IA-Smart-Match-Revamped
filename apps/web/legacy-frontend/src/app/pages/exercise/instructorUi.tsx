/**
 * The instructor page's small shared pieces (DESIGN.md §6.24, §7.11).
 *
 * Each panel on the page is one white card with a serif `h2`, so the panel is
 * the card: nesting stops at one level (§10). Rows inside a card are flat, and
 * an open detail or an inline confirm sits in a sunk well, not in a second card.
 */
import * as React from "react";

import { cn } from "../../components/ui/utils";
import { SkeletonRegion, Skeleton } from "./desk";

/** A text or number field on the instructor page: 2px outline, control radius, 48/56px tall. */
export const INSTRUCTOR_INPUT =
  "min-h-ce-control rounded-ce-control border-2 border-ce-line-strong bg-ce-surface px-ce-3 ce-type-body text-ce-ink";

/** A sunk well inside a card: an inline confirm, an open team's work, a data file. */
export const INSTRUCTOR_WELL = "rounded-ce-control bg-ce-surface-sunk p-ce-4";

export function PanelCard({
  title,
  slot,
  headerAction,
  className,
  children,
}: {
  readonly title: string;
  /** `data-slot` for the section; other tests find panels by it. */
  readonly slot?: string;
  /** One control beside the heading, e.g. "Check the teams again". */
  readonly headerAction?: React.ReactNode;
  readonly className?: string;
  readonly children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section
      data-slot={slot}
      className={cn("ce-card flex min-w-0 flex-col gap-ce-4 p-ce-4 md:p-ce-5", className)}
    >
      <div className="flex flex-wrap items-center justify-between gap-ce-3">
        <h2 className="ce-type-h2 text-ce-ink">{title}</h2>
        {headerAction}
      </div>
      {children}
    </section>
  );
}

/** The stated loading line (§6.21) with `rows` row-shaped blocks under it. */
export function PanelSkeleton({
  what,
  rows = 2,
}: {
  /** Finishes "Loading …", e.g. "the teams". */
  readonly what: string;
  readonly rows?: number;
}): React.JSX.Element {
  return (
    <SkeletonRegion label={`Loading ${what}…`} className="flex flex-col gap-ce-3">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} aria-hidden="true" className="flex items-center gap-ce-3 py-ce-2">
          <Skeleton className="h-6 w-2/5" />
          <Skeleton className="ml-auto h-10 w-32" />
        </div>
      ))}
    </SkeletonRegion>
  );
}
