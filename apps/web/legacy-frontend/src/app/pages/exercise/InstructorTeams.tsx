/**
 * The instructor's teams: who exists, what they have, and the one reset.
 *
 * **This is the only reset in the product.** PR #186, on the owner's ruling of
 * 2026-09-19: `POST /v1/exercise/workspaces/current/reset` is removed and
 * answers 404, because the workspace cookie is obtainable by anyone who types
 * a team's number and Session 2 has no backup. The button below is
 * `POST /v1/exercise/instructor/workspaces/{team_number}/reset`, behind the
 * passcode session. No team screen renders one, and a test over the source
 * tree keeps it that way.
 *
 * It clears one team's work and touches no other team — design spec §11's
 * "a reset per team that does not touch other teams", which is one of the four
 * things §18 calls easy to forget. It asks before it does it.
 *
 * `dataset_id` is passed on every per-team call from the team's own row.
 * Design spec §14's "As shipped" note: these routes resolve against the data
 * file the teams are actually on, not the newest upload, and several files in
 * use is refused with a sentence asking which — passing the id the team list
 * gave is what answers that question before it is asked.
 *
 * **The list stays current on its own.** Teams enter their numbers and press
 * their own buttons while the instructor watches this page, and nothing on it
 * hears about that. So it re-reads when the page's own actions land (the
 * `reloadKey`), on "Check the teams again", when the tab comes back into view, and every
 * {@link TEAMS_POLL_MS} while the tab is visible. A re-read keeps the rows on
 * screen (the hook's `refreshing`), so an open team or a pending "clear" is not
 * thrown away by a poll.
 */
import * as React from "react";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  listTeamWorkspaces,
  readTeamWorkspace,
  resetTeamWorkspace,
  type TeamDetailView,
  type TeamSummaryView,
} from "../../../lib/exerciseClient";
import { askingChoiceLabel } from "./askingChoices";
import { ExerciseLoading, ExerciseNotice } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";

/** How often the list is re-read while the tab is visible. Gentle: one small GET. */
export const TEAMS_POLL_MS = 15_000;

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-4 py-2 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

