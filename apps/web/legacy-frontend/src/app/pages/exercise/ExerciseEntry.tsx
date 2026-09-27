/**
 * The entry screen: a team number, and nothing else.
 *
 * Requirements, "Getting in" row: *"No login. A public web address. … a team
 * enters its team number (1-6) so its saved runs are labeled."* That is the
 * whole of the input. There is no password, no name, no email and no account,
 * because ADR-0025 D1 gives this scope no login at all — a team *is* its
 * number, and entering a number another team has already entered opens that
 * team's workspace, which is the point.
 *
 * The numbers come from `GET /v1/exercise` (`team_numbers`) rather than being
 * written here. The requirements fix them at 1-6 and that route reports them
 * as a constant of the scope, so there is one place they live.
 *
 * **An older data file's label is not a bug.** PR #186's owner ruling of
 * 2026-09-19: a team's entry no longer lands on the newest upload — an
 * existing workspace wins, and only an instructor re-point moves a team. So
 * after the instructor uploads a file, this screen may legitimately show the
 * previous file's label. Nothing here warns about that, deliberately.
 *
 * **The license line is a constant of the exercise, not of a data file.**
 * OQ-CE-09 closed 2026-09-25 (Ann Wang, email reply to the team's question
 * list): {@link EXERCISE_LICENSE_LINE}. It is
 * rendered here, in every state of the screen — loading, refused, unreachable
 * and ready — because this is the opening screen and no team has picked a
 * workspace yet, so no data file is in play. It is not read from
 * `DatasetView.license_line`: that column is per upload, the ingest never
 * fills it, and a team that has not entered a number has no dataset to read
 * it from.
 */
import * as React from "react";
import { useNavigate } from "react-router";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  enterTeamWorkspace,
  readCurrentWorkspace,
  readScopeFacts,
  type ExerciseScopeFacts,
  type TeamWorkspaceView,
} from "../../../lib/exerciseClient";
import { LectureHallArt, TeamBadgeArt } from "./exerciseArt";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ceButton, Spinner } from "./exerciseUi";
import { useExerciseResource } from "./useExerciseResource";
import { clearWorkspacePointer, readWorkspacePointer, writeWorkspacePointer } from "./workspacePointer";

/**
 * The opening screen's license line (OQ-CE-09, closed 2026-09-25). Ann's two
 * sentences, verbatim.
 */
export const EXERCISE_LICENSE_LINE =
  "For California State Polytechnic University, Pomona — College of Business Administration instructional use only. All student profiles are fictional.";

/** Where a team goes once it is in. */
export const EVENT_PICKER_PATH = "/exercise/events";

interface EntryData {
  readonly facts: ExerciseScopeFacts;
  /** `null` when this browser has not entered a number yet. */
  readonly workspace: TeamWorkspaceView | null;
}

/**
 * The scope's facts, plus whichever workspace the cookie points at.
 *
 * A browser that has not entered a number is refused with
 * `exercise_workspace_required`, and that refusal is the *ordinary first
 * visit* rather than a failure — so it is caught here and turned into
 * `workspace: null`. Every other refusal is left to propagate and is shown as
 * the sentence it is.
 */
async function loadEntry(signal: AbortSignal): Promise<EntryData> {
  const facts = await readScopeFacts(signal);
  try {
    return { facts, workspace: await readCurrentWorkspace(signal) };
  } catch (error) {
    if (isRefusal(error) && error.code === "exercise_workspace_required") {
      clearWorkspacePointer();
      return { facts, workspace: null };
    }
    throw error;
  }
}

/** The opening question and its lead (DESIGN.md §7.1, §11.1). */
const OPENING_TITLE = "Who should we invite?";
const OPENING_LEAD =
  "Your team is promoting a campus career event with 60 seats. Choose whom to invite, see what happened, then try again.";

export function ExerciseEntry(): React.JSX.Element {
  const { state, reload } = useExerciseResource(loadEntry, []);

  return (
    <ExerciseScreen title={OPENING_TITLE} intro={OPENING_LEAD}>
      {/*
        The opening zone's second column (§7.1): the license line in a quiet
        sunk card, and the lecture hall on desktop. The license line is here in
        every state — loading, refused, unreachable and ready.
      */}
      <div className="grid gap-6 lg:grid-cols-12 lg:items-center">
        <p
          className="ce-body ce-well px-5 py-4 text-ce-ink lg:col-span-7 md:px-6 md:py-5"
          data-slot="exercise-license-line"
        >
          {EXERCISE_LICENSE_LINE}
        </p>
        <div className="hidden justify-center text-ce-primary lg:col-span-5 lg:flex">
          <LectureHallArt className="h-[120px] w-[160px]" />
        </div>
      </div>

      <hr className="border-0 border-t border-ce-line" />

      <section aria-labelledby="exercise-entry-heading" className="flex flex-col gap-4">
        <h2 id="exercise-entry-heading" className="ce-h2 text-ce-ink">
          Which team are you?
        </h2>
        <p className="ce-body text-ce-muted">
          Pick your team's number. Your team's saved work is kept under that number.
        </p>
        {state.status === "loading" ? <ExerciseLoading what="the exercise" shape="tiles" /> : null}
        {state.status === "refused" ? <ExerciseNotice message={state.refusal.message} /> : null}
        {state.status === "unreachable" ? (
          <ExerciseNotice message={state.message} tone="problem">
            <button type="button" onClick={reload} className={ceButton("primary")}>
              Try again
            </button>
          </ExerciseNotice>
        ) : null}
        {state.status === "ready" ? <EntryForm data={state.data} /> : null}
      </section>
    </ExerciseScreen>
  );
}

