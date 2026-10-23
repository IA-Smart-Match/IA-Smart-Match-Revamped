/**
 * The team's status line, at the top of every team page, above the title
 * (DESIGN.md §6.1, issue #321).
 *
 * Ann's revisions of 2026-10-02 asked for team number, event, results,
 * way of asking and refresh on this line. Janice's revision of 2026-10-23
 * trims it to what a marketing student needs: which team they are on, and
 * the way back if that is wrong. The round and what the page is for are the
 * round banner's job, just below it. (`teamStatusItems` still builds the
 * longer line, should it come back.)
 *
 * **It reads the server and keeps nothing.** One read the team already has:
 * its workspace. The team number is never taken from `localStorage`
 * (`workspacePointer.ts` says why). A reload or a second tab mounts this
 * again and reads again.
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
import { readCurrentWorkspace, type TeamWorkspaceView } from "../../../lib/exerciseClient";
import { teamLine } from "./teamStatusWording";
import { useExerciseResource } from "./useExerciseResource";

async function readTeamStatus(signal: AbortSignal): Promise<TeamWorkspaceView> {
  const workspace = await readCurrentWorkspace(signal);
  // Checked, not trusted: a line built from an answer of the wrong shape would
  // state things nobody said. It is treated as an answer that did not arrive.
  if (typeof workspace?.team_number !== "number") {
    throw new ExerciseUnreachable();
  }
  return workspace;
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
const BAND =
  "sticky top-0 z-20 ce-card ce-type-body flex flex-wrap items-baseline gap-x-ce-4 gap-y-ce-1 p-ce-3 text-ce-ink md:px-ce-5";

export interface TeamStatusBandProps {
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
  const sentence = ready === null ? null : teamLine(ready.team_number);

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
      <p data-status="team" className="font-semibold">
        {sentence}
      </p>
      <p className="ce-type-meta text-ce-ink-muted">
        <Link to="/exercise">Not your team? Pick again</Link>
        {state.unreachable === null ? null : (
          <span data-slot="exercise-team-status-stale">
            {" "}
            Your team's status could not be updated. Reload the page to see the latest.
          </span>
        )}
      </p>
      <p aria-live="polite" data-slot="exercise-team-status-live" className="sr-only">
        {announcement}
      </p>
    </section>
  );
}
