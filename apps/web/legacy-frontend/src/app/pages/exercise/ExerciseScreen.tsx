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
 * Type is sized for "a projector at classroom distance" (§16, which gives no
 * numbers). The scale here matches `ExerciseResultsChart`'s, which chose 20px
 * axis labels and 26px values for the same room: `text-4xl` headings, `text-xl`
 * body, `text-2xl` on the controls a team actually operates.
 */
import * as React from "react";

// Imported from the module, not from `components/provenance`'s barrel. The
// barrel re-exports `MetricDrilldownSheet`, which imports `@/lib/api` — so a
// barrel import would give every exercise screen a path to the CBA client,
// which is exactly the edge ADR-0025 D1 forbids, and would pull it into the
// exercise chunks besides. `SyntheticDataMarker` itself reaches only `clsx`,
// `tailwind-merge` and an icon.
import { SyntheticDataBanner } from "../../components/provenance/SyntheticDataMarker";

/**
 * Why every exercise screen is synthetic, in one sentence.
 *
 * One constant rather than a sentence per screen: it is the same fact on all
 * of them, and `GET /v1/exercise` reports `synthetic_data: true` as a constant
 * of the scope rather than a property of a dataset.
 */
export const EXERCISE_SYNTHETIC_REASON =
  "Every profile and event in this exercise is made up. No real student appears, and nothing here is connected to university records.";

export interface ExerciseScreenProps {
  /** The page name, as the one `h1`. */
  readonly title: string;
  /** One line under the title, when the screen needs one. */
  readonly intro?: React.ReactNode;
  /** Shown at the top right of the header — e.g. which team and data file. */
  readonly aside?: React.ReactNode;
  readonly children: React.ReactNode;
}

export function ExerciseScreen({
  title,
  intro,
  aside,
  children,
}: ExerciseScreenProps): React.JSX.Element {
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <SyntheticDataBanner reason={EXERCISE_SYNTHETIC_REASON} />
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl leading-tight font-bold text-slate-900 dark:text-slate-50">
            {title}
          </h1>
          {intro === undefined ? null : (
            <p className="mt-2 text-xl text-slate-600 dark:text-slate-300">{intro}</p>
          )}
        </div>
        {aside === undefined ? null : (
          <div className="text-xl text-slate-600 dark:text-slate-300">{aside}</div>
        )}
      </header>
      {children}
    </main>
  );
}

/**
 * A refusal, or any other failure, as a calm state on the screen.
 *
 * The exercise's refusals are not errors in the usual sense: "the instructor
 * has not opened this event yet" and "the course owner has not confirmed the
 * results rule" are both the product working, and both arrive as a 409. PR
 * #190 asks for exactly this: render the sentence as a state, not as an error
 * toast. So the treatment is a bordered panel with the server's own sentence
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
  const palette =
    tone === "problem"
      ? "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100"
      : "border-slate-300 bg-slate-50 text-slate-800 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100";
  return (
    <div
      id={id}
      role="status"
      data-slot="exercise-notice"
      className={`rounded-lg border-2 px-5 py-4 text-xl leading-snug ${palette}`}
    >
      <p>{message}</p>
      {children === undefined ? null : <div className="mt-3">{children}</div>}
    </div>
  );
}

/** The loading state, stated rather than left blank (DESIGN.md's state table). */
export function ExerciseLoading({ what }: { readonly what: string }): React.JSX.Element {
  return (
    <p role="status" className="text-xl text-slate-600 dark:text-slate-300">
      Loading {what}…
    </p>
  );
}
