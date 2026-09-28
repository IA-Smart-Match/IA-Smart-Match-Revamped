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
 *
 * **Layout (DESIGN.md §6.11, §7.5).** The "Name these weights" field and
 * "Save these weights" above one index card per slot — `max_settings` of
 * them, a free slot drawn dashed. Each card has a "Compare" toggle; two may
 * be ticked, then the rest lock with "Two are chosen. Untick one to swap."
 * and "Show them side by side" asks for the pair in the order ticked.
 */
import * as React from "react";
import { Columns2 } from "lucide-react";

import type { SavedSettingsView, SavedSettingView } from "../../../lib/exerciseClient";
import { Button } from "./desk";
import { FreeSettingSlot, SavedSettingCard } from "./SavedSettingCard";

export interface SavedSettingsPanelProps {
  readonly saved: SavedSettingsView;
  /** The weights currently on screen, which "save" stores under a name. */
  readonly weights: Readonly<Record<string, number>>;
  /** Ann's words per factor key, from the list response, for the cards' weight rows. */
  readonly factorLabels: Readonly<Record<string, string>>;
  /** Saves under a name; resolves `true` only when the server accepted it. */
  readonly onSave: (name: string) => Promise<boolean>;
  /** Deletes one; resolves `true` only when the server accepted it. */
  readonly onDelete: (name: string) => Promise<boolean>;
  /** Load the list for a saved setting. */
  readonly onOpen: (name: string) => void;
  /** Show two of them side by side. */
  readonly onCompare: (a: string, b: string) => void;
  /**
   * Why "save" is off right now, or `null` when it is not: the list is being
   * rebuilt, or is not the answer to the numbers on screen. Saving stores the
   * list's own weights, so it waits until those are the ones on screen.
   */
  readonly saveBlockedReason?: string | null;
}

const COMPARE_NOTE_ID = "exercise-compare-note";

