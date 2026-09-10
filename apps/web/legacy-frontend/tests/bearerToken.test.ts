import { test } from "node:test";
import assert from "node:assert/strict";

import { resolveBearerToken } from "../src/lib/bearerToken.ts";

test("a signed-in credential wins over the build-time fixture token", () => {
  // The pilot appliance bakes `VITE_SMARTMATCH_BEARER_TOKEN=compose-api` into
  // the bundle, and that token maps to the seeded *coordinator*. When someone
  // signs in as a student, `POST /v1/auth/login` issues a session token into
  // `sessionStorage`; if the fixture kept winning, every `/v1` call — `GET
  // /v1/me` and `GET /v1/me/portals` included — would still authenticate as
  // the coordinator, and every principal would land in the coordinator portal.
  assert.equal(
    resolveBearerToken("compose-api", "issued-session-token"),
    "issued-session-token",
  );
});

test("the fixture token is the fallback when nobody has signed in", () => {
  // Removing this would break the documented compose walkthrough, where the
  // browser carries a fixture credential and never visits `/login` at all.
  assert.equal(resolveBearerToken("compose-api", null), "compose-api");
  assert.equal(resolveBearerToken("compose-api", "   "), "compose-api");
});

test("a stored credential is used when no fixture was built in", () => {
  assert.equal(
    resolveBearerToken(undefined, "issued-session-token"),
    "issued-session-token",
  );
  assert.equal(
    resolveBearerToken("", "issued-session-token"),
    "issued-session-token",
  );
});

test("both sources are trimmed, and neither is invented", () => {
  assert.equal(resolveBearerToken("  compose-api  ", null), "compose-api");
  assert.equal(resolveBearerToken(null, "  issued  "), "issued");
  assert.equal(resolveBearerToken(null, null), null);
  assert.equal(resolveBearerToken("   ", "   "), null);
});

test("a non-string from either source is not coerced into a credential", () => {
  assert.equal(resolveBearerToken(42 as unknown as string, null), null);
  assert.equal(resolveBearerToken(null, {} as unknown as string), null);
});
