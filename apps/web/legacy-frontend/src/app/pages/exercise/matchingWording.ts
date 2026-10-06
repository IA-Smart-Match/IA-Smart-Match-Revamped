/**
 * What the matching screen says after a press (issue #321).
 *
 * Ann's revisions of 2026-10-02: "After every press, a message appears next
 * to the button saying what happened. Example: “Saved 'Setting A' for
 * Northline. You have 2 of 3 slots left.”" Her checklist: the message "stays
 * on screen until the next action" and deleting "asks first, then says
 * “Deleted.”"
 *
 * The counts come from the server's answer to the press itself (the save and
 * the delete both return the team's settings and the cap), never from a
 * number written into a screen.
 */
import type { SavedSettingsView } from "../../../lib/exerciseClient";

/** One sentence beside the saved-settings buttons, and how it is drawn. */
export interface PanelNote {
  /** `done` for something that worked; `calm` for a refusal or a failure. */
  readonly tone: "done" | "calm";
  readonly text: string;
}

/** "You have 2 of 3 slots left." — or nothing when the answer does not say. */
function slotsLeft(after: SavedSettingsView | null | undefined): string {
  const used = after?.settings?.length;
  const cap = after?.max_settings;
  if (typeof used !== "number" || typeof cap !== "number") {
    return "";
  }
  return ` You have ${Math.max(0, cap - used)} of ${cap} slots left.`;
}

/** "Saved “Setting A” for Northline. You have 2 of 3 slots left." */
export function savedSentence(
  name: string,
  eventName: string,
  after: SavedSettingsView | null | undefined,
): string {
  return `Saved “${name}” for ${eventName}.${slotsLeft(after)}`;
}

/** "Deleted “Setting A”. You have 3 of 3 slots left." */
export function deletedSentence(name: string, after: SavedSettingsView | null | undefined): string {
  return `Deleted “${name}”.${slotsLeft(after)}`;
}

/** After "Open this list". */
export function openedSentence(name: string): string {
  return `Opened “${name}”. The list above is built from it.`;
}

/** After "Show them side by side". */
export function comparingSentence(a: string, b: string): string {
  return `Showing “${a}” and “${b}” side by side, below.`;
}

/** After "Close this comparison". */
export const COMPARISON_CLOSED = "Closed the side-by-side view.";

/** Beside "The list", once a list the team asked for has landed (her checklist, section 4). */
export const LIST_UPDATED = "List updated.";
