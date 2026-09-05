import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, type RouteObject } from "react-router";
import { isCapabilityEnabled, type Capability } from "@/lib/productScope";
import { Layout } from "./components/Layout";
import { StudentLayout } from "./components/StudentLayout";
import { CoordinatorPortalLayout } from "./components/CoordinatorPortalLayout";
import { VolunteerPortalLayout } from "./components/VolunteerPortalLayout";
import { RouteFallback } from "./components/RouteFallback";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";

// Portal/admin pages are code-split per route so the initial bundle only
// carries the landing/login flow. Each import below becomes its own chunk.
const Dashboard = lazy(() =>
  import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const Opportunities = lazy(() =>
  import("./pages/Opportunities").then((m) => ({ default: m.Opportunities })),
);
const Volunteers = lazy(() =>
  import("./pages/Volunteers").then((m) => ({ default: m.Volunteers })),
);
const Pipeline = lazy(() =>
  import("./pages/Pipeline").then((m) => ({ default: m.Pipeline })),
);
const Calendar = lazy(() =>
  import("./pages/Calendar").then((m) => ({ default: m.Calendar })),
);
const Outreach = lazy(() =>
  import("./pages/Outreach").then((m) => ({ default: m.Outreach })),
);
const AIMatching = lazy(() =>
  import("./pages/AIMatching").then((m) => ({ default: m.AIMatching })),
);

const StudentHome = lazy(() =>
  import("./pages/student/StudentHome").then((m) => ({ default: m.StudentHome })),
);
const StudentEvents = lazy(() =>
  import("./pages/student/StudentEvents").then((m) => ({ default: m.StudentEvents })),
);
const StudentHistory = lazy(() =>
  import("./pages/student/StudentHistory").then((m) => ({ default: m.StudentHistory })),
);
const StudentConnect = lazy(() =>
  import("./pages/student/StudentConnect").then((m) => ({ default: m.StudentConnect })),
);
const StudentRewards = lazy(() =>
  import("./pages/student/StudentRewards").then((m) => ({ default: m.StudentRewards })),
);

const CoordinatorHome = lazy(() =>
  import("./pages/coordinator/CoordinatorHome").then((m) => ({ default: m.CoordinatorHome })),
);
const CoordinatorEvents = lazy(() =>
  import("./pages/coordinator/CoordinatorEvents").then((m) => ({ default: m.CoordinatorEvents })),
);
const CoordinatorOutreach = lazy(() =>
  import("./pages/coordinator/CoordinatorOutreach").then((m) => ({
    default: m.CoordinatorOutreach,
  })),
);
const CoordinatorMeetings = lazy(() =>
  import("./pages/coordinator/CoordinatorMeetings").then((m) => ({
    default: m.CoordinatorMeetings,
  })),
);

const VolunteerHome = lazy(() =>
  import("./pages/volunteer/VolunteerHome").then((m) => ({ default: m.VolunteerHome })),
);
const VolunteerAssignments = lazy(() =>
  import("./pages/volunteer/VolunteerAssignments").then((m) => ({
    default: m.VolunteerAssignments,
  })),
);
const VolunteerProfile = lazy(() =>
  import("./pages/volunteer/VolunteerProfile").then((m) => ({ default: m.VolunteerProfile })),
);

/**
 * react-router v7's object-route `Component:` field renders the component
 * with no Suspense boundary of its own. Layout files are out of scope for
 * this lane, so each lazy page is wrapped locally here (via `element:`)
 * instead of relying on a boundary higher in the tree.
 */
function withSuspense(node: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{node}</Suspense>;
}

/**
 * Routes that exist only when this product offers every capability they need.
 *
 * Composition asks the shared policy (`src/lib/productScope.ts`, mirroring
 * `smartmatch_domain.product_scope`) rather than restating a product decision
 * here. A route the policy has disabled is never handed to the router at all,
 * so there is no path, no chunk fetch, and nothing for a link to point at.
 *
 * Two things this is not:
 *
 * - **Not authorization.** An absent route removes a *claim*; anyone can still
 *   call the API directly, and `/v1` stays deny-by-default and tenant-scoped
 *   (`smartmatch_authz`). See the policy module's own header.
 * - **Not deletion.** The page still exists and still compiles; the customer
 *   put the capability out of scope for this phase (§20), which is a different
 *   statement from "this code is wrong".
 *
 * Every capability must be enabled, not any: a surface that composes two gated
 * capabilities must not become reachable because a later phase re-opened one.
 */
function whenCapable(
  capabilities: readonly Capability[],
  ...routes: readonly RouteObject[]
): RouteObject[] {
  return capabilities.every(isCapabilityEnabled) ? [...routes] : [];
}

/**
 * What the legacy admin `/outreach` page would need in order to be an honest
 * offer, and why it is two capabilities rather than one.
 *
 * The page reaches unknown university contacts through the legacy
 * `/api/data/*` reads — cold contact of someone who never consented — *and* it
 * embeds `CrawlerFeed`, the retired external-discovery surface. Customer §20
 * puts both out of scope for this phase. Naming both here means a later phase
 * that re-opened only one of them does not silently restore the whole page.
 *
 * The preserved outreach path is the coordinator portal's, below: consented
 * `/v1` sends whose consent is re-checked at delivery. It shares a word with
 * this page and nothing else, and it is deliberately not gated.
 */
const LEGACY_COLD_OUTREACH_CAPABILITIES: readonly Capability[] = [
  "cold_unknown_contact_outreach",
  "external_speaker_acquisition",
];

export const router = createBrowserRouter([
  // Public routes (no sidebar) — kept static: this is the first code an
  // unauthenticated visitor needs, and lazy-loading it would add a fetch
  // round trip before anything can render at all.
  { path: "/", Component: LandingPage },
  { path: "/login", Component: LoginPage },

  // Student portal routes
  {
    path: "student-portal",
    Component: StudentLayout,
    children: [
      { index: true, element: withSuspense(<StudentHome />) },
      { path: "events", element: withSuspense(<StudentEvents />) },
      { path: "history", element: withSuspense(<StudentHistory />) },
      { path: "connect", element: withSuspense(<StudentConnect />) },
      { path: "rewards", element: withSuspense(<StudentRewards />) },
    ],
  },

  // Event coordinator portal routes
  {
    path: "coordinator-portal",
    Component: CoordinatorPortalLayout,
    children: [
      { index: true, element: withSuspense(<CoordinatorHome />) },
      { path: "events", element: withSuspense(<CoordinatorEvents />) },
      { path: "outreach", element: withSuspense(<CoordinatorOutreach />) },
      { path: "meetings", element: withSuspense(<CoordinatorMeetings />) },
    ],
  },

  // Volunteer portal routes
  {
    path: "volunteer-portal",
    Component: VolunteerPortalLayout,
    children: [
      { index: true, element: withSuspense(<VolunteerHome />) },
      { path: "assignments", element: withSuspense(<VolunteerAssignments />) },
      { path: "profile", element: withSuspense(<VolunteerProfile />) },
    ],
  },

  // IA Admin routes (with sidebar layout — pathless layout route)
  {
    Component: Layout,
    children: [
      { path: "dashboard", element: withSuspense(<Dashboard />) },
      { path: "opportunities", element: withSuspense(<Opportunities />) },
      { path: "volunteers", element: withSuspense(<Volunteers />) },
      { path: "ai-matching", element: withSuspense(<AIMatching />) },
      { path: "pipeline", element: withSuspense(<Pipeline />) },
      { path: "calendar", element: withSuspense(<Calendar />) },
      ...whenCapable(LEGACY_COLD_OUTREACH_CAPABILITIES, {
        path: "outreach",
        element: withSuspense(<Outreach />),
      }),
    ],
  },
]);
