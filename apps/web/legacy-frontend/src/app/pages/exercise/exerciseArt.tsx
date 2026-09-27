/**
 * The exercise's spot art: the geometric shapes in
 * `docs/design/class-exercise/assets/svg/`, as components.
 *
 * DESIGN.md §4: shapes, not pictures; coloured by `currentColor`; drawn at
 * 96–160px; only in empty, locked and first-visit states; at most one per
 * screen; never in a data row or next to a heading. Each is decorative — the
 * sentence beside it carries the meaning — so each is `aria-hidden`.
 */
import * as React from "react";

interface ArtProps {
  readonly className?: string;
}

function svgProps(viewBox: string, className: string | undefined) {
  return {
    viewBox,
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    "aria-hidden": true,
    focusable: false,
    className,
  } as const;
}

export function LectureHallArt({ className }: ArtProps): React.JSX.Element {
  const front = [10, 24, 38, 52, 66, 80, 94];
  const back = [17, 31, 45, 59, 73, 87];
  return (
    <svg {...svgProps("0 0 120 90", className)}>
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
          <rect key={`f${x}`} x={x} y="52" width="10" height="10" rx="2" opacity={x === 52 ? 0.3 : 1} />
        ))}
        {back.map((x) => (
          <rect
            key={`b${x}`}
            x={x}
            y="68"
            width="10"
            height="10"
            rx="2"
            opacity={x === 31 || x === 87 ? 0.3 : 1}
          />
        ))}
      </g>
    </svg>
  );
}

export function EnvelopeArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg {...svgProps("0 0 100 80", className)}>
      <rect
        x="6"
        y="16"
        width="88"
        height="58"
        rx="6"
        fill="currentColor"
        fillOpacity="0.12"
        stroke="currentColor"
        strokeWidth="3"
      />
      <path
        d="M6 20 L50 52 L94 20"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function EmptySlotArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg {...svgProps("0 0 100 80", className)}>
      <rect
        x="14"
        y="20"
        width="72"
        height="48"
        rx="8"
        fill="currentColor"
        fillOpacity="0.08"
        stroke="currentColor"
        strokeWidth="3"
        strokeDasharray="6 6"
      />
      <path d="M40 44 h20" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M50 34 v20" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function ProfileCardArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg {...svgProps("0 0 80 100", className)}>
      <rect
        x="6"
        y="4"
        width="68"
        height="92"
        rx="8"
        fill="currentColor"
        fillOpacity="0.08"
        stroke="currentColor"
        strokeWidth="3"
      />
      <circle cx="40" cy="34" r="14" fill="currentColor" opacity="0.6" />
      <rect x="22" y="58" width="36" height="6" rx="3" fill="currentColor" />
      <rect x="28" y="70" width="24" height="5" rx="2.5" fill="currentColor" opacity="0.5" />
      <rect x="16" y="82" width="48" height="6" rx="3" fill="currentColor" opacity="0.25" />
    </svg>
  );
}

export function PartlyKnownCardArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg {...svgProps("0 0 100 80", className)}>
      <rect
        x="8"
        y="10"
        width="84"
        height="60"
        rx="8"
        fill="currentColor"
        fillOpacity="0.1"
        stroke="currentColor"
        strokeWidth="3"
      />
      <rect x="8" y="10" width="42" height="60" rx="8" fill="currentColor" opacity="0.35" />
      <path d="M50 10 V70" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" />
      <circle cx="29" cy="34" r="8" fill="currentColor" opacity="0.7" />
      <rect x="19" y="48" width="20" height="4" rx="2" fill="currentColor" opacity="0.6" />
      <circle cx="71" cy="34" r="8" stroke="currentColor" strokeWidth="2" strokeDasharray="3 3" />
      <rect x="61" y="48" width="20" height="4" rx="2" fill="currentColor" opacity="0.25" />
    </svg>
  );
}

export function TeamBadgeArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg {...svgProps("0 0 80 90", className)}>
      <path
        d="M40 4 L70 16 V42 C70 62 58 76 40 86 C22 76 10 62 10 42 V16 Z"
        fill="currentColor"
        fillOpacity="0.12"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <circle cx="40" cy="38" r="14" stroke="currentColor" strokeWidth="3" />
      <path
        d="M33 38 L38 43 L48 31"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Round 1 → round 2, the strip at the top of round-two results (§7.10).
 * The numerals are part of the drawing, so the caller states the rounds in
 * words beside it.
 */
export function RoundJourneyArt({ className }: ArtProps): React.JSX.Element {
  return (
    <svg {...svgProps("0 0 120 60", className)}>
      <circle
        cx="20"
        cy="30"
        r="16"
        fill="currentColor"
        fillOpacity="0.15"
        stroke="currentColor"
        strokeWidth="3"
      />
      <text
        x="20"
        y="35"
        fontSize="16"
        fontWeight="700"
        fill="currentColor"
        textAnchor="middle"
        style={{ fontFamily: "var(--font-body)" }}
      >
        1
      </text>
      <path d="M40 30 H78" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeDasharray="1 8" />
      <path
        d="M72 22 L82 30 L72 38"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="100" cy="30" r="18" fill="currentColor" stroke="currentColor" strokeWidth="3" />
      <text
        x="100"
        y="36"
        fontSize="18"
        fontWeight="700"
        textAnchor="middle"
        style={{ fontFamily: "var(--font-body)", fill: "var(--ce-surface)" }}
      >
        2
      </text>
    </svg>
  );
}
