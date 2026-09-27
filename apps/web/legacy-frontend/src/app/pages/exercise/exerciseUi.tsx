/**
 * The invitation desk's small parts: buttons, chips, skeletons, the ruled
 * figures band, and the two media hooks every motion decision reads.
 *
 * Contract: `docs/design/class-exercise/DESIGN.md` §3 (tokens), §5 (motion),
 * §6 (components). The visual rules live in `src/styles/exercise.css` as
 * `ce-*` classes; this module only picks between them, so a screen never
 * spells a colour or a size itself.
 *
 * **Reduced motion is decided once, here.** CSS animations have their own
 * `prefers-reduced-motion` branch in the stylesheet. Motion that JavaScript
 * drives (the seat fill, the count-up, the confirm window's helper line, the
 * list re-order) asks {@link usePrefersReducedMotion}, which re-reads the
 * media query per mount and listens for changes, so a test can set it and a
 * classroom machine can flip it mid-lesson.
 */
import * as React from "react";
import { Loader2 } from "lucide-react";

/** `(prefers-reduced-motion: reduce)`, live. `false` where there is no `matchMedia`. */
export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}

/** Below the 768 layout: the 390 phone column (§3.8). */
export function useIsNarrow(): boolean {
  return useMediaQuery("(max-width: 767px)");
}

function useMediaQuery(query: string): boolean {
  const read = React.useCallback((): boolean => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  }, [query]);
  const [matches, setMatches] = React.useState(read);
  React.useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    const list = window.matchMedia(query);
    const onChange = (): void => setMatches(list.matches);
    onChange();
    list.addEventListener?.("change", onChange);
    return () => list.removeEventListener?.("change", onChange);
  }, [query]);
  return matches;
}

export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";

/**
 * A §6.3 button's classes. One primary per region is the caller's job; this
 * only makes the variants look like the table says.
 */
export function ceButton(variant: ButtonVariant, extra = ""): string {
  return `ce-btn ce-btn-${variant}${extra === "" ? "" : ` ${extra}`}`;
}

/** The 16px leading spinner for a pending button. Decorative: the label changes too. */
export function Spinner({ className = "" }: { readonly className?: string }): React.JSX.Element {
  return <Loader2 aria-hidden="true" className={`ce-spin size-4 shrink-0 ${className}`} />;
}

export type ChipTone = "neutral" | "primary" | "avocado" | "gold" | "outline";

const CHIP_TONES: Readonly<Record<ChipTone, string>> = {
  neutral: "bg-ce-sunk text-ce-ink",
  primary: "bg-ce-primary-tint text-ce-primary-tint-ink",
  avocado: "bg-ce-avocado-tint text-ce-ink",
  gold: "bg-ce-gold text-ce-gold-on",
  outline: "border-2 border-ce-line-strong text-ce-ink",
};

/** A pill: icon plus words, never colour alone (§6.8, §8.3). */
export function Chip({
  tone = "neutral",
  icon,
  children,
  className = "",
  slot,
}: {
  readonly tone?: ChipTone;
  readonly icon?: React.ReactNode;
  readonly children: React.ReactNode;
  readonly className?: string;
  readonly slot?: string;
}): React.JSX.Element {
  return (
    <span data-slot={slot} className={`ce-chip ${CHIP_TONES[tone]} ${className}`}>
      {icon}
      <span>{children}</span>
    </span>
  );
}

/** A content-shaped block for a skeleton (§6.21). Always decorative. */
export function SkeletonBlock({ className = "" }: { readonly className?: string }): React.JSX.Element {
  return <span aria-hidden="true" className={`ce-skeleton block ${className}`} />;
}

/**
 * A number that counts from 0 once per mount (`ce-count-up`, 700ms).
 *
 * Off unless `play` is set, and off under reduced motion or where there is
 * no `requestAnimationFrame`: the final number is always what renders then.
 * It never re-runs on a re-render, because `play` is read on mount only.
 */
export function useCountUp(value: number, play: boolean): number {
  const reduced = usePrefersReducedMotion();
  const animate = React.useRef(
    play && !reduced && typeof window !== "undefined" && typeof window.requestAnimationFrame === "function",
  );
  const [shown, setShown] = React.useState(animate.current ? 0 : value);
  React.useEffect(() => {
    if (!animate.current) {
      setShown(value);
      return undefined;
    }
    animate.current = false;
    const started = performance.now();
    let frame = 0;
    const tick = (now: number): void => {
      const t = Math.min(1, (now - started) / 700);
      // --ce-ease-out, approximated: fast start, long settle.
      const eased = 1 - Math.pow(1 - t, 4);
      setShown(Math.round(value * eased));
      if (t < 1) {
        frame = window.requestAnimationFrame(tick);
      }
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [value]);
  return shown;
}

export interface Figure {
  readonly label: string;
  readonly value: number;
}

/**
 * The ruled figures band (§6.15, §6.19): three columns split by 1px rules,
 * a display numeral over a label. A band, not cards — no surface, no shadow.
 *
 * The label comes first in the DOM, so the text reads "Seats in the room60"
 * and a screen reader hears the label before its number; the numeral is
 * drawn above it with `order`.
 */
export function FiguresBand({
  figures,
  slot,
  countUp = false,
  size = "display",
}: {
  readonly figures: readonly Figure[];
  readonly slot?: string;
  /** Count up once on mount; only the results reveal and a fresh refresh do. */
  readonly countUp?: boolean;
  readonly size?: "display" | "compact";
}): React.JSX.Element {
  return (
    <dl
      data-slot={slot}
      className="grid border-y border-ce-line-strong py-5"
      style={{ gridTemplateColumns: `repeat(${figures.length}, minmax(0, 1fr))` }}
    >
      {figures.map((figure, index) => (
        <FigureCell
          key={figure.label}
          figure={figure}
          first={index === 0}
          countUp={countUp}
          size={size}
        />
      ))}
    </dl>
  );
}

function FigureCell({
  figure,
  first,
  countUp,
  size,
}: {
  readonly figure: Figure;
  readonly first: boolean;
  readonly countUp: boolean;
  readonly size: "display" | "compact";
}): React.JSX.Element {
  const shown = useCountUp(figure.value, countUp);
  return (
    <div
      className={`flex min-w-0 flex-col px-3 md:px-6 ${
        first ? "pl-0 md:pl-0" : "border-l border-ce-line-strong"
      }`}
    >
      <dt className="ce-label order-2 mt-1 text-ce-ink">{figure.label}</dt>
      <dd
        className={`order-1 text-ce-primary ${
          size === "display" ? "ce-display" : "ce-h1 ce-num"
        }`}
      >
        {shown}
      </dd>
    </div>
  );
}

/** A visually hidden live region's text. */
export const SR_ONLY = "sr-only";
