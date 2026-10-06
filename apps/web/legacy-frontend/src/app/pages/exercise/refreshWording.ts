/**
 * Every sentence the exercise says about the refresh, in one place.
 *
 * Ann's review of 2026-10-02 asks for the refresh to say that it happened,
 * when, and what it changed, and gives the words: "Refresh done at 10:42 AM.
 * 9 people who came to Northline now count as having gone to a similar event.
 * 12 of the 22 invited people with no card completed one. 0 people stopped
 * responding." and "Already refreshed at 10:42 AM."
 *
 * **The server sends facts, never these sentences.** It sends a timestamp,
 * counts of people, and codes; this module writes the words. Two reasons. The
 * time must be the room's clock, and only the browser knows the room's time
 * zone. And the server's own sentences say "asking", never "refresh" (a test
 * there enforces it), so the one place this word is written is here.
 *
 * Counts only (ADR-0025 D8): no percentage is ever composed here.
 */
import type {
  RefreshAllTeamView,
  RefreshAllView,
  RefreshCountsView,
} from "../../../lib/exerciseClient";
import { markerLabel } from "./markers";

/** "10:42 AM", in the browser's own time zone. */
const CLOCK = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

/**
 * A server timestamp as the time on the room's clock: "10:42 AM".
 *
 * `null` when there is no timestamp or it cannot be read, so a caller can
 * leave the time out rather than print "Invalid Date". Newer browsers put a
 * narrow no-break space before "AM"; it is replaced with a plain space so the
 * text reads, copies and compares as written.
 */
export function formatClockTime(iso: string | null | undefined): string | null {
  if (iso === null || iso === undefined) {
    return null;
  }
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) {
    return null;
  }
  return CLOCK.format(when).replace(/[  ]/g, " ");
}

/** "1 person" / "9 people" / "0 people". */
function people(count: number): string {
  return count === 1 ? "1 person" : `${count} people`;
}

/** The first line of the summary: "Refresh done at 10:42 AM." */
export function refreshDoneLine(at: string | null | undefined): string {
  const time = formatClockTime(at);
  return time === null ? "Refresh done." : `Refresh done at ${time}.`;
}

/** The shut button's own words: "Already refreshed at 10:42 AM". */
export function alreadyRefreshedLabel(at: string | null | undefined): string {
  const time = formatClockTime(at);
  return time === null ? "Already refreshed" : `Already refreshed at ${time}`;
}

/**
 * What the refresh changed, in three plain sentences.
 *
 * `topics_added` counts the people who attended the first round's event; they
 * now have one more event on file. `cards_completed` of `invited_without_card`
 * is "12 of the 22". `eventName` is the first round's event as the data file
 * spells it; without one the sentence says "the first event".
 */
export function refreshChangeSentences(
  counts: RefreshCountsView,
  eventName: string | null | undefined,
): string[] {
  const event = eventName ?? "the first event";
  const went =
    counts.topics_added === 1
      ? `1 person who came to ${event} now counts as having gone to a similar event.`
      : `${counts.topics_added} people who came to ${event} now count as having gone to a similar event.`;
  const asked = counts.invited_without_card;
  const cards =
    asked === 0
      ? "Everyone your team invited already had a card."
      : `${counts.cards_completed} of the ${asked} invited ${asked === 1 ? "person" : "people"} with no card completed one.`;
  return [went, cards, `${people(counts.non_responding)} stopped responding.`];
}

/** The summary as one string, for a line that has no room for a list. */
export function refreshSummaryText(
  at: string | null | undefined,
  counts: RefreshCountsView | null,
  eventName: string | null | undefined,
): string {
  return [refreshDoneLine(at), ...(counts === null ? [] : refreshChangeSentences(counts, eventName))].join(
    " ",
  );
}

/** One "how much we know" group, before and after: "Completed card: 70 → 82". */
export interface MarkerCountLine {
  readonly marker: string;
  readonly label: string;
  readonly before: number;
  readonly after: number;
}

/** The order the three groups are listed in: most on file first. */
const MARKER_ORDER = ["completed_card", "major_plus_events", "major_only"] as const;

