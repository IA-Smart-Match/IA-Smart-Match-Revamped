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
  "cursor-not-allowed self-start rounded-lg border-2 border-slate-300 px-6 py-3 text-xl font-semibold text-slate-500 dark:border-slate-600 dark:text-slate-400";

/**
 * The major on file, shown for the student to confirm rather than asked for.
 * The value itself is not drawn: the mock-up has no profile behind it, and a
 * made-up major on a projector reads as a real one.
 */
function MajorConfirm(): React.JSX.Element {
  return (
    <section
      data-slot="exercise-card-major-confirm"
      className="rounded-lg border-2 border-slate-200 bg-white px-5 py-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <p className="text-2xl leading-snug font-semibold text-slate-900 dark:text-slate-50">
        Confirm your major
      </p>
      <p className="mt-1 text-lg text-slate-600 dark:text-slate-300">
        This is the major already on file for you. Year and the events you have been to are
        on file too, so nothing else here asks for them.
      </p>
      <div
        aria-hidden="true"
        className="mt-3 flex h-10 items-center rounded-md border-2 border-dashed border-slate-300 px-3 text-lg text-slate-500 dark:border-slate-600 dark:text-slate-400"
      >
        Your major, as it is on file
      </div>
      {/*
        Inert on purpose, like the button at the foot of the card: there is
        nothing behind it, and its label says so.
      */}
      <button type="button" disabled aria-disabled="true" className={`mt-3 ${INERT_BUTTON_CLASS}`}>
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
      className="rounded-lg border-2 border-slate-200 bg-white px-5 py-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <p className="text-2xl leading-snug font-semibold text-slate-900 dark:text-slate-50">
        {question.prompt}
      </p>
      <p className="mt-1 text-lg text-slate-600 dark:text-slate-300">{question.example}</p>
      {/*
        A blank line drawn, not an input: an input invites typing, and typing
        into a mock-up invites the belief that something was kept.
      */}
      <div
        aria-hidden="true"
        className="mt-3 h-10 rounded-md border-2 border-dashed border-slate-300 dark:border-slate-600"
      />
    </li>
  );
}

export function ProfileCardMockup(): React.JSX.Element {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10">
      <SyntheticDataBanner reason="This is a mock-up of the card, shown to the class. It asks nobody anything, keeps no answers, and is not connected to any list." />
      <header>
        <h1 className="text-4xl leading-tight font-bold text-slate-900 dark:text-slate-50">
          Two quick questions
        </h1>
        <p className="mt-2 text-xl text-slate-600 dark:text-slate-300">
          Answering these would let us suggest events worth your evening.
        </p>
      </header>
      <MajorConfirm />
      <ol className="flex flex-col gap-4">
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
    </main>
  );
}
