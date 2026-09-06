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

export interface OutreachEmailPayload {
  subject_line: string;
  greeting: string;
  body: string;
  closing: string;
  full_email: string;
}

export type OutreachEmailVoice = "school_coordinator" | "ia_west_chapter";

export interface OutreachEmailResponse {
  email: string;
  email_data: OutreachEmailPayload;
  /** Present when the API resolved sender perspective (school vs IA West chapter). */
  voice?: OutreachEmailVoice;
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
 * Two sources, in order: the build-time `VITE_SMARTMATCH_BEARER_TOKEN` (the
 * fixture token a compose/dev build is started with) and
 * `sessionStorage["smartmatch_bearer_token"]`. Both are *credentials* — the
 * server decides what they mean. Nothing here, and nothing downstream of
 * here, lets the browser assert a tenant, user, or role; that is the whole
 * point of Fix #7. See `src/lib/session.ts` for the identity the server
 * returns for a token.
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

  return (
    (typeof envToken === "string" && envToken.trim().length > 0 ? envToken.trim() : null) ??
    (typeof sessionToken === "string" && sessionToken.trim().length > 0
      ? sessionToken.trim()
      : null)
  );
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
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.authenticated ? smartmatchAuthHeaders() : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
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

export async function generateEmail(
  speakerName: string,
  eventName: string,
  options?: { voice?: OutreachEmailVoice; request_source?: string },
): Promise<OutreachEmailResponse> {
  return requestJson<OutreachEmailResponse>("/api/outreach/email", {
    method: "POST",
    body: JSON.stringify({
      speaker_name: speakerName,
      event_name: eventName,
      ...(options?.voice ? { voice: options.voice } : {}),
      ...(options?.request_source ? { request_source: options.request_source } : {}),
    }),
  });
}

export async function generateIcs(
  eventName: string,
  eventDate?: string,
  location?: string,
  description?: string,
): Promise<{ ics_content: string }> {
  return requestJson<{ ics_content: string }>("/api/outreach/ics", {
    method: "POST",
    body: JSON.stringify({
      event_name: eventName,
      event_date: eventDate,
      location,
      description,
    }),
  });
}

export interface WorkflowStepResult {
  status: "ok" | "error";
  error?: string;
}

export interface WorkflowResponse {
  email: string;
  email_data: OutreachEmailPayload;
  ics_content: string;
  pipeline_updated: boolean;
  steps: {
    email: WorkflowStepResult;
    ics: WorkflowStepResult;
    pipeline: WorkflowStepResult;
  };
  dispatch_mode: string;
}

export async function initiateWorkflow(
  speakerName: string,
  eventName: string,
): Promise<WorkflowResponse> {
  return requestJson<WorkflowResponse>("/api/outreach/workflow", {
    method: "POST",
    body: JSON.stringify({
      speaker_name: speakerName,
      event_name: eventName,
    }),
  });
}

export interface AgenticOutreachWorkflowInput {
  speaker_name: string;
  event_name: string;
  coordinator_id?: string;
  event_date?: string;
  request_source: string;
  voice: OutreachEmailVoice;
}

/**
 * Opens the agentic outreach workflow's server-sent-events stream. Routes
 * through the same fetch + error-envelope policy as `requestJson` (rather
 * than a bare `fetch`) so a refusal (auth, validation, etc.) surfaces the
 * backend's real `code`/`message` instead of failing silently; the caller
 * still owns reading and parsing the `data: ` lines out of the stream.
 */
export async function openAgenticOutreachWorkflowStream(
  input: AgenticOutreachWorkflowInput,
  signal: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const response = await fetch("/api/outreach/agentic-workflow/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });

  if (!response.ok) {
    await throwApiRequestError(response);
  }

  if (!response.body) {
    throw new ApiRequestError(
      "The server did not return a streaming response body.",
      response.status,
      "empty_stream_body",
    );
  }

  return response.body.getReader();
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
export type MatchScoreState = "measured" | "unknown";

/** One factor's contribution to one candidate's score, or its absence. */
export interface MatchFactorExplanation {
  factor_key: string;
  display_label: string;
  /** `suitability` or `penalty` — the two read in opposite directions. */
  kind: string;
  /** The normalized Stage B weight actually applied for this run. */
  weight: number;
  state: MatchScoreState;
  /** null when `state` is "unknown": absent evidence, never a measured zero. */
  value: number | null;
  /** `measured_zero`, `unknown`, or null when the value is neither. */
  zero_classification: string | null;
  /** Where the number came from — or why there is none. */
  basis: string;
  /** Set when the value is an explicitly coarse estimate. */
  estimate_label: string | null;
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
// Four calls, and one shape runs through all of them: **nothing here reports
// that a message was sent.** `submitOutreachSend` resolves with a job id, and
// the only thing that can say what happened to a message is a later read of
// `GET /v1/units/{unit_id}/outreach/sends/{send_id}`.
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
export async function createOutreachDraft(
  unitId: string,
  input: {
    contactChannelId: string;
    templateId: string;
    values: Record<string, string>;
    approve: boolean;
  },
): Promise<OutreachDraft> {
  return requestJson<OutreachDraft>(
    `/v1/units/${encodeURIComponent(unitId)}/outreach/drafts`,
    {
      method: "POST",
      body: JSON.stringify({
        contact_channel_id: input.contactChannelId,
        template_id: input.templateId,
        values: input.values,
        approve: input.approve,
      }),
    },
    { authenticated: true },
  );
}

/**
 * `POST /v1/units/{unit_id}/outreach/drafts/{draft_id}/send` — submit the command.
 *
 * Resolves with a job id when the server answers `202`. **Nothing has been sent
 * at that point.** The `Idempotency-Key` is generated per attempt so that a
 * retry after a network error cannot become a second message; `crypto.randomUUID`
 * is used rather than a timestamp because two clicks in the same millisecond are
 * two attempts, and a key that collided would silently merge them.
 */
export async function submitOutreachSend(
  unitId: string,
  draftId: string,
): Promise<OutreachSendAccepted> {
  return requestJson<OutreachSendAccepted>(
    `/v1/units/${encodeURIComponent(unitId)}/outreach/drafts/${encodeURIComponent(draftId)}/send`,
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
    },
    { authenticated: true },
  );
}

/** `GET /v1/units/{unit_id}/outreach/sends/{send_id}` — what actually happened. */
export async function fetchOutreachSend(unitId: string, sendId: string): Promise<OutreachSend> {
  return requestJson<OutreachSend>(
    `/v1/units/${encodeURIComponent(unitId)}/outreach/sends/${encodeURIComponent(sendId)}`,
    undefined,
    { authenticated: true },
  );
}

// ---------------------------------------------------------------------------
// Speaker Requests (CBA-EVENT-REQUEST, customer §12)
//
// One call, and the shape that matters runs through it: **the response is the
// stored request, not an echo of what was sent.** `submitSpeakerRequest`
// resolves with the row the server read back after committing — publication
// status, review status, timestamps and the resolved taxonomy names included —
// so a caller has something real to render and nothing optimistic to invent.
//
// There is deliberately no `Idempotency-Key` here, unlike `submitOutreachSend`
// above. A Speaker Request has a deterministic identity server-side (ADR-0012:
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
