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
import { Link, useNavigate } from "react-router";
import {
  Activity,
  AlertTriangle,
  BellRing,
  Briefcase,
  CalendarDays,
  ClipboardList,
  LogOut,
  MapPinned,
  MessageSquareHeart,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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
import {
  DiscoveryFeed,
  type DiscoveryFeedItem,
} from "@/app/components/DiscoveryFeed";
import { MetricCard } from "@/app/components/MetricCard";
import { PipelineFunnelTiles } from "@/app/components/PipelineFunnelTiles";
import {
  AccountableValue,
  MetricDrilldownSheet,
  MetricValueDisplay,
  unknownValue,
  type AccountableMetric,
} from "@/app/components/provenance";
import { useUnitMetrics } from "@/app/hooks/useUnitMetrics";
import { DemoModeBadge } from "@/app/components/ui/DemoModeBadge";
import { Button } from "@/app/components/ui/button";
import { useSignOut } from "../hooks/useSession";

const MEMBER_INQUIRY_METRIC_NAME = "pipeline_member_inquiry";

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

function FailureState({
  title = "We couldn't load this data",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
        <AlertTriangle className="h-5 w-5 text-red-600" />
      </div>
      <p className="mt-3 text-sm font-semibold text-red-800">{title}</p>
      <p className="mt-1 text-sm text-red-700">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function monthLabel(dateString: string): string {
  const [year, month, day] = dateString.split("-").map(Number);
  const date =
    [year, month, day].every((part) => Number.isFinite(part) && !Number.isNaN(part))
      ? new Date(year, month - 1, day)
      : new Date(dateString);
  if (Number.isNaN(date.getTime())) {
    return dateString;
  }
  return date.toLocaleDateString("en-US", { month: "short" });
}

type RegionalPulseRow = {
  region: string;
  eventCount: number;
  coveredCount: number;
  openCount: number;
  unknownCount: number;
  assignmentCount: number;
  uniqueVolunteers: number;
  coveragePercent: number | null;
  detail: string;
};

function calendarReach(records: CalendarEventSummary[]) {
  const byMonth = new Map<string, { windows: number; covered: number }>();
  for (const record of records) {
    const label = monthLabel(record.event_date);
    const current = byMonth.get(label) ?? { windows: 0, covered: 0 };
    byMonth.set(label, {
      windows: current.windows + 1,
      covered: current.covered + (record.coverage_status === "covered" ? 1 : 0),
    });
  }
  return Array.from(byMonth.entries()).map(([month, value]) => ({
    month,
    windows: value.windows,
    covered: value.covered,
  }));
}

/**
 * Rolls calendar windows and assignment overlays up by region.
 *
 * Both inputs come from the same calendar feed, so every count here is a count
 * of rows that feed actually returned — no cross-source join. `coveragePercent`
 * is `null` (not 0) for a region with no scheduled windows, because a coverage
 * ratio with no denominator is unknown, not zero percent.
 *
 * There is deliberately no "workload %" here. The tile used to divide overlay
 * rows by `eventCount * 3` — an invented capacity of three volunteers per
 * window that no contract, registry, or stakeholder ever set — and render the
 * quotient as a percentage. That is a heuristic score wearing an observed
 * measurement's clothes (DESIGN.md §1.1, ADR-0011), so it is gone rather than
 * relabelled; the honest counts it was built from are shown instead.
 */
function buildRegionalPulse(
  calendarEvents: CalendarEventSummary[],
  calendarAssignments: CalendarAssignmentSummary[],
): RegionalPulseRow[] {
  const regions = Array.from(
    new Set(
      [
        ...calendarEvents.map((event) => event.region),
        ...calendarAssignments.map((assignment) => assignment.region),
      ]
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  );

  return regions
    .map((region) => {
      const eventsInRegion = calendarEvents.filter((event) => event.region === region);
      const coverage = summarizeCalendarCoverage(
        eventsInRegion.map((event) => event.coverage_status),
      );
      const assignmentsInRegion = calendarAssignments.filter(
        (assignment) => assignment.region === region,
      );
      const eventCount = eventsInRegion.length;
      const assignmentCount = assignmentsInRegion.length;
      const uniqueVolunteers = new Set(
        assignmentsInRegion.map((assignment) => assignment.volunteer_name),
      ).size;
      const coveragePercent =
        coverage.coverageRatio === null
          ? null
          : Math.round(coverage.coverageRatio * 100);
      const detail = `${eventCount} calendar window${eventCount === 1 ? "" : "s"} and ${assignmentCount} assignment overlay${assignmentCount === 1 ? "" : "s"}.${coverage.unknown ? ` ${coverage.unknown} window${coverage.unknown === 1 ? " has" : "s have"} unresolved coverage.` : ""}`;

      return {
        region,
        eventCount,
        coveredCount: coverage.covered,
        openCount: coverage.explicitlyOpen,
        unknownCount: coverage.unknown,
        assignmentCount,
        uniqueVolunteers,
        coveragePercent,
        detail,
      };
    })
    .sort((left, right) => {
      if (right.eventCount !== left.eventCount) {
        return right.eventCount - left.eventCount;
      }
      if (right.assignmentCount !== left.assignmentCount) {
        return right.assignmentCount - left.assignmentCount;
      }
      return left.region.localeCompare(right.region);
    })
    .slice(0, 6);
}

function formatFactorName(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
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

  const {
    metricsByName,
    status: metricsStatus,
    loadError: metricsLoadError,
    metricsUnavailableReason,
    openDrilldown,
    drilldownOpen,
    setDrilldownOpen,
    drilldownLoading,
    drilldownError,
    drilldown,
  } = useUnitMetrics(reloadToken);

  const unavailableReason =
    metricsStatus === "unavailable"
      ? (metricsLoadError ?? metricsUnavailableReason)
      : metricsStatus === "loading"
        ? "Loading registered metrics…"
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
    {
      icon: Activity,
      title: "Member inquiry",
      metric: memberInquiry.metric,
      thresholds: null,
      detail: caption(memberInquirySummary, MEMBER_INQUIRY_METRIC_NAME),
    },
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
        <div className="h-10 w-48 animate-pulse rounded bg-gray-200" />
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <div
              key={index}
              className="h-36 animate-pulse rounded-2xl border border-gray-200 bg-white shadow-sm"
            />
          ))}
        </div>
        <div className="h-80 animate-pulse rounded-2xl border border-gray-200 bg-white shadow-sm" />
      </div>
    );
  }

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-semibold text-gray-900">
          Dashboard{isMockData && <DemoModeBadge />}
        </h1>
        <p className="mt-1 text-gray-600">
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
          className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-800 shadow-sm transition hover:border-gray-400 hover:bg-gray-50"
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

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          title="Opportunities"
          value={
            <AccountableValue
              metric={opportunities.metric}
              formatNumber={(value) => value.toLocaleString("en-US")}
            />
          }
          change={caption(opportunities.summary, OPPORTUNITIES_METRIC_NAME)}
          changeType="neutral"
          icon={Briefcase}
          iconColor="bg-[#e6effb] text-[#005394]"
        />
        <MetricCard
          title="Member Inquiry"
          value={
            <AccountableValue
              metric={memberInquiry.metric}
              formatNumber={(value) => value.toLocaleString("en-US")}
            />
          }
          change={caption(memberInquiry.summary, MEMBER_INQUIRY_METRIC_NAME)}
          changeType="neutral"
          icon={TrendingUp}
          iconColor="bg-[#e6effb] text-[#005394]"
        />
        <MetricCard
          title="Upcoming Events"
          value={
            <AccountableValue
              metric={upcomingEventsMetric}
              formatNumber={(value) => value.toLocaleString("en-US")}
            />
          }
          change="Calendar dataset"
          changeType="neutral"
          icon={CalendarDays}
          iconColor="bg-[#e6effb] text-[#005394]"
          href="/calendar"
        />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-900">Pipeline funnel</h2>
        <PipelineFunnelTiles reloadToken={reloadToken} />
        <p className="mt-3 text-sm text-gray-600">
          These are the same registered names the Pipeline page subscribes to, so the two surfaces
          cannot show different numbers for the same metric.
        </p>
      </div>

      <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-[#005394]" />
            <div>
              <h3 className="text-lg font-semibold text-gray-900">Recovery and coverage summary</h3>
              <p className="text-sm text-gray-600">
                A compact view of event coverage and volunteers needing to recover.
              </p>
            </div>
          </div>
          <Link
            to="/calendar"
            className="shrink-0 text-xs font-medium text-[#005394] hover:underline"
          >
            View calendar →
          </Link>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Covered Events</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              <AccountableValue
                metric={coveredEventsMetric}
                formatNumber={(value) => value.toLocaleString("en-US")}
              />
            </p>
            <p className="mt-1 text-sm text-gray-600">
              <AccountableValue
                metric={coverageRateMetric}
                formatNumber={(value) => `${Math.round(value * 100)}% covered`}
              />
            </p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Open Events</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              <AccountableValue
                metric={openEventsMetric}
                formatNumber={(value) => value.toLocaleString("en-US")}
              />
            </p>
            <p className="mt-1 text-sm text-gray-600">Still need volunteer coverage</p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Avg fatigue</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              <AccountableValue
                metric={averageFatigueMetric}
                formatNumber={(value) => `${Math.round(value * 100)}%`}
              />
            </p>
            <p className="mt-1 text-sm text-gray-600">From the assignment overlay data</p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Rest Recommended</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              <AccountableValue metric={restRecommendedMetric} />
            </p>
            <p className="mt-1 text-sm text-gray-600">Volunteers the matcher should avoid</p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <MessageSquareHeart className="h-5 w-5 text-[#005394]" />
            <div>
              <h3 className="text-lg font-semibold text-gray-900">Matching Algorithm Feedback</h3>
              <p className="text-sm text-gray-600">
                Coordinator feedback drives a bounded weight snapshot and pain-score trend.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-[#d5e0f7] bg-[#f7f9fc] px-3 py-1 text-xs font-medium text-[#005394]">
              <AccountableValue
                metric={feedbackRowsMetric}
                formatNumber={(value) => `${value.toLocaleString("en-US")} feedback rows`}
              />
            </div>
            <Link to="/ai-matching" className="text-xs font-medium text-[#005394] hover:underline">
              View matches →
            </Link>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Acceptance rate</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              <AccountableValue
                metric={feedbackAcceptanceMetric}
                formatNumber={(value) => `${Math.round(value * 100)}%`}
              />
            </p>
            <p className="mt-1 text-sm text-gray-600">
              {feedbackAvailable &&
              feedbackStats.accepted !== null &&
              feedbackStats.declined !== null
                ? `${feedbackStats.accepted} accepted / ${feedbackStats.declined} declined`
                : "Coordinator feedback breakdown unavailable."}
            </p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Pain score</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              <AccountableValue
                metric={feedbackPainMetric}
                formatNumber={(value) => Math.round(value).toLocaleString("en-US")}
              />
            </p>
            <p className="mt-1 text-sm text-gray-600">
              A lower score indicates a healthier matching loop.
            </p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Membership interest</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              <AccountableValue
                metric={feedbackMembershipMetric}
                formatNumber={(value) => `${Math.round(value * 100)}%`}
              />
            </p>
            <p className="mt-1 text-sm text-gray-600">
              {feedbackAvailable && feedbackStats.membership_interest_count !== null
                ? `${feedbackStats.membership_interest_count} attributed follow-through signals.`
                : "Membership interest signals unavailable."}
            </p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Lead adjustment</p>
            <p className="mt-2 text-lg font-semibold text-gray-900">
              {leadAdjustment
                ? formatFactorName(leadAdjustment.factor)
                : feedbackAvailable
                  ? "No adjustment yet"
                  : "Unknown"}
            </p>
            <p className="mt-1 text-sm text-gray-600">
              {leadAdjustment
                ? `${leadAdjustment.delta > 0 ? "+" : ""}${(leadAdjustment.delta * 100).toFixed(1)} pts`
                : feedbackAvailable
                  ? "Collect more coordinator outcomes to unlock recommendations."
                  : "Feedback optimizer stats are unavailable."}
            </p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[1fr_0.95fr]">
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <h4 className="mb-3 font-semibold text-gray-900">Acceptance trend</h4>
            {feedbackStats.trend.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-white p-6 text-sm text-gray-600">
                {feedbackAvailable
                  ? "Trend data will appear once coordinators submit feedback from the React workflow."
                  : "Feedback optimizer stats are unavailable."}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart
                  data={feedbackStats.trend.map((point) => ({
                    ...point,
                    acceptance_percent: Math.round(point.acceptance_rate * 100),
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6eef7" />
                  <XAxis dataKey="date" tick={{ fill: "#5a6472", fontSize: 12 }} />
                  <YAxis tick={{ fill: "#5a6472", fontSize: 12 }} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="acceptance_percent"
                    stroke="#005394"
                    strokeWidth={3}
                    name="Acceptance %"
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <div className="mb-3 flex items-center gap-2">
              <SlidersHorizontal className="h-4 w-4 text-[#005394]" />
              <h4 className="font-semibold text-gray-900">Recommended weight shifts</h4>
            </div>
            <div className="space-y-3">
              {feedbackStats.recommended_adjustments.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-white p-6 text-sm text-gray-600">
                  {feedbackAvailable
                    ? "No weight deltas yet. The optimizer is waiting for stronger coordinator signal."
                    : "Feedback optimizer stats are unavailable."}
                </div>
              ) : (
                feedbackStats.recommended_adjustments.slice(0, 4).map((adjustment) => (
                  <div
                    key={adjustment.factor}
                    className="rounded-2xl border border-[#d5e0f7] bg-white p-4 shadow-sm"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold text-gray-900">
                        {formatFactorName(adjustment.factor)}
                      </p>
                      <span className="text-sm font-semibold text-[#005394]">
                        {adjustment.delta > 0 ? "+" : ""}
                        {(adjustment.delta * 100).toFixed(1)} pts
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-gray-600">{adjustment.rationale}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <MapPinned className="h-5 w-5 text-[#005394]" />
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[#005394]/70">
                  Regional coverage pulse
                </p>
              </div>
              <h3 className="mt-2 text-xl font-semibold text-gray-900">
                Coordinator coverage pulse
              </h3>
              <p className="mt-1 text-sm text-gray-600">
                Rollup of calendar coverage and assignment overlays from the same feed.
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {regionalPulse.length ? (
              regionalPulse.map((region) => (
                <div
                  key={region.region}
                  className="rounded-2xl border border-[#d5e0f7] bg-[linear-gradient(180deg,#fafdff_0%,#edf4ff_100%)] p-5 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-gray-900">{region.region}</p>
                      <p className="mt-1 text-sm text-gray-600">{region.detail}</p>
                    </div>
                    <span className="rounded-full border border-[#d5e0f7] bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[#005394]">
                      {region.coveragePercent === null
                        ? "Coverage unknown"
                        : `${region.coveragePercent}% covered`}
                    </span>
                  </div>

                  <div className="mt-4 space-y-2">
                    <div className="flex items-center justify-between text-xs font-medium uppercase tracking-[0.18em] text-[#5a6472]">
                      <span>Coverage</span>
                      <span>
                        {region.coveredCount}/{region.eventCount} windows
                      </span>
                    </div>
                    {/* An unknown ratio gets a hatched, empty track rather than a
                        zero-width fill: a bar drawn at 0% reads as a measurement
                        of nothing covered, which is not what "unknown" means
                        (ADR-0011 rule 1). */}
                    {region.coveragePercent === null ? (
                      <div
                        className="h-2 rounded-full border border-dashed border-[#cfd8e5] bg-white/80"
                        role="img"
                        aria-label={
                          region.unknownCount
                            ? `Coverage ratio unknown — ${region.unknownCount} window${region.unknownCount === 1 ? " has" : "s have"} unresolved coverage.`
                            : "Coverage ratio unknown — this region has no scheduled windows to measure against."
                        }
                      />
                    ) : (
                      <div className="h-2 rounded-full bg-white/80">
                        <div
                          className="h-2 rounded-full bg-[#005394]"
                          style={{ width: `${region.coveragePercent}%` }}
                        />
                      </div>
                    )}
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-gray-700">
                    <div className="rounded-2xl border border-white/70 bg-white/85 px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#5a6472]">
                        Explicitly open
                      </p>
                      <p className="mt-1 text-lg font-semibold text-gray-900">{region.openCount}</p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/85 px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#5a6472]">
                        Volunteers
                      </p>
                      <p className="mt-1 text-lg font-semibold text-gray-900">
                        {region.uniqueVolunteers}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/85 px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#5a6472]">
                        Overlay rows
                      </p>
                      <p className="mt-1 text-lg font-semibold text-gray-900">
                        {region.assignmentCount}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/85 px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#5a6472]">
                        Member inquiry
                      </p>
                      <p className="mt-1 text-lg font-semibold text-gray-900">
                        <MetricValueDisplay
                          value={unknownValue(REGION_MEMBER_INQUIRY_UNKNOWN_REASON)}
                        />
                      </p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-[#f7f9fc] p-8 text-sm text-gray-600 lg:col-span-2">
                Regional coverage summaries appear once live calendar and overlay data are
                available.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <BellRing className="h-5 w-5 text-[#005394]" />
            <div>
              <h3 className="text-xl font-semibold text-gray-900">Discovery feed</h3>
              <p className="text-sm text-gray-600">
                Registered metrics from <code>/v1/units/&#123;unit_id&#125;/metrics</code>, graded
                red / yellow / green by the stated threshold rule. An unmeasured value is
                &ldquo;Not measured&rdquo;, never green and never zero.
              </p>
            </div>
          </div>

          <DiscoveryFeed items={discoveryFeed} className="mt-6" />
        </div>
      </div>

      <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-lg font-semibold text-gray-900">Calendar Reach Trend</h3>
        {reachTrend.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-[#f7f9fc] p-8 text-sm text-gray-600">
            No calendar windows in the current feed, so there is no reach trend to plot.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={reachTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e6eef7" />
              <XAxis dataKey="month" tick={{ fill: "#5a6472", fontSize: 12 }} />
              <YAxis tick={{ fill: "#5a6472", fontSize: 12 }} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="windows"
                stroke="#005394"
                strokeWidth={3}
                name="IA windows"
              />
              <Line
                type="monotone"
                dataKey="covered"
                stroke="#56a4e4"
                strokeWidth={3}
                name="Covered windows"
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
        <div className="mb-6 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-[#005394]" />
          <h3 className="text-lg font-semibold text-gray-900">Top Recommended Matches</h3>
        </div>

        <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-[#f7f9fc] p-8 text-center text-gray-600">
          <p className="text-sm font-semibold text-gray-900">Matching unavailable</p>
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
