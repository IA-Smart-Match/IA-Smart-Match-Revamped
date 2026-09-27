/**
 * The matching screen's side-by-side view (moved out of `ExerciseMatching.tsx`
 * as `ComparisonView`, unchanged in behaviour).
 */
import * as React from "react";

import type { CompareView } from "../../../lib/exerciseClient";
import { Button } from "./desk";
import { RankedList } from "./RankedList";

/**
 * Two saved settings' lists, with the names on both highlighted.
 *
 * `on_both_profile_nos` comes back in the first list's order, so the same set
 * marks both tables and the highlight means one thing: this person is on the
 * list either way, so the weighting did not decide them.
 */
export function MatchingCompareView({
  comparison,
  onClose,
}: {
  readonly comparison: CompareView;
  readonly onClose: () => void;
}): React.JSX.Element {
  const overlap = comparison.on_both_profile_nos;
  return (
    <section data-slot="exercise-compare" className="flex flex-col gap-ce-4">
      <div className="flex flex-wrap items-baseline justify-between gap-ce-3">
        <h2 className="ce-type-h2 text-ce-ink">Two settings, side by side</h2>
        <Button variant="secondary" onClick={onClose}>
          Close this comparison
        </Button>
      </div>
      <p className="ce-type-body text-ce-ink">
        {overlap.length === 0
          ? "Nobody is on both lists."
          : `${overlap.length} ${
              overlap.length === 1 ? "name is" : "names are"
            } on both lists, highlighted in each.`}
      </p>
      <div data-slot="exercise-compare-grid" className="grid gap-ce-6">
        {[comparison.a, comparison.b].map((list, index) => (
          <div key={index === 0 ? "a" : "b"} className="min-w-0">
            <RankedList
              entries={list.entries}
              factorLabels={list.factor_labels}
              highlightProfileNos={overlap}
              caption={list.setting_name ?? "This list"}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
