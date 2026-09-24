/**
 * Every load-band string the frontend shows (B26 T8d plan §7), and nothing else.
 *
 * Pure: no React, no request. A band is a **word**, never a number, a ratio or
 * a multiplier (OQ-CBA-005); this module switches on `band` and `reason` and
 * never reads any other field of a load. The run read's wire still carries
 * hours for audit; `MatchLoad` does not type them, and this file does not
 * reach for them.
 *
 * Two families:
 *
 * - **Run views** (Connector, stored at run time): the card's band word and
 *   detail, the run header row, the compose row, and the `load_full`
 *   exclusion. `FULL_RUN_LABEL` is spelled here and nowhere else.
 * - **Availability surfaces** (current, Connector panel and Speaker page):
 *   none of these strings says "available" (T5 §4.1, T6b-4 G2), so Full reads
 *   "Full" with "There is no override yet" instead of the run label.
 */
import type { EngagementWithoutEndTime, LoadBand, MatchLoad, SpeakerLoad } from "./api";

export type LoadAudience = "speaker" | "connector";

// ---------------------------------------------------------------------------
// Band words
// ---------------------------------------------------------------------------

const BAND_WORDS: Readonly<Record<LoadBand, string>> = {
  light: "Light",
  moderate: "Moderate",
  heavy: "Heavy",
  full: "Full",
  unknown: "Load not measurable",
};

/** The band as a word, for the availability surfaces. */
export function loadBandWord(band: LoadBand): string {
  return BAND_WORDS[band];
}

// ---------------------------------------------------------------------------
// Run views (§7.1)
// ---------------------------------------------------------------------------

/** Verbatim, parent §11 risk 3. Run views only: it contains "available". */
export const FULL_RUN_LABEL = "Full (no override available)";

export const WORKLOAD_TERM = "Workload";
export const RUN_LOAD_RECORDED = "Recorded per Speaker below";
export const RUN_LOAD_NOT_PART = "Not part of this run's matching";
/** `load_recorded` true but no block for this Speaker: a defect shown, never a default band. */
export const LOAD_NOT_RECORDED = "Workload not recorded for this Speaker";

const LOAD_FULL_REASON =
  "Their confirmed and recent engagements exceed the hours they can give, so this run left them out.";
/** The `load_full` exclusion token's words (the `MATCH_INELIGIBILITY_EXPLANATIONS` entry). */
export const LOAD_FULL_EXPLANATION = `${FULL_RUN_LABEL}. ${LOAD_FULL_REASON}`;
export const LOAD_FULL_NO_END_TIME = "Some of their engagements also have no end time.";

/** The band word on a run view: Full reads the run label. */
export function runLoadWord(band: LoadBand): string {
  return band === "full" ? FULL_RUN_LABEL : loadBandWord(band);
}

/** The card's detail sentence, or null for a band and reason the server never pairs. */
export function runLoadDetail(load: MatchLoad): string | null {
  switch (load.band) {
    case "light":
      return load.reason === "measured" ? "Workload did not change the ranking." : null;
    case "moderate":
      return load.reason === "measured" ? "Ranked a little lower for workload." : null;
    case "heavy":
      return load.reason === "measured" ? "Ranked lower for workload." : null;
    case "full":
      return load.reason === "full_by_known_hours"
        ? `${LOAD_FULL_REASON} ${LOAD_FULL_NO_END_TIME}`
        : LOAD_FULL_REASON;
    case "unknown":
      if (load.reason === "capacity_not_stated") {
        return "No capacity was stated, so workload did not change the ranking.";
      }
      if (load.reason === "hours_unknown") {
        return (
          "Some confirmed engagements had no end time, so workload did not change the ranking. " +
          "This Speaker's availability on Speaker contacts lists them."
        );
      }
      return null;
  }
}

/** The compose row: the band stored when the run matched this Speaker. */
export function composeLoadText(load: MatchLoad | null | undefined): string {
  return load ? `Workload when matched: ${runLoadWord(load.band)}` : LOAD_NOT_RECORDED;
}

/** The `load_full` exclusion's words, plus the end-time sentence when some hours were unknown. */
export function excludedLoadFullText(load: MatchLoad | null | undefined): string {
  return load?.reason === "full_by_known_hours"
    ? `${LOAD_FULL_EXPLANATION} ${LOAD_FULL_NO_END_TIME}`
    : LOAD_FULL_EXPLANATION;
}

// ---------------------------------------------------------------------------
// Availability surfaces: the current band (§7.2 Connector, §7.3 Speaker)
// ---------------------------------------------------------------------------

interface AudienceCopy {
  heading: string;
  intro: string;
  notUsed: string;
  used: Readonly<Record<LoadBand, string>>;
  capacityNotStated: string;
  hoursUnknown: string;
  fullByKnownHours: string;
  truncated: string;
}

