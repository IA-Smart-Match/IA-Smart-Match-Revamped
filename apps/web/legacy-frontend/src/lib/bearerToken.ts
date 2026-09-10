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
 * There is one thing that outranks both: an **explicit sign-out**. Clearing
 * `sessionStorage` used to leave the fixture as the only remaining source, so
 * the very next `/v1/me` succeeded again — as the fixture's coordinator. A
 * student who signed out of `/student-portal` was handed the coordinator
 * portal, which is a privilege escalation performed by the sign-out button.
 * The fixture is the default for a visitor who *has not asked for anything*,
 * and someone who has just asked to be signed out has asked for something.
 * So `signedOutDeliberately` suppresses it, and only it — a stored credential
 * still wins, because signing back in both writes one and clears the marker.
 *
 * Split out of `lib/api.ts` so it is a pure function of its inputs and can be
 * tested without `import.meta.env` or `sessionStorage`
 * (`tests/bearerToken.test.ts`). `api.ts` reads the sources; this decides
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
 * The token to send, or `null` when no usable source holds one.
 *
 * @param envToken The build-time `VITE_SMARTMATCH_BEARER_TOKEN`, if any.
 * @param sessionToken The token sign-in stored in this tab, if any.
 * @param signedOutDeliberately Whether this browser has explicitly signed out
 *   since it last signed in. When it has, the build-time fixture is not used:
 *   an explicit sign-out must not be undone by a token baked into the bundle.
 */
export function resolveBearerToken(
  envToken: string | null | undefined,
  sessionToken: string | null | undefined,
  signedOutDeliberately = false,
): string | null {
  const stored = usableCredential(sessionToken);
  if (stored) {
    return stored;
  }
  return signedOutDeliberately ? null : usableCredential(envToken);
}
