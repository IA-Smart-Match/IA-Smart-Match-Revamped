/**
 * A team's named weightings for one event, and the side-by-side view.
 *
 * Requirements, "Matching" row: *"A team can save up to three named settings
 * per event and view any two side by side with shared names highlighted."*
 *
 * **The cap is read, not written.** `max_settings` comes back on every
 * settings response and is what this panel says and counts against. Writing
 * `3` into a screen would be a second source of truth for a number the server
 * enforces under a lock, and the two would disagree the day it moved.
 *
 * **A fourth new name is refused by the server, with a sentence.** At the cap
 * the button is also disabled for a name the team does not already have, with
 * the reason beside it, so a class does not press into a refusal it can see
 * coming. Saving *over* a name the team already has is always allowed and
 * changes no count, so that stays enabled: the check compares the trimmed name
 * against the saved names exactly as the server does. The server still judges;
 * its refusal still shows if another browser saved in the meantime.
 *
 * `compare` is a reserved setting name — the compare route is declared before
 * the named-setting routes so the word cannot be read as a name, and the save
 * route refuses it. That refusal, too, is the server's to word.
 */
import * as React from "react";

import type { SavedSettingsView, SavedSettingView } from "../../../lib/exerciseClient";

export interface SavedSettingsPanelProps {
  readonly saved: SavedSettingsView;
  /** The weights currently on screen, which "save" stores under a name. */
  readonly weights: Readonly<Record<string, number>>;
  /** Saves under a name; resolves `true` only when the server accepted it. */
  readonly onSave: (name: string) => Promise<boolean>;
  /** Deletes one; resolves `true` only when the server accepted it. */
  readonly onDelete: (name: string) => Promise<boolean>;
  /** Load the list for a saved setting. */
  readonly onOpen: (name: string) => void;
  /** Show two of them side by side. */
  readonly onCompare: (a: string, b: string) => void;
}

const BUTTON =
  "rounded-lg border-2 border-slate-400 px-4 py-2 text-xl font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

export function SavedSettingsPanel({
  saved,
  weights,
  onSave,
  onDelete,
  onOpen,
  onCompare,
}: SavedSettingsPanelProps): React.JSX.Element {
  const [name, setName] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [a, setA] = React.useState("");
  const [b, setB] = React.useState("");

  /**
   * Run one action, and say whether it worked.
   *
   * This panel deliberately keeps no refusal state of its own. Its callers
   * already catch every refusal and show the sentence — so a second error slot
   * here was never reachable, and the `catch` that fed it never ran. Worse,
   * because the caller's guard resolved after swallowing, a *failed* save
   * looked exactly like a successful one from in here: the name box was
   * cleared and the team was left to work out that nothing had been saved.
   *
   * The caller now reports the outcome, and the only thing this panel does
   * with it is decide whether to clear the box.
   */
  async function run(action: () => Promise<boolean>): Promise<boolean> {
    if (pending) {
      return false;
    }
    setPending(true);
    try {
      return await action();
    } finally {
      setPending(false);
    }
  }

  const settings: readonly SavedSettingView[] = saved.settings;
  const trimmed = name.trim();
  const atCapForNewName =
    settings.length >= saved.max_settings &&
    trimmed !== "" &&
    !settings.some((setting) => setting.name === trimmed);

  return (
    <section data-slot="exercise-saved-settings" className="flex flex-col gap-4">
      <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
        Your team's saved settings
      </h2>
      <p className="text-xl text-slate-600 dark:text-slate-300" data-slot="exercise-settings-cap">
        {/* The cap, as the server reports it. */}
        Your team may keep {saved.max_settings} for this event. You have {settings.length}.
      </p>

      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim() === "") {
            return;
          }
          void run(async () => {
            const saved = await onSave(name.trim());
            // Only on success. A refused fourth name, or a name the server
            // will not take, leaves what the team typed where they can see
            // it and fix it.
            if (saved) {
              setName("");
            }
            return saved;
          });
        }}
      >
        <div className="flex flex-col gap-1">
          <label
            htmlFor="exercise-setting-name"
            className="text-xl text-slate-800 dark:text-slate-100"
          >
            Call these weights
          </label>
          <input
            id="exercise-setting-name"
            name="setting_name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-72 rounded-lg border-2 border-slate-400 px-3 py-2 text-2xl focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-50"
          />
        </div>
        <button
          type="submit"
          disabled={pending || trimmed === "" || atCapForNewName}
          aria-describedby="exercise-save-note"
          className={BUTTON}
        >
          Save these weights
        </button>
        <span id="exercise-save-note" className="text-lg text-slate-600 dark:text-slate-300">
          {atCapForNewName
            ? `Your team has ${saved.max_settings} saved settings for this event. Type one of those names to save over it, or delete one first.`
            : `Saves the ${Object.keys(weights).length} numbers now on screen.`}
        </span>
      </form>

      {settings.length === 0 ? (
        <p className="text-xl text-slate-700 dark:text-slate-200">
          Your team has not saved any settings for this event yet.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {settings.map((setting) => (
            <li key={setting.name} className="flex flex-wrap items-center gap-3 text-xl">
              <span className="font-semibold">{setting.name}</span>
              <button type="button" className={BUTTON} onClick={() => onOpen(setting.name)}>
                Open this list
              </button>
              <button
                type="button"
                className={BUTTON}
                disabled={pending}
                onClick={() => void run(() => onDelete(setting.name))}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}

      {settings.length < 2 ? (
        <p className="text-xl text-slate-600 dark:text-slate-300">
          Save two settings to see them side by side.
        </p>
      ) : (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (a !== "" && b !== "") {
              onCompare(a, b);
            }
          }}
        >
          <SettingPicker id="exercise-compare-a" label="Compare" value={a} onChange={setA} settings={settings} />
          <SettingPicker id="exercise-compare-b" label="with" value={b} onChange={setB} settings={settings} />
          <button type="submit" className={BUTTON} disabled={a === "" || b === ""}>
            Show them side by side
          </button>
        </form>
      )}
    </section>
  );
}

/** One saved setting chosen from a list; shared with the results screen's final-setting picker. */
export function SettingPicker({
  id,
  label,
  value,
  onChange,
  settings,
}: {
  readonly id: string;
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly settings: readonly SavedSettingView[];
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xl text-slate-800 dark:text-slate-100">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border-2 border-slate-400 px-3 py-2 text-2xl focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-50"
      >
        <option value="">Choose a setting</option>
        {settings.map((setting) => (
          <option key={setting.name} value={setting.name}>
            {setting.name}
          </option>
        ))}
      </select>
    </div>
  );
}
