/**
 * Admin / coordinator master calendar (legacy synthetic-pilot surface).
 *
 * **Before replacing this month grid with an agenda, read
 * `apps/web/DESIGN.md` §2.1.** Two authorised documents look like they
 * disagree here, and each is convincing on its own:
 *
 * - `docs/architecture/engagement-model.md` §5 (D-11) says "Not a month
 *   grid" — but scoped to the *student* surface, and argued from a
 *   student-specific harm (Fix #10: a sparse grid reads as a dead chapter to
 *   someone deciding whether to attend).
 * - The ratified G1 worksheet records the stakeholder directive "Month
 *   calendar bottom of events page | Legacy events UI | Presentation".
 *
 * A coordinator opens this page to find *gaps*, so an empty cell is the
 * signal they came for rather than a discouraging void. That is why the shape
 * that is wrong on the student agenda is right here. D-11 has not settled
 * whether the agenda rule binds every audience; until it does, this grid
 * stays and the student surface does not get one.
 *
 * What this file must hold regardless of that outcome (ADR-0010, and §5
 * insists on it too): dates render in a named zone, `date_only` renders as a
 * date, and a record whose date does not resolve is listed *outside* the grid
 * rather than guessed onto a day — see `@/lib/eventDates`.
 */
import { useEffect, useState } from "react";
import {
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Clock3,
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
import {
  calendarSourceProvenance,
  calendarSyntheticReason,
} from "@/lib/calendarProvenance";
import {
  DayDetailView,
  FailureState,
  MonthGridView,
  UnavailableState,
  WeekAgendaView,
  coverageTone,
  formatCount,
  formatPercent,
  recoveryFill,
  recoveryTone,
  sameDay,
  type DayCell,
} from "./CalendarSections";

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

type CalendarView = "month" | "week" | "day";
type CoverageFilter = "all" | "covered" | "open";

const parseLocalDate = parseCalendarDate;
const dateKey = calendarDateKey;

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
  // Keep provenance per endpoint. The two legacy routes can legitimately
  // return different source kinds during migration, so one combined flag
  // would mislabel live event metrics when only assignment overlays are demo
  // data (and vice versa).
  const [eventsAreMockData, setEventsAreMockData] = useState(false);
  const [assignmentsAreMockData, setAssignmentsAreMockData] = useState(false);
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

        if (eventResult.status === "fulfilled") {
          const { data, isMockData } = eventResult.value;
          setEvents(data);
          setEventsAvailable(true);
          setEventsAreMockData(isMockData);
        } else {
          // Events are the calendar's core data — without them there is
          // nothing honest to render, so surface a failure state instead of
          // substituting fixture events.
          setEvents([]);
          setAssignments([]);
          setEventsAvailable(false);
          setAssignmentsAvailable(false);
          setEventsAreMockData(false);
          setAssignmentsAreMockData(false);
          setFeedRetired(isRetiredRoute(eventResult.reason));
          setLoadFailed(true);
          setError(getErrorMessage(eventResult.reason, "Failed to load the calendar."));
          return;
        }

        if (assignmentResult.status === "fulfilled") {
          const { data, isMockData } = assignmentResult.value;
          setAssignments(data);
          setAssignmentsAvailable(true);
          setAssignmentsAreMockData(isMockData);
        } else {
          // Assignment overlays are supplementary — keep showing the real
          // events and surface a non-blocking warning instead of fabricating
          // overlay rows. Every tile they back goes to unknown, not to zero.
          setAssignments([]);
          setAssignmentsAvailable(false);
          setAssignmentsAreMockData(false);
          setError(
            `Assignment overlays are unavailable: ${getErrorMessage(assignmentResult.reason, "Request failed.")}`,
          );
        }

      })
      .catch((err: unknown) => {
        if (!active) {
          return;
        }
        setEvents([]);
        setAssignments([]);
        setEventsAvailable(false);
        setAssignmentsAvailable(false);
        setEventsAreMockData(false);
        setAssignmentsAreMockData(false);
        setFeedRetired(isRetiredRoute(err));
        setLoadFailed(true);
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
  const eventProvenance = calendarSourceProvenance(eventsAvailable, eventsAreMockData);
  const assignmentProvenance = calendarSourceProvenance(
    assignmentsAvailable,
    assignmentsAreMockData,
  );
  const syntheticDataReason = calendarSyntheticReason(
    eventsAreMockData,
    assignmentsAreMockData,
  );

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
        <div className="h-10 w-64 animate-pulse rounded bg-muted" />
        <div className="h-24 animate-pulse rounded-3xl border border-border bg-card shadow-sm" />
        <div className="h-[540px] animate-pulse rounded-3xl border border-border bg-card shadow-sm" />
      </div>
    );
  }

  if (loadFailed) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold text-foreground">Coordinator scheduling view</h1>
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
        <h1 className="text-3xl font-semibold text-foreground">Coordinator scheduling view</h1>
        <p className="text-muted-foreground">
          Track coverage, assignment overlays, and volunteer recovery without leaving the calendar.
          Dates are shown in {viewerTimeZone()}; the retired feed carries no per-event zone, so no
          event time on this page is rendered in the event&apos;s own zone yet (ADR-0010).
        </p>
        {/* DESIGN.md §1.1 singles the synthetic label out as needing to be
            unmistakable. A chip beside the heading is not that, so a
            fixture-backed calendar gets the full banner. */}
        {syntheticDataReason ? (
          <SyntheticDataBanner reason={syntheticDataReason} />
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {/* Every tile below routes its value through `AccountableValue`, so a
            number the page could not measure renders as "Unknown" with the
            reason attached rather than as a confident 0 (ADR-0011 rule 1). */}
        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Coverage rate</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue metric={coverageRateMetric} formatNumber={formatRatioPercent} />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {metrics.covered === null
              ? "Coverage is unknown while the calendar feed is unavailable."
              : `${metrics.covered} event${metrics.covered === 1 ? "" : "s"} already covered`}
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Needs coverage</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue metric={needsCoverageMetric} />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">Open windows that still need a volunteer</p>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Average fatigue</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue metric={averageFatigueMetric} formatNumber={formatRatioPercent} />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">Recovery posture from assignment overlays</p>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">On cooldown</p>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            <AccountableValue metric={cooldownMetric} />
          </p>
          <p className="mt-1 text-sm text-muted-foreground">Volunteers that should be left untouched</p>
        </div>
      </div>

      <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-white">
              <CalendarRange className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-primary">
                {periodLabel} · {viewerTimeZone()}
              </p>
              <h2 className="text-2xl font-semibold text-foreground">
                {view === "month" ? "Month grid" : view === "week" ? "Week agenda" : "Day detail"}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Coverage badges are derived from the coordinator-facing calendar contract.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex rounded-full border border-border bg-muted p-1">
              {(["month", "week", "day"] as CalendarView[]).map((candidate) => (
                <button
                  key={candidate}
                  type="button"
                  onClick={() => setView(candidate)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    view === candidate
                      ? "bg-primary text-white shadow-sm"
                      : "text-muted-foreground hover:bg-card"
                  }`}
                >
                  {candidate[0].toUpperCase() + candidate.slice(1)}
                </button>
              ))}
            </div>

            <div className="inline-flex rounded-full border border-border bg-card p-1 shadow-sm">
              <button
                type="button"
                onClick={() => movePeriod(-1)}
                className="rounded-full p-2 text-muted-foreground transition hover:bg-muted"
                aria-label="Previous period"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={jumpToToday}
                className="rounded-full px-4 py-2 text-sm font-medium text-foreground/80 transition hover:bg-muted"
              >
                Today
              </button>
              <button
                type="button"
                onClick={() => movePeriod(1)}
                className="rounded-full p-2 text-muted-foreground transition hover:bg-muted"
                aria-label="Next period"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-full border border-border bg-muted p-1">
            {(["all", "covered", "open"] as CoverageFilter[]).map((candidate) => (
              <button
                key={candidate}
                type="button"
                onClick={() => setCoverageFilter(candidate)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  coverageFilter === candidate
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-card"
                }`}
              >
                {candidate === "all" ? "All events" : candidate === "covered" ? "Covered" : "Needs coverage"}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-accent px-3 py-1 font-medium text-primary">
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
        <MonthGridView
          monthCells={monthCells}
          eventByDate={eventByDate}
          unresolvedEvents={unresolvedEvents}
          unresolvedAssignments={unresolvedAssignments}
          onSelectDay={(date) => {
            setFocusDate(date);
            setView("day");
          }}
        />
      ) : null}

      {view === "week" ? (
        <WeekAgendaView
          weekDays={weekDays}
          filteredEvents={filteredEvents}
          onSelectDay={(date) => {
            setFocusDate(date);
            setView("day");
          }}
        />
      ) : null}

      {view === "day" ? (
        <DayDetailView
          focusDate={focusDate}
          selectedDayEvents={selectedDayEvents}
          selectedDayAssignments={selectedDayAssignments}
          filteredEvents={filteredEvents}
        />
      ) : null}
    </div>
  );
}
