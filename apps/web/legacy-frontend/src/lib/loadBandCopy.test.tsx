/**
 * B26 T8d V-A (plan §7, §9.4): every load-band string, pure. A band word only,
 * never a number (OQ-CBA-005); nothing on an availability surface says
 * "available" (T5 §4.1, T6b-4 G2).
 */
import { describe, expect, it } from "vitest";

import type { EngagementWithoutEndTime, LoadBand, LoadReason, MatchLoad, SpeakerLoad } from "./api";
import {
  FULL_RUN_LABEL,
  LOAD_FULL_EXPLANATION,
  LOAD_FULL_NO_END_TIME,
  LOAD_NOT_RECORDED,
  RUN_LOAD_NOT_PART,
  RUN_LOAD_RECORDED,
  composeLoadText,
  currentLoadLines,
  eventsLinkName,
  excludedLoadFullText,
  gapItemText,
  loadBandWord,
  runLoadDetail,
  runLoadWord,
  type LoadAudience,
} from "./loadBandCopy";
import { speakerLoadFixture } from "@/test/speakerLoadFixture";

const BANDS: LoadBand[] = ["light", "moderate", "heavy", "full", "unknown"];
const REASONS: LoadReason[] = [
  "measured",
  "capacity_not_stated",
  "hours_unknown",
  "full_by_known_hours",
];
const AUDIENCES: LoadAudience[] = ["speaker", "connector"];
const TITLE = "Corporate treasury guest lecture";

function item(overrides: Partial<EngagementWithoutEndTime> = {}): EngagementWithoutEndTime {
  return {
    engagement_id: "e-one",
    shown: "event",
    event_title: TITLE,
    local_date: "2026-10-20",
    time_precision: "date_only",
    editable_here: false,
    ...overrides,
  };
}

const ITEMS: EngagementWithoutEndTime[] = [
  item({ time_precision: "exact" }),
  item({ time_precision: "date_only", editable_here: true }),
  item({ time_precision: "unresolved", local_date: null }),
  item({ time_precision: "date_only", editable_here: false }),
  item({
    engagement_id: null,
    shown: "other_unit",
    event_title: null,
    local_date: null,
    time_precision: null,
  }),
  item({ shown: "event_missing", event_title: null, local_date: null, time_precision: null }),
];

/** Every string the availability surfaces can show, for one audience. */
function availabilityStrings(audience: LoadAudience): string[] {
  const out: string[] = [];
  for (const band of BANDS) {
    for (const reason of REASONS) {
      for (const used of [true, false]) {
        for (const truncated of [true, false]) {
          const lines = currentLoadLines(
            speakerLoadFixture({
              band,
              reason,
              used_in_matching: used,
              engagements_without_end_time: ITEMS,
              engagements_without_end_time_truncated: truncated,
            }),
            audience,
          );
          out.push(
            ...[
              lines.heading,
              lines.word,
              lines.measuredLabel,
              lines.intro,
              lines.matching,
              lines.capacity,
              lines.listIntro,
              lines.truncated,
            ].filter((text): text is string => text !== null),
          );
        }
      }
    }
  }
  for (const entry of ITEMS) {
    const copy = gapItemText(entry, audience);
    out.push(
      ...[copy.title, copy.dateNotSet, copy.precision, copy.note].filter(
        (text): text is string => text !== null,
      ),
    );
  }
  if (audience === "connector") out.push(eventsLinkName(TITLE));
  return out;
}

/** Every string the run views can show. */
function runStrings(): string[] {
  const out = [
    FULL_RUN_LABEL,
    LOAD_FULL_EXPLANATION,
    LOAD_FULL_NO_END_TIME,
    LOAD_NOT_RECORDED,
    RUN_LOAD_NOT_PART,
    RUN_LOAD_RECORDED,
    composeLoadText(null),
    excludedLoadFullText(null),
  ];
  for (const band of BANDS) {
    out.push(runLoadWord(band));
    for (const reason of REASONS) {
      const load: MatchLoad = { band, reason };
      const detail = runLoadDetail(load);
      if (detail !== null) out.push(detail);
      out.push(composeLoadText(load), excludedLoadFullText(load));
    }
  }
  return out;
}

