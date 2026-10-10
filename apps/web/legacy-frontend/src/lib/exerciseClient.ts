/**
 * Every exercise call a screen can make, with the response shapes the backend
 * actually declares.
 *
 * The types below mirror the Pydantic response models in
 * `services/api/smartmatch_api/routers/exercise_*_models.py`,
 * `exercise_workspace.py` and `exercise_public.py`, field for field and in
 * their own snake_case. Those models are the source of truth, **not**
 * `contracts/openapi/smartmatch.json`: the exported contract builds the CBA
 * scope, and ADR-0025 D1 means the exercise routers are not registered in that
 * scope, so they are correctly absent from the export. `apps/web/AGENTS.md`
 * says to verify wiring against the contract; for this one product the
 * verifiable artefact is the response model, and that is what these types were
 * read from.
 *
 * Names are kept in the API's casing at this boundary — `signed_up_count`,
 * `missing_majors`, `profile_no` — per DESIGN.md's "use contract names and
 * exact field optionality at the network boundary". The shipped components
 * from PRs #161/#162 take camelCase props, so the mapping happens once, in the
 * screen that mounts them, and not in JSX scattered across a page.
 *
 * Nothing here invents a field. Where a screen would like a value the API does
 * not return — a profile's points, a name on a results panel — that is a
 * backend gap recorded in the pull request, not a field added here.
 */
import { exerciseRequest } from "./exerciseApi";

// ---------------------------------------------------------------------------
// Scope and workspace — `exercise_public.py`, `exercise_workspace.py`
// ---------------------------------------------------------------------------

/** `GET /v1/exercise` — constants of the scope, answerable before any upload. */
export interface ExerciseScopeFacts {
  readonly scope: string;
  readonly team_numbers: number[];
  readonly synthetic_data: boolean;
}

/** `TeamWorkspaceView` — three fields, and see the router for the four absent ones. */
export interface TeamWorkspaceView {
  readonly team_number: number;
  readonly dataset_label: string;
  readonly invite_limit: number;
}

// ---------------------------------------------------------------------------
// Matching — `exercise_matching_models.py`
// ---------------------------------------------------------------------------

export interface EventView {
  readonly event_key: string;
  readonly name: string;
  readonly topic_tags: string[];
  readonly target_majors: string[];
  readonly is_exercise_event: boolean;
  readonly sequence: number;
  /**
   * The event's short description, as the data file wrote it (#318), or
   * `null` when the file gives none: the past events, and any file from
   * before 2026-10-02. Printed as it is; nothing stands in for a `null`.
   */
  readonly description: string | null;
  /**
   * Whether the instructor has results for this event open right now. What to
   * show before a press; the run route still decides. `false` for past events.
   */
  readonly results_open: boolean;
  /** Whether this team has already used its one results run for this event. */
  readonly results_run: boolean;
}

export interface EventsView {
  readonly events: EventView[];
}

export interface PointsView {
  readonly total: number;
  readonly attendance_points: number;
  readonly card_points: number;
  readonly card_completion: "unknown" | "not_completed" | "completed";
}

/**
 * One name on the list.
 *
 * `rank` is a position, not a score (ADR-0025 D8). `contributing_factor_keys`
 * are rulebook keys and are rendered only through `factor_labels`.
 */
export interface ListEntryView {
  readonly rank: number;
  readonly profile_no: number;
  readonly display_name: string;
  readonly major: string;
  readonly class_year: string;
  readonly marker: string;
  readonly reason: string;
  readonly contributing_factor_keys: string[];
  /**
   * What this team's refresh changed about the profile: `new_card`,
   * `new_event`, `stopped_responding`. Empty before the refresh; may hold
   * several. The server always sends it; optional so older fixtures type-check.
   */
  readonly refresh_marks?: readonly string[];
  /** Proposal (#317): the profile's points counter; absent or null when not sent. */
  readonly points?: PointsView | null;
}

export interface GroupCountsView {
  readonly dimension: string;
  readonly on_list: Record<string, number>;
  readonly all_profiles: Record<string, number>;
}

export interface ListCoverageView {
  readonly missing_majors: string[];
  readonly missing_class_years: string[];
  readonly has_uncovered_group: boolean;
}

export interface ListCompositionView {
  readonly by_major: GroupCountsView;
  readonly by_class_year: GroupCountsView;
  readonly by_marker: GroupCountsView;
  readonly coverage: ListCoverageView;
}