const CURRENT: Readonly<Record<LoadAudience, AudienceCopy>> = {
  connector: {
    heading: "Workload",
    intro: "Recent and upcoming confirmed engagements, against the stated capacity.",
    notUsed: "Matching does not use workload yet.",
    used: {
      light: "Matching does not lower this Speaker's ranking for workload.",
      moderate: "Matching ranks this Speaker a little lower for workload.",
      heavy: "Matching ranks this Speaker lower for workload.",
      full: "New matching runs leave this Speaker out until the workload drops. There is no override yet.",
      unknown: "Matching does not change this Speaker's ranking until workload can be measured.",
    },
    capacityNotStated: "No capacity is stated. Add it below to measure workload.",
    hoursUnknown: "These confirmed engagements have no end time, so their hours cannot be counted:",
    fullByKnownHours:
      "The engagements with known hours already exceed the capacity. These others have no end time:",
    truncated: "More engagements also have no end time.",
  },
  speaker: {
    heading: "Your workload",
    intro: "Your recent and upcoming confirmed engagements, against the capacity you gave.",
    notUsed: "Matching does not use your workload yet.",
    used: {
      light: "Your workload does not lower your place in matching.",
      moderate: "Matching ranks you a little lower while your workload is Moderate.",
      heavy: "Matching ranks you lower while your workload is Heavy.",
      full: "You are not put forward for new events until your workload drops. Your Speaker Connector can tell you more.",
      unknown: "Your workload does not change matching until it can be measured.",
    },
    capacityNotStated:
      "You have not given a capacity. Add it below so your workload can be measured.",
    hoursUnknown:
      "These engagements have no end time yet, so their hours cannot be counted. Your Speaker Connector can add them:",
    fullByKnownHours:
      "Your engagements with known hours already exceed your capacity. These others have no end time yet:",
    truncated: "More of your engagements also have no end time.",
  },
};

export interface CurrentLoadLines {
  heading: string;
  word: string;
  /** Precedes the `<time>` holding `as_of`. */
  measuredLabel: string;
  intro: string;
  /** Whether and how matching uses the band. */
  matching: string;
  /** Set when no capacity is stated. */
  capacity: string | null;
  /** Introduces the list of engagements without an end time; null when the list is empty. */
  listIntro: string | null;
  /** Set when the server listed only the first engagements. */
  truncated: string | null;
}

/** The sentences for one current band, in reading order. */
export function currentLoadLines(load: SpeakerLoad, audience: LoadAudience): CurrentLoadLines {
  const copy = CURRENT[audience];
  const listed = load.engagements_without_end_time.length > 0;
  return {
    heading: copy.heading,
    word: loadBandWord(load.band),
    measuredLabel: "Measured",
    intro: copy.intro,
    matching: load.used_in_matching ? copy.used[load.band] : copy.notUsed,
    capacity: load.reason === "capacity_not_stated" ? copy.capacityNotStated : null,
    listIntro: listed
      ? load.reason === "full_by_known_hours"
        ? copy.fullByKnownHours
        : copy.hoursUnknown
      : null,
    truncated: load.engagements_without_end_time_truncated ? copy.truncated : null,
  };
}

// ---------------------------------------------------------------------------
// One engagement without an end time
// ---------------------------------------------------------------------------

export interface GapItemCopy {
  /** The event title, shown first; null when the item is a sentence. */
  title: string | null;
  /** `YYYY-MM-DD` for a `<time>` element, or null. */
  date: string | null;
  /** Shown in place of the date when the event has none. */
  dateNotSet: string | null;
  /** Connector only: what the stored time says. */
  precision: string | null;
  /** A sentence standing for, or following, the title. */
  note: string | null;
}

const PRECISION: Readonly<Record<"exact" | "date_only", string>> = {
  exact: "start time only",
  date_only: "date only, no times",
};

/** The words for one engagement without an end time, for one audience. */
export function gapItemText(item: EngagementWithoutEndTime, audience: LoadAudience): GapItemCopy {
  const none: GapItemCopy = {
    title: null,
    date: null,
    dateNotSet: null,
    precision: null,
    note: null,
  };
  if (item.shown === "other_unit") {
    return {
      ...none,
      note:
        audience === "connector"
          ? "An engagement another unit recorded. That unit's Speaker Connector can add the end time."
          : "An engagement another unit recorded.",
    };
  }
  if (item.shown === "event_missing") {
    return {
      ...none,
      note:
        audience === "connector"
          ? "An engagement whose event record is missing."
          : "An engagement whose event details are no longer on file.",
    };
  }
  const dated = item.local_date !== null && item.time_precision !== "unresolved";
  const precision =
    audience === "connector" && dated && item.time_precision !== null
      ? PRECISION[item.time_precision as "exact" | "date_only"]
      : null;
  return {
    title: item.event_title,
    date: dated ? item.local_date : null,
    dateNotSet: dated ? null : "date not set",
    precision,
    note:
      audience === "connector" && !item.editable_here
        ? "Recorded from an imported listing, so it cannot be edited here."
        : null,
  };
}

/** The Events link's visible text, around the title that only its accessible name adds. */
export const EVENTS_LINK_TEXT = {
  before: "Add the end time",
  after: "on the Events page",
} as const;

/** The Events link's accessible name: its visible text with the title added (WCAG 2.5.3). */
export function eventsLinkName(title: string | null): string {
  return title
    ? `${EVENTS_LINK_TEXT.before} for ${title} ${EVENTS_LINK_TEXT.after}`
    : `${EVENTS_LINK_TEXT.before} ${EVENTS_LINK_TEXT.after}`;
}

/** Where a Connector adds an end time. The Events page has no per-event link yet (OQ-5). */
export const EVENTS_PAGE_PATH = "/coordinator-portal/events";
