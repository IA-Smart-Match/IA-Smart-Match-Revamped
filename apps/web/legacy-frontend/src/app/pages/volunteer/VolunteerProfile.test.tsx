/**
 * The Host Profile page (B26 T7, plan `docs/plans/b26-tracks/T7-plan.md` §2-§3).
 *
 * The page shows the caller's own record from the two gated contexts
 * (`GET /v1/me`, `GET /v1/me/portals`) and links to the Organization page. It
 * issues no request of its own, so `fetch` is stubbed to fail on any call.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MeResponse, PortalDescriptor } from "@/lib/api";

import type { PortalAccessState } from "../../hooks/usePortalAccess";

import { VolunteerProfile } from "./VolunteerProfile";

const PRINCIPAL_A: MeResponse = {
  user_id: "7c1e2a4b-5d6f-4a8b-9c0d-1e2f3a4b5c6d",
  tenant_id: "0a9b8c7d-6e5f-4a3b-8c1d-2e3f4a5b6c7d",
  email: "host.alpha@example.test",
  suspended: false,
  memberships: [],
};

const PRINCIPAL_B: MeResponse = {
  user_id: "d4c3b2a1-f6e5-4d7c-8b9a-0f1e2d3c4b5a",
  tenant_id: "0a9b8c7d-6e5f-4a3b-8c1d-2e3f4a5b6c7d",
  email: "host.beta@example.test",
  suspended: false,
  memberships: [],
};

function grantFor(unitId: string, path: string, unitName: string): PortalDescriptor {
  return {
    portal: "volunteer",
    display_name: "Host portal (test)",
    home_path: "/volunteer-portal",
    role: "volunteer",
    roles: ["volunteer"],
    org_unit_path: path,
    units: [
      {
        unit_id: unitId,
        path,
        unit_type: "club",
        display_name: unitName,
        roles: ["volunteer"],
      },
    ],
    default_unit_id: unitId,
  };
}

const GRANT_A = grantFor("3f2e1d0c-9b8a-4c7d-8e6f-5a4b3c2d1e0f", "/cba/alpha-club", "Alpha Test Club");
const GRANT_B = grantFor("8e7d6c5b-4a39-4281-9f0e-1d2c3b4a5968", "/cba/beta-club", "Beta Test Club");

// Mutable so a test can switch principal or hold the grant unresolved;
// `vi.hoisted` because the mock factories are hoisted above everything else.
const state = vi.hoisted(() => ({
  principal: null as unknown,
  access: { status: "loading" } as PortalAccessState,
}));

vi.mock("../../hooks/useSession", () => ({
  useAuthenticatedPrincipal: () => state.principal,
}));

vi.mock("../../hooks/usePortalAccess", () => ({
  usePortalAccess: () => state.access,
}));

function ready(grant: PortalDescriptor): PortalAccessState {
  return { status: "ready", mapping: { portals: [grant], default_portal: "volunteer" } };
}

const fetchSpy = vi.fn(() => Promise.reject(new Error("VolunteerProfile must not fetch")));

function renderPage() {
  return render(
    <MemoryRouter>
      <VolunteerProfile />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.principal = PRINCIPAL_A;
  state.access = ready(GRANT_A);
  fetchSpy.mockClear();
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("VolunteerProfile", () => {
  it("renders the host's own record: email, role, org unit and units", () => {
    renderPage();
    // The card shows the email twice: as the display name (`h1`) and under "Signed in as".
    expect(screen.getAllByText("host.alpha@example.test")).toHaveLength(2);
    expect(screen.getByText("Role assigned by the server")).toBeTruthy();
    expect(screen.getByText("Org unit")).toBeTruthy();
    expect(screen.getByText("Signed in as")).toBeTruthy();
    expect(screen.getByText("Units this grant covers")).toBeTruthy();
    expect(screen.getByText("volunteer")).toBeTruthy();
    expect(screen.getByText("/cba/alpha-club")).toBeTruthy();
    expect(screen.getByText(/Alpha Test Club/)).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('heading outline is one h1 then h2 "Your organization"; "Profile" is an eyebrow', () => {
    const { container } = renderPage();
    const levels = Array.from(container.querySelectorAll("h1, h2, h3, h4, h5, h6")).map((h) =>
      Number(h.tagName.slice(1)),
    );
    expect(levels).toEqual([1, 2]);
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Your organization");
    const eyebrow = screen.getByText("Profile");
    expect(eyebrow.tagName).toBe("P");
    expect(eyebrow.className).not.toContain("text-2xl");
    expect(screen.getByText("Your Event Host record.")).toBeTruthy();
  });

  it('links to /volunteer-portal/organization with the name "Go to Organization"', () => {
    renderPage();
    const region = screen.getByRole("region", { name: "Your organization" });
    const link = within(region).getByRole("link", { name: "Go to Organization" });
    expect(link.getAttribute("href")).toBe("/volunteer-portal/organization");
    expect(within(region).getByText("Your organization is described on its own page.")).toBeTruthy();
  });

  it("organization link is keyboard-focusable with the visible focus ring", () => {
    renderPage();
    const link = screen.getByRole("link", { name: "Go to Organization" });
    expect(link.tagName).toBe("A");
    expect(link.hasAttribute("href")).toBe(true);
    const tabIndex = link.getAttribute("tabindex");
    expect(tabIndex === null || Number(tabIndex) >= 0).toBe(true);
    link.focus();
    expect(document.activeElement).toBe(link);
    expect(link.className).toContain("focus-visible:ring-2");
    expect(link.className).toContain("focus-visible:ring-ring");
    expect(link.className).toContain("focus-visible:ring-offset-2");
    expect(link.className).toContain("focus-visible:ring-offset-background");
    expect(link.className).toContain("focus-visible:outline-none");
  });

  it("does not render the legacy volunteer-profile panel", () => {
    const { container } = renderPage();
    expect(screen.queryByText("Your volunteer profile")).toBeNull();
    expect(container.textContent ?? "").not.toContain("/api/portals");
  });

  it("renders nothing and makes no request when the grant is not resolved", () => {
    state.access = { status: "loading" };
    const { container } = renderPage();
    expect(container.innerHTML).toBe("");
    expect(fetchSpy).toHaveBeenCalledTimes(0);
  });

  it("renders nothing and makes no request when the server granted no volunteer portal", () => {
    state.access = { status: "ready", mapping: { portals: [], default_portal: null } };
    const { container } = renderPage();
    expect(container.innerHTML).toBe("");
    expect(fetchSpy).toHaveBeenCalledTimes(0);
  });

  it("re-renders for a new principal without showing the old one", () => {
    const { rerender } = renderPage();
    expect(screen.getAllByText("host.alpha@example.test").length).toBeGreaterThan(0);
    expect(screen.getByText(/Alpha Test Club/)).toBeTruthy();

    state.principal = PRINCIPAL_B;
    state.access = ready(GRANT_B);
    rerender(
      <MemoryRouter>
        <VolunteerProfile />
      </MemoryRouter>,
    );

    expect(screen.getAllByText("host.beta@example.test").length).toBeGreaterThan(0);
    expect(screen.getByText(/Beta Test Club/)).toBeTruthy();
    expect(screen.queryAllByText("host.alpha@example.test")).toHaveLength(0);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
