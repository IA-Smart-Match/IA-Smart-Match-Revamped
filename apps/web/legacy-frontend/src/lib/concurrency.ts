/**
 * Bounded fan-out for reads that are genuinely per-row.
 *
 * `Promise.all(rows.map(fetch))` is not a concurrency strategy, it is the
 * absence of one: it opens as many sockets as the list is long, and the list is
 * server data whose length nobody chose. On the pilot unit that is ~116
 * simultaneous requests, and the far end is not the browser's to size — each
 * request takes a connection out of a SQLAlchemy pool of 5 plus 5 overflow for
 * the length of its authentication dependency alone, so the eleventh request
 * queues for `pool_timeout` and then fails the whole page with
 * `QueuePool limit of size 5 overflow 5 reached`. The user sees a page that
 * hangs rather than one that loads slowly.
 *
 * So the bound belongs on the client that is generating the fan-out. This
 * helper runs at most `limit` calls at once and returns results in input order,
 * which is the property `Promise.all` was being used for in the first place.
 *
 * **Prefer a bulk route where one exists.** This is the fallback for the case
 * where the server deliberately has no bulk read — see
 * `CoordinatorSpeakerFeedback.tsx` for one, where a per-speaker breakdown is
 * withheld on purpose and cannot be asked for in a single call.
 */

/**
 * The default ceiling on simultaneous reads from one page load.
 *
 * Matched to the API's connection pool size rather than to a round number: at
 * five in flight the pool's five base connections are the binding resource and
 * the five overflow slots stay free for every other caller, so a roster page
 * cannot starve the rest of the deployment while it loads.
 */
export const DEFAULT_READ_CONCURRENCY = 5;

/**
 * Map `items` through `worker`, at most `limit` at a time, in input order.
 *
 * `worker` is expected to settle rather than reject — a caller that wants
 * per-item error reporting should catch inside `worker` and return the failure
 * as a value, which is what keeps one bad row from discarding the good ones.
 * A rejection propagates like `Promise.all`'s: already-started calls run to
 * completion, and no further items are started.
 *
 * @param items - The input list. Not mutated.
 * @param limit - Maximum calls in flight. Must be a positive integer.
 * @param worker - Called once per item with the item and its index.
 * @returns Results positionally aligned with `items`.
 */
export async function mapWithConcurrency<TIn, TOut>(
  items: readonly TIn[],
  limit: number,
  worker: (item: TIn, index: number) => Promise<TOut>,
): Promise<TOut[]> {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new RangeError(`mapWithConcurrency: limit must be a positive integer, received ${limit}`);
  }

  const results = new Array<TOut>(items.length);
  // The shared cursor is what makes this a queue rather than a set of fixed
  // slices: a slow item holds up its own lane and nothing else, so N short
  // reads behind one long one still finish promptly.
  let cursor = 0;

  const lane = async (): Promise<void> => {
    for (;;) {
      const index = cursor;
      cursor += 1;
      if (index >= items.length) return;
      results[index] = await worker(items[index], index);
    }
  };

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => lane()));
  return results;
}
