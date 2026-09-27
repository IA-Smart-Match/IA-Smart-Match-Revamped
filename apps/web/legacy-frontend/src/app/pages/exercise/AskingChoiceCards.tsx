/**
 * The three ways of asking, as cards with an inline confirm.
 *
 * DESIGN.md §6.18, owner ruling 2026-09-26: a team picks once, so the pick
 * takes two presses on the same button. The first press turns "Choose this
 * way" into "Confirm: A small reward?" in CPP Green for about five seconds,
 * with a thin underline shrinking under the label (`ce-confirm-window`). A
 * second press inside the window commits. Letting it lapse, pressing Escape,
 * or arming another card puts the button back. No pop-up, no modal, no second
 * button. Screen readers hear "Press again to confirm A small reward. Your
 * team picks once." once, through a polite live region.
 *
 * Reduced motion: the label still swaps; the underline does not move, and a
 * static "5 seconds" note carries the window instead.
 *
 * The set of choices is the server's (`asking.choices`); only the words are
 * local, in `askingChoices.ts`.
 */
import * as React from "react";
import { Check } from "lucide-react";

import { askingChoiceLabel, askingChoiceLine, askingChoiceShort } from "./askingChoices";
import { ceButton, usePrefersReducedMotion } from "./exerciseUi";

/** How long an armed button waits for its second press (§6.18: about 5 s). */
export const CONFIRM_WINDOW_MS = 5000;

// `ChoiceCard` below is one card; `useConfirmWindow` is the shared state.

export interface ConfirmWindow {
  /** The choice whose button is waiting for its second press, if any. */
  readonly armed: string | null;
  /** The spoken hint while armed, else "". */
  readonly hint: string;
  readonly reduced: boolean;
  /** A press on `choice`'s button: arms it, or — when armed — commits it. */
  readonly press: (choice: string, onChoose: (choice: string) => void) => void;
  readonly disarm: () => void;
}

/**
 * The inline confirm's state: at most one armed button, a five-second window,
 * and the polite hint. The screen maps the server's `choices` itself and
 * hands each card its slice of this.
 */
export function useConfirmWindow(chosen: string | null): ConfirmWindow {
  const reduced = usePrefersReducedMotion();
  const [armed, setArmed] = React.useState<string | null>(null);

  // The window lapses on its own. Arming another card, or committing, starts
  // or clears it through `armed` changing.
  React.useEffect(() => {
    if (armed === null) {
      return undefined;
    }
    const timer = window.setTimeout(() => setArmed(null), CONFIRM_WINDOW_MS);
    return () => window.clearTimeout(timer);
  }, [armed]);

  // Once the team has picked, nothing is armed any more.
  React.useEffect(() => {
    if (chosen !== null) {
      setArmed(null);
    }
  }, [chosen]);

  const hint =
    armed === null
      ? ""
      : `Press again to confirm ${askingChoiceShort(armed)}. Your team picks once.`;

  return {
    armed,
    hint,
    reduced,
    press: (choice, onChoose) => {
      if (armed === choice) {
        setArmed(null);
        onChoose(choice);
      } else {
        // Arming one card puts any other armed card back.
        setArmed(choice);
      }
    },
    disarm: () => setArmed(null),
  };
}

/** The polite region the hint is announced through, once per arming (§8.6). */
export function ConfirmLiveRegion({ hint }: { readonly hint: string }): React.JSX.Element {
  return (
    <p aria-live="polite" className="sr-only" data-slot="exercise-asking-confirm-live">
      {hint}
    </p>
  );
}

export function ChoiceCard({
  choice,
  chosen,
  faded,
  locked,
  armed,
  pending,
  reduced,
  hint,
  onPress,
  onEscape,
}: {
  readonly choice: string;
  readonly chosen: boolean;
  readonly faded: boolean;
  readonly locked: boolean;
  readonly armed: boolean;
  readonly pending: boolean;
  readonly reduced: boolean;
  readonly hint: string;
  readonly onPress: () => void;
  readonly onEscape: () => void;
}): React.JSX.Element {
  const label = askingChoiceLabel(choice);
  const line = askingChoiceLine(choice);
  const buttonText = armed ? `Confirm: ${askingChoiceShort(choice)}?` : "Choose this way";
  return (
    <div
      data-slot="exercise-asking-card"
      data-state={chosen ? "chosen" : armed ? "armed" : "idle"}
      className={`relative flex h-full flex-col gap-3 rounded-[14px] p-5 transition-[opacity,background-color,box-shadow] duration-[240ms] ease-[var(--ce-ease-out)] md:p-6 ${
        chosen
          ? "bg-ce-primary-tint shadow-[var(--ce-elev-2)] outline-2 outline-ce-primary"
          : armed
            ? "bg-ce-surface shadow-[var(--ce-elev-2)] outline-2 outline-ce-primary"
            : "bg-ce-surface shadow-[var(--ce-elev-1)]"
      } ${faded ? "opacity-55" : ""}`}
    >
      {chosen ? (
        <span
          aria-hidden="true"
          className="absolute top-4 right-4 flex size-8 items-center justify-center rounded-full bg-ce-gold text-ce-gold-on"
        >
          <Check className="size-5" strokeWidth={3} />
        </span>
      ) : null}
      <h3 className="ce-h3 pr-10 text-ce-ink">{label}</h3>
      {line === null ? null : <p className="ce-body text-ce-muted">{line}</p>}
      {chosen ? (
        <p className="ce-label mt-auto border-t border-ce-line pt-3 text-ce-primary-tint-ink">
          Your team chose this.
        </p>
      ) : null}
      {locked ? null : (
        <div className="mt-auto flex flex-col gap-2 pt-2">
          <button
            type="button"
            disabled={pending}
            aria-label={armed ? buttonText : `${buttonText}: ${label}`}
            onClick={onPress}
            onKeyDown={(event) => {
              if (armed && event.key === "Escape") {
                event.preventDefault();
                onEscape();
              }
            }}
            className={`${ceButton(armed ? "primary" : "secondary", "relative w-full overflow-hidden")}`}
          >
            {buttonText}
            {armed && !reduced ? (
              <span
                aria-hidden="true"
                data-slot="exercise-confirm-underline"
                className="ce-confirm-underline absolute bottom-0 left-0 h-[3px] w-full bg-ce-gold"
              />
            ) : null}
          </button>
          {armed ? (
            <p className="ce-meta text-ce-muted" aria-hidden="true">
              {hint}
              {reduced ? <span data-slot="exercise-confirm-static"> 5 seconds</span> : null}
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}
