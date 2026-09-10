/**
 * Presentational states and view sections extracted from `Calendar.tsx`
 * (D1-M2 restyle) so the page component stays under the file-size ceiling.
 *
 * Every component here is presentation-only: it renders values its caller
 * already computed. Moving JSX here must not change what the calendar shows
 * or how it behaves (ADR-0010/ADR-0011 rules on dates and unknown values
 * stay enforced by the caller's data, not by anything in this file).
 */
import {
  AlertTriangle,
  Building2,
  CalendarDays,
  CalendarOff,
  MapPin,
  RefreshCw,
  ShieldCheck,
  Users,
} from "lucide-react";

import type { CalendarAssignmentSummary, CalendarEventSummary } from "@/lib/api";
import { Button } from "../components/ui/button";
import { calendarDateKey, parseCalendarDate, viewerTimeZone } from "@/lib/eventDates";

const parseLocalDate = parseCalendarDate;
const dateKey = calendarDateKey;

export function sameDay(left: Date, right: Date) {
  return dateKey(left) === dateKey(right);
}

export interface DayCell {
  key: string;
  date: Date | null;
}

/**
 * The designed "this data source does not exist" state.
 *
 * Distinct from {@link FailureState} on purpose, and deliberately without a
 * Retry button: offering one would imply the data is coming back on this
 * build, which it is not.
 */
export function UnavailableState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-2xl border border-border bg-muted p-8">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-muted">
        <CalendarOff className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      </div>
      <p className="mt-3 text-center text-sm font-semibold text-foreground">{title}</p>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm leading-6 text-muted-foreground">
        {message}
      </p>
    </div>
  );
}

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

export function coverageTone(status: CalendarEventSummary["coverage_status"]) {
  switch (status) {
    case "covered":
      return "border-primary/20 bg-accent text-primary";
    case "partial":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "needs_coverage":
      return "border-rose-200 bg-rose-50 text-rose-800";
    default:
      return "border-border bg-muted text-foreground/80";
  }
}

export function recoveryTone(status: CalendarAssignmentSummary["recovery_status"]) {
  switch (status) {
    case "Available":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "Needs Rest":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "Rest Recommended":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-border bg-muted text-foreground/80";
  }
}

export function recoveryFill(status: CalendarAssignmentSummary["recovery_status"]) {
  switch (status) {
    case "Available":
      return "bg-emerald-500";
    case "Needs Rest":
      return "bg-amber-500";
    case "Rest Recommended":
      return "bg-rose-500";
    default:
      return "bg-muted-foreground";
  }
}

// ADR-0011: a null fatigue/count means no evidence, not a measured zero — it
// renders as "Unknown", never as "0%" or "0".
export function formatPercent(value: number | null) {
  return value === null ? "Unknown" : `${Math.round(value * 100)}%`;
}

export function formatCount(value: number | null) {
  return value === null ? "Unknown" : `${value}`;
}

