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
 *
 * **An expired session signs the page out.** The instructor cookie lasts
 * twelve hours and nothing announces its end. Every read and action here that
 * is refused with `exercise_instructor_session_required` calls `onSignedOut`,
 * so the page returns to the passcode form instead of leaving controls that
 * will all fail. Every other panel on the page follows the same rule
 * (`instructorSession.ts`).
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
import { cn } from "../../components/ui/utils";
import { askingChoiceLabel } from "./askingChoices";
import { Button } from "./desk";
import { ExerciseNotice } from "./ExerciseScreen";
import { useSignOutOnExpiredRead } from "./instructorSession";
import { INSTRUCTOR_WELL, PanelCard, PanelSkeleton } from "./instructorUi";
import { INSTRUCTOR_SESSION_REQUIRED } from "./refusals";
import { useExerciseResource } from "./useExerciseResource";

/** How often the list is re-read while the tab is visible. Gentle: one small GET. */
export const TEAMS_POLL_MS = 15_000;

/** The page's sentence for a request that never landed. */
const UNREACHABLE = "The exercise could not be reached. Check the connection and try again.";

export function InstructorTeams({
  reloadKey = 0,
  onSignedOut,
}: {
  /**
   * Bumped by the page when something it did changes what this panel says: an
   * upload, a re-point, "Ask for every team", an unlock.
   */
  readonly reloadKey?: number;
  /** Called when the instructor session has expired; the page shows the passcode form. */
  readonly onSignedOut?: () => void;
} = {}): React.JSX.Element {
  const { state, reload } = useExerciseResource(listTeamWorkspaces, [reloadKey]);

  /**
   * The sentence to show for a thrown error, signing out first when the
   * session is gone. Shared by the reset and the team detail.
   */
  const describeError = React.useCallback(
    (error: unknown): string => {
      if (!isRefusal(error)) {
        return UNREACHABLE;
      }
      if (error.code === INSTRUCTOR_SESSION_REQUIRED) {
        onSignedOut?.();
      }
      return error.message;
    },
    [onSignedOut],
  );

  useSignOutOnExpiredRead(state, onSignedOut);
  const [refusal, setRefusal] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);
  const busy = state.status === "loading" || (state.status === "ready" && state.refreshing);

  /**
   * The poll only re-reads a list it has. A refused read (the twelve-hour
   * cookie ran out) or an unreachable one would otherwise be re-sent every
   * 15 s, flickering "Loading the teams" each time. Coming back to the tab and
   * the button still re-read.
   */
  const hasList = React.useRef(false);
  hasList.current = state.status === "ready";

  React.useEffect(() => {
    const whenVisible = (): void => {
      if (document.visibilityState === "visible") {
        void reload();
      }
    };
    const tick = (): void => {
      if (hasList.current) {
        whenVisible();
      }
    };
    document.addEventListener("visibilitychange", whenVisible);
    const timer = window.setInterval(tick, TEAMS_POLL_MS);
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
      setRefusal(describeError(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <PanelCard
      title="Teams"
      slot="exercise-instructor-teams"
      headerAction={
        <Button variant="secondary" disabled={busy} onClick={() => void reload()}>
          Check the teams again
        </Button>
      }
    >
      {refusal === null ? null : <ExerciseNotice message={refusal} />}

      {state.status === "loading" ? <PanelSkeleton what="the teams" rows={3} /> : null}
      {state.status === "refused" ? <ExerciseNotice message={state.refusal.message} /> : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem" />
      ) : null}
      {state.status === "ready" ? (
        <>
          <p className="ce-type-body ce-measure text-ce-ink-muted">
            {state.data.active_dataset_label === null
              ? "No data file has been uploaded yet."
              : `The newest data file is ${state.data.active_dataset_label}. A team stays in the file it entered on until it is moved.`}
          </p>
          {state.data.teams.length === 0 ? (
            <p className="ce-type-body text-ce-ink-muted">No team has entered a number yet.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-ce-line">
              {state.data.teams.map((team) => (
                <li
                  key={`${team.dataset_id}-${team.team_number}`}
                  className="py-ce-4 first:pt-ce-2 last:pb-0"
                >
                  <TeamRow
                    team={team}
                    pending={pending}
                    describeError={describeError}
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
    </PanelCard>
  );
}

function TeamRow({
  team,
  pending,
  describeError,
  onReset,
}: {
  readonly team: TeamSummaryView;
  readonly pending: boolean;
  readonly describeError: (error: unknown) => string;
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
      setDetailRefusal(describeError(error));
    }
  }

  return (
    <div className="flex items-start gap-ce-4">
      {/* The team's seal: its number, as on the place cards (§6.4). */}
      <span
        aria-hidden="true"
        className="ce-type-rank inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-ce-primary-tint text-ce-on-primary-tint"
      >
        {team.team_number}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-ce-3">
        <div className="flex flex-col gap-ce-1">
          <h3 className="ce-type-h3 text-ce-ink">Team {team.team_number}</h3>
          <p className="ce-type-body ce-tabular text-ce-ink">
            In {team.dataset_label} — {team.saved_setting_count} saved settings,{" "}
            {team.result_run_count} result runs.
          </p>
          <p className="ce-type-meta text-ce-ink-muted">
            {team.asking_choice === null
              ? "Has not picked a way of asking."
              : `Asking: ${askingChoiceLabel(team.asking_choice)}`}{" "}
            {team.refreshed_at === null ? "Has not asked yet." : "Has already asked."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-ce-3">
          <Button
            variant="secondary"
            className="w-full sm:w-auto"
            onClick={() => void openDetail()}
          >
            Open this team&apos;s work
          </Button>
          {confirming ? null : (
            <Button
              variant="quiet"
              data-slot="exercise-team-reset"
              onClick={() => setConfirming(true)}
            >
              Clear team {team.team_number}&apos;s work
            </Button>
          )}
        </div>

        {confirming ? (
          <div className={cn(INSTRUCTOR_WELL, "flex flex-col gap-ce-3")}>
            <p className="ce-type-body text-ce-ink">
              This clears team {team.team_number}&apos;s saved settings and result runs. No other
              team is touched.
            </p>
            <div className="flex flex-wrap items-center gap-ce-3">
              <Button
                variant="destructive"
                disabled={pending}
                onClick={() => {
                  setConfirming(false);
                  void onReset();
                }}
              >
                Yes, clear team {team.team_number}
              </Button>
              <Button variant="quiet" onClick={() => setConfirming(false)}>
                Keep their work
              </Button>
            </div>
          </div>
        ) : null}

        {detailRefusal === null ? null : <ExerciseNotice message={detailRefusal} />}
        {detail === null ? null : <TeamDetail detail={detail} />}
      </div>
    </div>
  );
}

function TeamDetail({ detail }: { readonly detail: TeamDetailView }): React.JSX.Element {
  return (
    <div className={cn(INSTRUCTOR_WELL, "ce-fade-rise flex flex-col gap-ce-4")}>
      <div className="flex flex-col gap-ce-1">
        <h4 className="ce-type-label text-ce-ink">Saved settings</h4>
        {detail.saved_settings.length === 0 ? (
          <p className="ce-type-body text-ce-ink-muted">None.</p>
        ) : (
          <ul className="ce-type-body flex flex-col gap-ce-1 text-ce-ink">
            {detail.saved_settings.map((setting) => (
              <li key={`${setting.event_key}-${setting.name}`}>
                {setting.name} — for {setting.event_key}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-col gap-ce-1">
        <h4 className="ce-type-label text-ce-ink">Result runs</h4>
        {detail.result_runs.length === 0 ? (
          <p className="ce-type-body text-ce-ink-muted">None.</p>
        ) : (
          <ul className="ce-type-body ce-tabular flex flex-col gap-ce-1 text-ce-ink">
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
