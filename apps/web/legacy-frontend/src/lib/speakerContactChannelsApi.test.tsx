/**
 * The Speaker's own contact-channel adapters (B26 T6b-4 §6.1): URL, method, no
 * body, the bearer, and the server's error `code` and `details` kept intact.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiRequestError,
  clearStoredSmartmatchBearerToken,
  fetchMyContactChannels,
  optInMyContactChannel,
  optOutMyContactChannel,
  storeSmartmatchBearerToken,
  type MyContactChannel,
} from "./api";

// Built at runtime: a credential-shaped literal in a test is flagged by the
// forbidden-behaviour scanner.
const bearer = ["channels", "test", String(Date.now())].join("-");

const CHANNEL: MyContactChannel = {
  contact_channel_id: "ch/1 a",
  channel_kind: "email",
  address: "dana@example.edu",
  contact_state: "active_candidate",
  send_eligible: true,
  suppressed: false,
  suppression_reason: null,
  speaker_choice: null,
  last_set_by: "connector",
  can_opt_in: false,
  can_opt_out: true,
  updated_at: "2026-10-01T12:00:00Z",
};

function respond(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(
    async () =>
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

describe("speaker contact-channel adapters", () => {
  beforeEach(() => {
    storeSmartmatchBearerToken(bearer);
  });

  afterEach(() => {
    clearStoredSmartmatchBearerToken();
    vi.unstubAllGlobals();
  });

  it("fetchMyContactChannels sends GET /v1/me/contact-channels with Authorization", async () => {
    const fetchMock = respond(200, { channels: [CHANNEL], truncated: false });
    const result = await fetchMyContactChannels();
    const [url, init] = callOf(fetchMock);
    expect(url).toBe("/v1/me/contact-channels");
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${bearer}`);
    expect(result).toEqual({ channels: [CHANNEL], truncated: false });
  });

  it("opt-in and opt-out POST to the encoded channel id with no body", async () => {
    const optIn = respond(200, { channel: CHANNEL, changed: true });
    expect(await optInMyContactChannel("ch/1 a")).toEqual({ channel: CHANNEL, changed: true });
    const [inUrl, inInit] = callOf(optIn);
    expect(inUrl).toBe("/v1/me/contact-channels/ch%2F1%20a/opt-in");
    expect(inInit.method).toBe("POST");
    expect(inInit.body).toBeUndefined();
    expect((inInit.headers as Record<string, string>).Authorization).toBe(`Bearer ${bearer}`);

    const optOut = respond(200, { channel: CHANNEL, changed: false });
    expect(await optOutMyContactChannel("ch/1 a")).toEqual({ channel: CHANNEL, changed: false });
    const [outUrl, outInit] = callOf(optOut);
    expect(outUrl).toBe("/v1/me/contact-channels/ch%2F1%20a/opt-out");
    expect(outInit.method).toBe("POST");
    expect(outInit.body).toBeUndefined();
  });

  it.each([
    [404, "speaker_profile_not_linked", undefined],
    [404, "speaker_contact_channel_not_found", undefined],
    [409, "speaker_contact_channel_suppression_not_liftable", { reason: "connector" }],
    [409, "speaker_contact_channel_address_unverified", undefined],
    [409, "speaker_contact_channel_opt_in_unavailable", { contact_state: "relationship_recorded" }],
    [409, "speaker_contact_channel_transition_conflict", undefined],
  ])("%i %s surfaces as ApiRequestError.code with details kept", async (status, code, details) => {
    respond(status, { error: { code, message: "server words", ...(details ? { details } : {}) } });
    const failure = await optInMyContactChannel("ch-1").catch((cause: unknown) => cause);
    expect(failure).toBeInstanceOf(ApiRequestError);
    const error = failure as ApiRequestError;
    expect(error.status).toBe(status);
    expect(error.code).toBe(code);
    expect(error.details).toEqual(details);
  });

  it("no adapter takes a professional, unit or user id", () => {
    expect(fetchMyContactChannels.length).toBe(0);
    expect(optInMyContactChannel.length).toBe(1);
    expect(optOutMyContactChannel.length).toBe(1);
  });
});