/** "completed card" → "Completed card". */
function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * The before-and-after counts of every profile, one line per group, in Ann's
 * words for the groups (`markers.ts`). A group the server names that is not
 * one of the three is listed after them under its own name.
 */
export function markerCountLines(counts: RefreshCountsView): MarkerCountLine[] {
  const before = counts.marker_counts_before ?? {};
  const after = counts.marker_counts_after ?? {};
  const known: readonly string[] = MARKER_ORDER;
  const extra = Object.keys({ ...before, ...after }).filter((marker) => !known.includes(marker));
  return [...known, ...extra]
    .filter((marker) => marker in before || marker in after)
    .map((marker) => ({
      marker,
      label: sentenceCase(markerLabel(marker)),
      before: before[marker] ?? 0,
      after: after[marker] ?? 0,
    }));
}

/** How many profiles the before-and-after counts cover: "all 300". */
export function markerCountTotal(counts: RefreshCountsView): number {
  return Object.values(counts.marker_counts_before ?? {}).reduce((sum, value) => sum + value, 0);
}

/** The wire value of the mark for a profile that stopped responding. */
export const STOPPED_RESPONDING = "stopped_responding";

/**
 * The words for one mark on a list entry: "New card", "New: went to
 * Northline", "Stopped responding". An unrecognised mark renders as itself,
 * as an unrecognised marker does.
 */
export function refreshMarkLabel(mark: string, eventName: string | null | undefined): string {
  if (mark === "new_card") {
    return "New card";
  }
  if (mark === "new_event") {
    return `New: went to ${eventName ?? "the first event"}`;
  }
  if (mark === STOPPED_RESPONDING) {
    return "Stopped responding";
  }
  return mark;
}

// ---------------------------------------------------------------------------
// The instructor's every-team report
// ---------------------------------------------------------------------------

/** "1 team" / "3 teams". */
function teams(count: number): string {
  return count === 1 ? "1 team" : `${count} teams`;
}

/** The report's first line: "Refreshed 2 teams. Skipped 3 teams." */
export function refreshAllHeadline(done: RefreshAllView): string {
  const all = done.teams ?? [];
  if (all.length === 0) {
    return "No team has entered a number yet, so there was nothing to refresh.";
  }
  const skipped = all.filter((team) => team.outcome === "skipped").length;
  return `Refreshed ${teams(done.refreshed)}. Skipped ${teams(skipped)}.`;
}

/** Why a team was skipped, in words, from the server's reason code. */
function skipReason(team: RefreshAllTeamView): string {
  if (team.reason_code === "no_asking_choice") {
    return "Skipped: it has not chosen a way of asking.";
  }
  if (team.reason_code === "no_round_one_run") {
    return "Skipped: it has not run results for its first event.";
  }
  if (team.reason_code === "already_refreshed") {
    const time = formatClockTime(team.refreshed_at);
    return time === null
      ? "Skipped: it was already refreshed."
      : `Skipped: it was already refreshed at ${time}.`;
  }
  // A reason this screen does not know: say it was skipped and invent no why.
  return "Skipped.";
}

/**
 * One team's line: who ("Team 2:") and what happened.
 *
 * A refreshed team gets the same summary that team reads on its own screen,
 * plus the completed-card count before and after. `nameFile` adds the data
 * file's label to the name, for a classroom split across two files where two
 * teams share a number.
 */
export function refreshAllTeamLine(
  team: RefreshAllTeamView,
  { nameFile }: { readonly nameFile: boolean },
): { readonly team: string; readonly what: string } {
  const name = nameFile
    ? `Team ${team.team_number} (${team.dataset_label}):`
    : `Team ${team.team_number}:`;
  if (team.outcome !== "refreshed") {
    return { team: name, what: skipReason(team) };
  }
  const time = formatClockTime(team.refreshed_at);
  const counts = team.refresh_counts;
  const cards = counts === null ? undefined : markerCountLines(counts)[0];
  const parts = [
    time === null ? "Refreshed." : `Refreshed at ${time}.`,
    ...(counts === null ? [] : refreshChangeSentences(counts, team.first_round_event_name)),
    ...(cards === undefined ? [] : [`${cards.label}: ${cards.before} → ${cards.after}.`]),
  ];
  return { team: name, what: parts.join(" ") };
}
