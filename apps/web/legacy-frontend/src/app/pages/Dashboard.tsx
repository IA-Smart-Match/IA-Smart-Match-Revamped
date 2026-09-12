/**
 * IA admin dashboard (P8 card O4b).
 *
 * Opportunity and pipeline numbers are registered metrics read from
 * `GET /v1/units/{unit_id}/metrics`; clicking one opens the drill-down of the
 * same owning query (`GET …/metrics/{name}/drill-down`), so an aggregate and
 * the rows behind it cannot drift apart (ADR-0011 rules 3 and 4). That is what
 * O4b fences: the registered metric name and its drill-down, in place of the
 * old "active opportunities" prose and `href`-only KPI navigation (B41).
 *
 * What this card removes is the client-side *merge*, not the product surface:
 *
 * - `fetchPipeline()` + `fetchSpecialists()` and the counts derived by joining
 *   them (volunteer utilization, stage counts, match volume by event, and the
 *   per-region member-inquiry attribution built from `event_name::speaker_name`
 *   string keys). Those numbers had no owning server query and let this page
 *   disagree with Pipeline and Opportunities (B41/B42, Fix #5).
 * - the crawler live feed (B38/B39 — explicitly not to be ported).
 *
 * Calendar coverage, recovery overlays, matcher-feedback telemetry and the
 * regional pulse each read one endpoint and report what it returned; they stay.
 * Every value in them is routed through `AccountableValue` (or an explicit
 * unknown) so a measurement nobody took renders as unknown, never as zero.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import {
  Activity,
  Briefcase,
  ClipboardList,
  LogOut,
  MapPinned,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import {
  emptyFeedbackStatsSummary,
  fetchCalendarAssignments,
  fetchCalendarEvents,
  fetchFeedbackStats,
  type CalendarAssignmentSummary,
  type CalendarEventSummary,
  type FeedbackStatsSummary,
  type MetricSummary,
} from "@/lib/api";
import {
  accountableDemoMetric,
  accountableMetricFromSummary,
  MATCHING_UNAVAILABLE_REASON,
  OPPORTUNITIES_METRIC_NAME,
  PENDING_REVIEW_ITEMS_METRIC_NAME,
  unavailableMatchingMetric,
  unavailableOpportunitiesMetric,
  unavailablePendingReviewMetric,
  unavailablePipelineMetric,
} from "@/lib/metrics";
import { summarizeCalendarCoverage } from "@/lib/calendarCoverage";
import type { SignalThresholds } from "@/lib/signals";
import { type DiscoveryFeedItem } from "@/app/components/DiscoveryFeed";
import { isCapabilityEnabled } from "@/lib/productScope";
import {
  MetricDrilldownSheet,
  type AccountableMetric,
} from "@/app/components/provenance";
import { grantedPortal } from "@/app/components/PortalGate";
import { usePortalAccess } from "@/app/hooks/usePortalAccess";
import {
  METRICS_UNIT_RESOLVING_REASON,
  useUnitMetrics,
} from "@/app/hooks/useUnitMetrics";
import { DemoModeBadge } from "@/app/components/ui/DemoModeBadge";
import { Button } from "@/app/components/ui/button";
import { useSignOut } from "../hooks/useSession";
import {
  buildRegionalPulse,
  calendarReach,
  CalendarReachChart,
  FailureState,
  MatchingFeedbackPanel,
  MetricCardsRow,
  RecoveryCoverageSummary,
  RegionalPulseAndDiscovery,
} from "./DashboardSections";

const MEMBER_INQUIRY_METRIC_NAME = "pipeline_member_inquiry";

/**
 * Whether this product presents `member_inquiry` as an outcome at all.
 *
 * Read from the shared capability policy (`src/lib/productScope.ts`), the same
 * decision `PipelineFunnelTiles` consults — the headline card and the funnel
 * tile are one claim wearing two layouts, and gating only the tile would leave
 * the larger version of the claim on the same screen.
 *
 * The metric itself stays registered, read, and stored; what is withheld is the
 * presentation. Customer §4 and §20 remove chapter membership, so a CBA user has
 * no outcome this number could describe.
 */
