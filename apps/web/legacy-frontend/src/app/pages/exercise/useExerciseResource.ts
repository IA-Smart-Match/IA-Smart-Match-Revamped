/**
 * Loading one exercise resource, with the four states a screen must handle.
 *
 * Deliberately not React Query. `src/lib/queryClient.ts` keys every cache
 * entry by principal first and clears the cache when identity changes; there
 * is no identity in this product (ADR-0025 D1), so every exercise key would
 * share one `undefined` principal and the isolation the CBA app relies on
 * would be isolating nothing. A team's workspace is a server row addressed by
 * a cookie and re-reading it is one request, so this hook holds no cache at
 * all: mount, fetch, render, and re-fetch when the screen says to.
 *
 * The state is a discriminated union rather than three booleans, because the
 * combinations that cannot happen — loaded *and* refused, loading *and* has
 * data — are exactly the ones a screen renders wrongly when they do.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ExerciseRefusal, ExerciseUnreachable } from "../../../lib/exerciseApi";

export type ExerciseResourceState<T> =
  /** Nothing has arrived yet. Only ever the *first* load — see `refreshing`. */
  | { readonly status: "loading" }
  | {
      readonly status: "ready";
      readonly data: T;
      /**
       * The refusal the *latest* load got, with the previous answer still on
       * screen beside it.
       *
       * Only ever non-null for a caller that passed `keepDataOnRefusal` — see
       * the hook's own docstring for why that is opt-in rather than the
       * default. `null` on every successful load, so a stale sentence cannot
       * outlive the request that produced it.
       */
      readonly refusal: ExerciseRefusal | null;
      /**
       * A newer load is in flight and this is the previous answer.
       *
       * The screen stays mounted while it runs. Dropping back to `loading`
       * would unmount the whole panel — which on the matching screen took the
       * weight inputs down mid-keystroke, and on the asking screen threw away
       * the counts from a refresh that may only happen once.
       */
      readonly refreshing: boolean;
    }
  /** The server refused, with a code to branch on and a sentence to show. */
  | { readonly status: "refused"; readonly refusal: ExerciseRefusal }
  /** The request never landed, or the answer was not the envelope. */
  | { readonly status: "unreachable"; readonly message: string };

/**
 * Turn any thrown value into a state.
 *
 * Nothing reaches a screen but a refusal's own sentence or this module's one
 * transport sentence — ADR-0025 D6's implementation note is emphatic that a
 * raw server or exception string must not be rendered, and the place to stop
 * that is where errors become state.
 */
export function stateFromError<T>(error: unknown): ExerciseResourceState<T> {
  if (error instanceof ExerciseRefusal) {
    return { status: "refused", refusal: error };
  }
  return { status: "unreachable", message: new ExerciseUnreachable().message };
}

export interface ExerciseResourceOptions {
  /**
   * Keep the answer already on screen when a later load is refused.
   *
   * **Opt-in, and deliberately not the default.** Whether a stale answer
   * beside a refusal is honest or dishonest depends entirely on what the
   * answer is.
   *
   * The matching screen wants it: a team asks for a weighting the server will
   * not take, and the list it is looking at is still the true answer to the
   * question it asked before that. Throwing the screen away to show one
   * sentence takes the weight boxes with it, leaving nothing to correct the
   * mistake in.
   *
   * The instructor and results screens must not have it. A refused read there
   * means the session has gone or the run cannot be produced, and showing the
   * previous dataset list or the previous run underneath that sentence would
   * be showing something that is no longer known to be true. They keep the
   * discarding behaviour: the refusal replaces the screen.
   */
  readonly keepDataOnRefusal?: boolean;
}

/**
 * Load a resource on mount and whenever `deps` change.
 *
 * `load` receives an `AbortSignal`: a participant who picks a second event
 * before the first list arrives must not see the first one land on top of it,
 * and an unmounted screen must not set state.
 */
