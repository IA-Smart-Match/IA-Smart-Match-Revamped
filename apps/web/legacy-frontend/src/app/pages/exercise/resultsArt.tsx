/**
 * Spot art for the results screens (DESIGN.md §4), inlined from
 * `docs/design/class-exercise/assets/svg/` so it inherits `currentColor`.
 *
 * Decorative only: every piece is `aria-hidden`, because the words next to it
 * already say what it shows. At most one per screen, never beside a heading.
 */
import * as React from "react";

interface ArtProps {
  readonly className?: string;
}

/** `invitation-envelope.svg`: the results locked state (§6.14). */
export function EnvelopeArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg viewBox="0 0 100 80" fill="none" aria-hidden="true" focusable="false" className={className}>
      <rect x="6" y="16" width="88" height="58" rx="6" fill="currentColor" opacity="0.12" stroke="currentColor" strokeWidth="3" />
      <path d="M6 20 L50 52 L94 20" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="50" cy="8" r="7" fill="currentColor" />
      <path d="M46 8 L49 11 L55 5" stroke="var(--ce-surface)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** `round-journey.svg`: round two, above the comparison (§7.10). */
export function RoundJourneyArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg viewBox="0 0 120 60" fill="none" aria-hidden="true" focusable="false" className={className}>
      <circle cx="20" cy="30" r="16" fill="currentColor" opacity="0.15" stroke="currentColor" strokeWidth="3" />
      <text x="20" y="35" fontFamily="var(--ce-font-display), Arial, sans-serif" fontSize="16" fontWeight="700" fill="currentColor" textAnchor="middle">
        1
      </text>
      <path d="M40 30 H78" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeDasharray="1 8" />
      <path d="M72 22 L82 30 L72 38" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="100" cy="30" r="18" fill="currentColor" opacity="0.9" stroke="currentColor" strokeWidth="3" />
      <text x="100" y="36" fontFamily="var(--ce-font-display), Arial, sans-serif" fontSize="18" fontWeight="700" fill="var(--ce-surface)" textAnchor="middle">
        2
      </text>
    </svg>
  );
}

/** `profile-card.svg`: the final-setting step when nothing is saved (§4). */
export function ProfileCardArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg viewBox="0 0 80 100" fill="none" aria-hidden="true" focusable="false" className={className}>
      <rect x="6" y="4" width="68" height="92" rx="8" fill="currentColor" opacity="0.08" stroke="currentColor" strokeWidth="3" />
      <circle cx="40" cy="34" r="14" fill="currentColor" opacity="0.6" />
      <rect x="22" y="58" width="36" height="6" rx="3" fill="currentColor" />
      <rect x="28" y="70" width="24" height="5" rx="2.5" fill="currentColor" opacity="0.5" />
      <rect x="16" y="82" width="48" height="6" rx="3" fill="currentColor" opacity="0.25" />
    </svg>
  );
}
