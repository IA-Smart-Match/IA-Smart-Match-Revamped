/**
 * The results screen: what your team's list actually did.
 *
 * **A refusal here is a state, not an error.** The results rule runs on the
 * coefficients Chau approved (wave-2 decision D7), so a run normally succeeds.
 * `POST …/events/{event_key}/results` answers 409
 * `exercise_results_rule_not_confirmed` only if that coefficient set is ever
 * removed. It renders as a calm state carrying the server's own sentence, not
 * as an error toast, and the same is true of the other two states a team meets
 * here:
 *
 * - `exercise_results_locked` — the instructor has not opened this event yet.
 * - `exercise_results_already_run` — design spec §9's one run per team per
 *   event, and its sentence is the spec's own.
 *
 * Each is one plain sentence written for a projector, shown as-is. A screen
 * that re-worded them, or that hid the button and implied the capability did
 * not exist, would be answering for the server.
 *
 * `exercise_results_not_run` (404) on the read is not a refusal to display at
 * all — it simply means this team has not run yet, which is the screen's
 * ordinary first state.
 *
 * **The team runs its final setting, and nothing else** (Ann to Chau, Discord,
 * 2026-09-24): set weights, save up to three settings and compare two, choose
 * one final setting, then run once the instructor unlocks the event. So the run
 * button stays off until one of this event's saved settings is chosen, and a
 * team with none saved is told to save one first. The server refuses a run
 * without a final setting too; this screen only makes the step visible.
 *
 * Names for the team's own panels are joined from the ranked list by
 * `profile_no` (owner decision, 2026-09-21): the results routes carry numbers
 * and counts, and nothing here asks the backend for names. The list asked is
 * the one the run's final setting built, so the names match who was invited.
 */
import * as React from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, Lock, RotateCcw } from "lucide-react";

import { isRefusal } from "../../../lib/exerciseApi";
import {
  readAskingChoice,
  readRankedList,
  readResults,
  readSavedSettings,
  refreshProfiles,
  runResults,
  type AskingStateView,
  type ListWeighting,
  type ResultsView,
  type SavedSettingsView,
  type SavedSettingView,
} from "../../../lib/exerciseClient";
import { EnvelopeArt, ProfileCardArt } from "./exerciseArt";
import { ExerciseLoading, ExerciseNotice, ExerciseScreen } from "./ExerciseScreen";
import { ceButton, Chip, Spinner } from "./exerciseUi";
import { ResultPanels, type NamesByProfileNo } from "./ResultPanels";
import { useExerciseResource } from "./useExerciseResource";
import { orderedKeys } from "./WeightsControls";
import { workspaceRequiredNotice } from "./refusals";

/** The read's 404, which means "not run yet" rather than "something is wrong". */
const NOT_RUN = "exercise_results_not_run";

/** The run's 404 for a final setting this team no longer has (deleted in another tab). */
const SETTING_UNKNOWN = "exercise_setting_unknown";

/** The run's 409 while the instructor has not opened this event. */
const LOCKED = "exercise_results_locked";

/** Says why the run button is off; the button points at it with `aria-describedby`. */
const FINAL_SETTING_HINT = "exercise-final-setting-hint";

interface ResultsData {
  /** `null` until this team has run results for this event. */
  readonly results: ResultsView | null;
  readonly names: NamesByProfileNo;
  /** Ann's words per factor key, to label a saved setting's weights; empty when unknown. */
  readonly factorLabels: Readonly<Record<string, string>>;
  readonly asking: AskingStateView;
  /** This event's saved settings, to choose the final one from; `null` once run. */
  readonly saved: SavedSettingsView | null;
}

