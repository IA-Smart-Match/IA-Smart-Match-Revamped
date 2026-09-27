/**
 * The matching screen: four weights, a ranked list, and who is on it.
 *
 * This is the screen the lesson turns on. A team sets how much each thing
 * counts, sees who that puts on the list, sees who it leaves off, saves the
 * weighting under a name, and compares two names side by side — the
 * requirements' "Matching", "Who is on the list" and "Download" rows in one
 * place, because they are one decision.
 *
 * Three things are read from the server rather than written here, each for the
 * same reason — a value written into a screen is a second source of truth:
 *
 * - **The factor labels.** Ann's four phrases arrive as `factor_labels`; the
 *   rulebook's keys are never rendered.
 * - **The settings cap.** `max_settings`, not `3`.
 * - **The invite limit.** The list is cut at the data file's limit, which the
 *   instructor sets; the screen reports it rather than assuming 30.
 *
 * Weights reach the list one of three ways and naming two is refused: a saved
 * setting's name, the four query parameters, or neither — which is what makes
 * the server's OQ-CE-02 equal defaults the defaults. This screen starts
 * with neither and switches to explicit weights the moment a team changes one.
 *
 * The CSV is an ordinary link (design spec §8's columns, served as `text/csv`
 * with its filename in `Content-Disposition`). Building the file in the
 * browser would be a second implementation of those columns, free to drift
 * from the server's.
 */
import * as React from "react";
import { Link, useParams } from "react-router";
import { ArrowRight, Download } from "lucide-react";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  compareSettings,
  deleteSetting,
  rankedListCsvHref,
  readRankedList,
  readSavedSettings,
  saveSetting,
  type CompareView as CompareData,
  type ListWeighting,
  type RankedListView,
  type SavedSettingsView,
} from "../../../lib/exerciseClient";
import { CompareView } from "./CompareView";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ceButton, Spinner, useIsNarrow } from "./exerciseUi";
import { ListCompositionTable } from "./ListCompositionTable";
import { ListCoverageNotice } from "./ListCoverageNotice.tsx";
import { RankedList } from "./RankedList";
import { SavedSettingsPanel } from "./SavedSettingsPanel";
import { useExerciseResource } from "./useExerciseResource";
import { orderedKeys, WeightsControls } from "./WeightsControls";
import { workspaceRequiredNotice } from "./refusals";

interface MatchingData {
  readonly list: RankedListView;
  readonly saved: SavedSettingsView;
}