describe("loadBandCopy", () => {
  it.each(
    BANDS.flatMap((band) =>
      AUDIENCES.map((audience) => [band, audience] as [LoadBand, LoadAudience]),
    ),
  )(
    "every band and reason has a word and a sentence for each audience (%s, %s)",
    (band, audience) => {
      expect(loadBandWord(band).length).toBeGreaterThan(0);
      expect(runLoadWord(band).length).toBeGreaterThan(0);
      for (const used of [true, false]) {
        const lines = currentLoadLines(
          speakerLoadFixture({ band, used_in_matching: used }),
          audience,
        );
        expect(lines.word).toBe(loadBandWord(band));
        expect(lines.matching.length).toBeGreaterThan(0);
        expect(lines.intro.length).toBeGreaterThan(0);
      }
      for (const reason of REASONS) {
        const lines = currentLoadLines(
          speakerLoadFixture({ band, reason, engagements_without_end_time: [item()] }),
          audience,
        );
        if (reason === "capacity_not_stated") expect(lines.capacity).not.toBeNull();
        expect(lines.listIntro).not.toBeNull();
      }
    },
  );

  it("words each band", () => {
    expect(BANDS.map(loadBandWord)).toEqual([
      "Light",
      "Moderate",
      "Heavy",
      "Full",
      "Load not measurable",
    ]);
  });

  it("words each run detail from band and reason", () => {
    expect(runLoadDetail({ band: "light", reason: "measured" })).toBe(
      "Workload did not change the ranking.",
    );
    expect(runLoadDetail({ band: "moderate", reason: "measured" })).toBe(
      "Ranked a little lower for workload.",
    );
    expect(runLoadDetail({ band: "heavy", reason: "measured" })).toBe("Ranked lower for workload.");
    expect(runLoadDetail({ band: "unknown", reason: "capacity_not_stated" })).toBe(
      "No capacity was stated, so workload did not change the ranking.",
    );
    expect(runLoadDetail({ band: "unknown", reason: "hours_unknown" })).toBe(
      "Some confirmed engagements had no end time, so workload did not change the ranking. This Speaker's availability on Speaker contacts lists them.",
    );
  });

  it('the run Full label is exactly "Full (no override available)"', () => {
    expect(FULL_RUN_LABEL).toBe("Full (no override available)");
    expect(runLoadWord("full")).toBe(FULL_RUN_LABEL);
    expect(LOAD_FULL_EXPLANATION).toBe(
      "Full (no override available). Their confirmed and recent engagements exceed the hours they can give, so this run left them out.",
    );
    expect(excludedLoadFullText({ band: "full", reason: "full_by_known_hours" })).toBe(
      `${LOAD_FULL_EXPLANATION} Some of their engagements also have no end time.`,
    );
    expect(excludedLoadFullText({ band: "full", reason: "measured" })).toBe(LOAD_FULL_EXPLANATION);
  });

  it("compose reads Workload when matched, or not recorded", () => {
    expect(composeLoadText({ band: "moderate", reason: "measured" })).toBe(
      "Workload when matched: Moderate",
    );
    expect(composeLoadText(null)).toBe(LOAD_NOT_RECORDED);
    expect(LOAD_NOT_RECORDED).toBe("Workload not recorded for this Speaker");
  });

  it("the not-used sentence is the audience's", () => {
    expect(currentLoadLines(speakerLoadFixture(), "connector").matching).toBe(
      "Matching does not use workload yet.",
    );
    expect(currentLoadLines(speakerLoadFixture(), "speaker").matching).toBe(
      "Matching does not use your workload yet.",
    );
  });

  it("no string contains a digit or a percent sign", () => {
    const all = [
      ...runStrings(),
      ...availabilityStrings("speaker"),
      ...availabilityStrings("connector"),
    ];
    expect(all.length).toBeGreaterThan(50);
    for (const text of all) {
      expect(text).not.toMatch(/[0-9%]/);
    }
  });

  it("no speaker or connector-panel string contains the word available", () => {
    for (const audience of AUDIENCES) {
      for (const text of availabilityStrings(audience)) {
        expect(text).not.toMatch(/\bavailable\b/i);
      }
    }
  });

  it("gap items keep the title and the date for the time element", () => {
    const copy = gapItemText(item({ time_precision: "exact" }), "connector");
    expect(copy.title).toBe(TITLE);
    expect(copy.date).toBe("2026-10-20");
    expect(copy.precision).toBe("start time only");
    expect(gapItemText(item(), "speaker").precision).toBeNull();
    expect(eventsLinkName(TITLE)).toBe(
      "Add the end time on the Events page for Corporate treasury guest lecture",
    );
  });

  it("a load with no gaps has no list intro", () => {
    const load: SpeakerLoad = speakerLoadFixture({
      band: "unknown",
      reason: "capacity_not_stated",
    });
    const lines = currentLoadLines(load, "speaker");
    expect(lines.listIntro).toBeNull();
    expect(lines.capacity).toBe(
      "You have not given a capacity. Add it below so your workload can be measured.",
    );
  });
});
