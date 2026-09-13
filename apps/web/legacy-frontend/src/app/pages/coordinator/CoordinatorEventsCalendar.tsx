/**
 * The month view of `CoordinatorEvents` — the same `GET /v1/units/{unit_id}/events`
 * response, drawn as a calendar.
 *
 * ## Why a view on this page and not a route
 *
 * The retired admin shell had a separate `/calendar` page; that address now
 * redirects here. The month grid is a second way to *read* the listing this
 * page already holds — the editor, the publish refusal, and the feedback QR
 * all live beside it, and a day selected in the grid opens into that same
 * editor through the same `onOpenEvent` path the list rows use. A sibling
 * route would have to re-create that wiring or strand the grid as read-only.
 *
 * ## What it does not do
 *
 *  - **No date filtering.** The route takes no `from`/`to` parameters and
 *    hard-caps at 200 rows; moving a month re-buckets the response already
 *    held rather than pretending to ask for a window. When the response was
 *    `truncated`, the page's own notice says the server stopped sending —
 *    which for a calendar means some days may be empty because their events
 *    never arrived, and the notice is left visible in this view for exactly
 *    that reason.
 *  - **No coverage or staffing overlay.** The response carries no
 *    assignment, roster, or open-slot data, and none is derived from what it
 *    does carry — the retired calendar's overlay domain does not exist in
 *    this API.
 *  - **No invented days.** `lib/eventCalendarDays` decides placement by the
 *    event's own precision and zone; an event that resolves to no day is
 *    named under the grid rather than guessed onto one (ADR-0010 — the
 *    defect the retired surface had, filing undated rows under today).
 *
 * ## Keyboard
 *
 * The grid follows the ARIA grid/date-picker pattern: one tab stop on the
 * focused day, arrow keys move by day or week, Home/End to the week's ends,
 * PageUp/PageDown by month, Enter or Space selects the day into the detail
 * list below. Every control is a real `<button>`.
 */
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import type { UnitEventSummary } from "@/lib/api";
import {
  dayLabel,
  eventCellTime,
  monthGridWeeks,
  monthKeyOfDay,
  monthKeyOfDate,
  monthLabel,
  partitionEventsByDay,
  shiftDayKey,
  shiftMonthKey,
  todayDayKey,
  unplacedReason,
  weekEndKey,
  weekStartKey,
  type DayKey,
  type MonthKey,
} from "@/lib/eventCalendarDays";
import { eventWhen, scheduleOfSummary } from "../eventListings";

/** The most event chips one cell draws before "and N more" takes over. */
const MAX_CELL_CHIPS = 3;

const WEEKDAY_LABELS: readonly { short: string; long: string }[] = [
  { short: "Sun", long: "Sunday" },
  { short: "Mon", long: "Monday" },
  { short: "Tue", long: "Tuesday" },
  { short: "Wed", long: "Wednesday" },
  { short: "Thu", long: "Thursday" },
  { short: "Fri", long: "Friday" },
  { short: "Sat", long: "Saturday" },
];

/** Arrow/Home/End/PageUp/PageDown moves, keyed by `KeyboardEvent.key`. */
const FOCUS_MOVES: Readonly<Record<string, (key: DayKey) => DayKey>> = {
  ArrowLeft: (key) => shiftDayKey(key, -1),
  ArrowRight: (key) => shiftDayKey(key, 1),
  ArrowUp: (key) => shiftDayKey(key, -7),
  ArrowDown: (key) => shiftDayKey(key, 7),
  Home: (key) => weekStartKey(key),
  End: (key) => weekEndKey(key),
  PageUp: (key) => shiftMonthKey(key, -1),
  PageDown: (key) => shiftMonthKey(key, 1),
};

const dayButtonId = (key: DayKey) => `events-calendar-day-${key}`;