const OFFERS_MEMBER_INQUIRY = isCapabilityEnabled("member_inquiry_narrative");

/**
 * Why a per-region member-inquiry count is not shown.
 *
 * The old tile counted it in the browser by joining calendar assignments to
 * legacy pipeline rows on `event_name::speaker_name`. The registered
 * `pipeline_member_inquiry` metric is unit-scoped, not region-scoped, so there
 * is no server query that answers this question yet.
 */
const REGION_MEMBER_INQUIRY_UNKNOWN_REASON =
  "No region-scoped registered metric exists: `pipeline_member_inquiry` is scoped to the organizational unit, and this page no longer attributes pipeline rows to regions in the browser.";

/**
 * Why the calendar-derived rows on this page can be unknown.
 *
 * `/api/calendar/*` are legacy routes that the current API does not serve —
 * the repository's own performance baseline records both as 404
 * (`docs/plans/perf-baseline-828.md`). Until unit-scoped event endpoints
 * exist (S3–S5; `services/api/smartmatch_api/routers/events.py` declares no
 * handlers yet), coverage is genuinely unmeasured, and this dashboard says
 * so rather than reporting zero uncovered windows.
 */
const CALENDAR_FEED_UNAVAILABLE_REASON =
  "The calendar feed is unavailable: `/api/calendar/events` is a retired legacy route and no unit-scoped event endpoint exists yet (S3–S5), so coverage is unknown rather than zero.";

/**
 * Presentation cut points for the review queue.
 *
 * These are *display* thresholds for the pilot surface, not a measured
 * standard: no stakeholder has set a service level for review latency. They
 * are stated in `rationale` and shown with the row precisely so nobody reads
 * the colour as a finding about the programme.
 */
const REVIEW_QUEUE_THRESHOLDS: SignalThresholds = {
  criticalAtOrAbove: 20,
  watchAtOrAbove: 1,
  rationale:
    "Display rule for this pilot surface: any pending item is amber, 20 or more is red. Not a stakeholder-approved service level.",
};

/** Presentation cut points for uncovered windows. Same caveat as the review queue. */
const UNCOVERED_WINDOW_THRESHOLDS: SignalThresholds = {
  criticalAtOrAbove: 5,
  watchAtOrAbove: 1,
  rationale:
    "Display rule for this pilot surface: any uncovered window is amber, 5 or more is red. Not a stakeholder-approved service level.",
};

/**
 * Reads a human message off a thrown value without assuming a specific error
 * shape. Tolerates plain Error instances, the API layer's ApiRequestError,
 * and anything else that merely looks like an error.
 */
function getErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === "object") {
    const maybeMessage = (err as { message?: unknown }).message;
    if (typeof maybeMessage === "string" && maybeMessage.trim().length > 0) {
      return maybeMessage;
    }
  }
  if (typeof err === "string" && err.trim().length > 0) {
    return err;
  }
  return fallback;
}


