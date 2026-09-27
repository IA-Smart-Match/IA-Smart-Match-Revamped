/**
 * The exercise's motion vocabulary (DESIGN.md §5), for Motion components.
 *
 * CSS carries the simple state motions (`ce-press`, `ce-lift`, `ce-skeleton`,
 * `ce-row-join`… in `src/styles/exercise-motion.css`). This module carries
 * the ones that need JavaScript: Motion `initial/animate/exit/transition`
 * bundles by name, the list re-order spring, the count-up, and a
 * reduced-motion hook a component can branch on. Every entry has a
 * reduced-motion form; callers pass the flag rather than each deciding.
 */
import * as React from "react";
import { animate, type MotionProps } from "motion/react";

/** §5 easing tokens, as Motion cubic-bézier arrays. */
export const CE_EASE = {
  out: [0.16, 1, 0.3, 1],
  inOut: [0.65, 0, 0.35, 1],
  exit: [0.7, 0, 0.84, 0],
} as const;

/** `--ce-spring-row`: stiffness 500, damping 40 (≈280ms settle). */
export const CE_SPRING_ROW = { type: "spring", stiffness: 500, damping: 40 } as const;

/** §5 named motion durations, in milliseconds. */
export const CE_MOTION_MS = {
  press: 100,
  lift: 160,
  fadeRise: 240,
  reducedFade: 150,
  rowJoin: 900,
  rowEnter: 200,
  rowLeave: 140,
  sliderSettle: 180,
  listRebuilding: 150,
  cardSave: 220,
  overlapPulse: 600,
  overlapStagger: 30,
  confirmSwap: 150,
  confirmWindow: 5000,
  choiceCommit: 240,
  unlock: 300,
  seatFill: 1800,
  countUp: 700,
  skeleton: 1600,
  noticeIn: 200,
  view: 220,
} as const;

export type CeMotionName =
  | "fade-rise"
  | "notice-in"
  | "card-save"
  | "row-reorder"
  | "row-enter"
  | "row-leave"
  | "choice-dim";

export type CeMotionProps = Pick<MotionProps, "initial" | "animate" | "exit" | "transition" | "layout">;

const seconds = (ms: number): number => ms / 1000;
const reducedFade = { duration: seconds(CE_MOTION_MS.reducedFade) };

/**
 * Motion props for one named motion. Spread onto a `motion.*` element:
 * `<motion.section {...ceMotion("fade-rise", reduced)} />`.
 */
export function ceMotion(name: CeMotionName, reduced: boolean): CeMotionProps {
  switch (name) {
    case "fade-rise":
      return reduced
        ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: reducedFade }
        : {
            initial: { opacity: 0, y: 8 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: seconds(CE_MOTION_MS.fadeRise), ease: CE_EASE.out },
          };
    case "notice-in":
      return reduced
        ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: reducedFade }
        : {
            initial: { opacity: 0, y: 4 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: seconds(CE_MOTION_MS.noticeIn), ease: CE_EASE.out },
          };
    case "card-save":
      return reduced
        ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: reducedFade }
        : {
            initial: { opacity: 0, scale: 0.96 },
            animate: { opacity: 1, scale: 1 },
            transition: { duration: seconds(CE_MOTION_MS.cardSave), ease: CE_EASE.out },
          };
    case "row-reorder":
      // Reduced: instant move plus a 150ms crossfade.
      return reduced
        ? { layout: true, transition: { layout: { duration: 0 }, opacity: reducedFade } }
        : { layout: true, transition: { layout: CE_SPRING_ROW } };
    case "row-enter":
      return reduced
        ? { initial: false, animate: { opacity: 1 } }
        : {
            initial: { opacity: 0 },
            animate: { opacity: 1 },
            transition: { duration: seconds(CE_MOTION_MS.rowEnter), ease: CE_EASE.out },
          };
    case "row-leave":
      return reduced
        ? { exit: { opacity: 0, transition: { duration: 0 } } }
        : {
            exit: {
              opacity: 0,
              height: 0,
              transition: { duration: seconds(CE_MOTION_MS.rowLeave), ease: CE_EASE.exit },
            },
          };
    case "choice-dim":
      return {
        animate: { opacity: 0.55 },
        transition: reduced
          ? reducedFade
          : { duration: seconds(CE_MOTION_MS.choiceCommit), ease: CE_EASE.out },
      };
  }
}

const REDUCE_QUERY = "(prefers-reduced-motion: reduce)";

function readReduced(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(REDUCE_QUERY).matches;
}

/** Whether the viewer asked the OS for reduced motion; follows live changes. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = React.useState(readReduced);
  React.useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    const query = window.matchMedia(REDUCE_QUERY);
    const onChange = (): void => setReduced(query.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

export interface CountUpOptions {
  readonly reduced: boolean;
  readonly durationMs?: number;
  readonly delayMs?: number;
}

/**
 * `ce-count-up`: a whole number that counts from 0 to `target` once per
 * mount (700ms, `--ce-ease-out`). Reduced motion, or a later change of
 * `target`, shows the number at once — a count-up never re-runs.
 */
export function useCountUp(target: number, options: CountUpOptions): number {
  const { reduced, durationMs = CE_MOTION_MS.countUp, delayMs = 0 } = options;
  const [value, setValue] = React.useState(reduced ? target : 0);
  const ran = React.useRef(false);

  React.useEffect(() => {
    if (reduced || ran.current) {
      setValue(target);
      return undefined;
    }
    ran.current = true;
    let finished = false;
    const controls = animate(0, target, {
      duration: seconds(durationMs),
      delay: seconds(delayMs),
      ease: CE_EASE.out,
      onUpdate: (latest) => setValue(Math.round(latest)),
      onComplete: () => {
        finished = true;
        setValue(target);
      },
    });
    return () => {
      controls.stop();
      // A StrictMode double-mount stops the first run; let the second start.
      if (!finished) {
        ran.current = false;
      }
    };
  }, [target, reduced, durationMs, delayMs]);

  return value;
}
