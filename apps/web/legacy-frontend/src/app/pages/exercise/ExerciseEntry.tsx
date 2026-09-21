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
 * **No license line.** OQ-CE-09 is open: Ann has not provided the sentence
 * that goes on the opening screen. The register's placeholder is "None shown
 * until Ann provides the sentence", so this screen renders nothing at all in
 * that slot — not a placeholder, not "License: TBD". `DatasetView.license_line`
 * is `null` until she does, and the instructor screen renders it only when it
 * is not.
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
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";
import { clearWorkspacePointer, readWorkspacePointer, writeWorkspacePointer } from "./workspacePointer";

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

export function ExerciseEntry(): React.JSX.Element {
  const { state, reload } = useExerciseResource(loadEntry, []);

  return (
    <ExerciseScreen
      title="Which team are you?"
      intro="Pick your team's number. Your team's saved work is kept under that number."
    >
      {state.status === "loading" ? <ExerciseLoading what="the exercise" /> : null}
      {state.status === "refused" ? (
        <ExerciseNotice message={state.refusal.message} />
      ) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={RETRY_CLASS}>
            Try again
          </button>
        </ExerciseNotice>
      ) : null}
      {state.status === "ready" ? <EntryForm data={state.data} /> : null}
    </ExerciseScreen>
  );
}

const RETRY_CLASS =
  "rounded-lg border-2 border-slate-400 px-5 py-2 text-xl font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

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
      <fieldset className="border-0 p-0">
        <legend className="text-2xl font-semibold text-slate-900 dark:text-slate-50">
          Team number
        </legend>
        <div className="mt-4 flex flex-wrap gap-3">
          {teamNumbers.map((number) => (
            <label
              key={number}
              className={`flex h-20 w-20 cursor-pointer items-center justify-center rounded-lg border-4 text-3xl font-bold focus-within:outline-2 focus-within:outline-offset-2 ${
                selected === number
                  ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                  : "border-slate-400 text-slate-800 hover:bg-slate-100 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800"
              }`}
            >
              <input
                type="radio"
                name="team_number"
                value={number}
                checked={selected === number}
                onChange={() => setSelected(number)}
                // The accessible name is stated rather than inherited from the
                // label's text. The label holds both the big projected numeral
                // and a visually-hidden word, so an inherited name read out as
                // "4 Team 4".
                aria-label={`Team ${number}`}
                className="sr-only"
              />
              <span aria-hidden="true">{number}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {data.workspace === null ? null : (
        <p className="text-xl text-slate-700 dark:text-slate-200" data-slot="exercise-entry-current">
          This browser is already in team {data.workspace.team_number}, working in{" "}
          <strong>{data.workspace.dataset_label}</strong>.
        </p>
      )}

      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      <div>
        <button
          type="submit"
          disabled={selected === null || pending}
          className="rounded-lg border-2 border-slate-900 bg-slate-900 px-8 py-4 text-2xl font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
        >
          {pending ? "Opening your team's work…" : "Open this team's work"}
        </button>
      </div>
      {/*
        PLACEHOLDER (OQ-CE-09): the opening screen's license line goes here
        once Ann provides the sentence. Nothing is rendered until then — not a
        placeholder and not "License: TBD", per the register's ruling.
      */}
    </form>
  );
}
