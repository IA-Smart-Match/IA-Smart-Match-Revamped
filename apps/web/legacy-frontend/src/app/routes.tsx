import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, createBrowserRouter, useSearchParams, type RouteObject } from "react-router";
import { StudentLayout } from "./components/StudentLayout";
import { CoordinatorPortalLayout } from "./components/CoordinatorPortalLayout";
import { VolunteerPortalLayout } from "./components/VolunteerPortalLayout";
import { RouteFallback } from "./components/RouteFallback";
import { NotFound } from "./components/NotFound";
import { LEGACY_ROUTE_REDIRECTS } from "./legacyRedirects";
import { Home } from "./pages/Home";
import { LoginPage } from "./pages/LoginPage";

// Portal pages are code-split per route so the initial bundle only carries the
// landing/login flow. Each import below becomes its own chunk.

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
// Customer §12's read side for the Connector: the Speaker Requests event hosts
// have filed with this unit. `GET /v1/units/{unit_id}/speaker-requests`,
// `admin`/`coordinator` server-side.
const CoordinatorSpeakerRequests = lazy(() =>
  import("./pages/coordinator/CoordinatorSpeakerRequests").then((m) => ({
    default: m.CoordinatorSpeakerRequests,
  })),
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
// The run a submitted match produced, read back with its per-factor
// explanation. Mounted by the `match-runs` route's `?run=` detail state — the
// successor to the retired `/ai-matching?run=` address, whose redirect forwards
// the parameter.
const AIMatching = lazy(() =>
  import("./pages/AIMatching").then((m) => ({ default: m.AIMatching })),
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
const VolunteerSpeakerRequest = lazy(() =>
  import("./pages/volunteer/VolunteerSpeakerRequest").then((m) => ({
    default: m.VolunteerSpeakerRequest,
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
 * with no Suspense boundary of its own, so each lazy page is wrapped locally
 * here (via `element:`) rather than relying on a boundary higher in the tree.
 */
function withSuspense(node: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{node}</Suspense>;
}

/**
 * The match-runs address has two states: the submission form, and — when a
 * `?run={id}` parameter names a persisted run — the shortlist that run
 * produced, which `pages/AIMatching.tsx` renders.
 *
 * This is the successor to the retired `/ai-matching?run={id}` address: the
 * redirect table forwards `run` onto this route, so a bookmarked shortlist
 * still opens the run it named. An empty or whitespace-only parameter is not
 * a run id and selects the form, same as no parameter.
 */
function MatchRunsOrShortlist() {
  const [searchParams] = useSearchParams();
  const run = searchParams.get("run");
  return run !== null && run.trim().length > 0 ? <AIMatching /> : <CoordinatorMatchRuns />;
}

/**
 * A retired address whose successor still reads some of its query string.
 *
 * `<Navigate to>` alone would drop the parameters, and for `/ai-matching` the
 * `?run=` parameter *is* the address: it names the persisted run the shortlist
 * page reads. Entries that declare `forwardParams` render this instead, which
 * copies exactly the named parameters — nothing else — onto the destination.
 */
function LegacyRouteRedirect({
  to,
  forwardParams,
}: {
  to: string;
  forwardParams?: readonly string[];
}) {
  const [searchParams] = useSearchParams();
  const forwarded = new URLSearchParams();
  for (const name of forwardParams ?? []) {
    const value = searchParams.get(name);
    if (value !== null && value.trim().length > 0) {
      forwarded.set(name, value.trim());
    }
  }
  const query = forwarded.toString();
  return <Navigate to={query === "" ? to : `${to}?${query}`} replace />;
}

/**
 * The retired addresses, turned into route objects.
 *
 * `replace` so the retired path does not sit in the history stack: pressing
 * Back onto it would only redirect forward again and trap the reader. The
 * table itself is `app/legacyRedirects.ts`, which exists as a separate,
 * JSX-free module so `tests/legacyRedirects.test.ts` can import and check it —
 * see that file's header for why the mapping is data rather than ten elements
 * scattered through this one.
 *
 * One of these deserves a note. `/outreach` was the legacy admin surface for
 * *cold* contact of people who never consented, and it was gated behind
 * `cold_unknown_contact_outreach` + `external_speaker_acquisition`, both out
 * of scope (customer §20). It is not restored here. The address now lands on
 * the coordinator portal's outreach page, which is a different thing sharing a
 * word: consented `/v1` sends whose consent is re-checked at delivery. The URL
 * survives; the retired capability does not, and no route in this file offers
 * it any more.
 */
const legacyRedirectRoutes: RouteObject[] = LEGACY_ROUTE_REDIRECTS.map(
  ({ from, to, forwardParams }) => ({
    path: from,
    element:
      forwardParams === undefined ? (
        <Navigate to={to} replace />
      ) : (
        <LegacyRouteRedirect to={to} forwardParams={forwardParams} />
      ),
  }),
);

export const router = createBrowserRouter([
  // Public routes (no sidebar) — kept static: this is the first code an
  // unauthenticated visitor needs, and lazy-loading it would add a fetch
  // round trip before anything can render at all.
  { path: "/", Component: Home, errorElement: <NotFound /> },
  { path: "/login", Component: LoginPage, errorElement: <NotFound /> },

  // Student portal routes
  {
    path: "student-portal",
    Component: StudentLayout,
    errorElement: <NotFound />,
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

  // The Connector Dashboard — one shell for both stored Speaker Connector
  // roles, `coordinator` and `admin`. The separate admin shell this replaced
  // (`components/Layout.tsx`) is deleted; its eight addresses are in
  // `legacyRedirectRoutes` above.
  //
  // Every child is mounted unconditionally, for the reason the shell's own
  // header gives at length: a route is a claim about what exists rather than a
  // permission. Each page behind one is authorized server-side per request —
  // deny-by-default, tenant-scoped — whatever this router renders, and each
  // shows the server's refusal as the answer it is rather than hiding its
  // controls and implying the capability is absent.
  {
    path: "coordinator-portal",
    Component: CoordinatorPortalLayout,
    errorElement: <NotFound />,
    children: [
      { index: true, element: withSuspense(<CoordinatorHome />) },
      { path: "speaker-requests", element: withSuspense(<CoordinatorSpeakerRequests />) },
      // The queue behind the home screen's `pending_review_items` badge and
      // the sidebar's Review queue count. `GET /v1/units/{unit_id}/review-items`
      // has existed since before anything linked to it.
      { path: "review-queue", element: withSuspense(<CoordinatorReviewQueue />) },
      // One events page. The Connector's create/edit/publish controls and the
      // per-event feedback QR live here alongside the unit's listing, rather
      // than on a second page in a second shell — both surfaces were
      // `admin`+`coordinator` server-side all along.
      { path: "events", element: withSuspense(<CoordinatorEvents />) },
      // Card B24's replacement: the Connector submits a real match run against
      // a filed Speaker Request. `POST /v1/units/{unit_id}/match-runs`.
      // The same address with a `?run={id}` is the run's detail state — the
      // shortlist viewer the retired `/ai-matching` page held. One address,
      // two states: the parameter selects which page mounts.
      {
        path: "match-runs",
        element: withSuspense(<MatchRunsOrShortlist />),
      },
      // §13's compose step, reached from a shortlist link carrying `?run={id}`.
      // `POST /v1/units/{unit_id}/speaker-invitations/batches` repeats the
      // consent check at dispatch and again at delivery.
      { path: "invitations", element: withSuspense(<CoordinatorInvitations />) },
      // The internal CBA meeting record (migration `0034`), `GET`/`POST
      // /v1/units/{unit_id}/meetings`. A *record*, not a booking — nothing
      // behind it sends an invitation or writes to anybody's calendar, and the
      // page says so on screen.
      { path: "meetings", element: withSuspense(<CoordinatorMeetings />) },
      // Customer §13's roster of professionals this unit knows.
      { path: "speaker-contacts", element: withSuspense(<CoordinatorSpeakerContacts />) },
      // §16's Connector read of student feedback, aggregate-only per
      // OQ-CBA-003 part 1. `GET .../speakers/{speaker_id}/feedback-summary` is
      // `admin`/`coordinator` server-side whatever the router renders, and
      // there is deliberately no route listing individual ratings for a later
      // page to reach for.
      { path: "speaker-feedback", element: withSuspense(<CoordinatorSpeakerFeedback />) },
      // The consented outreach record over `contact_channel`. Deliberately not
      // capability-gated: this is the preserved path, distinct from the retired
      // cold-contact page that once held the `/outreach` address.
      { path: "outreach", element: withSuspense(<CoordinatorOutreach />) },
      // §5's "one configurable location" for the four-factor weighting. Both
      // `GET`/`PATCH /v1/units/{unit_id}/matching-weights` are
      // `admin`/`coordinator`, deny-by-default and tenant-scoped; the page
      // shows the server's refusal rather than hiding the control.
      { path: "matching-weights", element: withSuspense(<CoordinatorMatchingWeights />) },
    ],
  },

  // Event Host portal routes
  {
    path: "volunteer-portal",
    Component: VolunteerPortalLayout,
    errorElement: <NotFound />,
    children: [
      { index: true, element: withSuspense(<VolunteerHome />) },
      // Customer §12's Event Host intake. Mounted unconditionally like every
      // other route in this shell: the capability that gates the *API* is
      // `speaker_request_intake`, and it is on under both product scopes. A UI
      // gate is not authorization in any case — the server decides, per request.
      { path: "speaker-request", element: withSuspense(<VolunteerSpeakerRequest />) },
      // OQ-CBA-014's read side. `GET .../host/speaker-requests` is
      // `volunteer`-only server-side, and the page renders a coordinator's or
      // admin's 403 as the answer it is.
      { path: "my-requests", element: withSuspense(<VolunteerMyRequests />) },
      { path: "profile", element: withSuspense(<VolunteerProfile />) },
    ],
  },

  // Every address the consolidation retired, pointed at its successor.
  ...legacyRedirectRoutes,

  // Anything else. An honest 404 rather than react-router's stock
  // "Unexpected Application Error!" with a stack trace — see `NotFound`.
  { path: "*", element: <NotFound /> },
]);
