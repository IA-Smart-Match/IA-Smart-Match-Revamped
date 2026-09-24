/**
 * The `/speaker-portal` shell (B26 T6b-4 §2.2, §8.1): two gates before any
 * chrome, a labelled nav with `aria-current`, the server's own names, a mobile
 * menu that manages focus, hover prefetch, and focus to the new page's `h1` on
 * a route change (never on the shell's first render).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpeakerPortalLayout } from "./SpeakerPortalLayout";

const UNIT = "22222222-2222-4222-8222-222222222222";

const state = vi.hoisted(() => ({
  session: { status: "signed-in" } as Record<string, unknown>,
  portals: [] as Record<string, unknown>[],
  principalKey: "principal-1" as string | null,
}));

const ME = {
  user_id: "u-speaker",
  tenant_id: "t1",
  email: "dana.speaker@example.edu",
  suspended: false,
  memberships: [],
};

const SPEAKER_GRANT = {
  portal: "speaker",
  display_name: "Speaker Portal",
  home_path: "/speaker-portal",
  role: "speaker",
  roles: ["speaker"],
  default_unit_id: UNIT,
  org_unit_path: "/cba/accounting",
};

vi.mock("../hooks/useSession", () => ({
  useSession: () => state.session,
  useSignOut: () => () => undefined,
  useRetrySession: () => () => undefined,
}));

vi.mock("../hooks/usePortalAccess", () => ({
  usePortalAccess: () => ({ status: "ready", mapping: { portals: state.portals } }),
  useRetryPortalAccess: () => () => undefined,
}));

vi.mock("./PrincipalQueryProvider", () => ({
  usePrincipalKey: () => state.principalKey,
}));

function Page({ heading }: { heading: string }) {
  return (
    <h1 tabIndex={-1} className="scroll-mt-20">
      {heading}
    </h1>
  );
}

let client: QueryClient;

function renderShell(path = "/speaker-portal") {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
  const router = createMemoryRouter(
    [
      {
        path: "/speaker-portal",
        Component: SpeakerPortalLayout,
        children: [
          { index: true, element: <Page heading="Home" /> },
          { path: "invitations", element: <Page heading="Invitations" /> },
          { path: "engagements", element: <Page heading="Engagements" /> },
          { path: "availability", element: <Page heading="Your availability" /> },
          { path: "contact-preferences", element: <Page heading="Contact preferences" /> },
        ],
      },
      { path: "/login", element: <p>Sign-in page</p> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

function nav(): HTMLElement {
  return screen.getByRole("navigation", { name: "Speaker Portal navigation" });
}

beforeEach(() => {
  state.session = { status: "signed-in", me: ME };
  state.portals = [SPEAKER_GRANT];
  state.principalKey = "principal-1";
  // `ScrollToTop` scrolls on each route change; jsdom does not implement it.
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

describe("<SpeakerPortalLayout />", () => {
  it("signed-out renders SessionGate and no nav", async () => {
    state.session = { status: "signed-out", reason: "no-token" };
    renderShell();
    expect(await screen.findByText("Sign-in page")).toBeTruthy();
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("no speaker grant renders PortalGate and no nav", () => {
    state.portals = [{ ...SPEAKER_GRANT, portal: "volunteer", display_name: "Event Host Portal" }];
    renderShell();
    expect(screen.getByText("This portal isn’t assigned to your account")).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Speaker Portal navigation" })).toBeNull();
  });

  it("granted renders the nav with 5 links named Home, Invitations, Engagements, Availability, Contact preferences", () => {
    renderShell();
    const names = within(nav())
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(names).toEqual([
      "Home",
      "Invitations",
      "Engagements",
      "Availability",
      "Contact preferences",
    ]);
    const hrefs = within(nav())
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual([
      "/speaker-portal",
      "/speaker-portal/invitations",
      "/speaker-portal/engagements",
      "/speaker-portal/availability",
      "/speaker-portal/contact-preferences",
    ]);
  });

  it("the current link has aria-current=page; Home only on the index", async () => {
    const router = renderShell();
    const home = within(nav()).getByRole("link", { name: "Home" });
    expect(home.getAttribute("aria-current")).toBe("page");

    await act(async () => {
      await router.navigate("/speaker-portal/engagements?when=past");
    });
    expect(within(nav()).getByRole("link", { name: "Home" }).getAttribute("aria-current")).toBeNull();
    expect(
      within(nav()).getByRole("link", { name: "Engagements" }).getAttribute("aria-current"),
    ).toBe("page");
    const current = within(nav())
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
  });

  it("the sidebar shows the server's display name and unit path", () => {
    renderShell();
    expect(screen.getAllByText("Speaker Portal").length).toBeGreaterThan(0);
    expect(screen.getByText("/cba/accounting")).toBeTruthy();
    expect(screen.getByText("dana.speaker@example.edu")).toBeTruthy();
  });

  it("the menu button toggles aria-expanded; opening moves focus to Close; Escape closes and returns focus", () => {
    renderShell();
    const open = screen.getByRole("button", { name: "Open navigation" });
    expect(open.getAttribute("aria-expanded")).toBe("false");
    expect(open.getAttribute("aria-controls")).toBe("speaker-portal-sidebar");
    expect(document.getElementById("speaker-portal-sidebar")).not.toBeNull();

    fireEvent.click(open);
    expect(open.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close navigation" }));

    fireEvent.keyDown(document, { key: "Escape" });
    expect(open.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(open);
  });

  it("the Close button closes the menu and returns focus to the menu button", () => {
    renderShell();
    const open = screen.getByRole("button", { name: "Open navigation" });
    fireEvent.click(open);
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(open.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(open);
  });

  it("hovering a link prefetches exactly that page's keys", () => {
    renderShell();
    const prefetch = vi.spyOn(client, "prefetchQuery").mockResolvedValue(undefined);
    fireEvent.mouseEnter(within(nav()).getByRole("link", { name: "Contact preferences" }));
    expect(prefetch.mock.calls.map(([options]) => options.queryKey)).toEqual([
      ["principal-1", "my-contact-channels"],
    ]);
    prefetch.mockClear();
    fireEvent.mouseEnter(within(nav()).getByRole("link", { name: "Home" }));
    expect(prefetch.mock.calls.map(([options]) => options.queryKey)).toEqual([
      ["principal-1", "my-invitations"],
      ["principal-1", "my-engagements", "upcoming"],
    ]);
  });

  it("nothing is prefetched while the principal key is null", () => {
    state.principalKey = null;
    renderShell();
    const prefetch = vi.spyOn(client, "prefetchQuery").mockResolvedValue(undefined);
    fireEvent.mouseEnter(within(nav()).getByRole("link", { name: "Contact preferences" }));
    expect(prefetch).not.toHaveBeenCalled();
  });

  it("navigating from Home to Invitations moves focus to the Invitations h1; the shell's first render moves no focus", async () => {
    renderShell();
    expect(screen.getByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(document.activeElement).toBe(document.body);

    await act(async () => {
      fireEvent.click(within(nav()).getByRole("link", { name: "Invitations" }));
    });
    const heading = await screen.findByRole("heading", { level: 1, name: "Invitations" });
    expect(document.activeElement).toBe(heading);
  });

  it("Sign out directly follows the profile block in the footer", () => {
    renderShell();
    const signOut = screen.getByRole("button", { name: "Sign out" });
    const previous = signOut.previousElementSibling;
    expect(previous).not.toBeNull();
    expect(previous?.textContent).toContain("dana.speaker@example.edu");
    expect(previous?.textContent).toContain("/cba/accounting");
  });
});
