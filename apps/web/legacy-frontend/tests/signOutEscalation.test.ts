/**
 * Regression test: **signing out must not escalate privileges.**
 *
 * Reproduced defect, on `main`: sign in as a student, open `/student-portal`,
 * press "Sign out". `POST /v1/auth/logout` returned 200 and `sessionStorage`
 * was cleared — and the app then landed on `/coordinator-portal` as the
 * seeded coordinator, with the full coordinator navigation. Nobody had
 * signed in as a coordinator. The compose bundle is built with
 * `VITE_SMARTMATCH_BEARER_TOKEN=compose-api`, the API maps that fixture to
 * the coordinator, and with the stored credential gone the fixture was the
 * only credential left — so the next `GET /v1/me` honestly answered
 * "coordinator" and the sign-out button became a privilege escalation.
 *
 * The seam is `resolveBearerToken()`: which credential a `/v1` request is
 * sent with. This test drives the real sequence — fixture build, sign in,
 * sign out, reload — through the real functions, passing a `sessionStorage`
 * double so no DOM is needed (`lib/signOutMarker.ts` takes its storage as an
 * argument for exactly this reason).
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { resolveBearerToken } from "../src/lib/bearerToken.ts";
import {
  clearSignedOut,
  hasSignedOut,
  markSignedOut,
  type MarkerStorage,
} from "../src/lib/signOutMarker.ts";

/** The fixture token a compose/dev bundle is built with. */
const FIXTURE_TOKEN = "compose-api";

/** A `sessionStorage` stand-in, holding only what the browser would hold. */
function fakeStorage(): MarkerStorage & { readonly keys: () => string[] } {
  const entries = new Map<string, string>();
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => {
      entries.set(key, value);
    },
    removeItem: (key) => {
      entries.delete(key);
    },
    keys: () => [...entries.keys()],
  };
}

/**
 * The browser's credential for the next `/v1` request, assembled exactly as
 * `readSmartmatchBearerToken()` in `lib/api.ts` assembles it.
 */
function credentialForNextRequest(
  storage: MarkerStorage,
  storedToken: string | null,
): string | null {
  return resolveBearerToken(FIXTURE_TOKEN, storedToken, hasSignedOut(storage));
}

test("signing out of a fixture build leaves NO credential, so the fixture principal cannot take over", () => {
  const storage = fakeStorage();

  // 1. A student signs in: `POST /v1/auth/login` issues a session token,
  //    `storeSmartmatchBearerToken()` stores it and clears any sign-out mark.
  let storedToken: string | null = "student-session-token";
  clearSignedOut(storage);
  assert.equal(credentialForNextRequest(storage, storedToken), "student-session-token");

  // 2. They press "Sign out": the session is revoked server-side, the stored
  //    token is dropped, and the deliberate sign-out is recorded.
  storedToken = null;
  markSignedOut(storage);

  // 3. The next `/v1` request — and every one after a reload — must carry no
  //    credential at all. Before the fix this was `"compose-api"`, which the
  //    API resolves to the seeded coordinator: `GET /v1/me` answered
  //    "coordinator", `GET /v1/me/portals` agreed, and `pages/Home.tsx`
  //    forwarded the signed-out student to `/coordinator-portal`.
  assert.equal(
    credentialForNextRequest(storage, storedToken),
    null,
    "an explicit sign-out must not be undone by the build-time fixture token",
  );
});

test("the sign-out mark survives a reload and is only undone by signing in again", () => {
  const storage = fakeStorage();

  markSignedOut(storage);
  // A reload re-reads the same `sessionStorage`; nothing in between clears it.
  assert.equal(hasSignedOut(storage), true);
  assert.equal(credentialForNextRequest(storage, null), null);

  // Signing in again is the one thing that supersedes it.
  clearSignedOut(storage);
  assert.equal(hasSignedOut(storage), false);
  assert.equal(credentialForNextRequest(storage, "second-session-token"), "second-session-token");

  // ...and the fixture convenience is back for a browser that has not asked
  // for anything, which is the only case it exists for.
  assert.equal(credentialForNextRequest(storage, null), FIXTURE_TOKEN);
});

test("a fresh tab that has never signed in still gets the fixture token", () => {
  // The developer convenience this fixture exists for: open the compose
  // appliance, never visit `/login`. A tab with empty storage has asked for
  // nothing, so nothing is suppressed.
  const storage = fakeStorage();
  assert.equal(hasSignedOut(storage), false);
  assert.equal(credentialForNextRequest(storage, null), FIXTURE_TOKEN);
});

test("a signed-out browser holds a mark and no credential — never a credential under another key", () => {
  const storage = fakeStorage();
  markSignedOut(storage);
  // The marker is a flag, not a credential: it must never be mistaken for one.
  assert.deepEqual(storage.keys(), ["smartmatch_signed_out"]);
  assert.equal(storage.getItem("smartmatch_bearer_token"), null);
});
