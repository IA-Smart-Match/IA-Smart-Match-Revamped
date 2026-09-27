/**
 * One asking choice as a card (DESIGN.md §6.18, owner ruling 3).
 *
 * The card is a native radio (so arrow keys move between cards) plus one
 * button, "Choose this way". The first press arms an inline confirm: the same
 * button turns primary and reads "Confirm: A small reward?" for about five
 * seconds, with the `ce-confirm-window` underline shrinking under the label.
 * A second press commits. There is no pop-up and no second button.
 *
 * This file owns the look only. The timing (`useConfirmWindow`), which card is
 * armed, and the request all live in `ExerciseAskingForMore.tsx`, which maps
 * over the server's `choices` and renders one of these per value.
 */
import * as React from "react";
import { Check } from "lucide-react";

import { cn } from "../../components/ui/utils";
import {
  askingChoiceConfirmHint,
  askingChoiceConfirmLabel,
  askingChoiceLabel,
  askingChoiceLine,
} from "./askingChoices";
import { Button, ConfirmWindowUnderline } from "./desk";

/** Open: still choosable. Chosen: the team's pick. Dimmed: not picked. */
export type AskingCardState = "open" | "chosen" | "dimmed";

export interface AskingChoiceCardProps {
  /** The stored value from the server's `choices`. */
  readonly choice: string;
  /** The radio group's `name`, shared by the three cards. */
  readonly group: string;
  readonly state: AskingCardState;
  /** The radio is checked (the card being considered, or the one chosen). */
  readonly selected: boolean;
  /** The confirm window is open on this card. */
  readonly armed: boolean;
  /** This card's choice is being sent. */
  readonly saving: boolean;
  /** Another request is in flight: presses are ignored. */
  readonly busy: boolean;
  readonly reduced: boolean;
  readonly onSelect: (choice: string) => void;
  readonly onPress: (choice: string) => void;
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
}

export function AskingChoiceCard({
  choice,
  group,
  state,
  selected,
  armed,
  saving,
  busy,
  reduced,
  onSelect,
  onPress,
  onKeyDown,
}: AskingChoiceCardProps): React.JSX.Element {
  const id = React.useId();
  const label = askingChoiceLabel(choice);
  const line = askingChoiceLine(choice);
  const chosen = state === "chosen";

  return (
    <div
      data-slot="exercise-asking-card"
      data-state={state}
      data-armed={armed ? "true" : undefined}
      className={cn(
        "relative flex flex-col gap-ce-3 rounded-ce-card p-ce-4 md:p-ce-5 lg:min-h-[200px]",
        "transition-[background-color,box-shadow,opacity] duration-[240ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
        chosen ? "bg-ce-primary-tint shadow-ce-2" : "bg-ce-surface shadow-ce-1",
        (armed || chosen) && "outline-[3px] outline-ce-primary outline-solid",
        state === "dimmed" && "ce-choice-dim",
      )}
    >
      <label className="flex min-h-ce-target cursor-pointer items-start gap-ce-3 pr-ce-7 has-[:disabled]:cursor-default">
        <input
          type="radio"
          name={group}
          value={choice}
          checked={selected}
          disabled={state !== "open"}
          aria-describedby={line === null ? undefined : `${id}-line`}
          onChange={() => onSelect(choice)}
          className="mt-1.5 size-5 shrink-0 accent-[var(--ce-primary)]"
        />
        <span className="ce-type-h3 text-ce-ink">{label}</span>
      </label>
      {line === null ? null : (
        <p id={`${id}-line`} className="ce-type-body text-ce-ink-muted">
          {line}
        </p>
      )}

      {chosen ? (
        <>
          <span
            aria-hidden="true"
            data-slot="exercise-asking-seal"
            className="absolute top-ce-4 right-ce-4 flex size-8 items-center justify-center rounded-ce-pill bg-ce-gold text-ce-on-gold md:top-ce-5 md:right-ce-5"
          >
            <Check className="size-5" strokeWidth={2.5} />
          </span>
          <p className="ce-type-label mt-auto border-t border-ce-line pt-ce-3 text-ce-primary">
            Your team chose this.
          </p>
        </>
      ) : null}

      {state === "open" ? (
        <div className="mt-auto flex flex-col gap-ce-2 pt-ce-2">
          <Button
            variant={armed ? "primary" : "secondary"}
            pending={saving}
            disabled={busy && !saving}
            onClick={() => onPress(choice)}
            onKeyDown={onKeyDown}
            // Three buttons read "Choose this way"; the name says which card.
            // It starts with the visible words (WCAG 2.5.3, label in name).
            aria-label={armed ? askingChoiceConfirmLabel(choice) : `Choose this way: ${label}`}
            className="w-full"
          >
            <span className="inline-flex flex-col items-stretch">
              <span>{armed ? askingChoiceConfirmLabel(choice) : "Choose this way"}</span>
              <ConfirmWindowUnderline active={armed && !reduced} reduced={false} />
            </span>
          </Button>
          <ConfirmWindowUnderline
            active={armed && reduced}
            reduced
            className="text-center text-ce-ink-muted"
          />
          {armed ? (
            // Seen, not read: the page's live region speaks the same words.
            <p aria-hidden="true" className="ce-type-meta text-center text-ce-ink-muted">
              {askingChoiceConfirmHint(choice)}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