/** Month grid: one cell per day, with unresolved-date records listed below. */
export function MonthGridView({
  monthCells,
  eventByDate,
  unresolvedEvents,
  unresolvedAssignments,
  onSelectDay,
}: {
  monthCells: DayCell[];
  eventByDate: Map<string, CalendarEventSummary[]>;
  unresolvedEvents: CalendarEventSummary[];
  unresolvedAssignments: CalendarAssignmentSummary[];
  onSelectDay: (date: Date) => void;
}) {
  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
      <div className="grid grid-cols-7 gap-3">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
          <div key={label} className="pb-2 text-center text-sm font-semibold text-muted-foreground">
            {label}
          </div>
        ))}

        {monthCells.map((cell) =>
          cell.date ? (
            <button
              key={cell.key}
              type="button"
              onClick={() => onSelectDay(cell.date as Date)}
              className={`group min-h-[145px] rounded-2xl border p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md ${
                sameDay(cell.date, new Date())
                  ? "border-primary/20 bg-accent/70"
                  : "border-border bg-muted/60"
              }`}
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <span
                  className={`text-base font-semibold ${
                    sameDay(cell.date, new Date()) ? "text-primary" : "text-foreground"
                  }`}
                >
                  {cell.date.getDate()}
                </span>
                {eventByDate.get(dateKey(cell.date))?.length ? (
                  <span className="rounded-full bg-card px-2 py-0.5 text-[11px] font-semibold text-muted-foreground shadow-sm">
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
                      <span className="rounded-full bg-card/90 px-2 py-0.5 text-[10px] font-semibold">
                        {event.assignment_count} assigned
                      </span>
                    </div>
                    <p className="mt-1 truncate text-[11px] opacity-80">
                      {event.coverage_label}
                    </p>
                  </div>
                ))}
                {(eventByDate.get(dateKey(cell.date))?.length ?? 0) > 2 ? (
                  <p className="text-xs font-medium text-muted-foreground">
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
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" aria-hidden="true" />
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
  );
}

/** Week agenda: one card per weekday. */
export function WeekAgendaView({
  weekDays,
  filteredEvents,
  onSelectDay,
}: {
  weekDays: Date[];
  filteredEvents: CalendarEventSummary[];
  onSelectDay: (date: Date) => void;
}) {
  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
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
              onClick={() => onSelectDay(day)}
              className={`min-h-[320px] rounded-2xl border p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md ${
                sameDay(day, new Date()) ? "border-primary/20 bg-accent/70" : "border-border bg-muted/60"
              }`}
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    {day.toLocaleDateString("en-US", { weekday: "short" })}
                  </p>
                  <p className={`text-lg font-semibold ${sameDay(day, new Date()) ? "text-primary" : "text-foreground"}`}>
                    {day.getDate()}
                  </p>
                </div>
                <span className="rounded-full bg-card px-2.5 py-1 text-[11px] font-semibold text-muted-foreground shadow-sm">
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
                  <p className="text-xs font-medium text-muted-foreground">+{dayEvents.length - 3} more</p>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Day detail: the selected day's events, assignment overlays, and coverage notes. */
export function DayDetailView({
  focusDate,
  selectedDayEvents,
  selectedDayAssignments,
  filteredEvents,
}: {
  focusDate: Date;
  selectedDayEvents: CalendarEventSummary[];
  selectedDayAssignments: CalendarAssignmentSummary[];
  filteredEvents: CalendarEventSummary[];
}) {
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.08fr_0.92fr]">
      <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-primary">
              Day detail
            </p>
            <h3 className="text-2xl font-semibold text-foreground">
              {focusDate.toLocaleDateString("en-US", {
                weekday: "long",
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              The coordinator can see coverage, volunteers, and recovery posture in one place.
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-muted px-4 py-3 text-right">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Events</p>
            <p className="text-2xl font-semibold text-foreground">{selectedDayEvents.length}</p>
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
                        <h4 className="text-xl font-semibold text-foreground">{event.event_name}</h4>
                        <span className="rounded-full bg-card px-3 py-1 text-xs font-semibold shadow-sm">
                          {event.coverage_label}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-4 text-sm text-foreground/80">
                        <span className="inline-flex items-center gap-2">
                          <MapPin className="h-4 w-4 text-primary" />
                          {event.region}
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <CalendarDays className="h-4 w-4 text-primary" />
                          {/* A date with no resolvable value says so; it is
                              never printed as a raw or guessed string. */}
                          {parseLocalDate(event.event_date)
                            ? `${event.event_date} (${viewerTimeZone()})`
                            : "Date unresolved"}
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <ShieldCheck className="h-4 w-4 text-primary" />
                          {event.assignment_count} assigned
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {event.nearby_universities.slice(0, 4).map((campus) => (
                          <span
                            key={campus}
                            className="rounded-full border border-white/70 bg-card/80 px-3 py-1 text-xs font-medium text-foreground/80"
                          >
                            {campus}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/70 bg-card/80 px-4 py-3 shadow-sm">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        Lecture window
                      </p>
                      <p className="mt-1 text-lg font-semibold text-foreground">
                        {event.suggested_lecture_window}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4">
                    <p className="mb-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
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
                        <span className="rounded-full border border-border bg-card/80 px-3 py-1 text-xs font-medium text-muted-foreground">
                          No assignment overlay rows
                        </span>
                      )}
                      {eventAssignments.length > 4 ? (
                        <span className="rounded-full border border-border bg-card/80 px-3 py-1 text-xs font-medium text-muted-foreground">
                          +{eventAssignments.length - 4} more
                        </span>
                      ) : null}
                    </div>
                  </div>
                </article>
              );
            })
          ) : (
            <div className="rounded-3xl border border-dashed border-border bg-muted p-10 text-center text-muted-foreground">
              No event windows are scheduled for this day.
            </div>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            <div>
              <h3 className="text-lg font-semibold text-foreground">Assignment overlays</h3>
              <p className="text-sm text-muted-foreground">
                Coverage-aware assignments and recovery status for the selected day.
              </p>
            </div>
          </div>

          <div className="space-y-3">
            {selectedDayAssignments.length ? (
              selectedDayAssignments.map((assignment) => (
                <div
                  key={assignment.assignment_id}
                  className="rounded-2xl border border-border bg-muted p-4 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-foreground">{assignment.volunteer_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {assignment.volunteer_title || "Board volunteer"}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
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
                    <div className="rounded-xl bg-card px-3 py-2">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                        Fatigue
                      </p>
                      <p className="mt-1 text-sm font-semibold text-foreground">
                        {formatPercent(assignment.volunteer_fatigue)}
                      </p>
                    </div>
                    <div className="rounded-xl bg-card px-3 py-2">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                        Recent
                      </p>
                      <p className="mt-1 text-sm font-semibold text-foreground">
                        {formatCount(assignment.recent_assignment_count)}
                      </p>
                    </div>
                    <div className="rounded-xl bg-card px-3 py-2">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                        Cadence
                      </p>
                      <p className="mt-1 text-sm font-semibold text-foreground">
                        {assignment.event_cadence || "n/a"}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-3xl border border-dashed border-border bg-muted p-8 text-center text-muted-foreground">
                No assignments were found for this day.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            <div>
              <h3 className="text-lg font-semibold text-foreground">Coverage notes</h3>
              <p className="text-sm text-muted-foreground">
                Simple labels that help coordinators see where to focus next.
              </p>
            </div>
          </div>

          <div className="mt-4 space-y-2">
            {(selectedDayEvents.length ? selectedDayEvents : filteredEvents.slice(0, 3)).map(
              (event) => (
                <div
                  key={`note-${event.event_id}`}
                  className="flex items-center justify-between rounded-2xl border border-border bg-muted px-4 py-3"
                >
                  <div>
                    <p className="font-medium text-foreground">{event.event_name}</p>
                    <p className="text-sm text-muted-foreground">{event.region}</p>
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
  );
}