export function ExerciseResults(): React.JSX.Element {
  const { eventKey = "" } = useParams();

  const load = React.useCallback(
    async (signal: AbortSignal): Promise<ResultsData> => {
      let results: ResultsView | null = null;
      try {
        results = await readResults(eventKey, signal);
      } catch (error) {
        if (!(isRefusal(error) && error.code === NOT_RUN)) {
          throw error;
        }
      }
      // Independent reads, so they go together. The saved settings are only
      // needed before the run: afterwards there is nothing left to choose.
      const [fromList, asking, saved] = await Promise.all([
        namesForEvent(eventKey, results?.setting_name ?? null, signal),
        readAskingChoice(signal),
        results === null ? readSavedSettings(eventKey, signal) : Promise.resolve(null),
      ]);
      return { results, names: fromList.names, factorLabels: fromList.factorLabels, asking, saved };
    },
    [eventKey],
  );
  const { state, reload } = useExerciseResource(load, [eventKey]);

  return (
    <ExerciseScreen
      title="Results"
      intro="What your team's list did, next to what emailing all 300 would have done."
      aside={
        <Link to={`/exercise/events/${encodeURIComponent(eventKey)}`} className={ceButton("secondary")}>
          <ArrowLeft aria-hidden="true" className="size-5" />
          Back to your team's list
        </Link>
      }
    >
      {state.status === "loading" ? <ExerciseLoading what="your team's results" /> : null}
      {state.status === "refused" ? workspaceRequiredNotice(state.refusal) : null}
      {state.status === "unreachable" ? (
        <ExerciseNotice message={state.message} tone="problem">
          <button type="button" onClick={reload} className={ceButton("primary")}>
            Try again
          </button>
        </ExerciseNotice>
      ) : null}
      {state.status === "ready" ? (
        <ResultsBody eventKey={eventKey} data={state.data} onChanged={reload} />
      ) : null}
    </ExerciseScreen>
  );
}

/**
 * The names the ranked list gives this event's profile numbers, and Ann's
 * words for the four factors from the same response.
 *
 * Asked of the list the run's final setting built, when there is a run, so the
 * team's own panel is named from the list it actually invited. A setting
 * deleted since the run is refused by the list route and falls back below.
 *
 * A failure here is not a failure of the results screen: the counts and the
 * comparison are the lesson, and the names are the illustration. So a refusal
 * on the list leaves the maps empty and the panels fall back to profile
 * numbers, rather than taking the whole screen down.
 */
async function namesForEvent(
  eventKey: string,
  settingName: string | null,
  signal: AbortSignal,
): Promise<{ names: NamesByProfileNo; factorLabels: Readonly<Record<string, string>> }> {
  const weighting: ListWeighting =
    settingName === null ? { kind: "default" } : { kind: "setting", name: settingName };
  try {
    const list = await readRankedList(eventKey, weighting, signal);
    return {
      names: new Map(list.entries.map((entry) => [entry.profile_no, entry.display_name])),
      factorLabels: list.factor_labels ?? {},
    };
  } catch (error) {
    // An abort is not a missing list — it is this load being replaced. It has
    // to propagate, or a superseded load resolves with an empty map and the
    // hook settles a stale answer over the live one.
    if (signal.aborted) {
      throw error;
    }
    return { names: new Map(), factorLabels: {} };
  }
}

