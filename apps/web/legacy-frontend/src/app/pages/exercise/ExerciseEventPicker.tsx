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
 * strings the file carries (OQ-CE-01 is open — the column names and value
 * vocabularies are not settled), and nothing here compares them to a list.
 */
import * as React from "react";
import { Link } from "react-router";

import { readEvents, type EventView } from "../../../lib/exerciseClient";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";
import { workspaceRequiredNotice } from "./refusals";

export function ExerciseEventPicker(): React.JSX.Element {
  const { state, reload } = useExerciseResource(readEvents, []);

  return (
    <ExerciseScreen
      title="Choose an event"
      intro="Build your team's list for one of the two events in the exercise."
    >
      {state.status === "loading" ? <ExerciseLoading what="the events" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button
            type="button"
            onClick={reload}
            className="rounded-lg border-2 border-slate-400 px-5 py-2 text-xl font-semibold"
          >
            Try again
          </button>
        </ExerciseNotice>
      ) : null}
      {state.status === "ready" ? <EventLists events={state.data.events} /> : null}
    </ExerciseScreen>
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
    <div className="flex flex-col gap-8">
      <section>
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
          The two events you can work on
        </h2>
        <ul className="mt-4 flex flex-col gap-4">
          {rounds.map((event, index) => (
            <li key={event.event_key}>
              <RoundCard event={event} roundNumber={index + 1} />
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
          Past events, for attendance history
        </h2>
        <p className="mt-2 text-xl text-slate-600 dark:text-slate-300">
          These are not events you build a list for. They are what “went to similar events before”
          reads.
        </p>
        {past.length === 0 ? (
          <p className="mt-3 text-xl text-slate-600 dark:text-slate-300">
            This data file carries no past events.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2 text-xl text-slate-800 dark:text-slate-100">
            {past.map((event) => (
              <li key={event.event_key}>
                {event.name}
                {event.topic_tags.length === 0 ? null : (
                  <span className="text-slate-600 dark:text-slate-300">
                    {" "}
                    — {event.topic_tags.join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

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
      className="block rounded-lg border-2 border-slate-400 px-6 py-5 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:hover:bg-slate-800"
    >
      <p className="text-lg font-semibold tracking-wide text-slate-600 uppercase dark:text-slate-300">
        Round {roundNumber}
      </p>
      <p className="text-3xl font-bold text-slate-900 dark:text-slate-50">{event.name}</p>
      {event.topic_tags.length === 0 ? null : (
        <p className="mt-2 text-xl text-slate-700 dark:text-slate-200">
          Topics: {event.topic_tags.join(", ")}
        </p>
      )}
      {event.target_majors.length === 0 ? null : (
        <p className="text-xl text-slate-700 dark:text-slate-200">
          Aimed at: {event.target_majors.join(", ")}
        </p>
      )}
    </Link>
  );
}