export function Dashboard() {
  const navigate = useNavigate();
  const signOut = useSignOut();

  function handleLogout() {
    // Drops the browser-held bearer token and re-resolves identity against
    // `GET /v1/me`. There is no client-side session object left to clear.
    signOut();
    navigate("/login");
  }

  const [calendarEvents, setCalendarEvents] = useState<CalendarEventSummary[]>([]);
  const [calendarAssignments, setCalendarAssignments] = useState<CalendarAssignmentSummary[]>([]);
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStatsSummary>(
    emptyFeedbackStatsSummary(),
  );
  const [calendarAvailable, setCalendarAvailable] = useState(false);
  const [assignmentsAvailable, setAssignmentsAvailable] = useState(false);
  const [feedbackAvailable, setFeedbackAvailable] = useState(false);
  const [isMockData, setIsMockData] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadFailed(false);
    setError(null);

    function resetToEmpty() {
      setCalendarEvents([]);
      setCalendarAssignments([]);
      setFeedbackStats(emptyFeedbackStatsSummary());
      setCalendarAvailable(false);
      setAssignmentsAvailable(false);
      setFeedbackAvailable(false);
      setIsMockData(false);
    }

    async function load() {
      try {
        const [calendarResult, assignmentResult, feedbackResult] = await Promise.allSettled([
          fetchCalendarEvents(),
          fetchCalendarAssignments(),
          fetchFeedbackStats(),
        ]);

        if (!active) {
          return;
        }

        let anyMock = false;

        // The calendar feed reads retired `/api/calendar/*` routes, while the
        // registered metrics come from `/v1/units/{unit_id}/metrics` — two
        // independent sources. A 404 on the retired one used to blank the
        // whole page, which withheld the accountable metrics that *did*
        // answer and left the coordinator with nothing at all.
        //
        // So a calendar failure now degrades only the calendar-derived
        // sections. That is not a fixture fallback: every one of those values
        // goes to `unknown` with its reason (ADR-0011 rule 1), and the header
        // says the feed is unavailable. The registered metrics render as
        // measured.
        if (calendarResult.status === "fulfilled") {
          setCalendarEvents(calendarResult.value.data);
          setCalendarAvailable(true);
          if (calendarResult.value.isMockData) anyMock = true;
        } else {
          setCalendarEvents([]);
          setCalendarAvailable(false);
        }

        if (assignmentResult.status === "fulfilled") {
          setCalendarAssignments(assignmentResult.value.data);
          setAssignmentsAvailable(true);
          if (assignmentResult.value.isMockData) anyMock = true;
        } else {
          // Assignment overlays are supplementary — keep the page honest and
          // surface a warning instead of fabricating overlays.
          setCalendarAssignments([]);
          setAssignmentsAvailable(false);
        }

        if (feedbackResult.status === "fulfilled") {
          setFeedbackStats(feedbackResult.value.data);
          setFeedbackAvailable(true);
          if (feedbackResult.value.isMockData) anyMock = true;
        } else {
          setFeedbackStats(emptyFeedbackStatsSummary());
          setFeedbackAvailable(false);
        }

        setIsMockData(anyMock);

        const warnings = [];
        if (calendarResult.status === "rejected") {
          warnings.push(CALENDAR_FEED_UNAVAILABLE_REASON);
        }
        if (assignmentResult.status === "rejected") {
          warnings.push(
            `Assignment overlays are unavailable: ${getErrorMessage(assignmentResult.reason, "Request failed.")}`,
          );
        }
        if (feedbackResult.status === "rejected") {
          warnings.push(
            `Feedback optimizer stats are unavailable: ${getErrorMessage(feedbackResult.reason, "Request failed.")}`,
          );
        }
        setError(warnings.length ? warnings.join(" ") : null);
      } catch (err: unknown) {
        if (active) {
          resetToEmpty();
          setLoadFailed(true);
          setError(getErrorMessage(err, "Failed to load dashboard data."));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      active = false;
    };
  }, [reloadToken]);

  // The unit this screen is about is the one the **server** granted this
  // account — `PortalDescriptor.default_unit_id` off `GET /v1/me/portals` —
  // resolved here because this page is what holds the grant.
  //
  // This page *is* a portal home screen, appearances notwithstanding: it sits
  // under the pathless `Layout` route rather than a portal shell, but
  // `_PORTAL_FOR_ROLE` in `services/api/smartmatch_api/routers/portals.py`
  // maps the stored `admin` role to the portal `admin` with
  // `home_path: "/dashboard"`, and `PortalGate` links a signed-in account
  // straight here. So the unit is resolved the way every other portal screen
  // resolves it, and not from a build variable.
  //
  // It used to be `getConfiguredUnitId()` inside `useUnitMetrics`, the
  // `VITE_SMARTMATCH_UNIT_ID` build variable that the pilot VM's bundle is
  // built without. On that deployment every registered metric here rendered
  // unknown with a reason instructing the reader to set a build variable —
  // which they cannot do, and which was not the true cause anyway.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "admin");
  const unitId = grant?.default_unit_id ?? null;
  // `grantedPortal()` returns `null` both while `GET /v1/me/portals` is in
  // flight and when the answer carried no grant. Only this page can tell those
  // two apart, so only this page may say which one the reader is looking at.
  const unitResolving = portalAccess.status === "loading";

  const {
    metricsByName,
    status: metricsStatus,
    loadError: metricsLoadError,
    metricsUnavailableReason,
    metricsNoUnitReason,
    openDrilldown,
    drilldownOpen,
    setDrilldownOpen,
    drilldownLoading,
    drilldownError,
    drilldown,
  } = useUnitMetrics(unitId, reloadToken);

  const unavailableReason =
    metricsStatus === "unavailable"
      ? (metricsLoadError ?? metricsUnavailableReason)
      : metricsStatus === "loading"
        ? "Loading registered metrics…"
        : metricsStatus === "idle"
          ? // Nothing was asked for. Not a failure, and — ADR-0011 rule 1 —
            // emphatically not a zero: every consumer of `unavailableReason`
            // wraps it in an explicit unknown.
            unitResolving
            ? METRICS_UNIT_RESOLVING_REASON
            : metricsNoUnitReason
          : "This metric is not present in the unit's register.";

  /** Wraps one registered summary, or an explicit unknown when it is absent. */
  function registeredMetric(
    metricName: string,
    fallback: (reason: string) => AccountableMetric,
  ): { metric: AccountableMetric; summary: MetricSummary | undefined } {
    const summary = metricsByName[metricName];
    if (!summary) {
      return { metric: fallback(unavailableReason), summary: undefined };
    }
    return {
      metric: accountableMetricFromSummary(summary, {
        provenance: "observed",
        onOpenDrilldown: () => {
          void openDrilldown(metricName);
        },
      }),
      summary,
    };
  }

  const opportunities = registeredMetric(OPPORTUNITIES_METRIC_NAME, (reason) =>
    unavailableOpportunitiesMetric(reason),
  );
  const memberInquiry = registeredMetric(MEMBER_INQUIRY_METRIC_NAME, (reason) =>
    unavailablePipelineMetric(MEMBER_INQUIRY_METRIC_NAME, reason),
  );
  const pendingReview = registeredMetric(PENDING_REVIEW_ITEMS_METRIC_NAME, (reason) =>
    unavailablePendingReviewMetric(reason),
  );

  /** The card caption: the register's own definition, or why there is none. */
  function caption(summary: MetricSummary | undefined, fallbackName: string): string {
    if (!summary) {
      return `Registered metric \`${fallbackName}\` — ${unavailableReason}`;
    }
    if (summary.value === null) {
      return summary.unknown_reason ?? summary.definition;
    }
    return summary.definition;
  }

  const demoProvenance = isMockData ? ("synthetic" as const) : ("observed" as const);
  const calendarProvenance = calendarAvailable ? demoProvenance : ("synthetic" as const);
  const assignmentProvenance = assignmentsAvailable ? demoProvenance : ("synthetic" as const);
  const feedbackProvenance = feedbackAvailable ? demoProvenance : ("synthetic" as const);

  const calendarCoverage = summarizeCalendarCoverage(
    calendarEvents.map((event) => event.coverage_status),
  );
  const coveredCalendarCount = calendarCoverage.covered;
  const unknownCalendarCoverageCount = calendarCoverage.unknown;
  const openCalendarCount = calendarCoverage.explicitlyOpen;
  const calendarCoverageFullyResolved = calendarCoverage.fullyResolved;

  const upcomingEventsMetric = accountableDemoMetric(
    "Upcoming events",
    "Scheduled windows returned by the calendar feed for this dataset.",
    calendarAvailable ? calendarEvents.length : null,
    {
      provenance: calendarProvenance,
      unknownReason: "The calendar feed is unavailable, so the number of windows is unknown.",
    },
  );
  const coveredEventsMetric = accountableDemoMetric(
    "Covered events",
    "Calendar windows the feed reports as covered.",
    calendarAvailable ? coveredCalendarCount : null,
    {
      provenance: calendarProvenance,
      unknownReason: "The calendar feed is unavailable, so coverage is unknown.",
    },
  );
  const openEventsMetric = accountableDemoMetric(
    "Open events",
    "Calendar windows the feed explicitly reports as partially covered or needing coverage.",
    calendarAvailable && calendarCoverageFullyResolved ? openCalendarCount : null,
    {
      provenance: calendarProvenance,
      // A row with coverage_status=unknown cannot safely be counted as either
      // open or covered. Propagating that uncertainty prevents the discovery
      // feed from turning missing evidence into an amber/red operational alert.
      unknownReason: !calendarAvailable
        ? "The calendar feed is unavailable, so open windows are unknown."
        : `${unknownCalendarCoverageCount} calendar window${unknownCalendarCoverageCount === 1 ? " has" : "s have"} unresolved coverage, so the total number of open windows is unknown.`,
    },
  );
  const coverageRateMetric = accountableDemoMetric(
    "Coverage rate",
    "Covered calendar windows divided by all calendar windows.",
    calendarAvailable ? calendarCoverage.coverageRatio : null,
    {
      provenance: calendarProvenance,
      unknownReason:
        !calendarAvailable
          ? "The calendar feed is unavailable, so the coverage rate is unknown."
          : calendarEvents.length === 0
            ? "No calendar windows yet, so there is no denominator for a coverage rate."
            : `${unknownCalendarCoverageCount} calendar window${unknownCalendarCoverageCount === 1 ? " has" : "s have"} unresolved coverage, so the coverage rate is unknown.`,
    },
  );

  const knownFatigueAssignments = calendarAssignments
    .map((assignment) => assignment.volunteer_fatigue)
    .filter((value): value is number => value !== null);
  const averageFatigueMetric = accountableDemoMetric(
    "Average volunteer fatigue",
    "Mean fatigue score from calendar assignment overlays.",
    assignmentsAvailable && knownFatigueAssignments.length > 0
      ? knownFatigueAssignments.reduce((sum, value) => sum + value, 0) /
          knownFatigueAssignments.length
      : null,
    {
      provenance: assignmentProvenance,
      unknownReason:
        assignmentsAvailable && calendarAssignments.length === 0
          ? "No assignment overlays recorded yet."
          : assignmentsAvailable
            ? "No overlay in this batch reported a fatigue signal."
            : "Assignment overlays are unavailable.",
    },
  );
  const restRecommendedMetric = accountableDemoMetric(
    "Rest recommended count",
    "Volunteers flagged for recovery in assignment overlays.",
    assignmentsAvailable
      ? calendarAssignments.filter(
          (assignment) => assignment.recovery_status === "Rest Recommended",
        ).length
      : null,
    {
      provenance: assignmentProvenance,
      unknownReason: "Assignment overlays are unavailable.",
    },
  );

  const feedbackRowsMetric = accountableDemoMetric(
    "Feedback rows",
    "Coordinator accept/decline submissions captured for matcher tuning.",
    feedbackAvailable ? feedbackStats.total_feedback : null,
    { provenance: feedbackProvenance, unknownReason: "Feedback optimizer stats are unavailable." },
  );
  const feedbackAcceptanceMetric = accountableDemoMetric(
    "Feedback acceptance rate",
    "Accepted decisions divided by all coordinator feedback rows.",
    feedbackAvailable && feedbackStats.total_feedback !== null && feedbackStats.total_feedback > 0
      ? feedbackStats.acceptance_rate
      : null,
    {
      provenance: feedbackProvenance,
      unknownReason:
        feedbackAvailable && feedbackStats.total_feedback === 0
          ? "No coordinator feedback submitted yet, so there is no rate to report."
          : "Feedback optimizer stats are unavailable.",
    },
  );
  const feedbackPainMetric = accountableDemoMetric(
    "Matcher pain score",
    "How much correction pressure the matcher is under from recent feedback.",
    feedbackAvailable ? feedbackStats.pain_score : null,
    { provenance: feedbackProvenance, unknownReason: "Feedback optimizer stats are unavailable." },
  );
  const feedbackMembershipMetric = accountableDemoMetric(
    "Membership interest rate",
    "Follow-through signals attributed to coordinator feedback.",
    feedbackAvailable && feedbackStats.total_feedback !== null && feedbackStats.total_feedback > 0
      ? feedbackStats.membership_interest_rate
      : null,
    {
      provenance: feedbackProvenance,
      unknownReason:
        feedbackAvailable && feedbackStats.total_feedback === 0
          ? "No coordinator feedback submitted yet, so there is no rate to report."
          : "Feedback optimizer stats are unavailable.",
    },
  );

  const reachTrend = calendarReach(calendarEvents);
  const leadAdjustment = feedbackAvailable
    ? (feedbackStats.recommended_adjustments[0] ?? null)
    : null;
  const regionalPulse = buildRegionalPulse(calendarEvents, calendarAssignments);
  const regionNeedingCoverage =
    regionalPulse
      .filter((row) => row.openCount > 0)
      .sort(
        (left, right) => right.openCount - left.openCount || right.eventCount - left.eventCount,
      )[0] ?? null;
  const strongestCoverageRegion =
    regionalPulse
      .filter((row) => row.eventCount > 0 && row.coveragePercent !== null)
      .sort(
        (left, right) =>
          (right.coveragePercent ?? 0) - (left.coveragePercent ?? 0) ||
          right.uniqueVolunteers - left.uniqueVolunteers,
      )[0] ?? null;

  const memberInquirySummary = memberInquiry.summary;

  /**
   * Discovery feed rows.
   *
   * Every row is a registered metric or an explicit unknown, and the
   * red/yellow/green tone is computed from that value by
   * `toneForBacklog` — never chosen here. The threshold rules are named in
   * `rationale` and printed with the row, so the colour is something a
   * viewer can check rather than a score the dashboard asserted.
   *
   * Rows that report a *state* rather than a backlog carry
   * `thresholds: null` and stay neutral: grading "how many opportunities is
   * a good number" is a stakeholder decision nobody has made, and guessing
   * it here would be exactly the invented score this feed exists to avoid.
   */
  const discoveryFeed: DiscoveryFeedItem[] = [
    {
      icon: ClipboardList,
      title: "Review queue",
      metric: pendingReview.metric,
      thresholds: REVIEW_QUEUE_THRESHOLDS,
      detail: caption(pendingReview.summary, PENDING_REVIEW_ITEMS_METRIC_NAME),
    },
    {
      icon: MapPinned,
      title: "Uncovered calendar windows",
      metric: openEventsMetric,
      thresholds: UNCOVERED_WINDOW_THRESHOLDS,
      detail: calendarAvailable
        ? calendarCoverageFullyResolved
          ? "Scheduled windows the calendar feed explicitly reports as partially covered or needing coverage."
          : `${unknownCalendarCoverageCount} window${unknownCalendarCoverageCount === 1 ? " has" : "s have"} unresolved coverage, so this backlog cannot be graded.`
        : CALENDAR_FEED_UNAVAILABLE_REASON,
    },
    {
      icon: Briefcase,
      title: "Opportunities in the register",
      metric: opportunities.metric,
      thresholds: null,
      detail: caption(opportunities.summary, OPPORTUNITIES_METRIC_NAME),
    },
    ...(OFFERS_MEMBER_INQUIRY
      ? [
          {
            icon: Activity,
            title: "Member inquiry",
            metric: memberInquiry.metric,
            thresholds: null,
            detail: caption(memberInquirySummary, MEMBER_INQUIRY_METRIC_NAME),
          },
        ]
      : []),
    {
      icon: Sparkles,
      title: "Matching recommendations",
      metric: unavailableMatchingMetric(),
      thresholds: null,
      detail: MATCHING_UNAVAILABLE_REASON,
    },
  ];

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="h-10 w-48 animate-pulse rounded bg-muted" />
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <div
              key={index}
              className="h-36 animate-pulse rounded-2xl border border-border bg-card shadow-sm"
            />
          ))}
        </div>
        <div className="h-80 animate-pulse rounded-2xl border border-border bg-card shadow-sm" />
      </div>
    );
  }

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-semibold text-foreground">
          Dashboard{isMockData && <DemoModeBadge />}
        </h1>
        <p className="mt-1 text-muted-foreground">
          Opportunity and pipeline numbers come from the registered metrics API; coverage and
          feedback sections report what their own feed returned.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setReloadToken((token) => token + 1)}
          aria-label="Reload dashboard data"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
        <button
          type="button"
          onClick={handleLogout}
          aria-label="Log out and return to portal login"
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground shadow-sm transition hover:border-border hover:bg-muted"
        >
          <LogOut className="h-4 w-4" aria-hidden />
          Log out
        </button>
      </div>
    </div>
  );

  if (loadFailed) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        {header}
        <FailureState
          title="The dashboard could not be loaded"
          message={error ?? "Failed to load dashboard data."}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {header}

      {metricsStatus === "unavailable" ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
          <p className="text-sm font-semibold text-amber-900">
            Registered metrics could not be read
          </p>
          <p className="mt-1 text-sm text-amber-800">{unavailableReason}</p>
          <p className="mt-2 text-sm text-amber-800">
            Opportunity and pipeline values stay unknown. Unknown is not zero, and this dashboard
            will not fall back to a locally merged number.
          </p>
        </div>
      ) : null}

      {error ? (
        <FailureState
          title="Some dashboard data is unavailable"
          message={error}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      ) : null}

      <MetricCardsRow
        opportunitiesMetric={opportunities.metric}
        opportunitiesCaption={caption(opportunities.summary, OPPORTUNITIES_METRIC_NAME)}
        offersMemberInquiry={OFFERS_MEMBER_INQUIRY}
        memberInquiryMetric={memberInquiry.metric}
        memberInquiryCaption={caption(memberInquiry.summary, MEMBER_INQUIRY_METRIC_NAME)}
        upcomingEventsMetric={upcomingEventsMetric}
        unitId={unitId}
        unitResolving={unitResolving}
        reloadToken={reloadToken}
      />

      <RecoveryCoverageSummary
        coveredEventsMetric={coveredEventsMetric}
        coverageRateMetric={coverageRateMetric}
        openEventsMetric={openEventsMetric}
        averageFatigueMetric={averageFatigueMetric}
        restRecommendedMetric={restRecommendedMetric}
      />

      <MatchingFeedbackPanel
        feedbackRowsMetric={feedbackRowsMetric}
        feedbackAcceptanceMetric={feedbackAcceptanceMetric}
        feedbackPainMetric={feedbackPainMetric}
        feedbackMembershipMetric={feedbackMembershipMetric}
        feedbackAvailable={feedbackAvailable}
        feedbackStats={feedbackStats}
        leadAdjustment={leadAdjustment}
      />

      <RegionalPulseAndDiscovery
        regionalPulse={regionalPulse}
        discoveryFeed={discoveryFeed}
        regionMemberInquiryUnknownReason={REGION_MEMBER_INQUIRY_UNKNOWN_REASON}
      />

      <CalendarReachChart reachTrend={reachTrend} />

      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <div className="mb-6 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-semibold text-foreground">Top Recommended Matches</h3>
        </div>

        <div className="rounded-2xl border border-dashed border-border bg-muted p-8 text-center text-muted-foreground">
          <p className="text-sm font-semibold text-foreground">Matching unavailable</p>
          <p className="mt-2 text-sm leading-6">{MATCHING_UNAVAILABLE_REASON}</p>
          <p className="mt-2 text-sm leading-6">
            Ranked recommendations and match scores stay off this dashboard until gate G1 closes.
          </p>
        </div>
      </div>

      <MetricDrilldownSheet
        open={drilldownOpen}
        onOpenChange={setDrilldownOpen}
        loading={drilldownLoading}
        drilldown={drilldown}
        error={drilldownError}
      />
    </div>
  );
}