export interface RankedListView {
  readonly event_key: string;
  readonly event_name: string;
  /** That event's description from the data file, or `null` (see `EventView`). */
  readonly event_description: string | null;
  readonly invite_limit: number;
  readonly setting_name: string | null;
  readonly weights: Record<string, number>;
  /** Ann's plain words for each factor key. The only thing a screen may print. */
  readonly factor_labels: Record<string, string>;
  readonly entries: ListEntryView[];
  /**
   * The first round's event name, so a `new_event` mark can say which event.
   * `null` when the file has no round. Optional for older fixtures.
   */
  readonly first_round_event_name?: string | null;
  readonly composition: ListCompositionView;
  readonly unlisted_class_years: string[];
  readonly unrankable_profile_count: number;
}

export interface CompareView {
  readonly a: RankedListView;
  readonly b: RankedListView;
  readonly on_both_profile_nos: number[];
}

export interface SavedSettingView {
  readonly name: string;
  readonly weights: Record<string, number>;
  readonly created_at: string;
}

export interface SavedSettingsView {
  readonly event_key: string;
  readonly settings: SavedSettingView[];
  /** The cap. Read from here — never written into a screen. */
  readonly max_settings: number;
}

/**
 * The four factor keys the ranked-list route accepts as query parameters.
 *
 * These are the rulebook's own keys and are *never* rendered: they exist here
 * because they are the wire names of the four weight parameters. Ann's words
 * for them arrive on every list response as `factor_labels`.
 */
export const EXERCISE_FACTOR_KEYS = [
  "same_major",
  "stated_interest_overlap",
  "career_goal_fit",
  "past_event_topic_overlap",
] as const;

export type ExerciseFactorKey = (typeof EXERCISE_FACTOR_KEYS)[number];

// ---------------------------------------------------------------------------
// Results — `exercise_results_models.py`
// ---------------------------------------------------------------------------

export interface ResultPanelView {
  readonly invited_profile_nos: number[];
  readonly signed_up_profile_nos: number[];
  readonly attended_profile_nos: number[];
  readonly invited_count: number;
  readonly signed_up_count: number;
  readonly attended_count: number;
}

export interface PreviousRoundView {
  readonly event_key: string;
  readonly round: number;
  readonly setting_name: string | null;
  readonly team: ResultPanelView;
  readonly seats_empty: number;
  readonly created_at: string;
}

/**
 * One name a run invited, as that team's ranked list showed it at the time —
 * `InvitedProfileView` in `exercise_results_models.py`.
 *
 * Stored with the run (issues #271, #319), so it does not change when the
 * saved setting is deleted or saved again. `rank`, `marker` and `reason` are
 * `null` only on a run stored before names were kept with the run: they could
 * not be rebuilt, and nothing stands in for them.
 */
export interface InvitedProfileView {
  readonly rank: number | null;
  readonly profile_no: number;
  readonly display_name: string;
  readonly major: string | null;
  readonly class_year: string | null;
  readonly marker: string | null;
  readonly reason: string | null;
}

export interface ResultsView {
  readonly event_key: string;
  readonly event_name: string;
  readonly round: number;
  readonly setting_name: string | null;
  readonly team: ResultPanelView;
  readonly email_everyone: ResultPanelView;
  readonly seats_empty: number;
  readonly event_seats: number;
  readonly existing_signups: number;
  /** `null` in round one; a populated panel in round two. */
  readonly round_one: PreviousRoundView | null;
  /**
   * The people this run invited, by name, in list order — the run's own
   * record. Optional so fixtures from before issue #271 still type-check; a
   * server from before it sends none, and the panels fall back to numbers.
   */
  readonly invited_profiles?: InvitedProfileView[];
  readonly created_at: string;
}

export interface AskingStateView {
  readonly choice: string | null;
  /** The three ways of asking, as the course names them. Never hard-coded. */
  readonly choices: string[];
  readonly refreshed: boolean;
  /** When the team's one refresh happened (ISO, UTC), or `null` before it has. */
  readonly refreshed_at: string | null;
  /**
   * What the team's refresh changed, read back from the server: `null` until
   * the team is refreshed (by itself or by the instructor).
   */
  readonly refresh_counts: RefreshCountsView | null;
  /** Whether the team has run round one's results. The choice opens only then. */
  readonly first_round_results: boolean;
  /** The first round's event name, or `null` when the file has no round. */
  readonly first_round_event_name: string | null;
}

/**
 * What one refresh changed, as counts of people. One shape for the team's own
 * press, every later read, and each team's line in the instructor's report.
 * The server sends no sentence: `refreshWording.ts` writes them.
 */
