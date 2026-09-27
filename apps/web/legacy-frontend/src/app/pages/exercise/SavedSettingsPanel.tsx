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
import { Columns2 } from "lucide-react";

import type { SavedSettingsView, SavedSettingView } from "../../../lib/exerciseClient";
import { EmptySlotArt } from "./exerciseArt";
import { ceButton, Chip, Spinner } from "./exerciseUi";
import { orderedKeys } from "./WeightsControls";

export interface SavedSettingsPanelProps {
  readonly saved: SavedSettingsView;
  /** The weights currently on screen, which "save" stores under a name. */
  readonly weights: Readonly<Record<string, number>>;
  /** Ann's words per factor key, to label each saved card's four weights. */
  readonly factorLabels?: Readonly<Record<string, string>>;
  /** Saves under a name; resolves `true` only when the server accepted it. */
  readonly onSave: (name: string) => Promise<boolean>;
  /** Deletes one; resolves `true` only when the server accepted it. */
  readonly onDelete: (name: string) => Promise<boolean>;
  /** Load the list for a saved setting. */
  readonly onOpen: (name: string) => void;
  /** Show two of them side by side. */
  readonly onCompare: (a: string, b: string) => void;
}

export function SavedSettingsPanel({
  saved,
  weights,
  factorLabels,
  onSave,
  onDelete,
  onOpen,
  onCompare,
}: SavedSettingsPanelProps): React.JSX.Element {
  const [name, setName] = React.useState("");
  const [pending, setPending] = React.useState(false);
  /** The two (at most) cards ticked for "Compare", in the order they were ticked. */
  const [ticked, setTicked] = React.useState<readonly string[]>([]);

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

  // A ticked name that has since been deleted is not ticked any more.
  const live = ticked.filter((tickedName) => settings.some((setting) => setting.name === tickedName));
  const fresh = useFreshNames(settings);
  const freeSlots = Math.max(0, saved.max_settings - settings.length);

  return (
    <section data-slot="exercise-saved-settings" className="flex flex-col gap-4">
      <h2 className="ce-h2 text-ce-ink">Your team's saved settings</h2>
      <p className="ce-body text-ce-muted" data-slot="exercise-settings-cap">
        {/* The cap, as the server reports it. */}
        Your team may keep {saved.max_settings} for this event. You have {settings.length}.
      </p>

      <form
        className="ce-card flex flex-col gap-3 p-4 md:flex-row md:flex-wrap md:items-end md:gap-4 md:p-6"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim() === "") {
            return;
          }
          void run(async () => {
            const accepted = await onSave(name.trim());
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
        <div className="flex min-w-0 flex-1 flex-col gap-1 md:min-w-[16rem]">
          <label htmlFor="exercise-setting-name" className="ce-label text-ce-ink">
            Name these weights
          </label>
          <input
            id="exercise-setting-name"
            name="setting_name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="ce-input w-full"
          />
        </div>
        <button
          type="submit"
          disabled={pending || trimmed === "" || atCapForNewName}
          aria-describedby="exercise-save-note"
          className={ceButton("secondary", "w-full md:w-auto")}
        >
          {pending ? <Spinner /> : null}
          {pending ? "Saving…" : "Save these weights"}
        </button>
        <span id="exercise-save-note" className="ce-meta text-ce-muted md:basis-full">
          {atCapForNewName
            ? `Your team has ${saved.max_settings} saved settings for this event. Type one of those names to save over it, or delete one first.`
            : `Saves the ${Object.keys(weights).length} numbers now on screen.`}
        </span>
      </form>

      {settings.length === 0 ? (
        <p className="ce-body text-ce-ink">
          Your team has not saved any settings for this event yet.
        </p>
      ) : null}

      <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-6">
        {settings.map((setting) => (
          <li key={setting.name} className={fresh.has(setting.name) ? "ce-card-save" : undefined}>
            <SettingCard
              setting={setting}
              factorLabels={factorLabels}
              comparing={live.includes(setting.name)}
              compareLocked={live.length >= 2 && !live.includes(setting.name)}
              pending={pending}
              onOpen={() => onOpen(setting.name)}
              onToggleCompare={(on) =>
                setTicked((previous) => {
                  const kept = previous.filter((tickedName) => tickedName !== setting.name);
                  return on ? [...kept, setting.name] : kept;
                })
              }
              onDelete={() => run(() => onDelete(setting.name))}
            />
          </li>
        ))}
        {Array.from({ length: freeSlots }, (_, index) => (
          <li key={`free-${index}`}>
            <div className="flex h-full min-h-48 flex-col items-center justify-center gap-3 rounded-[14px] border-2 border-dashed border-ce-line-strong p-6 text-center">
              <EmptySlotArt className="h-16 w-20 text-ce-line-strong" />
              <p className="ce-meta text-ce-muted">
                Slot {settings.length + index + 1} of {saved.max_settings} is free. Save the
                weights on screen to fill it.
              </p>
            </div>
          </li>
        ))}
      </ul>

      {settings.length < 2 ? (
        <p className="ce-body text-ce-muted">Save two settings to see them side by side.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {live.length >= 2 && settings.length > 2 ? (
            <p className="ce-meta text-ce-muted" id="exercise-compare-limit">
              Two are chosen. Untick one to swap.
            </p>
          ) : null}
          <div>
            <button
              type="button"
              className={ceButton("primary", "w-full sm:w-auto")}
              disabled={live.length !== 2}
              onClick={() => {
                const [a, b] = live;
                if (a !== undefined && b !== undefined) {
                  onCompare(a, b);
                }
              }}
            >
              <Columns2 aria-hidden="true" className="size-5" />
              Show them side by side
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * One saved setting as an index card (DESIGN.md §6.11): its name, its four
 * weights as numbers (no bars), "Open this list", a "Compare" tick box, and a
 * quiet "Delete" that asks first, inline.
 */
function SettingCard({
  setting,
  factorLabels,
  comparing,
  compareLocked,
  pending,
  onOpen,
  onToggleCompare,
  onDelete,
}: {
  readonly setting: SavedSettingView;
  readonly factorLabels: Readonly<Record<string, string>> | undefined;
  readonly comparing: boolean;
  readonly compareLocked: boolean;
  readonly pending: boolean;
  readonly onOpen: () => void;
  readonly onToggleCompare: (on: boolean) => void;
  readonly onDelete: () => Promise<boolean>;
}): React.JSX.Element {
  const [confirming, setConfirming] = React.useState(false);
  const compareId = `exercise-compare-${setting.name.replace(/\s+/g, "-")}`;
  const keys =
    factorLabels === undefined ? Object.keys(setting.weights) : orderedKeys(factorLabels);

  return (
    <div
      data-slot="exercise-setting-card"
      className={`ce-card ce-lift flex h-full flex-col gap-4 p-5 md:p-6 ${
        comparing ? "outline-3 outline-ce-primary" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="ce-h3 min-w-0 break-words text-ce-ink">{setting.name}</h3>
        {comparing ? <Chip tone="primary">Comparing</Chip> : null}
      </div>
      <dl className="flex flex-col border-y border-ce-line py-2">
        {keys.map((key) => (
          <div key={key} className="flex items-baseline justify-between gap-3 py-1">
            <dt className="ce-meta text-ce-muted">{factorLabels?.[key] ?? key}</dt>
            <dd className="ce-label ce-num text-ce-ink">{(setting.weights[key] ?? 0).toFixed(2)}</dd>
          </div>
        ))}
      </dl>

      {confirming ? (
        <div className="flex flex-col gap-3 rounded-[10px] bg-ce-sunk p-3" role="group" aria-label={`Delete ${setting.name}?`}>
          <p className="ce-meta text-ce-ink">Delete {setting.name}? It cannot be brought back.</p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={ceButton("danger")}
              disabled={pending}
              onClick={() => {
                void onDelete().then((deleted) => {
                  if (!deleted) {
                    setConfirming(false);
                  }
                });
              }}
            >
              {pending ? "Deleting…" : "Delete it"}
            </button>
            <button type="button" className={ceButton("quiet", "min-h-11")} onClick={() => setConfirming(false)}>
              Keep it
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2">
          <button type="button" className={ceButton("secondary")} onClick={onOpen}>
            Open this list
          </button>
          <label
            htmlFor={compareId}
            className={`ce-label flex min-h-11 items-center gap-2 ${
              compareLocked ? "cursor-not-allowed opacity-45" : "cursor-pointer"
            }`}
          >
            <input
              id={compareId}
              type="checkbox"
              checked={comparing}
              disabled={compareLocked}
              aria-describedby={compareLocked ? "exercise-compare-limit" : undefined}
              onChange={(event) => onToggleCompare(event.target.checked)}
              className="size-5 accent-[var(--ce-primary)]"
            />
            Compare
          </label>
          <button
            type="button"
            className={ceButton("quiet", "min-h-11")}
            disabled={pending}
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Setting names that appeared since the previous render, for `ce-card-save`.
 * Empty on the first render: the panel arriving is not a card being saved.
 */
function useFreshNames(settings: readonly SavedSettingView[]): ReadonlySet<string> {
  const seen = React.useRef<ReadonlySet<string> | null>(null);
  const previous = seen.current;
  const fresh =
    previous === null
      ? new Set<string>()
      : new Set(settings.map((setting) => setting.name).filter((name) => !previous.has(name)));
  React.useEffect(() => {
    seen.current = new Set(settings.map((setting) => setting.name));
  }, [settings]);
  return fresh;
}
