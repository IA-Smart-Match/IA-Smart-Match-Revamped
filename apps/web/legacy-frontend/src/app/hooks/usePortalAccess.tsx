/**
 * React access to the account-to-portal mapping: `GET /v1/me/portals`.
 *
 * The companion to `useSession()`. That hook answers "who is this", from
 * `/v1/me`; this one answers "which portals did the server grant them", from
 * `/v1/me/portals`. Both answers come from the server and neither is derived
 * in the browser — which is the whole reason this is a second request rather
 * than a function over `me.memberships`. See `lib/principal.ts`'s
 * `portalGrant()` for why a local re-derivation of the role-to-portal rule is
 * the wrong shape even when it would agree.
 *
 * Mount `<PortalAccessProvider>` inside `<SessionProvider>` (see
 * `src/app/App.tsx`). It fetches once per signed-in principal and holds the
 * result for the page load, so the three shells and every page inside them
 * share one request.
 *
 * There is deliberately no way to *set* a grant from here, exactly as there is
 * no way to set an identity in `useSession`. A component cannot put itself
 * into a portal the server did not list.
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

import { ApiRequestError, fetchMyPortals, type MyPortalsResponse } from "@/lib/api";

import { useSession } from "./useSession";

/**
 * Why the mapping is not available.
 *
 * `signed-out`: there is no session to ask about. Not an error — the shells
 *   render `SessionGate` for this long before they look at a portal grant.
 * `unreachable`: `/v1/me/portals` could not be reached or did not answer with
 *   a mapping. An outage, not a statement about this account, so it is offered
 *   a retry rather than turned into "you have no portals" — which would be the
 *   browser inventing a denial the server never made.
 */
export type PortalAccessProblem = "signed-out" | "unreachable";

export type PortalAccessState =
  | { status: "loading" }
  | { status: "ready"; mapping: MyPortalsResponse }
  | { status: "unavailable"; problem: PortalAccessProblem };

interface PortalAccessContextValue {
  readonly state: PortalAccessState;
  /** Re-asks `GET /v1/me/portals` with the same credential. */
  readonly retry: () => void;
}

const PortalAccessContext = createContext<PortalAccessContextValue | null>(null);

/**
 * Whether a `/v1/me/portals` body is actually a mapping.
 *
 * `fetchMyPortals()` asserts its response type rather than parsing it, so a
 * proxy error page would otherwise reach the shells as a `MyPortalsResponse`
 * and crash them on first property access. A body that is not a mapping is
 * treated as no answer at all — the same thing this module does with every
 * other failure.
 */
function isMapping(payload: MyPortalsResponse | undefined): payload is MyPortalsResponse {
  return !!payload && Array.isArray(payload.portals);
}

export function PortalAccessProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const [state, setState] = useState<PortalAccessState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  const principalId = session.status === "signed-in" ? session.me.user_id : null;

  useEffect(() => {
    if (session.status === "loading") {
      setState({ status: "loading" });
      return;
    }
    if (session.status !== "signed-in") {
      // No credential, so there is nothing to ask about. Reported rather than
      // left in `loading`, which would spin forever behind a sign-in screen.
      setState({ status: "unavailable", problem: "signed-out" });
      return;
    }

    let cancelled = false;
    setState({ status: "loading" });

    fetchMyPortals()
      .then((mapping) => {
        if (cancelled) return;
        setState(
          isMapping(mapping)
            ? { status: "ready", mapping }
            : { status: "unavailable", problem: "unreachable" },
        );
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // A 401/403 here means the credential stopped working between `/v1/me`
        // and this call. That is a session problem, not a portal one, and
        // `useSession` owns it — so this reports the honest "could not ask"
        // rather than manufacturing an empty grant list, which would look
        // exactly like a real denial.
        const problem: PortalAccessProblem =
          error instanceof ApiRequestError && (error.status === 401 || error.status === 403)
            ? "signed-out"
            : "unreachable";
        setState({ status: "unavailable", problem });
      });

    return () => {
      cancelled = true;
    };
    // The session's status and the principal's own id are what make this
    // answer stale; depending on the whole session object would refetch on
    // every unrelated re-render.
  }, [session.status, principalId, attempt]);

  const value = useMemo<PortalAccessContextValue>(() => ({ state, retry }), [state, retry]);

  return <PortalAccessContext.Provider value={value}>{children}</PortalAccessContext.Provider>;
}

function usePortalAccessContext(): PortalAccessContextValue {
  const value = useContext(PortalAccessContext);
  if (!value) {
    throw new Error("usePortalAccess must be used inside <PortalAccessProvider>.");
  }
  return value;
}

/** The current account-to-portal mapping state. */
export function usePortalAccess(): PortalAccessState {
  return usePortalAccessContext().state;
}

/** Re-asks the server, for the one unavailable state that may be temporary. */
export function useRetryPortalAccess(): () => void {
  return usePortalAccessContext().retry;
}
