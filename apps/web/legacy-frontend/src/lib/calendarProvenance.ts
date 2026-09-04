/** Source-specific provenance for the two independent legacy calendar feeds. */
import type { Provenance } from "../app/components/provenance/types.ts";

export function calendarSourceProvenance(
  available: boolean,
  isMockData: boolean,
): Provenance {
  return available && !isMockData ? "observed" : "synthetic";
}

/**
 * Banner copy must name only the source that is synthetic. Combining the two
 * flags first would make a demo assignment feed falsely relabel live event
 * windows (or the reverse) as fixture data.
 */
export function calendarSyntheticReason(
  eventsAreMockData: boolean,
  assignmentsAreMockData: boolean,
): string | null {
  if (eventsAreMockData && assignmentsAreMockData) {
    return "The calendar event and assignment feeds answered with demo/CSV rows. Every window, overlay, and count below is fixture data.";
  }
  if (eventsAreMockData) {
    return "The calendar event feed answered with demo/CSV rows. Event windows and event-derived counts are fixture data; assignment overlays retain their own provenance.";
  }
  if (assignmentsAreMockData) {
    return "The assignment feed answered with demo/CSV rows. Assignment overlays and overlay-derived counts are fixture data; calendar windows retain their own provenance.";
  }
  return null;
}
