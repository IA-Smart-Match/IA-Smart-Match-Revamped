/**
 * Presentational sections and pure helpers extracted from `Dashboard.tsx`
 * (D1-M1 restyle) so the page component stays under the file-size ceiling.
 *
 * Every component here is presentation-only: it renders values its caller
 * already computed through `AccountableValue`/`accountableDemoMetric`. No
 * component in this file fetches data, mutates state, or invents a number —
 * moving JSX here must not change what the dashboard shows or how it
 * behaves.
 */
import { Link } from "react-router";
import {
  AlertTriangle,
  BellRing,
  Briefcase,
  CalendarDays,
  MapPinned,
  MessageSquareHeart,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
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

import type {
  CalendarAssignmentSummary,
  CalendarEventSummary,
  FeedbackStatsSummary,
} from "@/lib/api";
import { summarizeCalendarCoverage } from "@/lib/calendarCoverage";
import { DiscoveryFeed, type DiscoveryFeedItem } from "@/app/components/DiscoveryFeed";
import { MetricCard } from "@/app/components/MetricCard";
import { PipelineFunnelTiles } from "@/app/components/PipelineFunnelTiles";
import {
  AccountableValue,
  MetricValueDisplay,
  unknownValue,
  type AccountableMetric,
} from "@/app/components/provenance";
import { Button } from "@/app/components/ui/button";

/** Plain-language failure card with an optional retry action. */
export function FailureState({
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

export function monthLabel(dateString: string): string {
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

export type RegionalPulseRow = {
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

export function calendarReach(records: CalendarEventSummary[]) {
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
export function buildRegionalPulse(
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

export function formatFactorName(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** Headline metric cards plus the shared pipeline funnel tiles. */
export function MetricCardsRow({
  opportunitiesMetric,
  opportunitiesCaption,
  offersMemberInquiry,
  memberInquiryMetric,
  memberInquiryCaption,
  upcomingEventsMetric,
  unitId,
  unitResolving,
  reloadToken,
}: {
  opportunitiesMetric: AccountableMetric;
  opportunitiesCaption: string;
  offersMemberInquiry: boolean;
  memberInquiryMetric: AccountableMetric;
  memberInquiryCaption: string;
  upcomingEventsMetric: AccountableMetric;
  unitId: string | null;
  unitResolving: boolean;
  reloadToken: number;
}) {
  return (
    <>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          title="Opportunities"
          value={
            <AccountableValue
              metric={opportunitiesMetric}
              formatNumber={(value) => value.toLocaleString("en-US")}
            />
          }
          change={opportunitiesCaption}
          changeType="neutral"
          icon={Briefcase}
          iconColor="bg-primary/10 text-primary"
        />
        {offersMemberInquiry ? (
          <MetricCard
            title="Member Inquiry"
            value={
              <AccountableValue
                metric={memberInquiryMetric}
                formatNumber={(value) => value.toLocaleString("en-US")}
              />
            }
            change={memberInquiryCaption}
            changeType="neutral"
            icon={TrendingUp}
            iconColor="bg-primary/10 text-primary"
          />
        ) : null}
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
          iconColor="bg-primary/10 text-primary"
          href="/calendar"
        />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-foreground">Pipeline funnel</h2>
        <PipelineFunnelTiles unitId={unitId} unitResolving={unitResolving} reloadToken={reloadToken} />
        <p className="mt-3 text-sm text-muted-foreground">
          These are the same registered names the Pipeline page subscribes to, so the two surfaces
          cannot show different numbers for the same metric.
        </p>
      </div>
    </>
  );
}

/** Calendar coverage and volunteer-recovery summary tiles. */
export function RecoveryCoverageSummary({
  coveredEventsMetric,
  coverageRateMetric,
  openEventsMetric,
  averageFatigueMetric,
  restRecommendedMetric,
}: {
  coveredEventsMetric: AccountableMetric;
  coverageRateMetric: AccountableMetric;
  openEventsMetric: AccountableMetric;
  averageFatigueMetric: AccountableMetric;
  restRecommendedMetric: AccountableMetric;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <div>
            <h3 className="text-lg font-semibold text-foreground">Recovery and coverage summary</h3>
            <p className="text-sm text-muted-foreground">
              A compact view of event coverage and volunteers needing to recover.
            </p>
          </div>
        </div>
        <Link to="/calendar" className="shrink-0 text-xs font-medium text-primary hover:underline">
          View calendar →
        </Link>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Covered Events</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue
              metric={coveredEventsMetric}
              formatNumber={(value) => value.toLocaleString("en-US")}
            />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            <AccountableValue
              metric={coverageRateMetric}
              formatNumber={(value) => `${Math.round(value * 100)}% covered`}
            />
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Open Events</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue
              metric={openEventsMetric}
              formatNumber={(value) => value.toLocaleString("en-US")}
            />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">Still need volunteer coverage</p>
        </div>
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Avg fatigue</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue
              metric={averageFatigueMetric}
              formatNumber={(value) => `${Math.round(value * 100)}%`}
            />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">From the assignment overlay data</p>
        </div>
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Rest Recommended</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue metric={restRecommendedMetric} />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">Volunteers the matcher should avoid</p>
        </div>
      </div>
    </div>
  );
}

type RecommendedAdjustment = FeedbackStatsSummary["recommended_adjustments"][number];

/** Coordinator feedback / matcher-tuning telemetry panel. */
export function MatchingFeedbackPanel({
  feedbackRowsMetric,
  feedbackAcceptanceMetric,
  feedbackPainMetric,
  feedbackMembershipMetric,
  feedbackAvailable,
  feedbackStats,
  leadAdjustment,
}: {
  feedbackRowsMetric: AccountableMetric;
  feedbackAcceptanceMetric: AccountableMetric;
  feedbackPainMetric: AccountableMetric;
  feedbackMembershipMetric: AccountableMetric;
  feedbackAvailable: boolean;
  feedbackStats: FeedbackStatsSummary;
  leadAdjustment: RecommendedAdjustment | null;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <MessageSquareHeart className="h-5 w-5 text-primary" />
          <div>
            <h3 className="text-lg font-semibold text-foreground">Matching Algorithm Feedback</h3>
            <p className="text-sm text-muted-foreground">
              Coordinator feedback drives a bounded weight snapshot and pain-score trend.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-primary">
            <AccountableValue
              metric={feedbackRowsMetric}
              formatNumber={(value) => `${value.toLocaleString("en-US")} feedback rows`}
            />
          </div>
          <Link to="/ai-matching" className="text-xs font-medium text-primary hover:underline">
            View matches →
          </Link>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Acceptance rate</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue
              metric={feedbackAcceptanceMetric}
              formatNumber={(value) => `${Math.round(value * 100)}%`}
            />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {feedbackAvailable && feedbackStats.accepted !== null && feedbackStats.declined !== null
              ? `${feedbackStats.accepted} accepted / ${feedbackStats.declined} declined`
              : "Coordinator feedback breakdown unavailable."}
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Pain score</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue
              metric={feedbackPainMetric}
              formatNumber={(value) => Math.round(value).toLocaleString("en-US")}
            />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            A lower score indicates a healthier matching loop.
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Membership interest</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue
              metric={feedbackMembershipMetric}
              formatNumber={(value) => `${Math.round(value * 100)}%`}
            />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {feedbackAvailable && feedbackStats.membership_interest_count !== null
              ? `${feedbackStats.membership_interest_count} attributed follow-through signals.`
              : "Membership interest signals unavailable."}
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-muted p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Lead adjustment</p>
          <p className="mt-2 text-lg font-semibold text-foreground">
            {leadAdjustment
              ? formatFactorName(leadAdjustment.factor)
              : feedbackAvailable
                ? "No adjustment yet"
                : "Unknown"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {leadAdjustment
              ? `${leadAdjustment.delta > 0 ? "+" : ""}${(leadAdjustment.delta * 100).toFixed(1)} pts`
              : feedbackAvailable
                ? "Collect more coordinator outcomes to unlock recommendations."
                : "Feedback optimizer stats are unavailable."}
          </p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[1fr_0.95fr]">
        <div className="rounded-2xl border border-border bg-muted p-4">
          <h4 className="mb-3 font-semibold text-foreground">Acceptance trend</h4>
          {feedbackStats.trend.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">
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
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="acceptance_percent"
                  stroke="var(--primary)"
                  strokeWidth={3}
                  name="Acceptance %"
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="rounded-2xl border border-border bg-muted p-4">
          <div className="mb-3 flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            <h4 className="font-semibold text-foreground">Recommended weight shifts</h4>
          </div>
          <div className="space-y-3">
            {feedbackStats.recommended_adjustments.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">
                {feedbackAvailable
                  ? "No weight deltas yet. The optimizer is waiting for stronger coordinator signal."
                  : "Feedback optimizer stats are unavailable."}
              </div>
            ) : (
              feedbackStats.recommended_adjustments.slice(0, 4).map((adjustment) => (
                <div
                  key={adjustment.factor}
                  className="rounded-2xl border border-border bg-card p-4 shadow-sm"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-foreground">
                      {formatFactorName(adjustment.factor)}
                    </p>
                    <span className="text-sm font-semibold text-primary">
                      {adjustment.delta > 0 ? "+" : ""}
                      {(adjustment.delta * 100).toFixed(1)} pts
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{adjustment.rationale}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Regional coverage pulse cards next to the registered-metrics discovery feed. */
export function RegionalPulseAndDiscovery({
  regionalPulse,
  discoveryFeed,
  regionMemberInquiryUnknownReason,
}: {
  regionalPulse: RegionalPulseRow[];
  discoveryFeed: DiscoveryFeedItem[];
  regionMemberInquiryUnknownReason: string;
}) {
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <MapPinned className="h-5 w-5 text-primary" />
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-primary/70">
                Regional coverage pulse
              </p>
            </div>
            <h3 className="mt-2 text-xl font-semibold text-foreground">
              Coordinator coverage pulse
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Rollup of calendar coverage and assignment overlays from the same feed.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          {regionalPulse.length ? (
            regionalPulse.map((region) => (
              <div
                key={region.region}
                className="rounded-2xl border border-border bg-card p-5 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold text-foreground">{region.region}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{region.detail}</p>
                  </div>
                  <span className="rounded-full border border-border bg-card px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                    {region.coveragePercent === null
                      ? "Coverage unknown"
                      : `${region.coveragePercent}% covered`}
                  </span>
                </div>

                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
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
                      className="h-2 rounded-full border border-dashed border-border bg-card/80"
                      role="img"
                      aria-label={
                        region.unknownCount
                          ? `Coverage ratio unknown — ${region.unknownCount} window${region.unknownCount === 1 ? " has" : "s have"} unresolved coverage.`
                          : "Coverage ratio unknown — this region has no scheduled windows to measure against."
                      }
                    />
                  ) : (
                    <div className="h-2 rounded-full bg-card/80">
                      <div
                        className="h-2 rounded-full bg-primary"
                        style={{ width: `${region.coveragePercent}%` }}
                      />
                    </div>
                  )}
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-foreground/80">
                  <div className="rounded-2xl border border-white/70 bg-card/85 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                      Explicitly open
                    </p>
                    <p className="mt-1 text-lg font-semibold text-foreground">{region.openCount}</p>
                  </div>
                  <div className="rounded-2xl border border-white/70 bg-card/85 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                      Volunteers
                    </p>
                    <p className="mt-1 text-lg font-semibold text-foreground">
                      {region.uniqueVolunteers}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-white/70 bg-card/85 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                      Overlay rows
                    </p>
                    <p className="mt-1 text-lg font-semibold text-foreground">
                      {region.assignmentCount}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-white/70 bg-card/85 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                      Member inquiry
                    </p>
                    <p className="mt-1 text-lg font-semibold text-foreground">
                      <MetricValueDisplay value={unknownValue(regionMemberInquiryUnknownReason)} />
                    </p>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-muted p-8 text-sm text-muted-foreground lg:col-span-2">
              Regional coverage summaries appear once live calendar and overlay data are
              available.
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <BellRing className="h-5 w-5 text-primary" />
          <div>
            <h3 className="text-xl font-semibold text-foreground">Discovery feed</h3>
            <p className="text-sm text-muted-foreground">
              Registered metrics from <code>/v1/units/&#123;unit_id&#125;/metrics</code>, graded
              red / yellow / green by the stated threshold rule. An unmeasured value is
              &ldquo;Not measured&rdquo;, never green and never zero.
            </p>
          </div>
        </div>

        <DiscoveryFeed items={discoveryFeed} className="mt-6" />
      </div>
    </div>
  );
}

/** Monthly calendar-reach line chart. */
export function CalendarReachChart({
  reachTrend,
}: {
  reachTrend: { month: string; windows: number; covered: number }[];
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <h3 className="mb-4 text-lg font-semibold text-foreground">Calendar Reach Trend</h3>
      {reachTrend.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-muted p-8 text-sm text-muted-foreground">
          No calendar windows in the current feed, so there is no reach trend to plot.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={reachTrend}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="month" tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
            <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
            <Tooltip />
            <Line type="monotone" dataKey="windows" stroke="var(--primary)" strokeWidth={3} name="IA windows" />
            <Line type="monotone" dataKey="covered" stroke="var(--chart-2)" strokeWidth={3} name="Covered windows" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
