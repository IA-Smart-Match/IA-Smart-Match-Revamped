/**
 * One saved setting as an index card (DESIGN.md §6.11), and a free slot.
 *
 * The card shows the name, the four weights in Ann's words with the numbers
 * the team chose (no bars: a weight is the team's input, not a score), and
 * three actions: "Open this list", a "Compare" toggle, and "Delete" behind an
 * inline confirm — "Delete Balanced? It cannot be brought back." / "Delete
 * it" / "Keep it" (§11.1). Nothing here calls the server; the panel does.
 */
import * as React from "react";

import type { SavedSettingView } from "../../../lib/exerciseClient";
import { cn } from "../../components/ui/utils";
import { Button, formatWeight } from "./desk";
import { EmptySlotArt } from "./EmptySlotArt";
import { orderedFactorKeys } from "./WeightsControls";

export interface SavedSettingCardProps {
  readonly setting: SavedSettingView;
  /** Unique within the page; prefixes the element ids. */
  readonly id: string;
  readonly factorLabels: Readonly<Record<string, string>>;
  readonly comparing: boolean;
  /** Two others are ticked: this toggle is off and says why via `compareNoteId`. */
  readonly compareLocked: boolean;
  readonly compareNoteId: string;
  readonly onToggleCompare: () => void;
  readonly onOpen: () => void;
  readonly onDelete: () => void;
  /** Another save or delete is running. */
  readonly busy: boolean;
  /** Saved during this visit: the `ce-card-save` entrance. */
  readonly fresh: boolean;
}

export function SavedSettingCard({
  setting,
  id,
  factorLabels,
  comparing,
  compareLocked,
  compareNoteId,
  onToggleCompare,
  onOpen,
  onDelete,
  busy,
  fresh,
}: SavedSettingCardProps): React.JSX.Element {
  const [confirming, setConfirming] = React.useState(false);
  const deleteButton = React.useRef<HTMLButtonElement>(null);
  const keepButton = React.useRef<HTMLButtonElement>(null);
  const nameId = `${id}-name`;
  // Ann's words for each weight the setting holds; a key with no label is
  // dropped rather than printed, and the Undecided label is not a weight.
  const rows = orderedFactorKeys(factorLabels).filter((key) => key in setting.weights);

  React.useEffect(() => {
    if (confirming) {
      keepButton.current?.focus();
    }
  }, [confirming]);

  function keep(): void {
    setConfirming(false);
    // Put focus back where the question was asked.
    window.setTimeout(() => deleteButton.current?.focus(), 0);
  }

  return (
    <li
      data-slot="exercise-setting-card"
      data-comparing={comparing ? "true" : undefined}
      className={cn(
        "ce-card ce-lift flex min-w-0 flex-col gap-ce-4 p-ce-4 md:p-ce-5",
        comparing && "outline-3 outline-offset-0 outline-ce-primary outline-solid",
        fresh && "ce-card-save",
      )}
    >
      <div className="flex items-start justify-between gap-ce-3">
        <h3 id={nameId} className="ce-type-h3 min-w-0 break-words text-ce-ink">
          {setting.name}
        </h3>
        {comparing ? (
          <span className="ce-type-meta shrink-0 rounded-ce-pill bg-ce-primary-tint px-ce-3 py-ce-1 text-ce-on-primary-tint">
            Comparing
          </span>
        ) : null}
      </div>

      <dl className="flex flex-col border-y border-ce-line py-ce-2">
        {rows.map((key) => (
          <div key={key} className="flex items-baseline justify-between gap-ce-3 py-ce-1">
            <dt className="ce-type-meta text-ce-ink-muted">{factorLabels[key]}</dt>
            <dd className="ce-type-value text-ce-ink">{formatWeight(setting.weights[key] ?? 0)}</dd>
          </div>
        ))}
      </dl>

      {confirming ? (
        <div role="group" aria-labelledby={`${id}-confirm`} className="flex flex-col gap-ce-3">
          <p id={`${id}-confirm`} className="ce-type-body text-ce-ink">
            Delete {setting.name}? It cannot be brought back.
          </p>
          <div className="flex flex-wrap gap-ce-3">
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => {
                setConfirming(false);
                onDelete();
              }}
            >
              Delete it
            </Button>
            <Button ref={keepButton} variant="secondary" onClick={keep}>
              Keep it
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-x-ce-3 gap-y-ce-1">
          <Button variant="secondary" describedBy={nameId} onClick={onOpen}>
            Open this list
          </Button>
          <label
            className={cn(
              "ce-type-label flex min-h-ce-target items-center gap-ce-2 text-ce-ink",
              compareLocked ? "cursor-not-allowed opacity-45" : "cursor-pointer",
            )}
          >
            <input
              type="checkbox"
              checked={comparing}
              disabled={compareLocked}
              aria-describedby={compareLocked ? compareNoteId : undefined}
              onChange={onToggleCompare}
              className="size-5 accent-ce-primary"
            />
            Compare<span className="sr-only"> {setting.name}</span>
          </label>
          <Button
            ref={deleteButton}
            variant="quiet"
            disabled={busy}
            aria-label={`Delete ${setting.name}`}
            onClick={() => setConfirming(true)}
          >
            Delete
          </Button>
        </div>
      )}
    </li>
  );
}

/** A free slot (§6.11 E): dashed outline, spot art, and where it comes from. */
export function FreeSettingSlot({
  slot,
  of,
}: {
  readonly slot: number;
  readonly of: number;
}): React.JSX.Element {
  return (
    <li
      data-slot="exercise-setting-free"
      className="flex min-h-40 flex-col items-center justify-center gap-ce-3 rounded-ce-card border-2 border-dashed border-ce-line-strong p-ce-4 text-center md:p-ce-5"
    >
      <EmptySlotArt className="w-20" />
      <p className="ce-type-meta ce-measure text-ce-ink-muted">
        Slot {slot} of {of} is free. Save the weights on screen to fill it.
      </p>
    </li>
  );
}
