/**
 * The portal switcher (B26 T6b-5 §6.1): one login, two roles. A disclosure of
 * page links — never `role="menu"` — shown only when the server granted two or
 * more portals. It grants nothing, fetches nothing and writes only the
 * remembered portal id.
 */
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PORTAL_CHOICE_KEY } from "@/lib/portalChoice";

import { PortalSwitcher } from "./PortalSwitcher";

const state = vi.hoisted(() => ({
  access: { status: "loading" } as Record<string, unknown>,
}));

vi.mock("../hooks/usePortalAccess", () => ({
  usePortalAccess: () => state.access,
  useRetryPortalAccess: () => () => undefined,
}));

const HOST = {
  portal: "volunteer",
  display_name: "Event Host Portal",
  home_path: "/volunteer-portal",
  role: "volunteer",
  roles: ["volunteer"],
  org_unit_path: "/cba",
  units: [],
  default_unit_id: null,
};

const SPEAKER = {
  portal: "speaker",
  display_name: "Speaker Portal",
  home_path: "/speaker-portal",
  role: "speaker",
  roles: ["speaker"],
  org_unit_path: "/cba",
  units: [],
  default_unit_id: null,
};

function ready(portals: Record<string, unknown>[]) {
  return { status: "ready", mapping: { portals, default_portal: "volunteer" } };
}

let fetchSpy: ReturnType<typeof vi.fn>;

