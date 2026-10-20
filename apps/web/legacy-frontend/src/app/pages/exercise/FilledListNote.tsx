import * as React from "react";

import type { ListEntryView } from "../../../lib/exerciseClient";

/**
 * Dr. Wang: when fewer students match than the list holds, say the rest were
 * added to fill it. A row "matched nothing" when no factor contributed
 * (`contributing_factor_keys` is empty; the server lists a factor only when
 * its value is known and above zero).
 */
export function FilledListNote({
  entries,
}: {
  readonly entries: readonly ListEntryView[];
}): React.JSX.Element | null {
  const filler = entries.filter((entry) => entry.contributing_factor_keys.length === 0).length;
  if (filler === 0) {
    return null;
  }
  return (
    <p data-slot="exercise-filled-list-note" className="ce-type-body text-ce-ink">
      {entries.length - filler} of your list matched what you asked for. The other {filler} were
      added to fill the list.
    </p>
  );
}