function ResultsBody({
  eventKey,
  data,
  onChanged,
}: {
  readonly eventKey: string;
  readonly data: ResultsData;
  readonly onChanged: () => void;
}): React.JSX.Element {
  const [pending, setPending] = React.useState(false);
  const [refusal, setRefusal] = React.useState<{ code: string; message: string } | null>(null);
  const [finalSetting, setFinalSetting] = React.useState("");
  /**
   * Set when this browser's own run just succeeded, so the seats fill once
   * (`ce-seat-fill`). A reload or a later visit mounts with it off and shows
   * the final state.
   */
  const [justRan, setJustRan] = React.useState(false);

  async function run(action: () => Promise<void>): Promise<void> {
    if (pending) {
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      await action();
    } catch (error) {
      // Every results refusal is a state, not an error: locked, already run,
      // and the rule not yet confirmed are all the product working. Each is
      // shown as the server's own sentence.
      setRefusal(
        isRefusal(error)
          ? { code: error.code, message: error.message }
          : {
              code: "unreachable",
              message: "The exercise could not be reached. Check the connection and try again.",
            },
      );
    } finally {
      setPending(false);
    }
  }

  function runFinal(): void {
    void run(async () => {
      try {
        await runResults(eventKey, finalSetting);
      } catch (error) {
        // The chosen name was deleted since this screen loaded: clear it and
        // re-read the list, so the picker only offers names the run route can
        // still find. The sentence still shows.
        if (isRefusal(error) && error.code === SETTING_UNKNOWN) {
          setFinalSetting("");
          onChanged();
        }
        throw error;
      }
      setJustRan(true);
      onChanged();
    });
  }

  const canRefresh = data.asking.choice !== null && !data.asking.refreshed;
  const locked = refusal !== null && refusal.code === LOCKED;

  return (
    <div className="flex flex-col gap-8 md:gap-12">
      {refusal === null || locked ? null : (
        <ExerciseNotice
          message={refusal.message}
          tone={refusal.code === "unreachable" ? "problem" : "calm"}
        />
      )}

      {data.results === null ? (
        <section className="flex flex-col gap-5">
          <p className="ce-body text-ce-muted">
            Your team has not run results for this event yet. A team runs them once.
          </p>
          <FinalSettingChoice
            eventKey={eventKey}
            saved={data.saved}
            factorLabels={data.factorLabels}
            value={finalSetting}
            onChange={setFinalSetting}
          />
          {locked ? (
            <LockPanel
              message={refusal.message}
              pending={pending}
              canCheck={finalSetting !== ""}
              onCheck={runFinal}
            />
          ) : null}
          <div>
            <button
              type="button"
              disabled={pending || finalSetting === ""}
              aria-describedby={FINAL_SETTING_HINT}
              onClick={runFinal}
              className={ceButton("primary", "ce-btn-lg w-full sm:w-auto")}
            >
              {pending ? <Spinner /> : null}
              {pending ? "Running…" : "Run results for this event"}
            </button>
          </div>
        </section>
      ) : (
        <ResultPanels results={data.results} names={data.names} reveal={justRan} />
      )}

      <section className="ce-card flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between md:p-6">
        <div className="flex flex-col gap-2">
          <h2 className="ce-h2 text-ce-ink">Ask the people your team invited</h2>
          {data.asking.choice === null ? (
            <p className="ce-body text-ce-ink">
              Your team has not picked a way of asking yet.{" "}
              <Link to="/exercise/asking" className="ce-link">
                Pick one first
              </Link>
              .
            </p>
          ) : (
            <p className="ce-meta text-ce-muted">Your team may ask once.</p>
          )}
        </div>
        {data.asking.choice === null ? null : (
          <button
            type="button"
            disabled={pending || !canRefresh}
            onClick={() =>
              void run(async () => {
                await refreshProfiles();
                onChanged();
              })
            }
            className={ceButton("secondary")}
          >
            {data.asking.refreshed ? "Your team has already asked" : "Ask them now"}
          </button>
        )}
      </section>
    </div>
  );
}

/**
 * The results lock, closed (DESIGN.md §6.14): the envelope, a `Lock` chip
 * "Results are closed", the server's own sentence, and "Check again", which
 * tries the run again with the chosen setting. Calm, never red — a closed
 * event is the product working.
 */
function LockPanel({
  message,
  pending,
  canCheck,
  onCheck,
}: {
  readonly message: string;
  readonly pending: boolean;
  readonly canCheck: boolean;
  readonly onCheck: () => void;
}): React.JSX.Element {
  return (
    <div
      role="status"
      data-slot="exercise-results-lock"
      className="ce-card ce-notice-in flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:gap-8 md:p-8"
    >
      <EnvelopeArt className="hidden h-20 w-24 shrink-0 text-ce-primary sm:block" />
      <div className="flex flex-col items-start gap-3">
        <Chip tone="neutral" icon={<Lock aria-hidden="true" className="size-4" />}>
          Results are closed
        </Chip>
        <p className="ce-body text-ce-ink">{message}</p>
        <button
          type="button"
          className={ceButton("secondary")}
          disabled={pending || !canCheck}
          onClick={onCheck}
        >
          <RotateCcw aria-hidden="true" className="size-5" />
          Check again
        </button>
      </div>
    </div>
  );
}

