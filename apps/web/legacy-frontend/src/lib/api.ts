import { resolveBearerToken } from "./bearerToken.ts";

export interface Specialist {
  name: string;
  board_role: string;
  metro_region: string;
  company: string;
  title: string;
  expertise_tags: string;
  initials: string;
}

export interface CppEvent {
  "Event / Program": string;
  Category: string;
  "Recurrence (typical)"?: string;
  "Host / Unit"?: string;
  "Volunteer Roles (fit)"?: string;
  "Primary Audience"?: string;
  "Public URL"?: string;
  "Point(s) of Contact (published)"?: string;
  "Contact Email / Phone (published)"?: string;
}

export interface CrawlerEvent {
  url: string;
  title: string;
  status: "crawling" | "found" | "error" | "done";
  timestamp: string;
  /** Which provider discovered this URL: seed URL list, Gemini grounding, or Tavily search. */
  source?: "seed" | "gemini" | "tavily" | "search";
}

export interface CrawlerResultsResponse {
  events: Array<Record<string, unknown>>;
  count: number;
  source: string;
}

/**
 * A legacy pipeline row as the client is allowed to see it.
 *
 * The legacy `/api/data/pipeline` response also carries `match_score` and
 * `rank`. Both are G1-gated factor-registry outputs
 * (`smartmatch_domain.factor_registry.REGISTRY_STATUS == "proposed"`, where
 * `assert_registry_approved()` still raises), so they are deliberately absent
 * from this type *and* stripped at the fetch boundary by
 * {@link stripG1ScoreFields}: a gate that hides a value it still holds in
 * application state is not closed. Restore them only once G1 is ratified.
 */
export interface PipelineRecord {
  event_name: string;
  speaker_name: string;
  stage: string;
  stage_order: string;
}

/**
 * Drops every G1-gated scoring field from one API row before it can reach
 * application state. Pure — returns a new object, never mutates the input.
 *
 * The rest of each row (stages, dates, names, coverage) is not gated and is
 * carried through untouched, which is why the surrounding requests stay:
 * they exist for the assignment/pipeline list, not for the score.
 */
function stripG1ScoreFields<T>(row: T): T {
  const {
    match_score: _matchScore,
    rank: _rank,
    factor_scores: _factorScores,
    ...rest
  } = row as Record<string, unknown>;
  return rest as T;
}

export interface CalendarRecord {
  "IA Event Date": string;
  Region: string;
  "Nearby Universities": string;
  "Suggested Lecture Window"?: string;
  "Course Alignment"?: string;
}

export type CoverageStatus = "covered" | "partial" | "needs_coverage" | "unknown";
export type RecoveryStatus = "Available" | "Needs Rest" | "Rest Recommended" | "Unknown";

export interface CalendarEventSummary {
  event_id: string;
  event_name: string;
  event_date: string;
  region: string;
  nearby_universities: string[];
  suggested_lecture_window: string;
  coverage_status: CoverageStatus;
  coverage_label: string;
  /** null when the source row carried no ratio — ADR-0011: absent evidence, not a measured zero. */
  coverage_ratio: number | null;
  assigned_volunteers: string[];
  assignment_count: number;
  open_slots: number;
  status_color: string;
}

export interface CalendarAssignmentSummary {
  assignment_id: string;
  event_id: string;
  event_name: string;
  event_date: string;
  region: string;
  volunteer_name: string;
  volunteer_title: string;
  volunteer_company: string;
  stage: string;
  coverage_status: CoverageStatus;
  coverage_label: string;
  /** null when the source record carried no fatigue/recovery signal — ADR-0011: absent evidence, not a measured zero. */
  volunteer_fatigue: number | null;
  recovery_status: RecoveryStatus;
  recovery_label: string;
  /** null when the source record omitted this count — ADR-0011: absent evidence, not a measured zero. */
  recent_assignment_count: number | null;
  days_since_last_assignment: number | null;
  travel_burden: number;
  event_cadence: number;
  status_color: string;
}

export interface VolunteerRecoverySummary {
  volunteer_name: string;
  volunteer_title: string;
  volunteer_company: string;
  event_names: string[];
  event_count: number;
  latest_event_date: string;
  volunteer_fatigue: number;
  recovery_status: RecoveryStatus;
  recovery_label: string;
  recent_assignment_count: number;
  days_since_last_assignment: number | null;
  travel_burden: number;
  event_cadence: number;
}

export interface PocContact extends Record<string, unknown> {}

export interface RankedMatch {
  rank: number;
  name: string;
  title: string;
  company: string;
  board_role: string;
  metro_region: string;
  expertise_tags: string;
  event_id: string;
  event_name: string;
  score: number;
  match_score: number;
  total_score: number;
  volunteer_fatigue?: number;
  recovery_status?: RecoveryStatus;
  recovery_label?: string;
  factor_scores: Record<string, number>;
  weighted_factor_scores: Record<string, number>;
}

export interface MatchScore {
  speaker_name: string;
  event_name: string;
  total_score: number;
  volunteer_fatigue?: number;
  factor_scores: Record<string, number>;
  weighted_factor_scores: Record<string, number>;
}

export interface QrCodeAsset {
  referral_code: string;
  speaker_name: string;
  speaker_title: string;
  speaker_company: string;
  event_name: string;
  generated_at: string;
  destination_url: string;
  scan_url: string;
  /** null when the QR analytics endpoint reported no count for this code — ADR-0011: absent evidence, not a measured zero. */
  scan_count: number | null;
  conversion_count: number | null;
  conversion_rate: number | null;
  last_scanned_at: string;
  qr_svg: string;
  qr_svg_data_url: string;
  qr_png_data_url: string;
  qr_image_url: string;
  download_url: string;
}

export interface QrStatsSummary {
  /** null when the QR analytics endpoint reported no total — ADR-0011: absent evidence, not a measured zero. */
  total_generated: number | null;
  total_scans: number | null;
  total_conversions: number | null;
  conversion_rate: number | null;
  entries: QrCodeAsset[];
}

export type FactorWeights = Record<string, number>;

export interface FeedbackAdjustment {
  factor: string;
  from_weight: number;
  to_weight: number;
  delta: number;
  rationale: string;
}

export interface FeedbackTrendPoint {
  date: string;
  feedback_count: number;
  accepted: number;
  declined: number;
  acceptance_rate: number;
}

export interface FeedbackWeightSnapshot {
  timestamp: string;
  total_feedback: number;
  accepted: number;
  declined: number;
  acceptance_rate: number;
  pain_score: number;
  weights: FactorWeights;
  baseline_weights: FactorWeights;
  adjustments: FeedbackAdjustment[];
}

export interface FeedbackStatsSummary {
  /** null when the feedback-stats endpoint reported no total — ADR-0011: absent evidence, not a measured zero. */
  total_feedback: number | null;
  accepted: number | null;
  declined: number | null;
  acceptance_rate: number | null;
  attended_count: number | null;
  membership_interest_count: number | null;
  membership_interest_rate: number | null;
  average_coordinator_rating: number | null;
  average_match_score_accepted: number | null;
  average_match_score_declined: number | null;
  pain_score: number | null;
  decline_reasons: Array<{ reason: string; count: number }>;
  event_outcomes: Array<{ outcome: string; count: number }>;
  trend: FeedbackTrendPoint[];
  default_weights: FactorWeights;
  current_weights: FactorWeights;
  suggested_weights: FactorWeights;
  recommended_adjustments: FeedbackAdjustment[];
  weight_history: FeedbackWeightSnapshot[];
}

export interface FeedbackSubmitInput {
  event_name: string;
  speaker_name: string;
  decision: "accept" | "decline";
  match_score?: number;
  decline_reason?: string;
  decline_notes?: string;
  event_outcome?: string;
  membership_interest?: boolean;
  coordinator_rating?: number;
  factor_scores?: Record<string, number>;
  weights_used?: FactorWeights;
}

export interface FeedbackSubmitResponse {
  feedback: Record<string, unknown>;
  optimizer_snapshot: FeedbackWeightSnapshot;
}

/**
 * The backend's stable error envelope (`services/api/smartmatch_api/errors.py`,
 * `ErrorEnvelope`): `{ "error": { "code": "...", "message": "...", "details"?: {...} } }`.
 * A 422 populates `details` with `{ fields: [...], field_count: number }`.
 */
interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
  };
}

function isApiErrorEnvelope(payload: unknown): payload is ApiErrorEnvelope {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const error = (payload as { error?: unknown }).error;
  if (!error || typeof error !== "object") {
    return false;
  }
  const { code, message } = error as { code?: unknown; message?: unknown };
  return typeof code === "string" && typeof message === "string";
}

/**
 * Thrown by `requestJson` for any non-2xx response. Carries the HTTP status
 * and the backend's machine-readable `code` (not just a human message) so
 * callers can branch on failure type instead of parsing text.
 */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(message: string, status: number, code: string, details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** Parses the standard error envelope off a failed response and throws {@link ApiRequestError}. */
async function throwApiRequestError(response: Response): Promise<never> {
  let code = "unknown_error";
  let message = `${response.status} ${response.statusText}`;
  let details: Record<string, unknown> | undefined;

  try {
    const payload: unknown = await response.json();
    if (isApiErrorEnvelope(payload)) {
      code = payload.error.code;
      message = payload.error.message;
      details = payload.error.details ?? undefined;
    }
  } catch {
    // Response body was not JSON at all (e.g. a dev-server/proxy HTML error
    // page). Fall back to the status-line message above.
  }

  throw new ApiRequestError(message, response.status, code, details);
}

/** The sessionStorage key the browser may hold a `/v1` bearer token under. */
export const SMARTMATCH_BEARER_STORAGE_KEY = "smartmatch_bearer_token";

/**
 * The bearer token `/v1` requests are sent with, or `null` when none is
 * configured.
 *
 * Two sources: `sessionStorage["smartmatch_bearer_token"]` (the token sign-in
 * stored for this tab) and the build-time `VITE_SMARTMATCH_BEARER_TOKEN` (the
 * fixture token a compose/dev build is started with). The stored one wins —
 * see `resolveBearerToken()` in `src/lib/bearerToken.ts` for why the other
 * order sent every signed-in principal into the coordinator portal. Both are
 * *credentials* — the server decides what they mean. Nothing here, and nothing
 * downstream of here, lets the browser assert a tenant, user, or role; that is
 * the whole point of Fix #7. See `src/lib/session.ts` for the identity the
 * server returns for a token.
 *
 * Exported so `src/lib/principalKey.ts` can derive its cache key from the
 * same lookup rather than keeping a second copy of it.
 */
export function readSmartmatchBearerToken(): string | null {
  const envToken = import.meta.env.VITE_SMARTMATCH_BEARER_TOKEN;
  const sessionToken =
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem(SMARTMATCH_BEARER_STORAGE_KEY)
      : null;

  return resolveBearerToken(envToken, sessionToken);
}

/**
 * Drops the browser-held bearer token.
 *
 * Only clears `sessionStorage`. A token supplied at build time through
 * `VITE_SMARTMATCH_BEARER_TOKEN` is baked into the bundle and cannot be
 * revoked from inside the page — sign-out says so rather than pretending
 * otherwise (`src/lib/session.ts`).
 */
export function clearStoredSmartmatchBearerToken(): void {
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.removeItem(SMARTMATCH_BEARER_STORAGE_KEY);
  }
}

/**
 * Stores the session token `POST /v1/auth/login` just issued.
 *
 * This is the *only* writer of browser storage in the frontend, and what it
 * writes is a **credential**, never an identity. The value is 32 bytes of
 * server-side randomness that mean nothing to the browser: it names no user,
 * no tenant, and above all no role. Who the holder is remains `GET /v1/me`'s
 * answer alone, which is what keeps the archived browser session blob (Fix #7)
 * from returning in a new spelling.
 *
 * `sessionStorage` rather than `localStorage` deliberately: a pilot session
 * should not outlive the tab it was opened in.
 */
export function storeSmartmatchBearerToken(token: string): void {
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.setItem(SMARTMATCH_BEARER_STORAGE_KEY, token);
  }
}

function smartmatchAuthHeaders(): Record<string, string> {
  const token = readSmartmatchBearerToken();

  if (!token) {
    return {};
  }

  return { Authorization: `Bearer ${token}` };
}

/** Whether a bearer token is configured for `/v1` routes. */
export function hasSmartmatchAuth(): boolean {
  return Object.keys(smartmatchAuthHeaders()).length > 0;
}

/** Unit scope for accountable metrics (`GET /v1/units/{unit_id}/metrics`). */
export function getConfiguredUnitId(): string | null {
  const unitId = import.meta.env.VITE_SMARTMATCH_UNIT_ID;
  return typeof unitId === "string" && unitId.trim().length > 0 ? unitId.trim() : null;
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  options?: { authenticated?: boolean },
): Promise<T> {
  // `init` is destructured rather than spread after `headers`, and that ordering
  // is the whole point of this shape.
  //
  // Spreading `...init` *after* a `headers` property does not merge the two:
  // `init.headers` replaces the assembled object wholesale, taking the
  // `Authorization` header with it. The result was a split personality — a
  // request that passed no headers of its own authenticated correctly, while
  // every caller that added one silently sent an anonymous request and got
  // `401 unauthenticated` back from a route it was in fact authorized for.
  // This affected every authenticated write carrying an `Idempotency-Key`.
  //
  // Destructuring makes the ordering impossible to reintroduce: `headers` is no
  // longer a key of `rest`, so no later spread can overwrite it.
  const { headers: initHeaders, ...rest } = init ?? {};
  const response = await fetch(path, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(options?.authenticated ? smartmatchAuthHeaders() : {}),
      ...(initHeaders ?? {}),
    },
  });

  if (!response.ok) {
    await throwApiRequestError(response);
  }

  return (await response.json()) as T;
}

function toObjectRecord(payload: unknown): Record<string, unknown> {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return payload as Record<string, unknown>;
  }
  return {};
}

function toRecordArray(payload: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(payload)) {
    return payload.filter((item): item is Record<string, unknown> => {
      return Boolean(item) && typeof item === "object";
    });
  }

  if (payload && typeof payload === "object") {
    const object = payload as {
      events?: unknown;
      assignments?: unknown;
      entries?: unknown;
      records?: unknown;
      items?: unknown;
      referrals?: unknown;
      referral_codes?: unknown;
      codes?: unknown;
      history?: unknown;
      assets?: unknown;
      qr_codes?: unknown;
      data?: unknown;
    };
    const candidate =
      object.events ??
      object.assignments ??
      object.entries ??
      object.records ??
      object.items ??
      object.referrals ??
      object.referral_codes ??
      object.codes ??
      object.history ??
      object.assets ??
      object.qr_codes ??
      object.data;
    if (Array.isArray(candidate)) {
      return candidate.filter((item): item is Record<string, unknown> => {
        return Boolean(item) && typeof item === "object";
      });
    }
    if (candidate && typeof candidate === "object") {
      return toRecordArray(candidate);
    }
  }

  return [];
}

function extractRecord(payload: unknown): Record<string, unknown> {
  if (Array.isArray(payload)) {
    const first = payload.find((item): item is Record<string, unknown> => {
      return Boolean(item) && typeof item === "object";
    });
    return first ?? {};
  }

  if (payload && typeof payload === "object") {
    const object = payload as Record<string, unknown>;
    const candidate =
      object.data ??
      object.result ??
      object.payload ??
      object.qr ??
      object.asset ??
      object.entry ??
      object.code ??
      object.summary;
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
      return candidate as Record<string, unknown>;
    }
    return object;
  }

  return {};
}

function parseString(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value;
  }
  if (value == null) {
    return fallback;
  }
  return String(value);
}

function parseNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * ADR-0011 seam: parses a numeric field but returns `null` — never a
 * fabricated zero — when the source value is absent or unparsable. Use this
 * (not `parseNumber`) for any field a UI surface renders as a measurement
 * (metric tile, rate, count, progress bar, score).
 */
function parseNumberOrNull(value: unknown): number | null {
  if (value == null) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((entry) => parseString(entry).trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return splitTags(value);
  }
  return [];
}

function parseNumberMap(value: unknown): FactorWeights {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return Object.entries(value as Record<string, unknown>).reduce<FactorWeights>((acc, [key, raw]) => {
    const parsed = parseNumber(raw, Number.NaN);
    if (Number.isFinite(parsed)) {
      acc[key] = parsed;
    }
    return acc;
  }, {});
}

function normalizeCoverageStatus(value: unknown): CoverageStatus {
  const raw = parseString(value).trim().toLowerCase();
  if (raw === "covered" || raw === "full" || raw === "assigned") {
    return "covered";
  }
  if (raw === "partial" || raw === "partially covered") {
    return "partial";
  }
  if (raw === "needs_match" || raw === "needs coverage" || raw === "needs_coverage" || raw === "open" || raw === "unassigned") {
    return "needs_coverage";
  }
  return "unknown";
}

function coverageLabel(status: CoverageStatus): string {
  switch (status) {
    case "covered":
      return "IA covered";
    case "partial":
      return "Partial coverage";
    case "needs_coverage":
      return "Needs volunteers";
    default:
      return "Coverage pending";
  }
}

function coverageTone(status: CoverageStatus): string {
  switch (status) {
    case "covered":
      return "#005394";
    case "partial":
      return "#c47c00";
    case "needs_coverage":
      return "#d14343";
    default:
      return "#5a6472";
  }
}

function normalizeRecoveryStatus(value: unknown, score?: number): RecoveryStatus {
  const raw = parseString(value).trim().toLowerCase();
  if (raw === "available" || raw === "fresh") {
    return "Available";
  }
  if (raw === "needs rest" || raw === "steady" || raw === "busy") {
    return "Needs Rest";
  }
  if (raw === "on cooldown" || raw === "at risk" || raw === "cooldown" || raw === "rest recommended") {
    return "Rest Recommended";
  }
  if (typeof score === "number") {
    if (score >= 0.75) {
      return "Rest Recommended";
    }
    if (score >= 0.4) {
      return "Needs Rest";
    }
    return "Available";
  }
  return "Unknown";
}

function recoveryLabel(status: RecoveryStatus): string {
  switch (status) {
    case "Available":
      return "Available";
    case "Needs Rest":
      return "Needs Rest";
    case "Rest Recommended":
      return "Rest Recommended";
    default:
      return "Recovery unknown";
  }
}

function recoveryTone(status: RecoveryStatus): string {
  switch (status) {
    case "Available":
      return "#0f766e";
    case "Needs Rest":
      return "#c47c00";
    case "Rest Recommended":
      return "#b91c1c";
    default:
      return "#5a6472";
  }
}

function normalizeFatigue(value: unknown, fallback = 0): number {
  const parsed = parseNumber(value, fallback);
  if (parsed > 1) {
    return clamp(parsed / 100, 0, 1);
  }
  return clamp(parsed, 0, 1);
}

/**
 * ADR-0011 seam: like `normalizeFatigue`, but returns `null` — never a
 * fabricated zero — when no fatigue/recovery signal is present at all.
 */
