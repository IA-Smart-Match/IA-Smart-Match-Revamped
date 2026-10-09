/**
 * The time of day something was done, for "Opened at 10:42 AM." and the like.
 *
 * Ann's revisions of 2026-10-02: a change to a team's saved work, and opening
 * or closing results, "shows the time it was done". The server sends an ISO
 * timestamp; the sentence around it is written by the screen that shows it.
 *
 * **The one clock formatter of the exercise.** Every screen that prints a time
 * (the lock row, a team's opened work, the refresh sentences, the status line)
 * calls this, so a time reads the same wherever it appears.
 */

/** "10:42 AM", in the browser's own time zone, so a classroom reads its own wall clock. */
const CLOCK = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

/** "10:43:07 AM": the same clock, to the second. See `clockNow`. */
const CLOCK_TO_THE_SECOND = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
});

export interface ClockTimeOptions {
  /** Show the seconds: "10:43:07 AM". Only for `clockNow`'s three lines. */
  readonly seconds?: boolean;
}

/**
 * This browser's clock now, to the second: "10:43:07 AM".
 *
 * For the three lines that say when a press was answered and have no server
 * time to show: "Checked at …", "Teams last read at …" and "Team 3 cleared
 * at …". To the minute, a second press inside the same minute rewrote the
 * line with the same words, so it looked and sounded as if nothing happened
 * (PR #346 review). Times the server recorded ("Run at", "Refreshed at",
 * "Opened at") stay to the minute.
 */
export function clockNow(): string | null {
  return clockTime(new Date().toISOString(), { seconds: true });
}

/**
 * A server timestamp as the time on the room's clock: "10:42 AM".
 *
 * `null` when there is no timestamp or it cannot be read, so a caller leaves
 * the time out instead of printing "Invalid Date". Newer browsers put a narrow
 * no-break space before "AM"; it is replaced with a plain space so the text
 * reads, copies and compares as written.
 */
export function clockTime(
  iso: string | null | undefined,
  options: ClockTimeOptions = {},
): string | null {
  if (iso === null || iso === undefined || iso === "") {
    return null;
  }
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    return null;
  }
  const clock = options.seconds === true ? CLOCK_TO_THE_SECOND : CLOCK;
  return clock.format(at).replace(/[  ]/g, " ");
}
