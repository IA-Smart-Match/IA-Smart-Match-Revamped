/**
 * "Check again" in the results lock panel, and what it found (issue #321;
 * DESIGN.md §6.14).
 *
 * A read of the lock, never the run. If results have opened, the lock panel —
 * and this with it — is gone when the read lands. If they have not, the press
 * says so under itself, with the time, instead of leaving the screen as it
 * was: "Checked at 10:43:07 AM. Results are still not open."
 *
 * **Only a read that landed may say that** (PR #346 review). The screen keeps
 * its last answer when a re-read cannot be reached, so a press made with the
 * network down used to print "Checked at … Results are still not open." about
 * a lock nobody had read. The line is written once the read has settled, from
 * whether that read landed: the checked sentence if it did, the page's
 * could-not-be-reached sentence if it did not.
 *
 * The time is this browser's clock to the second (`clockNow`), so a second
 * press in the same minute changes the line and is announced again.
 */
import * as React from "react";

import { ExerciseUnreachable } from "../../../lib/exerciseApi";
import { Button } from "./desk";
import { clockNow } from "./exerciseTime";

/** "Checked at 10:43:07 AM. Results are still not open." */
export function stillClosedSentence(at: string | null): string {
  return at === null
    ? "Checked. Results are still not open."
    : `Checked at ${at}. Results are still not open.`;
}

export interface ResultsCheckAgainProps {
  /** Another action is in flight. */
  readonly disabled: boolean;
  /** The screen's latest read could not be reached; its previous answer is still shown. */
  readonly readFailed: boolean;
  /** Re-read the screen; resolves once that read has settled, landed or not. */
  readonly onCheck: () => Promise<void>;
}

export function ResultsCheckAgain({
  disabled,
  readFailed,
  onCheck,
}: ResultsCheckAgainProps): React.JSX.Element {
  /** How many checks have settled. The line is written when this moves. */
  const [settledChecks, setSettledChecks] = React.useState(0);
  const [said, setSaid] = React.useState("");

  // Written in an effect, not in the press's own `then`: that callback still
  // holds the props from before the read. The render this runs after has the
  // settled read's `readFailed`.
  React.useEffect(() => {
    if (settledChecks > 0) {
      setSaid(readFailed ? new ExerciseUnreachable().message : stillClosedSentence(clockNow()));
    }
    // Only a settled check writes the line; `readFailed` is read, not watched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settledChecks]);

  return (
    <>
      <Button
        variant="secondary"
        disabled={disabled}
        onClick={() => {
          void onCheck().then(() => setSettledChecks((count) => count + 1));
        }}
      >
        Check again
      </Button>
      <p
        aria-live="polite"
        data-slot="exercise-results-checked"
        className="ce-type-meta text-ce-ink-muted"
      >
        {said}
      </p>
    </>
  );
}
