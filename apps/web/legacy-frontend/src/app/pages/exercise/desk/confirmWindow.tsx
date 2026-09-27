/**
 * `ce-confirm-window` (DESIGN.md §5, §6.18, ruling 3): a press arms an action
 * for five seconds; a second press inside the window commits it; the window
 * lapsing, Escape, or `cancel()` reverts it. No pop-up, no second button.
 *
 * The hook owns the timing only. The caller owns the words — "Choose this
 * way" / "Confirm: A small reward?" and the spoken hint come from DESIGN.md
 * §11.1 and are rendered by the page, so this module holds no copy beyond
 * the reduced-motion helper §5 names ("5 seconds").
 */
import * as React from "react";

import { CE_MOTION_MS } from "./motion";

/**
 * A second press this soon after arming is treated as the same click (a
 * double-click), not as the confirmation. A held Enter repeats after the OS
 * delay (about 500ms), which is past this guard.
 */
export const CONFIRM_GUARD_MS = 300;

/** "5 seconds" for 5000ms; "1 second" for 1000ms. */
export function confirmWindowHelper(windowMs: number): string {
  const seconds = Math.max(1, Math.round(windowMs / 1000));
  return seconds === 1 ? "1 second" : `${seconds} seconds`;
}

export interface ConfirmWindowOptions {
  readonly onConfirm: () => void;
  readonly windowMs?: number;
}

export interface ConfirmWindow {
  /** True while the second press would commit. */
  readonly armed: boolean;
  /** First press arms; a press while armed confirms. */
  readonly press: () => void;
  /** Revert without committing (another card chosen, focus left…). */
  readonly cancel: () => void;
  /** Spread onto the button: Escape reverts. */
  readonly onKeyDown: (event: Pick<React.KeyboardEvent, "key">) => void;
}

export function useConfirmWindow({
  onConfirm,
  windowMs = CE_MOTION_MS.confirmWindow,
}: ConfirmWindowOptions): ConfirmWindow {
  const [armed, setArmed] = React.useState(false);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const armedRef = React.useRef(false);
  const armedAt = React.useRef(0);
  const confirmRef = React.useRef(onConfirm);
  confirmRef.current = onConfirm;

  const clear = React.useCallback((): void => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const cancel = React.useCallback((): void => {
    clear();
    armedRef.current = false;
    setArmed(false);
  }, [clear]);

  const press = React.useCallback((): void => {
    if (armedRef.current) {
      if (Date.now() - armedAt.current < CONFIRM_GUARD_MS) {
        return;
      }
      cancel();
      confirmRef.current();
      return;
    }
    armedRef.current = true;
    armedAt.current = Date.now();
    setArmed(true);
    clear();
    timer.current = setTimeout(cancel, windowMs);
  }, [cancel, clear, windowMs]);

  const onKeyDown = React.useCallback(
    (event: Pick<React.KeyboardEvent, "key">): void => {
      if (event.key === "Escape" && armedRef.current) {
        cancel();
      }
    },
    [cancel],
  );

  React.useEffect(() => clear, [clear]);

  return { armed, press, cancel, onKeyDown };
}

export interface ConfirmWindowUnderlineProps {
  readonly active: boolean;
  readonly reduced: boolean;
  readonly windowMs?: number;
  /**
   * Shown instead of the underline under reduced motion (DESIGN.md §5).
   * Defaults to the window's length in words ("5 seconds").
   */
  readonly reducedHelper?: string;
  readonly className?: string;
}

/**
 * The 2px underline that shrinks from full width to 0 across the window.
 * Place it inside the armed button, under the label. Reduced motion shows a
 * static helper instead.
 */
export function ConfirmWindowUnderline({
  active,
  reduced,
  windowMs = CE_MOTION_MS.confirmWindow,
  reducedHelper,
  className,
}: ConfirmWindowUnderlineProps): React.JSX.Element | null {
  if (!active) {
    return null;
  }
  if (reduced) {
    return (
      <span data-slot="ce-confirm-helper" className={`ce-type-meta block ${className ?? ""}`}>
        {reducedHelper ?? confirmWindowHelper(windowMs)}
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      data-slot="ce-confirm-underline"
      className={`ce-confirm-underline ${className ?? ""}`}
      style={{ animationDuration: `${windowMs}ms` }}
    />
  );
}
