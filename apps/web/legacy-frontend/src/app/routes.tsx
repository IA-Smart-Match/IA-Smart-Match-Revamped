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
const StudentSpeakerFeedback = lazy(() =>
  import("./pages/student/StudentSpeakerFeedback").then((m) => ({
    default: m.StudentSpeakerFeedback,
  })),
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
const CoordinatorMatchRuns = lazy(() =>
  import("./pages/coordinator/CoordinatorMatchRuns").then((m) => ({
    default: m.CoordinatorMatchRuns,
  })),
);
const CoordinatorInvitations = lazy(() =>
  import("./pages/coordinator/CoordinatorInvitations").then((m) => ({
    default: m.CoordinatorInvitations,
  })),
);
const CoordinatorMatchingWeights = lazy(() =>
  import("./pages/coordinator/CoordinatorMatchingWeights").then((m) => ({
    default: m.CoordinatorMatchingWeights,
  })),
);
const CoordinatorSpeakerContacts = lazy(() =>
  import("./pages/coordinator/CoordinatorSpeakerContacts").then((m) => ({
    default: m.CoordinatorSpeakerContacts,
  })),
);
const CoordinatorSpeakerFeedback = lazy(() =>
  import("./pages/coordinator/CoordinatorSpeakerFeedback").then((m) => ({
    default: m.CoordinatorSpeakerFeedback,
  })),
);
const CoordinatorReviewQueue = lazy(() =>
  import("./pages/coordinator/CoordinatorReviewQueue").then((m) => ({
    default: m.CoordinatorReviewQueue,
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
const VolunteerSpeakerRequest = lazy(() =>
  import("./pages/volunteer/VolunteerSpeakerRequest").then((m) => ({
    default: m.VolunteerSpeakerRequest,
  })),
);
const VolunteerConfirmedSpeaker = lazy(() =>
  import("./pages/volunteer/VolunteerConfirmedSpeaker").then((m) => ({
    default: m.VolunteerConfirmedSpeaker,
  })),
);
// Customer §12's read side. `GET /v1/units/{unit_id}/host/speaker-requests`
// closed OQ-CBA-014; see the page's own header for the read it does and the
// one it must never call.
const VolunteerMyRequests = lazy(() =>
  import("./pages/volunteer/VolunteerMyRequests").then((m) => ({
    default: m.VolunteerMyRequests,
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
      // Customer §§15-16's student rating surface (OQ-CBA-003). Mounted
      // unconditionally like every other route in this shell: a route is a
      // claim about what exists rather than a permission, and both
      // `.../student/events/{event_id}/speaker-feedback` and the submit and
      // withdraw pair beside it are `student`-scoped server-side, authorized
      // per request against the loaded unit, whatever this router renders.
      { path: "speaker-feedback", element: withSuspense(<StudentSpeakerFeedback />) },
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
      // Customer §13's speaker-contact roster. Mounted unconditionally like
      // every other route in this shell: the capability that gates the *API* is
      // `speaker_contact_management`, and it is on under both product scopes,
      // so there is nothing here for `whenCapable` to remove. A UI gate is not
      // authorization in any case — the server decides, per request, and this
      // page is behind `admin`/`coordinator` there regardless of what the
      // browser renders.
      { path: "speaker-contacts", element: withSuspense(<CoordinatorSpeakerContacts />) },
      // Customer §16's Connector read of student feedback, aggregate-only per
      // OQ-CBA-003 part 1. Mounted unconditionally for the reason the roster
      // above is: a route is a claim about what exists rather than a
      // permission. `GET .../speakers/{speaker_id}/feedback-summary` is
      // `admin`/`coordinator` server-side whatever the router renders, and
      // there is deliberately no route listing individual ratings for a later
      // page to reach for.
      { path: "speaker-feedback", element: withSuspense(<CoordinatorSpeakerFeedback />) },
      // Card B24's replacement: the Connector submits a real match run against
      // a filed Speaker Request. Mounted unconditionally for the same reason
      // the roster above is — the capability gating the *API* is on under both
      // product scopes, and a route is a claim about what exists rather than a
      // permission. `POST /v1/units/{unit_id}/match-runs` is authorized
      // server-side per request whatever the router renders.
      { path: "match-runs", element: withSuspense(<CoordinatorMatchRuns />) },
      // §13's compose step, reached from a shortlist link carrying `?run={id}`.
      // Mounted unconditionally for the reason the two routes above are: a
      // route is a claim about what exists rather than a permission, and
      // `POST /v1/units/{unit_id}/speaker-invitations/batches` is authorized
      // server-side per request — deny-by-default, `admin`/`coordinator` only,
      // and with the consent check repeated at dispatch and again at delivery —
      // whatever this router renders.
      { path: "invitations", element: withSuspense(<CoordinatorInvitations />) },
      // §5's "one configurable location" for the four-factor weighting, and the
      // panel `cba-phase-deferred.md` deferred in writing. Mounted
      // unconditionally for the reason the routes above are: a route is a claim
      // about what exists rather than a permission, and both
      // `GET`/`PATCH /v1/units/{unit_id}/matching-weights` are authorized
      // server-side per request — `admin`/`coordinator`, deny-by-default,
      // tenant-scoped — whatever this router renders. The page shows the
      // server's refusal rather than hiding the control.
      { path: "matching-weights", element: withSuspense(<CoordinatorMatchingWeights />) },
      // The internal CBA meeting record (migration `0034`). This route already
      // existed, pointing at a `PortalDatasetUnavailable` placeholder for the
      // legacy `/api/portals/event-coordinators/{id}/meetings` dataset; what
      // changed is that the page behind it now reads and writes a real `/v1`
      // surface, `GET`/`POST /v1/units/{unit_id}/meetings`.
      //
      // Mounted unconditionally for the reason its siblings above are: a route
      // is a claim about what exists rather than a permission. Both routes are
      // `admin`/`coordinator` server-side, authorized per request against the
      // loaded unit, whatever this router renders.
      //
      // The page is a *record*, not a booking — nothing behind it sends an
      // invitation or writes to anybody's calendar, and G5 stays deferred. The
      // page says so on screen, because a coordinator who believed otherwise
      // would stop arranging the meeting themselves.
      { path: "meetings", element: withSuspense(<CoordinatorMeetings />) },
      // The queue behind the dashboard's `pending_review_items` badge. Until
      // `GET /v1/units/{unit_id}/review-items` existed the count had no route
      // to click through to, so the coordinator home screen showed a number it
      // could not explain.
      //
      // Appended at the end of this list rather than placed beside a related
      // entry, for a merge reason rather than a taxonomic one: several tracks
      // add children here at once, and an insertion in the middle conflicts
      // with every one of them.
      //
      // Mounted unconditionally, for the reason every route above it is: a
      // route is a claim about what exists rather than a permission. Both
      // `GET /v1/units/{unit_id}/review-items` and
      // `POST /v1/review-items/{id}/decision` are authorized server-side per
      // request — `admin`/`coordinator`, deny-by-default, tenant-scoped, with
      // another tenant's unit answering `404` rather than `403` — whatever
      // this router renders. The page shows the server's refusal instead of
      // hiding the controls and implying the capability is absent.
      { path: "review-queue", element: withSuspense(<CoordinatorReviewQueue />) },
    ],
  },

  // Volunteer portal routes
  {
    path: "volunteer-portal",
    Component: VolunteerPortalLayout,
    children: [
      { index: true, element: withSuspense(<VolunteerHome />) },
      // Customer §12's Event Host intake. Mounted unconditionally like every
      // other route in this shell: the capability that gates the *API* is
      // `speaker_request_intake`, and it is on under both product scopes, so
      // there is nothing here for `whenCapable` to remove. A UI gate is not
      // authorization in any case — the server decides, per request.
      { path: "speaker-request", element: withSuspense(<VolunteerSpeakerRequest />) },
      // Customer §6 step 9: the other end of the intake above. Mounted
      // unconditionally for the same reason it is — a route is a claim about
      // what exists, not a permission. `GET .../cba/confirmed-speakers` and the
      // hand-off `POST` beside it are `admin`/`coordinator` server-side
      // whatever the router renders, and the page treats the refusal as an
      // answer rather than hiding the control.
      { path: "confirmed-speaker", element: withSuspense(<VolunteerConfirmedSpeaker />) },
      // OQ-CBA-014's read side. Mounted unconditionally like its siblings — a
      // route is a claim about what exists, not a permission. `GET
      // .../host/speaker-requests` is `volunteer`-only server-side, and the
      // page renders a coordinator's or admin's 403 as the answer it is.
      { path: "my-requests", element: withSuspense(<VolunteerMyRequests />) },
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
