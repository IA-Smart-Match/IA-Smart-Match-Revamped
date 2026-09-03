/**
 * The browser's one source of authenticated identity: `GET /v1/me`.
 *
 * Fix #7 archived the pattern this replaces: a browser-written session blob
 * read back out of `sessionStorage`, with a hard-coded fallback id per portal
 * whenever it was absent — which it always was, since nothing ever wrote it.
 * That made every visitor, verified or not, look signed in as a fixture
 * person. `tests/unit/test_frontend_auth_contract.py` holds the exact key and
 * literals so they cannot come back; they are deliberately not repeated here.
 *
 * What is left is a credential and a server answer:
 *
 *  - the credential is a bearer token (`readSmartmatchBearerToken()` in
 *    `src/lib/api.ts`) — a build-time `VITE_SMARTMATCH_BEARER_TOKEN`, or one
 *    the browser holds in `sessionStorage`;
 *  - the answer is whatever `GET /v1/me` returns for it: user id, tenant,
 *    email, and server-assigned memberships.
 *
 * Nothing in this module derives identity from anything else. No token means
 * signed out. A token the API rejects means signed out. There is no third
 * path and no fallback principal, so a visitor without a verified token can
 * never be shown as signed in.
 *
 * The `/v1/me` call is memoized per page load so the several consumers
 * (`useSession()`, the query cache's principal key) share one request. The
 * memo is dropped by `resetSession()` — see `signOut()` in
 * `src/app/hooks/useSession.tsx`.
 */
import {
  ApiRequestError,
  clearStoredSmartmatchBearerToken,
  fetchMe,
  hasSmartmatchAuth,
  type MeResponse,
} from "@/lib/api";

/**
 * Why the browser has no verified identity.
 *
 * `no-token`: no bearer token is configured at all.
 * `rejected`: the API refused the token (401/403) — it is not a session.
 * `suspended`: the token resolves, but an administrator has suspended the
 *   account. `/v1/me` admits a suspended caller on purpose, precisely so it
 *   can learn this (`services/api/smartmatch_api/routers/me.py`); every other
 *   authorized route denies it with `principal_suspended`. Rendering a working
 *   portal around it would be the browser claiming an access the server has
 *   already withdrawn.
 * `unreachable`: `/v1/me` could not be reached, or answered with something
 *   that is not a principal.
 *
 * None of them is a session. They are distinguished only so the UI can say
 * something truthful about *why*, never to soften any of them into a partial
 * one.
 */
export type SignedOutReason = "no-token" | "rejected" | "suspended" | "unreachable";

export type SessionSnapshot =
  | { status: "signed-in"; me: MeResponse }
  | { status: "signed-out"; reason: SignedOutReason };

let pending: Promise<SessionSnapshot> | null = null;

/**
 * Whether a `/v1/me` body is actually a principal.
 *
 * `fetchMe()` asserts its response type rather than parsing it, so a proxy
 * error page or a shape change would otherwise reach the layouts as a
 * `MeResponse` and crash them on first property access. A body that is not a
 * principal is treated as no identity at all, which is the same answer the
 * rest of this module gives to every other failure.
 */
function isPrincipal(payload: MeResponse | undefined): payload is MeResponse {
  return (
    !!payload &&
    typeof payload.user_id === "string" &&
    payload.user_id.length > 0 &&
    typeof payload.tenant_id === "string" &&
    typeof payload.email === "string" &&
    typeof payload.suspended === "boolean" &&
    Array.isArray(payload.memberships)
  );
}

async function probe(): Promise<SessionSnapshot> {
  if (!hasSmartmatchAuth()) {
    return { status: "signed-out", reason: "no-token" };
  }

  try {
    const me = await fetchMe();
    if (!isPrincipal(me)) {
      return { status: "signed-out", reason: "unreachable" };
    }
    if (me.suspended) {
      return { status: "signed-out", reason: "suspended" };
    }
    return { status: "signed-in", me };
  } catch (error) {
    if (error instanceof ApiRequestError && (error.status === 401 || error.status === 403)) {
      return { status: "signed-out", reason: "rejected" };
    }
    return { status: "signed-out", reason: "unreachable" };
  }
}

/**
 * Resolves the current session, reusing the in-flight or completed `/v1/me`
 * call from this page load. Never throws: every failure resolves to a
 * `signed-out` snapshot.
 *
 * An `unreachable` answer is deliberately NOT memoized. It is a statement
 * about the network at one moment, not about who the caller is, and caching
 * it would strand the whole page on a transient outage until a full browser
 * reload. Every other outcome — including a rejected token — is a real answer
 * about this credential and is cached for the page load.
 */
export function loadSession(): Promise<SessionSnapshot> {
  pending ??= probe().then((snapshot) => {
    if (snapshot.status === "signed-out" && snapshot.reason === "unreachable") {
      pending = null;
    }
    return snapshot;
  });
  return pending;
}

/** Forgets the memoized `/v1/me` answer so the next `loadSession()` re-asks. */
export function resetSession(): void {
  pending = null;
}

/**
 * Signs out: drops the browser-held bearer token and forgets the cached
 * `/v1/me` answer.
 *
 * Returns whether the browser can still authenticate afterwards. That is
 * `true` when the running bundle was built with `VITE_SMARTMATCH_BEARER_TOKEN`
 * — a compose/dev fixture build holds its token in the bundle, so sign-out
 * cannot revoke it and the next `/v1/me` will succeed again. Callers show
 * that outcome rather than a signed-out screen the server would disagree
 * with.
 */
export function signOutOfSession(): { stillAuthenticated: boolean } {
  clearStoredSmartmatchBearerToken();
  resetSession();
  return { stillAuthenticated: hasSmartmatchAuth() };
}
