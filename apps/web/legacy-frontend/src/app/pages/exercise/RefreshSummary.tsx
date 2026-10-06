/**
 * What the refresh did, in words: when it happened, what it changed, and the
 * "how much we know" counts for every profile before and after (DESIGN.md
 * §6.19; Ann's checklist of 2026-10-02, section 6).
 *
 * A done-tone notice (§6.20) that is not itself a live region: it mounts
 * already filled, which screen readers often do not announce. The screen that
 * shows it keeps an always-present `aria-live` line carrying the same words,
 * so the press is announced once and a reload shows the same thing silently.
 * The words come from `refreshWording.ts`; the facts come from the server.
 *
 * Before and after are written as numbers with an arrow between them, and
 * read aloud as "70 before, 82 after": the arrow is never the only signal.
 */
import * as React from "react";

import type { RefreshCountsView } from "../../../lib/exerciseClient";
import { Notice } from "./desk";
import {
  markerCountLines,
  markerCountTotal,
  refreshChangeSentences,
  refreshDoneLine,
} from "./refreshWording";

export function RefreshSummary({
  at,
  counts,
  eventName,
}: {
  /** When the refresh happened (ISO), or `null` when the server has not said. */
  readonly at: string | null;
  /** What it changed, or `null` while only the fact of it is known. */
  readonly counts: RefreshCountsView | null;
  /** The first round's event name, or `null`. */
  readonly eventName: string | null;
}): React.JSX.Element {
  const sentences = counts === null ? [] : refreshChangeSentences(counts, eventName);
  const lines = counts === null ? [] : markerCountLines(counts);
  return (
    <div data-slot="exercise-refresh-summary">
      <Notice tone="done" live={false} message={[refreshDoneLine(at), ...sentences].join(" ")}>
        {counts === null || lines.length === 0 ? undefined : (
          <MarkerCountsBeforeAfter lines={lines} total={markerCountTotal(counts)} />
        )}
      </Notice>
    </div>
  );
}

/** "How much we know, all 300 profiles" and one "70 → 82" line per group. */
export function MarkerCountsBeforeAfter({
  lines,
  total,
}: {
  readonly lines: ReturnType<typeof markerCountLines>;
  readonly total: number;
}): React.JSX.Element {
  return (
    <div data-slot="exercise-refresh-before-after" className="flex flex-col gap-ce-2">
      <p className="ce-type-label text-ce-ink">
        {`How much we know, all ${total} profiles, before and after`}
      </p>
      <ul className="ce-type-body flex flex-col gap-ce-1 text-ce-ink">
        {lines.map((line) => (
          <li key={line.marker} data-marker={line.marker}>
            {`${line.label}: `}
            <span aria-hidden="true">{`${line.before} → ${line.after}`}</span>
            <span className="sr-only">{`${line.before} before, ${line.after} after`}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
