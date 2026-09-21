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
}

export interface EventsView {
  readonly events: EventView[];
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
  readonly invite_limit: number;
  readonly setting_name: string | null;
  readonly weights: Record<string, number>;
  /** Ann's plain words for each factor key. The only thing a screen may print. */
  readonly factor_labels: Record<string, string>;
  readonly entries: ListEntryView[];
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
  readonly created_at: string;
}

export interface AskingStateView {
  readonly choice: string | null;
  /** The three ways of asking, as the course names them. Never hard-coded. */
  readonly choices: string[];
  readonly refreshed: boolean;
}

export interface RefreshView {
  readonly choice: string;
  readonly cards_completed: number;
  readonly non_responding: number;
  readonly topics_added: number;
}

export interface RefreshAllView {
  readonly refreshed_team_numbers: number[];
  readonly refreshed: number;
  readonly skipped: number;
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
  /** OQ-CE-09: `null` until Ann provides a sentence. Rendered only when present. */
  readonly license_line: string | null;
}

export interface IngestReportView {
  readonly profile_count: number;
  readonly event_count: number;
  readonly exercise_event_count: number;
  readonly distinct_class_years: string[];
  readonly profiles_missing_major: number;
  readonly profiles_missing_class_year: number;
  readonly profiles_without_card: number;
  readonly distinct_stated_interest_terms: number;
  readonly distinct_topic_tag_terms: number;
  readonly events_without_topic_tags: number;
  readonly discarded_list_entries: number;
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

export interface InstructorSavedSettingView {
  readonly event_key: string;
  readonly name: string;
  readonly created_at: string;
}

export interface ResultRunView {
  readonly event_key: string;
  readonly round: number;
  readonly setting_name: string | null;
  readonly invited_count: number;
  readonly signed_up_count: number;
  readonly attended_count: number;
  readonly seats_empty: number;
  readonly created_at: string;
}

export interface TeamDetailView {
  readonly team_number: number;
  readonly saved_settings: InstructorSavedSettingView[];
  readonly result_runs: ResultRunView[];
}

export interface UnlockView {
  readonly event_key: string;
  readonly unlocked: boolean;
}

export interface RepointView {
  readonly dataset_label: string;
  readonly teams_moved: number;
  readonly teams_discarded: number;
}

// ---------------------------------------------------------------------------
// Team-facing calls
// ---------------------------------------------------------------------------

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

/** `POST …/events/{event_key}/results` — 201, once per team per event. */
export function runResults(eventKey: string, settingName: string | null, signal?: AbortSignal) {
  return exerciseRequest<ResultsView>(
    `/workspaces/current/events/${encodeURIComponent(eventKey)}/results`,
    { method: "POST", json: settingName === null ? {} : { setting_name: settingName }, signal },
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

/**
 * `POST /v1/exercise/instructor/datasets?label=…&source_filename=…`.
 *
 * **The one function that changes if owner decision 2 goes the other way.**
 * The route takes the CSV as a raw `text/csv` request body with the label and
 * the file name as query parameters, because FastAPI's multipart parsing needs
 * `python-multipart`, which this repository does not carry (PR #184, design
 * spec §3's "As shipped" note). Design spec §3 itself asks for multipart. If
 * the owner rules that way, this function and the one screen that calls it are
 * the whole of the change — which is why the shape is isolated here rather
 * than written into the upload form.
 */
export function uploadDataset(
  csv: string,
  label: string,
  sourceFilename: string | undefined,
  signal?: AbortSignal,
) {
  return exerciseRequest<UploadedDatasetView>("/instructor/datasets", {
    method: "POST",
    rawBody: { body: csv, contentType: "text/csv" },
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

export function unlockResults(eventKey: string, datasetId?: string, signal?: AbortSignal) {
  return exerciseRequest<UnlockView>(
    `/instructor/events/${encodeURIComponent(eventKey)}/unlock`,
    { method: "POST", query: { dataset_id: datasetId }, signal },
  );
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