export function InstructorTeams({
  reloadKey = 0,
}: {
  /**
   * Bumped by the page when something it did changes what this panel says: an
   * upload, a re-point, "Ask for every team", an unlock.
   */
  readonly reloadKey?: number;
} = {}): React.JSX.Element {
  const { state, reload } = useExerciseResource(listTeamWorkspaces, [reloadKey]);
  const [refusal, setRefusal] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);
  const busy = state.status === "loading" || (state.status === "ready" && state.refreshing);

  React.useEffect(() => {
    const whenVisible = (): void => {
      if (document.visibilityState === "visible") {
        void reload();
      }
    };
    document.addEventListener("visibilitychange", whenVisible);
    const timer = window.setInterval(whenVisible, TEAMS_POLL_MS);
    return () => {
      document.removeEventListener("visibilitychange", whenVisible);
      window.clearInterval(timer);
    };
  }, [reload]);

  async function run(action: () => Promise<void>): Promise<void> {
    if (pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      await action();
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
    <section className="flex flex-col gap-4" data-slot="exercise-instructor-teams">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">Teams</h2>
        <button type="button" className={BUTTON} disabled={busy} onClick={() => void reload()}>
          Check the teams again
        </button>
      </div>
      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      {state.status === "loading" ? <ExerciseLoading what="the teams" /> : null}
      {state.status === "refused" ? <ExerciseNotice message={state.refusal.message} /> : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem" />
      ) : null}
      {state.status === "ready" ? (
        <>
          <p className="text-xl text-slate-600 dark:text-slate-300">
            {state.data.active_dataset_label === null
              ? "No data file has been uploaded yet."
              : `The newest data file is ${state.data.active_dataset_label}. A team stays in the file it entered on until it is moved.`}
          </p>
          {state.data.teams.length === 0 ? (
            <p className="text-xl text-slate-700 dark:text-slate-200">
              No team has entered a number yet.
            </p>
          ) : (
            <ul className="flex flex-col gap-4">
              {state.data.teams.map((team) => (
                <li key={`${team.dataset_id}-${team.team_number}`}>
                  <TeamRow
                    team={team}
                    pending={pending}
                    onReset={() =>
                      run(async () => {
                        await resetTeamWorkspace(team.team_number, team.dataset_id);
                        reload();
                      })
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </section>
  );
}

function TeamRow({
  team,
  pending,
  onReset,
}: {
  readonly team: TeamSummaryView;
  readonly pending: boolean;
  readonly onReset: () => Promise<void>;
}): React.JSX.Element {
  const [confirming, setConfirming] = React.useState(false);
  const [detail, setDetail] = React.useState<TeamDetailView | null>(null);
  const [detailRefusal, setDetailRefusal] = React.useState<string | null>(null);

  async function openDetail(): Promise<void> {
    setDetailRefusal(null);
    try {
      setDetail(await readTeamWorkspace(team.team_number, team.dataset_id));
    } catch (error) {
      setDetailRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
    }
  }

  return (
    <div className="rounded-lg border-2 border-slate-300 px-5 py-4 dark:border-slate-600">
      <p className="text-2xl font-semibold text-slate-900 dark:text-slate-50">
        Team {team.team_number}
      </p>
      <p className="text-xl text-slate-600 dark:text-slate-300">
        In {team.dataset_label} — {team.saved_setting_count} saved settings,{" "}
        {team.result_run_count} result runs.
      </p>
      <p className="text-xl text-slate-600 dark:text-slate-300">
        {team.asking_choice === null
          ? "Has not picked a way of asking."
          : `Asking: ${askingChoiceLabel(team.asking_choice)}`}{" "}
        {team.refreshed_at === null ? "Has not asked yet." : "Has already asked."}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" className={BUTTON} onClick={() => void openDetail()}>
          Open this team's work
        </button>
        {confirming ? (
          <>
            <span className="text-xl">
              This clears team {team.team_number}'s saved settings and result runs. No other team is
              touched.
            </span>
            <button
              type="button"
              disabled={pending}
              className={BUTTON}
              onClick={() => {
                setConfirming(false);
                void onReset();
              }}
            >
              Yes, clear team {team.team_number}
            </button>
            <button type="button" className={BUTTON} onClick={() => setConfirming(false)}>
              Keep their work
            </button>
          </>
        ) : (
          <button
            type="button"
            className={BUTTON}
            data-slot="exercise-team-reset"
            onClick={() => setConfirming(true)}
          >
            Clear team {team.team_number}'s work
          </button>
        )}
      </div>

      {detailRefusal === null ? null : <ExerciseNotice message={detailRefusal} />}
      {detail === null ? null : <TeamDetail detail={detail} />}
    </div>
  );
}

function TeamDetail({ detail }: { readonly detail: TeamDetailView }): React.JSX.Element {
  return (
    <div className="mt-4 flex flex-col gap-3 text-xl">
      <div>
        <h4 className="text-2xl font-semibold">Saved settings</h4>
        {detail.saved_settings.length === 0 ? (
          <p className="text-slate-600 dark:text-slate-300">None.</p>
        ) : (
          <ul>
            {detail.saved_settings.map((setting) => (
              <li key={`${setting.event_key}-${setting.name}`}>
                {setting.name} — for {setting.event_key}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h4 className="text-2xl font-semibold">Result runs</h4>
        {detail.result_runs.length === 0 ? (
          <p className="text-slate-600 dark:text-slate-300">None.</p>
        ) : (
          <ul>
            {detail.result_runs.map((run) => (
              <li key={`${run.event_key}-${run.round}`}>
                {/* D8: open seats in words, not "N seats empty". */}
                Round {run.round} for {run.event_key}: invited {run.invited_count}, signed up{" "}
                {run.signed_up_count}, attended {run.attended_count}. {run.seats_empty}{" "}
                {run.seats_empty === 1 ? "seat is" : "seats are"} still open.
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