export interface RefreshCountsView {
  readonly cards_completed: number;
  readonly non_responding: number;
  readonly topics_added: number;
  /** How many invited profiles had no card: "12 of the **22**". */
  readonly invited_without_card: number;
  /** Every profile by "how much we know", before the refresh. Keyed by marker. */
  readonly marker_counts_before: Readonly<Record<string, number>>;
  /** The same, as the team sees the profiles after it. */
  readonly marker_counts_after: Readonly<Record<string, number>>;
}

export interface RefreshView {
  readonly choice: string;
  readonly cards_completed: number;
  readonly non_responding: number;
  readonly topics_added: number;
  readonly refreshed_at: string;
  readonly refresh_counts: RefreshCountsView;
}

/** Why the every-team refresh skipped a team. Codes; `refreshWording.ts` owns the words. */
export type RefreshSkipReason = "no_asking_choice" | "no_round_one_run" | "already_refreshed";

/** One team's line in the every-team refresh report. */
export interface RefreshAllTeamView {
  readonly team_number: number;
  /** The team's data file, by label. Shown only when the report spans two files. */
  readonly dataset_label: string;
  readonly outcome: "refreshed" | "skipped";
  /** `null` for a refreshed team. Typed loosely so a new code renders, not crashes. */
  readonly reason_code: RefreshSkipReason | (string & {}) | null;
  /** When it was refreshed: by this request, or earlier if `already_refreshed`. */
  readonly refreshed_at: string | null;
  /** What this request's refresh changed. `null` for a skipped team. */
  readonly refresh_counts: RefreshCountsView | null;
  readonly first_round_event_name: string | null;
}

export interface RefreshAllView {
  readonly refreshed_team_numbers: number[];
  readonly refreshed: number;
  /** Teams that had chosen and still could not be refreshed. Not `teams`' skipped count. */
  readonly skipped: number;
  /** Every team that exists, in the Teams panel's order. */
  readonly teams: RefreshAllTeamView[];
}

// ---------------------------------------------------------------------------
// Instructor — `exercise_instructor_models.py`
// ---------------------------------------------------------------------------

export interface InstructorSessionView {
  readonly signed_in: boolean;
}

export interface DatasetView {
  readonly dataset_id: string;
  readonly label: string;
  readonly source_filename: string;
  readonly uploaded_at: string;
  readonly row_count: number;
  readonly event_count: number;
  readonly checksum: string;
  readonly invite_limit: number;
  /**
   * A per-upload license line; the ingest does not fill it, so `null`.
   * Rendered only when present. The exercise's own license line (OQ-CE-09,
   * closed 2026-09-25) is `EXERCISE_LICENSE_LINE` on the opening screen.
   */
  readonly license_line: string | null;
}

export interface IngestReportView {
  readonly profile_count: number;
  readonly event_count: number;
  readonly exercise_event_count: number;
  readonly distinct_class_years: string[];
  readonly profiles_without_card: number;
  readonly distinct_stated_interest_terms: number;
  readonly distinct_topic_tag_terms: number;
  readonly events_without_topic_tags: number;
  readonly major_only: number;
  readonly major_plus_events: number;
  readonly completed_card: number;
}

export interface UploadedDatasetView {
  readonly dataset: DatasetView;
  readonly report: IngestReportView;
  /** The server's sentence saying an upload moved nobody. Shown as-is. */
  readonly notice: string;
}

export interface TeamSummaryView {
  readonly team_number: number;
  readonly dataset_id: string;
  readonly dataset_label: string;
  readonly created_at: string;
  readonly saved_setting_count: number;
  readonly result_run_count: number;
  readonly asking_choice: string | null;
  readonly refreshed_at: string | null;
}

export interface TeamListView {
  readonly teams: TeamSummaryView[];
  readonly active_dataset_label: string | null;
}

/** One saved setting: its four stated weights and the list of names it builds now. */
export interface InstructorSavedSettingView {
  readonly event_key: string;
  /** The event's label, as the data file spells it. */
  readonly event_name: string;
  /** 1 or 2, or `null` when the event is not one of the two rounds. */
  readonly round: number | null;
  readonly name: string;
  readonly created_at: string;
  /** The team's own four stated weights, by factor key. Never a score. */
  readonly weights: Record<string, number>;
  /** The list this setting builds right now, in order: what the team's screen shows. */
  readonly invited: InvitedProfileView[];
}

