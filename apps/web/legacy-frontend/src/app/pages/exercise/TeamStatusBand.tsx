/**
 * The team's status line, at the top of every team page (DESIGN.md §6.1,
 * issue #321).
 *
 * Student-facing status is intentionally compact: it identifies the team and
 * offers the route back to team selection. Round, results, asking, refresh,
 * and data-file state are internal progress details, not student UI.
 *
 * **It reads the server and keeps nothing.** The team number is never taken
 * from `localStorage` (`workspacePointer.ts` says why). A reload or a second
 * tab mounts this again and reads again.
 *
 * **It follows the page.** A page bumps `revision` after something it did has
 * landed (a run, a choice, a refresh) and the line is read again. Until the
 * new read lands the previous line stays, so the top of the page does not
 * jump.
 *
 * **It never speaks for the page.** A refused read (no team entered, access
 * gone) renders nothing: the page below shows that sentence and the way back.
 * It is not a live region for its own first appearance; one `sr-only` polite
 * line says the new state when it changes.
 */
import * as React from "react";
import { Link } from "react-router";

import { ExerciseUnreachable } from "../../../lib/exerciseApi";
import {
  readAskingChoice,
  readCurrentWorkspace,
  readEvents,
  type AskingStateView,
  type EventView,
  type TeamWorkspaceView,
} from "../../../lib/exerciseClient";
import { teamLine } from "./teamStatusWording";
import { useExerciseResource } from "./useExerciseResource";

interface TeamStatusData {
  readonly workspace: TeamWorkspaceView;
  readonly events: readonly EventView[];
  readonly asking: AskingStateView;
}

async function readTeamStatus(signal: AbortSignal): Promise<TeamStatusData> {
  const [workspace, events, asking] = await Promise.all([
    readCurrentWorkspace(signal),
    readEvents(signal),
    readAskingChoice(signal),
  ]);
  // Checked, not trusted: a line built from an answer of the wrong shape would
  // state things nobody said. It is treated as an answer that did not arrive.
  if (
    typeof workspace?.team_number !== "number" ||
    typeof workspace.dataset_label !== "string" ||
    !Array.isArray(events?.events) ||
    typeof asking !== "object" ||
    asking === null ||
    !(asking.choice === null || typeof asking.choice === "string")
  ) {
    throw new ExerciseUnreachable();
  }
  return { workspace, events: events.events, asking };
}

/** A later read that cannot reach the server keeps the line already shown. */
function keepWhenUnreachable(error: unknown): boolean {
  return error instanceof ExerciseUnreachable;
}

/**
 * A page's `reload`, followed by a new read of the status line.
 *
 * The line is read again only once the page's own re-read has landed, so the
 * two never disagree for longer than one request.
 */
export function useStatusRevision(reload: () => Promise<void>): {
  readonly revision: number;
  readonly reloadWithStatus: () => Promise<void>;
} {
  const [revision, setRevision] = React.useState(0);
  const reloadWithStatus = React.useCallback(async (): Promise<void> => {
    await reload();
    setRevision((value) => value + 1);
  }, [reload]);
  return { revision, reloadWithStatus };
}

// Pinned (Dr. Wang 2026-10-10): stays on screen while scrolling; .ce-card is opaque.
const BAND = "sticky top-0 z-20 ce-card ce-type-body flex flex-col gap-ce-2 p-ce-3 text-ce-ink md:px-ce-5 md:py-ce-4";

export interface TeamStatusBandProps {
  /** Kept for page-call-site compatibility; event details are intentionally not shown to students. */
  readonly eventKey?: string;
  /** Bumped by the page after a change of its own has landed: reads the line again. */
  readonly revision?: number;
}

export function TeamStatusBand({
  revision = 0,
}: TeamStatusBandProps): React.JSX.Element | null {
  const { state } = useExerciseResource(readTeamStatus, [revision], {
    keepDataOnError: keepWhenUnreachable,
  });

  const ready = state.status === "ready" ? state.data : null;
  const sentence = ready === null ? null : teamLine(ready.workspace.team_number, true);

  // Said aloud only when the line *changes*: its first appearance is part of
  // the page loading and is not announced on top of the page's own heading.
  const spoken = React.useRef<string | null>(null);
  const [announcement, setAnnouncement] = React.useState("");
  React.useEffect(() => {
    if (sentence === null) {
      return;
    }
    if (spoken.current !== null && spoken.current !== sentence) {
      setAnnouncement(sentence);
    }
    spoken.current = sentence;
  }, [sentence]);

  if (state.status === "loading") {
    return (
      <p data-slot="exercise-team-status" data-state="reading" className={`${BAND} text-ce-ink-muted`}>
        Reading your team&apos;s status…
      </p>
    );
  }
  if (state.status === "unreachable") {
    return (
      <p data-slot="exercise-team-status" data-state="unreachable" className={BAND}>
        Your team&apos;s status could not be read. Reload the page to read it again.
      </p>
    );
  }
  if (state.status !== "ready" || ready === null) {
    // Refused: the page says why, and where to go.
    return null;
  }

  return (
    <section aria-label="Your team's status" data-slot="exercise-team-status" className={BAND}>
      <dl className="flex flex-wrap items-baseline gap-x-ce-5 gap-y-ce-1">
        <div className="flex items-baseline gap-ce-2">
          <dt className="sr-only">Team</dt>
          <dd data-status="team" className="font-semibold">
            {teamLine(ready.workspace.team_number, true)}
          </dd>
        </div>
      </dl>
      <p className="ce-type-meta text-ce-ink-muted">
        <Link to="/exercise">Not your team? Pick again</Link>
        {state.unreachable === null ? null : (
          <span data-slot="exercise-team-status-stale">
            {" "}
            This line could not be read again just now, so it may be out of date.
          </span>
        )}
      </p>
      <p aria-live="polite" data-slot="exercise-team-status-live" className="sr-only">
        {announcement}
      </p>
    </section>
  );
}
