/**
 * The `load` block every `SpeakerAvailability` stub carries (B26 T8d plan §9.4).
 *
 * Not a `.test.tsx`, so Vitest does not collect it. Defaults to a measured
 * Light band that matching does not use yet, with no engagement lacking an end
 * time: the quietest block the server can send.
 */
import type { SpeakerLoad } from "@/lib/api";

export function speakerLoadFixture(overrides: Partial<SpeakerLoad> = {}): SpeakerLoad {
  return {
    band: "light",
    reason: "measured",
    as_of: "2026-10-06",
    used_in_matching: false,
    engagements_without_end_time: [],
    engagements_without_end_time_truncated: false,
    ...overrides,
  };
}
