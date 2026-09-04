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

export const breakNeedExplanation =
  "A higher percentage means this volunteer has had more recent assignments and may need a break.";
