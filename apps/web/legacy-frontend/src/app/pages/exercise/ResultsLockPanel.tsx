/**
 * The results lock panel, locked state (DESIGN.md §6.14).
 *
 * A team learns an event is locked only when the run route says so
 * (`exercise_results_locked`); there is no team-side read of the lock. So this
 * panel appears after that refusal, carries the server's sentence verbatim,
 * and "Check again" asks the run route again with the same final setting —
 * the only way the screen can find out whether the instructor has opened it.
 *
 * Calm, not red (§1.6, §10): a surface card, the envelope spot art, and a
 * `Lock` chip in words. `role="status"`, like every refusal (§8.6).
 */
import * as React from "react";
import { Lock, RotateCcw } from "lucide-react";

import { Button } from "./desk";
import { EnvelopeArt } from "./resultsArt";

export interface ResultsLockPanelProps {
  /** The server's sentence, verbatim. */
  readonly message: string;
  readonly onCheckAgain: () => void;
  /** This panel's own check is in flight. */
  readonly pending: boolean;
  /** Another action on the screen is in flight. */
  readonly disabled: boolean;
}

export function ResultsLockPanel({
  message,
  onCheckAgain,
  pending,
  disabled,
}: ResultsLockPanelProps): React.JSX.Element {
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
        <Button
          variant="secondary"
          leadingIcon={<RotateCcw />}
          pending={pending}
          pendingLabel="Running…"
          disabled={disabled}
          onClick={onCheckAgain}
        >
          Check again
        </Button>
      </div>
    </div>
  );
}
