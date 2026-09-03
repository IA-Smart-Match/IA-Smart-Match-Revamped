import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Building2,
  CalendarDays,
  CalendarOff,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Clock3,
  MapPin,
  RefreshCw,
  ShieldCheck,
  Users,
} from "lucide-react";

import {
  fetchCalendarAssignments,
  fetchCalendarEvents,
  splitTags,
  type CalendarAssignmentSummary,
  type CalendarEventSummary,
} from "@/lib/api";
import { Button } from "../components/ui/button";
import { AccountableValue, SyntheticDataBanner } from "../components/provenance";
import { accountableDemoMetric } from "@/lib/metrics";
import {
  calendarDateKey,
  parseCalendarDate,
  partitionByResolvedDate,
  viewerTimeZone,
} from "@/lib/eventDates";

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

/**
 * Why this page can have no events at all.
 *
 * `GET /api/calendar/events` and `/api/calendar/assignments` are legacy
 * routes the current API does not serve — the repository's own performance
 * baseline records both as 404 (`docs/plans/perf-baseline-828.md`), and
 * `services/api/smartmatch_api/routers/events.py` declares no handlers for
 * the unit-scoped replacement yet (S3-S5). The OpenAPI contract
 * (`contracts/openapi/smartmatch.json`) exposes no event operation either.
 *
 * So the honest state for this screen is *unavailable*, not *empty* and not
 * *failed*: there is nothing to retry into. Rendering a month grid of
 * fixtures or an ICS stub here is the "silent ICS fallback shown as success"
 * that DESIGN.md §1.2 names outright.
 */
const CALENDAR_FEED_RETIRED_REASON =
  "This calendar reads the retired legacy routes GET /api/calendar/events and /api/calendar/assignments, which the current API does not serve. Unit-scoped event endpoints are S3-S5 work and the OpenAPI contract exposes no event operation yet, so there are no event records to draw.";

/** True when a rejection is the API telling us the route no longer exists. */
function isRetiredRoute(reason: unknown): boolean {
  return (
    typeof reason === "object" &&
    reason !== null &&
    (reason as { status?: unknown }).status === 404
  );
}

/**
 * The designed "this data source does not exist" state.
 *
 * Distinct from {@link FailureState} on purpose, and deliberately without a
 * Retry button: offering one would imply the data is coming back on this
 * build, which it is not.
 */
function UnavailableState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-2xl border border-slate-300 bg-slate-50 p-8">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-slate-200">
        <CalendarOff className="h-5 w-5 text-slate-600" aria-hidden="true" />
      </div>
      <p className="mt-3 text-center text-sm font-semibold text-slate-800">{title}</p>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm leading-6 text-slate-600">
        {message}
      </p>
    </div>
  );
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
    <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-rose-100">
        <AlertTriangle className="h-5 w-5 text-rose-600" />
      </div>
      <p className="mt-3 text-sm font-semibold text-rose-800">{title}</p>
      <p className="mt-1 text-sm text-rose-700">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

type CalendarView = "month" | "week" | "day";
type CoverageFilter = "all" | "covered" | "open";

interface DayCell {
  key: string;
  date: Date | null;
}

const parseLocalDate = parseCalendarDate;
const dateKey = calendarDateKey;

function sameDay(left: Date, right: Date) {
  return dateKey(left) === dateKey(right);
}

function startOfWeek(date: Date) {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  result.setDate(result.getDate() - result.getDay());
  return result;
}

function addDays(date: Date, days: number) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function buildMonthCells(date: Date): DayCell[] {
  const year = date.getFullYear();
  const month = date.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: DayCell[] = [];

  for (let index = 0; index < firstDay; index += 1) {
    cells.push({ key: `leading-${index}`, date: null });
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const cellDate = new Date(year, month, day);
    cells.push({ key: dateKey(cellDate), date: cellDate });
  }

  while (cells.length % 7 !== 0) {
    cells.push({ key: `trailing-${cells.length}`, date: null });
  }

  return cells;
}

