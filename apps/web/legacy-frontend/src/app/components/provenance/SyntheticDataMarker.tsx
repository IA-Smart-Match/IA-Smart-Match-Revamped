/**
 * The "Synthetic / demo" marker — for screens the backend cannot yet serve.
 *
 * Implements `apps/web/DESIGN.md` §1.1 ("Synthetic / demo ... Must be
 * unmistakable") and the frontend-migration plan's settled decision that
 * fixture-backed screens must be visibly labeled rather than served as if
 * real (`docs/plans/frontend-migration.md`: "Per-value provenance ...
 * DESIGN.md §1.1. Only a page-level demo chip exists.").
 *
 * This module intentionally has two exports at two different volumes:
 *
 * - `SyntheticDataBanner` — a full-width, high-contrast banner for a screen
 *   (or a major section of one) that is entirely fixture-backed. This is the
 *   "unmistakable" treatment the task calls for: it is not a caption, it
 *   does not rely on color alone (an icon and the word "Synthetic" both
 *   carry the meaning), and it states *why* in a sentence rather than
 *   leaving the viewer to guess.
 * - `SyntheticDataBadge` — composes the existing `DemoModeBadge` (see
 *   `../ui/DemoModeBadge.tsx`) for the narrower case of labeling one value or
 *   one card inline, where a full banner would be disproportionate. It does
 *   not replace `DemoModeBadge`; it wraps it so a caller reaching into
 *   `components/provenance` gets one import surface for every provenance
 *   need, including this one.
 *
 * Neither component decides *when* a screen is synthetic — that is a page
 * concern (e.g. "no live source for this yet") supplied by the caller.
 */
import * as React from "react";
import { FlaskConical, Info } from "lucide-react";

import { cn } from "../ui/utils";
import { DemoModeBadge } from "../ui/DemoModeBadge";

export interface SyntheticDataBannerProps {
  /**
   * Why this screen (or section) is synthetic — e.g. "The matching API is
   * not live yet; every row below is fixture data." Shown verbatim, so it
   * should be a complete sentence a viewer can act on.
   */
  reason: string;
  /**
   * `loud` (default) is the CBA treatment below. `quiet` is the class
   * exercise's slim ribbon (docs/design/class-exercise/DESIGN.md §6.2, ruling
   * 5: a variant, not a copy): gold-tint wash, no border, an `Info` icon,
   * meta-size text. It reads the exercise's `--ce-*` tokens, so it belongs
   * inside the exercise's `.ce-root` scope only.
   */
  tone?: "loud" | "quiet";
  /**
   * The bold prefix. Defaults to "Synthetic / demo data —"; the exercise
   * passes "Fictional data —" (owner ruling, 2026-09-26).
   */
  label?: string;
  className?: string;
}

/**
 * An unmissable, full-width banner for a screen or section that is entirely
 * fixture-backed. Deliberately louder than any other provenance treatment in
 * this module — high-contrast border and fill, an icon, and bold label text
 * — because DESIGN.md §1.1 singles this one label out as needing to be
 * unmistakable, not merely present.
 */
export function SyntheticDataBanner({
  reason,
  tone = "loud",
  label = "Synthetic / demo data —",
  className,
}: SyntheticDataBannerProps): React.JSX.Element {
  if (tone === "quiet") {
    return (
      <div
        role="status"
        data-slot="synthetic-data-banner"
        data-tone="quiet"
        className={cn(
          "flex items-start gap-ce-2 rounded-ce-card bg-ce-gold-tint px-ce-4 py-ce-2 text-ce-ink",
          className,
        )}
      >
        <Info aria-hidden="true" className="mt-[3px] size-5 shrink-0 text-ce-gold-ink" />
        <p className="ce-type-meta">
          <span className="font-bold">{label} </span>
          {reason}
        </p>
      </div>
    );
  }
  return (
    <div
      role="status"
      data-slot="synthetic-data-banner"
      data-tone="loud"
      className={cn(
        "flex items-start gap-3 rounded-lg border-2 border-amber-400 bg-amber-100 px-4 py-3 text-amber-900 shadow-sm dark:border-amber-500 dark:bg-amber-950 dark:text-amber-100",
        className,
      )}
    >
      <FlaskConical
        aria-hidden="true"
        className="mt-0.5 size-5 shrink-0 text-amber-700 dark:text-amber-300"
      />
      <p className="text-sm leading-snug">
        <span className="font-bold uppercase tracking-wide">{label} </span>
        {reason}
      </p>
    </div>
  );
}

export interface SyntheticDataBadgeProps {
  className?: string;
}

/**
 * Inline synthetic/demo marker for one value or card, where a full banner
 * would be disproportionate. Composes the existing `DemoModeBadge` rather
 * than duplicating it — see this file's header comment.
 */
export function SyntheticDataBadge({
  className,
}: SyntheticDataBadgeProps): React.JSX.Element {
  return (
    <span data-slot="synthetic-data-badge" className={className}>
      <DemoModeBadge />
    </span>
  );
}
