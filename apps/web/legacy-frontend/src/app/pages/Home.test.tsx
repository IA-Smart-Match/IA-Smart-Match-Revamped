/**
 * `/` forwards a signed-in account to a portal the server granted (B26 T6b-5
 * §6.2): the remembered portal when it is still granted, else the server's
 * `default_portal`. The remembered value never names a portal by itself.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PORTAL_CHOICE_KEY } from "@/lib/portalChoice";

import { Home } from "./Home";

const state = vi.hoisted(() => ({
  access: { status: "loading" } as Record<string, unknown>,
}));

vi.mock("../hooks/useSession", () => ({
  useSession: () => ({
    status: "signed-in",
    me: {
      user_id: "u1",
      tenant_id: "t1",
      email: "a@example.edu",
      memberships: [],
    },
  }),
}));

vi.mock("../hooks/usePortalAccess", () => ({
  usePortalAccess: () => state.access,
  useRetryPortalAccess: () => () => undefined,
}));

vi.mock("./LandingPage", () => ({ LandingPage: () => <p>Landing</p> }));

function portal(id: string, home: string) {
  return {
    portal: id,
    display_name: id,
    home_path: home,
    role: id,
    roles: [id],
    org_unit_path: "/cba",
    units: [],
    default_unit_id: null,
  };
}

const HOST = portal("volunteer", "/volunteer-portal");
const SPEAKER = portal("speaker", "/speaker-portal");

function renderHome() {
  const router = createMemoryRouter(
    [
      { path: "/", Component: Home },
      { path: "/volunteer-portal", element: <p>Host home</p> },
      { path: "/speaker-portal", element: <p>Speaker home</p> },
    ],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  window.localStorage.clear();
  state.access = {
    status: "ready",
    mapping: { portals: [HOST, SPEAKER], default_portal: "volunteer" },
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("<Home /> with two portals", () => {
  it("goes to default_portal when nothing is remembered", async () => {
    renderHome();
    expect(await screen.findByText("Host home")).toBeTruthy();
  });

  it("a granted remembered portal wins", async () => {
    window.localStorage.setItem(PORTAL_CHOICE_KEY, "speaker");
    renderHome();
    expect(await screen.findByText("Speaker home")).toBeTruthy();
  });

  it("an ungranted remembered portal is ignored", async () => {
    window.localStorage.setItem(PORTAL_CHOICE_KEY, "speaker");
    state.access = {
      status: "ready",
      mapping: { portals: [HOST], default_portal: "volunteer" },
    };
    renderHome();
    expect(await screen.findByText("Host home")).toBeTruthy();
  });

  it("a throwing storage falls back to default_portal", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderHome();
    expect(await screen.findByText("Host home")).toBeTruthy();
  });
});
