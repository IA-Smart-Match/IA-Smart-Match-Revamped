/**
 * Keeps an inline question from being answered by the press that opened it
 * (PR #346 review; issue #321).
 *
 * The instructor's class-wide questions ("Refresh every team…", "Open results
 * for …?") appear in the page and move focus to their own confirming button,
 * so focus is never dropped (DESIGN.md §8.5). That put the "yes" under a key
 * that was still down: a held Enter repeats on whatever has focus, and a
 * double-click's second click lands where the first one put the button. Either
 * sent the request before the sentence could be read.
 *
 * Two guards, both needed. A repeated Enter or Space on the confirming button
 * is ignored however long the key is held — the repeat starts after the OS
 * delay, which is longer than any window worth waiting. And any press inside
 * `CONFIRM_GUARD_MS` of the question opening is ignored, which is the
 * double-click. It is the same number the two-press buttons use
 * (`useConfirmWindow`), so there is one guard length on the desk.
 */
import * as React from "react";

import { CONFIRM_GUARD_MS } from "./desk";

export interface InlineConfirmGuard {
  /** True while a press on the confirming button must be ignored. */
  readonly tooSoon: () => boolean;
  /** For the confirming button: a held Enter or Space does nothing. */
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
}

/** `open` is whether the question is on screen. */
export function useInlineConfirmGuard(open: boolean): InlineConfirmGuard {
  const openedAt = React.useRef<number | null>(null);
  // A layout effect, so the time is set in the same commit that shows the
  // question and before any later event can reach its button.
  React.useLayoutEffect(() => {
    openedAt.current = open ? Date.now() : null;
  }, [open]);

  const tooSoon = React.useCallback(
    (): boolean =>
      openedAt.current === null || Date.now() - openedAt.current < CONFIRM_GUARD_MS,
    [],
  );
  const onKeyDown = React.useCallback((event: React.KeyboardEvent): void => {
    if (event.repeat && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
    }
  }, []);

  return { tooSoon, onKeyDown };
}
