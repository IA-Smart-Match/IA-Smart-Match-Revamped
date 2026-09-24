/**
 * `/speaker-portal` is routed only when `speaker_portal` is on (B26 T6b-1, L6):
 * no page may exist for a role nothing can grant. The on-state is mocked.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { speakerPortalRoutes } from "./speakerPortalRoutes";

const scope = vi.hoisted(() => ({ on: false }));

vi.mock("../lib/productScope", () => ({
  isCapabilityEnabled: (capability: string) => capability === "speaker_portal" && scope.on,
}));

afterEach(() => {
  cleanup();
  scope.on = false;
});

describe("speakerPortalRoutes", () => {
  it("speaker-portal is not routed when the capability is off", () => {
    scope.on = false;
    expect(speakerPortalRoutes()).toEqual([]);
  });

  it("speaker-portal renders the placeholder when on", async () => {
    scope.on = true;
    const routes = speakerPortalRoutes();
    expect(routes.map((route) => route.path)).toEqual(["speaker-portal"]);
    const router = createMemoryRouter(routes, { initialEntries: ["/speaker-portal"] });
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole("heading", { name: "Speaker Portal" })).toBeTruthy();
  });
});
