/**
 * The availability draft model, validation and error messages (B26 T5 §8 A).
 *
 * Pure functions only: no React, no fetch. The limits and their order mirror
 * T1's `validate_availability_statement`; the messages mirror T5 plan §6.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, type SpeakerAvailability } from "./api";
import {
  addMonths,
  availabilityErrorMessage,
  draftFromAvailability,
  formatCalendarDate,
  isDraftUnchanged,
  payloadFromDraft,
  readInput,
  spanDays,
  utcToday,
  validateDraft,
  type AvailabilityDraft,
  type WindowDraft,
} from "./speakerAvailabilityDraft";

const TODAY = "2026-10-06";

function stored(overrides: Partial<SpeakerAvailability> = {}): SpeakerAvailability {
  return {
    professional_id: "p1",
    stated: true,
    version: 4,
    invitations_paused_until: null,
    declared_capacity_hours_per_90_days: null,
    unavailable: [],
    updated_source: "connector",
    updated_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

function notStated(): SpeakerAvailability {
  return stored({
    stated: false,
    version: null,
    updated_source: null,
    updated_at: null,
  });
}

function win(starts_on: string, ends_on: string, key = `w-${starts_on}-${ends_on}`): WindowDraft {
  return { key, starts_on, ends_on, startsBad: false, endsBad: false };
}

function draft(overrides: Partial<AvailabilityDraft> = {}): AvailabilityDraft {
  return {
    baseVersion: 4,
    pause: "",
    pauseBad: false,
    capacity: "",
    capacityBad: false,
    windows: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-06T03:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("dates", () => {
  it("utcToday returns the UTC date", () => {
    // 03:00Z on 6 October is still 5 October in Pacific time.
    expect(utcToday()).toBe("2026-10-06");
  });

  it("addMonths clamps to month end", () => {
    expect(addMonths("2026-08-31", 18)).toBe("2028-02-29");
    expect(addMonths("2027-08-31", 18)).toBe("2029-02-28");
    expect(addMonths("2026-10-06", 12)).toBe("2027-10-06");
  });

  it("spanDays counts whole UTC days and formatCalendarDate never shifts a day", () => {
    expect(spanDays("2026-11-02", "2026-11-06")).toBe(4);
    expect(spanDays("2026-03-01", "2026-03-31")).toBe(30);
    expect(formatCalendarDate("2026-11-02")).toBe("November 2, 2026");
    expect(formatCalendarDate("2027-01-01")).toBe("January 1, 2027");
  });
});

describe("draftFromAvailability", () => {
  it("stated false gives an empty draft with baseVersion null", () => {
    const d = draftFromAvailability(notStated());
    expect(d.baseVersion).toBeNull();
    expect(d.pause).toBe("");
    expect(d.capacity).toBe("");
    expect(d.windows).toEqual([]);
  });

  it("stated keeps server window order", () => {
    const d = draftFromAvailability(
      stored({
        unavailable: [
          { starts_on: "2026-12-20", ends_on: "2026-12-31", source: "speaker" },
          { starts_on: "2026-11-02", ends_on: "2026-11-06", source: "connector" },
        ],
      }),
    );
    expect(d.baseVersion).toBe(4);
    expect(d.windows.map((w) => [w.starts_on, w.ends_on])).toEqual([
      ["2026-12-20", "2026-12-31"],
      ["2026-11-02", "2026-11-06"],
    ]);
    expect(new Set(d.windows.map((w) => w.key)).size).toBe(2);
  });

  it('null capacity is "" never "0"', () => {
    expect(draftFromAvailability(stored()).capacity).toBe("");
    expect(
      draftFromAvailability(stored({ declared_capacity_hours_per_90_days: 24.5 })).capacity,
    ).toBe("24.5");
  });
});

describe("payloadFromDraft", () => {
  it("blanks become null, capacity is a JSON number, windows keep form order, expected_version is baseVersion", () => {
    const empty = payloadFromDraft(draft({ baseVersion: null }));
    expect(empty).toEqual({
      expected_version: null,
      invitations_paused_until: null,
      declared_capacity_hours_per_90_days: null,
      unavailable: [],
    });

    const full = payloadFromDraft(
      draft({
        pause: "2026-10-20",
        capacity: "24.5",
        windows: [win("2026-12-20", "2026-12-31"), win("2026-11-02", "2026-11-06")],
      }),
    );
    expect(full).toEqual({
      expected_version: 4,
      invitations_paused_until: "2026-10-20",
      declared_capacity_hours_per_90_days: 24.5,
      unavailable: [
        { starts_on: "2026-12-20", ends_on: "2026-12-31" },
        { starts_on: "2026-11-02", ends_on: "2026-11-06" },
      ],
    });
    expect(typeof full.declared_capacity_hours_per_90_days).toBe("number");
  });

  it("an explicit expected version overrides the base version", () => {
    expect(payloadFromDraft(draft(), 9).expected_version).toBe(9);
    expect(payloadFromDraft(draft(), null).expected_version).toBeNull();
  });
});

describe("isDraftUnchanged", () => {
  it("compares every field against the stored statement", () => {
    const s = stored({
      declared_capacity_hours_per_90_days: 24,
      unavailable: [{ starts_on: "2026-11-02", ends_on: "2026-11-06", source: "speaker" }],
    });
    const d = draftFromAvailability(s);
    expect(isDraftUnchanged(d, s)).toBe(true);
    expect(isDraftUnchanged({ ...d, capacity: "24.0" }, s)).toBe(true);
    expect(isDraftUnchanged({ ...d, capacity: "25" }, s)).toBe(false);
    expect(isDraftUnchanged({ ...d, windows: [] }, s)).toBe(false);
    expect(isDraftUnchanged({ ...d, pause: "2026-10-10" }, s)).toBe(false);
    expect(isDraftUnchanged(draftFromAvailability(notStated()), notStated())).toBe(true);
  });
});

describe("validateDraft", () => {
  const s = stored();

  it.each([
    ["0", false],
    ["-1", false],
    ["720.1", false],
    ["24.05", false],
    ["0.1", true],
    ["720", true],
    ["", true],
    // T1 quantizes: a value equal to itself at one decimal place is accepted.
    [".5", true],
    ["24.50", true],
    ["0.3", true],
    ["720.0", true],
    ["abc", false],
  ])("capacity %s → ok=%s", (capacity, ok) => {
    const failure = validateDraft(draft({ capacity }), TODAY, s);
    if (ok) {
      expect(failure).toBeNull();
    } else {
      expect(failure).toMatchObject({
        code: "speaker_availability_capacity_invalid",
        field: "capacity",
      });
    }
  });

  it.each([
    ["2026-10-05", false],
    ["2026-10-06", true],
    ["2027-10-06", true],
    ["2027-10-07", false],
  ])("pause %s → ok=%s", (pause, ok) => {
    const failure = validateDraft(draft({ pause }), TODAY, s);
    if (ok) {
      expect(failure).toBeNull();
    } else {
      expect(failure).toMatchObject({ code: "speaker_availability_pause_invalid", field: "pause" });
    }
  });

  it("21 windows → too_many", () => {
    const windows = Array.from({ length: 21 }, (_, i) => {
      const day = String(i + 1).padStart(2, "0");
      return win(`2026-12-${day}`, `2026-12-${day}`, `w${i}`);
    });
    expect(validateDraft(draft({ windows }), TODAY, s)).toMatchObject({
      code: "speaker_availability_too_many_windows",
      field: "count",
    });
  });

  it.each([
    ["blank date", win("2026-11-02", ""), "missing"],
    ["reversed", win("2026-11-06", "2026-11-02"), "reversed"],
    ["span 367", win("2026-11-01", "2027-11-03"), "too_long"],
    ["past today+18m", win("2028-04-01", "2028-04-07"), "past_horizon"],
  ])("window %s → invalid", (_label, bad, reason) => {
    const failure = validateDraft(
      draft({ windows: [win("2026-11-02", "2026-11-06", "a"), bad] }),
      TODAY,
      s,
    );
    expect(failure).toMatchObject({
      code: "speaker_availability_window_invalid",
      field: "window",
      index: 1,
      reason,
    });
  });

  it("span 366 is ok and a past window is ok", () => {
    expect(
      validateDraft(draft({ windows: [win("2026-11-01", "2027-11-02")] }), TODAY, s),
    ).toBeNull();
    expect(
      validateDraft(draft({ windows: [win("2025-01-01", "2025-01-05")] }), TODAY, s),
    ).toBeNull();
    expect(
      validateDraft(draft({ windows: [win("2028-03-30", "2028-04-06")] }), TODAY, s),
    ).toBeNull();
  });

  it("duplicate → reports the later index", () => {
    const failure = validateDraft(
      draft({
        windows: [
          win("2026-11-02", "2026-11-06", "a"),
          win("2026-12-01", "2026-12-02", "b"),
          win("2026-11-02", "2026-11-06", "c"),
        ],
      }),
      TODAY,
      s,
    );
    expect(failure).toMatchObject({ field: "window", index: 2, reason: "duplicate" });
  });

  it("reports the first failure in T1 order: capacity before pause before windows", () => {
    const everythingWrong = draft({
      capacity: "0",
      pause: "2026-01-01",
      windows: [win("2026-11-06", "2026-11-02")],
    });
    expect(validateDraft(everythingWrong, TODAY, s)?.field).toBe("capacity");
    expect(validateDraft({ ...everythingWrong, capacity: "" }, TODAY, s)?.field).toBe("pause");
    expect(
      validateDraft({ ...everythingWrong, capacity: "", pause: "" }, TODAY, s)?.field,
    ).toBe("window");
  });

  it("an unchanged stored expired pause is exempt; a changed past pause is not", () => {
    const withExpired = stored({ invitations_paused_until: "2026-09-30" });
    expect(validateDraft(draft({ pause: "2026-09-30" }), TODAY, withExpired)).toBeNull();
    expect(validateDraft(draft({ pause: "2026-09-29" }), TODAY, withExpired)).toMatchObject({
      code: "speaker_availability_pause_invalid",
    });
    // The exemption follows the latest stored value, not an older one.
    expect(validateDraft(draft({ pause: "2026-09-30" }), TODAY, stored())).toMatchObject({
      code: "speaker_availability_pause_invalid",
    });
  });

  it("badInput on capacity or a date is an error, not a blank", () => {
    expect(readInput("", true)).toEqual({ value: "", bad: true });
    expect(readInput("24", false)).toEqual({ value: "24", bad: false });

    expect(validateDraft(draft({ capacityBad: true }), TODAY, s)).toMatchObject({
      code: "input_unreadable",
      field: "capacity",
    });
    expect(validateDraft(draft({ pauseBad: true }), TODAY, s)).toMatchObject({
      code: "input_unreadable",
      field: "pause",
    });
    expect(
      validateDraft(
        draft({ windows: [{ ...win("2026-11-02", ""), endsBad: true }] }),
        TODAY,
        s,
      ),
    ).toMatchObject({ code: "input_unreadable", field: "window", index: 0, part: "to" });
  });
});

function apiError(status: number, code: string, message = "Server words.", details?: Record<string, unknown>) {
  return new ApiRequestError(message, status, code, details);
}

describe("availabilityErrorMessage", () => {
  const windows = [win("2026-11-02", "2026-11-06"), win("2026-12-20", "2026-12-31")];

  it.each([
    [409, "speaker_availability_stale", undefined, "form", /Someone changed this availability/],
    [
      422,
      "speaker_availability_window_invalid",
      { field: "unavailable", index: 0 },
      "window",
      /^Window 1 \(November 2, 2026 to November 6, 2026\) cannot be saved\./,
    ],
    [
      422,
      "speaker_availability_too_many_windows",
      { field: "unavailable", limit: 20 },
      "add",
      /at most 20 blocked date ranges/,
    ],
    [
      422,
      "speaker_availability_pause_invalid",
      { field: "invitations_paused_until" },
      "pause",
      /The pause must end today \(October 6, 2026\) or later, and no later than October 6, 2027\. Dates count in UTC\./,
    ],
    [
      422,
      "speaker_availability_capacity_invalid",
      { field: "declared_capacity_hours_per_90_days" },
      "capacity",
      /Capacity must be more than 0 and at most 720 hours per 90 days/,
    ],
    [404, "speaker_contact_not_found", undefined, "form", /no longer in your unit's roster/],
    [404, "unit_not_found", undefined, "form", /^Server words\. Nothing was changed\.$/],
    [403, "forbidden", undefined, "form", /^The server refused this request \(403\)\. Server words\..*Nothing was changed\.$/],
    [422, "invalid_request", undefined, "form", /^The server could not read this form, so nothing was saved\. Server words\.$/],
    [429, "rate_limited", undefined, "form", /Too many requests just now/],
    [401, "unauthenticated", undefined, "form", /Your session has ended/],
  ])("%s %s maps to its §6 message", (status, code, details, field, pattern) => {
    const mapped = availabilityErrorMessage(apiError(status, code, "Server words.", details), windows, TODAY);
    expect(mapped.field).toBe(field);
    expect(mapped.message).toMatch(pattern);
  });

  it("window message uses index+1 and the draft's dates", () => {
    const mapped = availabilityErrorMessage(
      apiError(422, "speaker_availability_window_invalid", "x", { field: "unavailable", index: 1 }),
      windows,
      TODAY,
    );
    expect(mapped).toMatchObject({ field: "window", index: 1 });
    expect(mapped.message).toContain("Window 2 (December 20, 2026 to December 31, 2026)");
    expect(mapped.message).toContain("April 6, 2028");
  });

  it("unknown code falls back and does not echo the server message as a value", () => {
    const mapped = availabilityErrorMessage(
      apiError(500, "internal_error", "secret-ish internal detail"),
      windows,
      TODAY,
    );
    expect(mapped.field).toBe("form");
    expect(mapped.message).toBe(
      "Availability could not be saved and the server gave no reason. Nothing was changed; your changes are still in the form.",
    );
    expect(availabilityErrorMessage(new TypeError("fetch failed"), windows, TODAY).message).toBe(
      mapped.message,
    );
  });
});
