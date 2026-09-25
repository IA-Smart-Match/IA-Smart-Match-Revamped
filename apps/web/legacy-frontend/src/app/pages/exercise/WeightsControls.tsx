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
 */
import * as React from "react";

import type { ExerciseRefusal } from "../../../lib/exerciseApi";
import { EXERCISE_FACTOR_KEYS } from "../../../lib/exerciseClient";

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
 */
function orderedKeys(factorLabels: Readonly<Record<string, string>>): string[] {
  const known = EXERCISE_FACTOR_KEYS.filter((key) => key in factorLabels);
  const extra = Object.keys(factorLabels).filter(
    (key) => !(EXERCISE_FACTOR_KEYS as readonly string[]).includes(key),
  );
  return [...known, ...extra];
}

/**
 * A strict decimal, ASCII-digit only, or `null`.
 *
 * `Number.parseFloat` reads a *prefix*: `"0.5abc"` is `0.5`, `"1,5"` (a
 * comma-locale team's five tenths) is `1` — both silently coerce a rejected
 * or foreign number into an accepted, wrong one. This instead matches the
 * whole string against one plain decimal shape and returns `null` for
 * anything else, `""` included, so the caller can tell "nothing usable was
 * typed" from "the number is legitimately unchanged".
 *
 * The shape accepts a leading-dot decimal (`.5`, same value as `0.5`) but not
 * a trailing-dot one (`5.` is not a number until a digit follows the dot,
 * same reasoning `inputMode="decimal"` above rests on), not `1,5` (a
 * comma-locale team's number, silently misread as `1` by `parseFloat`), not
 * scientific notation, and not a leading `+`.
 */
function strictDecimal(text: string): number | null {
  if (!/^-?(\d+(\.\d+)?|\.\d+)$/.test(text)) {
    return null;
  }
  return Number(text);
}

/** The server's numbers as the text the boxes start from. */
function textOf(
  weights: Readonly<Record<string, number>>,
  keys: readonly string[],
): Record<string, string> {
  const text: Record<string, string> = {};
  for (const key of keys) {
    text[key] = String(weights[key] ?? 0);
  }
  return text;
}