/** One results run: who and how many. The names are the run's own record. */
export interface ResultRunView {
  readonly event_key: string;
  readonly event_name: string;
  readonly round: number;
  readonly setting_name: string | null;
  /** The team no longer has a saved setting of that name; the run is unaffected. */
  readonly setting_deleted: boolean;
  /** The four stated weights the run's list was built with, or `null` when not recorded. */
  readonly setting_weights: Record<string, number> | null;
  readonly invited_count: number;
  readonly signed_up_count: number;
  readonly attended_count: number;
  readonly seats_empty: number;
  readonly created_at: string;
  /** Empty for a run stored before names were kept; the counts still stand. */
  readonly invited: InvitedProfileView[];
  readonly signed_up: InvitedProfileView[];
  readonly attended: InvitedProfileView[];
}

/** `GET …/instructor/workspaces/{team_number}`: one team's whole work (issue #319). */
export interface TeamDetailView {
  readonly team_number: number;
  /** The way of asking the team chose, or `null` before it has chosen. */
  readonly asking_choice: string | null;
  /** ISO time of the team's one refresh, or `null` when it has not happened. */
  readonly refreshed_at: string | null;
  /** Ann's words for each factor key, to render the four numbers with. */
  readonly factor_labels: Record<string, string>;
  readonly saved_settings: InstructorSavedSettingView[];
  readonly result_runs: ResultRunView[];
}

/**
 * One event the teams run, and whether its results are open right now.
 *
 * Three states off two timestamps (D16 amendment, 2026-10-06): never opened
 * (both `null`), open (`unlocked`, `closed_at` `null`), closed again
 * (`closed_at` set). `unlocked_at` is the most recent opening.
 */
export interface InstructorEventView {
  readonly event_key: string;
  readonly name: string;
  readonly unlocked: boolean;
  /** ISO time results were last opened, or `null` when they never were. */
  readonly unlocked_at: string | null;
  /** ISO time results were closed again, or `null` while open or never opened. */
  readonly closed_at: string | null;
  /** The same description the teams read, or `null` (see `EventView`). */
  readonly description: string | null;
}

/** `GET /v1/exercise/instructor/events`: the teams' data file and its events. */
export interface InstructorEventsView {
  /** The file the unlock writes to. Passed back on every unlock. */
  readonly dataset_id: string;
  readonly dataset_label: string;
  readonly events: InstructorEventView[];
}

export interface UnlockView {
  readonly event_key: string;
  readonly unlocked: boolean;
  /** ISO time of this opening. */
  readonly unlocked_at: string | null;
}

/** `POST …/instructor/events/{event_key}/lock`: results are closed again. */
export interface LockView {
  readonly event_key: string;
  readonly unlocked: boolean;
  /** ISO time of the close, or `null` when there was nothing open to close. */
  readonly closed_at: string | null;
}

export interface RepointView {
  readonly dataset_label: string;
  readonly teams_moved: number;
  readonly teams_discarded: number;
}

// ---------------------------------------------------------------------------
// Team-facing calls
// ---------------------------------------------------------------------------

/**
 * `GET /v1/exercise` — the scope's constants, before any data file exists.
 *
 * The entry screen reads its team numbers from here rather than writing 1-6
 * into a component: the requirements fix them and this route reports them,
 * so there is one place they live.
 */
export function readScopeFacts(signal?: AbortSignal) {
  return exerciseRequest<ExerciseScopeFacts>("", { signal });
}

/** `POST /v1/exercise/workspaces` — the entry screen's whole input. */
export function enterTeamWorkspace(teamNumber: number, signal?: AbortSignal) {
  return exerciseRequest<TeamWorkspaceView>("/workspaces", {
    method: "POST",
    json: { team_number: teamNumber },
    signal,
  });
}

/** `GET /v1/exercise/workspaces/current` — what this browser's cookie points at. */
export function readCurrentWorkspace(signal?: AbortSignal) {
  return exerciseRequest<TeamWorkspaceView>("/workspaces/current", { signal });
}

/** `GET /v1/exercise/workspaces/current/events`. */
export function readEvents(signal?: AbortSignal) {
  return exerciseRequest<EventsView>("/workspaces/current/events", { signal });
}

/**
 * The weights a list is built with: a saved setting's name, or four numbers,
 * or neither. Naming both is refused by the server with a sentence.
 */
export type ListWeighting =
  | { readonly kind: "default" }
  | { readonly kind: "setting"; readonly name: string }
  | { readonly kind: "weights"; readonly weights: Readonly<Record<string, number>> };

