/**
 * The four adjustable factors, in Ann's plain words.
 *
 * Requirements, "Matching" row: *"four adjustable factors, labeled in plain
 * words: same major; said they are interested in this topic; career goal fits
 * this event; went to similar events before"*. Those labels are not written
 * here — they arrive as `factor_labels` on every list response, keyed by the
 * rulebook's factor keys, and a key is never rendered. A screen that wrote the
 * four phrases into itself would be a second copy of Ann's wording, drifting
 * from the server's the first time she changes one.
 *
 * The numbers a team types *are* shown, and that is not a breach of ADR-0025
 * D8: D8 forbids a score, a percentage or a confidence — something the app
 * calculated about a person. A weight is the team's own input, and the whole
 * lesson turns on the team seeing what it chose.
 *
 * The starting values are the server's (OQ-CE-02 is open: what the four
 * factors weigh when a team opens an event is not settled). This screen sends
 * no weights at all until a team changes one, which is what makes the server's
 * placeholder defaults the defaults.
 */
import * as React from "react";

import { EXERCISE_FACTOR_KEYS } from "../../../lib/exerciseClient";

export interface WeightsControlsProps {
  /** Ann's words per factor key, from the list response. */
  readonly factorLabels: Readonly<Record<string, string>>;
  /** The weights the current list was built with. */
  readonly weights: Readonly<Record<string, number>>;
  readonly onChange: (weights: Readonly<Record<string, number>>) => void;
  readonly disabled?: boolean;
}

/**
 * The factor keys to show, in a stable order.
 *
 * The rulebook's four first, then anything else the server sent — so a fifth
 * factor appearing on the response is displayed rather than silently dropped,
 * and the four do not reshuffle when a key's order in the JSON changes.
 */
function orderedKeys(factorLabels: Readonly<Record<string, string>>): string[] {
  const known = EXERCISE_FACTOR_KEYS.filter((key) => key in factorLabels);
  const extra = Object.keys(factorLabels).filter(
    (key) => !(EXERCISE_FACTOR_KEYS as readonly string[]).includes(key),
  );
  return [...known, ...extra];
}

export function WeightsControls({
  factorLabels,
  weights,
  onChange,
  disabled = false,
}: WeightsControlsProps): React.JSX.Element {
  const keys = orderedKeys(factorLabels);

  function setOne(key: string, raw: string): void {
    const value = Number.parseFloat(raw);
    if (Number.isNaN(value)) {
      return;
    }
    // A new object, never a mutation of the one the response gave us.
    onChange({ ...weights, [key]: value });
  }

  return (
    <fieldset className="border-0 p-0" data-slot="exercise-weights">
      <legend className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
        How much each thing counts
      </legend>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {keys.map((key) => {
          const inputId = `exercise-weight-${key}`;
          return (
            <div key={key} className="flex flex-col gap-1">
              <label htmlFor={inputId} className="text-xl text-slate-800 dark:text-slate-100">
                {/* Ann's words. The key is the input's name, never its label. */}
                {factorLabels[key]}
              </label>
              <input
                id={inputId}
                name={key}
                type="number"
                min={0}
                step={0.05}
                value={weights[key] ?? 0}
                disabled={disabled}
                onChange={(event) => setOne(key, event.target.value)}
                className="w-40 rounded-lg border-2 border-slate-400 px-3 py-2 text-2xl focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-50"
              />
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
