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
import { Download, LoaderCircle } from "lucide-react";
import { Link, useParams } from "react-router";

import { ExerciseRefusal, ExerciseUnreachable, isRefusal } from "../../../lib/exerciseApi";
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
import { cn } from "../../components/ui/utils";
import { Button, SkeletonRankedRows, SkeletonRegion } from "./desk";
import { ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ListCompositionTable } from "./ListCompositionTable";
import { MatchingCompareView } from "./MatchingCompareView";
import { RankedList } from "./RankedList";
import { SavedSettingsPanel } from "./SavedSettingsPanel";
import { isAccessRefusal, useExerciseResource } from "./useExerciseResource";
import { isWeightsRefusal, WeightsControls } from "./WeightsControls";
import { workspaceRequiredNotice } from "./refusals";

/** A link drawn as the desk's secondary button (DESIGN.md §6.3). */
export const LINK_SECONDARY =
  "ce-press ce-type-label inline-flex min-h-ce-control min-w-ce-target items-center justify-center gap-ce-2 rounded-ce-control border-2 border-ce-line-strong bg-ce-surface px-ce-5 text-ce-ink no-underline hover:border-ce-primary hover:bg-ce-primary-tint hover:no-underline";

/** A link drawn as the desk's primary button: one per region (§6.3). */
const LINK_PRIMARY =
  "ce-press ce-lift ce-type-label inline-flex min-h-ce-control min-w-ce-target items-center justify-center gap-ce-2 rounded-ce-control bg-ce-primary px-ce-5 text-ce-on-primary no-underline hover:bg-[color-mix(in_srgb,var(--ce-primary)_92%,black)] hover:no-underline";

interface MatchingData {
  readonly list: RankedListView;
  readonly saved: SavedSettingsView;
}

function sameWeights(
  left: Readonly<Record<string, number>>,
  right: Readonly<Record<string, number>>,
): boolean {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  return [...keys].every((key) => left[key] === right[key]);
}

/**
 * Whether the list on screen is the answer to the weighting last asked for.
 *
 * The screen owns two weightings and they are not the same thing: the one it
 * *asked* for (`weighting`) and the one the server *accepted* (the list's own
 * `weights` and `setting_name`). Between a request and its answer, and after a
 * refusal, they differ — and anything that acts on "these weights" (the
 * status line, save, the download) has to know which one it means.
 */
function listAnswersWeighting(list: RankedListView, weighting: ListWeighting): boolean {
  if (weighting.kind === "weights") {
    return sameWeights(list.weights, weighting.weights);
  }
  if (weighting.kind === "setting") {
    return list.setting_name === weighting.name;
  }
  return list.setting_name === null;
}

/**
 * Which failed list reads keep the list already on screen.
 *
 * A refused weighting, or one that could not be sent, must not take the screen
 * down with it — the list a team was already looking at is still the true
 * answer to the question it asked before that one. The hook itself never
 * keeps data past a 401 or 403 (see `useExerciseResource`'s
 * `keepDataOnError`).
 */
function keepMatchingData(error: unknown): boolean {
  return error instanceof ExerciseRefusal || error instanceof ExerciseUnreachable;
}

/** The weighting the list on screen was built from, to ask for again. */
function acceptedWeighting(list: RankedListView): ListWeighting {
  return list.setting_name === null
    ? { kind: "weights", weights: { ...list.weights } }
    : { kind: "setting", name: list.setting_name };
}

/** Why the download and save are off, pointed at by both. */
const NOT_CURRENT_REASON = "exercise-list-not-current";

export function ExerciseMatching(): React.JSX.Element {
  const { eventKey = "" } = useParams();
  // Keyed by event: the weighting, the comparison and every refusal belong to
  // one event, and none of them may carry over to the next one picked.
  return <EventMatching key={eventKey} eventKey={eventKey} />;
}

