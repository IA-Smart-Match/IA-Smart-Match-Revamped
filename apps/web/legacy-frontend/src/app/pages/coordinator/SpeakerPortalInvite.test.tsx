/**
 * "Invite to portal" on one roster contact (B26 T6b-1 plan §7), against a
 * stubbed `fetch`. The capability is off in the build, so every on-state is
 * reached by mocking `lib/productScope`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpeakerPortalInvite } from "./SpeakerPortalInvite";

const UNIT = "11111111-1111-4111-8111-111111111111";
const PERSON = "22222222-2222-4222-8222-222222222222";
const CHANNEL = "33333333-3333-4333-8333-333333333333";
const BASE = `/v1/units/${UNIT}/speaker-contacts/${PERSON}`;

const scope = vi.hoisted(() => ({ on: true }));

vi.mock("../../../lib/productScope", () => ({
  isCapabilityEnabled: (capability: string) => capability === "speaker_portal" && scope.on,
}));

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => "principal-1",
}));

type Answer = { body: unknown; status?: number };
let calls: { url: string; init: RequestInit }[] = [];

function stub(answers: Record<string, Answer | Answer[]>): void {
  const queues: Record<string, Answer[]> = {};
  for (const [key, value] of Object.entries(answers)) {
    queues[key] = Array.isArray(value) ? [...value] : [value];
  }
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const key = `${init.method ?? "GET"} ${url}`;
      const queue = queues[key];
      const answer =
        queue === undefined
          ? { body: { error: { code: "test_unstubbed", message: key } }, status: 404 }
          : queue.length > 1
            ? (queue.shift() as Answer)
            : queue[0];
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function channel(overrides: Record<string, unknown> = {}) {
  return {
    channel: {
      contact_channel_id: CHANNEL,
      professional_id: PERSON,
      channel_kind: "email",
      address: "dana@example.org",
      contact_state: "active_candidate",
      suppressed: false,
      send_eligible: true,
      consent_source: "in_person",
      consent_recorded_at: "2026-09-01T00:00:00Z",
      consent_evidence: null,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
      ...overrides,
    },
    transitions: [],
  };
}

function channels(...items: unknown[]) {
  return { body: { professional_id: PERSON, channels: items, limit: 25, offset: 0 } };
}

let client: QueryClient;

function renderIt() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpeakerPortalInvite unitId={UNIT} professionalId={PERSON} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  scope.on = true;
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SpeakerPortalInvite", () => {
  it("renders nothing when the capability is off", () => {
    scope.on = false;
    stub({});
    const { container } = renderIt();
    expect(container.innerHTML).toBe("");
    expect(calls).toEqual([]);
  });

  it("disables invite with a reason when no channel is eligible", async () => {
    stub({
      [`GET ${BASE}/portal-access`]: { body: { status: "none" } },
      [`GET ${BASE}/channels`]: channels(channel({ send_eligible: false, suppressed: true })),
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Invite to portal" }));
    expect(
      await screen.findByText("No email address this Speaker agreed to receive"),
    ).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Send invitation" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("sends the chosen channel id and shows Invited from the response", async () => {
    stub({
      [`GET ${BASE}/portal-access`]: { body: { status: "none" } },
      [`GET ${BASE}/channels`]: channels(channel()),
      [`POST ${BASE}/portal-invitations`]: {
        status: 202,
        body: {
          invitation_id: "44444444-4444-4444-8444-444444444444",
          status: "invited",
          expires_at: "2026-11-09T15:00:00Z",
          job_id: "55555555-5555-4555-8555-555555555555",
          events_url: "/v1/jobs/55555555-5555-4555-8555-555555555555/events",
        },
      },
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Invite to portal" }));
    fireEvent.click(await screen.findByRole("radio", { name: "dana@example.org" }));
    fireEvent.click(screen.getByRole("button", { name: "Send invitation" }));

    expect(await screen.findByText(/Invited · link expires/)).toBeTruthy();
    const post = calls.find((call) => call.init.method === "POST");
    expect(JSON.parse(String(post?.init.body))).toEqual({ contact_channel_id: CHANNEL });
  });

  it.each([
    [409, "speaker_portal_already_active", "This Speaker already has portal access"],
    [
      409,
      "speaker_portal_invitation_conflict",
      "Another invitation was just sent. Refresh and try again",
    ],
    [422, "speaker_portal_channel_not_eligible", "That address can no longer be emailed"],
  ])("maps %s %s to its message", async (status, code, message) => {
    stub({
      [`GET ${BASE}/portal-access`]: { body: { status: "none" } },
      [`GET ${BASE}/channels`]: channels(channel()),
      [`POST ${BASE}/portal-invitations`]: { status, body: { error: { code, message: "x" } } },
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Invite to portal" }));
    fireEvent.click(await screen.findByRole("radio", { name: "dana@example.org" }));
    fireEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect((await screen.findByRole("alert")).textContent).toContain(message);
  });

  it("revoke asks first and invalidates only the access key", async () => {
    stub({
      [`GET ${BASE}/portal-access`]: [
        {
          body: {
            status: "invited",
            contact_channel_id: CHANNEL,
            issued_at: "2026-11-02T15:00:00Z",
            expires_at: "2026-11-09T15:00:00Z",
          },
        },
        { body: { status: "none" } },
      ],
      [`DELETE ${BASE}/portal-invitations/current`]: { body: { revoked: true } },
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValue(true);
    renderIt();
    const invalidate = vi.spyOn(client, "invalidateQueries");

    fireEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(calls.some((call) => call.init.method === "DELETE")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(invalidate).toHaveBeenCalled());
    expect(invalidate.mock.calls).toEqual([
      [{ queryKey: ["principal-1", "speaker-portal-access", UNIT, PERSON] }],
    ]);
    expect(await screen.findByRole("button", { name: "Invite to portal" })).toBeTruthy();
  });

  it("active state offers no revoke", async () => {
    stub({
      [`GET ${BASE}/portal-access`]: {
        body: { status: "active", bound_at: "2026-11-03T10:00:00Z" },
      },
    });
    renderIt();
    expect(await screen.findByText(/Portal active since/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Revoke" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Invite to portal" })).toBeNull();
  });
});
