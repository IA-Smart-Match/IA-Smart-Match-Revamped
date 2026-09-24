/**
 * `/speaker-portal` is routed only when `speaker_portal` is on (B26 T6b-1, L6):
 * no page may exist for a role nothing can grant. The on-state is mocked. On,
 * it is the Speaker Portal shell with its five pages (B26 T6b-4 §2.1).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { SpeakerPortalLayout } from "./components/SpeakerPortalLayout";
import { NotFound } from "./components/NotFound";
import { speakerPortalRoutes } from "./speakerPortalRoutes";

const scope = vi.hoisted(() => ({ on: false }));

vi.mock("../lib/productScope", () => ({
  isCapabilityEnabled: (capability: string) => capability === "speaker_portal" && scope.on,
}));

afterEach(() => {
  scope.on = false;
});

describe("speakerPortalRoutes", () => {
  it("speaker-portal is not routed when the capability is off", () => {
    scope.on = false;
    expect(speakerPortalRoutes()).toEqual([]);
  });

  it("capability on: speaker-portal has the layout and the 5 child paths", () => {
    scope.on = true;
    const routes = speakerPortalRoutes();
    expect(routes).toHaveLength(1);
    const [portal] = routes;
    expect(portal.path).toBe("speaker-portal");
    expect(portal.Component).toBe(SpeakerPortalLayout);
    expect((portal.errorElement as { type?: unknown } | undefined)?.type).toBe(NotFound);
    const children = portal.children ?? [];
    expect(children.map((child) => (child.index ? "(index)" : child.path))).toEqual([
      "(index)",
      "invitations",
      "engagements",
      "availability",
      "contact-preferences",
    ]);
    for (const child of children) {
      expect(child.element).toBeTruthy();
    }
  });
});
