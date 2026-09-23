/**
 * The availability form's draft model, its client-side checks and its error
 * messages (B26 T5). Pure: no React, no fetch.
 *
 * ## The server decides; this module is a courtesy
 *
 * `validateDraft` mirrors T1's `validate_availability_statement`
 * (`python/smartmatch_domain/smartmatch_domain/speaker_availability.py`): the
 * same limits, the same first-failure order (capacity, pause, window count,
 * then each window), and the same codes, so one message table serves a client
 * failure and a server `422` alike. A draft that passes here is still sent and
 * any refusal is shown; nothing here blocks a value the server might accept.
 *
 * ## "Not stated" is never a number and never "available"
 *
 * A blank capacity is `""` in the draft and `null` on the wire — never `"0"`.
 * `stated: false` gives an empty draft with `baseVersion: null`, and saving it
 * records "no dates blocked", which the form labels as exactly that.
 *
 * ## Dates are calendar dates in UTC
 *
 * "Today" is the UTC date (T3-C1), and every date here is a `YYYY-MM-DD`
 * string compared as text and formatted with `timeZone: "UTC"`, so a calendar
 * date never shifts by a day in a browser west of Greenwich.
 */
import {
  ApiRequestError,
  type SpeakerAvailability,
  type SpeakerAvailabilityUpdatePayload,
  type SpeakerAvailabilityWindow,
} from "./api";

// Re-declared from T1 (`speaker_availability.py` as built). The server's
// copies are the ones enforced; these only let the form explain a refusal
// before sending it.
export const MAX_WINDOWS = 20;
export const WINDOW_MAX_SPAN_DAYS = 366;
export const WINDOW_HORIZON_MONTHS = 18;
export const PAUSE_HORIZON_MONTHS = 12;
export const CAPACITY_MAX = 720;

const CAPACITY_PATTERN = /^\d{1,3}(\.\d)?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;

export interface WindowDraft {
  /** Per-form counter (`w1`, `w2`, …), not a date: equal dates stay distinct rows. */
  key: string;
  starts_on: string;
  ends_on: string;
  startsBad: boolean;
  endsBad: boolean;
}

export interface AvailabilityDraft {
  /** The version the draft was read at; `null` means the read said `stated: false`. */
  baseVersion: number | null;
  /** `""` = no pause; otherwise `YYYY-MM-DD`. */
  pause: string;
  pauseBad: boolean;
  /** `""` = not stated — never `"0"`. */
  capacity: string;
  capacityBad: boolean;
  /** Form order == request order == the server's `details.index`. */
  windows: WindowDraft[];
}

export type AvailabilityValidationCode =
  | "input_unreadable"
  | "speaker_availability_capacity_invalid"
  | "speaker_availability_pause_invalid"
  | "speaker_availability_too_many_windows"
  | "speaker_availability_window_invalid";

export type WindowFailureReason =
  | "missing"
  | "reversed"
  | "too_long"
  | "past_horizon"
  | "duplicate";

export interface DraftFailure {
  code: AvailabilityValidationCode;
  field: "capacity" | "pause" | "count" | "window";
  index?: number;
  /** Which input of a window was unreadable. */
  part?: "from" | "to";
  reason?: WindowFailureReason;
  /** For a duplicate: the earlier window it repeats. */
  duplicateOf?: number;
}

/** Where an error is shown and which input takes focus. */
export type ErrorField = "form" | "capacity" | "pause" | "add" | "window";

export interface AvailabilityError {
  field: ErrorField;
  index?: number;
  part?: "from" | "to";
  message: string;
}

// ---------------------------------------------------------------------------
// Dates

/** Today's calendar date in UTC (T3-C1). */
export function utcToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function parts(iso: string): [number, number, number] {
  const [y, m, d] = iso.split("-").map(Number);
  return [y, m, d];
}

function pad(n: number, width = 2): string {
  return String(n).padStart(width, "0");
}

/** `iso` plus `months` calendar months, the day clamped to month end (T1 `_add_months`). */
export function addMonths(iso: string, months: number): string {
  const [year, month, day] = parts(iso);
  const monthIndex = month - 1 + months;
  const targetYear = year + Math.floor(monthIndex / 12);
  const targetMonth = (((monthIndex % 12) + 12) % 12) + 1;
  const lastDay = new Date(Date.UTC(targetYear, targetMonth, 0)).getUTCDate();
  return `${pad(targetYear, 4)}-${pad(targetMonth)}-${pad(Math.min(day, lastDay))}`;
}

function utcMs(iso: string): number {
  const [y, m, d] = parts(iso);
  return Date.UTC(y, m - 1, d);
}

/** Whole days from `startsOn` to `endsOn` (T1's `(ends_on - starts_on).days`). */
export function spanDays(startsOn: string, endsOn: string): number {
  return Math.round((utcMs(endsOn) - utcMs(startsOn)) / DAY_MS);
}

