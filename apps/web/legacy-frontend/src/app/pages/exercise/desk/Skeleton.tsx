/**
 * Loading skeletons (DESIGN.md §6.21): content-shaped blocks in
 * `--ce-surface-sunk` that breathe (`ce-skeleton`; static at 0.75 under
 * reduced motion, in CSS).
 *
 * The blocks are `aria-hidden`. `SkeletonRegion` carries the one visually
 * hidden `role="status"` line ("Loading the list…") so the parent contract's
 * stated-loading rule still holds. Pass the words for what is loading.
 */
import * as React from "react";

import { cn } from "../../../components/ui/utils";

export interface SkeletonProps {
  readonly className?: string;
  readonly style?: React.CSSProperties;
}

/** One breathing block. Size it with classes or `style`. */
export function Skeleton({ className, style }: SkeletonProps): React.JSX.Element {
  return (
    <span
      aria-hidden="true"
      data-slot="ce-skeleton"
      className={cn("ce-skeleton block rounded-ce-control", className)}
      style={style}
    />
  );
}

export interface SkeletonRegionProps {
  /** What is loading, as a sentence: "Loading the list…". */
  readonly label: string;
  readonly children: React.ReactNode;
  readonly className?: string;
}

/** Wraps skeleton blocks with the stated loading line for screen readers. */
export function SkeletonRegion({ label, children, className }: SkeletonRegionProps): React.JSX.Element {
  return (
    <div data-slot="ce-skeleton-region" className={className}>
      <span role="status" className="sr-only">
        {label}
      </span>
      {children}
    </div>
  );
}

/** The ranked list's shape: rank square, name bar, reason bar (§6.7 L). */
export function SkeletonRankedRows({ rows = 8 }: { readonly rows?: number }): React.JSX.Element {
  return (
    <div aria-hidden="true" className="flex flex-col">
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          data-slot="ce-skeleton-row"
          className="flex items-start gap-ce-4 border-b border-ce-line py-ce-4 last:border-b-0"
        >
          <Skeleton className="size-7 shrink-0" />
          <div className="flex flex-1 flex-col gap-ce-2">
            <Skeleton className="h-5 w-2/5" />
            <Skeleton className="h-4 w-[70%]" />
          </div>
          <Skeleton className="hidden h-5 w-24 md:block" />
          <Skeleton className="hidden h-5 w-16 md:block" />
        </div>
      ))}
    </div>
  );
}

/** A card-shaped placeholder: a title bar and `lines` text bars. */
export function SkeletonCard({
  lines = 3,
  className,
}: {
  readonly lines?: number;
  readonly className?: string;
}): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      data-slot="ce-skeleton-card"
      className={cn("ce-card flex flex-col gap-ce-3 p-ce-4 md:p-ce-5", className)}
    >
      <Skeleton className="h-7 w-1/2" />
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className={cn("h-4", index === lines - 1 ? "w-3/5" : "w-full")} />
      ))}
    </div>
  );
}
