/**
 * The profile card — one screen, for the instructor to show.
 *
 * Requirements row "Asking for more": *"A one-screen mock-up of the 'five
 * quick questions' card for the instructor to show."* It is what a team is
 * imagining when it picks one of the three ways to ask the profiles it
 * invited to complete a card, so the class can see the thing being asked for
 * before arguing about how to ask for it.
 *
 * **What the card asks.** OQ-CE-11 closed 2026-09-25 (Ann Wang, email reply to
 * the team's question list): *"please ask only for interests and career goal.
 * Major and year are already on file, and past events are recorded by the app
 * when students attend, so students should not have to enter them again. On
 * activation, students just confirm their major."* So the card asks exactly
 * two questions — design spec §2's `stated_interests` and `career_goal` — and
 * shows the major on file with a confirm step. Year and past events are not
 * asked.
 *
 * **What it is not.** It is a mock-up, and says so in as many words. There is
 * no form, no request, nothing is stored, and every button is inert and
 * labelled inert, so nobody in the room can come away believing a card was
 * filed. The profile row's withheld column — the hidden "true" interests of
 * ADR-0025 D6 — is neither asked for nor shown here; it leaves the server for
 * nobody, least of all for the person it describes.
 *
 * It renders no rank, no weight, and no number of any kind (ADR-0025 D8), it
 * wraps itself in no portal shell and sits behind no session gate, and the
 * type is sized for the back of Dr. Lin's classroom (design spec §16).
 */
import * as React from "react";

// From the module rather than the `components/provenance` barrel: the barrel
// re-exports `MetricDrilldownSheet`, which imports `@/lib/api`, so importing
// it would give this screen an import path to the CBA client — the edge
// ADR-0025 D1 forbids. Changed by CE-MOUNT, which added the test that fails
// on it; nothing this screen renders changes.
import { SyntheticDataBanner } from "../../components/provenance/SyntheticDataMarker";
import { EXERCISE_RIBBON_LABEL, EXERCISE_SYNTHETIC_REASON } from "./ExerciseScreen";

interface CardQuestion {
  /** The `exercise_profile` column this question would fill (design spec §2). */
  readonly field: string;
  /** The question, in the words a profile would read. */
  readonly prompt: string;
  /** One line under the question, so the class can see what an answer looks like. */
  readonly example: string;
}

/**
 * The two questions, in the order a card would ask them: what you want to
 * hear about, then where you want to end up.
 *
 * The `field` strings are the design spec's column names rather than a
 * vocabulary of answers. The values a column may take are settled by Ann's
 * workbook of 2026-09-24, but they live on the server, so this screen shows
 * the shape of a card and never a fixed list of topics or goals. The card's
 * contents are confirmed (OQ-CE-11 closed 2026-09-25); the screen stays a
 * mock-up of the card, not the card.
 */
const CARD_QUESTIONS: readonly CardQuestion[] = [
  {
    field: "stated_interests",
    prompt: "What topics are you interested in?",
    example: "Pick as many as you like, or add your own.",
  },
  {
    field: "career_goal",
    prompt: "What kind of work do you want to end up doing?",
    example: "A sentence is plenty.",
  },
];

const INERT_BUTTON_CLASS =
  "ce-meta w-full cursor-not-allowed rounded-[10px] bg-ce-sunk px-4 py-3 text-center text-ce-muted";

/** The page's `h1` and caption (DESIGN.md §7.6, §11.1). */
const PAGE_TITLE = "What a profile would be asked";
const PAGE_CAPTION =
  "Major and year are already on file, and past events are recorded when someone attends. So the card asks only two things, and asks the person to confirm their major.";
/**
 * What the ribbon used to say on this page. The ribbon now carries the fixed
 * exercise sentence (DESIGN.md §6.2), so this moved to the caption.
 */
const MOCKUP_NOTE =
  "This is a mock-up of the card, shown to the class. It asks nobody anything, keeps no answers, and is not connected to any list.";

/**
 * The major on file, shown for the student to confirm rather than asked for.
 * The value itself is not drawn: the mock-up has no profile behind it, and a
 * made-up major on a projector reads as a real one.
 */