export function WeightsControls({
  factorLabels,
  weights,
  onChange,
  disabled = false,
  refusal = null,
}: WeightsControlsProps): React.JSX.Element {
  const keys = orderedKeys(factorLabels);

  /**
   * What is in the boxes, as text, while a team is typing.
   *
   * The inputs used to be driven straight from the server's echo, with every
   * keystroke sent upstream as a new weighting. That made typing `0.75`
   * impossible: `0` refetched the list, the refetch re-rendered the panel, and
   * the `.` had nowhere to land. A number input also reports an in-progress
   * `0.` as the empty string, so a controlled value parsed per keystroke
   * cannot represent one.
   *
   * So the text lives here until the team finishes with a box, and the server
   * hears about it once, on blur or on Enter.
   */
  const [draft, setDraft] = React.useState<Record<string, string>>(() => textOf(weights, keys));

  /**
   * Which box has focus, so the server's echo does not overwrite it.
   *
   * When a committed weighting comes back the response's numbers are adopted —
   * they are the truth about what the list was built from — but never into the
   * box the team is still in.
   */
  const focused = React.useRef<string | null>(null);

  /**
   * The base a commit merges onto: the last weighting this component asked
   * for, not necessarily the last one the server has confirmed.
   *
   * `weights` (the prop) only advances once a response lands, and the hook
   * keeps the *previous* ready data on screen while a request is in flight
   * (`refreshing`). Without this ref, committing box B before box A's
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

  /**
   * One box's rejection sentence, or `null`. Cleared the moment that box's
   * text changes again — the team is already fixing it.
   */
  const [errors, setErrors] = React.useState<Record<string, string | null>>({});

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
    setInFlight(false);
    const queued = queuedEdits.current;
    queuedEdits.current = null;
    setDraft((previous) => {
      const next = textOf(confirmed, keys);
      // Keep whatever the team is still typing in the focused box, and
      // whatever a queued-but-not-yet-sent edit set for any other box — both
      // are truer than the confirmed number for a box that has moved on.
      for (const key of Object.keys(next)) {
        if (key === focused.current || (queued !== null && key in queued)) {
          next[key] = previous[key] ?? next[key];
        }
      }
      return next;
    });
    if (queued !== null) {
      const next = { ...confirmed, ...queued };
      pendingBase.current = next;
      setInFlight(true);
      onChange(next);
    }
  }

  React.useEffect(() => {
    // A confirmed response is the newest truth about what was asked for.
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
   * the same reason.
   */
  React.useEffect(() => {
    if (refusal === null) {
      return;
    }
    onSettled(weights);
    // `weights` is read for its value as of the refusal, not watched — this
    // effect's own trigger is `refusal` itself, a fresh object per refused
    // attempt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refusal]);

  /**
   * Send the box's value upstream, once, when the team is done with it — or,
   * if another commit is already in flight, fold it into the one commit
   * queued behind it (see `queuedEdits`).
   *
   * A number the server will not take — a negative weight — is sent anyway and
   * refused with the server's own plain sentence, like every other refusal on
   * this screen. Guessing at the wording here would put a second copy of it in
   * the client. A number that is not a number at all — `"0.5abc"`, `"1,5"`,
   * an empty box — never reaches the server: it is rejected here, visibly,
   * rather than `Number.parseFloat` reading a prefix and sending a value the
   * team never typed.
   */
  function commit(key: string): void {
    const text = draft[key] ?? "";
    const value = strictDecimal(text);
    if (value === null) {
      setErrors((previous) => ({
        ...previous,
        [key]:
          text.trim() === ""
            ? "Type a number for this weight."
            : `"${text}" is not a plain number. Use digits and one decimal point, like 0.5.`,
      }));
      return;
    }
    setErrors((previous) => (previous[key] === null ? previous : { ...previous, [key]: null }));
    // What the next request would ask for if it went out right now: the
    // last confirmed base, with any already-queued edit layered on top.
    const effectiveBase = { ...pendingBase.current, ...(queuedEdits.current ?? {}) };
    if (value === effectiveBase[key]) {
      // Nothing changed relative to what has already been asked for or
      // queued: do not spend a request.
      return;
    }
    if (inFlight) {
      // The boxes stay editable while queued; this edit joins whatever else
      // is already waiting and both go out together once the in-flight
      // request settles.
      queuedEdits.current = { ...(queuedEdits.current ?? {}), [key]: value };
      return;
    }
    // A new object, never a mutation of the one the response gave us, built
    // on the last confirmed weighting.
    const next = { ...pendingBase.current, [key]: value };
    pendingBase.current = next;
    setInFlight(true);
    onChange(next);
  }

  return (
    <fieldset className="border-0 p-0" data-slot="exercise-weights">
      <legend className="text-3xl font-semibold text-slate-900 dark:text-slate-50">
        How much each thing counts
      </legend>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {keys.map((key) => {
          const inputId = `exercise-weight-${key}`;
          return (
            <div key={key} className="flex flex-col gap-1">
              <label htmlFor={inputId} className="text-xl text-slate-800 dark:text-slate-100">
                {/* Ann's words. The key is the input's name, never its label. */}
                {factorLabels[key]}
              </label>
              <input
                id={inputId}
                name={key}
                // `text`, not `number`. A number input *sanitizes its own
                // value*: while `0.` is being typed, `input.value` reads as
                // the empty string, in jsdom and in every browser, because
                // `0.` is not yet a valid floating-point number. A controlled
                // input therefore cannot hold a half-typed decimal at all —
                // which is the exact character this whole change exists to let
                // a team type. `inputMode="decimal"` still brings up the right
                // keyboard, and the value is parsed on commit.
                type="text"
                inputMode="decimal"
                value={draft[key] ?? ""}
                disabled={disabled}
                onChange={(event) => {
                  const typed = event.target.value;
                  setDraft((previous) => ({ ...previous, [key]: typed }));
                  // The team is already fixing whatever was rejected.
                  setErrors((previous) =>
                    previous[key] === null || previous[key] === undefined
                      ? previous
                      : { ...previous, [key]: null },
                  );
                }}
                aria-invalid={errors[key] != null}
                aria-describedby={errors[key] == null ? undefined : `${inputId}-error`}
                onFocus={() => {
                  focused.current = key;
                }}
                onBlur={() => {
                  focused.current = null;
                  commit(key);
                }}
                onKeyDown={(event) => {
                  // Enter in a single-input form would submit it; here it means
                  // "I am done with this box", which is the same as blurring.
                  if (event.key === "Enter") {
                    event.preventDefault();
                    commit(key);
                  }
                }}
                className="w-40 rounded-lg border-2 border-slate-400 px-3 py-2 text-2xl focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-50"
              />
              {errors[key] == null ? null : (
                <p
                  id={`${inputId}-error`}
                  role="alert"
                  data-slot="exercise-weight-error"
                  className="text-lg text-red-800 dark:text-red-300"
                >
                  {errors[key]}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
