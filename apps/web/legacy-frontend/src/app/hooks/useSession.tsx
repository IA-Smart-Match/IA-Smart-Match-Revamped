/**
 * React access to the one authenticated identity the browser has:
 * `GET /v1/me`, resolved once per page load by `src/lib/session.ts`.
 *
 * Mount `<SessionProvider>` above the router (see `src/app/App.tsx`). Layouts
 * gate on `useSession()`; pages rendered inside a gated layout take the
 * resolved principal from `useAuthenticatedPrincipal()`.
 *
 * There is deliberately no way to *set* an identity from here. The provider
 * reads the server's answer and nothing else, so no component can put a
 * person into a signed-in state the API has not agreed to.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { MeResponse } from "@/lib/api";
import {
  loadSession,
  resetSession,
  signOutOfSession,
  type SessionSnapshot,
} from "@/lib/session";

/** `loading` covers the `/v1/me` round trip; it is never a signed-in state. */
export type SessionState = { status: "loading" } | SessionSnapshot;

interface SessionContextValue {
  readonly state: SessionState;
  /** Drops the browser-held token and re-resolves against the server. */
  readonly signOut: () => void;
  /** Re-asks `GET /v1/me` with the same credential. */
  readonly retry: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    loadSession().then((snapshot) => {
      if (!cancelled) {
        setState(snapshot);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Not driven from here: `PrincipalIdentityTracker` (see
  // `components/PrincipalQueryProvider.tsx`), which clears the query cache on
  // an identity change. Sign-out leaves whatever it already holds in memory
  // until the next page load. Nothing in the UI can put a *different*
  // principal's token in place — there is no token writer — so no cached data
  // can be served to another principal; card A2 wires the tracker to the real
  // sign-in/out flow when one exists.
  const signOut = useCallback(() => {
    const { stillAuthenticated } = signOutOfSession();
    if (!stillAuthenticated) {
      setState({ status: "signed-out", reason: "no-token" });
      return;
    }
    // The bundle was built with VITE_SMARTMATCH_BEARER_TOKEN, so clearing
    // sessionStorage revoked nothing. Ask the server again rather than
    // showing a signed-out screen it would contradict.
    setState({ status: "loading" });
    loadSession().then(setState);
  }, []);

  const retry = useCallback(() => {
    resetSession();
    setState({ status: "loading" });
    loadSession().then(setState);
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({ state, signOut, retry }),
    [state, signOut, retry],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

function useSessionContext(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used inside <SessionProvider>.");
  }
  return value;
}

/** The current session state. `loading` and `signed-out` are not sessions. */
export function useSession(): SessionState {
  return useSessionContext().state;
}

/** Signs out: clears the browser-held token and re-resolves identity. */
export function useSignOut(): () => void {
  return useSessionContext().signOut;
}

/** Re-asks the server, for the one signed-out state that may be temporary. */
export function useRetrySession(): () => void {
  return useSessionContext().retry;
}

/**
 * The signed-in principal, for components that only ever render inside a
 * gated layout (`<PortalSessionGate>`).
 *
 * Throws rather than returning a placeholder if that invariant is broken:
 * a page that cannot name its principal must fail loudly, not fall back to
 * a fixture identity.
 */
export function useAuthenticatedPrincipal(): MeResponse {
  const state = useSessionContext().state;
  if (state.status !== "signed-in") {
    throw new Error(
      "useAuthenticatedPrincipal() requires a signed-in session; render this " +
        "component inside a <PortalSessionGate>.",
    );
  }
  return state.me;
}
