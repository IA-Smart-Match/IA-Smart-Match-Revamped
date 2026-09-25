/**
 * The "five quick questions" profile card — one screen, for the instructor
 * to show.
 *
 * Requirements row "Asking for more": *"A one-screen mock-up of the 'five
 * quick questions' card for the instructor to show."* It is what a team is
 * imagining when it picks one of the three ways to ask the profiles it
 * invited to complete a card, so the class can see the thing being asked for
 * before arguing about how to ask for it.
 *
 * **Where the five come from.** The requirements describe a completed card as
 * "stated interests and career goals" and never list five questions. Rather
 * than invent three more, the five here are the five fields the documents
 * already name as a profile's own: design spec §2's `exercise_profile`
 * columns `major`, `class_year`, `stated_interests`, `career_goal` and
 * `past_event_keys` — which are exactly what the four adjustable factors and
 * the tie-break read. If Ann's card turns out to ask something else, this
 * screen changes and nothing else does.
 *
 * **What it is not.** It is a mock-up, and says so in as many words. There is
 * no form, no request, nothing is stored, and the one button is inert and
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
 * The five questions, in the order a card would ask them: who you are, then
 * what you want, then where you have been.
 *
 * The `field` strings are the design spec's column names rather than a
 * vocabulary of answers. The data file's columns and the values they may take
 * are settled by Ann's workbook of 2026-09-24, but they live on the server, so
 * this screen shows the shape of a card and never a fixed list of majors or
 * years. OQ-CE-11 — what
 * the five questions actually are — is open too, so the five below are a
 * mock-up's stand-in until Ann confirms them.
 */
const CARD_QUESTIONS: readonly CardQuestion[] = [
  {
    field: "major",
    prompt: "What are you majoring in?",
    example: "One major, the way it appears on your programme.",
  },
  {
    field: "class_year",
    prompt: "What year are you in?",
    example: "The year your programme has you in.",
  },
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
  {
    field: "past_event_keys",
    prompt: "Which of these events have you been to before?",
    example: "Tick the ones you remember. It is fine to tick none.",
  },
];

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
          Five quick questions
        </h1>
        <p className="mt-2 text-xl text-slate-600 dark:text-slate-300">
          Answering these would let us suggest events worth your evening.
        </p>
      </header>
      <ol className="flex flex-col gap-4">
        {CARD_QUESTIONS.map((question) => (
          <QuestionRow key={question.field} question={question} />
        ))}
      </ol>
      {/*
        Inert on purpose, and disabled so it cannot be pressed even by
        accident. Its label is the honest one: there is nothing behind it.
      */}
      <button
        type="button"
        disabled
        aria-disabled="true"
        className="cursor-not-allowed self-start rounded-lg border-2 border-slate-300 px-6 py-3 text-xl font-semibold text-slate-500 dark:border-slate-600 dark:text-slate-400"
      >
        Mock-up only — this button does nothing
      </button>
    </main>
  );
}
