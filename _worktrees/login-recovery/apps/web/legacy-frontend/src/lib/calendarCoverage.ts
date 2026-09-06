/**
 * Honest rollups for the legacy calendar's categorical coverage signal.
 *
 * A missing/unrecognised status is `unknown`, not an uncovered window. It
 * also prevents an exact coverage ratio because the row may ultimately fall
 * on either side of that ratio. Keeping this rule in a pure helper lets the
 * dashboard and its regression tests share the same definition.
 */
import type { CoverageStatus } from "./api.ts";

export interface CalendarCoverageSummary {
  readonly total: number;
  readonly covered: number;
  readonly explicitlyOpen: number;
  readonly unknown: number;
  readonly fullyResolved: boolean;
  readonly coverageRatio: number | null;
}

export function summarizeCalendarCoverage(
  statuses: readonly CoverageStatus[],
): CalendarCoverageSummary {
  const covered = statuses.filter((status) => status === "covered").length;
  const explicitlyOpen = statuses.filter(
    (status) => status === "partial" || status === "needs_coverage",
  ).length;
  const unknown = statuses.filter((status) => status === "unknown").length;
  const fullyResolved = unknown === 0;

  return {
    total: statuses.length,
    covered,
    explicitlyOpen,
    unknown,
    fullyResolved,
    coverageRatio:
      statuses.length > 0 && fullyResolved ? covered / statuses.length : null,
  };
}
