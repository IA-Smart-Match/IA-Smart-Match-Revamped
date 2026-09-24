/**
 * `/speaker-portal`, routed only when `speaker_portal` is on (B26 T6b-1).
 *
 * A deliberate departure from `routes.tsx`'s "mount unconditionally" rule: no
 * page may exist for a role nothing can grant, and until the capability is on
 * nothing grants `speaker`. Off, the path falls through to `NotFound`.
 *
 * On, it is the Speaker Portal shell and its five pages (B26 T6b-4 §2.1), each
 * code-split like every other portal page.
 */
import { lazy, Suspense, type ReactNode } from "react";
import type { RouteObject } from "react-router";

import { isCapabilityEnabled } from "../lib/productScope";
import { NotFound } from "./components/NotFound";
import { RouteFallback } from "./components/RouteFallback";
import { SpeakerPortalLayout } from "./components/SpeakerPortalLayout";

const SpeakerHome = lazy(() =>
  import("./pages/speaker/SpeakerHome").then((m) => ({ default: m.SpeakerHome })),
);
const SpeakerInvitations = lazy(() =>
  import("./pages/speaker/SpeakerInvitations").then((m) => ({ default: m.SpeakerInvitations })),
);
const SpeakerEngagements = lazy(() =>
  import("./pages/speaker/SpeakerEngagements").then((m) => ({ default: m.SpeakerEngagements })),
);
const SpeakerOwnAvailability = lazy(() =>
  import("./pages/speaker/SpeakerOwnAvailability").then((m) => ({
    default: m.SpeakerOwnAvailability,
  })),
);
const SpeakerContactPreferences = lazy(() =>
  import("./pages/speaker/SpeakerContactPreferences").then((m) => ({
    default: m.SpeakerContactPreferences,
  })),
);

/** `routes.tsx`'s own wrapper, repeated here to avoid an import cycle. */
function withSuspense(node: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{node}</Suspense>;
}

export function speakerPortalRoutes(): RouteObject[] {
  if (!isCapabilityEnabled("speaker_portal")) return [];
  return [
    {
      path: "speaker-portal",
      Component: SpeakerPortalLayout,
      errorElement: <NotFound />,
      children: [
        { index: true, element: withSuspense(<SpeakerHome />) },
        { path: "invitations", element: withSuspense(<SpeakerInvitations />) },
        // `?when=upcoming|past`; any other value reads as `upcoming`.
        { path: "engagements", element: withSuspense(<SpeakerEngagements />) },
        { path: "availability", element: withSuspense(<SpeakerOwnAvailability />) },
        { path: "contact-preferences", element: withSuspense(<SpeakerContactPreferences />) },
      ],
    },
  ];
}
