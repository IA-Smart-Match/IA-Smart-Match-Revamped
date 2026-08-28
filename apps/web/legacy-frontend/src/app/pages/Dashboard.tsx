import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BellRing,
  Briefcase,
  CalendarDays,
  LogOut,
  Mail,
  MapPinned,
  MessageSquareHeart,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Funnel,
  FunnelChart,
  LabelList,
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
  fetchEvents,
  fetchFeedbackStats,
  fetchPipeline,
  fetchSpecialists,
  initiateWorkflow,
  rankSpeakers,
  splitTags,
  type CalendarAssignmentSummary,
  type CalendarEventSummary,
  type FeedbackStatsSummary,
  type PipelineRecord,
  type RankedMatch,
  type Specialist,
  type WorkflowResponse,
} from "@/lib/api";
import {
  accountableMetricFromSummary,
  OPPORTUNITIES_UNKNOWN_REASON,
  unavailableOpportunitiesMetric,
  unavailablePipelineMetric,
} from "@/lib/metrics";
import { PipelineFunnelTiles } from "@/app/components/PipelineFunnelTiles";
import { AccountableValue, MetricDrilldownSheet } from "@/app/components/provenance";
import { useUnitMetrics } from "@/app/hooks/useUnitMetrics";
import { OutreachWorkflowModal } from "@/components/OutreachWorkflowModal";
import { DemoModeBadge } from "../components/ui/DemoModeBadge";
import { Button } from "../components/ui/button";

import { MetricCard } from "../components/MetricCard";
import { CrawlerFeed } from "@/components/CrawlerFeed";

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

const funnelPalette = ["#005394", "#1f6fb2", "#2b87d1", "#56a4e4", "#a2c9ff"];

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
  assignmentCount: number;
  uniqueVolunteers: number;
  memberInquiryCount: number;
  coveragePercent: number;
  workloadPercent: number;
  detail: string;
};

function stageCounts(records: PipelineRecord[]) {
  const counts = new Map<string, { count: number; order: number }>();
  for (const record of records) {
    const stage = record.stage || "Unknown";
    const order = Number(record.stage_order) || 0;
    const current = counts.get(stage);
    counts.set(stage, {
      count: (current?.count ?? 0) + 1,
      order: current?.order ?? order,
    });
  }
  return Array.from(counts.entries())
    .sort((a, b) => a[1].order - b[1].order)
    .map(([stage, value], index) => ({
      name: stage,
      value: value.count,
      fill: funnelPalette[index % funnelPalette.length],
    }));
}

