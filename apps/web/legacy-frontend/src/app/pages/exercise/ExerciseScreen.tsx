/**
 * The frame every exercise screen sits in.
 *
 * Design spec §16 asks for `SyntheticDataMarker` on *every* screen, and the
 * requirements are emphatic about why: "Every row is fictional; no real
 * student appears." A rule that says "every screen" is kept by a component
 * that renders the marker whether or not a page remembers to, which is what
 * this is — six screens cannot each be trusted to carry it, and the seventh
 * one somebody adds later certainly cannot.
 *
 * It is deliberately *not* a portal shell. ADR-0025 D1 and §16 both forbid the
 * CBA shell and `SessionGate` here: there is no sidebar, no navigation built
 * from roles, no profile summary and no sign-out, because there is no account.
 * What it provides is what a projector screen needs — the marker, the CPP
 * logo, one `h1`, one lead line and a readable measure — and nothing else.
 *
 * **The invitation desk** (`docs/design/class-exercise/DESIGN.md` §6.1): an
 * Eggwhite page, the quiet "Fictional data —" ribbon (§6.2, owner ruling
 * 2026-09-26), a Transducer `h1` at 48px and a 22px muted lead, content capped
 * at 1152px with the §3.8 side margins. Every colour and size is a `ce-*`
 * token from `src/styles/exercise.css`.
 */
import * as React from "react";
import { CircleCheck, Info, TriangleAlert } from "lucide-react";
import { MotionConfig } from "motion/react";

import { BrandLogo } from "../../components/BrandLogo";
// Imported from the module, not from `components/provenance`'s barrel. The
// barrel re-exports `MetricDrilldownSheet`, which imports `@/lib/api` — so a
// barrel import would give every exercise screen a path to the CBA client,
// which is exactly the edge ADR-0025 D1 forbids, and would pull it into the
// exercise chunks besides. `SyntheticDataMarker` itself reaches only `clsx`,
// `tailwind-merge` and an icon.
import { SyntheticDataBanner } from "../../components/provenance/SyntheticDataMarker";
import { SkeletonBlock, usePrefersReducedMotion } from "./exerciseUi";

/**
 * Why every exercise screen is synthetic, in one sentence.
 *
 * One constant rather than a sentence per screen: it is the same fact on all
 * of them, and `GET /v1/exercise` reports `synthetic_data: true` as a constant
 * of the scope rather than a property of a dataset.
 *
 * Ann's wording rule (2026-09-25, email reply): describe the data only as
 * fictional profiles shaped by overall survey percentages, and never mention
 * real student data or individual responses.
 */
export const EXERCISE_SYNTHETIC_REASON =
  "All student profiles are fictional, shaped by overall survey percentages.";

/** The ribbon's bold prefix on exercise screens (DESIGN.md §6.2, §11 item 1). */
export const EXERCISE_RIBBON_LABEL = "Fictional data —";

export interface ExerciseScreenProps {
  /** The page name, as the one `h1`. */
  readonly title: string;
  /** One line under the title, when the screen needs one. */
  readonly intro?: React.ReactNode;
  /** Shown at the top right of the header — e.g. which team and data file. */
  readonly aside?: React.ReactNode;
  /** Centre the header, for the instructor's passcode card (§7.11). */
  readonly centered?: boolean;
  readonly children: React.ReactNode;
}

export function ExerciseScreen({
  title,
  intro,
  aside,
  centered = false,
  children,
}: ExerciseScreenProps): React.JSX.Element {
  const reduced = usePrefersReducedMotion();
  const headingRef = React.useRef<HTMLHeadingElement>(null);

  // §8.5: a route change moves focus to the `h1`. Once per mount — never on
  // a re-render, which would pull focus out of a box a team is typing in.
  React.useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, []);

  return (
    <MotionConfig reducedMotion={reduced ? "always" : "never"}>
      <div className="ce-root min-h-screen">
        <main
          data-slot="exercise-screen"
          className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 px-4 pt-6 pb-16 md:gap-8 md:px-8 md:pt-8 lg:px-10 xl:px-16"
        >
          <SyntheticDataBanner
            tone="quiet"
            label={EXERCISE_RIBBON_LABEL}
            reason={EXERCISE_SYNTHETIC_REASON}
          />
          <header
            className={`flex flex-col gap-4 ${
              centered ? "items-center text-center" : "md:flex-row md:items-start md:justify-between"
            }`}
          >
            <div className={`flex min-w-0 flex-col gap-3 ${centered ? "items-center" : ""}`}>
              <BrandLogo
                compact
                className="w-[132px] dark:rounded-md dark:bg-white dark:px-2 dark:py-1"
              />
              <h1
                ref={headingRef}
                tabIndex={-1}
                className="ce-h1 mt-2 text-ce-ink md:mt-4"
                data-slot="exercise-title"
              >
                {title}
              </h1>
              {intro === undefined ? null : (
                <p className="ce-lead max-w-[64ch] text-ce-muted">{intro}</p>
              )}
            </div>
            {aside === undefined ? null : (
              <div className="ce-body flex shrink-0 flex-wrap items-center gap-3 text-ce-muted md:pt-10">
                {aside}
              </div>
            )}
          </header>
          {children}
        </main>
      </div>
    </MotionConfig>
  );
}

