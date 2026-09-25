/**
 * The Event Host shell's portal switcher slots (B26 T6b-5 §6.3): above the
 * profile block in the sidebar (DESIGN.md "Signed-in shells"), and the mobile
 * header's right-hand slot. Nothing is shown with one portal.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VolunteerPortalLayout } from "./VolunteerPortalLayout";

const state = vi.hoisted(() => ({
  portals: [] as Record<string, unknown>[],
}));

const ME = {
  user_id: "u-host",
  tenant_id: "t1",
  email: "harper.host@example.edu",
  suspended: false,
  memberships: [],
};

const HOST_GRANT = {
  portal: "volunteer",
  display_name: "Event Host Portal",
  home_path: "/volunteer-portal",
  role: "volunteer",
  roles: ["volunteer"],
  default_unit_id: null,
  org_unit_path: "/cba/marketing",
  units: [],
};

const SPEAKER_GRANT = {
  ...HOST_GRANT,
  portal: "speaker",
  display_name: "Speaker Portal",
  home_path: "/speaker-portal",
  role: "speaker",
  roles: ["speaker"],
};

vi.mock("../hooks/useSession", () => ({
  useSession: () => ({ status: "signed-in", me: ME }),
  useSignOut: () => () => undefined,
  useRetrySession: () => () => undefined,
}));

vi.mock("../hooks/usePortalAccess", () => ({
  usePortalAccess: () => ({
    status: "ready",
    mapping: { portals: state.portals },
  }),
  useRetryPortalAccess: () => () => undefined,
}));

vi.mock("./PrincipalQueryProvider", () => ({
  usePrincipalKey: () => "principal-1",
}));

function renderShell() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      {
        path: "/volunteer-portal",
        Component: VolunteerPortalLayout,
        children: [{ index: true, element: <h1>Home</h1> }],
      },
    ],
    { initialEntries: ["/volunteer-portal"] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function sidebar(): HTMLElement {
  return screen.getByRole("complementary");
}

beforeEach(() => {
  state.portals = [HOST_GRANT];
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response("{}", { status: 404 }))),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("<VolunteerPortalLayout /> portal switcher", () => {
  it("with one portal there is no portal switcher", () => {
    renderShell();
    expect(screen.getByRole("heading", { name: "Home" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Switch portal" })).toBeNull();
  });

  it("with a second portal the sidebar switcher sits above the profile block, and Sign out directly follows the profile", () => {
    state.portals = [HOST_GRANT, SPEAKER_GRANT];
    renderShell();
    const inSidebar = within(sidebar()).getByRole("button", {
      name: "Switch portal",
    });
    const signOut = within(sidebar()).getByRole("button", { name: "Sign out" });
    const profile = signOut.previousElementSibling as HTMLElement;
    expect(profile.textContent).toContain("harper.host@example.edu");
    expect(
      inSidebar.compareDocumentPosition(profile) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(profile.contains(inSidebar)).toBe(false);
  });

  it("with a second portal the mobile header carries the switcher, marking the Event Host portal current", () => {
    state.portals = [HOST_GRANT, SPEAKER_GRANT];
    renderShell();
    const header = screen.getByRole("banner");
    fireEvent.click(within(header).getByRole("button", { name: "Switch portal" }));
    expect(
      within(header).getByRole("link", { name: "Event Host Portal" }).getAttribute("aria-current"),
    ).toBe("true");
    expect(within(header).getByRole("link", { name: "Speaker Portal" }).getAttribute("href")).toBe(
      "/speaker-portal",
    );
  });
});
