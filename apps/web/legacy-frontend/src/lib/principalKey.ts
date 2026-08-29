/**
 * Derives the principal key used to scope the frontend query cache
 * (see `src/lib/queryClient.ts` for the cache-key shapes and the identity
 * seam that must be driven whenever this key changes).
 *
 * This is the "impure edge" of the caching lane: unlike `queryClient.ts` it
 * is Vite-only (`import.meta.env`) and browser-only (`sessionStorage`,
 * `crypto.subtle`), so it is never imported from the plain-Node test file.
 *
 * Preference order:
 *  1. `fetchMe()`'s `user_id` -- the real, server-derived identity.
 *  2. A SHA-256 hash of the active bearer token, when `/v1/me` is
 *     unavailable (no session backend yet -- plan P2 has not landed).
 *  3. `null`, when neither is available (no token configured at all).
 *
 * The returned string is always prefixed with its provenance
 * (`user:` vs `token:`) so a reader of a cache key can never mistake a
 * token-derived fallback key for a real server-assigned user id.
 *
 * This function never throws: any failure from `fetchMe()` is treated as
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
import { fetchMe } from "@/lib/api";

/**
 * Reads the active bearer token exactly the way `src/lib/api.ts`'s
 * (private, unexported) `smartmatchAuthHeaders()` does.
 *
 * DELIBERATE DUPLICATION: `api.ts` is outside this lane's fence and does not
 * export the raw token, only derived auth headers / a boolean
 * (`hasSmartmatchAuth()`). This re-implements that same env-then-session-
 * storage lookup so the cache can derive a stable fallback key without
 * modifying `api.ts`. MUST be kept in sync with `smartmatchAuthHeaders()` in
 * `src/lib/api.ts` if that lookup ever changes, and is expected to be
 * DELETED once plan P2 (cards A1b/A2) lands a real session and this
 * fallback path is no longer needed.
 */
function readActiveBearerToken(): string | null {
  const envToken = import.meta.env.VITE_SMARTMATCH_BEARER_TOKEN;
  const sessionToken =
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem("smartmatch_bearer_token")
      : null;

  const token =
    (typeof envToken === "string" && envToken.trim().length > 0 ? envToken.trim() : null) ??
    (typeof sessionToken === "string" && sessionToken.trim().length > 0
      ? sessionToken.trim()
      : null);

  return token;
}

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
  try {
    const me = await fetchMe();
    if (me && typeof me.user_id === "string" && me.user_id.length > 0) {
      return `user:${me.user_id}`;
    }
  } catch {
    // /v1/me unavailable or unauthenticated -- fall through to the
    // token-based fallback below. Never log the error here: it may embed
    // request details we don't want captured incidentally.
  }

  const token = readActiveBearerToken();
  if (!token) {
    return null;
  }

  const hash = await sha256Hex(token);
  return `token:${hash}`;
}
