/**
 * The event picker: which event is this team building a list for?
 *
 * `GET /v1/exercise/workspaces/current/events` returns all twelve events in
 * the data file, and only two of them are targets. The other ten are past
 * events, there so a profile can have an attendance history — requirements,
 * "Data" row: *"About 300 profiles and 12 events (10 past events for
 * attendance history plus the 2 exercise events)."* So the two rounds are
 * offered as the choices and the ten are listed separately, named for what
 * they are, rather than hidden: a team that can see the attendance history
 * exists can also see what "went to similar events before" is reading.
 *
 * Which event is a round comes from `is_exercise_event` and `sequence`, never
 * from an event's name. The names are Ann's data file's and may change.
 *
 * No vocabulary is written into this screen. Topics and majors render as the
 * strings the server sends. Ann's workbook of 2026-09-24 closed the columns
 * and vocabularies, but the server owns them, so nothing here compares them to
 * a list.
 *
 * Layout: DESIGN.md §7.3. Round cards follow §6.5; past events are a quiet
 * two-column list, folded behind a disclosure below 768px.
 */
import * as React from "react";
import { Link } from "react-router";
import { CalendarDays, ChevronDown, ChevronRight } from "lucide-react";

import { readEvents, type EventView } from "../../../lib/exerciseClient";
import { cn } from "../../components/ui/utils";
import { Button, Skeleton, SkeletonCard, SkeletonRegion } from "./desk";
import { ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

const PAST_LIST_ID = "exercise-past-events";

export function ExerciseEventPicker(): React.JSX.Element {
  const { state, reload } = useExerciseResource(readEvents, []);

  return (
    <ExerciseScreen
      title="Choose an event"
      intro="Build your team's list for one of the two events in the exercise."
    >
      {state.status === "loading" ? <PickerSkeleton /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <Button variant="secondary" onClick={reload}>
            Try again
          </Button>
        </ExerciseNotice>
      ) : null}
      {state.status === "ready" ? <EventLists events={state.data.events} /> : null}
    </ExerciseScreen>
  );
}

/** §6.5 L: two card skeletons and four line skeletons. */
function PickerSkeleton(): React.JSX.Element {
  return (
    <SkeletonRegion label="Loading the events…" className="flex flex-col gap-ce-5">
      <SkeletonCard lines={2} />
      <SkeletonCard lines={2} />
      <div aria-hidden="true" className="mt-ce-4 grid gap-ce-3 md:grid-cols-2">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} data-slot="exercise-past-event-skeleton">
            <Skeleton className="h-5 w-3/5" />
          </div>
        ))}
      </div>
    </SkeletonRegion>
  );
}

function EventLists({ events }: { readonly events: readonly EventView[] }): React.JSX.Element {
  const rounds = events
    .filter((event) => event.is_exercise_event)
    .slice()
    .sort((a, b) => a.sequence - b.sequence);
  const past = events.filter((event) => !event.is_exercise_event);

  if (rounds.length === 0) {
    return (
      <ExerciseNotice message="This data file has no exercise events in it yet. The instructor can upload a file that does." />
    );
  }

  return (
    <div className="flex flex-col gap-ce-6 md:gap-ce-7">
      <section className="flex flex-col gap-ce-4">
        <h2 className="ce-type-h2 text-ce-ink">The two events you can work on</h2>
        <ul className="flex flex-col gap-ce-4 md:gap-ce-5">
          {rounds.map((event, index) => (
            <li key={event.event_key}>
              <RoundCard event={event} roundNumber={index + 1} />
            </li>
          ))}
        </ul>
      </section>

      <PastEvents past={past} />
    </div>
  );
}

/**
 * One round (§6.5): a numbered seal, the event name in the serif, its topics
 * and majors as the server sends them, and a chevron. The whole card is the
 * link, so the ring and the lift wrap the card.
 */