function coverageTone(status: CalendarEventSummary["coverage_status"]) {
  switch (status) {
    case "covered":
      return "border-blue-200 bg-blue-50 text-blue-800";
    case "partial":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "needs_coverage":
      return "border-rose-200 bg-rose-50 text-rose-800";
    default:
      return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

function recoveryTone(status: CalendarAssignmentSummary["recovery_status"]) {
  switch (status) {
    case "Available":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "Needs Rest":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "Rest Recommended":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

function recoveryFill(status: CalendarAssignmentSummary["recovery_status"]) {
  switch (status) {
    case "Available":
      return "bg-emerald-500";
    case "Needs Rest":
      return "bg-amber-500";
    case "Rest Recommended":
      return "bg-rose-500";
    default:
      return "bg-slate-400";
  }
}

// ADR-0011: a null fatigue/count means no evidence, not a measured zero — it
// renders as "Unknown", never as "0%" or "0".
function formatPercent(value: number | null) {
  return value === null ? "Unknown" : `${Math.round(value * 100)}%`;
}

function formatCount(value: number | null) {
  return value === null ? "Unknown" : `${value}`;
}

/** Renders a 0..1 ratio as a whole-number percentage for `AccountableValue`. */
function formatRatioPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

/**
 * Rolls the loaded rows up into the four header tiles.
 *
 * Each field is `number | null`, and `null` means the tile has no evidence
 * behind it — either the feed that would supply it did not answer, or (for
 * coverage rate) there is no denominator to divide by. ADR-0011 rule 1: a
 * count of zero rows returned by a *failed* request is not a measurement of
 * zero, and the previous version of this page rendered exactly that — an
 * unreachable assignments feed produced "0 on cooldown", which reads as
 * "nobody needs rest".
 */
function summaryCounts(
  events: CalendarEventSummary[],
  assignments: CalendarAssignmentSummary[],
  eventsAvailable: boolean,
  assignmentsAvailable: boolean,
) {
  const covered = events.filter((event) => event.coverage_status === "covered").length;
  const needsCoverage = events.filter((event) => event.coverage_status === "needs_coverage").length;
  const knownFatigue = assignments
    .map((assignment) => assignment.volunteer_fatigue)
    .filter((value): value is number => value !== null);
  const averageFatigue = knownFatigue.length
    ? knownFatigue.reduce((sum, value) => sum + value, 0) / knownFatigue.length
    : null;
  const cooldownCount = assignments.filter((assignment) => assignment.recovery_status === "Rest Recommended").length;

  return {
    covered: eventsAvailable ? covered : null,
    needsCoverage: eventsAvailable ? needsCoverage : null,
    // A coverage *rate* with no scheduled windows has no denominator. It is
    // unknown, not 0% — "no data yet versus zero" (DESIGN.md §1.2).
    coverageRate: eventsAvailable && events.length > 0 ? covered / events.length : null,
    averageFatigue: assignmentsAvailable ? averageFatigue : null,
    cooldownCount: assignmentsAvailable ? cooldownCount : null,
  };
}

export function Calendar() {
  const [view, setView] = useState<CalendarView>("month");
  const [coverageFilter, setCoverageFilter] = useState<CoverageFilter>("all");
  const [focusDate, setFocusDate] = useState(() => new Date());
  const [events, setEvents] = useState<CalendarEventSummary[]>([]);
  const [assignments, setAssignments] = useState<CalendarAssignmentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [isMockData, setIsMockData] = useState(false);
  const [eventsAvailable, setEventsAvailable] = useState(false);
  const [assignmentsAvailable, setAssignmentsAvailable] = useState(false);
  // `/api/calendar/*` are retired legacy routes. A 404 here is not a transient
  // failure a Retry can clear, so it gets its own designed state rather than
  // an error banner that invites the viewer to try again forever.
  const [feedRetired, setFeedRetired] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadFailed(false);
    setFeedRetired(false);
    setError(null);

    Promise.allSettled([fetchCalendarEvents(), fetchCalendarAssignments()])
      .then(([eventResult, assignmentResult]) => {
        if (!active) {
          return;
        }

        let anyMock = false;

        if (eventResult.status === "fulfilled") {
          const { data, isMockData } = eventResult.value;
          setEvents(data);
          setEventsAvailable(true);
          if (isMockData) anyMock = true;
        } else {
          // Events are the calendar's core data — without them there is
          // nothing honest to render, so surface a failure state instead of
          // substituting fixture events.
          setEvents([]);
          setAssignments([]);
          setEventsAvailable(false);
          setAssignmentsAvailable(false);
          setFeedRetired(isRetiredRoute(eventResult.reason));
          setLoadFailed(true);
          setError(getErrorMessage(eventResult.reason, "Failed to load the calendar."));
          setIsMockData(false);
          return;
        }

        if (assignmentResult.status === "fulfilled") {
          const { data, isMockData } = assignmentResult.value;
          setAssignments(data);
          setAssignmentsAvailable(true);
          if (isMockData) anyMock = true;
        } else {
          // Assignment overlays are supplementary — keep showing the real
          // events and surface a non-blocking warning instead of fabricating
          // overlay rows. Every tile they back goes to unknown, not to zero.
          setAssignments([]);
          setAssignmentsAvailable(false);
          setError(
            `Assignment overlays are unavailable: ${getErrorMessage(assignmentResult.reason, "Request failed.")}`,
          );
        }

        setIsMockData(anyMock);
      })
      .catch((err: unknown) => {
        if (!active) {
          return;
        }
        setEvents([]);
        setAssignments([]);
        setEventsAvailable(false);
        setAssignmentsAvailable(false);
        setFeedRetired(isRetiredRoute(err));
        setLoadFailed(true);
        setIsMockData(false);
        setError(getErrorMessage(err, "Failed to load calendar."));
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [reloadToken]);

  const monthCells = buildMonthCells(focusDate);
  const weekStart = startOfWeek(focusDate);
  const weekDays = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
  const activeDayKey = dateKey(focusDate);

  const filteredEvents = events.filter((event) => {
    if (coverageFilter === "covered") {
      return event.coverage_status === "covered";
    }
    if (coverageFilter === "open") {
      return event.coverage_status !== "covered";
    }
    return true;
  });

  // Rows whose date does not resolve are kept *out* of the grid and listed
  // separately below it (ADR-0010): a cell is a claim that something happens
  // on that day, and we cannot make that claim for a record with no date.
  const { byDateKey: assignmentByDate, unresolved: unresolvedAssignments } =
    partitionByResolvedDate(assignments, (assignment) => assignment.event_date);
  const { byDateKey: eventByDate, unresolved: unresolvedEvents } = partitionByResolvedDate(
    filteredEvents,
    (event) => event.event_date,
  );

  const selectedDayEvents = eventByDate.get(activeDayKey) ?? [];
  const selectedDayAssignments = (assignmentByDate.get(activeDayKey) ?? []).filter((assignment) =>
    selectedDayEvents.some(
      (event) => event.event_id === assignment.event_id || event.event_name === assignment.event_name,
    ),
  );
  const metrics = summaryCounts(events, assignments, eventsAvailable, assignmentsAvailable);

  // Provenance for calendar-derived tiles: a feed that answered with rows it
  // labelled demo/csv is synthetic; one that did not answer at all is
  // synthetic too, because whatever the tile shows is not an observation.
  const eventProvenance = eventsAvailable && !isMockData ? ("observed" as const) : ("synthetic" as const);
  const assignmentProvenance =
    assignmentsAvailable && !isMockData ? ("observed" as const) : ("synthetic" as const);

  const coverageRateMetric = accountableDemoMetric(
    "Coverage rate",
    "Share of the loaded calendar windows the feed reports as covered.",
    metrics.coverageRate,
    {
      provenance: eventProvenance,
      unknownReason: eventsAvailable
        ? "No calendar windows are loaded, so a coverage rate has no denominator. An empty set is unknown, not 0%."
        : CALENDAR_FEED_RETIRED_REASON,
    },
  );
  const needsCoverageMetric = accountableDemoMetric(
    "Needs coverage",
    "Loaded calendar windows the feed reports as needing coverage.",
    metrics.needsCoverage,
    { provenance: eventProvenance, unknownReason: CALENDAR_FEED_RETIRED_REASON },
  );
  const averageFatigueMetric = accountableDemoMetric(
    "Average fatigue",
    "Mean of the fatigue values the assignment overlays actually carried; overlays without one are excluded rather than counted as zero.",
    metrics.averageFatigue,
    {
      provenance: assignmentProvenance,
      unknownReason: assignmentsAvailable
        ? "No loaded assignment overlay carries a fatigue value, so there is nothing to average."
        : CALENDAR_FEED_RETIRED_REASON,
    },
  );
  const cooldownMetric = accountableDemoMetric(
    "On cooldown",
    "Assignment overlays whose recovery status is Rest Recommended.",
    metrics.cooldownCount,
    { provenance: assignmentProvenance, unknownReason: CALENDAR_FEED_RETIRED_REASON },
  );

  const periodLabel =
    view === "month"
      ? focusDate.toLocaleDateString("en-US", { month: "long", year: "numeric" })
      : view === "week"
        ? `${weekDays[0].toLocaleDateString("en-US", { month: "short", day: "numeric" })} - ${weekDays[6].toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`
        : focusDate.toLocaleDateString("en-US", {
            weekday: "long",
            month: "long",
            day: "numeric",
            year: "numeric",
          });

  const movePeriod = (direction: number) => {
    setFocusDate((current) => {
      const next = new Date(current);
      if (view === "month") {
        next.setMonth(current.getMonth() + direction);
      } else if (view === "week") {
        next.setDate(current.getDate() + direction * 7);
      } else {
        next.setDate(current.getDate() + direction);
      }
      return next;
    });
  };

  const jumpToToday = () => {
    setFocusDate(new Date());
    setView("month");
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="h-10 w-64 animate-pulse rounded bg-slate-200" />
        <div className="h-24 animate-pulse rounded-3xl border border-slate-200 bg-white shadow-sm" />
        <div className="h-[540px] animate-pulse rounded-3xl border border-slate-200 bg-white shadow-sm" />
      </div>
    );
  }

  if (loadFailed) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-700">
            Master calendar
          </p>
          <h1 className="text-3xl font-semibold text-slate-900">Coordinator scheduling view</h1>
        </div>
        {feedRetired ? (
          <UnavailableState
            title="The month calendar has no event source yet"
            message={CALENDAR_FEED_RETIRED_REASON}
          />
        ) : (
          <FailureState
            title="The calendar could not be loaded"
            message={error ?? "Failed to load calendar."}
            onRetry={() => setReloadToken((token) => token + 1)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-700">
          Master calendar
        </p>
        <h1 className="text-3xl font-semibold text-slate-900">Coordinator scheduling view</h1>
        <p className="text-slate-600">
          Track coverage, assignment overlays, and volunteer recovery without leaving the calendar.
          Dates are shown in {viewerTimeZone()}; the retired feed carries no per-event zone, so no
          event time on this page is rendered in the event&apos;s own zone yet (ADR-0010).
        </p>
        {/* DESIGN.md §1.1 singles the synthetic label out as needing to be
            unmistakable. A chip beside the heading is not that, so a
            fixture-backed calendar gets the full banner. */}
        {isMockData ? (
          <SyntheticDataBanner reason="The calendar feed answered with demo/CSV rows, not live records. Every window, overlay, and count below is fixture data." />
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {/* Every tile below routes its value through `AccountableValue`, so a
            number the page could not measure renders as "Unknown" with the
            reason attached rather than as a confident 0 (ADR-0011 rule 1). */}
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Coverage rate</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">
            <AccountableValue metric={coverageRateMetric} formatNumber={formatRatioPercent} />
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {metrics.covered === null
              ? "Coverage is unknown while the calendar feed is unavailable."
              : `${metrics.covered} event${metrics.covered === 1 ? "" : "s"} already covered`}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Needs coverage</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">
            <AccountableValue metric={needsCoverageMetric} />
          </p>
          <p className="mt-1 text-sm text-slate-600">Open windows that still need a volunteer</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Average fatigue</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">
            <AccountableValue metric={averageFatigueMetric} formatNumber={formatRatioPercent} />
          </p>
          <p className="mt-1 text-sm text-slate-600">Recovery posture from assignment overlays</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">On cooldown</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">
            <AccountableValue metric={cooldownMetric} />
          </p>
          <p className="mt-1 text-sm text-slate-600">Volunteers that should be left untouched</p>
        </div>
      </div>

      <div className="rounded-3xl border border-blue-100 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white">
              <CalendarRange className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-700">
                {periodLabel} · {viewerTimeZone()}
              </p>
              <h2 className="text-2xl font-semibold text-slate-900">
                {view === "month" ? "Month grid" : view === "week" ? "Week agenda" : "Day detail"}
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Coverage badges are derived from the coordinator-facing calendar contract.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-1">
              {(["month", "week", "day"] as CalendarView[]).map((candidate) => (
                <button
                  key={candidate}
                  type="button"
                  onClick={() => setView(candidate)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    view === candidate
                      ? "bg-blue-600 text-white shadow-sm"
                      : "text-slate-600 hover:bg-white"
                  }`}
                >
                  {candidate[0].toUpperCase() + candidate.slice(1)}
                </button>
              ))}
            </div>

            <div className="inline-flex rounded-full border border-slate-200 bg-white p-1 shadow-sm">
              <button
                type="button"
                onClick={() => movePeriod(-1)}
                className="rounded-full p-2 text-slate-600 transition hover:bg-slate-100"
                aria-label="Previous period"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={jumpToToday}
                className="rounded-full px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
              >
                Today
              </button>
              <button
                type="button"
                onClick={() => movePeriod(1)}
                className="rounded-full p-2 text-slate-600 transition hover:bg-slate-100"
                aria-label="Next period"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-1">
            {(["all", "covered", "open"] as CoverageFilter[]).map((candidate) => (
              <button
                key={candidate}
                type="button"
                onClick={() => setCoverageFilter(candidate)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  coverageFilter === candidate
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-white"
                }`}
              >
                {candidate === "all" ? "All events" : candidate === "covered" ? "Covered" : "Needs coverage"}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 font-medium text-blue-700">
              <ShieldCheck className="h-4 w-4" />
              IA covered
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 font-medium text-amber-700">
              <Clock3 className="h-4 w-4" />
              Partial coverage
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-rose-200 bg-rose-50 px-3 py-1 font-medium text-rose-700">
              <Users className="h-4 w-4" />
              Needs volunteers
            </span>
          </div>
        </div>
      </div>

      {error ? (
        <FailureState
          title="Some calendar data is unavailable"
          message={error}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      ) : null}

      {view === "month" ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="grid grid-cols-7 gap-3">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
              <div key={label} className="pb-2 text-center text-sm font-semibold text-slate-600">
                {label}
              </div>
            ))}

            {monthCells.map((cell) =>
              cell.date ? (
                <button
                  key={cell.key}
                  type="button"
                  onClick={() => {
                    setFocusDate(cell.date ?? focusDate);
                    setView("day");
                  }}
                  className={`group min-h-[145px] rounded-2xl border p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md ${
                    sameDay(cell.date, new Date())
                      ? "border-blue-200 bg-blue-50/70"
                      : "border-slate-200 bg-slate-50/60"
                  }`}
                >
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <span
                      className={`text-base font-semibold ${
                        sameDay(cell.date, new Date()) ? "text-blue-700" : "text-slate-900"
                      }`}
                    >
                      {cell.date.getDate()}
                    </span>
                    {eventByDate.get(dateKey(cell.date))?.length ? (
                      <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-600 shadow-sm">
                        {eventByDate.get(dateKey(cell.date))?.length}
                        {eventByDate.get(dateKey(cell.date))?.length === 1 ? " event" : " events"}
                      </span>
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    {(eventByDate.get(dateKey(cell.date)) ?? []).slice(0, 2).map((event) => (
                      <div
                        key={event.event_id}
                        className={`rounded-xl border px-3 py-2 ${coverageTone(event.coverage_status)}`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-[12px] font-semibold">{event.event_name}</p>
                          <span className="rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold">
                            {event.assignment_count} assigned
                          </span>
                        </div>
                        <p className="mt-1 truncate text-[11px] opacity-80">
                          {event.coverage_label}
                        </p>
                      </div>
                    ))}
                    {(eventByDate.get(dateKey(cell.date))?.length ?? 0) > 2 ? (
                      <p className="text-xs font-medium text-slate-500">
                        +{(eventByDate.get(dateKey(cell.date))?.length ?? 0) - 2} more windows
                      </p>
                    ) : null}
                  </div>
                </button>
              ) : (
                <div key={cell.key} className="min-h-[145px] rounded-2xl border border-transparent" />
              ),
            )}
          </div>

          {/*
            ADR-0010 / DESIGN.md §1.8: an event whose date does not resolve
            "renders as unresolved, not as a guess". These rows used to be
            dropped into today's cell by a `new Date()` fallback, which made a
            record with no date indistinguishable from one happening today.
            They are named here instead, outside the grid.
          */}
          {unresolvedEvents.length || unresolvedAssignments.length ? (
            <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  className="mt-0.5 h-5 w-5 shrink-0 text-amber-700"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-amber-900">
                    Not placed on the calendar: {unresolvedEvents.length} event
                    {unresolvedEvents.length === 1 ? "" : "s"}
                    {unresolvedAssignments.length
                      ? ` and ${unresolvedAssignments.length} assignment overlay${unresolvedAssignments.length === 1 ? "" : "s"}`
                      : ""}{" "}
                    with an unresolved date
                  </p>
                  <p className="mt-1 text-sm leading-6 text-amber-800">
                    These records carry no date that resolves, so no day cell can honestly claim
                    them. They are listed here rather than guessed onto a date.
                  </p>
                  <ul className="mt-3 space-y-1 text-sm text-amber-900">
                    {unresolvedEvents.slice(0, 8).map((event) => (
                      <li key={`unresolved-${event.event_id}`} className="truncate">
                        {event.event_name || "Untitled event"} · {event.region} · date unresolved
                      </li>
                    ))}
                    {unresolvedEvents.length > 8 ? (
                      <li className="font-medium">
                        +{unresolvedEvents.length - 8} more with unresolved dates
                      </li>
                    ) : null}
                  </ul>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {view === "week" ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="grid gap-3 lg:grid-cols-7">
            {weekDays.map((day) => {
              const dayEvents = filteredEvents.filter((event) => {
                const parsed = parseLocalDate(event.event_date);
                return parsed ? sameDay(parsed, day) : false;
              });

              return (
                <button
                  key={dateKey(day)}
                  type="button"
                  onClick={() => {
                    setFocusDate(day);
                    setView("day");
                  }}
                  className={`min-h-[320px] rounded-2xl border p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md ${
                    sameDay(day, new Date()) ? "border-blue-200 bg-blue-50/70" : "border-slate-200 bg-slate-50/60"
                  }`}
                >
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        {day.toLocaleDateString("en-US", { weekday: "short" })}
                      </p>
                      <p className={`text-lg font-semibold ${sameDay(day, new Date()) ? "text-blue-700" : "text-slate-900"}`}>
                        {day.getDate()}
                      </p>
                    </div>
                    <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 shadow-sm">
                      {dayEvents.length}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {dayEvents.slice(0, 3).map((event) => (
                      <div
                        key={event.event_id}
                        className={`rounded-xl border px-3 py-2 ${coverageTone(event.coverage_status)}`}
                      >
                        <p className="truncate text-sm font-semibold">{event.event_name}</p>
                        <p className="mt-1 truncate text-[11px] opacity-80">{event.region}</p>
                        <div className="mt-2 flex items-center justify-between text-[11px] font-semibold">
                          <span>{event.coverage_label}</span>
                          <span>{event.assignment_count} assigned</span>
                        </div>
                      </div>
                    ))}
                    {dayEvents.length > 3 ? (
                      <p className="text-xs font-medium text-slate-500">+{dayEvents.length - 3} more</p>
                    ) : null}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {view === "day" ? (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.08fr_0.92fr]">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-700">
                  Day detail
                </p>
                <h3 className="text-2xl font-semibold text-slate-900">
                  {focusDate.toLocaleDateString("en-US", {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                </h3>
                <p className="mt-1 text-sm text-slate-600">
                  The coordinator can see coverage, volunteers, and recovery posture in one place.
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-right">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Events</p>
                <p className="text-2xl font-semibold text-slate-900">{selectedDayEvents.length}</p>
              </div>
            </div>

            <div className="space-y-4">
              {selectedDayEvents.length ? (
                selectedDayEvents.map((event) => {
                  const eventAssignments = selectedDayAssignments.filter(
                    (assignment) =>
                      assignment.event_id === event.event_id ||
                      assignment.event_name === event.event_name,
                  );

                  return (
                    <article
                      key={event.event_id}
                      className={`rounded-3xl border p-5 ${coverageTone(event.coverage_status)}`}
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <h4 className="text-xl font-semibold text-slate-900">{event.event_name}</h4>
                            <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold shadow-sm">
                              {event.coverage_label}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-700">
                            <span className="inline-flex items-center gap-2">
                              <MapPin className="h-4 w-4 text-blue-700" />
                              {event.region}
                            </span>
                            <span className="inline-flex items-center gap-2">
                              <CalendarDays className="h-4 w-4 text-blue-700" />
                              {/* A date with no resolvable value says so; it is
                                  never printed as a raw or guessed string. */}
                              {parseLocalDate(event.event_date)
                                ? `${event.event_date} (${viewerTimeZone()})`
                                : "Date unresolved"}
                            </span>
                            <span className="inline-flex items-center gap-2">
                              <ShieldCheck className="h-4 w-4 text-blue-700" />
                              {event.assignment_count} assigned
                            </span>
                          </div>

                          <div className="flex flex-wrap gap-2">
                            {event.nearby_universities.slice(0, 4).map((campus) => (
                              <span
                                key={campus}
                                className="rounded-full border border-white/70 bg-white/80 px-3 py-1 text-xs font-medium text-slate-700"
                              >
                                {campus}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3 shadow-sm">
                          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                            Lecture window
                          </p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">
                            {event.suggested_lecture_window}
                          </p>
                        </div>
                      </div>

                      <div className="mt-4">
                        <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">
                          Assignment overlays
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {eventAssignments.length ? (
                            eventAssignments.slice(0, 4).map((assignment) => (
                              <span
                                key={assignment.assignment_id}
                                className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${recoveryTone(
                                  assignment.recovery_status,
                                )}`}
                              >
                                <span
                                  className={`h-2.5 w-2.5 rounded-full ${recoveryFill(
                                    assignment.recovery_status,
                                  )}`}
                                />
                                {assignment.volunteer_name}
                              </span>
                            ))
                          ) : (
                            <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-medium text-slate-600">
                              No assignment overlay rows
                            </span>
                          )}
                          {eventAssignments.length > 4 ? (
                            <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-medium text-slate-600">
                              +{eventAssignments.length - 4} more
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </article>
                  );
                })
              ) : (
                <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-slate-600">
                  No event windows are scheduled for this day.
                </div>
              )}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-4 flex items-center gap-2">
                <Users className="h-5 w-5 text-blue-700" />
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">Assignment overlays</h3>
                  <p className="text-sm text-slate-600">
                    Coverage-aware assignments and recovery status for the selected day.
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {selectedDayAssignments.length ? (
                  selectedDayAssignments.map((assignment) => (
                    <div
                      key={assignment.assignment_id}
                      className="rounded-2xl border border-slate-200 bg-slate-50 p-4 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-slate-900">{assignment.volunteer_name}</p>
                          <p className="text-sm text-slate-600">
                            {assignment.volunteer_title || "Board volunteer"}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            {assignment.event_name} · {assignment.stage}
                          </p>
                        </div>
                        <span
                          className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${recoveryTone(
                            assignment.recovery_status,
                          )}`}
                        >
                          <span className={`mr-2 h-2.5 w-2.5 rounded-full ${recoveryFill(assignment.recovery_status)}`} />
                          {assignment.recovery_label}
                        </span>
                      </div>

                      <div className="mt-4 grid grid-cols-3 gap-3">
                        <div className="rounded-xl bg-white px-3 py-2">
                          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                            Fatigue
                          </p>
                          <p className="mt-1 text-sm font-semibold text-slate-900">
                            {formatPercent(assignment.volunteer_fatigue)}
                          </p>
                        </div>
                        <div className="rounded-xl bg-white px-3 py-2">
                          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                            Recent
                          </p>
                          <p className="mt-1 text-sm font-semibold text-slate-900">
                            {formatCount(assignment.recent_assignment_count)}
                          </p>
                        </div>
                        <div className="rounded-xl bg-white px-3 py-2">
                          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                            Cadence
                          </p>
                          <p className="mt-1 text-sm font-semibold text-slate-900">
                            {assignment.event_cadence || "n/a"}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-slate-600">
                    No assignments were found for this day.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-blue-700" />
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">Coverage notes</h3>
                  <p className="text-sm text-slate-600">
                    Simple labels that help coordinators see where to focus next.
                  </p>
                </div>
              </div>

              <div className="mt-4 space-y-2">
                {(selectedDayEvents.length ? selectedDayEvents : filteredEvents.slice(0, 3)).map(
                  (event) => (
                    <div
                      key={`note-${event.event_id}`}
                      className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                    >
                      <div>
                        <p className="font-medium text-slate-900">{event.event_name}</p>
                        <p className="text-sm text-slate-600">{event.region}</p>
                      </div>
                      <span className={`rounded-full border px-3 py-1 text-xs font-medium ${coverageTone(event.coverage_status)}`}>
                        {event.coverage_label}
                      </span>
                    </div>
                  ),
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