export function SavedSettingsPanel({
  saved,
  weights,
  factorLabels,
  onSave,
  onDelete,
  onOpen,
  onCompare,
  saveBlockedReason = null,
}: SavedSettingsPanelProps): React.JSX.Element {
  const [name, setName] = React.useState("");
  /** Which action is running, if any: one at a time. */
  const [action, setAction] = React.useState<"save" | "delete" | null>(null);
  /** Names ticked for comparing, in the order ticked (A, then B). */
  const [ticked, setTicked] = React.useState<readonly string[]>([]);
  /** Names on screen at first render: any later card is new this visit (`ce-card-save`). */
  const [initialNames] = React.useState(
    () => new Set(saved.settings.map((setting) => setting.name)),
  );
  const pending = action !== null;

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
  async function run(kind: "save" | "delete", work: () => Promise<boolean>): Promise<boolean> {
    if (pending) {
      return false;
    }
    setAction(kind);
    try {
      return await work();
    } finally {
      setAction(null);
    }
  }

  const settings: readonly SavedSettingView[] = saved.settings;
  const trimmed = name.trim();
  const atCapForNewName =
    settings.length >= saved.max_settings &&
    trimmed !== "" &&
    !settings.some((setting) => setting.name === trimmed);
  const saveBlocked = pending || trimmed === "" || atCapForNewName || saveBlockedReason !== null;
  // A deleted setting cannot stay ticked.
  const chosen = ticked.filter((picked) => settings.some((setting) => setting.name === picked));
  const twoChosen = chosen.length === 2;
  const freeSlots = Math.max(0, saved.max_settings - settings.length);

  function toggle(settingName: string): void {
    setTicked((previous) => {
      const live = previous.filter((picked) => settings.some((setting) => setting.name === picked));
      if (live.includes(settingName)) {
        return live.filter((picked) => picked !== settingName);
      }
      return live.length >= 2 ? live : [...live, settingName];
    });
  }

  return (
    <section data-slot="exercise-saved-settings" className="flex flex-col gap-ce-4">
      <div className="flex flex-col gap-ce-2">
        <h2 className="ce-type-h2 text-ce-ink">Your team's saved settings</h2>
        <p className="ce-type-body text-ce-ink-muted" data-slot="exercise-settings-cap">
          {/* The cap, as the server reports it. */}
          Your team may keep {saved.max_settings} for this event. You have {settings.length}.
        </p>
      </div>

      <form
        className="ce-card flex flex-wrap items-end gap-ce-3 p-ce-4 md:p-ce-5"
        onSubmit={(event) => {
          event.preventDefault();
          // The button is `aria-disabled` (it stays focusable, §6.3), so
          // Enter in the box can still submit: hold the same line here.
          if (saveBlocked) {
            return;
          }
          void run("save", async () => {
            const accepted = await onSave(trimmed);
            // Only on success. A refused fourth name, or a name the server
            // will not take, leaves what the team typed where they can see
            // it and fix it.
            if (accepted) {
              setName("");
            }
            return accepted;
          });
        }}
      >
        <div className="flex min-w-0 flex-1 basis-64 flex-col gap-ce-1">
          <label htmlFor="exercise-setting-name" className="ce-type-label text-ce-ink">
            Name these weights
          </label>
          <input
            id="exercise-setting-name"
            name="setting_name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="ce-type-body min-h-ce-control w-full rounded-ce-control border-2 border-ce-line-strong bg-ce-surface px-ce-3 text-ce-ink"
          />
        </div>
        <Button
          type="submit"
          variant="secondary"
          disabled={saveBlocked}
          pending={action === "save"}
          pendingLabel="Saving…"
          describedBy="exercise-save-note"
        >
          Save these weights
        </Button>
        <span id="exercise-save-note" className="ce-type-meta basis-full text-ce-ink-muted">
          {saveBlockedReason !== null
            ? saveBlockedReason
            : atCapForNewName
            ? `Your team has ${saved.max_settings} saved settings for this event. Type one of those names to save over it, or delete one first.`
            : `Saves the ${Object.keys(weights).length} numbers now on screen.`}
        </span>
      </form>

      {settings.length === 0 ? (
        <p className="ce-type-body text-ce-ink">
          Your team has not saved any settings for this event yet.
        </p>
      ) : null}

      <ul className="grid items-stretch gap-ce-4 md:grid-cols-2 lg:grid-cols-3 md:gap-ce-5">
        {settings.map((setting, index) => {
          const comparing = chosen.includes(setting.name);
          return (
            <SavedSettingCard
              key={setting.name}
              id={`exercise-setting-${index}`}
              setting={setting}
              factorLabels={factorLabels}
              comparing={comparing}
              compareLocked={twoChosen && !comparing}
              compareNoteId={COMPARE_NOTE_ID}
              onToggleCompare={() => toggle(setting.name)}
              onOpen={() => onOpen(setting.name)}
              onDelete={() => void run("delete", () => onDelete(setting.name))}
              busy={pending}
              fresh={!initialNames.has(setting.name)}
            />
          );
        })}
        {Array.from({ length: freeSlots }, (_, index) => (
          <FreeSettingSlot
            key={`free-${index}`}
            slot={settings.length + index + 1}
            of={saved.max_settings}
          />
        ))}
      </ul>

      {settings.length < 2 ? (
        <p className="ce-type-body text-ce-ink-muted">Save two settings to see them side by side.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-ce-4">
          <Button
            leadingIcon={<Columns2 />}
            disabled={!twoChosen}
            onClick={() => onCompare(chosen[0], chosen[1])}
          >
            Show them side by side
          </Button>
          {twoChosen && settings.length > 2 ? (
            <p id={COMPARE_NOTE_ID} className="ce-type-meta text-ce-ink-muted">
              Two are chosen. Untick one to swap.
            </p>
          ) : null}
        </div>
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
    <div className="flex flex-col gap-ce-1">
      <label htmlFor={id} className="ce-type-label text-ce-ink">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="ce-type-body min-h-ce-control rounded-ce-control border-2 border-ce-line-strong bg-ce-surface px-ce-3 text-ce-ink"
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