function MajorConfirm(): React.JSX.Element {
  return (
    <section
      data-slot="exercise-card-major-confirm"
      className="flex flex-col gap-2 border-t border-ce-line pt-5"
    >
      <h3 className="ce-h3 text-ce-ink">Confirm your major</h3>
      <p className="ce-meta text-ce-muted">
        This is the major already on file for you. Year and the events you have been to are
        on file too, so nothing else here asks for them.
      </p>
      <div
        aria-hidden="true"
        className="ce-meta flex min-h-11 items-center justify-center rounded-[10px] border-2 border-dashed border-ce-line-strong px-3 text-ce-muted"
      >
        Your major, as it is on file
      </div>
      {/*
        Inert on purpose, like the button at the foot of the card: there is
        nothing behind it, and its label says so.
      */}
      <button type="button" disabled aria-disabled="true" className={INERT_BUTTON_CLASS}>
        Confirm — mock-up only, this button does nothing
      </button>
    </section>
  );
}

function QuestionRow({ question }: { question: CardQuestion }): React.JSX.Element {
  return (
    <li
      data-slot="exercise-card-question"
      data-field={question.field}
      className="flex flex-col gap-1 border-t border-ce-line pt-5"
    >
      <h3 className="ce-h3 text-ce-ink">{question.prompt}</h3>
      <p className="ce-meta text-ce-muted">{question.example}</p>
      {/*
        A blank line drawn, not an input: an input invites typing, and typing
        into a mock-up invites the belief that something was kept.
      */}
      <div aria-hidden="true" className="mt-6 border-b-2 border-dashed border-ce-line-strong" />
    </li>
  );
}

/**
 * The page (DESIGN.md §6.22, §7.6): a phone-sized card, 360px wide, on the
 * eggwhite desk, with a "Mock-up only" chip in its corner, and a caption
 * column beside it on desktop (above it on a phone).
 */
export function ProfileCardMockup(): React.JSX.Element {
  return (
    <div className="ce-root min-h-screen">
      <main className="mx-auto flex w-full max-w-[1280px] flex-col gap-8 px-4 pt-6 pb-16 md:px-8 md:pt-8 lg:px-10 xl:px-16">
        {/* The fixed ribbon every exercise screen carries (DESIGN.md §6.2). */}
        <SyntheticDataBanner
          tone="quiet"
          label={EXERCISE_RIBBON_LABEL}
          reason={EXERCISE_SYNTHETIC_REASON}
        />
        <div className="flex flex-col items-center gap-8 lg:flex-row lg:items-start lg:justify-center lg:gap-16">
          <header className="flex w-full max-w-[360px] flex-col gap-4 lg:pt-4">
            <h1 className="ce-h1 text-ce-ink">{PAGE_TITLE}</h1>
            <p className="ce-lead text-ce-muted md:text-xl">{PAGE_CAPTION}</p>
            <p className="ce-lead text-ce-muted md:text-xl">{MOCKUP_NOTE}</p>
          </header>
          <article
            aria-label="Profile card mock-up"
            className="ce-card flex w-full max-w-[360px] flex-col gap-5 p-6 shadow-[var(--ce-elev-3)]"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="ce-h2 text-ce-ink">Two quick questions</h2>
              <span className="ce-chip shrink-0 bg-ce-sunk text-ce-ink">Mock-up only</span>
            </div>
            <p className="ce-body -mt-2 text-ce-muted">
              Answering these would let us suggest events worth your evening.
            </p>
            <MajorConfirm />
            <ol className="flex flex-col gap-5">
              {CARD_QUESTIONS.map((question) => (
                <QuestionRow key={question.field} question={question} />
              ))}
            </ol>
            {/*
              Inert on purpose, and disabled so it cannot be pressed even by
              accident. Its label is the honest one: there is nothing behind it.
            */}
            <button type="button" disabled aria-disabled="true" className={INERT_BUTTON_CLASS}>
              Mock-up only — this button does nothing
            </button>
          </article>
        </div>
      </main>
    </div>
  );
}
