/**
 * Spot art for the opening screen (DESIGN.md §4): the geometric shapes from
 * `docs/design/class-exercise/assets/svg/`, inlined so they take
 * `currentColor` and ship without an asset request.
 *
 * Both are decorative. The sentence beside each says everything the shape
 * does, so they are `aria-hidden` rather than labelled.
 */
import * as React from "react";

interface ArtProps {
  readonly className?: string;
}

/** `lecture-hall.svg`: beside the opening title, desktop only (§7.1). */
export function LectureHallArt({ className }: ArtProps): React.JSX.Element {
  const front = [10, 24, 38, 52, 66, 80, 94];
  const back = [17, 31, 45, 59, 73, 87];
  const faintFront = new Set([52]);
  const faintBack = new Set([31, 87]);
  return (
    <svg
      viewBox="0 0 120 90"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
      data-slot="exercise-lecture-hall"
      className={className}
    >
      <rect x="4" y="6" width="112" height="34" rx="4" fill="currentColor" opacity="0.12" />
      <path
        d="M20 30 L60 10 L100 30"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <g fill="currentColor">
        {front.map((x) => (
          <rect
            key={`f${x}`}
            x={x}
            y="52"
            width="10"
            height="10"
            rx="2"
            opacity={faintFront.has(x) ? 0.3 : undefined}
          />
        ))}
        {back.map((x) => (
          <rect
            key={`b${x}`}
            x={x}
            y="68"
            width="10"
            height="10"
            rx="2"
            opacity={faintBack.has(x) ? 0.3 : undefined}
          />
        ))}
      </g>
    </svg>
  );
}

/** `team-badge.svg`: at 32px beside "This browser is already in team …" (§7.2). */
export function TeamBadgeArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 80 90"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
      data-slot="exercise-team-badge"
      className={className}
    >
      <path
        d="M40 4 L70 16 V42 C70 62 58 76 40 86 C22 76 10 62 10 42 V16 Z"
        fill="currentColor"
        fillOpacity="0.12"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinejoin="round"
      />
      <circle cx="40" cy="38" r="14" stroke="currentColor" strokeWidth="5" />
      <path
        d="M33 38 L38 43 L48 31"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x="26" y="60" width="28" height="6" rx="3" fill="currentColor" opacity="0.5" />
    </svg>
  );
}