function normalizeFatigueOrNull(value: unknown): number | null {
  const parsed = parseNumberOrNull(value);
  if (parsed === null) {
    return null;
  }
  if (parsed > 1) {
    return clamp(parsed / 100, 0, 1);
  }
  return clamp(parsed, 0, 1);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeCalendarEvent(record: Record<string, unknown>, index: number): CalendarEventSummary {
  const eventName = parseString(record.event_name ?? record["Event / Program"] ?? record.title ?? `Event ${index + 1}`);
  const coverageStatus = normalizeCoverageStatus(
    record.coverage_status ?? record.assignment_status ?? record.status ?? record.coverage,
  );
  const assignedVolunteers = parseStringArray(
    record.assigned_volunteers ?? record.assignedVolunteers ?? record.volunteers ?? record.assignees,
  );
  // ADR-0011: a source row that carried no coverage ratio has an *unknown*
  // ratio. The old fallback manufactured one from the status string (covered
  // -> 1, partial -> 0.5, anything else -> 0), which turned a categorical
  // label into a measurement the source never made — and, for the common
  // case, drew "we were not told" as a hard 0.
  const coverageRatioValue = parseNumber(record.coverage_ratio ?? record.coverage_percentage ?? record.coveragePercent, Number.NaN);
  const coverageRatio: number | null =
    Number.isFinite(coverageRatioValue)
      ? clamp(coverageRatioValue > 1 ? coverageRatioValue / 100 : coverageRatioValue, 0, 1)
      : null;
  const assignmentCount = Math.max(
    parseNumber(record.assignment_count ?? record.assigned_count ?? assignedVolunteers.length, assignedVolunteers.length),
    assignedVolunteers.length,
  );
  const openSlots = Math.max(
    parseNumber(record.open_slots ?? record.slots_open ?? record.openSlots, 0),
    0,
  );

  return {
    event_id: parseString(record.event_id ?? record.id ?? `${eventName}-${index}`),
    event_name: eventName,
    event_date: parseString(record.event_date ?? record["IA Event Date"] ?? record.date ?? ""),
    region: parseString(record.region ?? record.Region ?? record.location ?? "West Coast"),
    nearby_universities: parseStringArray(
      record.nearby_universities ?? record["Nearby Universities"] ?? record.nearbyUniversities,
    ),
    suggested_lecture_window: parseString(
      record.suggested_lecture_window ?? record["Suggested Lecture Window"] ?? record.window,
      "Window TBD",
    ),
    coverage_status: coverageStatus,
    coverage_label: parseString(record.coverage_label ?? record.status_label, coverageLabel(coverageStatus)),
    coverage_ratio: coverageRatio,
    assigned_volunteers: assignedVolunteers,
    assignment_count: assignmentCount,
    open_slots: openSlots,
    status_color: parseString(record.status_color ?? record.color ?? coverageTone(coverageStatus)),
  };
}

function normalizeCalendarAssignment(record: Record<string, unknown>, index: number): CalendarAssignmentSummary {
  const volunteerFatigue = normalizeFatigueOrNull(
    record.volunteer_fatigue ?? record.fatigue_score ?? record.fatigue ?? record.recovery_score,
  );
  const recoveryStatus = normalizeRecoveryStatus(
    record.recovery_status ?? record.recoveryState,
    volunteerFatigue ?? undefined,
  );
  const coverageStatus = normalizeCoverageStatus(
    record.coverage_status ?? record.assignment_status ?? record.status ?? record.coverage,
  );

  return {
    assignment_id: parseString(record.assignment_id ?? record.id ?? `${parseString(record.event_name ?? record["Event / Program"] ?? "assignment")}-${parseString(record.volunteer_name ?? record.speaker_name ?? record.name ?? index)}`),
    event_id: parseString(record.event_id ?? record.eventId ?? `${parseString(record.event_name ?? record["Event / Program"] ?? "event")}-${index}`),
    event_name: parseString(record.event_name ?? record["Event / Program"] ?? record.title ?? ""),
    event_date: parseString(record.event_date ?? record.date ?? record["IA Event Date"] ?? ""),
    region: parseString(record.region ?? record.Region ?? record.location ?? "West Coast"),
    volunteer_name: parseString(record.volunteer_name ?? record.speaker_name ?? record.name ?? ""),
    volunteer_title: parseString(record.volunteer_title ?? record.title ?? record.speaker_title ?? ""),
    volunteer_company: parseString(record.volunteer_company ?? record.company ?? record.speaker_company ?? ""),
    stage: parseString(record.stage ?? record.assignment_stage ?? "Matched"),
    coverage_status: coverageStatus,
    coverage_label: parseString(record.coverage_label ?? record.status_label, coverageLabel(coverageStatus)),
    volunteer_fatigue: volunteerFatigue,
    recovery_status: recoveryStatus,
    recovery_label: parseString(record.recovery_label ?? record.recoveryLabel, recoveryLabel(recoveryStatus)),
    recent_assignment_count: parseNumberOrNull(
      record.recent_assignment_count ?? record.recentAssignments ?? record.assignment_count,
    ),
    days_since_last_assignment:
      record.days_since_last_assignment == null && record.daysSinceLastAssignment == null
        ? null
        : parseNumber(record.days_since_last_assignment ?? record.daysSinceLastAssignment, 0),
    travel_burden: parseNumber(record.travel_burden ?? record.regional_travel_burden ?? record.travelBurden, 0),
    event_cadence: parseNumber(record.event_cadence ?? record.cadence ?? record.eventCadence, 0),
    status_color: parseString(record.status_color ?? record.color ?? recoveryTone(recoveryStatus)),
  };
}

function normalizeVolunteerRecovery(record: Record<string, unknown>, assignments: CalendarAssignmentSummary[]): VolunteerRecoverySummary {
  const volunteerName = parseString(record.volunteer_name ?? record.speaker_name ?? record.name ?? "");
  const volunteerAssignments = assignments.filter(
    (assignment) => assignment.volunteer_name.trim().toLowerCase() === volunteerName.trim().toLowerCase(),
  );
  const latestEventDate = volunteerAssignments
    .map((assignment) => assignment.event_date)
    .filter(Boolean)
    .sort();
  const lastEventDate = latestEventDate[latestEventDate.length - 1] ?? "";
  // VolunteerRecoverySummary is not currently rendered by any page (see the
  // Z1 inventory); this field keeps its plain-number shape, but the average
  // below must still ignore assignments with no fatigue evidence rather than
  // silently treating a missing value as 0.
  const knownFatigueAssignments = volunteerAssignments.filter(
    (assignment): assignment is CalendarAssignmentSummary & { volunteer_fatigue: number } =>
      assignment.volunteer_fatigue !== null,
  );
  const volunteerFatigue = knownFatigueAssignments.length
    ? knownFatigueAssignments.reduce((sum, assignment) => sum + assignment.volunteer_fatigue, 0) /
      knownFatigueAssignments.length
    : normalizeFatigue(record.volunteer_fatigue ?? record.fatigue_score ?? 0);
  const recoveryStatus = normalizeRecoveryStatus(
    record.recovery_status ?? record.recoveryState ?? volunteerAssignments[0]?.recovery_status,
    volunteerFatigue,
  );

  return {
    volunteer_name: volunteerName,
    volunteer_title: parseString(record.volunteer_title ?? record.title ?? record.speaker_title ?? ""),
    volunteer_company: parseString(record.volunteer_company ?? record.company ?? record.speaker_company ?? ""),
    event_names: [...new Set(volunteerAssignments.map((assignment) => assignment.event_name).filter(Boolean))],
    event_count: volunteerAssignments.length,
    latest_event_date: lastEventDate,
    volunteer_fatigue: volunteerFatigue,
    recovery_status: recoveryStatus,
    recovery_label: parseString(record.recovery_label ?? record.recoveryLabel, recoveryLabel(recoveryStatus)),
    recent_assignment_count: parseNumber(record.recent_assignment_count ?? record.recentAssignments ?? volunteerAssignments.length, volunteerAssignments.length),
    days_since_last_assignment:
      record.days_since_last_assignment == null && record.daysSinceLastAssignment == null
        ? null
        : parseNumber(record.days_since_last_assignment ?? record.daysSinceLastAssignment, 0),
    travel_burden: parseNumber(record.travel_burden ?? record.regional_travel_burden ?? 0, 0),
    event_cadence: parseNumber(record.event_cadence ?? record.cadence ?? 0, 0),
  };
}
function normalizeRankedMatch(payload: Partial<RankedMatch> & Record<string, unknown>): RankedMatch {
  const factorScores = (payload.factor_scores ?? {}) as Record<string, number>;
  const weightedFactorScores = (payload.weighted_factor_scores ?? {}) as Record<string, number>;
  const rawScoreValue =
    Number(payload.score ?? payload.match_score ?? payload.total_score ?? 0) || 0;
  // Normalize to 0-1 range: if backend returned 0-100 scale, convert down.
  const rawScore = rawScoreValue > 1 ? rawScoreValue / 100 : rawScoreValue;
  const volunteerFatigue = normalizeFatigue(
    payload.volunteer_fatigue ?? factorScores.volunteer_fatigue ?? 0,
  );

  if (factorScores.volunteer_fatigue == null) {
    factorScores.volunteer_fatigue = volunteerFatigue;
  }
  if (weightedFactorScores.volunteer_fatigue == null && payload.weighted_factor_scores) {
    weightedFactorScores.volunteer_fatigue = volunteerFatigue;
  }

  return {
    rank: Number(payload.rank ?? 0) || 0,
    name: String(payload.name ?? payload.speaker_name ?? ""),
    title: String(payload.title ?? payload.speaker_title ?? ""),
    company: String(payload.company ?? payload.speaker_company ?? ""),
    board_role: String(payload.board_role ?? payload.speaker_board_role ?? ""),
    metro_region: String(payload.metro_region ?? payload.speaker_metro_region ?? ""),
    expertise_tags: String(payload.expertise_tags ?? payload.speaker_expertise_tags ?? ""),
    event_id: String(payload.event_id ?? ""),
    event_name: String(payload.event_name ?? ""),
    score: rawScore,
    match_score: rawScore,
    total_score: rawScore,
    volunteer_fatigue: volunteerFatigue,
    recovery_status: normalizeRecoveryStatus(payload.recovery_status ?? payload.recoveryState, volunteerFatigue),
    recovery_label: parseString(
      payload.recovery_label ?? payload.recoveryLabel,
      recoveryLabel(normalizeRecoveryStatus(payload.recovery_status ?? payload.recoveryState, volunteerFatigue)),
    ),
    factor_scores: factorScores,
    weighted_factor_scores: weightedFactorScores,
  };
}

function normalizeQrCodeAsset(payload: unknown, index = 0): QrCodeAsset {
  const record = extractRecord(payload);
  const conversionCountRaw = parseNumberOrNull(
    record.conversion_count ??
      record.conversions ??
      record.member_inquiry_count ??
      record.membership_interest_count,
  );
  const conversionCount = conversionCountRaw === null ? null : Math.max(conversionCountRaw, 0);
  const scanCountRaw = parseNumberOrNull(record.scan_count ?? record.scans ?? record.total_scans);
  const scanCount = scanCountRaw === null ? null : Math.max(scanCountRaw, 0);
  const conversionRateValue = parseNumberOrNull(
    record.conversion_rate ?? record.conversionRate ?? record.roi_rate,
  );
  // A rate needs a denominator: with no scans (real or unknown), there is no
  // ratio to report, so the derived rate is null rather than a fabricated 0.
  const derivedConversionRate =
    scanCount !== null && scanCount > 0 && conversionCount !== null ? conversionCount / scanCount : null;
  const normalizedConversionRate =
    conversionRateValue !== null
      ? clamp(conversionRateValue > 1 ? conversionRateValue / 100 : conversionRateValue, 0, 1)
      : derivedConversionRate !== null
        ? clamp(derivedConversionRate, 0, 1)
        : null;

  return {
    referral_code: parseString(
      record.referral_code ?? record.referralCode ?? record.code ?? record.slug,
      `${parseString(record.speaker_name ?? record.name ?? "qr")}-${parseString(
        record.event_name ?? record.event ?? index,
      )}`,
    ),
    speaker_name: parseString(record.speaker_name ?? record.speaker ?? record.name ?? ""),
    speaker_title: parseString(record.speaker_title ?? record.title ?? record.speakerTitle ?? ""),
    speaker_company: parseString(record.speaker_company ?? record.company ?? record.speakerCompany ?? ""),
    event_name: parseString(record.event_name ?? record.event ?? record["Event / Program"] ?? ""),
    generated_at: parseString(record.generated_at ?? record.created_at ?? record.createdAt ?? ""),
    destination_url: parseString(
      record.destination_url ?? record.destinationUrl ?? record.landing_url ?? record.redirect_url ?? "",
    ),
    scan_url: parseString(record.scan_url ?? record.scanUrl ?? record.redirect_url ?? record.url ?? ""),
    scan_count: scanCount,
    conversion_count: conversionCount,
    conversion_rate: normalizedConversionRate,
    last_scanned_at: parseString(record.last_scanned_at ?? record.lastScanAt ?? record.latest_scan_at ?? ""),
    qr_svg: parseString(record.qr_svg ?? record.svg ?? record.qrMarkup ?? ""),
    qr_svg_data_url: parseString(record.qr_svg_data_url ?? record.svg_data_url ?? ""),
    qr_png_data_url: parseString(
      record.qr_png_data_url ??
        record.png_data_url ??
        record.qr_data_url ??
        (record.qr_png_base64 ? `data:image/png;base64,${parseString(record.qr_png_base64)}` : ""),
    ),
    qr_image_url: parseString(record.qr_image_url ?? record.image_url ?? record.imageUrl ?? record.qr_url ?? ""),
    download_url: parseString(
      record.download_url ?? record.asset_url ?? record.downloadUrl ?? record.qr_data_url ?? "",
    ),
  };
}

function normalizeQrStats(payload: unknown): QrStatsSummary {
  const source = extractRecord(payload);
  const entries = toRecordArray(payload)
    .map((record, index) => normalizeQrCodeAsset(record, index))
    .sort((left, right) => {
      const leftTime = Date.parse(left.last_scanned_at || left.generated_at || "");
      const rightTime = Date.parse(right.last_scanned_at || right.generated_at || "");
      return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
    });
  // Entries carry their own null-safe counts (see normalizeQrCodeAsset); a
  // derived sum is only meaningful once every entry actually reports one.
  const entryScanCounts = entries.map((entry) => entry.scan_count);
  const entryConversionCounts = entries.map((entry) => entry.conversion_count);
  const allEntryScansKnown = entries.length > 0 && entryScanCounts.every((value) => value !== null);
  const allEntryConversionsKnown = entries.length > 0 && entryConversionCounts.every((value) => value !== null);

  const totalGenerated =
    parseNumberOrNull(
      source.total_generated ??
        source.generated_count ??
        source.codes_generated ??
        source.referral_count ??
        source.total_codes,
    ) ?? (entries.length > 0 ? entries.length : null);
  const totalScans =
    parseNumberOrNull(source.total_scans ?? source.scan_count ?? source.scans ?? source.total_visits) ??
    (allEntryScansKnown
      ? (entryScanCounts as number[]).reduce((sum, value) => sum + value, 0)
      : null);
  const totalConversions =
    parseNumberOrNull(
      source.total_conversions ??
        source.conversion_count ??
        source.conversions ??
        source.total_inquiries ??
        source.membership_interest_count,
    ) ??
    (allEntryConversionsKnown
      ? (entryConversionCounts as number[]).reduce((sum, value) => sum + value, 0)
      : null);
  const conversionRateValue = parseNumberOrNull(
    source.conversion_rate ?? source.conversionRate ?? source.roi_rate,
  );
  // No scans (real or unknown) means no ratio to report — null, not a
  // fabricated 0.
  const derivedConversionRate =
    totalScans !== null && totalScans > 0 && totalConversions !== null
      ? totalConversions / totalScans
      : null;

  return {
    total_generated: totalGenerated,
    total_scans: totalScans,
    total_conversions: totalConversions,
    conversion_rate:
      conversionRateValue !== null
        ? clamp(conversionRateValue > 1 ? conversionRateValue / 100 : conversionRateValue, 0, 1)
        : derivedConversionRate !== null
          ? clamp(derivedConversionRate, 0, 1)
          : null,
    entries,
  };
}

function normalizeFeedbackAdjustment(payload: unknown): FeedbackAdjustment {
  const record = extractRecord(payload);
  return {
    factor: parseString(record.factor ?? record.key ?? "unknown"),
    from_weight: parseNumber(record.from_weight ?? record.fromWeight ?? 0, 0),
    to_weight: parseNumber(record.to_weight ?? record.toWeight ?? 0, 0),
    delta: parseNumber(record.delta ?? 0, 0),
    rationale: parseString(record.rationale ?? record.reason ?? ""),
  };
}

function normalizeFeedbackTrend(payload: unknown): FeedbackTrendPoint {
  const record = extractRecord(payload);
  return {
    date: parseString(record.date ?? record.timestamp ?? ""),
    feedback_count: parseNumber(record.feedback_count ?? record.count ?? 0, 0),
    accepted: parseNumber(record.accepted ?? 0, 0),
    declined: parseNumber(record.declined ?? 0, 0),
    acceptance_rate: clamp(
      parseNumber(record.acceptance_rate ?? record.rate ?? 0, 0),
      0,
      1,
    ),
  };
}

function normalizeFeedbackWeightSnapshot(payload: unknown): FeedbackWeightSnapshot {
  const record = extractRecord(payload);
  return {
    timestamp: parseString(record.timestamp ?? record.created_at ?? ""),
    total_feedback: parseNumber(record.total_feedback ?? record.total ?? 0, 0),
    accepted: parseNumber(record.accepted ?? 0, 0),
    declined: parseNumber(record.declined ?? 0, 0),
    acceptance_rate: clamp(parseNumber(record.acceptance_rate ?? 0, 0), 0, 1),
    pain_score: parseNumber(record.pain_score ?? 0, 0),
    weights: parseNumberMap(record.weights),
    baseline_weights: parseNumberMap(record.baseline_weights ?? record.default_weights),
    adjustments: toRecordArray(record.adjustments).map(normalizeFeedbackAdjustment),
  };
}

function normalizeFeedbackStats(payload: unknown): FeedbackStatsSummary {
  const record = extractRecord(payload);
  const trend = toRecordArray(record.trend).map(normalizeFeedbackTrend);
  const declineReasons = toRecordArray(record.decline_reasons).map((entry) => ({
    reason: parseString(entry.reason ?? entry.label ?? ""),
    count: parseNumber(entry.count ?? entry.value ?? 0, 0),
  }));
  const eventOutcomes = toRecordArray(record.event_outcomes).map((entry) => ({
    outcome: parseString(entry.outcome ?? entry.label ?? ""),
    count: parseNumber(entry.count ?? entry.value ?? 0, 0),
  }));
  const weightHistory = toRecordArray(record.weight_history).map(normalizeFeedbackWeightSnapshot);
  const recommendedAdjustments = toRecordArray(record.recommended_adjustments).map(
    normalizeFeedbackAdjustment,
  );

  const acceptanceRateRaw = parseNumberOrNull(record.acceptance_rate);
  const membershipInterestRateRaw = parseNumberOrNull(
    record.membership_interest_rate ?? record.conversion_rate,
  );

  return {
    total_feedback: parseNumberOrNull(record.total_feedback ?? record.total),
    accepted: parseNumberOrNull(record.accepted),
    declined: parseNumberOrNull(record.declined),
    acceptance_rate: acceptanceRateRaw === null ? null : clamp(acceptanceRateRaw, 0, 1),
    attended_count: parseNumberOrNull(record.attended_count),
    membership_interest_count: parseNumberOrNull(
      record.membership_interest_count ?? record.total_conversions,
    ),
    membership_interest_rate:
      membershipInterestRateRaw === null ? null : clamp(membershipInterestRateRaw, 0, 1),
    average_coordinator_rating: parseNumberOrNull(record.average_coordinator_rating),
    average_match_score_accepted: parseNumberOrNull(record.average_match_score_accepted),
    average_match_score_declined: parseNumberOrNull(record.average_match_score_declined),
    pain_score: parseNumberOrNull(record.pain_score),
    decline_reasons: declineReasons,
    event_outcomes: eventOutcomes,
    trend,
    default_weights: parseNumberMap(record.default_weights),
    current_weights: parseNumberMap(record.current_weights),
    suggested_weights: parseNumberMap(record.suggested_weights ?? record.current_weights),
    recommended_adjustments: recommendedAdjustments,
    weight_history: weightHistory,
  };
}

export function splitTags(raw: string): string[] {
  return raw
    .split(/[;,]/)
    .map((value) => value.trim())
    .filter(Boolean);
}

export interface WithSource<T> {
  data: T;
  source: "live" | "demo" | "csv";
  isMockData: boolean;
}

export async function fetchSpecialists(): Promise<WithSource<Specialist[]>> {
  const raw = await requestJson<unknown>("/api/data/specialists");
  const payload = toRecordArray(raw);
  const rawSource = payload[0]?.source;
  const source: "live" | "demo" | "csv" = rawSource === "demo" ? "demo" : rawSource === "csv" ? "csv" : "live";
  return { data: payload as unknown as Specialist[], source, isMockData: source !== "live" };
}

export async function fetchEvents(): Promise<WithSource<CppEvent[]>> {
  const raw = await requestJson<unknown>("/api/data/events");
  const payload = toRecordArray(raw);
  const rawSource = payload[0]?.source;
  const source: "live" | "demo" | "csv" = rawSource === "demo" ? "demo" : rawSource === "csv" ? "csv" : "live";
  return { data: payload as unknown as CppEvent[], source, isMockData: source !== "live" };
}

export async function fetchPipeline(): Promise<WithSource<PipelineRecord[]>> {
  const raw = await requestJson<unknown>("/api/data/pipeline");
  const payload = toRecordArray(raw);
  const rawSource = payload[0]?.source;
  const source: "live" | "demo" | "csv" = rawSource === "demo" ? "demo" : rawSource === "csv" ? "csv" : "live";
  // G1 fail-closed: `match_score`/`rank` never leave this boundary.
  const rows = payload.map((row) => stripG1ScoreFields(row)) as unknown as PipelineRecord[];
  return { data: rows, source, isMockData: source !== "live" };
}

export async function fetchCalendar(): Promise<CalendarRecord[]> {
  return requestJson<CalendarRecord[]>("/api/data/calendar");
}

export async function fetchCalendarEvents(): Promise<WithSource<CalendarEventSummary[]>> {
  const payload = await requestJson<unknown>("/api/calendar/events");
  const rows = toRecordArray(payload);
  const rawSource = (rows[0] as Record<string, unknown>)?.source;
  const source: "live" | "demo" | "csv" = rawSource === "demo" ? "demo" : rawSource === "csv" ? "csv" : "live";
  return { data: rows.map((record, index) => normalizeCalendarEvent(record, index)), source, isMockData: source !== "live" };
}

export async function fetchCalendarAssignments(): Promise<WithSource<CalendarAssignmentSummary[]>> {
  const payload = await requestJson<unknown>("/api/calendar/assignments");
  const rows = toRecordArray(payload);
  const rawSource = (rows[0] as Record<string, unknown>)?.source;
  const source: "live" | "demo" | "csv" = rawSource === "demo" ? "demo" : rawSource === "csv" ? "csv" : "live";
  return { data: rows.map((record, index) => normalizeCalendarAssignment(record, index)), source, isMockData: source !== "live" };
}

export async function fetchVolunteerRecovery(): Promise<VolunteerRecoverySummary[]> {
  const { data: assignments } = await fetchCalendarAssignments();
  const byVolunteer = new Map<string, Record<string, unknown>>();

  for (const assignment of assignments) {
    const key = assignment.volunteer_name.trim().toLowerCase();
    if (!byVolunteer.has(key)) {
      byVolunteer.set(key, {
        volunteer_name: assignment.volunteer_name,
        volunteer_title: assignment.volunteer_title,
        volunteer_company: assignment.volunteer_company,
        recovery_status: assignment.recovery_status,
        recovery_label: assignment.recovery_label,
        volunteer_fatigue: assignment.volunteer_fatigue,
        recent_assignment_count: assignment.recent_assignment_count,
        days_since_last_assignment: assignment.days_since_last_assignment,
        travel_burden: assignment.travel_burden,
        event_cadence: assignment.event_cadence,
      });
    }
  }

  return Array.from(byVolunteer.values()).map((record) =>
    normalizeVolunteerRecovery(record, assignments),
  );
}

export async function fetchContacts(): Promise<PocContact[]> {
  return requestJson<PocContact[]>("/api/data/contacts");
}

/**
 * Placeholder used before the first fetch resolves or after a failed fetch.
 * All numeric fields are `null` — ADR-0011: this is "no evidence yet," never
 * a measured zero. Callers gate rendering on an `*Available` flag rather than
 * inferring availability from these values.
 */
export function emptyQrStatsSummary(): QrStatsSummary {
  return {
    total_generated: null,
    total_scans: null,
    total_conversions: null,
    conversion_rate: null,
    entries: [],
  };
}

/** See `emptyQrStatsSummary` — same "no evidence yet" contract. */
export function emptyFeedbackStatsSummary(): FeedbackStatsSummary {
  return {
    total_feedback: null,
    accepted: null,
    declined: null,
    acceptance_rate: null,
    attended_count: null,
    membership_interest_count: null,
    membership_interest_rate: null,
    average_coordinator_rating: null,
    average_match_score_accepted: null,
    average_match_score_declined: null,
    pain_score: null,
    decline_reasons: [],
    event_outcomes: [],
    trend: [],
    default_weights: {},
    current_weights: {},
    suggested_weights: {},
    recommended_adjustments: [],
    weight_history: [],
  };
}

export async function fetchQrStats(): Promise<WithSource<QrStatsSummary>> {
  const payload = await requestJson<Record<string, unknown>>("/api/qr/stats");
  const rawSource = payload?.source;
  const source: "live" | "demo" | "csv" = rawSource === "demo" ? "demo" : rawSource === "csv" ? "csv" : "live";
  return { data: normalizeQrStats(payload), source, isMockData: source !== "live" };
}

export async function fetchFeedbackStats(): Promise<WithSource<FeedbackStatsSummary>> {
  const payload = await requestJson<Record<string, unknown>>("/api/feedback/stats");
  const rawSource = payload?.source;
  const source: "live" | "demo" | "csv" = rawSource === "demo" ? "demo" : rawSource === "csv" ? "csv" : "live";
  return { data: normalizeFeedbackStats(payload), source, isMockData: source !== "live" };
}

export async function submitFeedback(
  input: FeedbackSubmitInput,
): Promise<FeedbackSubmitResponse> {
  const payload = await requestJson<unknown>("/api/feedback/submit", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const record = extractRecord(payload);
  return {
    feedback: toObjectRecord(record.feedback),
    optimizer_snapshot: normalizeFeedbackWeightSnapshot(record.optimizer_snapshot),
  };
}

export async function generateQrAsset(
  speakerName: string,
  eventName: string,
): Promise<QrCodeAsset | null> {
  const payload = await requestJson<unknown>("/api/qr/generate", {
    method: "POST",
    body: JSON.stringify({
      speaker_name: speakerName,
      event_name: eventName,
    }),
  });
  const asset = normalizeQrCodeAsset(payload);
  if (
    !asset.referral_code &&
    !asset.scan_url &&
    !asset.qr_svg &&
    !asset.qr_svg_data_url &&
    !asset.qr_png_data_url &&
    !asset.qr_image_url &&
    !asset.download_url
  ) {
    return null;
  }
  return asset;
}

export async function rankSpeakers(
  eventName: string,
  limit = 5,
  weights?: FactorWeights,
): Promise<RankedMatch[]> {
  const payload = await requestJson<Array<Record<string, unknown>>>("/api/matching/rank", {
    method: "POST",
    body: JSON.stringify({
      event_name: eventName,
      limit,
      weights,
    }),
  });

  return payload.map(normalizeRankedMatch);
}

export async function scoreSpeaker(
  speakerName: string,
  eventName: string,
  weights?: FactorWeights,
): Promise<MatchScore> {
  return requestJson<MatchScore>("/api/matching/score", {
    method: "POST",
    body: JSON.stringify({
      speaker_name: speakerName,
      event_name: eventName,
      weights,
    }),
  }).then((payload) => {
    const fatigue = normalizeFatigue(
      (payload as Partial<MatchScore> & Record<string, unknown>).volunteer_fatigue ?? 0,
    );
    return {
      ...payload,
      volunteer_fatigue: fatigue,
    };
  });
}

export interface CppCourse {
  course_key: string;
  display_name: string;
  Instructor: string;
  Course: string;
  Section: string;
  Title: string;
  Days: string;
  "Start Time": string;
  "End Time": string;
  "Enrl Cap": number;
  Mode: string;
  "Guest Lecture Fit": string;
  source: string;
}

export async function fetchCourses(): Promise<CppCourse[]> {
  const raw = await requestJson<unknown>("/api/data/courses");
  return toRecordArray(raw) as unknown as CppCourse[];
}

export async function rankSpeakersForCourse(
  courseKey: string,
  limit = 5,
  weights?: FactorWeights,
): Promise<RankedMatch[]> {
  const payload = await requestJson<Array<Record<string, unknown>>>("/api/matching/rank-for-course", {
    method: "POST",
    body: JSON.stringify({ course_key: courseKey, limit, weights }),
  });
  return payload.map(normalizeRankedMatch);
}

export async function startCrawl(): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/api/crawler/start", {
    method: "POST",
  });
}

