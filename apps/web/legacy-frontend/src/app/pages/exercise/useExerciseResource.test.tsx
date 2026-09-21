/**
 * `reload()`'s promise, specifically: what it does when there is no later
 * run left to resolve it.
 *
 * `ExerciseMatching.test.tsx` and `ExerciseAskingForMore.test.tsx` exercise
 * this hook through the screens that use it; these are unit tests on the one
 * piece those screens cannot put a screen-level test around — a `reload()`
 * whose caller unmounts before the reload it started has settled.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useExerciseResource } from "./useExerciseResource";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useExerciseResource's reload()", () => {
  it("settles reload() on unmount instead of leaving it pending forever", async () => {
    // Round 3, finding 4. A run's cleanup hands its unresolved waiters to
    // "whichever run replaces it" — there is no such run when the hook
    // itself unmounts, so before this fix those resolvers were never called
    // and `await reload()` hung forever. This is exactly the shape a
    // once-only button's `run()` is in if a team navigates away the instant
    // after clicking it.
    let releaseSecondLoad: (() => void) | null = null;
    let loadCount = 0;
    const load = vi.fn(() => {
      loadCount += 1;
      if (loadCount === 1) {
        return Promise.resolve("first");
      }
      return new Promise<string>((resolve) => {
        releaseSecondLoad = () => resolve("second");
      });
    });

    const { result, unmount } = renderHook(() => useExerciseResource(load, []));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    let reloadSettled = false;
    let reloadPromise: Promise<void> = Promise.resolve();
    act(() => {
      reloadPromise = result.current.reload().then(() => {
        reloadSettled = true;
      });
    });

    // The reload's fetch is in flight (held open by `releaseSecondLoad`) and
    // has not settled — `reloadSettled` must still be false.
    await waitFor(() => expect(loadCount).toBe(2));
    expect(reloadSettled).toBe(false);

    // The screen this hook belongs to goes away before that fetch lands.
    unmount();

    await reloadPromise;
    expect(reloadSettled).toBe(true);

    // Nothing pending should still be trying to release into a gone hook;
    // resolving the never-awaited fetch afterwards must not throw.
    expect(() => releaseSecondLoad?.()).not.toThrow();
  });

  it("still hands an unsettled reload to the run that replaces it when nothing has unmounted", async () => {
    // The ordinary case this must not regress: two `reload()` calls in a
    // row, no unmount in between. The first attempt's own fetch never
    // resolves (superseded before it can), but its `reload()` promise still
    // resolves once the *second* attempt's fetch lands — per G3, a caller
    // of `reload()` waits for the state to actually reflect *a* later
    // answer, not specifically its own request.
    const resolvers: Array<(value: string) => void> = [];
    const load = vi.fn(() => new Promise<string>((resolve) => resolvers.push(resolve)));

    const { result } = renderHook(() => useExerciseResource(load, []));
    // The initial mount's own fetch is resolved first, so there is a "ready"
    // state for `reload()` to advance from.
    await waitFor(() => expect(resolvers.length).toBe(1));
    act(() => {
      resolvers[0]("initial");
    });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    let firstSettled = false;
    let secondSettled = false;
    act(() => {
      void result.current.reload().then(() => {
        firstSettled = true;
      });
    });
    act(() => {
      void result.current.reload().then(() => {
        secondSettled = true;
      });
    });

    await waitFor(() => expect(resolvers.length).toBe(3));
    expect(firstSettled).toBe(false);
    expect(secondSettled).toBe(false);

    // Only the last attempt's fetch settling should be needed to resolve
    // both `reload()` calls that were still pending underneath it.
    act(() => {
      resolvers[2]("latest");
    });

    await waitFor(() => expect(firstSettled).toBe(true));
    expect(secondSettled).toBe(true);
  });
});
