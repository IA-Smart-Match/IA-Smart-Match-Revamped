/**
 * `/speaker-portal`, routed only when `speaker_portal` is on (B26 T6b-1).
 *
 * A deliberate departure from `routes.tsx`'s "mount unconditionally" rule: no
 * page may exist for a role nothing can grant, and until the capability is on
 * nothing grants `speaker`. Off, the path falls through to `NotFound`.
 */
import type { RouteObject } from "react-router";

import { isCapabilityEnabled } from "../lib/productScope";
import { NotFound } from "./components/NotFound";
import { SpeakerPortalPlaceholder } from "./pages/speaker/SpeakerPortalPlaceholder";

export function speakerPortalRoutes(): RouteObject[] {
  if (!isCapabilityEnabled("speaker_portal")) return [];
  return [
    { path: "speaker-portal", Component: SpeakerPortalPlaceholder, errorElement: <NotFound /> },
  ];
}
