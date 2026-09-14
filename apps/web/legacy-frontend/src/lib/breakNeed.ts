/**
 * DESIGN.md's "Break need" labels for a speaker's recovery/workload status.
 *
 * "Break need" describes recent workload, not a medical condition or a
 * judgment about the speaker (DESIGN.md, "Preferred terminology"). This is
 * the single place that maps a server-reported status string to the four
 * user-facing labels; a page must not invent its own wording or its own
 * percentage-to-label thresholds.
 */
export function breakNeedLabel(status: string | null | undefined): string {
  switch (status?.trim().toLowerCase()) {
    case "available":
    case "fresh":
      return "Available";
    case "needs rest":
    case "steady":
    case "busy":
      return "Consider a break";
    case "rest recommended":
    case "on cooldown":
    case "at risk":
    case "cooldown":
      return "Break recommended";
    default:
      return "Not enough recent assignment data";
  }
}

/** The disclosure DESIGN.md requires wherever a break-need percentage appears. */
export const breakNeedExplanation =
  "A higher percentage means this speaker has had more recent assignments and may need a break.";
