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
  className?: string;
  /**
   * How loud the banner is. `"loud"` (the default) is the CBA treatment and
   * is unchanged. `"quiet"` is the class exercise's slim ribbon
   * (`docs/design/class-exercise/DESIGN.md` §6.2): a gold-tint wash with no
   * border, an `Info` icon and sentence-case text. It is still always
   * visible, never dismissible, and icon plus words; only the volume differs.
   */
  tone?: "loud" | "quiet";
  /**
   * The bold prefix before `reason`. Defaults to the CBA wording, so every
   * existing caller renders exactly as before. The exercise passes
   * "Fictional data —" (owner ruling 2026-09-26).
   */
  label?: string;
}

/** The CBA prefix, unchanged. */
const DEFAULT_LABEL = "Synthetic / demo data —";

/**
 * An unmissable, full-width banner for a screen or section that is entirely
 * fixture-backed. Deliberately louder than any other provenance treatment in
 * this module — high-contrast border and fill, an icon, and bold label text
 * — because DESIGN.md §1.1 singles this one label out as needing to be
 * unmistakable, not merely present.
 */
export function SyntheticDataBanner({
  reason,
  className,
  tone = "loud",
  label = DEFAULT_LABEL,
}: SyntheticDataBannerProps): React.JSX.Element {
  if (tone === "quiet") {
    return (
      <div
        role="status"
        data-slot="synthetic-data-banner"
        data-tone="quiet"
        className={cn(
          "flex items-start gap-3 rounded-[14px] bg-[var(--ce-gold-tint,#fff1cc)] px-4 py-3 text-[var(--ce-ink,#163229)]",
          className,
        )}
      >
        <Info
          aria-hidden="true"
          className="mt-0.5 size-5 shrink-0 text-[var(--ce-gold-ink,#7a5200)]"
        />
        <p className="text-[15px] leading-[22px] font-medium md:text-base md:leading-6">
          <span className="font-bold text-[var(--ce-gold-ink,#7a5200)]">{label} </span>
          {reason}
        </p>
      </div>
    );
  }
  return (
    <div
      role="status"
      data-slot="synthetic-data-banner"
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
        <span className="font-bold uppercase tracking-wide">
          {label}{" "}
        </span>
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
