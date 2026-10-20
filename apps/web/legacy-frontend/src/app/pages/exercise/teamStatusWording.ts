/**
 * The words of the team's status line (DESIGN.md §6.1, issue #321).
 *
 * Ann's revisions of 2026-10-02: "Each team page has a line at the top that is
 * always visible: team number, which event, results used or not, way of
 * asking chosen or not, refresh done or not." Her checklist adds "round one
 * or round two", and that after a reload "the status line still shows where
 * the team is".
 *
 * **Nothing here is remembered by the browser.** Every word is built from
 * three reads the server already offers: the team's workspace, its events
 * (with `results_open` / `results_run`, issue #328) and its asking state
 * (with `refreshed_at`, issue #329). A reload, or a second tab, reads them
 * again and says the same thing.
 *
 * **The refresh's words are written here, not sent.** The server's own
 * sentences say "asking", never "refresh".
 */
import type { AskingStateView, EventView, TeamWorkspaceView } from "../../../lib/exerciseClient";
import { askingChoiceLabel } from "./askingChoices";
import { clockTime } from "./exerciseTime";

/** One of the exercise's rounds, as the status line needs it. */
export interface RoundStatus {
  /** 1 for the first exercise event in the file's order, 2 for the next. */
  readonly round: number;
  readonly eventKey: string;
  readonly name: string;
  /** The instructor has results for this event open right now. */
  readonly open: boolean;
  /** This team has used its one results run for this event. */
  readonly run: boolean;
}

/** One "label: value" pair on the line. */
export interface TeamStatusItem {
  /** Stable, for keys and tests: `round-1`, `asking`, `refresh`, `file`. */
  readonly key: string;
  readonly label: string;
  readonly value: string;
}

/**
 * The exercise's rounds, in order. A round is an event the file marks as one;
 * its number is its place among them by `sequence`, exactly as the event
 * picker numbers them. Never read from an event's name.
 */
export function roundsOf(events: readonly EventView[]): RoundStatus[] {
  return events
    .filter((event) => event.is_exercise_event)
    .slice()
    .sort((a, b) => a.sequence - b.sequence)
    .map((event, index) => ({
      round: index + 1,
      eventKey: event.event_key,
      name: event.name,
      open: event.results_open === true,
      run: event.results_run === true,
    }));
}

/** "You are Team 3": Ann's checklist, section 3. */
export function teamLine(teamNumber: number): string {
  return `You are Team ${teamNumber}`;
}

/** "Round 1 · Northline Analytics: Behind the Business", as the instructor's page writes it. */
export function roundLabel(round: RoundStatus, onThisPage: boolean): string {
  const label = `Round ${round.round} · ${round.name}`;
  return onThisPage ? `${label} (this page)` : label;
}

/**
 * Whether the team has used its one results run, and whether it could.
 * Run wins over open, as on the results screen (§6.14).
 */
export function resultsWords(round: Pick<RoundStatus, "open" | "run">): string {
  if (round.run) {
    return "Results run";
  }
  return round.open ? "Results open, not run yet" : "Results not open yet";
}

/** "A small reward" / "Not chosen yet". */
export function askingWords(choice: string | null): string {
  return choice === null ? "Not chosen yet" : askingChoiceLabel(choice).replace(/\.$/, "");
}

/** "Done at 10:42 AM" / "Done" (no time known) / "Not done yet". */
export function refreshWords(refreshed: boolean, at: string | null | undefined): string {
  if (!refreshed) {
    return "Not done yet";
  }
  const time = clockTime(at);
  return time === null ? "Done" : `Asked at ${time}`;
}

/**
 * Every pair on the line after the team's own, in the order Ann lists them:
 * each round with its results, the way of asking, the refresh, then the data
 * file (her checklist, section 8: "each team page says which file it uses").
 *
 * Both rounds are always listed, so the line says where the team is on every
 * page; `eventKey` marks the one the page is about.
 */
export function teamStatusItems(
  workspace: TeamWorkspaceView,
  events: readonly EventView[],
  asking: Pick<AskingStateView, "choice" | "refreshed" | "refreshed_at">,
  eventKey?: string,
): TeamStatusItem[] {
  return [
    ...roundsOf(events).map((round) => ({
      key: `round-${round.round}`,
      label: roundLabel(round, round.eventKey === eventKey),
      value: resultsWords(round),
    })),
    { key: "asking", label: "Way of asking", value: askingWords(asking.choice) },
    { key: "refresh", label: "Asked for more", value: refreshWords(asking.refreshed, asking.refreshed_at) },
    { key: "file", label: "Data file", value: workspace.dataset_label },
  ];
}

/** The whole line as one sentence run, for the announcement when it changes. */
export function teamStatusSentence(teamNumber: number, items: readonly TeamStatusItem[]): string {
  return [teamLine(teamNumber), ...items.map((item) => `${item.label}: ${item.value}`)]
    .map((part) => `${part}.`)
    .join(" ");
}

/** Which student page a round banner sits on. */
export type RoundPage = "event" | "asking" | "results";

/** "Northline Analytics: Behind the Business" -> "Northline". */
export function shortEventName(name: string): string {
  return name.trim().split(/[\s:]+/)[0] ?? name;
}

/** Dr. Wang 2026-10-23: "Round 1 of 2: Northline". */
export function roundBannerTitle(round: RoundStatus, total: number): string {
  return `Round ${round.round} of ${total}: ${shortEventName(round.name)}`;
}

/** The one line on what to do, per page (each at most 20 words). */
export function roundBannerLine(page: RoundPage, round: RoundStatus): string {
  if (page === "asking") {
    return "Start by choosing how to ask students for more information.";
  }
  if (page === "results") {
    return "See how your list did.";
  }
  return round.round === 1
    ? "Build your list of students for CBACH to email, then choose one setting and see results."
    : `Build your ${shortEventName(round.name)} list with what you now know, then choose one setting and see results.`;
}

/** Shown once round 1's results exist. */
export function roundOneDoneLine(next: RoundStatus): string {
  return `Round 1 done. Next: Round ${next.round}, ${shortEventName(next.name)}. Start by choosing how to ask students for more information.`;
}
