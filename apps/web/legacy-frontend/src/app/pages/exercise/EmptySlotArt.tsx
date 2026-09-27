/**
 * The "empty slot" spot art (DESIGN.md §4: `assets/svg/empty-state.svg`),
 * inline so it takes `currentColor`. Used only in empty states on the
 * matching screen: the empty list (§6.7 E) and a free saved-setting slot
 * (§6.11). Decorative: the sentence beside it carries the meaning.
 */
import * as React from "react";

import { cn } from "../../components/ui/utils";

export function EmptySlotArt({ className }: { readonly className?: string }): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 100 80"
      fill="none"
      aria-hidden="true"
      focusable="false"
      data-slot="exercise-empty-art"
      className={cn("shrink-0 text-ce-primary", className)}
    >
      <rect
        x="14"
        y="20"
        width="72"
        height="48"
        rx="8"
        fill="currentColor"
        opacity="0.08"
        stroke="currentColor"
        strokeWidth="3"
        strokeDasharray="6 6"
      />
      <path d="M40 44 h20" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M50 34 v20" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
