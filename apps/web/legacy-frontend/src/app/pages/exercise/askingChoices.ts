/**
 * The three ways of asking, in words a projector can carry.
 *
 * `GET …/asking-choice` returns `choices` as the stored values —
 * `better_recommendations`, `small_reward`, `required` — because those are
 * what the database's check constraint holds. It does **not** return a plain
 * words label for each, the way the list response returns `factor_labels` for
 * the four factors. That asymmetry is recorded as a backend gap on the pull
 * request; until it closes, the wording lives here.
 *
 * What is local is only the *wording*. The **set** is the server's: the screen
 * maps over `choices` from the response and never over the keys of this table,
 * so a fourth way of asking appears on screen the day the server offers one —
 * as its own value, which is ugly but honest, rather than not at all.
 *
 * The three phrases are the ones `smartmatch_domain/exercise/asking.py` writes
 * against each enum member, which are in turn the requirements' own:
 * *"promise better recommendations; small reward; required"*.
 *
 * **No percentages.** Ann's build table gives each choice an illustrative
 * share, confirmed under OQ-CE-04 (closed 2026-09-25). The API does not
 * return them, and ADR-0025 D8 would keep them off a participant's screen in
 * any case. The
 * outcome a team sees is the count the refresh actually produced.
 */

/** Ann's words per stored choice value. */
const ASKING_CHOICE_LABELS: Readonly<Record<string, string>> = {
  better_recommendations: "Promise better recommendations.",
  small_reward: "A small reward.",
  required: "Required.",
};

/**
 * One choice, in words — or the stored value itself when it is not one of the
 * three, so a choice the server adds is shown rather than swallowed.
 */
export function askingChoiceLabel(choice: string): string {
  return ASKING_CHOICE_LABELS[choice] ?? choice;
}

/**
 * One supporting line under each choice's title (DESIGN.md §6.18; wording
 * approved as drafted in §11.1). Like the labels, this is only wording: the
 * set is still the server's `choices`.
 */
const ASKING_CHOICE_LINES: Readonly<Record<string, string>> = {
  better_recommendations: "Tell them a card helps us suggest events worth their evening.",
  small_reward: "Offer something small for a completed card.",
  required: "Make the card a condition of hearing about events.",
};

/** The supporting line for a choice, or `null` for a value the server adds. */
export function askingChoiceLine(choice: string): string | null {
  return ASKING_CHOICE_LINES[choice] ?? null;
}

/** The label without its final full stop, for the sentences below. */
function bareLabel(choice: string): string {
  return askingChoiceLabel(choice).replace(/\.$/, "");
}

/** The armed button's label (§6.18, §11.1): "Confirm: A small reward?". */
export function askingChoiceConfirmLabel(choice: string): string {
  return `Confirm: ${bareLabel(choice)}?`;
}

/** The spoken hint while a choice is armed (§6.18, §11.1). */
export function askingChoiceConfirmHint(choice: string): string {
  return `Press again to confirm ${bareLabel(choice)}. Your team picks once.`;
}
