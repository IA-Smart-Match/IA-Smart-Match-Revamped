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
 * the server's OQ-CE-02 placeholder defaults the defaults. This screen starts
 * with neither and switches to explicit weights the moment a team changes one.
 *
 * The CSV is an ordinary link (design spec §8's columns, served as `text/csv`
 * with its filename in `Content-Disposition`). Building the file in the
 * browser would be a second implementation of those columns, free to drift
 * from the server's.
 */
import * as React from "react";
import { Link, useParams } from "react-router";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  compareSettings,
  deleteSetting,
  rankedListCsvHref,
  readRankedList,
  readSavedSettings,
  saveSetting,
  type CompareView,
  type ListWeighting,
  type RankedListView,
  type SavedSettingsView,
} from "../../../lib/exerciseClient";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ListCompositionTable } from "./ListCompositionTable";
import { RankedList } from "./RankedList";
import { SavedSettingsPanel } from "./SavedSettingsPanel";
import { useExerciseResource } from "./useExerciseResource";
import { WeightsControls } from "./WeightsControls";
import { workspaceRequiredNotice } from "./refusals";

const BUTTON =
  "inline-block rounded-lg border-2 border-slate-400 px-5 py-2 text-xl font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:text-slate-100 dark:hover:bg-slate-800";

interface MatchingData {
  readonly list: RankedListView;
  readonly saved: SavedSettingsView;
}

export function ExerciseMatching(): React.JSX.Element {
  const { eventKey = "" } = useParams();

  /** What the list on screen was built from. */
  const [weighting, setWeighting] = React.useState<ListWeighting>({ kind: "default" });
  /** The side-by-side view, when a team has asked for one. */
  const [comparison, setComparison] = React.useState<CompareView | null>(null);
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

  return (
    <ExerciseScreen
      title={state.status === "ready" ? state.data.list.event_name : "Your team's list"}
      intro="Decide how much each thing counts, then see who that puts on the list — and who it leaves off."
      aside={
        <Link to="/exercise/events" className={BUTTON}>
          Choose a different event
        </Link>
      }
    >
      {state.status === "loading" ? <ExerciseLoading what="the list" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={BUTTON}>
            Try again
          </button>
        </ExerciseNotice>
      ) : null}

      {state.status !== "ready" ? null : (
        <div className="flex flex-col gap-8">
          {panelRefusal === null ? null : <ExerciseNotice message={panelRefusal} />}
          {state.refusal === null ? null : (
            <ExerciseNotice message={state.refusal.message} tone="problem" />
          )}

          {/*
            Mounted continuously, including while a new list is being fetched.
            It holds the text a team is typing, so unmounting it between
            keystrokes — which is what happened while a refetch dropped the
            screen to `loading` — made a decimal impossible to type.
          */}
          <WeightsControls
            factorLabels={state.data.list.factor_labels}
            weights={state.data.list.weights}
            refusal={state.refusal}
            onChange={(weights) => {
              setComparison(null);
              setWeighting({ kind: "weights", weights });
            }}
          />

          <section className="flex flex-col gap-3">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
                The list
              </h2>
              {state.refreshing ? (
                <p
                  role="status"
                  data-slot="exercise-list-refreshing"
                  className="text-xl text-slate-600 dark:text-slate-300"
                >
                  Rebuilding the list…
                </p>
              ) : null}
              <a
                href={rankedListCsvHref(eventKey, weighting)}
                download
                className={BUTTON}
                data-slot="exercise-csv-download"
              >
                Download this list as a spreadsheet
              </a>
            </div>
            <p className="text-xl text-slate-600 dark:text-slate-300">
              Cut at {state.data.list.invite_limit} names, the limit set for this data file.
              {state.data.list.setting_name === null
                ? null
                : ` Built from your team's setting “${state.data.list.setting_name}”.`}
            </p>
            <RankedList
              entries={state.data.list.entries}
              factorLabels={state.data.list.factor_labels}
              caption={`The names for ${state.data.list.event_name}, in order.`}
            />
          </section>

          <ListCompositionTable
            composition={state.data.list.composition}
            unrankableProfileCount={state.data.list.unrankable_profile_count}
            unlistedClassYears={state.data.list.unlisted_class_years}
          />

          <SavedSettingsPanel
            saved={state.data.saved}
            weights={state.data.list.weights}
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
            <ComparisonView comparison={comparison} onClose={() => setComparison(null)} />
          )}

          <p className="text-xl">
            <Link to={`/exercise/events/${encodeURIComponent(eventKey)}/results`} className={BUTTON}>
              Go to results for this event
            </Link>
          </p>
        </div>
      )}
    </ExerciseScreen>
  );
}

/**
 * Two saved settings' lists, with the names on both highlighted.
 *
 * `on_both_profile_nos` comes back in the first list's order, so the same set
 * marks both tables and the highlight means one thing: this person is on the
 * list either way, so the weighting did not decide them.
 */
function ComparisonView({
  comparison,
  onClose,
}: {
  readonly comparison: CompareView;
  readonly onClose: () => void;
}): React.JSX.Element {
  const overlap = comparison.on_both_profile_nos;
  return (
    <section data-slot="exercise-compare" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
          Two settings, side by side
        </h2>
        <button type="button" onClick={onClose} className={BUTTON}>
          Close this comparison
        </button>
      </div>
      <p className="text-xl text-slate-700 dark:text-slate-200">
        {overlap.length === 0
          ? "Nobody is on both lists."
          : `${overlap.length} ${
              overlap.length === 1 ? "name is" : "names are"
            } on both lists, highlighted in each.`}
      </p>
      <div className="grid gap-8 lg:grid-cols-2">
        {[comparison.a, comparison.b].map((list, index) => (
          <RankedList
            key={index === 0 ? "a" : "b"}
            entries={list.entries}
            factorLabels={list.factor_labels}
            highlightProfileNos={overlap}
            caption={list.setting_name ?? "This list"}
          />
        ))}
      </div>
    </section>
  );
}
