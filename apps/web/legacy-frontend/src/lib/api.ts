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

export interface PipelineRecord {
  event_name: string;
  speaker_name: string;
  match_score: string;
  rank: string;
  stage: string;
  stage_order: string;
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
  coverage_ratio: number;
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
  volunteer_fatigue: number;
  recovery_status: RecoveryStatus;
  recovery_label: string;
  recent_assignment_count: number;
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
  scan_count: number;
  conversion_count: number;
  conversion_rate: number;
  last_scanned_at: string;
  qr_svg: string;
  qr_svg_data_url: string;
  qr_png_data_url: string;
  qr_image_url: string;
  download_url: string;
}

export interface QrStatsSummary {
  total_generated: number;
  total_scans: number;
  total_conversions: number;
  conversion_rate: number;
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
  total_feedback: number;
  accepted: number;
  declined: number;
  acceptance_rate: number;
  attended_count: number;
  membership_interest_count: number;
  membership_interest_rate: number;
  average_coordinator_rating: number | null;
  average_match_score_accepted: number;
  average_match_score_declined: number;
  pain_score: number;
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

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Ignore non-JSON error bodies.
    }
    const error = new Error(detail) as Error & { status?: number };
    error.status = response.status;
    throw error;
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
  const coverageRatioValue = parseNumber(record.coverage_ratio ?? record.coverage_percentage ?? record.coveragePercent, Number.NaN);
  const coverageRatio =
    Number.isFinite(coverageRatioValue)
      ? clamp(coverageRatioValue > 1 ? coverageRatioValue / 100 : coverageRatioValue, 0, 1)
      : coverageStatus === "covered"
        ? 1
        : coverageStatus === "partial"
          ? 0.5
          : 0;
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
  const volunteerFatigue = normalizeFatigue(
    record.volunteer_fatigue ?? record.fatigue_score ?? record.fatigue ?? record.recovery_score,
  );
  const recoveryStatus = normalizeRecoveryStatus(record.recovery_status ?? record.recoveryState, volunteerFatigue);
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
    recent_assignment_count: parseNumber(record.recent_assignment_count ?? record.recentAssignments ?? record.assignment_count ?? 0, 0),
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
  const volunteerFatigue = volunteerAssignments.length
    ? volunteerAssignments.reduce((sum, assignment) => sum + assignment.volunteer_fatigue, 0) / volunteerAssignments.length
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
  const conversionCount = Math.max(
    parseNumber(
      record.conversion_count ??
        record.conversions ??
        record.member_inquiry_count ??
        record.membership_interest_count,
      0,
    ),
    0,
  );
  const scanCount = Math.max(parseNumber(record.scan_count ?? record.scans ?? record.total_scans, 0), 0);
  const conversionRateValue = parseNumber(
    record.conversion_rate ?? record.conversionRate ?? record.roi_rate,
    Number.NaN,
  );
  const derivedConversionRate = scanCount > 0 ? conversionCount / scanCount : 0;
  const normalizedConversionRate = Number.isFinite(conversionRateValue)
    ? clamp(conversionRateValue > 1 ? conversionRateValue / 100 : conversionRateValue, 0, 1)
    : clamp(derivedConversionRate, 0, 1);

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
  const totalGenerated = parseNumber(
    source.total_generated ??
      source.generated_count ??
      source.codes_generated ??
      source.referral_count ??
      source.total_codes,
    entries.length,
  );
  const totalScans = parseNumber(
    source.total_scans ?? source.scan_count ?? source.scans ?? source.total_visits,
    entries.reduce((sum, entry) => sum + entry.scan_count, 0),
  );
  const totalConversions = parseNumber(
    source.total_conversions ??
      source.conversion_count ??
      source.conversions ??
      source.total_inquiries ??
      source.membership_interest_count,
    entries.reduce((sum, entry) => sum + entry.conversion_count, 0),
  );
  const conversionRateValue = parseNumber(
    source.conversion_rate ?? source.conversionRate ?? source.roi_rate,
    Number.NaN,
  );
  const derivedConversionRate = totalScans > 0 ? totalConversions / totalScans : 0;

  return {
    total_generated: totalGenerated,
    total_scans: totalScans,
    total_conversions: totalConversions,
    conversion_rate: Number.isFinite(conversionRateValue)
      ? clamp(conversionRateValue > 1 ? conversionRateValue / 100 : conversionRateValue, 0, 1)
      : clamp(derivedConversionRate, 0, 1),
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

  return {
    total_feedback: parseNumber(record.total_feedback ?? record.total ?? 0, 0),
    accepted: parseNumber(record.accepted ?? 0, 0),
    declined: parseNumber(record.declined ?? 0, 0),
    acceptance_rate: clamp(parseNumber(record.acceptance_rate ?? 0, 0), 0, 1),
    attended_count: parseNumber(record.attended_count ?? 0, 0),
    membership_interest_count: parseNumber(
      record.membership_interest_count ?? record.total_conversions ?? 0,
      0,
    ),
    membership_interest_rate: clamp(
      parseNumber(record.membership_interest_rate ?? record.conversion_rate ?? 0, 0),
      0,
      1,
    ),
    average_coordinator_rating:
      record.average_coordinator_rating == null
        ? null
        : parseNumber(record.average_coordinator_rating, 0),
    average_match_score_accepted: parseNumber(record.average_match_score_accepted ?? 0, 0),
    average_match_score_declined: parseNumber(record.average_match_score_declined ?? 0, 0),
    pain_score: parseNumber(record.pain_score ?? 0, 0),
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
  return { data: payload as unknown as PipelineRecord[], source, isMockData: source !== "live" };
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

export function emptyQrStatsSummary(): QrStatsSummary {
  return {
    total_generated: 0,
    total_scans: 0,
    total_conversions: 0,
    conversion_rate: 0,
    entries: [],
  };
}

export function emptyFeedbackStatsSummary(): FeedbackStatsSummary {
  return {
    total_feedback: 0,
    accepted: 0,
    declined: 0,
    acceptance_rate: 0,
    attended_count: 0,
    membership_interest_count: 0,
    membership_interest_rate: 0,
    average_coordinator_rating: null,
    average_match_score_accepted: 0,
    average_match_score_declined: 0,
    pain_score: 0,
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

export interface MockLoginResponse {
  role: string;
  user: Record<string, unknown>;
  redirect_path: string;
  available_roles: Array<{ role: string; email: string; name: string; id: string }>;
}

const API_BASE = "/api";

export async function mockLogin(email: string, role?: string): Promise<MockLoginResponse> {
  const res = await fetch(`${API_BASE}/portals/auth/mock-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) {
    let detail = res.statusText || String(res.status);
    try {
      const errBody = (await res.json()) as { detail?: unknown };
      if (typeof errBody.detail === "string") {
        detail = errBody.detail;
      } else if (Array.isArray(errBody.detail)) {
        detail = JSON.stringify(errBody.detail);
      }
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(`Login failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchStudentProfile(studentId: string): Promise<StudentProfile & { source: string }> {
  const res = await fetch(`${API_BASE}/portals/students/${studentId}`);
  if (!res.ok) throw new Error(`Student not found: ${studentId}`);
  return res.json();
}

export async function fetchStudentRegistrations(studentId: string): Promise<{ data: StudentRegistration[]; total: number; source: string }> {
  const res = await fetch(`${API_BASE}/portals/students/${studentId}/registrations`);
  if (!res.ok) throw new Error(`Registrations not found`);
  return res.json();
}

export async function fetchStudentConnectionSuggestions(
  studentId: string,
): Promise<StudentConnectionSuggestionsResponse> {
  const params = new URLSearchParams({ student_id: studentId });
  const endpoints = [
    `${API_BASE}/portals/student-connections?${params.toString()}`,
    `${API_BASE}/portals/students/${encodeURIComponent(studentId)}/connection-suggestions`,
  ];

  for (const endpoint of endpoints) {
    const res = await fetch(endpoint);
    if (res.ok) {
      return res.json();
    }

    // During local development it is common to have a stale backend process;
    // if one route is missing, try the compatibility endpoint before failing.
    if (res.status === 404) {
      continue;
    }

    throw new Error(`Connection suggestions failed: ${res.status}`);
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
  const res = await fetch(`${API_BASE}/portals/students/${studentId}/recommendations`);
  if (!res.ok) throw new Error(`Recommendations failed`);
  return res.json();
}

export async function fetchStudentNudge(
  studentId: string,
): Promise<(RetentionNudge & { source: string }) | null> {
  const res = await fetch(`${API_BASE}/portals/students/${studentId}/nudge`);
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(`Nudge failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchCoordinatorProfile(coordinatorId: string): Promise<EventCoordinator & { source: string }> {
  const res = await fetch(`${API_BASE}/portals/event-coordinators/${coordinatorId}`);
  if (!res.ok) throw new Error(`Coordinator not found`);
  return res.json();
}

export async function fetchCoordinatorThreads(coordinatorId: string): Promise<{ data: OutreachThread[]; total: number; source: string }> {
  const res = await fetch(`${API_BASE}/portals/event-coordinators/${coordinatorId}/threads`);
  if (!res.ok) throw new Error(`Threads failed`);
  return res.json();
}

export async function fetchCoordinatorMeetings(coordinatorId: string): Promise<{ data: MeetingBooking[]; total: number; source: string }> {
  const res = await fetch(`${API_BASE}/portals/event-coordinators/${coordinatorId}/meetings`);
  if (!res.ok) throw new Error(`Meetings failed`);
  return res.json();
}

export async function fetchCoordinatorEvents(coordinatorId: string): Promise<{ data: (CalendarEventSummary & { staffing_open: boolean })[]; total: number; source: string }> {
  const res = await fetch(`${API_BASE}/portals/event-coordinators/${coordinatorId}/events`);
  if (!res.ok) {
    throw new Error(`Coordinator events failed: ${res.status}`);
  }
  const payload = (await res.json()) as {
    data?: (CalendarEventSummary & { staffing_open?: boolean })[];
    events?: (CalendarEventSummary & { staffing_open?: boolean })[];
    total?: number;
    source?: string;
  };
  const data = payload.data ?? payload.events ?? [];
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

export interface VolunteerAssignment {
  assignment_id: string;
  event_id: string;
  event_name: string;
  event_date: string;
  region: string;
  stage: AssignmentStage;
  match_score: number;
  volunteer_fatigue: number;
  recovery_status: string;
  recovery_label: string;
  coverage_status: string;
}

export async function fetchVolunteerProfile(
  volunteerId: string,
): Promise<VolunteerProfile & { source: string }> {
  const res = await fetch(`${API_BASE}/portals/volunteers/${encodeURIComponent(volunteerId)}`);
  if (!res.ok) throw new Error(`Volunteer not found: ${volunteerId}`);
  return res.json();
}

export async function fetchVolunteerAssignments(
  volunteerId: string,
): Promise<{ data: VolunteerAssignment[]; total: number; source: string }> {
  const res = await fetch(
    `${API_BASE}/portals/volunteers/${encodeURIComponent(volunteerId)}/assignments`,
  );
  if (!res.ok) throw new Error(`Assignments not found for volunteer: ${volunteerId}`);
  return res.json();
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