/**
 * Step three of the owner's flow: the team's one final setting for this event.
 *
 * Radio cards, not a `<select>` (DESIGN.md §6.13): each shows the setting's
 * name and its four weights in Ann's words. The choices are the team's saved
 * settings, read from the server, so a name here is always one the run route
 * can find. Nothing is chosen for the team, even when it has saved only one:
 * choosing is the step.
 */
function FinalSettingChoice({
  eventKey,
  saved,
  factorLabels,
  value,
  onChange,
}: {
  readonly eventKey: string;
  readonly saved: SavedSettingsView | null;
  readonly factorLabels: Readonly<Record<string, string>>;
  readonly value: string;
  readonly onChange: (value: string) => void;
}): React.JSX.Element {
  const settings = saved?.settings ?? [];
  if (settings.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <h2 id="exercise-final-setting-heading" className="ce-h2 text-ce-ink">
          Your team's final setting
        </h2>
        <div className="ce-card flex flex-col items-center gap-4 p-6 text-center md:p-8">
          <ProfileCardArt className="h-24 w-20 text-ce-primary" />
          <p
            id={FINAL_SETTING_HINT}
            className="ce-body max-w-[52ch] text-ce-ink"
            data-slot="exercise-final-setting"
          >
            Your team has not saved any settings for this event yet. Save one on{" "}
            <Link to={`/exercise/events/${encodeURIComponent(eventKey)}`} className="ce-link">
              your team's list
            </Link>{" "}
            first, then choose it here as your final setting.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4" data-slot="exercise-final-setting">
      <div className="flex flex-col gap-2">
        <h2 id="exercise-final-setting-heading" className="ce-h2 text-ce-ink">
          Your team's final setting
        </h2>
        <p id={FINAL_SETTING_HINT} className="ce-body text-ce-muted">
          Your team's invited list is built from the setting you choose. Choose one to run
          results.
        </p>
      </div>
      <div
        role="radiogroup"
        aria-labelledby="exercise-final-setting-heading"
        className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-6"
      >
        {settings.map((setting) => (
          <SettingRadioCard
            key={setting.name}
            setting={setting}
            factorLabels={factorLabels}
            checked={value === setting.name}
            onChange={() => onChange(setting.name)}
          />
        ))}
      </div>
    </div>
  );
}

function SettingRadioCard({
  setting,
  factorLabels,
  checked,
  onChange,
}: {
  readonly setting: SavedSettingView;
  readonly factorLabels: Readonly<Record<string, string>>;
  readonly checked: boolean;
  readonly onChange: () => void;
}): React.JSX.Element {
  // Only factors the server has words for; a rulebook key is never printed.
  const keys = orderedKeys(factorLabels).filter((key) => key in setting.weights);
  return (
    <label
      className={`ce-card ce-lift flex cursor-pointer flex-col gap-3 p-5 has-[input:focus-visible]:outline-3 has-[input:focus-visible]:outline-offset-3 has-[input:focus-visible]:outline-ce-primary md:p-6 ${
        checked ? "outline-3 outline-ce-primary" : ""
      }`}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="ce-h3 min-w-0 break-words text-ce-ink">{setting.name}</span>
        <input
          type="radio"
          name="exercise-final-setting"
          value={setting.name}
          checked={checked}
          onChange={onChange}
          aria-label={setting.name}
          className="mt-1 size-6 shrink-0 accent-[var(--ce-primary)]"
        />
      </span>
      {keys.length === 0 ? null : (
        <span className="flex flex-col">
          {keys.map((key) => (
            <span key={key} className="flex items-baseline justify-between gap-3 py-1">
              <span className="ce-meta text-ce-muted">{factorLabels[key]}</span>
              <span className="ce-label ce-num text-ce-ink">
                {(setting.weights[key] ?? 0).toFixed(2)}
              </span>
            </span>
          ))}
        </span>
      )}
    </label>
  );
}