function EventMatching({ eventKey }: { readonly eventKey: string }): React.JSX.Element {
  /** What the list on screen was built from. */
  const [weighting, setWeighting] = React.useState<ListWeighting>({ kind: "default" });
  /** The side-by-side view, when a team has asked for one. */
  const [comparison, setComparison] = React.useState<CompareView | null>(null);
  const [panelRefusal, setPanelRefusal] = React.useState<string | null>(null);
  /** A save, delete or compare refused because this browser lost access. */
  const [accessRefusal, setAccessRefusal] = React.useState<ExerciseRefusal | null>(null);
  /** Whether a weight box holds text that has not been committed yet. */
  const [hasUnsent, setHasUnsent] = React.useState(false);
  /** Bumped to put every weight box back to the list's own weights. */
  const [controlsRevision, setControlsRevision] = React.useState(0);

  const load = React.useCallback(
    async (signal: AbortSignal): Promise<MatchingData> => ({
      list: await readRankedList(eventKey, weighting, signal),
      saved: await readSavedSettings(eventKey, signal),
    }),
    [eventKey, weighting],
  );
  // See `keepMatchingData`, and `useExerciseResource`'s `keepDataOnError`
  // docstring for why the other exercise screens do not opt into this.
  const { state, reload } = useExerciseResource(load, [eventKey, weighting], {
    keepDataOnError: keepMatchingData,
  });

  /** The list on screen answers the boxes: nothing typed and unsent, nothing asked and unanswered. */
  const listCurrent =
    state.status === "ready" && !hasUnsent && listAnswersWeighting(state.data.list, weighting);
  /**
   * The list on screen is settled and is the answer to the boxes. Only then
   * may it be saved or downloaded: "these weights" must mean the list's own.
   */
  const settled =
    state.status === "ready" &&
    !state.refreshing &&
    state.refusal === null &&
    state.unreachable === null &&
    listCurrent;
  /** The list is the answer to an earlier weighting than the one last asked for. */
  const stale = state.status === "ready" && (state.refusal !== null || state.unreachable !== null);

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
      if (isAccessRefusal(error)) {
        // The workspace cookie has gone or access was refused: nothing on this
        // screen is known to be readable any more, so it all goes.
        setAccessRefusal(error);
        return false;
      }
      setPanelRefusal(
        isRefusal(error)
          ? error.message
          : "The exercise could not be reached. Check the connection and try again.",
      );
      return false;
    }
  }

  /**
   * A refused weighting's sentence is shown once, under the slider
   * (`WeightsControls`, owner ruling 2026-09-27); every other refusal of the
   * list request is this screen's notice.
   */
  const listRefusal =
    state.status === "ready" &&
    state.refusal !== null &&
    !(weighting.kind === "weights" && isWeightsRefusal(state.refusal))
      ? state.refusal
      : null;

  return (
    <ExerciseScreen
      title={
        state.status === "ready" && accessRefusal === null
          ? state.data.list.event_name
          : "Your team's list"
      }
      intro="Decide how much each thing counts, then see who that puts on the list — and who it leaves off."
      aside={
        <Link to="/exercise/events" className={LINK_SECONDARY}>
          Choose a different event
        </Link>
      }
    >
      {state.status === "loading" ? (
        // §6.21: shaped like the list, with the stated-loading sentence.
        <SkeletonRegion label="Loading the list…" className="ce-card p-ce-4 md:p-ce-5">
          <SkeletonRankedRows />
        </SkeletonRegion>
      ) : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <Button variant="secondary" onClick={reload}>
            Try again
          </Button>
        </ExerciseNotice>
      ) : null}

      {accessRefusal === null ? null : workspaceRequiredNotice(accessRefusal)}

      {state.status !== "ready" || accessRefusal !== null ? null : (
        <div className="flex flex-col gap-ce-6 md:gap-ce-7">
          {panelRefusal === null && listRefusal === null ? null : (
            <div className="flex flex-col gap-ce-3">
              {panelRefusal === null ? null : <ExerciseNotice message={panelRefusal} />}
              {listRefusal === null ? null : (
                <ExerciseNotice
                  id="exercise-list-refusal"
                  message={listRefusal.message}
                  tone="problem"
                />
              )}
            </div>
          )}
          {state.unreachable === null ? null : (
            // Asked again only when the team says so: no retry loop.
            <ExerciseNotice id="exercise-list-unreachable" message={state.unreachable} tone="problem">
              <Button variant="secondary" onClick={() => void reload()}>
                Try again
              </Button>
            </ExerciseNotice>
          )}

          {/*
            §7.4: the weights sit beside the list at 1280 (sticky, 360px) and
            above it on narrower layouts.
          */}
          <div className="grid gap-ce-5 xl:grid-cols-[360px_minmax(0,1fr)] xl:items-start">
            {/*
              Mounted continuously, including while a new list is being
              fetched. It holds the text a team is typing, so unmounting it
              between keystrokes — which is what happened while a refetch
              dropped the screen to `loading` — made a decimal impossible to
              type.
            */}
            <div className="min-w-0 xl:sticky xl:top-ce-5">
              <WeightsControls
                key={controlsRevision}
                factorLabels={state.data.list.factor_labels}
                weights={state.data.list.weights}
                refusal={state.refusal}
                transportFailed={state.unreachable !== null}
                onUnsentChange={setHasUnsent}
                onChange={(weights) => {
                  setComparison(null);
                  setWeighting({ kind: "weights", weights });
                }}
              />
            </div>

            <section
              className="ce-card flex min-w-0 flex-col gap-ce-3 p-ce-4 md:p-ce-5"
              aria-describedby={
                !stale
                  ? undefined
                  : listRefusal !== null
                    ? "exercise-list-refusal"
                    : state.unreachable !== null
                      ? "exercise-list-unreachable exercise-list-stale"
                      : "exercise-list-stale"
              }
            >
              <div className="flex flex-wrap items-start justify-between gap-ce-3">
                <div className="flex flex-wrap items-center gap-ce-3">
                  <h2 className="ce-type-h2 text-ce-ink">The list</h2>
                  {state.refreshing ? (
                    <p
                      id={NOT_CURRENT_REASON}
                      role="status"
                      data-slot="exercise-list-refreshing"
                      className="ce-type-meta flex items-center gap-ce-2 text-ce-ink-muted"
                    >
                      <LoaderCircle
                        aria-hidden="true"
                        className="size-4 animate-spin text-ce-primary motion-reduce:animate-none"
                      />
                      Rebuilding the list…
                    </p>
                  ) : !stale && !listCurrent ? (
                    <p
                      id={NOT_CURRENT_REASON}
                      data-slot="exercise-list-not-current"
                      className="ce-type-meta text-ce-ink-muted"
                    >
                      This list is not built from the numbers above yet. Leave the box or press
                      Enter to rebuild it.
                    </p>
                  ) : null}
                </div>
                {settled ? (
                  // Settled means the weighting asked for is the one this list
                  // was built from, so the file is this list and no other.
                  <a
                    href={rankedListCsvHref(eventKey, weighting)}
                    download
                    className={LINK_SECONDARY}
                    data-slot="exercise-csv-download"
                  >
                    <Download aria-hidden="true" className="size-5 shrink-0" />
                    Download this list as a spreadsheet
                  </a>
                ) : (
                  <a
                    role="link"
                    aria-disabled="true"
                    tabIndex={0}
                    aria-describedby={stale ? "exercise-list-stale" : NOT_CURRENT_REASON}
                    className={cn(LINK_SECONDARY, "cursor-not-allowed opacity-45")}
                    data-slot="exercise-csv-download"
                  >
                    <Download aria-hidden="true" className="size-5 shrink-0" />
                    Download this list as a spreadsheet
                  </a>
                )}
              </div>
              {state.unreachable === null ? null : (
                <p id="exercise-list-stale" data-slot="exercise-list-stale" className="ce-type-reason text-ce-ink-muted">
                  This is the list from before that change — it could not be rebuilt, so the list
                  has not changed.
                </p>
              )}
              {state.refusal === null ? null : (
                // The list below is stale the moment a commit is refused: it is
                // still the answer to the *previous* weighting, not to the one
                // the refusal sentence above is about. `aria-describedby` on the
                // section carries that for assistive tech; this carries it for
                // sighted readers who may not read the notice above as tied to
                // the rows below it.
                <p id="exercise-list-stale" data-slot="exercise-list-stale" className="ce-type-reason text-ce-ink-muted">
                  This is the list from before that change — it was refused, so the list has not
                  changed.
                </p>
              )}
              {state.refreshing || (!stale && listCurrent) ? null : (
                <div>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setComparison(null);
                      setWeighting(acceptedWeighting(state.data.list));
                      setControlsRevision((value) => value + 1);
                    }}
                  >
                    Go back to this list's weights
                  </Button>
                </div>
              )}
              <p className="ce-type-meta text-ce-ink-muted">
                Cut at {state.data.list.invite_limit} names, the limit set for this data file.
                {state.data.list.setting_name === null
                  ? null
                  : ` Built from your team's setting “${state.data.list.setting_name}”.`}
              </p>
              {/* §5 ce-list-rebuilding: dim while a new list is fetched, or stale after a refusal. */}
              <div
                aria-busy={state.refreshing ? "true" : undefined}
                className={cn("ce-rebuildable min-w-0", stale && "opacity-60")}
              >
                <RankedList
                  entries={state.data.list.entries}
                  factorLabels={state.data.list.factor_labels}
                  caption={`The names for ${state.data.list.event_name}, in order.`}
                  firstRoundEventName={state.data.list.first_round_event_name}
                />
              </div>
            </section>
          </div>

          <ListCompositionTable
            composition={state.data.list.composition}
            unrankableProfileCount={state.data.list.unrankable_profile_count}
            unlistedClassYears={state.data.list.unlisted_class_years}
          />

          <SavedSettingsPanel
            saved={state.data.saved}
            weights={state.data.list.weights}
            factorLabels={state.data.list.factor_labels}
            saveBlockedReason={
              settled
                ? null
                : "Saving is off until the list is built from the numbers above."
            }
            onSave={(name) =>
              guard(async () => {
                await saveSetting(eventKey, name, state.data.list.weights);
                // Held until the saved list is re-read, so the panel stays busy.
                await reload();
              })
            }
            onDelete={(name) =>
              guard(async () => {
                await deleteSetting(eventKey, name);
                await reload();
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
            <MatchingCompareView comparison={comparison} onClose={() => setComparison(null)} />
          )}

          <p>
            <Link
              to={`/exercise/events/${encodeURIComponent(eventKey)}/results`}
              className={LINK_PRIMARY}
            >
              Go to results for this event
            </Link>
          </p>
        </div>
      )}
    </ExerciseScreen>
  );
}
