/**
 * The results lock panel, locked state (DESIGN.md §6.14).
 *
 * A team learns an event is locked only when the run route says so
 * (`exercise_results_locked`); there is no team-side read of the lock. So this
 * panel appears after that refusal and carries the server's sentence verbatim.
 *
 * **It has no action.** The only way to find out whether the instructor has
 * opened the event is to send the run again, and the run is once per team per
 * event. A "Check again" button would be that one-time run under a
 * harmless-sounding name, beside the Run button that already sends it. So the
 * primary "Run results for this event" stays the only retry.
 *
 * Calm, not red (§1.6, §10): a surface card, the envelope spot art, and a
 * `Lock` chip in words. It sits in the seating chart's place (§7.8).
 */
import * as React from "react";
import { Lock } from "lucide-react";

import { EnvelopeArt } from "./resultsArt";

export interface ResultsLockPanelProps {
  /** The server's sentence, verbatim. */
  readonly message: string;
}

export function ResultsLockPanel({ message }: ResultsLockPanelProps): React.JSX.Element {
  return (
    <div
      role="status"
      data-slot="exercise-results-lock"
      className="ce-card ce-fade-rise flex flex-col gap-ce-4 p-ce-4 sm:flex-row sm:items-start md:gap-ce-6 md:p-ce-6"
    >
      <EnvelopeArt className="h-auto w-24 shrink-0 text-ce-primary md:w-[120px]" />
      <div className="flex min-w-0 flex-col items-start gap-ce-3">
        <span className="ce-type-meta inline-flex items-center gap-ce-2 rounded-ce-pill bg-ce-surface-sunk px-ce-3 py-ce-1 text-ce-ink">
          <Lock aria-hidden="true" className="size-4 shrink-0" />
          Results are closed
        </span>
        <p className="ce-type-body ce-measure text-ce-ink">{message}</p>
      </div>
    </div>
  );
}
