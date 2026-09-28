/**
 * The four adjustable factors, in Ann's plain words.
 *
 * Requirements, "Matching" row: *"four adjustable factors, labeled in plain
 * words: same major; said they are interested in this topic; career goal fits
 * this event; went to similar events before"*. Those labels are not written
 * here — they arrive as `factor_labels` on every list response, keyed by the
 * rulebook's factor keys, and a key is never rendered. A screen that wrote the
 * four phrases into itself would be a second copy of Ann's wording, drifting
 * from the server's the first time she changes one.
 *
 * The numbers a team types *are* shown, and that is not a breach of ADR-0025
 * D8: D8 forbids a score, a percentage or a confidence — something the app
 * calculated about a person. A weight is the team's own input, and the whole
 * lesson turns on the team seeing what it chose.
 *
 * The starting values are the server's: equal weights (OQ-CE-02, closed
 * 2026-09-25 — "Teams should decide for themselves which factors matter
 * most"). This screen sends no weights at all until a team changes one, which
 * is what makes the server's equal defaults the defaults.
 *
 * **The controls are the desk's `WeightSlider` (DESIGN.md §6.6, owner ruling
 * 2).** Each one owns its slider, its number box, the strict-decimal rule and
 * the field's own messages, and calls `commit` once per finished change —
 * pointer-up, a key step, Enter or leaving the box. The queue and in-flight
 * logic below is unchanged: one request in flight, one merged commit queued
 * behind it. A number typed in a box is sent exactly as typed, even outside
 * 0–1: the server refuses a negative weight in its own sentence.
 */
import * as React from "react";

import type { ExerciseRefusal } from "../../../lib/exerciseApi";
import { EXERCISE_FACTOR_KEYS, UNDECIDED_GOAL_HALF_LABEL_KEY } from "../../../lib/exerciseClient";
import { WeightSlider, formatWeightTotal, weightTotal } from "./desk";
import { WeightsCompactBar } from "./WeightsCompactBar";

/**
 * What the total means, in Ann's background-note framing ("twice as much").
 * The scorer divides each weight by the total (`factor_registry.py`
 * `normalize_weights`), so the total itself changes nothing: no weight has
 * to add up to 1, and no percentage is shown (ADR-0025 D8).
 */
export const WEIGHT_TOTAL_MEANING =
  "What matters is how the weights compare: a factor set to 0.50 counts twice as much as one set to 0.25.";

/** The server's sentence for an all-zero weighting (`exercise_matching_weights.py`), shown before it is sent. */
export const WEIGHT_TOTAL_ZERO = "At least one number must be above 0.";

/**
 * The server's code for a refused weighting (`exercise_matching_weights.py`).
 * Owner ruling 2026-09-27: its sentence is shown once, under the slider, and
 * the screen does not repeat it in a page notice. Any other refusal of a list
 * request is the screen's to show.
 */
export const WEIGHTS_REFUSAL_CODE = "exercise_weights_invalid";

export function isWeightsRefusal(refusal: ExerciseRefusal | null): boolean {
  return refusal !== null && refusal.code === WEIGHTS_REFUSAL_CODE;
}

/** The id of a refusal sentence drawn under a box the team is still in. */
function refusalSentenceId(key: string): string {
  return `exercise-weight-${key}-refusal`;
}

export interface WeightsControlsProps {
  /** Ann's words per factor key, from the list response. */
  readonly factorLabels: Readonly<Record<string, string>>;
  /** The weights the current list was built with — always the last CONFIRMED weighting. */
  readonly weights: Readonly<Record<string, number>>;
  readonly onChange: (weights: Readonly<Record<string, number>>) => void;
  readonly disabled?: boolean;
  /**
   * The refusal the *latest* commit got, if any — from the screen's
   * `useExerciseResource` state, which keeps `weights` unchanged (the same
   * object reference) when a request is refused. Without this, a refused
   * commit's speculative base is never told it was rejected: `weights`
   * changing is this component's only signal that anything happened, and a
   * refusal produces no change at all to notice.
   */
  readonly refusal?: ExerciseRefusal | null;
}

/**
 * The factor keys to show, in a stable order.
 *
 * The rulebook's four first, then anything else the server sent — so a fifth
 * factor appearing on the response is displayed rather than silently dropped,
 * and the four do not reshuffle when a key's order in the JSON changes.
 * {@link UNDECIDED_GOAL_HALF_LABEL_KEY} is a label for the ranked list, not a
 * weight, so it never gets a box.
 */