/** "November 2, 2026" — a calendar date, never shifted by the viewer's zone. */
export function formatCalendarDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    dateStyle: "long",
    timeZone: "UTC",
  });
}

/** A server timestamp in the viewer's locale, like the rest of the portal. */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function isDate(value: string): boolean {
  return ISO_DATE.test(value);
}

/**
 * One input's reading. A date or number input holding half-typed text reports
 * `value === ""` with `validity.badInput`; without the flag a typo would save
 * as "not stated" or "no pause".
 */
export function readInput(value: string, badInput: boolean): { value: string; bad: boolean } {
  return badInput ? { value: "", bad: true } : { value, bad: false };
}

// ---------------------------------------------------------------------------
// Draft <-> statement

export function windowDraft(key: string, starts_on = "", ends_on = ""): WindowDraft {
  return { key, starts_on, ends_on, startsBad: false, endsBad: false };
}

/** The draft a stored statement seeds. Window keys start at `w{firstKey}`. */
export function draftFromAvailability(
  availability: SpeakerAvailability,
  firstKey = 1,
): AvailabilityDraft {
  if (!availability.stated) {
    return {
      baseVersion: null,
      pause: "",
      pauseBad: false,
      capacity: "",
      capacityBad: false,
      windows: [],
    };
  }
  const capacity = availability.declared_capacity_hours_per_90_days;
  return {
    baseVersion: availability.version,
    pause: availability.invitations_paused_until ?? "",
    pauseBad: false,
    capacity: capacity === null ? "" : String(capacity),
    capacityBad: false,
    windows: availability.unavailable.map((w, i) =>
      windowDraft(`w${firstKey + i}`, w.starts_on, w.ends_on),
    ),
  };
}

/** The full-replace body. Windows keep form order so `details.index` names the same row. */
export function payloadFromDraft(
  draft: AvailabilityDraft,
  expectedVersion: number | null = draft.baseVersion,
): SpeakerAvailabilityUpdatePayload {
  return {
    expected_version: expectedVersion,
    invitations_paused_until: draft.pause === "" ? null : draft.pause,
    declared_capacity_hours_per_90_days: draft.capacity === "" ? null : Number(draft.capacity),
    unavailable: draft.windows.map((w) => ({ starts_on: w.starts_on, ends_on: w.ends_on })),
  };
}

/** Whether saving the draft would store exactly what is stored now. */
export function isDraftUnchanged(draft: AvailabilityDraft, stored: SpeakerAvailability): boolean {
  if (draft.pauseBad || draft.capacityBad) return false;
  if (draft.pause !== (stored.invitations_paused_until ?? "")) return false;
  const storedCapacity = stored.declared_capacity_hours_per_90_days;
  if (storedCapacity === null ? draft.capacity !== "" : Number(draft.capacity) !== storedCapacity) {
    return false;
  }
  if (draft.windows.length !== stored.unavailable.length) return false;
  return draft.windows.every((w, i) => {
    const s = stored.unavailable[i];
    return !w.startsBad && !w.endsBad && w.starts_on === s.starts_on && w.ends_on === s.ends_on;
  });
}

/** Whether nothing at all has been entered. */
export function isDraftEmpty(draft: AvailabilityDraft): boolean {
  return (
    draft.pause === "" &&
    !draft.pauseBad &&
    draft.capacity === "" &&
    !draft.capacityBad &&
    draft.windows.length === 0
  );
}

// ---------------------------------------------------------------------------
// Validation

function unreadable(draft: AvailabilityDraft): DraftFailure | null {
  if (draft.capacityBad) return { code: "input_unreadable", field: "capacity" };
  if (draft.pauseBad) return { code: "input_unreadable", field: "pause" };
  for (const [index, w] of draft.windows.entries()) {
    if (w.startsBad) return { code: "input_unreadable", field: "window", index, part: "from" };
    if (w.endsBad) return { code: "input_unreadable", field: "window", index, part: "to" };
  }
  return null;
}

function capacityOk(value: string): boolean {
  if (value === "") return true;
  if (!CAPACITY_PATTERN.test(value)) return false;
  const hours = Number(value);
  return hours > 0 && hours <= CAPACITY_MAX;
}

