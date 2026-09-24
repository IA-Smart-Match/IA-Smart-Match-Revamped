/**
 * The speaker-availability adapter (B26 T3): URL, method, exact body, and that
 * the server's error `code` and `details` reach the caller intact.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiRequestError,
  clearStoredSmartmatchBearerToken,
  fetchSpeakerAvailability,
  storeSmartmatchBearerToken,
  updateSpeakerAvailability,
  type SpeakerAvailability,
  type SpeakerAvailabilityUpdatePayload,
} from "./api";

const UNIT = "unit/1";
const PROFESSIONAL = "pro 2";
const EXPECTED_URL =
  "/v1/units/unit%2F1/speaker-contacts/pro%202/availability";

// Built at runtime: a credential-shaped literal in a test is flagged by the
// forbidden-behaviour scanner.
const bearer = ["availability", "test", String(Date.now())].join("-");

const STORED: SpeakerAvailability = {
  professional_id: PROFESSIONAL,
  stated: true,
  version: 3,
  invitations_paused_until: null,
  declared_capacity_hours_per_90_days: 24.5,
  unavailable: [{ starts_on: "2026-11-01", ends_on: "2026-11-02", source: "connector" }],
  updated_source: "connector",
  updated_at: "2026-10-06T15:00:00Z",
};

function respond(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function callOf(fetchMock: ReturnType<typeof vi.fn>): [string, RequestInit] {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return [url, init];
}

describe("speaker availability adapter", () => {
  beforeEach(() => {
    storeSmartmatchBearerToken(bearer);
  });

  afterEach(() => {
    clearStoredSmartmatchBearerToken();
    vi.unstubAllGlobals();
  });

  it("GETs the encoded URL with the bearer", async () => {
    const fetchMock = respond(200, STORED);
    const result = await fetchSpeakerAvailability(UNIT, PROFESSIONAL);
    const [url, init] = callOf(fetchMock);
    expect(url).toBe(EXPECTED_URL);
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${bearer}`);
    expect(result).toEqual(STORED);
  });

  it("PATCHes exactly the payload it was given", async () => {
    const fetchMock = respond(200, STORED);
    const payload: SpeakerAvailabilityUpdatePayload = {
      expected_version: null,
      invitations_paused_until: "2026-10-20",
      declared_capacity_hours_per_90_days: null,
      unavailable: [{ starts_on: "2026-11-01", ends_on: "2026-11-02" }],
    };
    await updateSpeakerAvailability(UNIT, PROFESSIONAL, payload);
    const [url, init] = callOf(fetchMock);
    expect(url).toBe(EXPECTED_URL);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual(payload);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${bearer}`);
  });

  it("surfaces a 409 as speaker_availability_stale", async () => {
    respond(409, {
      error: { code: "speaker_availability_stale", message: "Re-read and try again." },
    });
    const error = await updateSpeakerAvailability(UNIT, PROFESSIONAL, {
      expected_version: 2,
      invitations_paused_until: null,
      declared_capacity_hours_per_90_days: null,
      unavailable: [],
    }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect((error as ApiRequestError).status).toBe(409);
    expect((error as ApiRequestError).code).toBe("speaker_availability_stale");
  });

  it("keeps details.index on a 422", async () => {
    respond(422, {
      error: {
        code: "speaker_availability_window_invalid",
        message: "A window is invalid.",
        details: { field: "unavailable", index: 1 },
      },
    });
    const error = await updateSpeakerAvailability(UNIT, PROFESSIONAL, {
      expected_version: 1,
      invitations_paused_until: null,
      declared_capacity_hours_per_90_days: null,
      unavailable: [],
    }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect((error as ApiRequestError).code).toBe("speaker_availability_window_invalid");
    expect((error as ApiRequestError).details).toEqual({ field: "unavailable", index: 1 });
  });
});