export async function fetchCrawlerResults(): Promise<CrawlerResultsResponse> {
  return requestJson<CrawlerResultsResponse>("/api/crawler/results");
}

export async function clearCrawlerResults(): Promise<{ deleted: number; status: string }> {
  return requestJson<{ deleted: number; status: string }>("/api/crawler/results", {
    method: "DELETE",
  });
}

export interface CrawlerVisitedUrl {
  url: string;
  source: "seed" | "gemini" | "tavily";
  title: string;
  timestamp: string;
}

export interface CrawlerStatusResponse {
  state: "idle" | "running" | "done";
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  visited_count?: number;
  visited_urls?: CrawlerVisitedUrl[];
}

export async function fetchCrawlerStatus(): Promise<CrawlerStatusResponse> {
  return requestJson<CrawlerStatusResponse>("/api/crawler/status");
}

export interface UniversityContact {
  name: string;
  email: string;
  host_unit: string;
  event_name: string;
  source: "university";
}

export async function fetchUniversityContacts(): Promise<UniversityContact[]> {
  try {
    const data = await requestJson<unknown>("/api/data/university-contacts");
    return Array.isArray(data) ? (data as UniversityContact[]) : [];
  } catch {
    return [];
  }
}

// --- Portal types ---
export interface StudentProfile {
  student_id: string;
  name: string;
  email: string;
  school: string;
  major: string;
  year: string;
  interests: string;
  attendance_streak: number;
  events_attended: number;
  churn_risk: "low" | "medium" | "high";
  membership_interest: boolean;
  suggested_connections: string;
  source?: string;
}

export interface EventCoordinator {
  coordinator_id: string;
  name: string;
  email: string;
  school: string;
  department: string;
  hosted_events: string;
  contact_status: "active" | "pending" | "new";
  last_contact_date: string;
  meeting_availability: string;
  source?: string;
}

export interface StudentRegistration {
  registration_id: string;
  student_id: string;
  event_id: string;
  event_name: string;
  registered_at: string;
  /** Event date from calendar_events (YYYY-MM-DD), when available. */
  event_date?: string | null;
  status: "registered" | "attended" | "cancelled";
  check_in_time: string | null;
  check_out_time: string | null;
  source?: string;
}

export interface AttendedEventRef {
  event_id: string;
  event_name: string;
}

export interface StudentConnectionSuggestion {
  peer_student_id: string;
  name: string;
  school: string;
  major: string;
  interests: string;
  shared_events: AttendedEventRef[];
  shared_event_count: number;
}

export interface StudentConnectionSuggestionsResponse {
  student_id: string;
  attended_past_events: AttendedEventRef[];
  suggestions: StudentConnectionSuggestion[];
  total: number;
  source: string;
}

export interface StudentSpeakerSuggestion {
  speaker_name: string;
  speaker_title: string;
  speaker_company: string;
  board_role: string;
  metro_region: string;
  expertise_tags: string;
  shared_events: AttendedEventRef[];
  shared_event_count: number;
}

export interface OutreachThread {
  thread_id: string;
  coordinator_id: string;
  event_id: string;
  ia_contact: string;
  subject: string;
  status: "confirmed" | "in_progress" | "awaiting_response" | "new";
  last_message_at: string;
  message_count: number;
  next_action: string;
  source?: string;
}

export interface MeetingBooking {
  booking_id: string;
  thread_id: string;
  coordinator_id: string;
  ia_contact: string;
  event_id: string;
  title: string;
  scheduled_at: string;
  duration_minutes: number;
  status: "confirmed" | "pending_confirmation";
  meeting_link: string;
  notes: string;
  source?: string;
}

export interface RetentionNudge {
  student_id: string;
  nudge_type: "next_event" | "re_engage" | "streak" | "membership";
  message: string;
  event_id: string | null;
  cta_label: string;
  points_earned: number;
  source?: string;
}


const API_BASE = "/api";

/**
 * Raised before `fetch` when a legacy `/api/portals/*` request has no subject
 * id to address.
 *
 * The account-to-portal *mapping* is no longer the missing piece: `GET
 * /v1/me/portals` provides it, derived from the caller's server-assigned
 * memberships, and {@link fetchMyPortals} is how the shells read it. What is
 * still missing is different and narrower — the `/api/portals/*` backend
 * itself is not part of this repository, and the legacy `student_id` /
 * `coordinator_id` / `volunteer_id` namespaces it keys on exist nowhere here.
 * An account UUID is not one of those ids, so passing `me.user_id` off as one
 * would cross two unrelated namespaces *and* make the browser the authority
 * for a path subject.
 *
 * No page calls these functions today; the portal pages render an explicit
 * unavailable panel naming the dataset instead. They are kept, with this
 * error, so that the day a real backend arrives the seam is already the shape
 * it needs to be — and so nothing can quietly start guessing an id in the
 * meantime.
 */
export class PortalSubjectUnavailableError extends Error {
  constructor(portal: "student" | "coordinator" | "volunteer") {
    super(
      `The legacy ${portal} dataset is not served by this API. This deployment ` +
        "provides the authenticated account-to-portal mapping (GET /v1/me/portals) " +
        "but no /api/portals/* backend.",
    );
    this.name = "PortalSubjectUnavailableError";
  }
}

/** Validates and URL-encodes a server-issued legacy portal id before I/O. */
function portalSubjectPath(
  value: string,
  portal: "student" | "coordinator" | "volunteer",
): string {
  const subjectId = value.trim();
  if (!subjectId) {
    throw new PortalSubjectUnavailableError(portal);
  }
  return encodeURIComponent(subjectId);
}


export async function fetchStudentProfile(studentId: string): Promise<StudentProfile & { source: string }> {
  const subjectPath = portalSubjectPath(studentId, "student");
  return requestJson<StudentProfile & { source: string }>(
    `${API_BASE}/portals/students/${subjectPath}`,
  );
}

export async function fetchStudentRegistrations(studentId: string): Promise<{ data: StudentRegistration[]; total: number; source: string }> {
  const subjectPath = portalSubjectPath(studentId, "student");
  return requestJson<{ data: StudentRegistration[]; total: number; source: string }>(
    `${API_BASE}/portals/students/${subjectPath}/registrations`,
  );
}

export async function fetchStudentConnectionSuggestions(
  studentId: string,
): Promise<StudentConnectionSuggestionsResponse> {
  const subjectPath = portalSubjectPath(studentId, "student");
  const params = new URLSearchParams({ student_id: studentId });
  const endpoints = [
    `${API_BASE}/portals/student-connections?${params.toString()}`,
    `${API_BASE}/portals/students/${subjectPath}/connection-suggestions`,
  ];

  for (const endpoint of endpoints) {
    try {
      return await requestJson<StudentConnectionSuggestionsResponse>(endpoint);
    } catch (err) {
      // During local development it is common to have a stale backend process;
      // if one route is missing, try the compatibility endpoint before failing.
      if (err instanceof ApiRequestError && err.status === 404) {
        continue;
      }
      throw err;
    }
  }

  return {
    student_id: studentId,
    attended_past_events: [],
    suggestions: [],
    total: 0,
    source: "unavailable",
  };
}

export async function fetchStudentRecommendations(studentId: string): Promise<{ recommendations: (CalendarEventSummary & { is_recommended: boolean })[]; source: string }> {
  const subjectPath = portalSubjectPath(studentId, "student");
  return requestJson<{ recommendations: (CalendarEventSummary & { is_recommended: boolean })[]; source: string }>(
    `${API_BASE}/portals/students/${subjectPath}/recommendations`,
  );
}

