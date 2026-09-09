/**
 * Derives the principal key used to scope the frontend query cache
 * (see `src/lib/queryClient.ts` for the cache-key shapes and the identity
 * seam that must be driven whenever this key changes).
 *
 * Identity itself is resolved by `src/lib/session.ts`, which is the one
 * caller of `fetchMe()`; this module only turns that answer into a cache
 * key.
 *
 * This is the "impure edge" of the caching lane: unlike `queryClient.ts` it
 * is Vite-only (`import.meta.env`) and browser-only (`sessionStorage`,
 * `crypto.subtle`), so it is never imported from the plain-Node test file.
 *
 * Preference order:
 *  1. The signed-in principal's `user_id` -- the real, server-derived
 *     identity, from `loadSession()`.
 *  2. A SHA-256 hash of the active bearer token, when a token is
 *     configured but `/v1/me` refused it or could not be reached. The
 *     cache still needs a stable per-credential key in that case; the
 *     UI, by contrast, treats the same state as signed out.
 *  3. `null`, when neither is available (no token configured at all).
 *
 * The returned string is always prefixed with its provenance
 * (`user:` vs `token:`) so a reader of a cache key can never mistake a
 * token-derived fallback key for a real server-assigned user id.
 *
 * This function never throws: a signed-out session is treated as
 * "no server identity available" and falls through to the token-based
 * fallback (or `null`). Note that falling from a `user:...` key to a
 * `token:...` key (or vice versa) still changes the key's contents, so
 * `PrincipalIdentityTracker.apply` will correctly detect this as an
 * identity change and clear the cache -- no special-casing of "fetchMe
 * failed" is needed here beyond returning an honest, differently-prefixed
 * key.
 *
 * The token itself is NEVER logged, and neither the token nor the derived
 * key is ever written to any storage (sessionStorage, localStorage, etc.) --
 * the derived key exists only in memory for the lifetime of the identity
 * seam's tracked state.
 */
import { readSmartmatchBearerToken } from "@/lib/api";
import { loadSession } from "@/lib/session";

/** Hex-encodes a SHA-256 digest of `value` via the Web Crypto API. */
async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Resolves the current principal key for cache scoping. See module docs for
 * the preference order and the "never throws" guarantee.
 */
export async function resolvePrincipalKey(): Promise<string | null> {
  // `loadSession()` memoizes the one `GET /v1/me` this page load makes, so
  // asking here costs no extra request: `useSession()` shares the answer.
  // It never throws -- an unavailable or unauthenticated /v1/me resolves to
  // a signed-out snapshot and falls through to the token-based key below.
  const session = await loadSession();
  if (session.status === "signed-in" && session.me.user_id.length > 0) {
    return `user:${session.me.user_id}`;
  }

  const token = readSmartmatchBearerToken();
  if (!token) {
    return null;
  }

  const hash = await sha256Hex(token);
  return `token:${hash}`;
}