export function ExerciseMatching(): React.JSX.Element {
  const { eventKey = "" } = useParams();

  /** What the list on screen was built from. */
  const [weighting, setWeighting] = React.useState<ListWeighting>({ kind: "default" });
  /** The side-by-side view, when a team has asked for one. */
  const [comparison, setComparison] = React.useState<CompareData | null>(null);
  const [panelRefusal, setPanelRefusal] = React.useState<string | null>(null);

  const load = React.useCallback(
    async (signal: AbortSignal): Promise<MatchingData> => ({
      list: await readRankedList(eventKey, weighting, signal),
      saved: await readSavedSettings(eventKey, signal),
    }),
    [eventKey, weighting],
  );
  // A refused weighting must not take the screen down with it — the list a
  // team was already looking at is still the true answer to the question it
  // asked before the one that was refused. See `useExerciseResource`'s
  // `keepDataOnRefusal` docstring for why the other exercise screens do not
  // opt into this.
  const { state, reload } = useExerciseResource(load, [eventKey, weighting], {
    keepDataOnRefusal: true,
  });

  /**
   * Run one action; show any refusal, and say whether it worked.
   *
   * The boolean matters. This used to swallow the refusal and resolve, which
   * from the saved-settings panel's side was indistinguishable from success —
   * so a refused save still cleared the name box. The one error slot on this
   * screen is `panelRefusal`; the outcome goes back to the caller.
   */
  async function guard(action: () => Promise<void>): Promise<boolean> {
    setPanelRefusal(null);
    try {
      await action();
      return true;
    } catch (error) {
      setPanelRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
      return false;
    }
  }

  /** The weights card, so the phone's compact bar can scroll back to it. */
  const weightsRef = React.useRef<HTMLDivElement>(null);

  return (
    <ExerciseScreen
      title={state.status === "ready" ? state.data.list.event_name : "Your team's list"}
      intro="Decide how much each thing counts, then see who that puts on the list — and who it leaves off."
      aside={
        <Link to="/exercise/events" className={ceButton("secondary")}>
          Choose a different event
          <ArrowRight aria-hidden="true" className="size-5" />
        </Link>
      }
    >
      {state.status === "loading" ? <ExerciseLoading what="the list" shape="list" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={ceButton("primary")}>
            Try again
          </button>
        </ExerciseNotice>
      ) : null}

      {state.status !== "ready" ? null : (
        <div className="flex flex-col gap-8 md:gap-12">
          {panelRefusal === null ? null : <ExerciseNotice message={panelRefusal} />}
          {state.refusal === null ? null : (
            <ExerciseNotice
              id="exercise-list-refusal"
              message={state.refusal.message}
              tone="problem"
            />
          )}

          <CompactWeightsBar
            target={weightsRef}
            factorLabels={state.data.list.factor_labels}
            weights={state.data.list.weights}
          />

          {/* §7.4: the weights card (360px, sticky) beside the list on desktop. */}
          <div className="grid items-start gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
            <div ref={weightsRef} className="lg:sticky lg:top-6">
              {/*
                Mounted continuously, including while a new list is being
                fetched. It holds the text a team is typing, so unmounting it
                between keystrokes — which is what happened while a refetch
                dropped the screen to `loading` — made a decimal impossible to
                type.
              */}
              <WeightsControls
                factorLabels={state.data.list.factor_labels}
                weights={state.data.list.weights}
                refusal={state.refusal}
                rebuilding={state.refreshing}
                onChange={(weights) => {
                  setComparison(null);
                  setWeighting({ kind: "weights", weights });
                }}
              />
            </div>

            <section
              className="ce-card flex min-w-0 flex-col gap-4 p-4 md:p-6"
              aria-describedby={state.refusal === null ? undefined : "exercise-list-refusal"}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="ce-h2 text-ce-ink">The list</h2>
                    {/* `ce-list-rebuilding`: announced once, politely. */}
                    <p
                      aria-live="polite"
                      role="status"
                      className="ce-meta flex items-center gap-2 text-ce-muted"
                    >
                      {state.refreshing ? (
                        <span data-slot="exercise-list-refreshing" className="flex items-center gap-2">
                          <Spinner className="text-ce-primary" />
                          Rebuilding the list…
                        </span>
                      ) : null}
                    </p>
                  </div>
                  <p className="ce-meta text-ce-muted">
                    Cut at {state.data.list.invite_limit} names, the limit set for this data file.
                    {state.data.list.setting_name === null
                      ? null
                      : ` Built from your team's setting “${state.data.list.setting_name}”.`}
                  </p>
                </div>
                <a
                  href={rankedListCsvHref(eventKey, weighting)}
                  download
                  className={ceButton("secondary", "w-full sm:w-auto")}
                  data-slot="exercise-csv-download"
                >
                  <Download aria-hidden="true" className="size-5" />
                  Download this list as a spreadsheet
                </a>
              </div>

              <ListCoverageNotice
                missingMajors={state.data.list.composition.coverage.missing_majors}
                missingClassYears={state.data.list.composition.coverage.missing_class_years}
              />

              {state.refusal === null ? null : (
                // The list below is stale the moment a commit is refused: it
                // is still the answer to the *previous* weighting, not to the
                // one the refusal sentence above is about. `aria-describedby`
                // on the section carries that for assistive tech; this carries
                // it for sighted readers who may not read the notice above as
                // tied to the rows below it.
                <p data-slot="exercise-list-stale" className="ce-reason text-ce-muted italic">
                  This is the list from before that change — it was refused, so the list has not
                  changed.
                </p>
              )}
              <div
                className={
                  state.refreshing || state.refusal !== null ? "ce-rebuilding" : "ce-settled"
                }
              >
                <RankedList
                  entries={state.data.list.entries}
                  factorLabels={state.data.list.factor_labels}
                  caption={`The names for ${state.data.list.event_name}, in order.`}
                />
              </div>
            </section>
          </div>

          <ListCompositionTable
            composition={state.data.list.composition}
            unrankableProfileCount={state.data.list.unrankable_profile_count}
            unlistedClassYears={state.data.list.unlisted_class_years}
            showCoverageNotice={false}
          />

          <SavedSettingsPanel
            saved={state.data.saved}
            weights={state.data.list.weights}
            factorLabels={state.data.list.factor_labels}
            onSave={(name) =>
              guard(async () => {
                await saveSetting(eventKey, name, state.data.list.weights);
                reload();
              })
            }
            onDelete={(name) =>
              guard(async () => {
                await deleteSetting(eventKey, name);
                reload();
              })
            }
            onOpen={(name) => {
              setComparison(null);
              setWeighting({ kind: "setting", name });
            }}
            onCompare={(a, b) => {
              void guard(async () => {
                setComparison(await compareSettings(eventKey, a, b));
              });
            }}
          />

          {comparison === null ? null : (
            <CompareView comparison={comparison} onClose={() => setComparison(null)} />
          )}

          <p>
            <Link
              to={`/exercise/events/${encodeURIComponent(eventKey)}/results`}
              className={ceButton("primary", "ce-btn-lg w-full sm:w-auto")}
            >
              Go to results for this event
              <ArrowRight aria-hidden="true" className="size-5" />
            </Link>
          </p>
        </div>
      )}
    </ExerciseScreen>
  );
}