/**
 * A refusal, or any other failure, as a calm state on the screen.
 *
 * The exercise's refusals are not errors in the usual sense: "the instructor
 * has not opened this event yet" and "the course owner has not confirmed the
 * results rule" are both the product working, and both arrive as a 409. PR
 * #190 asks for exactly this: render the sentence as a state, not as an error
 * toast. So the treatment is a composed card with the server's own sentence
 * and, optionally, the one action that would move it along — never a red
 * alert, never a retry button for something retrying will not fix.
 *
 * DESIGN.md §6.20's three tones: **calm** (a refusal: white card, `Info` in
 * primary), **problem** (transport: a 2px danger outline and
 * `TriangleAlert`), **done** (success: avocado-tint wash and `CircleCheck`).
 * No left border stripe on any of them. Each enters with `ce-notice-in`.
 *
 * `message` is rendered verbatim. It is one plain sentence written for a
 * projector; capitalising, truncating or re-wording it here would be putting
 * words in Ann's mouth.
 */
export function ExerciseNotice({
  message,
  tone = "calm",
  children,
  id,
  art,
}: {
  readonly message: string;
  readonly tone?: "calm" | "problem" | "done";
  readonly children?: React.ReactNode;
  /** Lets another element point at this notice with `aria-describedby`. */
  readonly id?: string;
  /** One spot illustration, only for an empty or locked state (§4). */
  readonly art?: React.ReactNode;
}): React.JSX.Element {
  const surface =
    tone === "problem"
      ? "bg-ce-surface border-2 border-ce-danger"
      : tone === "done"
        ? "bg-ce-avocado-tint"
        : "ce-card";
  const icon =
    tone === "problem" ? (
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-6 shrink-0 text-ce-danger" />
    ) : tone === "done" ? (
      <CircleCheck aria-hidden="true" className="mt-0.5 size-6 shrink-0 text-ce-primary" />
    ) : (
      <Info aria-hidden="true" className="mt-0.5 size-6 shrink-0 text-ce-primary" />
    );
  return (
    <div
      id={id}
      role="status"
      data-slot="exercise-notice"
      data-tone={tone}
      className={`ce-notice-in flex items-start gap-4 rounded-[14px] px-5 py-4 md:px-6 md:py-5 ${surface}`}
    >
      {art === undefined ? icon : <div className="hidden shrink-0 text-ce-primary sm:block">{art}</div>}
      <div className="flex min-w-0 flex-col gap-3">
        <p className="ce-body text-ce-ink">{message}</p>
        {children === undefined ? null : <div>{children}</div>}
      </div>
    </div>
  );
}

/** The skeleton shapes a screen can ask for (§6.21). */
export type LoadingShape = "list" | "cards" | "tiles" | "block";

/**
 * The loading state: a content-shaped skeleton, plus the stated sentence.
 *
 * The parent contract's state table wants loading *stated*, so the words
 * "Loading the list…" stay, in a visually hidden `role="status"`; the
 * breathing blocks are decorative (`ce-skeleton`, static under reduced
 * motion).
 */
export function ExerciseLoading({
  what,
  shape = "block",
}: {
  readonly what: string;
  readonly shape?: LoadingShape;
}): React.JSX.Element {
  return (
    <div data-slot="exercise-loading" className="flex flex-col gap-4">
      <p role="status" className="sr-only">
        Loading {what}…
      </p>
      <LoadingSkeleton shape={shape} />
    </div>
  );
}

function LoadingSkeleton({ shape }: { readonly shape: LoadingShape }): React.JSX.Element {
  if (shape === "tiles") {
    return (
      <div aria-hidden="true" className="grid grid-cols-3 gap-4 sm:flex sm:flex-wrap">
        {[1, 2, 3, 4, 5, 6].map((key) => (
          <SkeletonBlock key={key} className="h-24 w-full rounded-[14px] sm:size-28" />
        ))}
      </div>
    );
  }
  if (shape === "cards") {
    return (
      <div aria-hidden="true" className="flex flex-col gap-4">
        <SkeletonBlock className="h-36 w-full rounded-[14px]" />
        <SkeletonBlock className="h-36 w-full rounded-[14px]" />
        {[1, 2, 3, 4].map((key) => (
          <SkeletonBlock key={key} className="h-5 w-1/2" />
        ))}
      </div>
    );
  }
  if (shape === "list") {
    return (
      <div aria-hidden="true" className="ce-card flex flex-col gap-4 p-5 md:p-6">
        <SkeletonBlock className="h-7 w-48" />
        {[1, 2, 3, 4, 5, 6, 7, 8].map((key) => (
          <div key={key} className="flex items-center gap-4">
            <SkeletonBlock className="size-8 shrink-0 rounded-md" />
            <SkeletonBlock className="h-4 w-1/3" />
            <SkeletonBlock className="h-4 w-1/2" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div aria-hidden="true" className="ce-card flex flex-col gap-3 p-5 md:p-6">
      <SkeletonBlock className="h-7 w-56" />
      <SkeletonBlock className="h-4 w-3/4" />
      <SkeletonBlock className="h-4 w-2/3" />
    </div>
  );
}
