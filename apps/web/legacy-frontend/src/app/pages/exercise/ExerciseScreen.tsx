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
 * What it provides is the three things a projector screen needs — the marker,
 * one `h1`, and a readable measure — and nothing else.
 *
 * Visual system: `docs/design/class-exercise/DESIGN.md` ("The invitation
 * desk"). The wrapper carries `.ce-root`, which scopes every `--ce-*` token
 * (`src/styles/exercise.css`) to the exercise so no CBA screen changes. The
 * header follows §6.1: compact CPP logo, the quiet fictional-data ribbon
 * (§6.2), one `h1` in the display face, one lead line, an optional aside, and
 * on a team's pages the team's status line under them.
 * Shared pieces pages compose live in `./desk` (see its README).
 */
import * as React from "react";
import { MotionConfig } from "motion/react";

import { BrandLogo } from "../../components/BrandLogo";

// Imported from the module, not from `components/provenance`'s barrel. The
// barrel re-exports `MetricDrilldownSheet`, which imports `@/lib/api` — so a
// barrel import would give every exercise screen a path to the CBA client,
// which is exactly the edge ADR-0025 D1 forbids, and would pull it into the
// exercise chunks besides. `SyntheticDataMarker` itself reaches only `clsx`,
// `tailwind-merge` and an icon.
import { SyntheticDataBanner } from "../../components/provenance/SyntheticDataMarker";
import { Notice } from "./desk/Notice";

/** The ribbon's bold prefix on every exercise screen (DESIGN.md §6.2, ruling 1). */
export const EXERCISE_RIBBON_LABEL = "Fictional data —";

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

export interface ExerciseScreenProps {
  /** The page name, as the one `h1`. */
  readonly title: string;
  /** One line under the title, when the screen needs one. */
  readonly intro?: React.ReactNode;
  /** Shown at the top right of the header: the page's one way back. */
  readonly aside?: React.ReactNode;
  /**
   * The team's status line (§6.1, issue #321), between the header and the
   * body, so it is in the same place on every team page. Team pages pass
   * `<TeamStatusBand />`; the opening screen and the instructor page pass
   * nothing, because neither is a team's page.
   */
  readonly status?: React.ReactNode;
  readonly children: React.ReactNode;
}

export function ExerciseScreen({
  title,
  intro,
  aside,
  status,
  children,
}: ExerciseScreenProps): React.JSX.Element {
  const heading = React.useRef<HTMLHeadingElement>(null);

  // §8.5: a route change moves focus to the h1. After a link click the link
  // unmounts and focus falls to <body>; only then is it moved, so a screen
  // never takes focus away from a control someone is using.
  React.useEffect(() => {
    const active = document.activeElement;
    if (active === null || active === document.body) {
      heading.current?.focus();
    }
  }, []);

  return (
    <div className="ce-root min-h-screen">
      <MotionConfig reducedMotion="user">
        <main className="ce-container flex flex-col gap-ce-5 pt-ce-5 pb-ce-7 md:gap-ce-6 md:pt-ce-8">
          <div className="flex flex-col gap-ce-4">
            {/* The shared BrandLogo is also the CBA portals'; the plate is the
                exercise's own wrapper, lit only in dark mode (exercise.css). */}
            <span data-slot="ce-logo" className="ce-logo">
              <BrandLogo compact />
            </span>
            <SyntheticDataBanner
              tone="quiet"
              label={EXERCISE_RIBBON_LABEL}
              reason={EXERCISE_SYNTHETIC_REASON}
            />
          </div>
          <header className="flex flex-wrap items-start justify-between gap-ce-4">
            <div className="flex min-w-0 flex-col gap-ce-2">
              <h1 ref={heading} tabIndex={-1} className="ce-type-h1 text-ce-ink">
                {title}
              </h1>
              {intro === undefined ? null : (
                <p className="ce-type-lead ce-measure text-ce-ink-muted">{intro}</p>
              )}
            </div>
            {aside === undefined ? null : (
              <div className="ce-type-body text-ce-ink-muted">{aside}</div>
            )}
          </header>
          {status}
          {children}
        </main>
      </MotionConfig>
    </div>
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
 * `message` is rendered verbatim. It is one plain sentence written for a
 * projector; capitalising, truncating or re-wording it here would be putting
 * words in Ann's mouth.
 */
export function ExerciseNotice({
  message,
  tone = "calm",
  children,
  id,
}: {
  readonly message: string;
  readonly tone?: "calm" | "problem";
  readonly children?: React.ReactNode;
  /** Lets another element point at this notice with `aria-describedby`. */
  readonly id?: string;
}): React.JSX.Element {
  // The desk Notice (DESIGN.md §6.20) is the one notice; this keeps the
  // signature every screen already calls.
  return <Notice id={id} tone={tone} message={message} action={children} />;
}

/** The loading state, stated rather than left blank (DESIGN.md's state table). */
export function ExerciseLoading({ what }: { readonly what: string }): React.JSX.Element {
  return (
    <p role="status" className="ce-type-body text-ce-ink-muted">
      Loading {what}…
    </p>
  );
}
