/**
 * The results lock panel, closed state (DESIGN.md §6.14, amended 2026-10-06).
 *
 * The team's event read says whether results are open
 * (`EventView.results_open`, issue #328), so this panel is on screen **before**
 * anybody presses: Ann's checklist of 2026-10-02 asks for a results button
 * that is grey until the instructor opens results. It carries one sentence —
 * "Results for {event} are not open yet. Ask your instructor." — which is also
 * what the run route answers, and which the grey button points at with
 * `aria-describedby` (`messageId`).
 *
 * **It may carry an action.** Finding out whether results have opened used to
 * mean sending the one-time run again, so this panel had none. It is a read
 * now, so the screen passes "Check again" as `children`.
 *
 * Calm, not red (§1.6, §10): a surface card, the envelope spot art, and a
 * `Lock` chip in words. It sits in the seating chart's place (§7.8). The
 * `status` role is on the chip and sentence only, not the whole card.
 */
import * as React from "react";
import { Lock } from "lucide-react";

import { EnvelopeArt } from "./resultsArt";

export interface ResultsLockPanelProps {
  /** Why results cannot be run yet: one sentence. */
  readonly message: string;
  /** `id` for the sentence, so the grey run button can be described by it. */
  readonly messageId?: string;
  /** One action under the sentence, e.g. "Check again". */
  readonly children?: React.ReactNode;
}

export function ResultsLockPanel({
  message,
  messageId,
  children,
}: ResultsLockPanelProps): React.JSX.Element {
  return (
    <div
      data-slot="exercise-results-lock"
      className="ce-card ce-fade-rise flex flex-col gap-ce-4 p-ce-4 sm:flex-row sm:items-start md:gap-ce-6 md:p-ce-6"
    >
      <EnvelopeArt className="h-auto w-24 shrink-0 text-ce-primary md:w-[120px]" />
      <div className="flex min-w-0 flex-col items-start gap-ce-3">
        {/* §8.6: the state is a status. Only the words carry it; the art and
            the action stay outside the live region. */}
        <div role="status" className="flex min-w-0 flex-col items-start gap-ce-3">
          <span className="ce-type-meta inline-flex items-center gap-ce-2 rounded-ce-pill bg-ce-surface-sunk px-ce-3 py-ce-1 text-ce-ink">
            <Lock aria-hidden="true" className="size-4 shrink-0" />
            Results are closed
          </span>
          <p id={messageId} className="ce-type-body ce-measure text-ce-ink">
            {message}
          </p>
        </div>
        {children}
      </div>
    </div>
  );
}