function matchVolume(records: PipelineRecord[]) {
  const counts = new Map<string, number>();
  for (const record of records) {
    counts.set(record.event_name, (counts.get(record.event_name) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 7)
    .map(([event, count]) => ({
      event: event.length > 18 ? `${event.slice(0, 18)}…` : event,
      matches: count,
    }));
}

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

function buildRegionalPulse(
  calendarEvents: CalendarEventSummary[],
  calendarAssignments: CalendarAssignmentSummary[],
  pipeline: PipelineRecord[],
): RegionalPulseRow[] {
  const assignmentKeyToRegion = new Map<string, string>();
  for (const assignment of calendarAssignments) {
    assignmentKeyToRegion.set(
      `${assignment.event_name.trim().toLowerCase()}::${assignment.volunteer_name.trim().toLowerCase()}`,
      assignment.region,
    );
  }

  const memberInquiriesByRegion = new Map<string, number>();
  for (const record of pipeline) {
    if (record.stage !== "Member Inquiry") {
      continue;
    }
    const region = assignmentKeyToRegion.get(
      `${record.event_name.trim().toLowerCase()}::${record.speaker_name.trim().toLowerCase()}`,
    );
    if (!region) {
      continue;
    }
    memberInquiriesByRegion.set(region, (memberInquiriesByRegion.get(region) ?? 0) + 1);
  }

  const regions = Array.from(
    new Set(
      [...calendarEvents.map((event) => event.region), ...calendarAssignments.map((assignment) => assignment.region)]
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  );

  return regions
    .map((region) => {
      const eventsInRegion = calendarEvents.filter((event) => event.region === region);
      const assignmentsInRegion = calendarAssignments.filter((assignment) => assignment.region === region);
      const coveredCount = eventsInRegion.filter((event) => event.coverage_status === "covered").length;
      const eventCount = eventsInRegion.length;
      const openCount = eventsInRegion.filter((event) => event.coverage_status !== "covered").length;
      const assignmentCount = assignmentsInRegion.length;
      const uniqueVolunteers = new Set(assignmentsInRegion.map((assignment) => assignment.volunteer_name)).size;
      const memberInquiryCount = memberInquiriesByRegion.get(region) ?? 0;
      const coveragePercent = eventCount ? Math.round((coveredCount / eventCount) * 100) : 0;
      const workloadPercent = Math.max(0, Math.min(Math.round((assignmentCount / Math.max(eventCount * 3, 1)) * 100), 100));
      const detail = `${eventCount} calendar window${eventCount === 1 ? "" : "s"}, ${assignmentCount} assignment overlay${assignmentCount === 1 ? "" : "s"}, ${memberInquiryCount} member inquir${memberInquiryCount === 1 ? "y" : "ies"}.`;

      return {
        region,
        eventCount,
        coveredCount,
        openCount,
        assignmentCount,
        uniqueVolunteers,
        memberInquiryCount,
        coveragePercent,
        workloadPercent,
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

  function handleLogout() {
    sessionStorage.removeItem("iaw_session");
    navigate("/login");
  }

  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [pipeline, setPipeline] = useState<PipelineRecord[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEventSummary[]>([]);
  const [calendarAssignments, setCalendarAssignments] = useState<CalendarAssignmentSummary[]>(
    [],
  );
  const [topMatches, setTopMatches] = useState<RankedMatch[]>([]);
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStatsSummary>(
    emptyFeedbackStatsSummary(),
  );
  const [isMockData, setIsMockData] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [showWorkflowModal, setShowWorkflowModal] = useState(false);
  const [selectedVolunteer, setSelectedVolunteer] = useState<RankedMatch | null>(null);
  const [workflowResult, setWorkflowResult] = useState<WorkflowResponse | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadFailed(false);
    setError(null);

    function resetToEmpty() {
      setSpecialists([]);
      setPipeline([]);
      setCalendarEvents([]);
      setCalendarAssignments([]);
      setFeedbackStats(emptyFeedbackStatsSummary());
      setTopMatches([]);
      setIsMockData(false);
    }

    async function load() {
      try {
        const results = await Promise.allSettled([
          fetchSpecialists(),
          fetchEvents(),
          fetchPipeline(),
          fetchCalendarEvents(),
          fetchCalendarAssignments(),
          fetchFeedbackStats(),
        ]);
        const [
          specialistResult,
          eventResult,
          pipelineResult,
          calendarResult,
          assignmentResult,
          feedbackResult,
        ] = results;

        if (!active) {
          return;
        }

        // Specialists, events, pipeline, and calendar windows are the
        // dashboard's core data. If any of them failed to load, the
        // dashboard cannot honestly render — show a failure state instead
        // of discarding whatever did succeed and substituting fixtures.
        if (
          specialistResult.status !== "fulfilled" ||
          eventResult.status !== "fulfilled" ||
          pipelineResult.status !== "fulfilled" ||
          calendarResult.status !== "fulfilled"
        ) {
          const reason =
            specialistResult.status === "rejected"
              ? specialistResult.reason
              : eventResult.status === "rejected"
                ? eventResult.reason
                : pipelineResult.status === "rejected"
                  ? pipelineResult.reason
                  : (calendarResult as PromiseRejectedResult).reason;
          resetToEmpty();
          setLoadFailed(true);
          setError(getErrorMessage(reason, "Failed to load dashboard data."));
          return;
        }

        let anyMock = false;

        const specialistRows = specialistResult.value.data;
        const eventRows = eventResult.value.data;
        if (specialistResult.value.isMockData) anyMock = true;
        if (eventResult.value.isMockData) anyMock = true;

        const pipelineRows = pipelineResult.value.data;
        if (pipelineResult.value.isMockData) anyMock = true;

        const calendarRows = calendarResult.value.data;
        if (calendarResult.value.isMockData) anyMock = true;

        setSpecialists(specialistRows);
        setPipeline(pipelineRows);
        setCalendarEvents(calendarRows);

        if (assignmentResult.status === "fulfilled") {
          setCalendarAssignments(assignmentResult.value.data);
          if (assignmentResult.value.isMockData) anyMock = true;
        } else {
          // Assignment overlays are supplementary — keep the core dashboard
          // honest and surface a warning instead of fabricating overlays.
          setCalendarAssignments([]);
        }

        if (feedbackResult.status === "fulfilled") {
          setFeedbackStats(feedbackResult.value.data);
          if (feedbackResult.value.isMockData) anyMock = true;
        } else {
          setFeedbackStats(emptyFeedbackStatsSummary());
        }

        setIsMockData(anyMock);

        const warnings = [];
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

        const firstEventName = eventRows[0]?.["Event / Program"];
        if (firstEventName) {
          try {
            const feedbackWeights =
              feedbackResult.status === "fulfilled" &&
              Object.keys(feedbackResult.value.data.current_weights).length > 0
                ? feedbackResult.value.data.current_weights
                : undefined;
            const ranked = await rankSpeakers(firstEventName, 4, feedbackWeights);
            if (active) {
              setTopMatches(ranked);
            }
          } catch {
            if (active) {
              setTopMatches([]);
            }
          }
        }
      } catch (err: unknown) {
        if (active) {
          // Unexpected failure — report it honestly rather than
          // substituting fixture data for the whole dashboard.
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

  const memberInquirySummary = metricsByName.pipeline_member_inquiry;
  const memberInquiryMetric = memberInquirySummary
    ? accountableMetricFromSummary(memberInquirySummary, {
        provenance: "observed",
        onOpenDrilldown: () => {
          void openDrilldown("pipeline_member_inquiry");
        },
      })
    : unavailablePipelineMetric(
        "pipeline_member_inquiry",
        metricsStatus === "unavailable"
          ? (metricsLoadError ?? metricsUnavailableReason)
          : "Loading registered metrics…",
      );

  const opportunitiesMetric = unavailableOpportunitiesMetric();

  const funnelData = stageCounts(pipeline);
  const eventVolume = matchVolume(pipeline);
  const reachTrend = calendarReach(calendarEvents);
  const memberInquiryDemoCount =
    funnelData.find((stage) => stage.name === "Member Inquiry")?.value ?? 0;
  const uniqueMatchedSpeakers = new Set(pipeline.map((record) => record.speaker_name)).size;
  const utilization = specialists.length
    ? Math.round((uniqueMatchedSpeakers / specialists.length) * 100)
    : 0;
  const primaryMatch = topMatches[0];
  const coveredCalendarCount = calendarEvents.filter(
    (event) => event.coverage_status === "covered",
  ).length;
  const openCalendarCount = calendarEvents.filter(
    (event) => event.coverage_status !== "covered",
  ).length;
  const averageFatigue = calendarAssignments.length
    ? Math.round(
        (calendarAssignments.reduce((sum, assignment) => sum + assignment.volunteer_fatigue, 0) /
          calendarAssignments.length) *
          100,
      )
    : 0;
  const cooldownCount = calendarAssignments.filter(
    (assignment) => assignment.recovery_status === "Rest Recommended",
  ).length;
  const leadAdjustment = feedbackStats.recommended_adjustments[0] ?? null;
  const regionalPulse = buildRegionalPulse(calendarEvents, calendarAssignments, pipeline);
  const regionNeedingCoverage =
    regionalPulse
      .filter((row) => row.openCount > 0)
      .sort((left, right) => right.openCount - left.openCount || right.eventCount - left.eventCount)[0] ??
    null;
  const strongestCoverageRegion =
    regionalPulse
      .filter((row) => row.eventCount > 0)
      .sort(
        (left, right) =>
          right.coveragePercent - left.coveragePercent ||
          right.uniqueVolunteers - left.uniqueVolunteers,
      )[0] ?? null;
  const hottestInquiryRegion =
    regionalPulse
      .filter((row) => row.memberInquiryCount > 0)
      .sort((left, right) => right.memberInquiryCount - left.memberInquiryCount)[0] ?? null;

  const handleConnect = async (match: RankedMatch) => {
    setSelectedVolunteer(match);
    setShowWorkflowModal(true);
    setWorkflowLoading(true);
    setWorkflowError(null);
    setWorkflowResult(null);
    try {
      const result = await initiateWorkflow(match.name, match.event_name);
      setWorkflowResult(result);
    } catch (err: unknown) {
      setWorkflowError(err instanceof Error ? err.message : "Workflow failed.");
    } finally {
      setWorkflowLoading(false);
    }
  };

  const discoveryFeed = [
    {
      icon: BellRing,
      title: primaryMatch
        ? `Lead match ready: ${primaryMatch.name}`
        : "Lead match queue ready",
      detail: primaryMatch
        ? `${primaryMatch.event_name} is sitting at ${(primaryMatch.score * 100).toFixed(
            0,
          )}% confidence and can be reviewed now.`
        : "Run the matcher to populate the top recommendation feed.",
      stamp: primaryMatch ? "Top recommendation" : "Awaiting data",
    },
    {
      icon: MapPinned,
      title: regionNeedingCoverage
        ? `${regionNeedingCoverage.region} has ${regionNeedingCoverage.openCount} uncovered window${regionNeedingCoverage.openCount === 1 ? "" : "s"}`
        : `${calendarEvents.length} calendar windows are currently covered`,
      detail: regionNeedingCoverage
        ? `${regionNeedingCoverage.assignmentCount} assignment overlays are attached across ${regionNeedingCoverage.eventCount} scheduled windows in that region.`
        : "Every scheduled calendar window currently has covered status in the live feed.",
      stamp: "Coverage",
    },
    {
      icon: Activity,
      title:
        memberInquirySummary?.value !== null && memberInquirySummary?.value !== undefined
          ? `${memberInquirySummary.value} records reached member inquiry (registered metric)`
          : "Pipeline funnel metrics load from the register when authenticated",
      detail:
        memberInquirySummary?.unknown_reason ??
        `${memberInquiryDemoCount} demo pipeline rows are at member inquiry until S12 persistence lands.`,
      stamp: "Pipeline",
    },
    {
      icon: ShieldCheck,
      title: strongestCoverageRegion
        ? `${strongestCoverageRegion.region} is at ${strongestCoverageRegion.coveragePercent}% covered`
        : "Regional coverage is waiting on live calendar data",
      detail: hottestInquiryRegion
        ? `${hottestInquiryRegion.memberInquiryCount} member inquiry record${hottestInquiryRegion.memberInquiryCount === 1 ? "" : "s"} are currently attributed to ${hottestInquiryRegion.region}.`
        : strongestCoverageRegion
          ? `${strongestCoverageRegion.uniqueVolunteers} volunteer${strongestCoverageRegion.uniqueVolunteers === 1 ? "" : "s"} are attached to that region's current windows.`
          : "The dashboard will populate regional coverage notes once calendar and pipeline data are available.",
      stamp: "Regional watch",
    },
  ];

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="h-10 w-48 animate-pulse rounded bg-gray-200" />
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
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

  if (loadFailed) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold text-gray-900">Dashboard</h1>
            <p className="mt-1 text-gray-600">
              Live summary of the specialist roster, pipeline movement, and registered metrics.
            </p>
          </div>
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-gray-900">
            Dashboard{isMockData && <DemoModeBadge />}
          </h1>
          <p className="mt-1 text-gray-600">
            Live summary of the specialist roster, pipeline movement, and registered metrics.
          </p>
        </div>
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

      {error ? (
        <FailureState
          title="Some dashboard data is unavailable"
          message={error}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="Opportunities"
          value={<AccountableValue metric={opportunitiesMetric} />}
          change={OPPORTUNITIES_UNKNOWN_REASON}
          changeType="neutral"
          icon={Briefcase}
          iconColor="bg-[#e6effb] text-[#005394]"
          href="/opportunities"
        />
        <MetricCard
          title="Volunteer Utilization"
          value={`${utilization}%`}
          change={`${uniqueMatchedSpeakers} specialists in pipeline`}
          changeType="positive"
          icon={Users}
          iconColor="bg-[#e6effb] text-[#005394]"
          href="/volunteers"
        />
        <MetricCard
          title="Upcoming Events"
          value={calendarEvents.length}
          change="Calendar dataset"
          changeType="neutral"
          icon={CalendarDays}
          iconColor="bg-[#e6effb] text-[#005394]"
          href="/calendar"
        />
        <MetricCard
          title="Member Inquiry"
          value={<AccountableValue metric={memberInquiryMetric} />}
          change={memberInquirySummary?.definition ?? "Registered pipeline_member_inquiry metric"}
          changeType="positive"
          icon={TrendingUp}
          iconColor="bg-[#e6effb] text-[#005394]"
          href="/pipeline"
        />
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
          <Link to="/calendar" className="shrink-0 text-xs font-medium text-[#005394] hover:underline">
            View calendar →
          </Link>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Covered Events</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">{coveredCalendarCount}</p>
            <p className="mt-1 text-sm text-gray-600">
              {calendarEvents.length
                ? `${Math.round((coveredCalendarCount / calendarEvents.length) * 100)}% covered`
                : "No calendar events yet"}
            </p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Open Events</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">{openCalendarCount}</p>
            <p className="mt-1 text-sm text-gray-600">Still need volunteer coverage</p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Avg fatigue</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">{averageFatigue}%</p>
            <p className="mt-1 text-sm text-gray-600">From the assignment overlay data</p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Rest Recommended</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">{cooldownCount}</p>
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
                Coordinator feedback now drives a bounded weight snapshot and pain-score trend.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-[#d5e0f7] bg-[#f7f9fc] px-3 py-1 text-xs font-medium text-[#005394]">
              {feedbackStats.total_feedback} feedback rows
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
              {Math.round(feedbackStats.acceptance_rate * 100)}%
            </p>
            <p className="mt-1 text-sm text-gray-600">
              {feedbackStats.accepted} accepted / {feedbackStats.declined} declined
            </p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Pain score</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              {Math.round(feedbackStats.pain_score)}
            </p>
            <p className="mt-1 text-sm text-gray-600">A lower score indicates a healthier matching loop.</p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Membership interest</p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              {Math.round(feedbackStats.membership_interest_rate * 100)}%
            </p>
            <p className="mt-1 text-sm text-gray-600">
              {feedbackStats.membership_interest_count} attributed follow-through signals.
            </p>
          </div>
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Lead adjustment</p>
            <p className="mt-2 text-lg font-semibold text-gray-900">
              {leadAdjustment ? formatFactorName(leadAdjustment.factor) : "No adjustment yet"}
            </p>
            <p className="mt-1 text-sm text-gray-600">
              {leadAdjustment
                ? `${leadAdjustment.delta > 0 ? "+" : ""}${(leadAdjustment.delta * 100).toFixed(1)} pts`
                : "Collect more coordinator outcomes to unlock recommendations."}
            </p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[1fr_0.95fr]">
          <div className="rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4">
            <h4 className="mb-3 font-semibold text-gray-900">Acceptance trend</h4>
            {feedbackStats.trend.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-white p-6 text-sm text-gray-600">
                Trend data will appear once coordinators submit feedback from the React workflow.
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
                  No weight deltas yet. The optimizer is waiting for stronger coordinator signal.
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
                Live rollup built from calendar coverage, assignment overlays, and pipeline follow-through.
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
                      {region.coveragePercent}% covered
                    </span>
                  </div>

                  <div className="mt-4 space-y-2">
                    <div className="flex items-center justify-between text-xs font-medium uppercase tracking-[0.18em] text-[#5a6472]">
                      <span>Coverage</span>
                      <span>{region.coveredCount}/{region.eventCount || 0} windows</span>
                    </div>
                    <div className="h-2 rounded-full bg-white/80">
                      <div
                        className="h-2 rounded-full bg-[#005394]"
                        style={{ width: `${region.coveragePercent}%` }}
                      />
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-gray-700">
                    <div className="rounded-2xl border border-white/70 bg-white/85 px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#5a6472]">
                        Open windows
                      </p>
                      <p className="mt-1 text-lg font-semibold text-gray-900">{region.openCount}</p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/85 px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#5a6472]">
                        Workload
                      </p>
                      <p className="mt-1 text-lg font-semibold text-gray-900">
                        {region.workloadPercent}%
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
                        {region.memberInquiryCount}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-[#f7f9fc] p-8 text-sm text-gray-600 lg:col-span-2">
                Regional coverage summaries will appear once live calendar and overlay data are available.
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
                Lightweight coordinator notifications derived from the current dataset.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            {discoveryFeed.map((item) => {
              const Icon = item.icon;

              return (
                <div
                  key={item.title}
                  className="flex gap-4 rounded-2xl border border-[#d5e0f7] bg-[#f7f9fc] p-4 shadow-sm"
                >
                  <div className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-[#d5e0f7] bg-white text-[#005394]">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3">
                      <p className="font-semibold text-gray-900">{item.title}</p>
                      <span className="rounded-full bg-[#e6effb] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#005394]">
                        {item.stamp}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-gray-600">{item.detail}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <PipelineFunnelTiles reloadToken={reloadToken} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">Pipeline Funnel (demo rows)</h3>
            <Link to="/pipeline" className="text-xs font-medium text-[#005394] hover:underline">
              View pipeline →
            </Link>
          </div>
          <p className="mb-4 text-xs text-gray-600">
            Chart below uses legacy /api pipeline rows for layout only. KPI tiles above use the
            registered metrics API and show Unknown until S12 persistence exists.
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <FunnelChart>
              <Tooltip />
              <Funnel dataKey="value" data={funnelData}>
                <LabelList position="right" fill="#1f2937" stroke="none" dataKey="name" />
              </Funnel>
            </FunnelChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold text-gray-900">Match Volume by Event</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={eventVolume}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e6eef7" />
              <XAxis dataKey="event" tick={{ fill: "#5a6472", fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fill: "#5a6472", fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="matches" fill="#2b6cb0" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-lg font-semibold text-gray-900">Calendar Reach Trend</h3>
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
      </div>

      <div className="rounded-2xl border border-[#d5e0f7] bg-white p-6 shadow-sm">
        <div className="mb-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-[#005394]" />
            <h3 className="text-lg font-semibold text-gray-900">Top Recommended Matches</h3>
          </div>
          <Link
            to="/ai-matching"
            className="flex items-center gap-1 text-sm font-medium text-[#005394] transition-colors hover:text-[#00477f]"
          >
            View All
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        <div className="space-y-4">
          {topMatches.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-[#f7f9fc] p-8 text-center text-gray-600">
              Ranking data will appear here once the FastAPI backend is running with the matching endpoint.
            </div>
          ) : (
            topMatches.map((match) => (
              <div
                key={`${match.event_name}-${match.name}`}
                className="flex items-center justify-between gap-4 rounded-2xl border border-[#d5e0f7] bg-gradient-to-r from-white to-[#f2f7ff] p-4 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-gray-900">{match.name}</p>
                    <span className="rounded-full bg-[#e6effb] px-2 py-0.5 text-xs text-[#005394]">
                      {splitTags(match.expertise_tags)[0] || match.board_role || "Specialist"}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-gray-600">
                    {match.event_name} · {match.company || "IA West volunteer"}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-sm text-gray-600">Match Score</p>
                    <p className="text-2xl font-semibold text-[#005394]">
                      {(match.score * 100).toFixed(0)}%
                    </p>
                  </div>
                  <button
                    onClick={() => void handleConnect(match)}
                    disabled={workflowLoading}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-[#00477f] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Mail className="h-3.5 w-3.5" />
                    Connect
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Web Crawler Live Feed */}
      <CrawlerFeed />

      {showWorkflowModal && selectedVolunteer && (
        <OutreachWorkflowModal
          volunteer={selectedVolunteer}
          result={workflowResult}
          loading={workflowLoading}
          error={workflowError}
          onClose={() => setShowWorkflowModal(false)}
        />
      )}

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
