/**
 * The roster row's Availability disclosure (B26 T5 §8 D).
 *
 * The roster read is stubbed; the availability read is stubbed per contact so
 * the test can count which rows asked. Nothing is fetched for a row until its
 * disclosure is opened.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SpeakerContact } from "@/lib/api";
import { speakerLoadFixture } from "@/test/speakerLoadFixture";

import { CoordinatorSpeakerContacts } from "./CoordinatorSpeakerContacts";

const UNIT = "11111111-1111-4111-8111-111111111111";
const ROSTER = `/v1/units/${UNIT}/speaker-contacts`;

vi.mock("../../hooks/useSession", () => ({
  useAuthenticatedPrincipal: () => ({
    user_id: "u1",
    tenant_id: "t1",
    email: "connector@example.edu",
    suspended: false,
    memberships: [],
  }),
}));

vi.mock("../../hooks/usePortalAccess", () => ({
  usePortalAccess: () => ({
    status: "ready",
    mapping: {
      portals: [
        {
          portal: "coordinator",
          display_name: "Connector Dashboard",
          home_path: "/coordinator-portal",
          role: "coordinator",
          roles: ["coordinator"],
          default_unit_id: "11111111-1111-4111-8111-111111111111",
          org_unit_path: "/cba/finance",
        },
      ],
    },
  }),
}));

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => "principal-1",
}));

let calls: string[] = [];

function contact(index: number): SpeakerContact {
  const id = `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
  return {
    professional_id: id,
    owning_unit_id: UNIT,
    full_name: `Contact ${String(index).padStart(2, "0")}`,
    company: null,
    title: null,
    topic_text: null,
    prior_talk: null,
    location_city: null,
    location_postal_code: null,
    primary_industry_code: null,
    industry_taxonomy_version: null,
    primary_role_code: null,
    role_taxonomy_version: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    match_eligible: false,
    match_ineligibility_reason: "unclassified",
    withheld_fields: [],
  };
}

function stubRoster(contacts: SpeakerContact[]): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push(`${method} ${url}`);
      if (method === "GET" && url === ROSTER) {
        return new Response(JSON.stringify({ contacts, truncated: false }), { status: 200 });
      }
      const match = url.match(/speaker-contacts\/([^/]+)\/availability$/);
      if (method === "GET" && match) {
        return new Response(
          JSON.stringify({
            professional_id: decodeURIComponent(match[1]),
            stated: false,
            version: null,
            invitations_paused_until: null,
            declared_capacity_hours_per_90_days: null,
            unavailable: [],
            updated_source: null,
            updated_at: null,
            load: speakerLoadFixture(),
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ error: { code: "test_unstubbed", message: url } }), {
        status: 404,
      });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CoordinatorSpeakerContacts />
    </QueryClientProvider>,
  );
}

function availabilityCalls(): string[] {
  return calls.filter((c) => c.endsWith("/availability"));
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<CoordinatorSpeakerContacts /> availability disclosure", () => {
  it("each row has an Availability disclosure named with the contact, with aria-expanded and aria-controls", async () => {
    stubRoster([contact(1), contact(2)]);
    renderPage();
    const button = await screen.findByRole("button", { name: "Availability for Contact 01" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.getAttribute("aria-controls")).toBe(
      `availability-panel-${contact(1).professional_id}`,
    );
    expect(button.className).toContain("min-h-11");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById(button.getAttribute("aria-controls") ?? "")).not.toBeNull();
    // Closing keeps focus on the button.
    button.focus();
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(button);
  });

  it("two open panels are regions with distinct names", async () => {
    stubRoster([contact(1), contact(2)]);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Availability for Contact 01" }));
    fireEvent.click(screen.getByRole("button", { name: "Availability for Contact 02" }));
    const regions = screen.getAllByRole("region", { name: /^Availability for / });
    expect(regions).toHaveLength(2);
    const names = regions.map((r) => r.getAttribute("aria-labelledby"));
    expect(new Set(names).size).toBe(2);
    expect(screen.getByRole("region", { name: "Availability for Contact 01" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Availability for Contact 02" })).toBeTruthy();
  });

  it("no availability GET until a row is opened; one GET per opened row", async () => {
    stubRoster([contact(1), contact(2), contact(3)]);
    renderPage();
    const first = await screen.findByRole("button", { name: "Availability for Contact 01" });
    await new Promise((r) => setTimeout(r, 30));
    expect(availabilityCalls()).toEqual([]);

    fireEvent.click(first);
    await waitFor(() => expect(availabilityCalls()).toHaveLength(1));
    expect(availabilityCalls()[0]).toBe(
      `GET ${ROSTER}/${contact(1).professional_id}/availability`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Availability for Contact 03" }));
    await waitFor(() => expect(availabilityCalls()).toHaveLength(2));
    expect(availabilityCalls()[1]).toBe(
      `GET ${ROSTER}/${contact(3).professional_id}/availability`,
    );
    await screen.findAllByText(/Not stated\./);
  });

  it("the roster still pages", async () => {
    stubRoster(Array.from({ length: 12 }, (_, i) => contact(i + 1)));
    renderPage();
    await screen.findByRole("button", { name: "Availability for Contact 10" });
    expect(screen.queryByRole("button", { name: "Availability for Contact 11" })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Next page of contacts" })[0]);
    await screen.findByRole("button", { name: "Availability for Contact 11" });
    expect(screen.queryByRole("button", { name: "Availability for Contact 01" })).toBeNull();
  });
});
