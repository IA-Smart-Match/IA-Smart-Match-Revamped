/**
 * `/speaker-portal/availability` (B26 T6b-4). Skeleton: the heading and tab
 * title; the form (T5's `SpeakerAvailabilityForm`) lands with T6b-2's
 * `/v1/me/availability` adapters.
 */
import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

const HEADING = "Your availability";

export function SpeakerOwnAvailability() {
  useSpeakerPageTitle(HEADING);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1
        id="my-availability-heading"
        tabIndex={-1}
        className="scroll-mt-20 text-2xl font-semibold text-foreground focus:outline-none"
      >
        {HEADING}
      </h1>
      {/* SLOT(T8d): the Speaker's own load band — a band word only, never a number (OQ-CBA-005) */}
    </div>
  );
}
