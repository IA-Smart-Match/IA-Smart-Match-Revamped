/**
 * Marker chip, "how much we know" (DESIGN.md §6.8).
 *
 * Icon plus Ann's words, never colour alone. The words come from
 * `markers.ts` (the requirements' three phrases); an unrecognised marker
 * renders its raw string in the neutral style, with no icon, rather than
 * being folded into one of the three. Not interactive.
 */
import * as React from "react";
import { Circle, CircleDot, IdCard, type LucideIcon } from "lucide-react";

import { cn } from "../../../components/ui/utils";
import { markerLabel } from "../markers";

type MarkerTone = "neutral" | "events" | "card";

const KNOWN: Readonly<Record<string, { tone: MarkerTone; Icon: LucideIcon }>> = {
  major_only: { tone: "neutral", Icon: Circle },
  major_plus_events: { tone: "events", Icon: CircleDot },
  completed_card: { tone: "card", Icon: IdCard },
};

const TONE_CLASSES: Readonly<Record<MarkerTone, string>> = {
  neutral: "bg-ce-surface-sunk text-ce-ink",
  events: "bg-ce-avocado-tint text-ce-ink",
  card: "bg-ce-primary-tint text-ce-on-primary-tint",
};

export interface MarkerChipProps {
  /** The API's wire value: `major_only`, `major_plus_events`, `completed_card`. */
  readonly marker: string;
  readonly className?: string;
}

export function MarkerChip({ marker, className }: MarkerChipProps): React.JSX.Element {
  const known = KNOWN[marker];
  const tone: MarkerTone = known?.tone ?? "neutral";
  const Icon = known?.Icon;
  return (
    <span
      data-slot="ce-marker-chip"
      data-marker={marker}
      data-tone={tone}
      className={cn(
        "ce-type-meta inline-flex items-center gap-ce-1 whitespace-nowrap rounded-ce-pill px-ce-3 py-ce-1",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {Icon === undefined ? null : <Icon aria-hidden="true" className="size-4 shrink-0" />}
      <span>{markerLabel(marker)}</span>
    </span>
  );
}
