/**
 * Principal-scoped reads over the shared TanStack Query cache — the common
 * case of "this page needs `GET /v1/...` for the unit the server granted".
 *
 * This is the general form of what `useUnitMetrics.ts` does by hand: resolve
 * the principal key (`PrincipalQueryProvider`), put it in the first segment
 * of the query key so two principals can never collide, and keep the query
 * `enabled: false` until the key is known so nothing is ever cached under a
 * fake identity (the provider's "do not enable principal-scoped queries until
 * a key is known" rule).
 *
 * ## What the cache buys
 *
 * `createAppQueryClient` sets `staleTime: 30_000`, so navigating away and
 * back inside that window renders the cached answer immediately while a
 * background refetch keeps it honest — the R4 stale-while-revalidate
 * behaviour the cache lane was built for. Before this hook, every page ran
 * its own `useEffect` + `fetch` with no cache, so every route change paid a
 * full network round trip (and pages like `CoordinatorHome` paid it as a
 * sequential waterfall).
 *
 * ## Failure semantics are unchanged
 *
 * Pages that used `Promise.allSettled` or per-read try/catch keep exactly
 * that behaviour: each `useScopedQuery` call is an independent query that
 * fails independently, and {@link queryToLoaded} maps the result onto the
 * `{ data, error, settled }` shape the pages already render — including the
 * rule that a failed read reports the server's own words and never
 * substitutes an empty list or a fabricated value (ADR-0011).
 *
 * ## What does not belong here
 *
 * Mutations (`useMutation`), detail reads opened by a click, and job-status
 * polling are not page-load reads; they keep their existing call sites. This
 * hook is for the read a page makes because it mounted.
 */
import {
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiRequestError } from "@/lib/api";
import { scopedQueryKey } from "@/lib/queryClient";
import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";

/**
 * Placeholder first key segment used only while the principal is still
 * resolving. The query is `enabled: false` for the entire time this
 * placeholder would be part of the key, so it never populates the cache
 * under a fake identity — same rule `useUnitMetrics` documents.
 */
const UNRESOLVED_PRINCIPAL = "unresolved-principal";

export interface ScopedQuerySpec<TData> {
  /**
   * The resource segment of the cache key — the route's own name for what it
   * reads, e.g. `"speaker-requests"`, `"review-items"`. Pages reading the
   * same route with the same params share one cache entry, which is what
   * lets the portal shell's badge counts pre-warm the page behind the link.
   */
  readonly resource: string;
  /** Extra key segments after the resource — unit id, status filter, etc. */
  readonly params?: readonly unknown[];
  readonly queryFn: () => Promise<TData>;
  /**
   * Caller-side gating on top of the principal check — typically
   * `unitId !== null`. The query never runs while the principal key is
   * unresolved, whatever this says.
   */
  readonly enabled?: boolean;
}

/**
 * One principal-scoped, cached read. Returns the stock `UseQueryResult` so
 * callers keep `refetch`, `isPending`, `isError`, and friends.
 */
export function useScopedQuery<TData>(
  spec: ScopedQuerySpec<TData>,
): UseQueryResult<TData> {
  const principalKey = usePrincipalKey();
  return useQuery({
    queryKey: scopedQueryKey(
      principalKey ?? UNRESOLVED_PRINCIPAL,
      spec.resource,
      ...(spec.params ?? []),
    ),
    queryFn: spec.queryFn,
    enabled: principalKey !== null && spec.enabled !== false,
  });
}

/**
 * What one read returned, or why it returned nothing — the shape the portal
 * pages already render. Kept beside the data rather than in a page-level
 * banner because reads fail independently: a refusal on one route says
 * nothing about another, and one banner over all of them would misreport
 * which capability the server actually withheld.
 */
export type Loaded<T> = { data: T | null; error: string | null; settled: boolean };

/** The not-yet-asked / still-in-flight value. */
export const PENDING: Loaded<never> = { data: null, error: null, settled: false };

/**
 * The server's own words where it gave any. `ApiRequestError.message` carries
 * the API's error text, including the refusal a `403` explains, and a
 * rephrasing here would be this page's opinion about someone else's decision.
 */
export function describeFailure(cause: unknown, subject: string): string {
  return cause instanceof ApiRequestError
    ? cause.message
    : `${subject} could not be read and the server gave no reason.`;
}

/**
 * Maps a scoped query onto the `Loaded` shape a page renders.
 *
 * `settled` follows `isPending` rather than `isFetched`: a query that is
 * `enabled: false` because the unit is still resolving has never been asked,
 * and reporting it as settled would let a page draw "nothing here" over a
 * read that has not happened yet.
 */
export function queryToLoaded<T>(
  query: UseQueryResult<T>,
  subject: string,
): Loaded<T> {
  if (query.isPending) {
    return { data: null, error: null, settled: false };
  }
  if (query.isError) {
    return { data: null, error: describeFailure(query.error, subject), settled: true };
  }
  return { data: query.data, error: null, settled: true };
}
