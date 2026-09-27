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
 */
import * as React from "react";
import { Link } from "react-router";
import { CalendarDays, ChevronRight } from "lucide-react";

import { readEvents, type EventView } from "../../../lib/exerciseClient";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ceButton, useIsNarrow } from "./exerciseUi";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

export function ExerciseEventPicker(): React.JSX.Element {
  const { state, reload } = useExerciseResource(readEvents, []);

  return (
    <ExerciseScreen
      title="Choose an event"
      intro="Build your team's list for one of the two events in the exercise."
    >
      {state.status === "loading" ? <ExerciseLoading what="the events" shape="cards" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={ceButton("primary")}>
            Try again
          </button>
        </ExerciseNotice>
      ) : null}
      {state.status === "ready" ? <EventLists events={state.data.events} /> : null}
    </ExerciseScreen>
  );
}

function EventLists({ events }: { readonly events: readonly EventView[] }): React.JSX.Element {
  const narrow = useIsNarrow();
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

  const pastList =
    past.length === 0 ? (
      <p className="ce-body mt-3 text-ce-muted">This data file carries no past events.</p>
    ) : (
      <ul className="mt-4 grid gap-x-12 gap-y-3 md:grid-cols-2">
        {past.map((event) => (
          <li key={event.event_key} className="ce-body flex items-start gap-3 text-ce-ink">
            <CalendarDays aria-hidden="true" className="mt-1 size-5 shrink-0 text-ce-muted" />
            <span>
              {event.name}
              {event.topic_tags.length === 0 ? null : (
                <span className="text-ce-muted"> — {event.topic_tags.join(", ")}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    );

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <section className="flex flex-col gap-4">
        <h2 className="ce-h2 text-ce-ink">The two events you can work on</h2>
        <ul className="flex flex-col gap-4 md:gap-6">
          {rounds.map((event, index) => (
            <li key={event.event_key}>
              <RoundCard event={event} roundNumber={index + 1} />
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col">
        <h2 className="ce-h2 text-ce-ink">Past events, for attendance history</h2>
        <p className="ce-body mt-2 max-w-[64ch] text-ce-muted">
          These are not events you build a list for. They are what “went to similar events before”
          reads.
        </p>
        {/* §7.3: on a phone the ten fold behind a disclosure. */}
        {narrow && past.length > 0 ? (
          <details className="mt-4">
            <summary className={ceButton("quiet", "cursor-pointer")}>
              Show the {past.length} past events
            </summary>
            {pastList}
          </details>
        ) : (
          pastList
        )}
      </section>
    </div>
  );
}

/**
 * A round card (§6.5): the round's seal, the event name in Proxima Sera, its
 * topics and majors, and a trailing chevron that slides on hover. The whole
 * card is the link.
 */
function RoundCard({
  event,
  roundNumber,
}: {
  readonly event: EventView;
  readonly roundNumber: number;
}): React.JSX.Element {
  return (
    <Link
      to={`/exercise/events/${encodeURIComponent(event.event_key)}`}
      className="ce-card ce-lift group flex items-start gap-4 p-5 text-ce-ink no-underline md:gap-6 md:p-6"
    >
      <span
        className={`ce-label flex size-11 shrink-0 items-center justify-center rounded-full border-2 border-ce-primary ce-num ${
          roundNumber === 1 ? "text-ce-primary" : "bg-ce-primary text-ce-on-primary"
        }`}
      >
        <span className="sr-only">Round </span>
        {roundNumber}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="ce-h2 text-ce-ink">{event.name}</span>
        {event.topic_tags.length === 0 ? null : (
          <span className="ce-body text-ce-ink">Topics: {event.topic_tags.join(", ")}</span>
        )}
        {event.target_majors.length === 0 ? null : (
          <span className="ce-body text-ce-ink">Aimed at: {event.target_majors.join(", ")}</span>
        )}
      </span>
      <ChevronRight
        aria-hidden="true"
        className="mt-3 size-6 shrink-0 self-center text-ce-muted transition-transform duration-150 group-hover:translate-x-1 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
      />
    </Link>
  );
}
