/**
 * Round steps on an event page (Ann, 2026-10-18).
 *
 * Round one: "How much we know, all 300 profiles", above the list.
 * Round two (Harbor): step 1 is asking students for more information. The list
 * builder is step 4, so it stays hidden until the team has asked. Any failed
 * read leaves the page as it was: the server still decides every refusal.
 */
import * as React from "react";
import { Link } from "react-router";

import {
  readAskingChoice,
  readCurrentWorkspace,
  readEvents,
  type AskingStateView,
} from "../../../lib/exerciseClient";
import { MarkerCountsBefore } from "./RefreshSummary";
import { refreshChangeSentences } from "./refreshWording";
import { roundsOf } from "./teamStatusWording";
import { useExerciseResource } from "./useExerciseResource";

interface Gate {
  readonly round: number | null;
  readonly asking: AskingStateView;
  readonly roundTwoOpen: boolean | undefined;
}

async function readGate(
  eventKey: string,
  signal: AbortSignal,
): Promise<Gate | null> {
  try {
    const [events, asking, workspace] = await Promise.all([
      readEvents(signal),
      readAskingChoice(signal),
      readCurrentWorkspace(signal),
    ]);
    const index = roundsOf(events.events).findIndex(
      (round) => round.eventKey === eventKey,
    );
    return {
      round: index < 0 ? null : index + 1,
      asking,
      roundTwoOpen: workspace.round_two_open,
    };
  } catch (error) {
    if (signal.aborted) {
      throw error;
    }
    return null;
  }
}

export function RoundStepsGate({
  eventKey,
  children,
}: {
  readonly eventKey: string;
  readonly children: React.ReactNode;
}): React.JSX.Element {
  const { state } = useExerciseResource(
    (signal) => readGate(eventKey, signal),
    [eventKey],
  );
  if (state.status === "loading") {
    // Not the list: round two's list must not flash before the gate is known.
    return <></>;
  }
  const gate = state.status === "ready" ? state.data : null;
  if (gate === null) {
    return <>{children}</>;
  }
  if (gate.round === 1) {
    return (
      <>
        <MarkerCountsBefore before={gate.asking.marker_counts_before ?? {}} />
        {children}
      </>
    );
  }
  if (gate.round !== 2) {
    return <>{children}</>;
  }
  const { asking } = gate;
  if (!asking.refreshed || asking.refresh_counts === null) {
    return (
      <section
        data-slot="exercise-round-two-step"
        className="ce-card flex flex-col gap-ce-3 p-ce-4"
      >
        <h2 className="ce-type-h2 text-ce-ink">
          Round 2 starts here: ask students for more information
        </h2>
        {gate.roundTwoOpen === false ? (
          <p className="ce-type-body text-ce-ink-muted">
            Round 2 opens after your Northline results.
          </p>
        ) : (
          <>
            <p className="ce-type-body text-ce-ink-muted">
              Ask first. The list comes after, so it can use what the students
              tell us.
            </p>
            <p>
              <Link to="/exercise/asking">
                Choose how to ask students for more information
              </Link>
            </p>
          </>
        )}
      </section>
    );
  }
  return (
    <>
      <section
        data-slot="exercise-round-two-step"
        className="ce-card flex flex-col gap-ce-2 p-ce-4"
      >
        <h2 className="ce-type-h2 text-ce-ink">
          Students were asked for more information
        </h2>
        <p className="ce-type-body text-ce-ink">
          {
            refreshChangeSentences(
              asking.refresh_counts,
              asking.first_round_event_name,
            )[0]
          }
        </p>
        <p>
          <Link to="/exercise/asking">See what changed</Link>
        </p>
      </section>
      {children}
    </>
  );
}

/** "Next: build the Harbor list", linked to the round-two event; nothing if events cannot be read. */
export function NextHarborLink({
  className,
}: {
  readonly className: string;
}): React.JSX.Element | null {
  const { state } = useExerciseResource(async (signal) => {
    try {
      return roundsOf((await readEvents(signal)).events)[1]?.eventKey ?? null;
    } catch (error) {
      if (signal.aborted) {
        throw error;
      }
      return null;
    }
  }, []);
  const key = state.status === "ready" ? state.data : null;
  return key === null ? null : (
    <p data-slot="exercise-asking-next">
      <Link
        to={`/exercise/events/${encodeURIComponent(key)}`}
        className={className}
      >
        Next: build the Harbor list
      </Link>
    </p>
  );
}
