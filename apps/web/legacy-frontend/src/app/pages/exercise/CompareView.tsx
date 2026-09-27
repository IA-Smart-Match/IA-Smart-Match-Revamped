/**
 * Two saved settings' lists, with the names on both highlighted.
 *
 * `on_both_profile_nos` comes back in the first list's order, so the same set
 * marks both tables and the highlight means one thing: this person is on the
 * list either way, so the weighting did not decide them.
 *
 * DESIGN.md §6.12 and §7.5: side by side on desktop; on a phone a segmented
 * control "Setting A | Setting B" with the summary sentence pinned above, and
 * each list showing its first 10 rows with "Showing 10 of 30. Show all 30".
 * Overlap rows carry the full gold wash and the "on both lists" chip, never a
 * left stripe, and pulse once as the comparison opens (`ce-overlap-pulse`).
 */
import * as React from "react";
import { X } from "lucide-react";

import type { CompareView as CompareData, RankedListView } from "../../../lib/exerciseClient";
import { ceButton, useIsNarrow } from "./exerciseUi";
import { RankedList } from "./RankedList";
import { orderedKeys } from "./WeightsControls";

/** Rows each list shows on a phone before "Show all" (§6.12). */
const PHONE_ROWS = 10;

export function CompareView({
  comparison,
  onClose,
}: {
  readonly comparison: CompareData;
  readonly onClose: () => void;
}): React.JSX.Element {
  const narrow = useIsNarrow();
  const overlap = comparison.on_both_profile_nos;
  const lists = [comparison.a, comparison.b] as const;
  const [shown, setShown] = React.useState<0 | 1>(0);
  const tabIds = ["exercise-compare-tab-a", "exercise-compare-tab-b"] as const;

  const summary = (
    <p className="ce-body text-ce-ink" data-slot="exercise-compare-summary">
      {overlap.length === 0
        ? "Nobody is on both lists."
        : `${overlap.length} ${
            overlap.length === 1 ? "name is" : "names are"
          } on both lists, highlighted in each.`}
    </p>
  );

  return (
    <section data-slot="exercise-compare" className="ce-fade-rise flex flex-col gap-4">
      <hr className="border-0 border-t border-ce-line" />
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="ce-h2 text-ce-ink">Two settings, side by side</h2>
        <button type="button" onClick={onClose} className={ceButton("quiet")}>
          <X aria-hidden="true" className="size-5" />
          Close this comparison
        </button>
      </div>

      {narrow ? (
        <>
          <div className="sticky top-0 z-10 flex flex-col gap-3 bg-ce-page py-2">
            {summary}
            <div
              role="tablist"
              aria-label="Two settings, side by side"
              className="grid grid-cols-2 gap-1 rounded-[10px] bg-ce-sunk p-1"
            >
              {lists.map((list, index) => (
                <button
                  key={tabIds[index]}
                  id={tabIds[index]}
                  type="button"
                  role="tab"
                  aria-selected={shown === index}
                  aria-controls={`${tabIds[index]}-panel`}
                  onClick={() => setShown(index === 0 ? 0 : 1)}
                  className={`ce-btn min-h-11 border-0 px-3 ${
                    shown === index
                      ? "bg-ce-primary text-ce-on-primary"
                      : "bg-transparent text-ce-ink"
                  }`}
                >
                  {list.setting_name ?? "This list"}
                </button>
              ))}
            </div>
          </div>
          <div data-slot="exercise-compare-grid" className="grid gap-6">
            <div
              id={`${tabIds[shown]}-panel`}
              role="tabpanel"
              aria-labelledby={tabIds[shown]}
              className="min-w-0"
            >
              <CompareColumn key={shown} list={lists[shown]} overlap={overlap} limit={PHONE_ROWS} />
            </div>
          </div>
        </>
      ) : (
        <>
          {summary}
          {/*
            Side by side from the 1024 layout up (§6.12); stacked below it.
            `min-w-0` lets a grid child shrink below its table's width, so a
            table scrolls in its own box rather than widening the page.
          */}
          <div data-slot="exercise-compare-grid" className="grid gap-6 lg:grid-cols-2">
            {lists.map((list, index) => (
              <div key={index === 0 ? "a" : "b"} className="min-w-0">
                <CompareColumn list={list} overlap={overlap} limit={null} />
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function CompareColumn({
  list,
  overlap,
  limit,
}: {
  readonly list: RankedListView;
  readonly overlap: readonly number[];
  /** Rows to show before "Show all"; `null` for all of them. */
  readonly limit: number | null;
}): React.JSX.Element {
  const [all, setAll] = React.useState(false);
  const keys = orderedKeys(list.factor_labels);
  const entries =
    limit === null || all || list.entries.length <= limit
      ? list.entries
      : list.entries.slice(0, limit);
  const title = list.setting_name ?? "This list";
  return (
    <div className="ce-card flex flex-col gap-3 p-4 md:p-6">
      <div>
        <h3 className="ce-h3 text-ce-ink">{title}</h3>
        <p className="ce-meta ce-num text-ce-muted">
          {keys.map((key) => (list.weights[key] ?? 0).toFixed(2)).join(" · ")}
        </p>
      </div>
      <RankedList
        entries={entries}
        factorLabels={list.factor_labels}
        highlightProfileNos={overlap}
        caption={title}
        variant="compact"
        pulseOverlap
      />
      {entries.length < list.entries.length ? (
        <p className="ce-meta text-center text-ce-muted">
          Showing {entries.length} of {list.entries.length}.{" "}
          <button type="button" className={ceButton("quiet", "ce-link min-h-11")} onClick={() => setAll(true)}>
            Show all {list.entries.length}
          </button>
        </p>
      ) : null}
    </div>
  );
}