function EntryForm({ data }: { readonly data: EntryData }): React.JSX.Element {
  const navigate = useNavigate();
  const teamNumbers = data.facts.team_numbers;

  // Pre-select what this browser last entered, when the mirror has it and the
  // server still offers it. The value is never trusted for anything: it seeds
  // a form control, and the server decides on submit.
  const [selected, setSelected] = React.useState<number | null>(
    () => data.workspace?.team_number ?? readWorkspacePointer(teamNumbers),
  );
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (selected === null || pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      const workspace = await enterTeamWorkspace(selected);
      writeWorkspacePointer(workspace.team_number);
      await navigate(EVENT_PICKER_PATH);
    } catch (error) {
      setRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-6">
      <div className="flex w-full flex-col gap-6 sm:w-fit">
        {/*
          A real radio group: the six tiles share one `name`, so arrow keys move
          between them (§8.4). The group's name is the legend; the section's
          heading above says the same thing for sighted readers.
        */}
        <fieldset className="border-0 p-0" disabled={pending}>
          <legend className="sr-only">Team number</legend>
          <div className="grid grid-cols-3 gap-4 sm:flex sm:flex-wrap">
            {teamNumbers.map((number) => (
              <TeamTile
                key={number}
                number={number}
                selected={selected === number}
                dimmed={pending}
                onSelect={() => setSelected(number)}
              />
            ))}
          </div>
        </fieldset>

        {data.workspace === null ? null : (
          <p
            className="ce-body flex items-center gap-3 text-ce-ink"
            data-slot="exercise-entry-current"
          >
            <TeamBadgeArt className="size-8 shrink-0 text-ce-primary" />
            <span>
              This browser is already in team {data.workspace.team_number}, working in{" "}
              <strong>{data.workspace.dataset_label}</strong>.
            </span>
          </p>
        )}

        {refusal === null ? null : <ExerciseNotice message={refusal} />}

        {/*
          Right-aligned under the tiles on desktop (§7.2). On a phone it is
          full width and, once a tile is chosen, sticks to the bottom safe area.
        */}
        <div
          className={`flex sm:justify-end ${
            selected === null
              ? ""
              : "sticky bottom-0 z-10 -mx-4 bg-ce-page px-4 pt-3 pb-[max(12px,env(safe-area-inset-bottom))] sm:static sm:mx-0 sm:bg-transparent sm:p-0"
          }`}
        >
          <button
            type="submit"
            disabled={selected === null || pending}
            aria-busy={pending || undefined}
            className={ceButton("primary", "ce-btn-lg w-full sm:w-auto")}
          >
            {pending ? <Spinner /> : null}
            {pending ? "Opening your team's work…" : "Open this team's work"}
          </button>
        </div>
      </div>
    </form>
  );
}

/**
 * One numbered place card (§6.4): 112px on desktop, 96px on a phone, a
 * Transducer numeral. Selected is CPP Green with a white numeral and a small
 * gold corner notch; the notch is decoration, the fill and `checked` state
 * carry the meaning.
 */
function TeamTile({
  number,
  selected,
  dimmed,
  onSelect,
}: {
  readonly number: number;
  readonly selected: boolean;
  readonly dimmed: boolean;
  readonly onSelect: () => void;
}): React.JSX.Element {
  return (
    <label
      className={`group relative flex aspect-square w-full cursor-pointer items-center justify-center overflow-hidden rounded-[14px] transition-[transform,box-shadow,background-color] duration-150 has-[input:focus-visible]:outline-3 has-[input:focus-visible]:outline-offset-3 has-[input:focus-visible]:outline-ce-primary sm:size-28 ${
        selected
          ? "bg-ce-primary text-ce-on-primary shadow-[var(--ce-elev-2)]"
          : "ce-lift bg-ce-surface text-ce-ink shadow-[var(--ce-elev-1)] hover:text-ce-primary"
      } ${dimmed ? "opacity-60" : ""}`}
    >
      <input
        type="radio"
        name="team_number"
        value={number}
        checked={selected}
        onChange={onSelect}
        // The accessible name is stated rather than inherited from the
        // label's text. The label holds the big projected numeral, so an
        // inherited name would read as a bare digit.
        aria-label={`Team ${number}`}
        className="sr-only"
      />
      <span aria-hidden="true" className="ce-num text-[40px] leading-none font-bold sm:text-[44px]" style={{ fontFamily: "var(--font-headline)" }}>
        {number}
      </span>
      {selected ? (
        <span
          aria-hidden="true"
          className="absolute top-0 right-0 size-0 border-t-[18px] border-l-[18px] border-t-ce-gold border-l-transparent"
        />
      ) : null}
    </label>
  );
}
