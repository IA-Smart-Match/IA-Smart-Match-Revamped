/**
 * The six teams' 4-digit entry codes (issue #413), hidden until the
 * instructor asks, so a projected screen does not show them by accident.
 * Read only while shown; re-read when `reloadKey` changes (a reset issues a
 * new code).
 */
import * as React from "react";

import { listTeamCodes, type TeamCodesView } from "../../../lib/exerciseClient";
import { Button } from "./desk";
import { ExerciseNotice } from "./ExerciseScreen";
import { useExerciseResource } from "./useExerciseResource";

export function InstructorTeamCodes({
  reloadKey = 0,
}: {
  readonly reloadKey?: number;
}): React.JSX.Element {
  const [shown, setShown] = React.useState(false);
  return (
    <div className="flex flex-col gap-ce-3" data-slot="exercise-team-codes">
      <Button variant="secondary" className="self-start" onClick={() => setShown((s) => !s)}>
        {shown ? "Hide team codes" : "Show team codes"}
      </Button>
      {shown ? <CodeList reloadKey={reloadKey} /> : null}
    </div>
  );
}

function CodeList({ reloadKey }: { readonly reloadKey: number }): React.JSX.Element {
  const { state } = useExerciseResource<TeamCodesView>(listTeamCodes, [reloadKey]);
  if (state.status === "loading") {
    return <p className="ce-type-body text-ce-ink-muted">Loading the team codes…</p>;
  }
  if (state.status === "refused") {
    return <ExerciseNotice message={state.refusal.message} />;
  }
  if (state.status === "unreachable") {
    return <ExerciseNotice message={state.message} tone="problem" />;
  }
  return (
    <ul className="grid grid-cols-2 gap-ce-2 md:grid-cols-3">
      {state.data.teams.map((team) => (
        <li key={team.team_number} className="ce-type-body text-ce-ink">
          {`Team ${team.team_number}: `}
          <span className="ce-tabular font-semibold tracking-widest">{team.code}</span>
        </li>
      ))}
    </ul>
  );
}