export function CoordinatorEventsCalendar({
  events,
  selectedId,
  onOpenEvent,
}: {
  /** The server's presentable events — the same array the list view draws. */
  events: readonly UnitEventSummary[];
  /** The event currently open in the page's editor, so its row can show it. */
  selectedId: string | null;
  /** The page's open-an-event path; the same one a list row's edit button uses. */
  onOpenEvent: (event: UnitEventSummary) => void;
}) {
  const todayKey = todayDayKey();
  // `focusKey` drives the roving tab stop; `selectedKey` drives the detail
  // list; `viewMonth` is the month drawn. They part company on purpose —
  // paging the grid does not re-select a day, and selecting a day in the
  // detail list does not move keyboard focus.
  const [focusKey, setFocusKey] = useState<DayKey>(todayKey);
  const [selectedKey, setSelectedKey] = useState<DayKey>(todayKey);
  const [viewMonth, setViewMonth] = useState<MonthKey>(monthKeyOfDate(new Date()));
  // Set only by the keyboard handler: roving tabindex moves the stop, but DOM
  // focus still has to be moved to the newly-tabbable cell. Click-driven
  // changes must not steal focus back onto the grid.
  const moveFocusToCell = useRef(false);

  useEffect(() => {
    if (!moveFocusToCell.current) {
      return;
    }
    moveFocusToCell.current = false;
    document.getElementById(dayButtonId(focusKey))?.focus();
  }, [focusKey]);

  const { byDay, unplaced } = useMemo(() => partitionEventsByDay(events), [events]);
  const weeks = useMemo(() => monthGridWeeks(viewMonth), [viewMonth]);
  const selectedDayEvents = byDay.get(selectedKey) ?? [];
  const monthIsEmpty = useMemo(
    () =>
      !weeks.some((week) =>
        week.some((key) => key !== null && (byDay.get(key)?.length ?? 0) > 0),
      ),
    [weeks, byDay],
  );

  const moveFocus = (nextKey: DayKey) => {
    // A move that lands where focus already is changes nothing — and must not
    // arm the focus effect, or the next non-keyboard `setFocusKey` would steal
    // DOM focus into the grid.
    if (nextKey === focusKey) {
      return;
    }
    moveFocusToCell.current = true;
    setFocusKey(nextKey);
    const nextMonth = monthKeyOfDay(nextKey);
    if (nextMonth !== viewMonth) {
      setViewMonth(nextMonth);
    }
  };

  const changeMonth = (months: number) => {
    // Keep the focused day inside the month being shown, or the grid's one
    // tab stop leaves the grid altogether and Tab skips past it. DOM focus
    // stays on the nav button — only the roving stop moves.
    moveFocusToCell.current = false;
    const nextFocus = shiftMonthKey(focusKey, months);
    setFocusKey(nextFocus);
    setViewMonth(monthKeyOfDay(nextFocus));
  };

  const goToThisMonth = () => {
    moveFocusToCell.current = false;
    setFocusKey(todayKey);
    setSelectedKey(todayKey);
    setViewMonth(monthKeyOfDate(new Date()));
  };

  const onDayKeyDown = (event: KeyboardEvent<HTMLButtonElement>, key: DayKey) => {
    const move = FOCUS_MOVES[event.key];
    if (move === undefined) {
      return;
    }
    event.preventDefault();
    moveFocus(move(key));
  };

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="events-calendar-month-label" className="text-sm font-semibold text-foreground">
          {monthLabel(viewMonth)}
        </h3>
        <div
          className="flex items-center gap-1 rounded-xl border border-border p-1"
          role="group"
          aria-label="Change which month is shown"
        >
          <button
            type="button"
            onClick={() => changeMonth(-1)}
            aria-label="Previous month"
            className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg px-2 text-muted-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={goToThisMonth}
            className="min-h-[40px] rounded-lg px-3 py-2 text-sm font-medium text-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            This month
          </button>
          <button
            type="button"
            onClick={() => changeMonth(1)}
            aria-label="Next month"
            className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg px-2 text-muted-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <p className="text-xs leading-5 text-muted-foreground">
        Days are placed by each event&apos;s own time zone where the server recorded one; an
        event that resolves to no day is named below the grid rather than guessed onto one.
      </p>

      <div role="grid" aria-labelledby="events-calendar-month-label">
        <div role="rowgroup">
          <div role="row" className="grid grid-cols-7 gap-1 sm:gap-2">
            {WEEKDAY_LABELS.map((weekday) => (
              <div
                key={weekday.short}
                role="columnheader"
                aria-label={weekday.long}
                className="pb-1 text-center text-xs font-semibold text-muted-foreground"
              >
                <span aria-hidden="true">{weekday.short}</span>
              </div>
            ))}
          </div>
        </div>
        <div role="rowgroup" className="space-y-1 sm:space-y-2">
          {weeks.map((week, weekIndex) => (
            <div role="row" key={weekIndex} className="grid grid-cols-7 gap-1 sm:gap-2">
              {week.map((dayKey, dayIndex) =>
                dayKey === null ? (
                  // A padding cell for a day this month does not have. Drawn
                  // as an inert gridcell rather than left out so the row
                  // still spans seven columns for assistive technology.
                  <div
                    key={`pad-${weekIndex}-${dayIndex}`}
                    role="gridcell"
                    aria-disabled="true"
                    className="min-h-[72px] rounded-xl sm:min-h-[104px]"
                  />
                ) : (
                  <CalendarDayCell
                    key={dayKey}
                    dayKey={dayKey}
                    events={byDay.get(dayKey) ?? []}
                    isToday={dayKey === todayKey}
                    isSelected={dayKey === selectedKey}
                    tabbable={dayKey === focusKey}
                    onKeyDown={onDayKeyDown}
                    onSelect={(key) => {
                      setSelectedKey(key);
                      setFocusKey(key);
                    }}
                  />
                ),
              )}
            </div>
          ))}
        </div>
      </div>

      {monthIsEmpty ? (
        <p className="text-sm text-muted-foreground">
          No listed events fall in {monthLabel(viewMonth)}.
        </p>
      ) : null}

      <section
        className="rounded-xl border border-border/70 bg-muted/30 p-4"
        aria-label="Selected day"
      >
        <h4 className="text-sm font-semibold text-foreground">
          {dayLabel(selectedKey)}
          {selectedKey === todayKey ? " — today" : ""}
        </h4>
        <p role="status" className="mt-1 text-xs text-muted-foreground">
          {selectedDayEvents.length === 0
            ? "No listed events on this day."
            : `${selectedDayEvents.length} listed ${
                selectedDayEvents.length === 1 ? "event" : "events"
              } on this day.`}
        </p>
        {selectedDayEvents.length > 0 ? (
          <ul className="mt-3 space-y-2">
            {selectedDayEvents.map((event) => (
              <li
                key={event.id}
                className={`flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xl border p-3 ${
                  selectedId === event.id
                    ? "border-primary bg-primary/5"
                    : "border-border bg-card"
                }`}
              >
                <div className="min-w-0">
                  <p className="font-medium text-foreground">{event.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {eventWhen(scheduleOfSummary(event))}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onOpenEvent(event)}
                  className="min-h-[40px] shrink-0 rounded-xl border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  Edit this event
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {unplaced.length > 0 ? (
        <section
          className="rounded-xl border border-dashed border-border bg-muted/30 p-4"
          aria-label="Events not placed on the calendar"
        >
          <h4 className="text-sm font-semibold text-foreground">
            Not placed on a day: {unplaced.length}{" "}
            {unplaced.length === 1 ? "event" : "events"}
          </h4>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            No day cell can honestly claim these — each one says why. This is in addition to the
            withheld counts below: the route already refuses to list events with no resolved date
            at all.
          </p>
          <ul className="mt-3 space-y-1 text-sm text-foreground">
            {unplaced.map((event) => (
              <li key={event.id} className="truncate">
                <span className="font-medium">{event.title}</span>
                <span className="text-muted-foreground"> — {unplacedReason(event.time)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

/**
 * One day cell: a `gridcell` wrapping the day's single focusable button.
 *
 * The event chips inside the button are `aria-hidden`: the button's
 * accessible name already reports the count ("Monday, September 14, 2026 —
 * 2 events"), and the full event names are reachable in the selected-day
 * list below the grid, so repeating them inside every cell would double the
 * announcement without adding information.
 */
function CalendarDayCell({
  dayKey,
  events,
  isToday,
  isSelected,
  tabbable,
  onKeyDown,
  onSelect,
}: {
  dayKey: DayKey;
  events: readonly UnitEventSummary[];
  isToday: boolean;
  isSelected: boolean;
  tabbable: boolean;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>, key: DayKey) => void;
  onSelect: (key: DayKey) => void;
}) {
  const label = `${dayLabel(dayKey)}${isToday ? ", today" : ""} — ${
    events.length === 0
      ? "no events"
      : `${events.length} ${events.length === 1 ? "event" : "events"}`
  }`;

  return (
    <div
      role="gridcell"
      aria-selected={isSelected}
      className={`min-h-[72px] rounded-xl border sm:min-h-[104px] ${
        isSelected
          ? "border-primary bg-primary/5"
          : isToday
            ? "border-primary/30 bg-accent/50"
            : "border-border/70 bg-card"
      }`}
    >
      <button
        type="button"
        id={dayButtonId(dayKey)}
        tabIndex={tabbable ? 0 : -1}
        onClick={() => onSelect(dayKey)}
        onKeyDown={(event) => onKeyDown(event, dayKey)}
        aria-label={label}
        className="flex h-full w-full flex-col gap-1 rounded-xl p-1.5 text-left transition-colors duration-150 motion-reduce:transition-none hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 sm:p-2"
      >
        <span className="flex items-baseline justify-between gap-1">
          <span
            className={`text-xs font-semibold sm:text-sm ${
              isToday ? "text-primary" : "text-foreground"
            }`}
          >
            {Number(dayKey.slice(8, 10))}
          </span>
          {events.length > 0 ? (
            <span
              aria-hidden="true"
              className="rounded-full border border-border/70 bg-muted px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground"
            >
              {events.length}
            </span>
          ) : null}
        </span>
        {events.length > 0 ? (
          <span aria-hidden="true" className="hidden min-w-0 flex-col gap-1 sm:flex">
            {events.slice(0, MAX_CELL_CHIPS).map((event) => {
              const chipTime = eventCellTime(event);
              return (
                <span
                  key={event.id}
                  className="truncate rounded-md border border-border/60 bg-muted/60 px-1.5 py-0.5 text-[10px] leading-4 text-foreground"
                >
                  <span className="font-medium">{event.title}</span>
                  {chipTime !== null ? (
                    <span className="text-muted-foreground"> · {chipTime}</span>
                  ) : null}
                </span>
              );
            })}
            {events.length > MAX_CELL_CHIPS ? (
              <span className="px-1 text-[10px] font-medium text-muted-foreground">
                +{events.length - MAX_CELL_CHIPS} more
              </span>
            ) : null}
          </span>
        ) : null}
      </button>
    </div>
  );
}
