/**
 * For tests that answer an inline question (`useInlineConfirmGuard`).
 *
 * A press on the confirming button is ignored for `CONFIRM_GUARD_MS` after the
 * question opens, so a test that means "the instructor read it and said yes"
 * waits that long first, as a person does. Not a `*.test.tsx` file, so Vitest
 * does not collect it.
 */
import { CONFIRM_GUARD_MS } from "./desk";

/** Resolves once a press on the confirming button counts. */
export function pastTheConfirmGuard(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
}