/**
 * The phone's compact weights bar (DESIGN.md §7.4, §11.1).
 *
 * When the weights card scrolls out of view on a phone, a slim bar pins to
 * the top with the four confirmed numbers and "Edit weights", which scrolls
 * back to the card and puts focus in its first box. Nothing here edits a
 * weight; the card does.
 */
function CompactWeightsBar({
  target,
  factorLabels,
  weights,
}: {
  readonly target: React.RefObject<HTMLDivElement | null>;
  readonly factorLabels: Readonly<Record<string, string>>;
  readonly weights: Readonly<Record<string, number>>;
}): React.JSX.Element | null {
  const narrow = useIsNarrow();
  const [outOfView, setOutOfView] = React.useState(false);

  React.useEffect(() => {
    const element = target.current;
    if (!narrow || element === null || typeof IntersectionObserver === "undefined") {
      setOutOfView(false);
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => {
      setOutOfView(entry !== undefined && !entry.isIntersecting && entry.boundingClientRect.top < 0);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [narrow, target]);

  if (!narrow || !outOfView) {
    return null;
  }
  const numbers = orderedKeys(factorLabels)
    .map((key) => (weights[key] ?? 0).toFixed(2))
    .join(" · ");
  return (
    <div
      data-slot="exercise-weights-bar"
      className="ce-fade-rise fixed inset-x-0 top-0 z-20 flex items-center justify-between gap-3 bg-ce-surface px-4 py-2 shadow-[var(--ce-elev-3)]"
    >
      <span className="ce-meta ce-num text-ce-ink">Weights {numbers}</span>
      <button
        type="button"
        className={ceButton("quiet", "min-h-11")}
        onClick={() => {
          target.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          target.current?.querySelector<HTMLInputElement>('input[type="text"]')?.focus({
            preventScroll: true,
          });
        }}
      >
        Edit weights
      </button>
    </div>
  );
}