export function useExerciseResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  options: ExerciseResourceOptions = {},
): { readonly state: ExerciseResourceState<T>; readonly reload: () => Promise<void> } {
  const keepDataOnRefusal = options.keepDataOnRefusal ?? false;
  const [state, setState] = useState<ExerciseResourceState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  // Kept in a ref so a caller may pass an inline closure without the effect
  // re-running on every render; `deps` is what decides when to re-fetch.
  const loadRef = useRef(load);
  loadRef.current = load;

  // Resolved when the *next* effect run settles, so a caller of `reload` can
  // tell the difference between "the request is in flight" and "the state on
  // screen now reflects it" — a once-only button must stay disabled for the
  // whole of that, not just for its own network call.
  const settled = useRef<(() => void)[]>([]);

  // Set the moment this hook's owner unmounts, and nowhere else. A run's
  // cleanup hands its unresolved waiters to "whichever run replaces it" —
  // there is no such run on an unmount, so without this they wait forever.
  // React runs every effect's unmount cleanup in *declaration* order (verified
  // against react-dom directly — not the reverse-order teardown a class
  // component or a stack-based mental model would suggest), so this effect,
  // declared *before* the data-fetching one below, has already set this to
  // `true` by the time that effect's own cleanup checks it.
  const unmounted = useRef(false);
  useEffect(() => {
    // `React.StrictMode` (`main.tsx` wraps the app in it) mounts every
    // component twice in development: mount, cleanup, mount again, all
    // synchronously. That first cleanup would otherwise leave this `true`
    // for the component's entire real life — every `reload()` in dev would
    // then resolve immediately, before its data ever lands, silently
    // breaking G3 in exactly the environment this is developed in.
    // Un-setting it here, in the effect's own setup, is what makes the
    // *second* mount's cleanup (the one that fires on a genuine unmount) the
    // one that sticks.
    unmounted.current = false;
    return () => {
      unmounted.current = true;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let live = true;
    let settledThisRun = false;
    // Resolvers queued by `reload` calls made before this run started. If
    // this run itself gets superseded before settling (a second `reload`
    // arriving while the first is still in flight), they are handed to the
    // next run rather than dropped, so a caller awaiting the first `reload`
    // still resolves once *some* later state lands, rather than never.
    const resolvers = settled.current;
    settled.current = [];
    const resolveAll = (): void => {
      settledThisRun = true;
      for (const resolve of resolvers) {
        resolve();
      }
    };
    // Keep whatever is on screen while the new answer is fetched. Only a
    // screen that has never had data drops to `loading`; one that has shows
    // the previous answer and says it is busy. This is what keeps the weight
    // inputs mounted between keystrokes and the refresh counts on screen
    // across the reload that follows them.
    setState((previous) =>
      previous.status === "ready"
        ? { status: "ready", data: previous.data, refreshing: true, refusal: null }
        : { status: "loading" },
    );
    loadRef
      .current(controller.signal)
      .then((data) => {
        if (live) {
          setState({ status: "ready", data, refreshing: false, refusal: null });
          resolveAll();
        }
      })
      .catch((error: unknown) => {
        if (!live || controller.signal.aborted) {
          return;
        }
        setState((previous) => {
          if (
            keepDataOnRefusal &&
            previous.status === "ready" &&
            error instanceof ExerciseRefusal
          ) {
            // The answer on screen is still the true answer to the question
            // that produced it. The refusal is about the *new* question.
            return { status: "ready", data: previous.data, refreshing: false, refusal: error };
          }
          return stateFromError<T>(error);
        });
        resolveAll();
      });
    return () => {
      live = false;
      controller.abort();
      if (settledThisRun) {
        return;
      }
      if (unmounted.current) {
        // There is no next run to hand these to — the component that asked
        // is gone. Resolve rather than leak: a caller awaiting `reload()`
        // (a once-only button's `run`, for instance) must not hang forever
        // just because the screen it was on has since unmounted.
        for (const resolve of resolvers) {
          resolve();
        }
        return;
      }
      // This run never settled and the hook is still mounted — hand its
      // waiters to whichever run replaces it, rather than resolving early
      // (the state has not changed yet) or forgetting them (a caller of
      // `reload` would hang).
      settled.current = [...resolvers, ...settled.current];
    };
    // `deps` is the caller's declared dependency list; `attempt` forces a
    // reload. `keepDataOnRefusal` is a caller constant, not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const reload = useCallback(() => {
    return new Promise<void>((resolve) => {
      settled.current = [...settled.current, resolve];
      setAttempt((value) => value + 1);
    });
  }, []);

  return { state, reload };
}