export async function fetchStudentNudge(
  studentId: string,
): Promise<(RetentionNudge & { source: string }) | null> {
  try {
    const subjectPath = portalSubjectPath(studentId, "student");
    return await requestJson<RetentionNudge & { source: string }>(
      `${API_BASE}/portals/students/${subjectPath}/nudge`,
    );
  } catch (err) {
    if (err instanceof ApiRequestError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function fetchCoordinatorProfile(coordinatorId: string): Promise<EventCoordinator & { source: string }> {
  const subjectPath = portalSubjectPath(coordinatorId, "coordinator");
  return requestJson<EventCoordinator & { source: string }>(
    `${API_BASE}/portals/event-coordinators/${subjectPath}`,
  );
}

export async function fetchCoordinatorThreads(coordinatorId: string): Promise<{ data: OutreachThread[]; total: number; source: string }> {
  const subjectPath = portalSubjectPath(coordinatorId, "coordinator");
  return requestJson<{ data: OutreachThread[]; total: number; source: string }>(
    `${API_BASE}/portals/event-coordinators/${subjectPath}/threads`,
  );
}

export async function fetchCoordinatorMeetings(coordinatorId: string): Promise<{ data: MeetingBooking[]; total: number; source: string }> {
  const subjectPath = portalSubjectPath(coordinatorId, "coordinator");
  return requestJson<{ data: MeetingBooking[]; total: number; source: string }>(
    `${API_BASE}/portals/event-coordinators/${subjectPath}/meetings`,
  );
}

export async function fetchCoordinatorEvents(coordinatorId: string): Promise<{ data: (CalendarEventSummary & { staffing_open: boolean })[]; total: number; source: string }> {
  const subjectPath = portalSubjectPath(coordinatorId, "coordinator");
  const payload = await requestJson<{
    data?: (CalendarEventSummary & { staffing_open?: boolean })[];
    events?: (CalendarEventSummary & { staffing_open?: boolean })[];
    total?: number;
    source?: string;
  }>(`${API_BASE}/portals/event-coordinators/${subjectPath}/events`);
  const data = (payload.data ?? payload.events ?? []).map((event) => ({
    ...event,
    staffing_open: event.staffing_open ?? false,
  }));
  return {
    data,
    total: typeof payload.total === "number" ? payload.total : data.length,
    source: typeof payload.source === "string" ? payload.source : "demo",
  };
}

// ---------------------------------------------------------------------------
// Volunteer portal types
// ---------------------------------------------------------------------------

export interface VolunteerProfile {
  volunteer_id: string;
  name: string;
  title: string;
  company: string;
  board_role: string;
  metro_region: string;
  expertise_tags: string;
  initials: string;
  recovery_status: string;
  recovery_label: string;
  volunteer_fatigue: number;
  source?: string;
}

export type AssignmentStage = "Matched" | "Contacted" | "Confirmed" | "Attended";

/**
 * One volunteer assignment as the client is allowed to see it.
 *
 * `match_score` is intentionally absent: it is a G1-gated factor-registry
 * output and is stripped by {@link stripG1ScoreFields} inside
 * {@link fetchVolunteerAssignments}, so it never reaches component state.
 * The request itself stays because the rest of the row (event, date, region,
 * stage, recovery) is what the assignments list is actually built from.
 */
export interface VolunteerAssignment {
  assignment_id: string;
  event_id: string;
  event_name: string;
  event_date: string;
  region: string;
  stage: AssignmentStage;
  volunteer_fatigue: number;
  recovery_status: string;
  recovery_label: string;
  coverage_status: string;
}

export async function fetchVolunteerProfile(
  volunteerId: string,
): Promise<VolunteerProfile & { source: string }> {
  const subjectPath = portalSubjectPath(volunteerId, "volunteer");
  return requestJson<VolunteerProfile & { source: string }>(
    `${API_BASE}/portals/volunteers/${subjectPath}`,
  );
}

export async function fetchVolunteerAssignments(
  volunteerId: string,
): Promise<{ data: VolunteerAssignment[]; total: number; source: string }> {
  const subjectPath = portalSubjectPath(volunteerId, "volunteer");
  const payload = await requestJson<{
    data: VolunteerAssignment[];
    total: number;
    source: string;
  }>(`${API_BASE}/portals/volunteers/${subjectPath}/assignments`);
  // G1 fail-closed: the score is discarded here, not merely left unrendered.
  return { ...payload, data: (payload.data ?? []).map(stripG1ScoreFields) };
}

// ---------------------------------------------------------------------------
// Identity + accountable metrics (`contracts/openapi/smartmatch.json`)
// ---------------------------------------------------------------------------

export interface MembershipResponse {
  org_unit_path: string;
  role: string;
  valid_from: string | null;
  valid_until: string | null;
  is_active: boolean;
}

export interface MeResponse {
  user_id: string;
  tenant_id: string;
  email: string;
  suspended: boolean;
  memberships: MembershipResponse[];
}

/** `GET /v1/me` — caller identity and server-assigned memberships. */
export async function fetchMe(): Promise<MeResponse> {
  return requestJson<MeResponse>("/v1/me", undefined, { authenticated: true });
}

// ---------------------------------------------------------------------------
// Pilot sign-in (`POST /v1/auth/login`, `POST /v1/auth/logout`)
//
// A pilot-scoped stand-in for institutional sign-in, authorized by the project
// owner on 2026-09-04 and recorded in
// `docs/decisions/pilot-login-decision-2026-09-04.md`. It is not A1b and does
// not unblock it.
//
// The request below carries an email and a password and *nothing else*. The
// server's `LoginRequest` forbids extra fields outright, so a body carrying a
// role, tenant, or unit is rejected with a 422 rather than ignored — there is
// no shape of this call that lets a browser say what it is allowed to do.
// ---------------------------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
}

/**
 * `POST /v1/auth/login` — exchange pilot credentials for a session token.
 *
 * Returns the token; it deliberately does **not** store it or say who the
 * caller is. Storing is {@link storeSmartmatchBearerToken}'s job and identity
 * is `GET /v1/me`'s, so that "I have a credential" and "this is who I am" stay
 * two separate answers with one source each.
 */
export async function postLogin(email: string, password: string): Promise<LoginResponse> {
  return requestJson<LoginResponse>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export interface LogoutResponse {
  ended: boolean;
}

/** `POST /v1/auth/logout` — revoke the session this browser is holding. */
export async function postLogout(): Promise<LogoutResponse> {
  return requestJson<LogoutResponse>(
    "/v1/auth/logout",
    { method: "POST" },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// The authenticated account-to-portal mapping (`GET /v1/me/portals`)
// ---------------------------------------------------------------------------

/**
 * One org unit a granted portal covers, carrying the id `/v1` routes take.
 *
 * `GET /v1/me` reports a membership's `org_unit_path` (an ltree), while every
 * unit-scoped route — metrics, imports, events, match runs, rewards — takes a
 * `unit_id`. Nothing joined the two, so the browser had no way to get from
 * "who am I" to "whose metrics may I read". These ids are resolved
 * server-side from the caller's own memberships; the browser never constructs
 * or supplies one, which is the same rule that keeps the portal itself
 * server-decided.
 */
export interface PortalUnit {
  unit_id: string;
  path: string;
  unit_type: string;
  display_name: string;
}

export interface PortalDescriptor {
  portal: string;
  display_name: string;
  home_path: string;
  role: string;
  org_unit_path: string;
  /** Units the granting membership covers, shallowest first. May be empty. */
  units: PortalUnit[];
  /** The first entry's `unit_id`, or `null` when `units` is empty. */
  default_unit_id: string | null;
}

export interface MyPortalsResponse {
  portals: PortalDescriptor[];
  default_portal: string | null;
}

/**
 * `GET /v1/me/portals` — which portals the caller's server-assigned roles open.
 *
 * Takes no argument, because there is nothing for the caller to name: the
 * answer follows from the bearer token. This is the route that replaces the
 * banner the shells used to render, and it is deliberately not
 * `/api/portals/{id}` — an id in the path is the archived defect (MM-A01).
 */
export async function fetchMyPortals(): Promise<MyPortalsResponse> {
  return requestJson<MyPortalsResponse>("/v1/me/portals", undefined, { authenticated: true });
}

export interface MetricSummary {
  name: string;
  display_name: string;
  definition: string;
  value: number | null;
  unknown_reason?: string | null;
  drill_down_url: string;
}

export interface MetricsResponse {
  unit_id: string;
  metrics: MetricSummary[];
}

export interface MetricDrillDownResponse {
  unit_id: string;
  name: string;
  definition: string;
  aggregate_value: number | null;
  unknown_reason?: string | null;
  rows: Array<Record<string, unknown>>;
}

/** `GET /v1/units/{unit_id}/metrics` — all registered accountable metrics. */
export async function fetchUnitMetrics(unitId: string): Promise<MetricsResponse> {
  return requestJson<MetricsResponse>(`/v1/units/${encodeURIComponent(unitId)}/metrics`, undefined, {
    authenticated: true,
  });
}

/** `GET /v1/units/{unit_id}/metrics/{metric_name}/drill-down`. */
export async function fetchMetricDrillDown(
  unitId: string,
  metricName: string,
): Promise<MetricDrillDownResponse> {
  return requestJson<MetricDrillDownResponse>(
    `/v1/units/${encodeURIComponent(unitId)}/metrics/${encodeURIComponent(metricName)}/drill-down`,
    undefined,
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Match runs (`contracts/openapi/smartmatch.json`, cards M8b/M9/M10)
// ---------------------------------------------------------------------------

/**
 * Whether a number exists — carried beside the number, never inferred from it.
 *
 * This is the client half of ADR-0011. The API sends `state` next to `value`
 * precisely so no consumer has to reconstruct "unknown" from a `null`, because
 * a `null` is one `?? 0` away from becoming a fabricated zero. Read `state`
 * first; read `value` only in the `"measured"` branch.
 */
export type MatchScoreState = "measured" | "policy_neutral" | "unknown";

/** One factor's contribution to one candidate's score, or its absence. */
export interface MatchFactorExplanation {
  factor_key: string;
  display_label: string;
  /** `suitability` or `penalty` — the two read in opposite directions. */
  kind: string;
  /** The normalized Stage B weight actually applied for this run. */
  weight: number;
  state: MatchScoreState;
  /**
   * The factor value in [0, 1], or null when `state` is `"unknown"`.
   *
   * A null is an absence of evidence and is never a zero. A `"policy_neutral"`
   * value is a stated customer policy rather than a measurement — it is a real
   * number, and rendering it as "Unknown" would be as wrong as rendering an
   * unknown as `0`.
   */
  value: number | null;
  /** `measured_zero`, `unknown`, or null when the value is neither. */
  zero_classification: string | null;
  /** Where the number came from — or why there is none. */
  basis: string;
  /** Set when the value is an explicitly coarse estimate. */
  estimate_label: string | null;
  /**
   * The customer policy behind a `"policy_neutral"` value, null otherwise.
   * Carried so a neutral default is attributable rather than indistinguishable
   * from a measurement that happened to land there (ADR-0016).
   */
  policy_id: string | null;
  /** The policy's version. Set exactly when `policy_id` is. */
  policy_version: string | null;
}

/** One candidate's heuristic score and every factor behind it. */
export interface MatchCandidateExplanation {
  subject_id: string;
  /** In [0, 1]. Never a percentage, and null when `state` is "unknown". */
  heuristic_score: number | null;
  state: MatchScoreState;
  /** Always "heuristic score" — the ratified G1 provenance label. */
  score_label: string;
  /** The factor-registry version this score was produced under. */
  registry_version: string;
  formula_version: string;
  unknown_factor_keys: string[];
  /**
   * The factors whose value came from a stated customer policy rather than a
   * measurement, in registry order. Listed so a consumer can say which parts of
   * a score were policy without comparing floats to a constant.
   */
  policy_neutral_factor_keys?: string[];
  /**
   * The approved caption a surface must show beside this score, **verbatim**,
   * or null when none applies (ADR-0016 Proposal 8). Not a sentence this client
   * composes and not one it may paraphrase.
   */
  caption?: string | null;
  /**
   * The model this score was produced under — `cba-virtual-1`,
   * `cba-physical-1`, or null for a run stored before the vocabulary existed.
   * A null is **not** `cba-physical-1`: a pre-ADR-0016 run never asked the
   * question, and reading it as physical would claim a proximity factor was
   * scored.
   */
  scoring_mode?: string | null;
  /** The mode vocabulary's version. Set exactly when `scoring_mode` is. */
  scoring_mode_version?: string | null;
  factors: MatchFactorExplanation[];
}

/**
 * One persisted match run: the pinned snapshot, its shortlist, and the
 * explanations behind every candidate.
 *
 * `shortlist` holds 2-3 speakers per the ratified presentation rule, and is
 * empty when `shortlist_available` is false — in which case
 * `shortlist_unavailable_reason` says why. It is never approximated, so a
 * client must render that reason rather than treat an empty list as a result.
 */
export interface MatchRunRead {
  id: string;
  unit_id: string;
  job_id: string;
  event_need_id: string;
  created_at: string;
  supersedes_run_id: string | null;

  score_label: string;
  registry_version: string;
  registry_hash: string;
  weights: Record<string, number>;
  optimizer_model_version: string;
  solver_name: string;
  solver_version: string;
  route_estimate_source: string;
  route_estimate_version: string;
  inputs_hash: string;
  portfolio_size: number;
  random_seed: number;
  portfolio_status: string;

  shortlist: MatchCandidateExplanation[];
  shortlist_available: boolean;
  shortlist_unavailable_reason: string | null;
  considered: MatchCandidateExplanation[];
  /** Candidates excluded because a factor had no evidence. Never scored at 0. */
  unscorable: MatchCandidateExplanation[];
}

/** `GET /v1/units/{unit_id}/match-runs/{match_run_id}`. */
export async function fetchMatchRun(
  unitId: string,
  matchRunId: string,
): Promise<MatchRunRead> {
  return requestJson<MatchRunRead>(
    `/v1/units/${encodeURIComponent(unitId)}/match-runs/${encodeURIComponent(matchRunId)}`,
    undefined,
    { authenticated: true },
  );
}

/**
 * One match-run submission: which filed request, and whom to consider.
 *
 * These three fields are the whole of `MatchRunRequest` in
 * `contracts/openapi/smartmatch.json`, and the omissions are the contract.
 * There is no field here for a speaker's expertise, sector, seniority or
 * whereabouts, and none for the event's own description or its virtual/
 * physical switch: every one of those is read server-side from this tenant's
 * rows (`smartmatch_api.match_run_evidence`). A body that could state what a
 * speaker is good at is a body that can decide its own shortlist — OQ-CBA-031.
 *
 * Nor does it name a tenant, an actor, or the unit. The unit travels in the
 * authorized path; the other two come off the verified bearer token (MM-A01).
 */
export interface MatchRunSubmission {
  /** The filed Speaker Request this run answers, by the id the queue reported. */
  speaker_request_id: string;
  /**
   * The professionals to consider, at most 200, each a `professional_id` the
   * §13 roster reported. Never an identifier derived from a name.
   */
  candidate_subject_ids: string[];
  /**
   * How many speakers to shortlist. The server bounds this to 2-3 per the
   * ratified presentation rule and refuses anything else, so a caller that
   * sends 5 gets a refusal rather than a quietly trimmed answer.
   */
  portfolio_size?: number;
  /** Seed handed to the solver. Same pool, size and seed give the same picks. */
  random_seed?: number;
}

/** One named subject that never entered the pool, and the server's word for why. */
export interface ExcludedMatchCandidate {
  subject_id: string;
  /**
   * A stable token — `speaker_profile_not_found`,
   * `industry_classification_awaiting_review`, and the rest of the vocabulary
   * `ExcludedCandidateView` documents. Distinct from *unscorable*: an
   * unscorable candidate was evaluated and some factor had no evidence, an
   * excluded one was never evaluated at all. Collapsing the two would tell a
   * Connector somebody scored poorly when nobody has looked at their record.
   */
  reason: string;
}

/**
 * The `202` acknowledgement. **Nothing has been matched when this arrives.**
 *
 * No `match_run` row exists yet and there is no run id in this body — only a
 * job id and the counts the server could answer at submission. A client
 * rendering this may say "queued" and may say how large the pool turned out to
 * be; it may not say a shortlist exists, and it cannot link to one, because
 * the run id does not arrive until the job completes.
 */
export interface MatchRunAccepted {
  status: string;
  job_id: string;
  /** Where to follow the work: `/v1/jobs/{job_id}/events`. */
  events_url: string;
  /** True when an identical request under the same key was already accepted. */
  replayed: boolean;
  /** The factor registry version the pool was scored under. */
  registry_version: string;
  /** The model within that registry, resolved from the request's own switch. */
  scoring_mode: string;
  scoring_mode_version: string;
  /** The only label these scores may be displayed under. Never a percentage. */
  score_label: string;
  /** Candidates with complete evidence, entered into the pool. */
  scored_candidates: number;
  /** Evaluated, composite unknown. Reported, never entered at zero (ADR-0011). */
  unscorable_candidates: number;
  /** Named subjects never evaluated at all, each with the reason. */
  excluded_candidates: ExcludedMatchCandidate[];
}

/**
 * `POST /v1/units/{unit_id}/match-runs` — submit one match-run command.
 *
 * Resolves on `202` with a job id. It does **not** resolve with a shortlist,
 * and the absence is deliberate: the command is recorded and dispatched, and
 * the run appears later. Callers must render the acceptance as queued work.
 *
 * Rejects with {@link ApiRequestError} on a 4xx, so a caller renders the
 * server's own refusal — `422` when fewer candidates can be scored than the
 * requested shortlist needs (the physical model's ordinary answer for a roster
 * whose ZIPs are missing, since an unresolved distance is unknown and never
 * Far), `400` for an oversized or duplicated pool, `404` for a request that is
 * not this unit's, `503` while the registry is not ready.
 *
 * The `Idempotency-Key` is generated per attempt with `crypto.randomUUID`: a
 * retry of *this* attempt is
 * safe, and a deliberate resubmission is a new command rather than a silently
 * swallowed one.
 */
export async function createMatchRun(
  unitId: string,
  submission: MatchRunSubmission,
): Promise<MatchRunAccepted> {
  return requestJson<MatchRunAccepted>(
    `/v1/units/${encodeURIComponent(unitId)}/match-runs`,
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify(submission),
    },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Durable jobs (`GET /v1/jobs/{job_id}`, `GET /v1/jobs/{job_id}/events`)
// ---------------------------------------------------------------------------
//
// Every `202` in this file becomes one of these. A job is the only honest
// answer to "did it work?" for an accepted command, and it is the *server's*
// answer: nothing here infers a state from elapsed time or from the fact that
// a request returned.

/** Every state a durable job may occupy (`JobState` in the OpenAPI contract). */
export type JobState =
  | "queued"
  | "dispatched"
  | "running"
  | "succeeded"
  | "partial"
  | "failed_provider"
  | "failed_budget"
  | "failed_policy"
  | "cancelled"
  | "timed_out"
  | "redrive_pending"
  | "abandoned";

/** The states a job never leaves. Anything else is still in flight. */
const TERMINAL_JOB_STATES: readonly JobState[] = [
  "succeeded",
  "partial",
  "failed_provider",
  "failed_budget",
  "failed_policy",
  "cancelled",
  "timed_out",
  "abandoned",
];

/** Whether this job has settled. A `redrive_pending` job has not. */
export function isTerminalJobState(state: JobState): boolean {
  return TERMINAL_JOB_STATES.includes(state);
}

/** One job's current state. */
export interface JobStatus {
  id: string;
  command_type: string;
  status: JobState;
  latest_sequence: number;
  created_at: string;
  updated_at: string;
}

/** `GET /v1/jobs/{job_id}` — the server's own word on an accepted command. */
export async function fetchJobStatus(jobId: string): Promise<JobStatus> {
  return requestJson<JobStatus>(
    `/v1/jobs/${encodeURIComponent(jobId)}`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * The terminal `job.completed` summary, or null when the stream carries none.
 *
 * `GET /v1/jobs/{job_id}/events` is Server-Sent Events, not JSON, so this is
 * the one helper in this file that reads a response body as text. Each frame is
 * `data: {"sequence": n, "payload": {...}, "occurred_at": "..."}`; the terminal
 * frame's payload has `type: "job.completed"` and carries the summary the
 * handler recorded. For a match run that summary holds `match_run_id`, and it
 * is the **only** place a client can learn it — no route maps a job to its run,
 * and `tests/e2e/test_pilot_clickthrough.py` recovers the id the same way.
 *
 * Returns null rather than throwing when no completion frame is present: a job
 * that has not finished has no summary, which is a state and not an error. A
 * caller must therefore branch on null instead of treating a missing summary as
 * a failure — or as a success.
 */
export async function fetchJobCompletionSummary(
  jobId: string,
): Promise<Record<string, unknown> | null> {
  const response = await fetch(`/v1/jobs/${encodeURIComponent(jobId)}/events`, {
    headers: { ...smartmatchAuthHeaders() },
  });

  if (!response.ok) {
    await throwApiRequestError(response);
  }

  const body = await response.text();
  for (const line of body.split("\n")) {
    if (!line.startsWith("data: ")) {
      continue;
    }
    let frame: unknown;
    try {
      frame = JSON.parse(line.slice("data: ".length));
    } catch {
      // A malformed frame is skipped rather than failing the whole read: the
      // summary may still arrive on a later one, and a parse error here is not
      // evidence about the job.
      continue;
    }
    const payload = toObjectRecord(toObjectRecord(frame).payload);
    if (payload.type === "job.completed") {
      const summary = payload.summary;
      return summary && typeof summary === "object" && !Array.isArray(summary)
        ? (summary as Record<string, unknown>)
        : null;
    }
  }
  return null;
}

/**
 * Reads a match run's id off a completion summary, or null when it has none.
 *
 * Typed as `unknown` on the way in and narrowed here, because a summary is a
 * handler-shaped JSON blob rather than a schema in the OpenAPI document. The
 * narrowing is the point: a caller must not be able to interpolate whatever the
 * summary happened to hold into a URL.
 */
export function readMatchRunIdFromSummary(
  summary: Record<string, unknown> | null,
): string | null {
  if (summary === null) {
    return null;
  }
  const value = summary.match_run_id;
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

export interface AgentStepEvent {
  event: "workflow_start" | "agent_queued" | "agent_running" | "agent_done" | "workflow_complete";
  agent_id?: string;
  agent_name?: string;
  role?: string;
  step?: number;
  output?: Record<string, unknown>;
  duration_ms?: number;
  speaker_name?: string;
  event_name?: string;
  total_agents?: number;
  dispatch_mode?: string;
  summary?: string;
  human_approval_required?: boolean;
}

// ---------------------------------------------------------------------------
// Rewards and redemptions (`contracts/openapi/smartmatch.json`, card U1)
// ---------------------------------------------------------------------------

/**
 * Whether a points figure exists — carried beside the figure, never inferred.
 *
 * The client half of ADR-0011 for the rewards surface, and the same shape
 * {@link MatchScoreState} already uses. Read `state` first; read the number
 * only in the `"measured"` branch. This exists because the file it replaces
 * (`studentPoints.ts`) did the opposite: its call sites wrote
 * `profile ? getStudentTotalPoints(profile) : 0`, so "we have not loaded this
 * student yet" rendered as a balance of zero.
 */
export type RewardPointsState = "measured" | "unknown";

/** `balance` from `GET /v1/units/{unit_id}/rewards`. */
export interface RewardBalance {
  state: RewardPointsState;
  /** Null whenever `state` is `"unknown"`. Never coerce this to 0. */
  points: number | null;
  /** How many ledger entries the server folded. The evidence for a measured zero. */
  ledger_entry_count: number;
  unknown_reason?: string | null;
}

/**
 * One listable reward. Every item the server sends is funded and has a named
 * budget owner — that filtering happens in SQL, so there is nothing for this
 * client to filter and no `funded` flag to branch on.
 */
export interface RewardCatalogItem {
  item_id: string;
  name: string;
  points_cost: number;
  affordable: boolean;
  /** `"unknown"` means render no progress bar: the distance has no honest value. */
  progress_state: RewardPointsState;
  points_still_needed: number | null;
  events_still_needed: number | null;
}

export interface RewardCatalogResponse {
  unit_id: string;
  balance: RewardBalance;
  points_per_verified_attendance: number;
  /** False while D7 is tentative. Surfaced so the UI can say so rather than imply ratification. */
  earn_policy_ratified: boolean;
  items: RewardCatalogItem[];
}

export type RedemptionState =
  | "requested"
  | "approved"
  | "fulfilled"
  | "denied"
  | "expired";

/** One redemption ticket, rendered from the server's own snapshots. */
export interface Redemption {
  redemption_id: string;
  item_id: string;
  item_name: string;
  points_cost: number;
  state: RedemptionState;
}

export interface RedemptionListResponse {
  unit_id: string;
  redemptions: Redemption[];
}

/** `GET /v1/units/{unit_id}/rewards` — funded catalog plus the caller's own balance. */
export async function fetchRewardCatalog(unitId: string): Promise<RewardCatalogResponse> {
  return requestJson<RewardCatalogResponse>(
    `/v1/units/${encodeURIComponent(unitId)}/rewards`,
    undefined,
    { authenticated: true },
  );
}

/** `GET /v1/units/{unit_id}/redemptions` — the caller's own tickets. */
export async function fetchOwnRedemptions(unitId: string): Promise<RedemptionListResponse> {
  return requestJson<RedemptionListResponse>(
    `/v1/units/${encodeURIComponent(unitId)}/redemptions`,
    undefined,
    { authenticated: true },
  );
}

/**
 * `POST /v1/units/{unit_id}/redemptions` — ask for one reward.
 *
 * The body carries `item_id` and nothing else. There is deliberately no
 * `subject_id` parameter here and there must never be one: the server takes the
 * student from the verified bearer token, which is the whole of stakeholder
 * Fix #7 (MM-A01).
 */
export async function requestRedemption(unitId: string, itemId: string): Promise<Redemption> {
  return requestJson<Redemption>(
    `/v1/units/${encodeURIComponent(unitId)}/redemptions`,
    { method: "POST", body: JSON.stringify({ item_id: itemId }) },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Outreach (R4, gate G4)
//
// Read-only legacy outreach records remain available during the transition.
//
// That is the direct correction of the defect `docs/plans/frontend-broken-buttons.md`
// catalogues as B17: the legacy Send button called `console.log("Message sent:")`,
// showed "Message sent!" for two seconds, and closed the dialog, having made no
// request at all. Replacing it with a real request that resolves to an
// optimistic success would be the same defect with a network round trip in the
// middle, so the types below give a caller nothing optimistic to render.
// ---------------------------------------------------------------------------

/** One stored draft, as `GET`/`POST .../outreach/drafts` returns it. */
export interface OutreachDraft {
  draft_id: string;
  contact_channel_id: string;
  template_id: string;
  /**
   * `"synthetic"` for pilot copy that has not been through institutional
   * review, `"reviewed"` otherwise. Rendered in the UI rather than hidden: it
   * is the fact that decides whether this message could go to a real person.
   */
  content_status: string;
  subject: string;
  body: string;
  status: string;
  version: number;
  recipient_address: string;
}

export interface OutreachDraftListResponse {
  drafts: OutreachDraft[];
  limit: number;
  offset: number;
}

/**
 * What a submitted send command returns.
 *
 * Note the fields it does *not* have. There is no status, no disposition, and
 * nothing about a message, because when this resolves the command has been
 * recorded and the dispatcher has not moved it. A UI that wants to say
 * something true at this point can say "queued" and show the job id.
 */
export interface OutreachSendAccepted {
  job_id: string;
  events_url: string;
  replayed: boolean;
}

export interface OutreachDeliveryEvent {
  event_type: string;
  occurred_at: string;
  provider_event_id: string | null;
}

/**
 * One send attempt and its delivery stream.
 *
 * `disposition` is `null` while the attempt is in flight. That is a third
 * state, not a missing value: render it as in-progress and never as a failure.
 * Even `"accepted"` means only that a provider took custody — delivery is a
 * later event in the stream and may never arrive.
 */
export interface OutreachSend {
  send_id: string;
  draft_id: string;
  job_id: string;
  recipient_address: string;
  disposition: string | null;
  provider: string | null;
  provider_message_id: string | null;
  failure_reason: string | null;
  delivery_events: OutreachDeliveryEvent[];
}

/** `GET /v1/units/{unit_id}/outreach/drafts` — a coordinator's drafts. */
export async function fetchOutreachDrafts(unitId: string): Promise<OutreachDraftListResponse> {
  return requestJson<OutreachDraftListResponse>(
    `/v1/units/${encodeURIComponent(unitId)}/outreach/drafts`,
    undefined,
    { authenticated: true },
  );
}

/**
 * `POST /v1/units/{unit_id}/outreach/drafts` — compose one message.
 *
 * The body carries a template id and its placeholder values. There is
 * deliberately no `body` or `subject` parameter and there must never be one:
 * the server's closed template registry decides what the words are, and
 * free-form text from a browser would reopen the hole that registry closes.
 */
/**
 * `POST /v1/units/{unit_id}/outreach/drafts/{draft_id}/send` — submit the command.
 *
 * Resolves with a job id when the server answers `202`. **Nothing has been sent
 * at that point.** The `Idempotency-Key` is generated per attempt so that a
 * retry after a network error cannot become a second message; `crypto.randomUUID`
 * is used rather than a timestamp because two clicks in the same millisecond are
 * two attempts, and a key that collided would silently merge them.
 */
/** `GET /v1/units/{unit_id}/outreach/sends/{send_id}` — what actually happened. */
export async function fetchOutreachSend(unitId: string, sendId: string): Promise<OutreachSend> {
  return requestJson<OutreachSend>(
    `/v1/units/${encodeURIComponent(unitId)}/outreach/sends/${encodeURIComponent(sendId)}`,
    undefined,
    { authenticated: true },
  );
}

/**
 * One send in a listing, **without** its delivery stream.
 *
 * The stream is absent rather than summarised, and the route says why: folding
 * a send's events into one word is a choice about which fact to forget — a
 * provider can report `delivered` and then `complained` — and making that
 * choice once per row would bury it where nobody reviews it. A reader who needs
 * to explain what happened to one message reads that send with
 * {@link fetchOutreachSend}.
 *
 * `disposition` is `null` while the attempt is in flight. That is a third
 * state, not a missing value: render it as in progress, never as a failure and
 * never as a success.
 */
export interface OutreachSendSummary {
  send_id: string;
  draft_id: string;
  job_id: string;
  recipient_address: string;
  /** `accepted`, `blocked`, `failed`, or null while the attempt is in flight. */
  disposition: string | null;
  provider: string | null;
  provider_message_id: string | null;
  failure_reason: string | null;
  created_at: string;
  /** When the attempt reached an outcome, or null while it has not. */
  concluded_at: string | null;
}

/**
 * A page of sends, and how many were asked for.
 *
 * There is no total, and a caller must not derive one. `limit` and `offset` are
 * what was asked for, not what exists; the number of send attempts a unit has
 * made is not a figure this response reports.
 */
export interface OutreachSendListResponse {
  sends: OutreachSendSummary[];
  limit: number;
  offset: number;
}

/**
 * `GET /v1/units/{unit_id}/outreach/sends` — the unit's send attempts, newest first.
 *
 * The listing the coordinator surface was missing. Drafts could be listed and a
 * single send could be read by id, so the only way to see what a unit had
 * actually attempted was to have kept the ids from when it attempted them.
 *
 * These are **sends**, not threads. OQ-008 records that this slice stores send
 * records rather than conversations: nothing here implies a reply exists, no
 * row is part of an exchange, and a caller that renders this list under a
 * "threads" heading is asserting a shape the data does not have.
 */
export async function fetchOutreachSends(unitId: string): Promise<OutreachSendListResponse> {
  return requestJson<OutreachSendListResponse>(
    `/v1/units/${encodeURIComponent(unitId)}/outreach/sends`,
    { method: "GET" },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Speaker invitations (CBA-INVITATIONS, customer §6 steps 7-8, §13, §14)
//
// Five calls, all on the consented `/v1` path. Nothing here touches
// `/api/data/*`, `fetchSpecialists`, or the legacy cold flow — an invitation is
// an `outreach_draft` addressed to an already-consented contact channel, sent by
// the same `outreach.send` command every other message on this surface uses.
//
// **The types below keep two facts in two objects, and that is the whole point
// of this section.** `SpeakerInvitationOutcome.delivery` is what a *mail
// provider* did; `SpeakerInvitationOutcome.speaker_response` is what a *person*
// said. They share no field and no value: a provider's "accepted" means custody
// of some bytes, while a Speaker's acceptance is spelled `accepted_invitation`.
// Flattening them into one status in the browser would reintroduce here exactly
// the confusion the server's schema, its CHECK constraints and its tests are all
// arranged to prevent — and it would reintroduce it at the boundary where it
// actually reaches an Event Host's eyes.
// ---------------------------------------------------------------------------

/**
 * What a mail provider did with one invitation's message.
 *
 * `null` at the top level of an outcome when no send has been submitted at all.
 * A non-null object whose `disposition` is `null` is an attempt in flight — a
 * third state, to be rendered as in-progress and never as a failure.
 */
export interface SpeakerInvitationDelivery {
  send_id: string;
  /**
   * `"accepted"`, `"blocked"`, `"failed"`, or `null` while in flight.
   * `"accepted"` means a provider took custody. It does **not** mean delivered,
   * and it says nothing whatever about whether the Speaker agreed to come.
   */
  disposition: string | null;
  provider: string | null;
  failure_reason: string | null;
  concluded_at: string | null;
}

/**
 * What the Speaker said. Never what a provider did.
 *
 * `response` is `"awaiting_response"`, `"accepted_invitation"` or
 * `"declined_invitation"` — every value names the invitation, so none of them
 * can be confused with a delivery disposition. `"awaiting_response"` is a real
 * state and the ordinary condition of every invitation until somebody reads
 * their mail; it is not a failure.
 */
export interface SpeakerInvitationResponse {
  response: string;
  recorded_at: string | null;
  /**
   * `"speaker_link"` when the Speaker followed the link in their own
   * invitation, `"connector_recorded"` when a coordinator entered what they
   * were told. Worth rendering: the second is a weaker evidentiary claim, and a
   * screen that showed them alike would assert a directness nobody has.
   */
  channel: string | null;
  recorded_by_user_id: string | null;
}

/** One named recipient's outcome, with the two facts kept apart. */
export interface SpeakerInvitationOutcome {
  invitation_id: string;
  professional_id: string;
  /** `"pending"`, `"dispatched"` or `"skipped"`. What the platform did. */
  status: string;
  /** Why nobody was written to, present exactly when `status` is `"skipped"`. */
  skip_reason: string | null;
  recipient_address: string | null;
  delivery: SpeakerInvitationDelivery | null;
  speaker_response: SpeakerInvitationResponse;
}

/** One batch and every outcome in it. */
export interface SpeakerInvitationBatch {
  batch_id: string;
  match_run_id: string | null;
  template_id: string;
  event_name: string;
  /** As the Connector typed it. Rendered verbatim; never parsed or reformatted. */
  event_date: string;
  created_at: string;
  /** True when this response replayed a key already used; nobody was invited twice. */
  replayed: boolean;
  invited_count: number;
  skipped_count: number;
  invitations: SpeakerInvitationOutcome[];
}

/** One batch in a listing, deliberately without its outcomes. */
export interface SpeakerInvitationBatchSummary {
  batch_id: string;
  match_run_id: string | null;
  template_id: string;
  event_name: string;
  event_date: string;
  created_at: string;
}

export interface SpeakerInvitationBatchListResponse {
  batches: SpeakerInvitationBatchSummary[];
  limit: number;
  offset: number;
}

/**
 * What a dispatch submitted, and what it refused to submit.
 *
 * Note the absent field: there is no count of messages sent, because when this
 * resolves nothing has been sent. Each `dispatched` entry is a command the
 * dispatcher has not moved yet.
 */
export interface SpeakerInvitationDispatchResponse {
  batch_id: string;
  dispatched: Array<{
    invitation_id: string;
    job_id: string;
    events_url: string;
    replayed: boolean;
  }>;
  /** Refused at dispatch on a consent fact read *now*, with the reason. */
  not_dispatched: Array<{ invitation_id: string; reason: string }>;
}

/** Legacy Connector invitation-list response retained for stored-data compatibility. */
/** Legacy invitation-detail response retained for stored-data compatibility. */
/**
 * Historical batch request shape; there is no active browser command for it.
 *
 * There is deliberately no `template_id`, no `body`, no recipient address and no
 * response link in this payload, and there must never be one. The template is
 * the server's closed registry; the address comes from the recipient's own
 * stored channels; and a browser-supplied link would put an arbitrary URL into
 * an institutional email to an already-consented address.
 *
 * The `Idempotency-Key` is generated per attempt with `crypto.randomUUID` rather
 * than a timestamp: two clicks in the same
 * millisecond are two attempts, and a colliding key would silently merge them.
 * The server treats a repeat of one key as a replay and invites nobody twice.
 */
/**
 * `POST .../batches/{batch_id}/dispatch` — submit the send commands.
 *
 * Resolves when the server answers `202`. **Nothing has been sent at that
 * point**, and the response has no field that could be rendered otherwise. No
 * `Idempotency-Key` header: each command's key is derived server-side from the
 * invitation id, which is a stronger promise than a per-attempt key — a second
 * dispatch replays rather than queueing a second message to the same person.
 */
/**
 * `POST .../speaker-invitations/{invitation_id}/response` — record an answer a
 * Speaker gave the Connector out of band.
 *
 * The verb is `"accept"` or `"decline"`, deliberately not a status value: a
 * vocabulary a browser could paste a delivery disposition into is a vocabulary
 * that will eventually receive one. The server stores it as
 * `accepted_invitation` / `declined_invitation` and records that a coordinator,
 * rather than the Speaker themselves, is the one who entered it.
 */
// ---------------------------------------------------------------------------
// Speaker Requests (CBA-EVENT-REQUEST, customer §12)
//
// One call, and the shape that matters runs through it: **the response is the
// stored request, not an echo of what was sent.** `submitSpeakerRequest`
// resolves with the row the server read back after committing — publication
// status, review status, timestamps and the resolved taxonomy names included —
// so a caller has something real to render and nothing optimistic to invent.
//
// There is deliberately no `Idempotency-Key` here. A Speaker Request has a
// deterministic identity server-side (ADR-0012:
// host unit, folded title, resolved date), so a second submission of the same
// request updates the first rather than filing a duplicate — a stronger promise
// than a per-attempt key, which only recognises a byte-identical repeat.
// ---------------------------------------------------------------------------

/** What an Event Host is asking for. Codes come from `lib/cbaTaxonomies.ts`. */
export interface SpeakerRequestPayload {
  title: string;
  /** IANA zone the event happens in, e.g. `America/Los_Angeles`. Never the browser's. */
  time_zone: string;
  /** One or more NAICS sector codes (customer §7). */
  industry_codes: string[];
  /** One or more CBA role-category codes (customer §8). */
  role_codes: string[];
  is_virtual: boolean;
  /** ISO-8601 instant, e.g. `2026-10-14T19:30:00Z`. Send this or `on_date`. */
  starts_at?: string;
  /** ISO-8601 instant. Only alongside `starts_at`, and only when the host stated one. */
  ends_at?: string;
  /** Calendar date, e.g. `2026-10-14`, when the hour is not settled. */
  on_date?: string;
  description?: string;
  location_city?: string;
  location_postal_code?: string;
}

/** One resolved target of a request, with the name the released taxonomy gives it. */
export interface SpeakerRequestClassificationView {
  code: string;
  display_name: string;
  taxonomy_version: string;
}

/** One filed Speaker Request, exactly as the server read it back. */
export interface SpeakerRequest {
  unit_id: string;
  request_id: string;
  title: string;
  description: string | null;
  time: {
    precision: string;
    starts_at: string | null;
    ends_at: string | null;
    on_date: string | null;
    time_zone: string | null;
  };
  is_virtual: boolean;
  location_city: string | null;
  location_postal_code: string | null;
  industries: SpeakerRequestClassificationView[];
  roles: SpeakerRequestClassificationView[];
  publication_status: string;
  review_status: string;
  created_at: string;
  updated_at: string;
}

/**
 * `POST /v1/units/{unit_id}/speaker-requests` — file one request.
 *
 * The unit is the one the server granted this account
 * (`PortalDescriptor.default_unit_id`), never a value the browser composed. The
 * body carries no tenant, host unit or actor and must never gain one: the server
 * takes all three from the verified bearer token and the path, which is
 * stakeholder Fix #7 (MM-A01).
 *
 * Rejects with `ApiRequestError` on a 4xx, so a caller renders the server's own
 * refusal — an unreleased taxonomy code, an undated request, a virtual request
 * carrying a location — rather than a message the browser made up.
 */
export async function submitSpeakerRequest(
  unitId: string,
  payload: SpeakerRequestPayload,
): Promise<SpeakerRequest> {
  return requestJson<SpeakerRequest>(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-requests`,
    { method: "POST", body: JSON.stringify(payload) },
    { authenticated: true },
  );
}

/**
 * A unit's incoming Speaker Requests, soonest event first (customer §13).
 *
 * `truncated` is an **answer**, not a hint. The server reads one row past its
 * cap and reports the overflow from the same query that produced the rows, so a
 * full page never reads as a complete queue. A client that dropped the flag
 * would show a Connector a partial queue as though it were the whole one.
 */
export interface SpeakerRequestList {
  unit_id: string;
  requests: SpeakerRequest[];
  truncated: boolean;
}

/**
 * `GET /v1/units/{unit_id}/speaker-requests` — what hosts actually asked for.
 *
 * Only requests. The repository restricts the query to
 * `origin = 'coordinator_entry'`, so an extracted event never appears here —
 * a queue promising "what hosts asked for" must not answer with something a
 * crawler produced. There is correspondingly nothing for a caller to merge in.
 *
 * `admin` and `coordinator` only, and authorization runs before any request row
 * is read. Rejects with {@link ApiRequestError} on a 4xx.
 */
export async function fetchSpeakerRequests(unitId: string): Promise<SpeakerRequestList> {
  return requestJson<SpeakerRequestList>(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-requests`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * `GET /v1/units/{unit_id}/host/speaker-requests` — the requests **this
 * Event Host filed**, in the same shape the Connector's queue returns.
 *
 * **OQ-CBA-014**, closed 7 September 2026. This is a different query from
 * {@link fetchSpeakerRequests}, not a narrower view of it: the queue holds
 * every host's filings for the unit and stays `admin`/`coordinator` only,
 * while this route is scoped server-side to `filed_by_user_id ==
 * principal.user_id` and granted to `volunteer` alone. Nothing in the
 * request selects whose rows come back, so this helper takes no filter
 * beyond the unit.
 *
 * A request filed before the `filed_by_user_id` column existed is listed by
 * nobody, including the host who filed it — the column is `NULL` for those
 * rows and was never backfilled. That is a true statement about what the
 * server knows, not a bug in this helper.
 *
 * Rejects with {@link ApiRequestError} on a 4xx, so a `403` renders as the
 * server's own refusal rather than an empty list.
 */
export async function fetchMySpeakerRequests(unitId: string): Promise<SpeakerRequestList> {
  return requestJson<SpeakerRequestList>(
    `/v1/units/${encodeURIComponent(unitId)}/host/speaker-requests`,
    { method: "GET" },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Speaker contacts (CBA-CONTACT-MANAGEMENT, customer §13)
//
// The other end of the arrow from Speaker Requests above. Those are an Event
// Host asking for a speaker; these are a Speaker Connector recording who their
// unit already knows.
//
// Two shapes worth reading before using any of it.
//
// **`contact_email` is sent and is not stored.** The field exists on the
// payload because §13's form collects one; the server discards it and names it
// in `withheld_fields` (OQ-CBA-011, ratified). A caller **must** render that
// array rather than assume a `201` means everything was saved — see
// `SpeakerContact.withheld_fields`. Nothing in this file, and nothing
// server-side, turns that address into something sendable.
//
// **A duplicate name is a `409`, not an update.** Unlike `submitSpeakerRequest`
// directly above — where ADR-0012's identity key makes a resubmission the same
// request — a repeat create here is refused, because the identity derives from
// the name and two different people can share one. `createSpeakerContact`
// rejects with `ApiRequestError` carrying `speaker_contact_name_already_used`,
// and a caller renders the server's own message, which names who is already
// there (OQ-CBA-017).
// ---------------------------------------------------------------------------

/** What a Speaker Connector is recording about one professional. */
export interface SpeakerContactPayload {
  full_name: string;
  company?: string;
  title?: string;
  /** §18's topic/interests/expertise text. */
  topic_text?: string;
  /** §18's optional prior talk information. */
  prior_talk?: string;
  /** §10: city or ZIP is sufficient, and neither is derived from the other. */
  location_city?: string;
  location_postal_code?: string;
  /** One NAICS sector code (customer §7). Singular — a speaker has one primary. */
  primary_industry_code?: string;
  /** One CBA role-category code (customer §8). Singular, for the same reason. */
  primary_role_code?: string;
  /**
   * Accepted by the server and then discarded. Never stored, never a contact
   * channel, never sendable. Present here because §13's form collects it; the
   * response reports it in `withheld_fields`.
   */
  contact_email?: string;
}

/** One stored contact, exactly as the server read it back. */
export interface SpeakerContact {
  professional_id: string;
  owning_unit_id: string;
  full_name: string;
  company: string | null;
  title: string | null;
  topic_text: string | null;
  prior_talk: string | null;
  location_city: string | null;
  location_postal_code: string | null;
  primary_industry_code: string | null;
  industry_taxonomy_version: string | null;
  primary_role_code: string | null;
  role_taxonomy_version: string | null;
  created_at: string;
  updated_at: string;
  /**
   * Whether customer §19's review step has been satisfied on both axes, and
   * therefore whether this contact may enter matching. False for an
   * unclassified contact **and** for one carrying a classifier's proposal
   * nobody has reviewed.
   *
   * Read it; never re-derive it. Inferring eligibility from a null
   * `primary_industry_code` would be a second copy of §19's rule living in a
   * bundle nobody versions, and it cannot tell an unreviewed proposal from an
   * absent one — which are the two states this field exists to separate.
   */
  match_eligible: boolean;
  /**
   * Why this contact may not enter matching yet, or null when it may. A stable
   * token rather than a sentence, so a screen can tell "the classifier proposed
   * Finance and nobody has checked" from "we have no idea where this person
   * works" — two states that call for different actions and would otherwise be
   * one greyed-out row.
   */
  match_ineligibility_reason: string | null;
  /**
   * Fields this request supplied that were deliberately not stored. Empty on
   * reads. **Render it.** An unrendered discard is indistinguishable from a
   * save, which is the belief OQ-CBA-011 exists to prevent.
   */
  withheld_fields: string[];
}

/** A page of one unit's roster. */
export interface SpeakerContactList {
  contacts: SpeakerContact[];
  /** True when more contacts exist than this response carries. */
  truncated: boolean;
}

/** Which classification axes a correction replaces. Omitted means "leave alone". */
export interface ClassificationCorrectionPayload {
  primary_industry_code?: string;
  primary_role_code?: string;
}

/**
 * `POST /v1/units/{unit_id}/speaker-contacts` — record one professional.
 *
 * The unit is the one the server granted this account
 * (`PortalDescriptor.default_unit_id`), never a value the browser composed. The
 * body carries no tenant, owning unit or actor and must never gain one, and it
 * carries no professional id either: the server derives that from the name, so a
 * caller cannot choose somebody else's identity (MM-A01).
 *
 * Rejects with `ApiRequestError` on a 4xx. A `409` carrying
 * `speaker_contact_name_already_used` means this unit already holds a contact
 * under the identity this name derives — render the server's message, which
 * names them.
 */
export async function createSpeakerContact(
  unitId: string,
  payload: SpeakerContactPayload,
): Promise<SpeakerContact> {
  return requestJson<SpeakerContact>(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-contacts`,
    { method: "POST", body: JSON.stringify(payload) },
    { authenticated: true },
  );
}

/** `GET /v1/units/{unit_id}/speaker-contacts` — this unit's roster, by name. */
export async function fetchSpeakerContacts(unitId: string): Promise<SpeakerContactList> {
  return requestJson<SpeakerContactList>(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-contacts`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * `POST /v1/units/{unit_id}/speaker-contacts/{professional_id}/classification`
 * — correct what the pipeline assigned (customer §§7-8, §19).
 *
 * An axis this payload omits is left alone, never cleared. The server stores the
 * current value only: no history, no record of who corrected it, and no
 * inferred-versus-human flag (OQ-CBA-008). A caller must not render a claim
 * about provenance, because there is none to render.
 */
export async function correctSpeakerContactClassification(
  unitId: string,
  professionalId: string,
  payload: ClassificationCorrectionPayload,
): Promise<SpeakerContact> {
  return requestJson<SpeakerContact>(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-contacts/` +
      `${encodeURIComponent(professionalId)}/classification`,
    { method: "POST", body: JSON.stringify(payload) },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Student events (customer §15, card `CBA-STUDENT-EVENTS`)
// ---------------------------------------------------------------------------
//
// Two reads and two writes. The writes arrived with card
// `CBA-STUDENT-REGISTRATION` and migration `0026`, which gave a registration
// its own `event_registration` table. Before that there was no route to call:
// the only table that looked like it would serve, `attendance_record`, is
// attendance, and ADR-0013 makes it the sole input to points — so a row written
// at registration time would have credited somebody for an event they had not
// attended.
//
// Neither write takes a body. The event is in the path and the student is the
// caller, so there is no field naming a subject and there must never be one
// (MM-A01). Idempotency is the server's uniqueness on
// (tenant, subject, event) rather than an `Idempotency-Key` header: a body-less
// request has no identical body for a header key to recognise a repeat of.
//
// Do not add a client-side set of "registered" event ids. The server reports
// whether a place is held on every read, in `StudentEvent.registration`; a
// browser-held set is a claim the next page load cannot confirm, which is
// exactly `docs/plans/frontend-broken-buttons.md` B06's defect.

/** An event's time at whichever precision is actually known (ADR-0010). */
export interface StudentEventTime {
  /** `exact` or `date_only`. Never `unresolved` on either student surface. */
  precision: string;
  /** The instant, present only at `exact` precision. */
  starts_at: string | null;
  /**
   * The instant it finishes, present only when the source stated one. `null` is
   * not a duration of zero and not a default of an hour — it is the absence
   * that makes an .ics refusable rather than guessable.
   */
  ends_at: string | null;
  /** The calendar date, present only at `date_only` precision. */
  on_date: string | null;
  /** The IANA zone the event happens in — never the viewer's or the browser's. */
  time_zone: string | null;
}

/**
 * Whether this caller can download this event's .ics, and where from.
 *
 * Exactly one of `download_path` and `unavailable_reason` is set, which is what
 * makes this usable as a render condition: show the link when there is a path,
 * show the reason when there is not, and never decide for yourself. Do not
 * compose the URL in the browser, and do not render a download control when
 * `available` is false — the server has already evaluated the three conditions
 * `GET .../invite.ics` would refuse on.
 */
export interface StudentEventCalendar {
  available: boolean;
  download_path: string | null;
  /**
   * `event_time_unresolved`, `event_end_unknown`, or `event_not_on_your_agenda`.
   * Null when available.
   */
  unavailable_reason: string | null;
}

/**
 * This caller's registration for one event, or `null` where there has never
 * been one.
 *
 * A registration you cancelled comes back as an object reading `cancelled`, not
 * as `null`. The two are different facts and the server keeps them apart
 * deliberately — a `DELETE` on cancel would have made "you cancelled" and "you
 * never registered" the same absence, and a client that could not tell them
 * apart would have no way to show that a cancellation had taken effect.
 */
export interface StudentEventRegistration {
  /** `registered` — you hold a place — or `cancelled`. There is no waitlist. */
  status: string;
  /**
   * When the place was first taken. Does not move when you cancel and register
   * again.
   */
  registered_at: string;
  /**
   * When the status last moved. Equal to `registered_at` on a registration that
   * has never changed, and a repeated Register does not advance it.
   */
  updated_at: string;
}

/** One event as a student sees it. No review status and no extraction provenance. */
export interface StudentEvent {
  id: string;
  title: string;
  description: string | null;
  time: StudentEventTime;
  is_virtual: boolean;
  location_city: string | null;
  location_postal_code: string | null;
  location: string | null;
  tags: string[];
  /**
   * True when you hold an active registration for this event **or** are
   * recorded at it. Still named for what it is rather than "registered": the
   * narrower name would exclude every event a department recorded you at
   * without you clicking anything — a coordinator entry or an imported roster.
   * Ask `registration` below for the narrower question.
   */
  on_my_agenda: boolean;
  /** Your registration, or null if you have never registered for this event. */
  registration: StudentEventRegistration | null;
  calendar: StudentEventCalendar;
}

/** What a register or cancel left behind, read back out of the server's own row. */
export interface StudentRegistrationResult {
  unit_id: string;
  event_id: string;
  /**
   * Null only from a cancel by a student who had never registered, which writes
   * no row — a registration nobody made is not a thing to record the
   * cancellation of.
   */
  registration: StudentEventRegistration | null;
}

/** The unit's published events, and an honest count of what is not shown. */
export interface StudentEventList {
  unit_id: string;
  events: StudentEvent[];
  /**
   * Events the unit holds but has not published. Render it: without the count,
   * "this unit has nothing for me" and "this unit has nine events it has not
   * published" are the same empty list (ADR-0011).
   */
  withheld_unpublished: number;
  truncated: boolean;
}

/** The caller's own events, soonest first. */
export interface StudentAgenda {
  unit_id: string;
  events: StudentEvent[];
  /** Events you are recorded at whose date could not be resolved (ADR-0010 rule 2). */
  withheld_unresolved_date: number;
  truncated: boolean;
}

/**
 * `GET /v1/units/{unit_id}/student/events` — the unit's published catalog.
 *
 * The unit is the one the server granted this account
 * (`PortalDescriptor.default_unit_id`), never a value the browser composed. The
 * server authorizes it again per request, deny-by-default and tenant-scoped.
 */
export async function fetchStudentEvents(unitId: string): Promise<StudentEventList> {
  return requestJson<StudentEventList>(
    `/v1/units/${encodeURIComponent(unitId)}/student/events`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * `GET /v1/units/{unit_id}/student/agenda` — the events you are recorded at.
 *
 * Scoped to the caller by the server's own query, not by anything sent from
 * here: there is no subject parameter and there must never be one (MM-A01).
 */
export async function fetchStudentAgenda(unitId: string): Promise<StudentAgenda> {
  return requestJson<StudentAgenda>(
    `/v1/units/${encodeURIComponent(unitId)}/student/agenda`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * `POST /v1/units/{unit_id}/student/events/{event_id}/registration` — take a
 * place at an event (customer §15).
 *
 * No body, and that absence is the self-scope: the server takes the student
 * from the verified principal, so there is no field through which a caller
 * could name somebody else (MM-A01).
 *
 * Safe to call twice. The server's uniqueness on (tenant, subject, event) makes
 * a second call the same registration rather than a second one — it answers
 * `201` the first time and `200` afterwards, and this function returns the same
 * stored row either way. A caller does **not** need to check first, and should
 * not disable the control on the strength of its own memory of having clicked.
 */
export async function registerForEvent(
  unitId: string,
  eventId: string,
): Promise<StudentRegistrationResult> {
  return requestJson<StudentRegistrationResult>(
    `/v1/units/${encodeURIComponent(unitId)}/student/events/` +
      `${encodeURIComponent(eventId)}/registration`,
    { method: "POST" },
    { authenticated: true },
  );
}

/**
 * `DELETE /v1/units/{unit_id}/student/events/{event_id}/registration` — give up
 * your place.
 *
 * Addresses your claim on the event: after it you hold none. The server keeps
 * the row and moves its status to `cancelled` rather than deleting it, and says
 * so in the response — so render what comes back rather than assuming an
 * absence.
 *
 * Idempotent in both directions a caller can reach it: cancelling an
 * already-cancelled registration, and cancelling one that never existed, are
 * both `200` and neither is an error. The second returns `registration: null`,
 * because a registration nobody made leaves nothing to cancel.
 */
export async function cancelEventRegistration(
  unitId: string,
  eventId: string,
): Promise<StudentRegistrationResult> {
  return requestJson<StudentRegistrationResult>(
    `/v1/units/${encodeURIComponent(unitId)}/student/events/` +
      `${encodeURIComponent(eventId)}/registration`,
    { method: "DELETE" },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Speaker-contact channels (customer §13, consent — appended for the
// invitation-compose surface)
//
// One read, and it exists so that "why can I not invite this person" is
// answerable *before* a batch is composed rather than only afterwards, out of
// the batch's skip reasons.
//
// **`send_eligible` is the server's answer and is never recomputed here.** The
// route computes it at read time from the row's lifecycle state, its consent
// source and a live suppression join, all three together. A browser that
// derived "consented" from any subset of those would be a second answer to
// "may we write to this person", and the disagreement between two such answers
// resolves toward sending every time. So this client reads the boolean and
// renders the three inputs beside it as explanation — never as arithmetic.
//
// A person with no channel at all returns an empty list, which is the ordinary
// case for a contact added through the §13 form (that form writes no channel;
// OQ-CBA-011) and is the honest answer rather than a 404.
// ---------------------------------------------------------------------------

/** One channel belonging to one §13 roster contact, exactly as the server read it. */
export interface SpeakerContactChannel {
  contact_channel_id: string;
  professional_id: string;
  /** `"email"` today. Reported rather than assumed. */
  channel_kind: string;
  address: string;
  /** The lifecycle state — `"active_candidate"` is the only one a send may use. */
  contact_state: string;
  /** Under a suppression record. Outranks every consent record and state. */
  suppressed: boolean;
  /**
   * Whether a send may address this channel: an active candidate, an approved
   * consent source, and no suppression. All three, always. **Read it; never
   * re-derive it.**
   */
  send_eligible: boolean;
  /** Where the consent came from, or null when nothing was recorded. */
  consent_source: string | null;
  consent_recorded_at: string | null;
  consent_evidence: string | null;
  created_at: string;
  updated_at: string;
}

/** One channel and the trail of every move made to it. */
export interface SpeakerContactChannelWithHistory {
  channel: SpeakerContactChannel;
  transitions: Array<{
    from_state: string | null;
    to_state: string;
    reason: string | null;
    occurred_at: string;
  }>;
}

/** A page of one roster contact's channels. */
export interface SpeakerContactChannelList {
  professional_id: string;
  channels: SpeakerContactChannelWithHistory[];
  limit: number;
  offset: number;
}

/**
 * `GET /v1/units/{unit_id}/speaker-contacts/{professional_id}/channels`
 *
 * Rejects with `ApiRequestError` carrying a `404` when the person is not on
 * this unit's roster — which is a different fact from "holds no channel", and
 * the two must not be folded together by a caller.
 */
export async function fetchSpeakerContactChannels(
  unitId: string,
  professionalId: string,
): Promise<SpeakerContactChannelList> {
  return requestJson<SpeakerContactChannelList>(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-contacts/` +
      `${encodeURIComponent(professionalId)}/channels`,
    { method: "GET" },
    { authenticated: true },
  );
}

// CBA speaker handoff (CBA-HANDOFF-PIPELINE, customer §6 step 9)
//
// The far end of the arrow `submitSpeakerRequest` starts: an Event Host asked
// for a speaker, a Connector matched and invited one, and this is where the
// Host is handed whoever agreed to come.
//
// Two properties of `routers/cba_handoff.py` decide what a caller may render,
// and both are easy to lose in a refactor.
//
// **The Host is handed acceptances, and nothing about the people who did not
// accept.** OQ-CBA-042 settles that narrowly and on purpose: an Event Host
// learning that three named professionals turned them down learns a fact about
// those people that nobody agreed to share. Neither shape below carries an
// invitation answer, a count of them, or a batch total, and a caller must not
// reconstruct one from another surface — the invitation tracking is the Speaker
// Connector's by name.
//
// **Nothing here is asserted by the browser.** `SpeakerHandoffPayload` names an
// invitation and, optionally, an attendance row; every funnel step and every
// timestamp written is read out of those stored rows server-side. There is
// deliberately nothing in the body for a browser to toggle.
// ---------------------------------------------------------------------------

/**
 * One step of a speaker's funnel journey, beside the stored row that makes it
 * true.
 *
 * `occurred_at` is the evidencing row's own timestamp — an invitation's
 * `dispatched_at`, an attendance record's own clock — never a server reading
 * taken when the handoff was reconciled. So rendering it as "when this
 * happened" is honest, and rendering it as "when we recorded it" is not.
 *
 * Empty on the list surface, which reads stored rows rather than re-deriving
 * the plan behind them. A caller must treat `[]` as "not reported here", never
 * as "no evidence exists".
 */
export interface SpeakerHandoffStageEvidence {
  stage: string;
  /**
   * Which kind of stored row supports it: `invitation_composed`,
   * `invitation_dispatched`, `invitation_accepted` or `attendance_record`.
   */
  evidence: string;
  occurred_at: string;
}

/**
 * One confirmed speaker, as an Event Host is handed them.
 *
 * Carries no member-inquiry field, mirroring `ConfirmedSpeakerView`: the
 * capability is off under `ProductScope.CBA` and the API honours that
 * structurally rather than by filtering at the edge, so there is no field here
 * for a surface to render by accident.
 *
 * The three identity fields are `null` when the tenant holds no
 * `speaker_profile` for the id — an honest unknown, never a blank name standing
 * in for one. The speaker is identified by `professional_id`; the name is for
 * display and nothing is derived from it.
 */
export interface ConfirmedSpeaker {
  record_id: string;
  professional_id: string;
  event_id: string;
  full_name: string | null;
  company: string | null;
  title: string | null;
  /** The furthest CBA step reached, derived server-side from the timestamps below. */
  current_stage: string;
  matched_at: string;
  contacted_at: string | null;
  confirmed_at: string;
  attended_at: string | null;
  attendance_id: string | null;
  stages: SpeakerHandoffStageEvidence[];
}

/** The confirmed speakers a unit can hand its Event Hosts. */
export interface ConfirmedSpeakerList {
  unit_id: string;
  /** The event this list was filtered to, or `null` when it covers the unit. */
  event_id: string | null;
  speakers: ConfirmedSpeaker[];
}

/**
 * `GET /v1/units/{unit_id}/cba/confirmed-speakers` — who agreed to come.
 *
 * Speakers whose `confirmed_at` is set, ordered by it, so a Host reads them in
 * the order they said yes. Optionally narrowed to one event.
 *
 * An empty `speakers` array means exactly one thing: nobody is confirmed. It is
 * not a report about invitations and a caller must not explain it as one —
 * "nobody has accepted yet" and "four people were asked" are different facts,
 * and the second belongs to the Connector (OQ-CBA-042).
 *
 * `admin` and `coordinator` only, authorized per request against the loaded
 * unit. A caller the server refuses gets {@link ApiRequestError} with status
 * `403`, which is an answer to render rather than a state to hide.
 */
export async function fetchConfirmedSpeakers(
  unitId: string,
  eventId?: string,
): Promise<ConfirmedSpeakerList> {
  const query = eventId ? `?event_id=${encodeURIComponent(eventId)}` : "";
  return requestJson<ConfirmedSpeakerList>(
    `/v1/units/${encodeURIComponent(unitId)}/cba/confirmed-speakers${query}`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * What to reconcile: an invitation, and optionally the attendance a presented
 * talk is cited from.
 *
 * There is no `stage` field and no `reached_at` field, and their absence is the
 * contract rather than an omission. A request names a record that already says
 * something happened; it cannot say so itself.
 */
export interface SpeakerHandoffPayload {
  /**
   * The `cba_invitation` whose stored answer is the evidence for Confirmed.
   * Must belong to this unit, and must record an accepted invitation — an
   * invitation carrying any other answer is a `409`, not a confirmation.
   */
  invitation_id: string;
  /**
   * The `attendance_record` an Attended journey cites. Optional: a speaker who
   * has agreed but not yet presented is the ordinary state. It is cited here
   * and never created here.
   */
  attendance_id?: string;
}

/**
 * What the reconciliation wrote, and the speaker it leaves behind.
 *
 * `applied` is only the stages *this* request wrote, so a replay returns an
 * empty array beside an unchanged speaker. "They are confirmed" and "this
 * request confirmed them" stay separable, and a caller must render the
 * distinction rather than reporting a write it did not cause.
 */
export interface SpeakerHandoffResult {
  applied: string[];
  speaker: ConfirmedSpeaker;
}

/**
 * `POST /v1/units/{unit_id}/cba/events/{event_id}/speaker-handoff` — bring one
 * speaker's journey up to whatever the stored evidence already supports.
 *
 * `200`, not `202`: the writes land in this request or they do not, and the
 * speaker returned is read back through the same query the Host's own list
 * uses. There is no `Idempotency-Key` — the operation is idempotent in the
 * data, because every step and every timestamp derives from a stored row.
 *
 * Rejects with {@link ApiRequestError}: `404` when the invitation is not in this
 * unit or the event not in this tenant; `409` when the invitation records no
 * acceptance (`cba_invitation_not_accepted`), when the cited attendance is not
 * this journey's, or when the stored timestamps cannot be ordered into the
 * funnel; `403` when the server does not grant this account the operation.
 * Render the server's own message — it says which of those happened.
 */
export async function reconcileSpeakerHandoff(
  unitId: string,
  eventId: string,
  payload: SpeakerHandoffPayload,
): Promise<SpeakerHandoffResult> {
  return requestJson<SpeakerHandoffResult>(
    `/v1/units/${encodeURIComponent(unitId)}/cba/events/` +
      `${encodeURIComponent(eventId)}/speaker-handoff`,
    { method: "POST", body: JSON.stringify(payload) },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Student speaker feedback (OQ-CBA-003) — customer §§15-16
// ---------------------------------------------------------------------------

/**
 * What a student says about one speaker they heard.
 *
 * Two fields, because OQ-CBA-003 approved one overall dimension and customer
 * §16 says not to over-design the requirement. There is no `student_id` here
 * and there is none on any type below: every route takes the author from
 * `principal.user_id` and accepts one in no body and no path, so a field for it
 * would be a field the server has nothing to receive.
 */
export interface SpeakerFeedbackSubmission {
  /**
   * 1 through 5. Required, and there is no zero on this scale — a speaker
   * nobody rated has no row, which is a different fact from a speaker rated
   * badly. To take one back, call {@link withdrawSpeakerFeedback}; do not send
   * a sentinel the server would reject anyway.
   */
  rating: number;
  /**
   * Optional free text. Omit it, or send `null`, when the student wrote
   * nothing. A blank or whitespace-only string is normalized to absent
   * server-side rather than stored, so there is no third state between "wrote
   * nothing" and "wrote something".
   */
  comment?: string | null;
}

/**
 * When a rating stops being its author's to change.
 *
 * Read `state`; never compare a date in the browser. The window closes seven
 * days after the event and the server resolves it from the event's own anchor —
 * a page doing its own arithmetic would be a second copy of the rule, and would
 * get it wrong for every event whose date is not resolved.
 */
export interface StudentSpeakerFeedbackWindow {
  /**
   * `open`, `closed`, or `unknown`. `unknown` means the event carries no
   * resolved date, so no cutoff can be measured — which is neither a cutoff
   * that has not arrived nor one that has. Render it as the third thing it is.
   */
  state: string;
  /** When the window shuts, ISO-8601, or `null` when the state is `unknown`. */
  closes_at: string | null;
}

/**
 * One of the caller's own ratings, as the server stored it.
 *
 * Carries no student identifier. Not because it would leak — these are the
 * caller's own rows — but because a field that exists nowhere in this lane
 * cannot be copied onto a Connector's surface later, which is where OQ-CBA-003
 * part 1 would actually be lost.
 */
export interface StudentSpeakerFeedback {
  speaker_professional_id: string;
  /** `submitted` or `withdrawn`. */
  status: string;
  /**
   * 1 to 5, or `null` on a withdrawn rating. Null is an absence, never a zero:
   * the rating was taken back, not scored badly (ADR-0011 rule 1).
   */
  rating: number | null;
  /**
   * The student's words, or `null`. Null both when they wrote none and after a
   * withdrawal took them back — a retraction takes back the words as well as
   * the number.
   */
  comment: string | null;
  submitted_at: string;
  updated_at: string;
  edit_window: StudentSpeakerFeedbackWindow;
}

/**
 * The result of one submit or withdraw.
 *
 * `changed` is the field that keeps this honest. A repeat of an identical
 * submission, and a withdrawal with nothing to withdraw, both return `false` —
 * so "this is your rating" and "this request changed it" stay separable, and a
 * page must not collapse them into one confirmation.
 */
export interface StudentSpeakerFeedbackResult {
  /**
   * The rating as it now stands, or `null` from a withdrawal by a student who
   * never rated this speaker — which stores nothing rather than manufacturing a
   * pre-withdrawn row.
   */
  feedback: StudentSpeakerFeedback | null;
  changed: boolean;
}

/** What this student has already said about speakers at one event. */
export interface StudentSpeakerFeedbackList {
  unit_id: string;
  event_id: string;
  /**
   * Withdrawn rows are included. "You withdrew this" and "you have not rated
   * this speaker" are different states, and this is the one surface that has to
   * tell them apart.
   */
  feedback: StudentSpeakerFeedback[];
}

/**
 * `POST /v1/units/{unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback`
 * — rate a speaker at an event you attended, or amend the rating you left.
 *
 * Submit and amend are the same call: the row is unique per student, event and
 * speaker, so a second submission replaces the first rather than adding one.
 *
 * The server refuses, in words, every reason this is not allowed, and each
 * refusal is about a fact the caller already has. {@link ApiRequestError}:
 * `404 event_not_found` or `404 speaker_contact_not_found`;
 * `403 student_feedback_not_eligible` when there is no attendance record for
 * this caller at this event — feedback is limited to what you attended;
 * `409 student_feedback_window_closed` once the cutoff has passed. Render the
 * server's own message, which says which of those happened.
 *
 * `student` role only, authorized per request against the loaded unit. The
 * author is taken from the session and cannot be supplied.
 */
export async function submitSpeakerFeedback(
  unitId: string,
  eventId: string,
  speakerId: string,
  payload: SpeakerFeedbackSubmission,
): Promise<StudentSpeakerFeedbackResult> {
  return requestJson<StudentSpeakerFeedbackResult>(
    `/v1/units/${encodeURIComponent(unitId)}/student/events/` +
      `${encodeURIComponent(eventId)}/speakers/${encodeURIComponent(speakerId)}/feedback`,
    { method: "POST", body: JSON.stringify(payload) },
    { authenticated: true },
  );
}

/**
 * `DELETE /v1/units/{unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback`
 * — take a rating back.
 *
 * A route of its own rather than a submission carrying a sentinel. The row
 * survives with its attribution — migration `0031` explains why dropping it
 * would break retraction, de-duplication and abuse tracing at once — and the
 * number and the words are cleared.
 *
 * Refuses the same way the submission does, with the same codes. Withdrawing
 * something never rated is a `200` carrying `changed: false`, not an error:
 * there is nothing wrong with the request, and nothing happened.
 */
export async function withdrawSpeakerFeedback(
  unitId: string,
  eventId: string,
  speakerId: string,
): Promise<StudentSpeakerFeedbackResult> {
  return requestJson<StudentSpeakerFeedbackResult>(
    `/v1/units/${encodeURIComponent(unitId)}/student/events/` +
      `${encodeURIComponent(eventId)}/speakers/${encodeURIComponent(speakerId)}/feedback`,
    { method: "DELETE" },
    { authenticated: true },
  );
}

/**
 * `GET /v1/units/{unit_id}/student/events/{event_id}/speaker-feedback` — what
 * you have already said about speakers at this event.
 *
 * Scoped to the caller by the server, which takes the student from the session:
 * there is no parameter this could be aimed at somebody else with, and adding
 * one to this signature would not create the route that honours it.
 *
 * Withdrawn rows come back too, because "you withdrew this" and "you have not
 * rated this speaker" have to be told apart on the one surface that shows both.
 *
 * **A student surface's read.** It returns rows carrying ratings and comments,
 * and it must not be called from a Connector page — the Connector's read is
 * {@link fetchSpeakerFeedbackSummary} and nothing else (OQ-CBA-003 part 1).
 */
export async function fetchMySpeakerFeedback(
  unitId: string,
  eventId: string,
): Promise<StudentSpeakerFeedbackList> {
  return requestJson<StudentSpeakerFeedbackList>(
    `/v1/units/${encodeURIComponent(unitId)}/student/events/` +
      `${encodeURIComponent(eventId)}/speaker-feedback`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * How students rated one speaker, in aggregate. Three numbers and a sentence.
 *
 * There is no field here a student could be named in, and there is no route
 * that would fill one. That is OQ-CBA-003 part 1 held as a type rather than as
 * a discipline a reviewer has to remember.
 */
export interface SpeakerFeedbackSummary {
  speaker_professional_id: string;
  /**
   * True when fewer than `minimum_responses` students have rated this speaker.
   * Both numbers below are then `null` — the count is withheld along with the
   * mean rather than published beside it, because "two students rated this
   * speaker" narrows the field considerably in a class of thirty.
   */
  suppressed: boolean;
  /** How many ratings the mean was computed from, or `null` when suppressed. */
  response_count: number | null;
  /**
   * The average, to two decimals, or `null` when suppressed. Never coerce it to
   * `0`: ADR-0011 rule 1, a value with no evidence is unknown, and a speaker
   * nobody rated must not read as a speaker rated zero.
   */
  mean_rating: number | null;
  /**
   * What to render. Reads "not enough responses yet" when suppressed — a
   * sentence rather than a dash or a zero, so a reader can tell "we are not
   * telling you" from "the answer is nothing".
   */
  display_text: string;
  /**
   * The threshold below which nothing is published. Sent so a surface can
   * explain a suppression without hard-coding the number, which is a decided
   * value and can move.
   */
  minimum_responses: number;
}

/**
 * `GET /v1/units/{unit_id}/speakers/{speaker_id}/feedback-summary` — the
 * Connector's read, and the only one they have.
 *
 * Customer §16's "Speaker Connectors/admin users must be able to view the
 * feedback", read as an aggregate rather than a transcript. No student is
 * named, no individual rating is returned, and there is deliberately no route
 * that lists them: thirty rows carrying timestamps and free text re-identify
 * their authors whether or not a column says so.
 *
 * These ratings are **not** a matching input. OQ-CBA-053 settles it: student
 * speaker feedback is an event outcome, no factor reads the table, and nothing
 * derived from it enters a score. A surface rendering this beside a roster must
 * say so rather than leaving a reader to assume the obvious wrong thing.
 *
 * A speaker not on this unit's roster is a `404`, not an empty summary, so the
 * route cannot be used to enumerate ids. `admin` and `coordinator` only; a
 * caller the server refuses gets {@link ApiRequestError} with status `403`,
 * which is an answer to render rather than a state to hide.
 */
export async function fetchSpeakerFeedbackSummary(
  unitId: string,
  speakerId: string,
): Promise<SpeakerFeedbackSummary> {
  return requestJson<SpeakerFeedbackSummary>(
    `/v1/units/${encodeURIComponent(unitId)}/speakers/` +
      `${encodeURIComponent(speakerId)}/feedback-summary`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * How students rated a whole unit's speakers, pooled — the Connector
 * dashboard's read, and not a sum this browser is allowed to produce itself.
 *
 * **Not a total of the per-speaker aggregates.** A suppressed per-speaker
 * summary contributes `null`, so a client-side fold either drops it
 * (undercounting) or republishes what suppression withheld. This is one
 * server query with its own suppression rule.
 *
 * **Suppression here is not the same test as the per-speaker route's.** The
 * per-speaker summary is public to the same reader, so a pooled `n` can be
 * *differenced* against an already-published speaker's count to isolate a
 * smaller, still-suppressed group. The unit aggregate is published only when
 * the pool clears `minimum_responses` **and** the residual against every
 * published speaker is zero or itself at or above that threshold. A unit
 * with a large pool can therefore still be `suppressed`, and that is the
 * rule working, not failing.
 */
export interface UnitFeedbackSummary {
  unit_id: string;
  /**
   * True when the pooled aggregate is withheld — below threshold, or because
   * publishing it would let a reader difference an already-published
   * speaker's aggregate out of it. Both numbers below are then `null`.
   */
  suppressed: boolean;
  /** How many ratings, across the unit, the mean was computed from, or `null` when suppressed. */
  response_count: number | null;
  /** The unit's average, to two decimals, over the pooled ratings, or `null` when suppressed. */
  mean_rating: number | null;
  /**
   * What to render. Carries the server's own reason for a suppression — a
   * sentence, not a dash or a zero, so "we are withholding this" reads as
   * distinct from "the answer is nothing".
   */
  display_text: string;
  /** The threshold below which nothing is published. Never hard-code it; render this instead. */
  minimum_responses: number;
}

/**
 * `GET /v1/units/{unit_id}/speaker-feedback-summary` — the Connector
 * dashboard's one read for feedback across the whole unit.
 *
 * `admin`/`coordinator` only, and there is no per-speaker breakdown, no
 * rated-speaker count and no list of speaker ids on this response — every
 * extra number would be a handle to difference the pooled one against, which
 * is exactly what the suppression rule above exists to close. Rejects with
 * {@link ApiRequestError} on a 4xx.
 */
export async function fetchUnitSpeakerFeedbackSummary(
  unitId: string,
): Promise<UnitFeedbackSummary> {
  return requestJson<UnitFeedbackSummary>(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-feedback-summary`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * What one scoring mode would actually score with, right now.
 *
 * Derived server-side on every read from the factor registry plus this unit's
 * overrides, and — this is the part a client must not undo — **never stored**.
 * `weights` is already normalized over the mode's factors. A browser that
 * renormalized it, rounded it, or totalled it would be publishing a second
 * opinion about a number the server already settled.
 */
export interface ScoringModeWeights {
  scoring_mode: string;
  registry_version: string;
  /** Factor key to effective weight, as the server computed it for this response. */
  weights: Record<string, number>;
}

/**
 * `GET /v1/units/{unit_id}/matching-weights` — one unit's weight configuration.
 *
 * Two fields are easy to confuse and must not be. `overrides` is what this unit
 * has deliberately stored, and a factor absent from it has **no stored weight
 * anywhere**; `modes` is what a run would score with today. A panel renders the
 * first as "not set" rather than filling in what it guesses the registry says —
 * a printed default is a second copy of the registry that keeps showing
 * yesterday's figure after ADR-0016 revises it.
 *
 * `version` is null for a unit that has never configured anything. Echo whatever
 * it is back as {@link MatchingWeightsUpdatePayload.expected_version}.
 *
 * `ignored_factor_keys` holds stored keys no current registry model admits. The
 * server reports them instead of dropping them; so must anything rendering this.
 */
export interface MatchingWeights {
  unit_id: string;
  registry_version: string;
  configurable_factors: string[];
  overrides: Record<string, number>;
  modes: ScoringModeWeights[];
  version: number | null;
  updated_by_user_id: string | null;
  updated_at: string | null;
  ignored_factor_keys: string[];
}

/**
 * A proposed weighting for one unit.
 *
 * `overrides` is the **complete** override set after the change, not a patch of
 * a patch: `{}` returns the unit to the registry's weights, and omitting a
 * factor that was previously overridden clears that override.
 *
 * `expected_version` is the version a prior read returned. Sending it is what
 * turns a concurrent edit into a `409 matching_weights_stale` instead of a
 * silent overwrite of somebody else's save; omitting it is last-write-wins.
 */
export interface MatchingWeightsUpdatePayload {
  overrides: Record<string, number>;
  expected_version?: number | null;
}

/**
 * Read a unit's matching weights and the version they are at.
 *
 * `admin` and `coordinator` only, authorized per request against the loaded
 * unit — a UI that renders a panel grants nothing. A caller the server refuses
 * gets {@link ApiRequestError} with status `403`, which is an answer to render
 * rather than a state to hide.
 */
export async function fetchMatchingWeights(unitId: string): Promise<MatchingWeights> {
  return requestJson<MatchingWeights>(
    `/v1/units/${encodeURIComponent(unitId)}/matching-weights`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * `PATCH /v1/units/{unit_id}/matching-weights` — change what the next run scores with.
 *
 * Nothing is normalized, clamped or dropped on the way through, here or on the
 * server: an inadmissible proposal comes back as {@link ApiRequestError} with
 * status `422` and code `invalid_matching_weights`, whose message names every
 * offending field at once. A stale `expected_version` comes back as `409` with
 * code `matching_weights_stale` — a conflict a person resolves by re-reading,
 * never a retry a client performs on their behalf.
 *
 * The response is the stored configuration read back, including its new
 * `version`. It is the only thing a caller may show as saved.
 *
 * This changes no recorded match run. A `match_run` row carries the weights it
 * was scored with and is immutable; a new weighting applies to the next run
 * submitted and re-runs nothing.
 */
export async function updateMatchingWeights(
  unitId: string,
  payload: MatchingWeightsUpdatePayload,
): Promise<MatchingWeights> {
  return requestJson<MatchingWeights>(
    `/v1/units/${encodeURIComponent(unitId)}/matching-weights`,
    { method: "PATCH", body: JSON.stringify(payload) },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Pilot statistics for the Speaker Connector (TRACK 14)
//
// Two reads, both of which count server-side. That is the whole point of them:
// the numbers a Connector's landing surface shows are numbers a query owns and
// can be drilled into, not sums a browser produced from lists it happened to
// have loaded (ADR-0011 rules 1 and 3).
// ---------------------------------------------------------------------------

/**
 * `GET /v1/units/{unit_id}/metrics?surface=cba` — the register as CBA presents it.
 *
 * The same route {@link fetchUnitMetrics} calls, asked a different question.
 * `surface` is a real query parameter and the **server** decides what `cba`
 * means: `pipeline_member_inquiry` omitted, because
 * `Capability.MEMBER_INQUIRY_NARRATIVE` is off under `ProductScope.CBA`, and
 * the four funnel metrics relabelled for a surface whose subject is a speaker
 * ("Speakers matched" rather than "Matched"). Asking for the default view and
 * dropping the entry in the browser would be a second copy of that exclusion
 * list, and the browser's copy is the one that goes stale after the register
 * moves.
 *
 * Every `MetricSummary` it returns is measured or explicitly unknown, never
 * both and never neither: `value` is `null` exactly when no evidence source
 * exists, and `unknown_reason` says which. A caller that coerced that null to a
 * zero would turn "we cannot answer" into "the answer is none" — the
 * substitution ADR-0011 rule 1 exists to prevent — so read `value === null`
 * first and render the reason.
 *
 * A measured `0` is a real answer and must render as one. "No `pipeline_record`
 * rows exist for this unit" is what the funnel metrics currently measure
 * everywhere, because no write path advances a funnel stage yet; that is a
 * different claim from "no matching has happened", and nothing on either side
 * of this call can tell the two apart.
 *
 * Aggregates are `admin`-tenant-wide and otherwise decided by subtree
 * containment, per request against the loaded unit. A caller the server refuses
 * gets {@link ApiRequestError} with status `403`, which is an answer to render
 * rather than a state to hide.
 */
export async function fetchCbaUnitMetrics(unitId: string): Promise<MetricsResponse> {
  return requestJson<MetricsResponse>(
    `/v1/units/${encodeURIComponent(unitId)}/metrics?surface=cba`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * One unit's attendance evidence, counted. Never a roster.
 *
 * `total` is the sum of `by_method`, **folded server-side from the same counts
 * this response carries**. It is a field rather than something a caller adds up
 * for exactly the reason the route documents: a client-side total is a second
 * calculation of a published number, and the two disagree the first time a
 * method is added to `ck_attendance_record_method`.
 *
 * `by_method` always carries all three allowed mechanisms — `qr_scan`,
 * `coordinator_entry`, `import` — and a mechanism with no rows is a measured
 * `0`, not an absent key. `distinct_subjects` is a count and nothing more:
 * there is no route that lists the accounts behind it while D8 is open, and
 * this type has no field one could be put in.
 *
 * The two instants are `null` when nothing has been recorded, which is the one
 * honest way to say "there is no earliest row".
 */
export interface AttendanceSummary {
  unit_id: string;
  /** Attendance rows recorded for this unit; the server's own fold of `by_method`. */
  total: number;
  /** Row count per allowed mechanism. All three keys are always present. */
  by_method: Record<string, number>;
  /** How many different accounts those rows belong to — a count, never a list. */
  distinct_subjects: number;
  /** How many different events those rows attest to. */
  distinct_events: number;
  /** When the earliest row was recorded, or `null` when there are none. */
  first_recorded_at: string | null;
  /** When the latest was recorded, or `null` when there are none. */
  last_recorded_at: string | null;
}

/**
 * `GET /v1/units/{unit_id}/engagement/attendance-summary` — how much evidence
 * this unit holds.
 *
 * A unit with nothing recorded answers `total: 0`, all three methods at `0`,
 * and two null instants. That zero is *measured* — the query ran and found
 * none — which is a different claim from "we did not look", and a surface that
 * rendered the two the same way would be discarding the distinction the route
 * was built to preserve.
 *
 * Authorization runs before any attendance row is read, against the unit the
 * counts are scoped to. `admin` and `coordinator` only, with no tenant-wide
 * widening: a caller the server refuses gets {@link ApiRequestError} with
 * status `403`, and a unit in another tenant is a `404` rather than a `403`
 * that would confirm the id names something real.
 */
export async function fetchAttendanceSummary(unitId: string): Promise<AttendanceSummary> {
  return requestJson<AttendanceSummary>(
    `/v1/units/${encodeURIComponent(unitId)}/engagement/attendance-summary`,
    { method: "GET" },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// A unit's presentable events (`GET /v1/units/{unit_id}/events`)
//
// The route the coordinator portal was not calling. It has existed since the
// discovery slice — `routers/events.py` — while the portal went on rendering an
// "unavailable" panel for hosted events beside it, which said something false
// about this deployment rather than something true about the legacy backend.
//
// Two things about the response shape are load-bearing and neither may be
// flattened by a caller.
//
// `time` is a view, not a timestamp (ADR-0010). A `date_only` event has no
// instant, and reporting one — midnight in some zone — is the fabrication that
// ADR exists to stop, so `precision` says which of `starts_at` and `on_date` is
// real and a renderer reads that rather than inferring it from a null.
//
// The two `withheld_*` counts are what keep an empty list meaningful: no events
// and nothing withheld means the unit has none, while no events and seven
// withheld means the unit has seven the pipeline could not finish. ADR-0011's
// rule is that an unknown is never rendered as a zero, and the corollary this
// response applies is that an omission is never rendered as an absence. Render
// them.
// ---------------------------------------------------------------------------

/**
 * An event's time at whichever precision is actually known (ADR-0010).
 *
 * Never collapsed to one nullable instant. `precision` is `exact`, `date_only`,
 * or `unresolved`; `ends_at` is null when the source stated no end rather than
 * when the event lasts no time, which is the absence that makes a calendar
 * download refusable rather than guessable.
 */
export interface UnitEventTime {
  precision: string;
  starts_at: string | null;
  ends_at: string | null;
  on_date: string | null;
  /** The IANA zone the event happens in — never the viewer's or the server's. */
  time_zone: string | null;
}

/**
 * Where the event came from (ADR-0012), as its own object.
 *
 * Every field but `origin` is null on a `coordinator_entry` event: a human
 * typing an event fetched nothing, and a source URL invented to fill the column
 * would be a fabricated field arriving through a response model.
 */
export interface UnitEventProvenance {
  origin: string;
  source_url: string | null;
  fetched_at: string | null;
  extractor_version: string | null;
}

/** One presentable event, as a coordinator's unit listing returns it. */
export interface UnitEventSummary {
  id: string;
  title: string;
  description: string | null;
  time: UnitEventTime;
  /** Mapped vocabulary terms only. A quarantined value has no term to carry. */
  tags: string[];
  publication_status: string;
  review_status: string;
  provenance: UnitEventProvenance;
}

/** The unit's presentable events, and an honest account of what is missing. */
export interface UnitEventList {
  unit_id: string;
  events: UnitEventSummary[];
  /** Excluded because no date could be resolved (ADR-0010 rule 2). Render it. */
  withheld_unresolved_date: number;
  /** Excluded because a tag value awaits human review (ADR-0012). Render it. */
  withheld_quarantined_tags: number;
  /** True when the unit holds more presentable events than the response cap returns. */
  truncated: boolean;
}

/**
 * The three statuses a review item may be listed at.
 *
 * Mirrors the server's `ReviewItemStatusFilter`, which is a `Literal` for the
 * reason worth repeating on this side: there is deliberately no "all" member.
 * A caller always names exactly one status, so no value a UI could pass — an
 * empty string, an unset variable — resolves to "every row". The server refuses
 * anything outside this union with a `422` rather than widening the query.
 */
export type ReviewItemStatus = "pending" | "accepted" | "rejected";

/**
 * One quarantined import row awaiting — or carrying — a coordinator's decision.
 *
 * `row_data` is the submitted record verbatim, and its shape is genuinely
 * unknown to this client: it is whatever columns the import carried, which vary
 * by dataset. It is typed as an open record rather than given invented fields,
 * because a type that claimed to know the columns would be wrong for the first
 * import that carried different ones.
 *
 * There is no `decided_by`, and its absence is a decision rather than an
 * oversight. The column exists on the row and holds a `user_account` id; no
 * route in this API discloses one, and the list route deliberately does not
 * become the first. A field added here would be permanently null, which reads
 * as "nobody decided it" rather than "we are not told".
 *
 * `decided_at` is `null` for exactly the pending rows — undecided, never
 * unknown (ADR-0011 rule 1). A surface that rendered it as a dash or a zero
 * date would be discarding that distinction.
 */
export interface ReviewItem {
  id: string;
  /** The import that submitted this row; rows from one import share it. */
  import_batch_id: string;
  /** This row's position within its import batch, from zero. */
  row_index: number;
  status: ReviewItemStatus;
  /** The submitted record, exactly as the import wrote it. Columns vary by dataset. */
  row_data: Record<string, unknown>;
  created_at: string;
  /** When this item was decided, or `null` while it is still pending. */
  decided_at: string | null;
}

/**
 * One unit's review items at one status.
 *
 * Carries no count, of these items or of the unit's pending total. That number
 * has an owning query — `GET /v1/units/{unit_id}/metrics` — and ADR-0011 rule 4
 * is that it is read from there rather than recomputed beside it.
 * `items.length` is the length of *this page* and is not a total whenever
 * `truncated` is true.
 *
 * `truncated` is measured rather than guessed: the server reads one row beyond
 * its cap and reports whether it came back. A surface that ignored it would
 * render a full page as a complete one, which is the silent-zero failure
 * ADR-0011 rule 1 forbids.
 */
export interface ReviewItemListResponse {
  unit_id: string;
  /** The status these items were filtered to; echoes the request. */
  status: ReviewItemStatus;
  items: ReviewItem[];
  /** True when more items exist at this status than the response cap returned. */
  truncated: boolean;
}

/**
 * `GET /v1/units/{unit_id}/events` — the unit's presentable events.
 *
 * The unit is the one the server granted this account
 * (`PortalDescriptor.default_unit_id`), never a value the browser composed and
 * never a build variable. `admin` and `coordinator` only, authorized
 * server-side per request against the loaded unit: a caller the server refuses
 * gets {@link ApiRequestError} with status `403`, and a unit in another tenant
 * is a `404` rather than a `403` that would confirm the id names something
 * real.
 */
export async function fetchUnitEvents(unitId: string): Promise<UnitEventList> {
  return requestJson<UnitEventList>(
    `/v1/units/${encodeURIComponent(unitId)}/events`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * `GET /v1/units/{unit_id}/review-items` — the queue behind the
 * `pending_review_items` badge.
 *
 * The dashboard has counted pending review items since before this route
 * existed, and nothing listed them, so the screen showed a number it could not
 * explain. Both sides derive a row's owning unit through the same join, so the
 * length of this list and the value of that metric are the same number by
 * construction rather than by coincidence.
 *
 * Nothing but `unitId` selects whose rows come back. `status` chooses a column
 * value and cannot widen across units, and there is no caller identity on this
 * path at all. Authorization is `admin`/`coordinator` against the loaded unit,
 * decided per request: a caller the server refuses gets {@link ApiRequestError}
 * with status `403`, and a unit in another tenant is a `404` rather than a
 * `403` that would confirm the id names something real.
 */
export async function fetchReviewItems(
  unitId: string,
  status: ReviewItemStatus = "pending",
): Promise<ReviewItemListResponse> {
  return requestJson<ReviewItemListResponse>(
    `/v1/units/${encodeURIComponent(unitId)}/review-items?status=${encodeURIComponent(status)}`,
    { method: "GET" },
    { authenticated: true },
  );
}

/** What a coordinator may write to a pending item. Never `pending`: that is not a decision. */
export type ReviewDecision = "accepted" | "rejected";

/**
 * What changed, read back from the row rather than echoed from the request.
 *
 * No pending count, for the reason {@link ReviewItemListResponse} gives: the
 * metrics route owns that number. A caller wanting the new count re-reads it
 * there, which is also the only way the two can be guaranteed to agree.
 */
export interface ReviewDecisionResult {
  id: string;
  status: ReviewDecision;
  decided_at: string;
}

/**
 * `POST /v1/review-items/{review_item_id}/decision` — accept or reject one row.
 *
 * The item is named, and the unit the decision is authorized against is derived
 * server-side from that item's own import batch. No unit travels in this call,
 * deliberately: a caller who could name one could name a sibling department's,
 * and an authorizer that trusted the assertion over the row's own ancestry is
 * the archived MM-A01 defect.
 *
 * A second decision on the same row is a `409`, not a silent success — the
 * server's `UPDATE` is guarded by `status = 'pending'`, so a retried request
 * refuses cleanly rather than double-applying. Callers should surface that as
 * the state disagreement it is, typically by re-reading the queue.
 */
export async function decideReviewItem(
  reviewItemId: string,
  decision: ReviewDecision,
): Promise<ReviewDecisionResult> {
  return requestJson<ReviewDecisionResult>(
    `/v1/review-items/${encodeURIComponent(reviewItemId)}/decision`,
    { method: "POST", body: JSON.stringify({ decision }) },
    { authenticated: true },
  );
}

/**
 * One meeting a unit recorded with the CBA team (migration `0034`).
 *
 * **An internal record, not a booking.** Nothing in this system tells anybody
 * outside it that this meeting exists — no invitation is composed, queued or
 * sent, and no address is read. The row is the unit's own note. A surface that
 * implied otherwise would be promising something the server cannot do.
 *
 * `scheduled_at` is **never null and never inferred.** A meeting with no
 * resolved time cannot be stored: the column is `NOT NULL` with no default, the
 * repository refuses a time carrying no zone, and the route answers `422` rather
 * than choosing one. That is ADR-0010 rule 2 and migration finding F-003 — the
 * legacy turned an unparsed date into "30 days from now" and rendered a slot
 * nobody had chosen. The practical consequence for a caller is that this field
 * needs no absent branch: there is no such row to render.
 *
 * `time_zone` is the IANA zone the time was *agreed in*, and it is a separate
 * field because `scheduled_at` cannot recover it. Rendering the instant in the
 * reader's own zone without saying which zone it was agreed in is how a 5pm
 * meeting becomes an 8pm one on somebody's screen.
 *
 * There is deliberately **no participant field of any kind** — not a name, not
 * an account, not free text. What a "meeting with the CBA team" is contractually
 * (who may book, whether an external participant is a user account or free text,
 * whether a booking ever leaves the system) is **OQ-CBA-066**, open, and a field
 * here would be an answer to it shipped in a client.
 */
export interface Meeting {
  id: string;
  unit_id: string;
  /** What the meeting is. Never blank — the server refuses an empty title. */
  title: string;
  /** When it is, ISO-8601 with an offset. Never null, never inferred. */
  scheduled_at: string;
  /** The IANA zone the time was agreed in, e.g. `America/Los_Angeles`. */
  time_zone: string;
  /** A room, a building, or a join link. `null` when nobody has said yet. */
  location_or_link: string | null;
  /** `scheduled` or `cancelled`. Cancelled meetings are listed, not hidden. */
  status: string;
  /** When the note was made, ISO-8601. */
  recorded_at: string;
  /** When the note last moved, ISO-8601. */
  updated_at: string;
}

/**
 * A bounded page of a unit's meetings, plus a measured total.
 *
 * `total` is counted server-side across every meeting the unit holds, not folded
 * from `meetings`. Comparing the two is how a caller tells a full page from a
 * truncated one — which is a question a bounded listing would otherwise leave a
 * client to guess at, and guessing it is how a surface ends up claiming a number
 * nobody measured (ADR-0011 rule 1).
 */
export interface MeetingList {
  unit_id: string;
  meetings: Meeting[];
  total: number;
  /** The bound this listing was taken under. */
  limit: number;
}

/**
 * What a coordinator supplies to record a meeting.
 *
 * No `status` and no recorder: every meeting starts `scheduled`, and the author
 * is the verified principal behind the bearer token. Neither is a field the
 * client can set, which is what keeps caller-selected identity out of the write.
 */
export interface NewMeeting {
  title: string;
  /**
   * ISO-8601 **with an offset**. A value with no offset is a wall-clock reading
   * rather than an instant and is refused with `422 meeting_time_unresolved`;
   * `new Date(...).toISOString()` produces an acceptable value.
   */
  scheduled_at: string;
  /** The IANA zone the time was agreed in. Required. */
  time_zone: string;
  /** Optional. Omit or send `null` when nobody has said where yet. */
  location_or_link?: string | null;
}

/**
 * `GET /v1/units/{unit_id}/meetings` — the meetings this unit has recorded.
 *
 * Soonest first, bounded by the server, with cancelled meetings **included**: a
 * surface has to render "this was called off" differently from "this was never
 * arranged", and a route that dropped them would take that distinction away from
 * the only caller who needs it.
 *
 * Authorization runs before any meeting row is read, against the unit the list
 * is scoped to. `admin` and `coordinator` only, with no tenant-wide widening: a
 * caller the server refuses gets {@link ApiRequestError} with status `403`, and
 * a unit in another tenant is a `404` rather than a `403` that would confirm the
 * id names something real.
 */
export async function fetchMeetings(unitId: string, limit?: number): Promise<MeetingList> {
  const query = limit === undefined ? "" : `?limit=${encodeURIComponent(String(limit))}`;
  return requestJson<MeetingList>(
    `/v1/units/${encodeURIComponent(unitId)}/meetings${query}`,
    { method: "GET" },
    { authenticated: true },
  );
}

/**
 * `POST /v1/units/{unit_id}/meetings` — record one meeting.
 *
 * Returns the meeting as stored, read back out of the table rather than echoed:
 * the two provenance instants are server-written, so an echo would be this
 * client's guess at what was saved.
 *
 * **Sends nothing to anybody.** This writes a row. If a future caller needs an
 * invitation delivered, that is a different capability with a different consent
 * story, and it does not exist.
 *
 * A `422` with code `meeting_time_unresolved` means the time carried no offset.
 * **Do not retry it by supplying one** — picking a zone on the unit's behalf is
 * the fabrication the refusal exists to prevent. Ask the person for the zone.
 */
export async function createMeeting(unitId: string, input: NewMeeting): Promise<Meeting> {
  return requestJson<Meeting>(
    `/v1/units/${encodeURIComponent(unitId)}/meetings`,
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Manual events, external feedback QR codes, and speaker handoffs
// ---------------------------------------------------------------------------

export type ManualEventStatus = "draft" | "published" | "cancelled";
export type ManualEventTimePrecision = "exact" | "date_only" | "unresolved";

export interface ManualEvent {
  id: string;
  unit_id: string;
  title: string;
  description: string | null;
  category: string | null;
  time_precision: ManualEventTimePrecision;
  starts_at: string | null;
  ends_at: string | null;
  on_date: string | null;
  time_zone: string | null;
  location: string | null;
  capacity: number | null;
  volunteer_openings: number | null;
  volunteer_needs: string | null;
  audience: string | null;
  contact_name: string | null;
  contact_email: string | null;
  speaker_topics: string[];
  region: string | null;
  status: ManualEventStatus;
  provenance: "observed" | "synthetic";
  created_at: string;
  updated_at: string;
  version: number;
  attendance_closed_at: string | null;
  cancelled_at: string | null;
}

export interface ManualEventInput {
  title: string;
  description?: string | null;
  category?: string | null;
  time_precision: ManualEventTimePrecision;
  starts_at?: string | null;
  ends_at?: string | null;
  on_date?: string | null;
  time_zone?: string | null;
  location?: string | null;
  capacity?: number | null;
  volunteer_openings?: number | null;
  volunteer_needs?: string | null;
  audience?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  speaker_topics?: string[];
  region?: string | null;
}

export interface SpeakerProfile {
  id: string;
  name: string;
  title: string | null;
  company: string | null;
  board_role: string | null;
  expertise_topics: string[];
  home_region: string | null;
  service_regions: string[];
  contact_email?: string | null;
  contact_phone?: string | null;
  available?: boolean;
  active?: boolean;
  version?: number;
  created_at?: string;
  updated_at?: string;
}

export interface SpeakerProfileInput {
  name: string;
  title?: string | null;
  company?: string | null;
  board_role?: string | null;
  expertise_topics: string[];
  home_region?: string | null;
  service_regions: string[];
  contact_email?: string | null;
  contact_phone?: string | null;
  available: boolean;
  active: boolean;
}

export interface SpeakerPortalProfile extends SpeakerProfile {
  contact_email: string | null;
  contact_phone: string | null;
  available: boolean;
}

export interface SpeakerPortalEngagement {
  id: string;
  event_id: string;
  event_title: string;
  event_status: ManualEventStatus;
  status: SpeakerEventStatus;
  starts_at: string | null;
  on_date: string | null;
  time_zone: string | null;
  location: string | null;
}

export interface MatchSuggestion
  extends Omit<SpeakerProfile, "contact_email" | "contact_phone" | "available" | "active"> {
  speaker_id: string;
  explanations: string[];
}

export interface MatchRun {
  id: string;
  event_id: string;
  suggestions: MatchSuggestion[];
  created_at: string;
}

export type SpeakerEventStatus =
  | "not_emailed_yet"
  | "awaiting_response"
  | "declined"
  | "ready_for_handoff"
  | "handed_off"
  | "awaiting_final_confirmation"
  | "confirmed"
  | "withdrawn"
  | "attended"
  | "did_not_attend"
  | "event_cancelled";

export interface SpeakerEventHistory {
  id: string;
  from_status: SpeakerEventStatus | null;
  to_status: SpeakerEventStatus;
  action_kind: string;
  actor_id: string;
  note: string | null;
  correction_reason: string | null;
  created_at: string;
}

export interface SpeakerEventNote {
  id: string;
  actor_id: string;
  body: string;
  created_at: string;
}

export interface SpeakerEventRecord {
  id: string;
  event_id: string;
  speaker_id: string;
  assigned_host_id: string;
  status: SpeakerEventStatus;
  version: number;
  speaker_name: string;
  speaker_title: string | null;
  speaker_company: string | null;
  event_title: string;
  created_at: string;
  updated_at: string;
  history: SpeakerEventHistory[];
  notes: SpeakerEventNote[];
}

export interface FeedbackQrAsset {
  id: string;
  event_id: string;
  destination_url: string;
  redirect_url: string;
  open_count: number;
  last_opened_at: string | null;
  created_at: string;
  updated_at: string;
}

export async function fetchManualEvents(
  unitId: string,
  status: "published" | "draft" | "all" = "published",
): Promise<{ data: ManualEvent[]; total: number }> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events?status=${status}`,
    undefined,
    { authenticated: true },
  );
}

export async function createManualEvent(
  unitId: string,
  input: ManualEventInput,
  idempotencyKey = crypto.randomUUID(),
): Promise<ManualEvent> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
    { authenticated: true },
  );
}

export async function updateManualEvent(
  unitId: string,
  eventId: string,
  version: number,
  input: Partial<ManualEventInput>,
): Promise<ManualEvent> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events/${encodeURIComponent(eventId)}`,
    { method: "PATCH", body: JSON.stringify({ ...input, version }) },
    { authenticated: true },
  );
}

export async function publishManualEvent(unitId: string, eventId: string): Promise<ManualEvent> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events/${encodeURIComponent(eventId)}/publish`,
    { method: "POST" },
    { authenticated: true },
  );
}

export async function fetchFeedbackQr(
  unitId: string,
  eventId: string,
): Promise<FeedbackQrAsset | null> {
  try {
    return await requestJson(
      `/v1/units/${encodeURIComponent(unitId)}/events/${encodeURIComponent(eventId)}/feedback-qr`,
      undefined,
      { authenticated: true },
    );
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) return null;
    throw error;
  }
}

export async function saveFeedbackQr(
  unitId: string,
  eventId: string,
  destinationUrl: string,
): Promise<FeedbackQrAsset> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events/${encodeURIComponent(eventId)}/feedback-qr`,
    { method: "PUT", body: JSON.stringify({ destination_url: destinationUrl }) },
    { authenticated: true },
  );
}

export async function fetchSpeakers(
  unitId: string,
): Promise<{
  data: SpeakerProfile[];
  total: number;
  roster_version: number | null;
  published_at: string | null;
}> {
  return requestJson(`/v1/units/${encodeURIComponent(unitId)}/speakers`, undefined, {
    authenticated: true,
  });
}

export async function fetchMySpeakerProfile(unitId: string): Promise<SpeakerPortalProfile> {
  return requestJson(`/v1/units/${encodeURIComponent(unitId)}/speaker-portal/profile`, undefined, {
    authenticated: true,
  });
}

export async function fetchMySpeakerEngagements(
  unitId: string,
): Promise<SpeakerPortalEngagement[]> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-portal/engagements`,
    undefined,
    { authenticated: true },
  );
}

export async function createSpeaker(
  unitId: string,
  input: SpeakerProfileInput,
): Promise<SpeakerProfile> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speakers`,
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export async function updateSpeaker(
  unitId: string,
  speakerId: string,
  input: SpeakerProfileInput & { version: number },
): Promise<SpeakerProfile> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speakers/${encodeURIComponent(speakerId)}`,
    { method: "PATCH", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export async function publishSpeakerRoster(
  unitId: string,
): Promise<{ version: number; published_at: string }> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-roster/publish`,
    { method: "POST" },
    { authenticated: true },
  );
}

export async function runSpeakerMatch(
  unitId: string,
  eventId: string,
  idempotencyKey = crypto.randomUUID(),
): Promise<MatchRun> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events/${encodeURIComponent(eventId)}/match-runs`,
    { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    { authenticated: true },
  );
}

export async function submitSpeakerShortlist(
  unitId: string,
  matchRunId: string,
  speakerIds: string[],
  idempotencyKey = crypto.randomUUID(),
): Promise<SpeakerEventRecord[]> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/match-runs/${encodeURIComponent(matchRunId)}/shortlist`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ speaker_ids: speakerIds }),
    },
    { authenticated: true },
  );
}

export async function fetchSpeakerEvents(
  unitId: string,
  eventId?: string,
): Promise<SpeakerEventRecord[]> {
  const query = eventId ? `?event_id=${encodeURIComponent(eventId)}` : "";
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-events${query}`,
    undefined,
    { authenticated: true },
  );
}

export async function fetchSpeakerEvent(
  unitId: string,
  recordId: string,
): Promise<SpeakerEventRecord> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-events/${encodeURIComponent(recordId)}`,
    undefined,
    { authenticated: true },
  );
}

export async function transitionSpeakerEvent(
  unitId: string,
  recordId: string,
  toStatus: SpeakerEventStatus,
  expectedVersion: number,
  note?: string,
): Promise<SpeakerEventRecord> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-events/${encodeURIComponent(recordId)}/transitions`,
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({
        to_status: toStatus,
        expected_version: expectedVersion,
        note,
      }),
    },
    { authenticated: true },
  );
}

export async function addSpeakerEventNote(
  unitId: string,
  recordId: string,
  body: string,
): Promise<SpeakerEventNote> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-events/${encodeURIComponent(recordId)}/notes`,
    { method: "POST", body: JSON.stringify({ body }) },
    { authenticated: true },
  );
}

export async function correctSpeakerEvent(
  unitId: string,
  recordId: string,
  toStatus: SpeakerEventStatus,
  expectedVersion: number,
  reason: string,
): Promise<SpeakerEventRecord> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/speaker-events/${encodeURIComponent(recordId)}/corrections`,
    {
      method: "POST",
      body: JSON.stringify({ to_status: toStatus, expected_version: expectedVersion, reason }),
    },
    { authenticated: true },
  );
}

export async function closeEventAttendance(
  unitId: string,
  eventId: string,
  expectedVersion: number,
): Promise<SpeakerEventRecord[]> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events/${encodeURIComponent(eventId)}/close-attendance`,
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    { authenticated: true },
  );
}

export async function cancelManualEvent(
  unitId: string,
  eventId: string,
  expectedVersion: number,
  reason: string,
): Promise<SpeakerEventRecord[]> {
  return requestJson(
    `/v1/units/${encodeURIComponent(unitId)}/events/${encodeURIComponent(eventId)}/cancel`,
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ expected_version: expectedVersion, reason }),
    },
    { authenticated: true },
  );
}
