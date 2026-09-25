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