function weightingQuery(weighting: ListWeighting): Record<string, string | undefined> {
  if (weighting.kind === "setting") {
    return { setting: weighting.name };
  }
  if (weighting.kind === "weights") {
    const query: Record<string, string> = {};
    for (const key of EXERCISE_FACTOR_KEYS) {
      const value = weighting.weights[key];
      if (typeof value === "number") {
        query[key] = String(value);
      }
    }
    return query;
  }
  return {};
}

/** `GET …/events/{event_key}/list`. */
export function readRankedList(
  eventKey: string,
  weighting: ListWeighting = { kind: "default" },
  signal?: AbortSignal,
) {
  return exerciseRequest<RankedListView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/list`,
    { query: weightingQuery(weighting), signal },
  );
}

/**
 * The address of the CSV download, for an ordinary `<a download>`.
 *
 * A link rather than a fetch-and-blob: the browser already knows how to save a
 * `text/csv` response, the filename comes back in `Content-Disposition`, and
 * building the file client-side would mean a second implementation of §8's
 * columns that could drift from the server's.
 */
export function rankedListCsvHref(
  eventKey: string,
  weighting: ListWeighting = { kind: "default" },
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(weightingQuery(weighting))) {
    if (value !== undefined) {
      search.set(key, value);
    }
  }
  const suffix = search.toString();
  const path = `/v1/exercise/workspaces/current/events/${encodeURIComponent(eventKey)}/list.csv`;
  return suffix === "" ? path : `${path}?${suffix}`;
}

/** `GET …/events/{event_key}/settings`. */
export function readSavedSettings(eventKey: string, signal?: AbortSignal) {
  return exerciseRequest<SavedSettingsView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/settings`,
    { signal },
  );
}

/** `PUT …/events/{event_key}/settings/{name}`. */
export function saveSetting(
  eventKey: string,
  name: string,
  weights: Readonly<Record<string, number>>,
  signal?: AbortSignal,
) {
  return exerciseRequest<SavedSettingsView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/settings/${encodeURIComponent(name)}`,
    { method: "PUT", json: { weights }, signal },
  );
}

/** `DELETE …/events/{event_key}/settings/{name}`. */
export function deleteSetting(eventKey: string, name: string, signal?: AbortSignal) {
  return exerciseRequest<SavedSettingsView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/settings/${encodeURIComponent(name)}`,
    { method: "DELETE", signal },
  );
}

/** `GET …/events/{event_key}/settings/compare?a=&b=`. */
export function compareSettings(eventKey: string, a: string, b: string, signal?: AbortSignal) {
  return exerciseRequest<CompareView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/settings/compare`,
    { query: { a, b }, signal },
  );
}

/**
 * `POST …/events/{event_key}/results` — 201, once per team per event.
 *
 * `settingName` is the team's **final setting**, one of its saved settings for
 * this event, and is required: the server refuses a run without one (Ann to
 * Chau, Discord, 2026-09-24). There is no run on the course's starting values.
 */
export function runResults(eventKey: string, settingName: string, signal?: AbortSignal) {
  return exerciseRequest<ResultsView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/results`,
    { method: "POST", json: { setting_name: settingName }, signal },
  );
}

