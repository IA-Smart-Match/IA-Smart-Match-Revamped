/**
 * The time of day something was done, for "Opened at 10:42 AM." and the like.
 *
 * Ann's revisions of 2026-10-02: a change to a team's saved work, and opening
 * or closing results, "shows the time it was done". The server sends an ISO
 * timestamp; the sentence around it is written by the screen that shows it.
 *
 * Hour and minute in the browser's own locale and time zone, so a classroom
 * reads the clock on its own wall. `null` for a value that is not a time,
 * so a caller leaves the line out instead of printing "Invalid Date".
 */
export function clockTime(iso: string | null | undefined): string | null {
  if (iso === null || iso === undefined || iso === "") {
    return null;
  }
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    return null;
  }
  return at.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