function RoundCard({
  event,
  roundNumber,
}: {
  readonly event: EventView;
  readonly roundNumber: number;
}): React.JSX.Element {
  // round-journey.svg geometry: round one is a tinted ring, later rounds a
  // filled disc.
  const first = roundNumber === 1;
  return (
    <Link
      to={`/exercise/events/${encodeURIComponent(event.event_key)}`}
      className="group ce-card ce-lift flex items-start gap-ce-4 p-ce-4 text-ce-ink no-underline md:gap-ce-5 md:p-ce-5"
    >
      <div
        className={cn(
          "flex size-11 shrink-0 items-center justify-center rounded-full border-[3px] border-ce-primary font-ce-display text-[22px] leading-none font-bold tabular-nums md:size-14 md:text-[26px]",
          first ? "bg-ce-primary-tint text-ce-on-primary-tint" : "bg-ce-primary text-ce-on-primary",
        )}
      >
        <span className="sr-only">Round </span>
        {roundNumber}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-ce-2">
        <p className="ce-type-h2 break-words text-ce-ink">{event.name}</p>
        {event.topic_tags.length === 0 ? null : (
          <p className="ce-type-body text-ce-ink">Topics: {event.topic_tags.join(", ")}</p>
        )}
        {event.target_majors.length === 0 ? null : (
          <p className="ce-type-body text-ce-ink-muted">
            Aimed at: {event.target_majors.join(", ")}
          </p>
        )}
      </div>
      <ChevronRight
        aria-hidden="true"
        className="size-6 shrink-0 self-center text-ce-ink-muted transition-transform duration-150 group-hover:translate-x-1 group-hover:text-ce-primary motion-reduce:transition-none"
      />
    </Link>
  );
}

/** The ten past events: a quiet list, never cards and never links (§6.5). */
function PastEvents({ past }: { readonly past: readonly EventView[] }): React.JSX.Element {
  const [expanded, setExpanded] = React.useState(false);
  const count = past.length;

  return (
    <section className="flex flex-col gap-ce-3">
      <h2 className="ce-type-h2 text-ce-ink">Past events, for attendance history</h2>
      <p className="ce-type-body ce-measure text-ce-ink-muted">
        These are not events you build a list for. They are what “went to similar events before”
        reads.
      </p>
      {count === 0 ? (
        <p className="ce-type-body text-ce-ink-muted">This data file carries no past events.</p>
      ) : (
        <>
          <Button
            variant="quiet"
            aria-expanded={expanded}
            aria-controls={PAST_LIST_ID}
            onClick={() => setExpanded((open) => !open)}
            leadingIcon={
              <ChevronDown
                className={cn(
                  "transition-transform duration-150 motion-reduce:transition-none",
                  expanded && "rotate-180",
                )}
              />
            }
            className="-ml-ce-2 self-start md:hidden"
          >
            {count === 1 ? "Show the 1 past event" : `Show the ${count} past events`}
          </Button>
          <ul
            id={PAST_LIST_ID}
            data-expanded={expanded ? "true" : "false"}
            // Two columns read top to bottom, then across, as a printed list.
            style={{ "--ce-past-rows": Math.ceil(count / 2) } as React.CSSProperties}
            className={cn(
              "mt-ce-2 grid gap-x-ce-6 gap-y-ce-3 md:grid-flow-col md:grid-cols-2 md:grid-rows-[repeat(var(--ce-past-rows),auto)]",
              !expanded && "max-md:hidden",
            )}
          >
            {past.map((event) => (
              <li key={event.event_key} className="ce-type-body flex items-start gap-ce-3 text-ce-ink">
                <CalendarDays
                  aria-hidden="true"
                  className="mt-[5px] size-5 shrink-0 text-ce-ink-muted"
                />
                <span className="min-w-0">
                  {event.name}
                  {event.topic_tags.length === 0 ? null : (
                    <span className="text-ce-ink-muted"> — {event.topic_tags.join(", ")}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
