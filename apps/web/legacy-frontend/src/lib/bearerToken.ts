/**
 * Which of the two credential sources `/v1` requests are sent with.
 *
 * There are exactly two places a bearer token can come from, and they are not
 * peers:
 *
 * * `sessionStorage["smartmatch_bearer_token"]` — a token `POST /v1/auth/login`
 *   issued because a person typed their own credentials into `/login`;
 * * the build-time `VITE_SMARTMATCH_BEARER_TOKEN` — a fixture baked into a
 *   compose/dev bundle so the appliance can be opened without signing in.
 *
 * The stored one wins. It is the credential this browser was *asked* to use;
 * the fixture is the default for a visitor who has not asked for anything.
 * Reversing that is not a stylistic difference — the pilot appliance builds the
 * bundle with `VITE_SMARTMATCH_BEARER_TOKEN=compose-api`, which the API maps to
 * the seeded **coordinator**, so a fixture-first order made every `/v1` call
 * authenticate as the coordinator no matter who had just signed in. `GET
 * /v1/me/portals` then honestly answered "coordinator" for a student, a host,
 * and an administrator alike, and `pages/Home.tsx` honestly forwarded all three
 * to `/coordinator-portal`. The sign-in appeared to succeed and changed nothing.
 *
 * Both values are *credentials* and neither is an identity: this function picks
 * which opaque string to send, and the server alone decides whose it is. That
 * is why the choice can live here at all — no role, tenant, or unit is being
 * decided in the browser, only which of two tokens to present.
 *
 * Split out of `lib/api.ts` so it is a pure function of its two inputs and can
 * be tested without `import.meta.env` or `sessionStorage`
 * (`tests/bearerToken.test.ts`). `api.ts` reads the two sources; this decides
 * between them.
 */

/** A source's value, or `null` when it holds nothing usable. */
function usableCredential(value: string | null | undefined): string | null {
  // Non-strings are dropped rather than stringified: `import.meta.env` and
  // `sessionStorage` are both untyped at runtime, and a coerced `[object
  // Object]` would be sent as an `Authorization` header.
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

/**
 * The token to send, or `null` when neither source holds one.
 *
 * @param envToken The build-time `VITE_SMARTMATCH_BEARER_TOKEN`, if any.
 * @param sessionToken The token sign-in stored in this tab, if any.
 */
export function resolveBearerToken(
  envToken: string | null | undefined,
  sessionToken: string | null | undefined,
): string | null {
  return usableCredential(sessionToken) ?? usableCredential(envToken);
}