export function orderedFactorKeys(factorLabels: Readonly<Record<string, string>>): string[] {
  const known = EXERCISE_FACTOR_KEYS.filter((key) => key in factorLabels);
  const extra = Object.keys(factorLabels).filter(
    (key) =>
      !(EXERCISE_FACTOR_KEYS as readonly string[]).includes(key) &&
      key !== UNDECIDED_GOAL_HALF_LABEL_KEY,
  );
  return [...known, ...extra];
}

export function WeightsControls({
  factorLabels,
  weights,
  onChange,
  disabled = false,
  refusal = null,
}: WeightsControlsProps): React.JSX.Element {
  const keys = orderedFactorKeys(factorLabels);
  const card = React.useRef<HTMLFieldSetElement>(null);

  /**
   * Which weight's number box the team is still in, so a refusal
   * does not wipe what they are typing. Each `WeightSlider` already keeps its
   * own box's text when the server's echo arrives; this is the one place the
   * panel needs to know, because it decides whose slider hears a refusal.
   */
  const focused = React.useRef<string | null>(null);

  /**
   * The base a commit merges onto: the last weighting this component asked
   * for, not necessarily the last one the server has confirmed.
   *
   * `weights` (the prop) only advances once a response lands, and the hook
   * keeps the *previous* ready data on screen while a request is in flight
   * (`refreshing`). Without this ref, committing weight B before weight A's
   * request had resolved built B's payload on top of the stale prop — the
   * answer to a question the server hadn't been asked yet — and silently
   * dropped A's edit from the request that went out for B. One team's two
   * commits in one round trip must both reach the server; the second must
   * build on the first, not erase it.
   */
  const pendingBase = React.useRef<Readonly<Record<string, number>>>(weights);

  /**
   * Whether a commit's request is currently in flight — i.e. `onChange` has
   * been called and neither `weights` nor `refusal` has answered it yet.
   *
   * At most one request in flight, at most one commit queued behind it (see
   * `queuedEdits`). Sending a second commit while the first is still open
   * used to let the two race: if the server processed them out of order, or
   * refused the first but accepted the second, the accepted commit's own
   * payload still carried the *other* commit's now-meaningless number,
   * because it was built by merging onto a `pendingBase` that had already
   * been advanced optimistically for a request nobody had answered yet.
   * Queuing removes the interleaving entirely — the second commit is built
   * only once the first is known to have succeeded or failed.
   */
  const [inFlight, setInFlight] = React.useState(false);

  /**
   * Edits committed while a request was in flight, merged into one map and
   * sent as a single follow-up commit once that request settles — built on
   * whatever the settled request's outcome says the confirmed weights now
   * are, never on the in-flight request's own optimistic guess.
   */
  const queuedEdits = React.useRef<Record<string, number> | null>(null);

  /** The weights the in-flight request changed: whose sliders a refusal is about. */
  const inFlightKeys = React.useRef<readonly string[]>([]);

  /** Weights sent or queued and not yet answered: each shows a small spinner (§6.6 L). */
  const [pendingKeys, setPendingKeys] = React.useState<readonly string[]>([]);

  /**
   * The latest refusal and the one slider that shows its sentence (§6.6 X).
   * Handing the refusal object to a slider is what returns it to the
   * confirmed weight — a new object per refused attempt, so it reverts even
   * when the sentence repeats. Cleared when that weight is committed again,
   * and once a list is accepted.
   *
   * One refusal answers one weighting, so a weights refusal's sentence is
   * shown once (owner ruling 2026-09-27): under the number box the team is
   * still typing in, else the slider that holds focus, else the first
   * refused one. A box being typed in keeps its text, so there the sentence
   * is drawn under it here rather than handed to the slider (which would
   * reset the box). Any other slider the same request changed is reverted by
   * remounting it (`revision`), which shows nothing. Any other refusal is
   * the screen's notice to show; the sliders only revert.
   */
  const [shownRefusal, setShownRefusal] = React.useState<{
    readonly key: string;
    readonly refusal: ExerciseRefusal;
    /** The team is still in this weight's box: draw the sentence, keep the text. */
    readonly inBox: boolean;
  } | null>(null);
  const [revision, setRevision] = React.useState<Readonly<Record<string, number>>>({});
  const rows = React.useRef<Record<string, HTMLDivElement | null>>({});

  /**
   * Each slider's number as shown right now, committed or not, so the total
   * follows a drag or typing. `null` (text that is not a number) or a missing
   * key falls back to the confirmed weight.
   */
  const [liveValues, setLiveValues] = React.useState<Readonly<Record<string, number | null>>>({});
  const onLiveChange = React.useCallback((key: string, value: number | null): void => {
    setLiveValues((previous) => (previous[key] === value ? previous : { ...previous, [key]: value }));
  }, []);
  const total = weightTotal(keys.map((key) => liveValues[key] ?? weights[key] ?? 0));

  function send(next: Readonly<Record<string, number>>, changed: readonly string[]): void {
    pendingBase.current = next;
    inFlightKeys.current = changed;
    setInFlight(true);
    onChange(next);
  }

  /**
   * Common to both ways a commit settles: a successful load (`weights`
   * changed) and a refusal (`weights` unchanged, `refusal` fresh). Either
   * way `weights` is the newest confirmed truth — on a refusal because
   * `useExerciseResource` never applied the rejected data at all.
   *
   * If an edit was queued while the just-settled request was in flight, it
   * is sent now, merged onto this confirmed base — never onto the settled
   * request's own optimistic `pendingBase`, which is exactly the base a
   * refused commit must not be built on (H1's fix, extended to the queue).
   */
  function onSettled(confirmed: Readonly<Record<string, number>>): void {
    pendingBase.current = confirmed;
    inFlightKeys.current = [];
    setInFlight(false);
    const queued = queuedEdits.current;
    queuedEdits.current = null;
    if (queued === null) {
      setPendingKeys([]);
      return;
    }
    const changed = Object.keys(queued);
    setPendingKeys(changed);
    send({ ...confirmed, ...queued }, changed);
  }

  React.useEffect(() => {
    // A confirmed response is the newest truth about what was asked for.
    setShownRefusal(null);
    onSettled(weights);
    // `keys` is derived from `factorLabels`; both change only with a new event.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weights, factorLabels]);

  /**
   * A refused commit never changes `weights` — `useExerciseResource`
   * deliberately keeps the same, previous `data` object when a request is
   * refused, so the effect above (keyed on `weights`) never reruns for it.
   * Without this, `pendingBase` stayed on the rejected value forever: every
   * later commit merged onto a base the server had already said no to,
   * instead of onto the truth `weights` still holds.
   *
   * `refusal` is a fresh `ExerciseRefusal` instance per failed attempt, so
   * it is a reliable trigger even when two commits in a row are refused for
   * the same reason. The sliders the refused request changed hear the
   * sentence and fall back to the confirmed weight — except one the team is
   * still in, whose text stays theirs until they leave it.
   */
  React.useEffect(() => {
    if (refusal === null) {
      return;
    }
    const inBox = focused.current;
    const refused = keys.filter((key) => inFlightKeys.current.includes(key));
    if (refused.length > 0) {
      let announcer: string | null = null;
      if (isWeightsRefusal(refusal)) {
        const active = document.activeElement;
        announcer =
          (inBox !== null && refused.includes(inBox) ? inBox : null) ??
          refused.find((key) => active !== null && rows.current[key]?.contains(active)) ??
          refused[0];
        setShownRefusal({ key: announcer, refusal, inBox: announcer === inBox });
      } else {
        setShownRefusal(null);
      }
      const others = refused.filter((key) => key !== announcer && key !== inBox);
      if (others.length > 0) {
        setRevision((previous) => {
          const next = { ...previous };
          for (const key of others) {
            next[key] = (next[key] ?? 0) + 1;
          }
          return next;
        });
      }
    }
    onSettled(weights);
    // `weights` is read for its value as of the refusal, not watched — this
    // effect's own trigger is `refusal` itself, a fresh object per refused
    // attempt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refusal]);

  /**
   * Send one weight upstream, once, when the team is done with it — or, if
   * another commit is already in flight, fold it into the one commit queued
   * behind it (see `queuedEdits`).
   *
   * Text that is not a plain number never gets here: the slider's box
   * rejects it with its own message, rather than `Number.parseFloat` reading
   * a prefix and sending a value the team never typed. A number the server
   * will not take is sent and refused in the server's own words, like every
   * other refusal on this screen.
   */
  function commit(key: string, value: number): void {
    setShownRefusal((previous) => (previous?.key === key ? null : previous));
    // What the next request would ask for if it went out right now: the
    // last confirmed base, with any already-queued edit layered on top.
    const effectiveBase = { ...pendingBase.current, ...(queuedEdits.current ?? {}) };
    if (value === effectiveBase[key]) {
      // Nothing changed relative to what has already been asked for or
      // queued: do not spend a request.
      return;
    }
    setPendingKeys((previous) => (previous.includes(key) ? previous : [...previous, key]));
    if (inFlight) {
      // The controls stay live while queued; this edit joins whatever else is
      // already waiting and both go out together once the in-flight request
      // settles.
      queuedEdits.current = { ...(queuedEdits.current ?? {}), [key]: value };
      return;
    }
    // A new object, never a mutation of the one the response gave us, built
    // on the last confirmed weighting.
    send({ ...pendingBase.current, [key]: value }, [key]);
  }

  /**
   * While a refusal's sentence waits under a box the team is still typing in,
   * the box itself is marked invalid and names the sentence. `WeightSlider`
   * owns the box and takes no such props, so the two attributes are set on
   * it directly and handed back once the slider shows the refusal itself.
   */
  React.useLayoutEffect(() => {
    if (shownRefusal === null || !shownRefusal.inBox) {
      return undefined;
    }
    const box = document.getElementById(`exercise-weight-${shownRefusal.key}-value`);
    const sentenceId = refusalSentenceId(shownRefusal.key);
    if (box === null) {
      return undefined;
    }
    box.setAttribute("aria-invalid", "true");
    box.setAttribute("aria-describedby", sentenceId);
    return () => {
      // Only undo what this effect set: the slider may already point the box
      // at its own copy of the sentence.
      if (box.getAttribute("aria-describedby") === sentenceId) {
        box.removeAttribute("aria-describedby");
        box.setAttribute("aria-invalid", "false");
      }
    };
  }, [shownRefusal]);

  function focusFirstSlider(): void {
    card.current?.querySelector<HTMLElement>('[role="slider"]')?.focus();
  }

  return (
    <>
      <fieldset
        ref={card}
        data-slot="exercise-weights"
        className="ce-card m-0 flex min-w-0 scroll-mt-ce-8 flex-col gap-ce-5 border-0 p-ce-4 md:p-ce-5"
      >
        <legend className="ce-type-h3 float-left w-full text-ce-ink">
          How much each thing counts
        </legend>
        <div className="clear-both flex flex-col gap-ce-5">
          {keys.map((key) => (
            <div
              key={key}
              ref={(element) => {
                rows.current[key] = element;
              }}
              // Only the number box holds text a refusal could wipe; a focused
              // slider thumb takes the refusal and snaps back like any other.
              onFocus={(event) => {
                focused.current = event.target instanceof HTMLInputElement ? key : null;
              }}
              onBlur={() => {
                focused.current = null;
                // #251 review H1: a refusal that landed while the team was in
                // this box is handed to the slider once they leave it, which
                // reverts box and thumb to the confirmed weight and keeps the
                // one sentence, now linked by the slider.
                setShownRefusal((previous) =>
                  previous !== null && previous.key === key && previous.inBox
                    ? { ...previous, inBox: false }
                    : previous,
                );
              }}
            >
              <WeightSlider
                key={revision[key] ?? 0}
                id={`exercise-weight-${key}`}
                // Ann's words. The key is the box's name, never its label.
                label={factorLabels[key] ?? ""}
                name={key}
                value={weights[key] ?? 0}
                onCommit={(value) => commit(key, value)}
                onLiveChange={(value) => onLiveChange(key, value)}
                refusal={
                  shownRefusal?.key === key && !shownRefusal.inBox ? shownRefusal.refusal : null
                }
                pending={pendingKeys.includes(key)}
                disabled={disabled}
              />
              {shownRefusal?.key === key && shownRefusal.inBox ? (
                <p
                  id={refusalSentenceId(key)}
                  role="status"
                  data-slot="exercise-weight-error"
                  className="ce-type-meta mt-ce-2 text-ce-danger"
                >
                  {shownRefusal.refusal.message}
                </p>
              ) : null}
            </div>
          ))}
        </div>
        <div
          data-slot="exercise-weight-total"
          className="flex flex-col gap-ce-2 border-t border-ce-line pt-ce-4"
        >
          {/* The team's own numbers added up: a sum, never a percentage (D8). */}
          <p className="ce-type-label ce-tabular text-ce-ink">
            Total weight: <span className="ce-type-value">{formatWeightTotal(total)}</span>
          </p>
          <p className="ce-type-body text-ce-ink">{WEIGHT_TOTAL_MEANING}</p>
          {/* Shown before sending; a refusal already on screen is not repeated (owner rule). */}
          {total === 0 && shownRefusal === null ? (
            <p
              role="status"
              data-slot="exercise-weight-total-zero"
              className="ce-type-meta text-ce-danger"
            >
              {WEIGHT_TOTAL_ZERO}
            </p>
          ) : null}
          <p className="ce-type-meta text-ce-ink-muted">
            The list is rebuilt when you let go of a slider or press Enter.
          </p>
        </div>
      </fieldset>
      <WeightsCompactBar
        target={card}
        values={keys.map((key) => weights[key] ?? 0)}
        onEdit={focusFirstSlider}
      />
    </>
  );
}
