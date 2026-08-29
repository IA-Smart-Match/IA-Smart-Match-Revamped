/**
 * Wires the frontend query cache (`src/lib/queryClient.ts`) into the React
 * tree and drives its identity seam.
 *
 * On mount this resolves the active principal (`src/lib/principalKey.ts`,
 * which calls `fetchMe()`) and applies it through
 * `PrincipalIdentityTracker.apply`, which clears the whole query cache
 * whenever the observed key differs from the one currently in effect --
 * including the very first resolution (`null -> key`) and any failure
 * (treated as `null`). Plan P2 card A2 will call the same tracker from the
 * sign-in/out flow once a real session exists; this provider only covers
 * the "resolve on load" path for now.
 *
 * IMPORTANT (R2 -- first paint must never block): the `QueryClient` is
 * created synchronously and `<QueryClientProvider>` renders `children`
 * immediately. Principal resolution happens in a `useEffect` and never
 * gates the render. Consumers must not enable principal-scoped queries
 * until `usePrincipalKey()` returns a non-null key -- see
 * `useUnitMetrics.ts`, which does exactly that -- so a component can never
 * serve another principal's cached data while resolution is still in
 * flight; it simply has nothing to show yet.
 */
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { QueryClientProvider } from "@tanstack/react-query";

import { createAppQueryClient, createPrincipalIdentity } from "@/lib/queryClient";
import { resolvePrincipalKey } from "@/lib/principalKey";

const PrincipalKeyContext = createContext<string | null>(null);

/**
 * The resolved principal key for the current session, or `null` while
 * resolution is still in flight (or if it failed / no identity is
 * available). Consumers MUST treat `null` as "not yet safe to enable
 * principal-scoped queries," not as an error state to render.
 */
export function usePrincipalKey(): string | null {
  return useContext(PrincipalKeyContext);
}

export function PrincipalQueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => createAppQueryClient());
  const identityRef = useRef(createPrincipalIdentity());
  const [principalKey, setPrincipalKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    resolvePrincipalKey()
      .then((key) => {
        if (cancelled) {
          return;
        }
        identityRef.current.apply(client, key);
        setPrincipalKey(key);
      })
      .catch(() => {
        // resolvePrincipalKey() is documented to never throw, but guard
        // defensively: total resolution failure is treated exactly like a
        // `fetchMe()` failure with no fallback token -- no known principal,
        // clear whatever may already be cached rather than guess.
        if (cancelled) {
          return;
        }
        identityRef.current.apply(client, null);
        setPrincipalKey(null);
      });

    return () => {
      cancelled = true;
    };
    // Intentionally re-runs only when `client` changes (never, in practice,
    // since it is created once via useState's lazy initializer). Re-running
    // per render would repeatedly re-resolve identity for no reason.
  }, [client]);

  return (
    <QueryClientProvider client={client}>
      <PrincipalKeyContext.Provider value={principalKey}>
        {children}
      </PrincipalKeyContext.Provider>
    </QueryClientProvider>
  );
}