/** `GET …/events/{event_key}/results` — the stored run, read back. */
export function readResults(eventKey: string, signal?: AbortSignal) {
  return exerciseRequest<ResultsView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/results`,
    { signal },
  );
}

/** `GET …/asking-choice`. */
export function readAskingChoice(signal?: AbortSignal) {
  return exerciseRequest<AskingStateView>("/workspaces/current/asking-choice", { signal });
}

/** `POST …/asking-choice` — one choice, once. */
export function chooseAsking(choice: string, signal?: AbortSignal) {
  return exerciseRequest<AskingStateView>("/workspaces/current/asking-choice", {
    method: "POST",
    json: { choice },
    signal,
  });
}

/** `POST …/refresh` — design spec §13's one refresh, after the choice. */
export function refreshProfiles(signal?: AbortSignal) {
  return exerciseRequest<RefreshView>("/workspaces/current/refresh", { method: "POST", signal });
}

// ---------------------------------------------------------------------------
// Instructor calls
// ---------------------------------------------------------------------------

export function instructorLogin(passcode: string, signal?: AbortSignal) {
  return exerciseRequest<InstructorSessionView>("/instructor/login", {
    method: "POST",
    json: { passcode },
    signal,
  });
}

export function instructorLogout(signal?: AbortSignal) {
  return exerciseRequest<InstructorSessionView>("/instructor/logout", { method: "POST", signal });
}

export function listDatasets(signal?: AbortSignal) {
  return exerciseRequest<DatasetView[]>("/instructor/datasets", { signal });
}

/** The content type of Ann's Excel workbook, the only file the upload takes. */
export const XLSX_CONTENT_TYPE =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/**
 * `POST /v1/exercise/instructor/datasets?label=…&source_filename=…`.
 *
 * The route takes Ann's workbook (.xlsx) as a raw request body of type
 * `XLSX_CONTENT_TYPE`, with the label and the file name as query parameters.
 * There is no multipart and no `FormData`: FastAPI's multipart parsing needs
 * `python-multipart`, which this repository does not carry (PR #184), and the
 * owner ruled on 2026-09-21 that the raw body stays. The shape is isolated
 * here rather than written into the upload form, so a later change to it is
 * this function and the one screen that calls it.
 */
export function uploadDataset(
  workbook: ArrayBuffer,
  label: string,
  sourceFilename: string | undefined,
  signal?: AbortSignal,
) {
  return exerciseRequest<UploadedDatasetView>("/instructor/datasets", {
    method: "POST",
    rawBody: { body: workbook, contentType: XLSX_CONTENT_TYPE },
    query: { label, source_filename: sourceFilename },
    signal,
  });
}

export function setInviteLimit(datasetId: string, inviteLimit: number, signal?: AbortSignal) {
  return exerciseRequest<DatasetView>(`/instructor/datasets/${encodeURIComponent(datasetId)}`, {
    method: "PATCH",
    json: { invite_limit: inviteLimit },
    signal,
  });
}

export function repointWorkspaces(datasetId: string, signal?: AbortSignal) {
  return exerciseRequest<RepointView>(
    `/instructor/datasets/${encodeURIComponent(datasetId)}/repoint`,
    { method: "POST", signal },
  );
}

/**
 * `GET /v1/exercise/instructor/events` — the unlock panel's list, behind the
 * passcode session alone. Resolved on the server exactly as the unlock is, so
 * `unlocked` is the lock state of the file the button writes to.
 */
export function listInstructorEvents(signal?: AbortSignal) {
  return exerciseRequest<InstructorEventsView>("/instructor/events", { signal });
}

export function unlockResults(eventKey: string, datasetId?: string, signal?: AbortSignal) {
  return exerciseRequest<UnlockView>(
    `/instructor/events/${encodeURIComponent(eventKey)}/unlock`,
    { method: "POST", query: { dataset_id: datasetId }, signal },
  );
}

/**
 * `POST /v1/exercise/instructor/events/{event_key}/lock` — close results for
 * one event again. Nothing is deleted: teams that already ran keep their
 * results; teams that have not are refused until the event is opened again.
 */
export function lockResults(eventKey: string, datasetId?: string, signal?: AbortSignal) {
  return exerciseRequest<LockView>(`/instructor/events/${encodeURIComponent(eventKey)}/lock`, {
    method: "POST",
    query: { dataset_id: datasetId },
    signal,
  });
}

export function listTeamWorkspaces(signal?: AbortSignal) {
  return exerciseRequest<TeamListView>("/instructor/workspaces", { signal });
}

export function readTeamWorkspace(teamNumber: number, datasetId?: string, signal?: AbortSignal) {
  return exerciseRequest<TeamDetailView>(`/instructor/workspaces/${teamNumber}`, {
    query: { dataset_id: datasetId },
    signal,
  });
}

/**
 * `POST /v1/exercise/instructor/workspaces/{team_number}/reset`.
 *
 * The only reset in the product. PR #186 removed the team's own route, which
 * now answers 404, on the owner's ruling of 2026-09-19: the workspace cookie
 * is obtainable by anyone who types a team's number, and Session 2 has no
 * backup. No team screen may render a reset control.
 */
export function resetTeamWorkspace(teamNumber: number, datasetId?: string, signal?: AbortSignal) {
  return exerciseRequest<TeamSummaryView>(`/instructor/workspaces/${teamNumber}/reset`, {
    method: "POST",
    query: { dataset_id: datasetId },
    signal,
  });
}

/** `POST /v1/exercise/instructor/refresh-all` — all teams that have chosen. */
export function refreshAllWorkspaces(signal?: AbortSignal) {
  return exerciseRequest<RefreshAllView>("/instructor/refresh-all", { method: "POST", signal });
}