function renderSwitcher(
  current: "volunteer" | "speaker" = "speaker",
  placement: "sidebar" | "header" = "sidebar",
) {
  const router = createMemoryRouter(
    [
      {
        path: "/speaker-portal",
        element: (
          <div>
            <p>Speaker home</p>
            <button type="button">Outside</button>
            <PortalSwitcher current={current} placement={placement} />
          </div>
        ),
      },
      { path: "/volunteer-portal", element: <p>Host home</p> },
    ],
    { initialEntries: ["/speaker-portal"] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

function toggle(): HTMLElement {
  return screen.getByRole("button", { name: "Switch portal" });
}

beforeEach(() => {
  state.access = ready([HOST, SPEAKER]);
  fetchSpy = vi.fn(() => Promise.resolve(new Response("{}", { status: 500 })));
  vi.stubGlobal("fetch", fetchSpy);
  try {
    window.localStorage.clear();
  } catch {
    // jsdom always has it; the guard mirrors the module under test.
  }
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("<PortalSwitcher />", () => {
  it("renders nothing with one portal", () => {
    state.access = ready([SPEAKER]);
    renderSwitcher();
    expect(screen.queryByRole("button", { name: "Switch portal" })).toBeNull();
    expect(screen.getByText("Speaker home")).toBeTruthy();
  });

  it("renders nothing while loading", () => {
    state.access = { status: "loading" };
    renderSwitcher();
    expect(screen.queryByRole("button", { name: "Switch portal" })).toBeNull();
  });

  it("renders nothing when the mapping is unavailable", () => {
    state.access = { status: "unavailable", problem: "unreachable" };
    renderSwitcher();
    expect(screen.queryByRole("button", { name: "Switch portal" })).toBeNull();
  });

  it("is a disclosure button, collapsed, with no menu role", () => {
    renderSwitcher();
    const button = toggle();
    expect(button.getAttribute("type")).toBe("button");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.getAttribute("aria-haspopup")).toBeNull();
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.queryByRole("link", { name: "Event Host Portal" })).toBeNull();
  });

  it("aria-expanded toggles and aria-controls names the list", () => {
    renderSwitcher();
    fireEvent.click(toggle());
    expect(toggle().getAttribute("aria-expanded")).toBe("true");
    const listId = toggle().getAttribute("aria-controls");
    expect(listId).toBeTruthy();
    expect(document.getElementById(listId as string)?.tagName).toBe("UL");
    fireEvent.click(toggle());
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("lists the server's display names in the server's order, linking home_path", () => {
    renderSwitcher();
    fireEvent.click(toggle());
    const list = document.getElementById(toggle().getAttribute("aria-controls") as string);
    const links = within(list as HTMLElement).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Event Host Portal", "Speaker Portal"]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/volunteer-portal",
      "/speaker-portal",
    ]);
  });

  it('marks only the current portal with aria-current="true"', () => {
    renderSwitcher("speaker");
    fireEvent.click(toggle());
    expect(screen.getByRole("link", { name: "Speaker Portal" }).getAttribute("aria-current")).toBe(
      "true",
    );
    expect(
      screen.getByRole("link", { name: "Event Host Portal" }).getAttribute("aria-current"),
    ).toBeNull();
  });

  it("Escape closes the list and returns focus to the button", () => {
    renderSwitcher();
    fireEvent.click(toggle());
    const link = screen.getByRole("link", { name: "Event Host Portal" });
    link.focus();
    fireEvent.keyDown(link, { key: "Escape" });
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(toggle());
  });

  it("focus leaving the switcher closes it", () => {
    renderSwitcher();
    fireEvent.click(toggle());
    const outside = screen.getByRole("button", { name: "Outside" });
    fireEvent.blur(toggle(), { relatedTarget: outside });
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("Tab from the button into the list keeps it open (real focus move)", () => {
    renderSwitcher();
    toggle().focus();
    fireEvent.click(toggle());
    const link = screen.getByRole("link", { name: "Event Host Portal" });
    act(() => link.focus());
    expect(toggle().getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(link);
  });

  it("focus moving to nothing (WebKit mouse click) keeps it open; a pointer-down outside then closes it", () => {
    renderSwitcher();
    toggle().focus();
    fireEvent.click(toggle());
    act(() => toggle().blur());
    expect(toggle().getAttribute("aria-expanded")).toBe("true");
    fireEvent.pointerDown(screen.getByText("Speaker home"));
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("Escape while open does not reach a document keydown listener (the shell's drawer)", () => {
    const documentKeydown = vi.fn();
    document.addEventListener("keydown", documentKeydown);
    try {
      renderSwitcher();
      fireEvent.click(toggle());
      const link = screen.getByRole("link", { name: "Event Host Portal" });
      act(() => link.focus());
      fireEvent.keyDown(link, { key: "Escape" });
      expect(documentKeydown).not.toHaveBeenCalled();
      expect(document.activeElement).toBe(toggle());
    } finally {
      document.removeEventListener("keydown", documentKeydown);
    }
  });

  it("Escape while closed still propagates", () => {
    const documentKeydown = vi.fn();
    document.addEventListener("keydown", documentKeydown);
    try {
      renderSwitcher();
      fireEvent.keyDown(toggle(), { key: "Escape" });
      expect(documentKeydown).toHaveBeenCalledTimes(1);
    } finally {
      document.removeEventListener("keydown", documentKeydown);
    }
  });

  it("a pointer-down outside closes it", () => {
    renderSwitcher();
    fireEvent.click(toggle());
    fireEvent.pointerDown(screen.getByText("Speaker home"));
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("choosing a portal remembers its id, closes and navigates", async () => {
    const router = renderSwitcher();
    fireEvent.click(toggle());
    await act(async () => {
      fireEvent.click(screen.getByRole("link", { name: "Event Host Portal" }));
    });
    expect(router.state.location.pathname).toBe("/volunteer-portal");
    expect(window.localStorage.getItem(PORTAL_CHOICE_KEY)).toBe("volunteer");
  });

  it("a throwing localStorage still navigates", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const router = renderSwitcher();
    fireEvent.click(toggle());
    await act(async () => {
      fireEvent.click(screen.getByRole("link", { name: "Event Host Portal" }));
    });
    expect(router.state.location.pathname).toBe("/volunteer-portal");
  });

  it("makes no fetch on open or select", async () => {
    renderSwitcher();
    fireEvent.click(toggle());
    await act(async () => {
      fireEvent.click(screen.getByRole("link", { name: "Event Host Portal" }));
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("the header placement keeps the accessible name and a 44px target", () => {
    renderSwitcher("speaker", "header");
    const button = toggle();
    expect(button.className).toContain("min-h-11");
    expect(button.className).toContain("min-w-11");
  });

  it("two instances never share a list id", () => {
    const router = createMemoryRouter(
      [
        {
          path: "/speaker-portal",
          element: (
            <div>
              <PortalSwitcher current="speaker" placement="sidebar" />
              <PortalSwitcher current="speaker" placement="header" />
            </div>
          ),
        },
      ],
      { initialEntries: ["/speaker-portal"] },
    );
    render(<RouterProvider router={router} />);
    const ids = screen
      .getAllByRole("button", { name: "Switch portal" })
      .map((button) => button.getAttribute("aria-controls"));
    expect(new Set(ids).size).toBe(2);
  });
});
