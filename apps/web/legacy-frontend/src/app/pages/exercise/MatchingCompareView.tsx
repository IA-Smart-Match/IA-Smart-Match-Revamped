/**
 * The compare view (DESIGN.md §6.12, §7.5): two saved settings' lists, with
 * the names on both highlighted. Moved out of `ExerciseMatching.tsx`, where it
 * was `ComparisonView`; the data and the words are unchanged.
 *
 * `on_both_profile_nos` comes back in the first list's order, so the same set
 * marks both lists and the highlight means one thing: this person is on the
 * list either way, so the weighting did not decide them. Each overlap row has
 * the gold wash and an "on both lists" chip, and pulses once on opening
 * (`ce-overlap-pulse`).
 *
 * - **768 and up:** two real tables (§8.7, owner ruling 2026-09-27), each
 *   a card with the setting's name and its four weights. They stack rather
 *   than sit side by side (§6.12): two five-column tables do not fit half of
 *   the 1152px page with major, year and marker all visible, so each gets the
 *   full width and its own scroll box.
 * - **Below 768:** a segmented control, one tab per setting, with the
 *   summary sentence above it; each list is cards, 10 rows first and
 *   "Showing 10 of 30. Show all 30" (§11.1).
 */
import * as React from "react";
import { X } from "lucide-react";

import type { CompareView, RankedListView } from "../../../lib/exerciseClient";
import { cn } from "../../components/ui/utils";
import { Button, formatWeight } from "./desk";
import { RankedList } from "./RankedList";
import { useNarrowViewport } from "./useNarrowViewport";
import { orderedFactorKeys } from "./WeightsControls";

/** Rows shown first on 390 before "Show all". */
const PHONE_ROWS = 10;

function settingName(list: RankedListView): string {
  return list.setting_name ?? "This list";
}

export function MatchingCompareView({
  comparison,
  onClose,
}: {
  readonly comparison: CompareView;
  readonly onClose: () => void;
}): React.JSX.Element {
  const narrow = useNarrowViewport();
  const overlap = comparison.on_both_profile_nos;
  const lists = [comparison.a, comparison.b] as const;

  return (
    <section data-slot="exercise-compare" className="flex flex-col gap-ce-4">
      <div className="flex flex-wrap items-baseline justify-between gap-ce-3">
        <h2 className="ce-type-h2 text-ce-ink">Two settings, side by side</h2>
        <Button variant="quiet" leadingIcon={<X />} onClick={onClose} className="underline">
          Close this comparison
        </Button>
      </div>
      <p
        className={cn(
          "ce-type-body text-ce-ink",
          // §7.5: pinned above the segmented control on 390.
          narrow && "sticky top-16 z-10 bg-ce-page py-ce-2",
        )}
      >
        {overlap.length === 0
          ? "Nobody is on both lists."
          : `${overlap.length} ${
              overlap.length === 1 ? "name is" : "names are"
            } on both lists, highlighted in each.`}
      </p>
      {narrow ? (
        <CompareTabs lists={lists} overlap={overlap} />
      ) : (
        <div data-slot="exercise-compare-grid" className="grid gap-ce-5">
          {lists.map((list, index) => (
            <div key={index === 0 ? "a" : "b"} className="ce-card min-w-0 p-ce-4 md:p-ce-5">
              <CompareListHeading list={list} />
              <RankedList
                entries={list.entries}
                factorLabels={list.factor_labels}
                highlightProfileNos={overlap}
                caption={settingName(list)}
                firstRoundEventName={list.first_round_event_name}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/** The setting's name and the four numbers it was built from. */
function CompareListHeading({ list }: { readonly list: RankedListView }): React.JSX.Element {
  const values = orderedFactorKeys(list.factor_labels)
    .filter((key) => key in list.weights)
    .map((key) => formatWeight(list.weights[key] ?? 0));
  return (
    <div className="flex flex-col gap-ce-1 border-b border-ce-line pb-ce-3">
      <h3 className="ce-type-h3 text-ce-ink">{settingName(list)}</h3>
      {values.length === 0 ? null : (
        <p className="ce-type-meta ce-tabular text-ce-ink-muted">{values.join(" · ")}</p>
      )}
    </div>
  );
}

/** §7.5 on 390: "Setting A | Setting B" as tabs, one list at a time. */
function CompareTabs({
  lists,
  overlap,
}: {
  readonly lists: readonly [RankedListView, RankedListView];
  readonly overlap: readonly number[];
}): React.JSX.Element {
  const [shown, setShown] = React.useState<0 | 1>(0);
  const [showAll, setShowAll] = React.useState(false);
  const tabs = [React.useRef<HTMLButtonElement>(null), React.useRef<HTMLButtonElement>(null)];
  const list = lists[shown];
  const entries = showAll ? list.entries : list.entries.slice(0, PHONE_ROWS);

  function select(next: 0 | 1): void {
    setShown(next);
    setShowAll(false);
    tabs[next].current?.focus();
  }

  return (
    <div data-slot="exercise-compare-grid" className="flex min-w-0 flex-col gap-ce-3">
      <div
        role="tablist"
        className="grid grid-cols-2 gap-ce-1 rounded-ce-control bg-ce-surface-sunk p-ce-1"
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            select(shown === 0 ? 1 : 0);
          }
        }}
      >
        {lists.map((each, index) => {
          const selected = index === shown;
          return (
            <button
              key={index === 0 ? "a" : "b"}
              ref={tabs[index]}
              type="button"
              role="tab"
              id={`exercise-compare-tab-${index}`}
              aria-selected={selected}
              aria-controls="exercise-compare-panel"
              tabIndex={selected ? 0 : -1}
              onClick={() => select(index === 0 ? 0 : 1)}
              className={cn(
                "ce-type-label min-h-ce-target min-w-0 truncate rounded-ce-control px-ce-3",
                selected ? "bg-ce-surface text-ce-ink shadow-ce-1" : "text-ce-ink-muted",
              )}
            >
              {settingName(each)}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id="exercise-compare-panel"
        aria-labelledby={`exercise-compare-tab-${shown}`}
        className="ce-card min-w-0 p-ce-4"
      >
        <CompareListHeading list={list} />
        <RankedList
          key={`${shown}-${showAll}`}
          entries={entries}
          factorLabels={list.factor_labels}
          highlightProfileNos={overlap}
          caption={settingName(list)}
          layout="cards"
          firstRoundEventName={list.first_round_event_name}
        />
        {showAll || list.entries.length <= PHONE_ROWS ? null : (
          <p className="ce-type-meta pt-ce-3 text-center text-ce-ink-muted">
            Showing {PHONE_ROWS} of {list.entries.length}.{" "}
            <Button variant="quiet" className="underline" onClick={() => setShowAll(true)}>
              Show all {list.entries.length}
            </Button>
          </p>
        )}
      </div>
    </div>
  );
}
