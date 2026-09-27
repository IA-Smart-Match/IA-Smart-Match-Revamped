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
 * **What it is not.** It is a mock-up, and says so in as many words: a
 * "Mock-up only" chip on the card, the sentence in the caption beside it, and
 * on both buttons. There is no form, no request, nothing is stored, and every
 * button is inert and labelled inert, so nobody in the room can come away
 * believing a card was filed. The profile row's withheld column — the hidden
 * "true" interests of ADR-0025 D6 — is neither asked for nor shown here; it
 * leaves the server for nobody, least of all for the person it describes.
 *
 * It renders no rank, no weight, and no number of any kind (ADR-0025 D8), and
 * sits behind no session gate. It lives in the shared exercise frame
 * (`ExerciseScreen`), so it carries the same quiet "Fictional data —" ribbon
 * as every other exercise screen instead of a loud banner of its own.
 *
 * Layout (DESIGN.md §6.22, §7.6, "The invitation desk"): at 1280 a caption
 * column of at most 360px beside a phone-sized 360px card on the eggwhite
 * desk; at 390 the caption above and the card full width. The type roles are
 * sized for the back of Dr. Lin's classroom (design spec §16).
 */
import * as React from "react";

import { ExerciseScreen } from "./ExerciseScreen";

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

/**
 * Inert buttons: sunk fill, muted text, a quiet outline, `not-allowed`. They
 * are `disabled`, so they cannot be pressed even by accident.
 */
const INERT_BUTTON_CLASS =
  "ce-type-label min-h-ce-target w-full cursor-not-allowed rounded-ce-control border-2 border-ce-line bg-ce-surface-sunk px-ce-4 py-ce-2 text-ce-ink-muted";

/**
 * The major on file, shown for the student to confirm rather than asked for.
 * The value itself is not drawn: the mock-up has no profile behind it, and a
 * made-up major on a projector reads as a real one.
 */
function MajorConfirm(): React.JSX.Element {
  return (
    <section
      data-slot="exercise-card-major-confirm"
      className="flex flex-col gap-ce-3 border-t border-ce-line pt-ce-4"
    >
      <h3 className="ce-type-h3 text-ce-ink">Confirm your major</h3>
      <p className="ce-type-meta text-ce-ink-muted">
        This is the major already on file for you. Year and the events you have been to are on
        file too, so nothing else here asks for them.
      </p>
      <div
        aria-hidden="true"
        className="ce-type-body flex min-h-ce-target items-center justify-center rounded-ce-control border-2 border-dashed border-ce-line-strong px-ce-3 text-ce-ink-muted"
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
      className="flex flex-col gap-ce-2"
    >
      <p className="ce-type-h3 text-ce-ink">{question.prompt}</p>
      <p className="ce-type-meta text-ce-ink-muted">{question.example}</p>
      {/*
        A blank line drawn, not an input: an input invites typing, and typing
        into a mock-up invites the belief that something was kept.
      */}
      <div aria-hidden="true" className="mt-ce-5 border-b-2 border-dashed border-ce-line-strong" />
    </li>
  );
}

/** The phone-sized card on the desk (§6.22). */
function PhoneCard(): React.JSX.Element {
  return (
    <article
      data-slot="exercise-profile-card"
      aria-labelledby="exercise-profile-card-title"
      className="ce-fade-rise relative mx-auto flex w-full max-w-[360px] flex-col gap-ce-4 rounded-ce-card bg-ce-surface p-ce-4 shadow-ce-3 md:p-ce-5"
    >
      <span className="ce-type-meta absolute top-ce-4 right-ce-4 rounded-ce-pill bg-ce-surface-sunk px-ce-3 py-ce-1 text-ce-ink md:top-ce-5 md:right-ce-5">
        Mock-up only
      </span>
      <header className="flex flex-col gap-ce-2 pr-[7.5rem]">
        <h2 id="exercise-profile-card-title" className="ce-type-h3 text-ce-ink">
          Two quick questions
        </h2>
      </header>
      <p className="ce-type-body -mt-ce-2 text-ce-ink-muted">
        Answering these would let us suggest events worth your evening.
      </p>
      <MajorConfirm />
      <ol className="flex flex-col gap-ce-5 border-t border-ce-line pt-ce-4">
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
  );
}

export function ProfileCardMockup(): React.JSX.Element {
  return (
    <ExerciseScreen title="What a profile would be asked">
      <div className="grid items-start gap-ce-6 md:grid-cols-[minmax(0,360px)_minmax(0,1fr)] md:gap-ce-7">
        <div className="ce-measure flex flex-col gap-ce-4">
          <p className="ce-type-lead text-ce-ink-muted">
            Major and year are already on file, and past events are recorded when someone attends.
            So the card asks only two things, and asks the person to confirm their major.
          </p>
          <p className="ce-type-body text-ce-ink-muted">
            This is a mock-up of the card, shown to the class. It asks nobody anything, keeps no
            answers, and is not connected to any list.
          </p>
        </div>
        <PhoneCard />
      </div>
    </ExerciseScreen>
  );
}