function windowFailure(
  windows: readonly WindowDraft[],
  index: number,
  horizon: string,
): DraftFailure | null {
  const w = windows[index];
  const failure = (reason: WindowFailureReason, duplicateOf?: number): DraftFailure => ({
    code: "speaker_availability_window_invalid",
    field: "window",
    index,
    reason,
    ...(duplicateOf === undefined ? {} : { duplicateOf }),
  });
  if (!isDate(w.starts_on) || !isDate(w.ends_on)) return failure("missing");
  if (w.ends_on < w.starts_on) return failure("reversed");
  if (spanDays(w.starts_on, w.ends_on) > WINDOW_MAX_SPAN_DAYS) return failure("too_long");
  if (w.ends_on > horizon) return failure("past_horizon");
  const earlier = windows
    .slice(0, index)
    .findIndex((o) => o.starts_on === w.starts_on && o.ends_on === w.ends_on);
  if (earlier !== -1) return failure("duplicate", earlier);
  return null;
}

/**
 * The first failure, in T1's order, or `null`.
 *
 * `stored` is the **latest** statement read (the fresh one after a 409): an
 * unchanged, stored, already-expired pause is exempt, because the server drops
 * it to `null` on save rather than refusing it (T3 §3 step 6).
 */
export function validateDraft(
  draft: AvailabilityDraft,
  today: string,
  stored: SpeakerAvailability | null,
): DraftFailure | null {
  const bad = unreadable(draft);
  if (bad !== null) return bad;

  if (!capacityOk(draft.capacity)) {
    return { code: "speaker_availability_capacity_invalid", field: "capacity" };
  }

  if (draft.pause !== "") {
    const storedPause = stored?.invitations_paused_until ?? null;
    const expiredAndUnchanged = storedPause === draft.pause && storedPause < today;
    const inRange =
      isDate(draft.pause) &&
      draft.pause >= today &&
      draft.pause <= addMonths(today, PAUSE_HORIZON_MONTHS);
    if (!expiredAndUnchanged && !inRange) {
      return { code: "speaker_availability_pause_invalid", field: "pause" };
    }
  }

  if (draft.windows.length > MAX_WINDOWS) {
    return { code: "speaker_availability_too_many_windows", field: "count" };
  }

  const horizon = addMonths(today, WINDOW_HORIZON_MONTHS);
  for (let index = 0; index < draft.windows.length; index += 1) {
    const failure = windowFailure(draft.windows, index, horizon);
    if (failure !== null) return failure;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Messages

const CAPACITY_MESSAGE =
  "Capacity must be more than 0 and at most 720 hours per 90 days, with at most one decimal place. Leave it blank if not stated.";
const NOT_FOUND_MESSAGE =
  "This contact is no longer in your unit's roster, so its availability cannot be read or saved.";
const STALE_MESSAGE =
  "Someone changed this availability since you opened it. Your changes are still in the form and were not saved.";
const FALLBACK_MESSAGE =
  "Availability could not be saved and the server gave no reason. Nothing was changed; your changes are still in the form.";

function pauseMessage(today: string): string {
  return (
    `The pause must end today (${formatCalendarDate(today)}) or later, and no later than ` +
    `${formatCalendarDate(addMonths(today, PAUSE_HORIZON_MONTHS))}. Dates count in UTC.`
  );
}

function tooManyMessage(limit: number): string {
  return `A Speaker can have at most ${limit} blocked date ranges. Remove one, then save again.`;
}

function windowLabel(windows: readonly SpeakerAvailabilityWindow[], index: number): string {
  const w = windows[index];
  const n = index + 1;
  if (w !== undefined && isDate(w.starts_on) && isDate(w.ends_on)) {
    return `Window ${n} (${formatCalendarDate(w.starts_on)} to ${formatCalendarDate(w.ends_on)})`;
  }
  return `Window ${n}`;
}

function serverWindowMessage(
  windows: readonly SpeakerAvailabilityWindow[],
  index: number,
  today: string,
): string {
  const horizon = formatCalendarDate(addMonths(today, WINDOW_HORIZON_MONTHS));
  return (
    `${windowLabel(windows, index)} cannot be saved. The end must be on or after the start, ` +
    `the range can cover at most 367 days, it must end by ${horizon}, and it cannot repeat ` +
    "another window."
  );
}

/** The client-side failure as the message shown beside its field. */
export function failureMessage(failure: DraftFailure, today: string): AvailabilityError {
  const n = (failure.index ?? 0) + 1;
  switch (failure.code) {
    case "input_unreadable":
      return {
        field: failure.field === "count" ? "form" : failure.field,
        index: failure.index,
        part: failure.part,
        message:
          failure.field === "capacity"
            ? "Enter a number of hours, like 24 or 24.5."
            : "Enter a full date.",
      };
    case "speaker_availability_capacity_invalid":
      return { field: "capacity", message: CAPACITY_MESSAGE };
    case "speaker_availability_pause_invalid":
      return { field: "pause", message: pauseMessage(today) };
    case "speaker_availability_too_many_windows":
      return { field: "add", message: tooManyMessage(MAX_WINDOWS) };
    case "speaker_availability_window_invalid": {
      const horizon = formatCalendarDate(addMonths(today, WINDOW_HORIZON_MONTHS));
      const reasons: Record<WindowFailureReason, string> = {
        missing: "it needs both dates.",
        reversed: "the end date is before the start date.",
        too_long: "the range covers more than 367 days.",
        past_horizon: `the range ends after ${horizon}.`,
        duplicate: `it repeats window ${(failure.duplicateOf ?? 0) + 1}.`,
      };
      return {
        field: "window",
        index: failure.index,
        part: "from",
        message: `Window ${n}: ${reasons[failure.reason ?? "missing"]}`,
      };
    }
  }
}

function numberDetail(details: Record<string, unknown> | undefined, key: string): number | null {
  const value = details?.[key];
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

/** The 403 sentence, in the `refusalMessage` shape of the other Connector pages. */
export function refusalMessage(serverMessage: string, doing: "Reading" | "Saving"): string {
  return (
    `The server refused this request (403). ${serverMessage} ${doing} a Speaker's availability ` +
    "is granted to Speaker Connectors in this unit; this account was not granted it here." +
    (doing === "Saving" ? " Nothing was changed." : "")
  );
}

/**
 * A failed save as the message to show and where (plan §6). Branches on the
 * error's `code` and `status`, never on its text. Window numbers are 1-based
 * and only the user's own dates are echoed.
 */
export function availabilityErrorMessage(
  cause: unknown,
  windows: readonly SpeakerAvailabilityWindow[],
  today: string,
): AvailabilityError {
  if (!(cause instanceof ApiRequestError)) return { field: "form", message: FALLBACK_MESSAGE };
  if (cause.status === 403) {
    return { field: "form", message: refusalMessage(cause.message, "Saving") };
  }
  switch (cause.code) {
    case "speaker_availability_stale":
      return { field: "form", message: STALE_MESSAGE };
    case "speaker_availability_window_invalid": {
      const index = numberDetail(cause.details, "index");
      if (index === null) {
        return { field: "form", message: serverWindowMessage(windows, 0, today) };
      }
      return {
        field: "window",
        index,
        part: "from",
        message: serverWindowMessage(windows, index, today),
      };
    }
    case "speaker_availability_too_many_windows":
      return {
        field: "add",
        message: tooManyMessage(numberDetail(cause.details, "limit") ?? MAX_WINDOWS),
      };
    case "speaker_availability_pause_invalid":
      return { field: "pause", message: pauseMessage(today) };
    case "speaker_availability_capacity_invalid":
      return { field: "capacity", message: CAPACITY_MESSAGE };
    case "speaker_contact_not_found":
      return { field: "form", message: NOT_FOUND_MESSAGE };
    case "unit_not_found":
      return { field: "form", message: `${cause.message} Nothing was changed.` };
    case "invalid_request":
      return {
        field: "form",
        message: `The server could not read this form, so nothing was saved. ${cause.message}`,
      };
    case "rate_limited":
      return {
        field: "form",
        message:
          "Too many requests just now. Wait a moment, then save again. Your changes are still in the form.",
      };
    case "unauthenticated":
      return {
        field: "form",
        message: "Your session has ended. Sign in again; your changes on this page were not saved.",
      };
    default:
      return { field: "form", message: FALLBACK_MESSAGE };
  }
}

/** A failed read (GET) as one sentence: the panel's read states and the in-form alert. */
export function readErrorMessage(cause: unknown): string {
  if (cause instanceof ApiRequestError) {
    if (cause.status === 403) return refusalMessage(cause.message, "Reading");
    if (cause.code === "speaker_contact_not_found") return NOT_FOUND_MESSAGE;
    return `Availability could not be loaded. ${cause.message}`;
  }
  return "Availability could not be loaded. The server gave no reason.";
}

// ---------------------------------------------------------------------------
// Copy

/** Words that differ between the Connector's panel and the Speaker's own page (T6b-4). */
export interface AvailabilityCopy {
  notStated: string;
  emptySaveHint: string;
  windowsLegend: string;
  sourceLabel: Record<"speaker" | "connector", string>;
  changedBy: Record<"speaker" | "connector", string>;
  addReason: string;
}

export const COPY: { connector: AvailabilityCopy } = {
  connector: {
    notStated:
      "This Speaker has not said when they can speak, so matching treats their availability as unknown.",
    emptySaveHint:
      "Saving an empty form records that this Speaker told you they have no dates blocked. Only save if they did.",
    windowsLegend: "Dates this Speaker cannot speak",
    sourceLabel: { speaker: "Added by the Speaker", connector: "Added by a Speaker Connector" },
    changedBy: { speaker: "by the Speaker", connector: "by a Speaker Connector" },
    addReason: `${MAX_WINDOWS} is the most a Speaker can have. Remove one to add another.`,
  },
};
