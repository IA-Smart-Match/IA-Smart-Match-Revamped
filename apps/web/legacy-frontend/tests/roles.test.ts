/**
 * `hasActiveRole` answers "does this person hold this role *now*".
 *
 * The reason it exists is the CBA merge: `coordinator` and `admin` open one
 * shell, so `GET /v1/me/portals` can no longer tell them apart and the
 * Administration section has to be revealed from `GET /v1/me`'s membership
 * rows instead. What these tests pin is the two ways that could quietly go
 * wrong — an expired grant still reading as held, and an unloaded identity
 * reading as permissive — because both fail *open*, and a menu that fails
 * open is only visibly wrong once somebody clicks it and gets a 403.
 *
 * Runs under `node --test tests/`, importing the module by relative path.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { hasActiveRole } from "../src/lib/roles.ts";
import type { MeResponse, MembershipResponse } from "../src/lib/api.ts";

function membership(overrides: Partial<MembershipResponse> = {}): MembershipResponse {
  return {
    org_unit_path: "pilot",
    role: "coordinator",
    valid_from: null,
    valid_until: null,
    is_active: true,
    ...overrides,
  };
}

function me(memberships: MembershipResponse[]): MeResponse {
  return {
    user_id: "00000000-0000-4000-8000-000000000001",
    tenant_id: "00000000-0000-4000-8000-000000000002",
    email: "connector@example.invalid",
    suspended: false,
    memberships,
  };
}

test("a held, in-force role is reported", () => {
  const identity = me([membership({ role: "coordinator" }), membership({ role: "admin" })]);

  assert.equal(hasActiveRole(identity, "admin"), true);
  assert.equal(hasActiveRole(identity, "coordinator"), true);
});

test("a role the account does not hold is not reported", () => {
  const identity = me([membership({ role: "coordinator" })]);

  assert.equal(hasActiveRole(identity, "admin"), false);
  assert.equal(hasActiveRole(identity, "student"), false);
});

test("an expired membership grants nothing, though the row is still reported", () => {
  // `/v1/me` returns every row and marks it, rather than dropping some — so
  // this is the case a bare `.some(m => m.role === "admin")` gets wrong.
  const identity = me([
    membership({ role: "coordinator" }),
    membership({ role: "admin", is_active: false, valid_until: "2020-01-01T00:00:00Z" }),
  ]);

  assert.equal(hasActiveRole(identity, "admin"), false);
  assert.equal(hasActiveRole(identity, "coordinator"), true);
});

test("a role held both actively and expired is still held", () => {
  // Two grants over different subtrees, one lapsed. The live one decides.
  const identity = me([
    membership({ role: "admin", org_unit_path: "pilot.old", is_active: false }),
    membership({ role: "admin", org_unit_path: "pilot", is_active: true }),
  ]);

  assert.equal(hasActiveRole(identity, "admin"), true);
});

test("an unloaded or failed identity answers false, never true", () => {
  // Deny-by-default applied to rendering: "we do not know yet" must look
  // exactly like "no", or a slow `/v1/me` flashes an administration menu.
  for (const absent of [null, undefined]) {
    assert.equal(hasActiveRole(absent, "admin"), false);
  }
  assert.equal(hasActiveRole(me([]), "admin"), false);
});

test("the stored role string is matched exactly, never a display label", () => {
  const identity = me([membership({ role: "admin" })]);

  // `roleLabels.ts` renders `admin` as "Speaker Connector (administrator)".
  // If a label ever reached this function, renaming a persona would silently
  // change who sees the administration surface.
  for (const notTheStoredString of [
    "Admin",
    "admin ",
    " admin",
    "Speaker Connector (administrator)",
    "speaker_connector",
    "",
  ]) {
    assert.equal(
      hasActiveRole(identity, notTheStoredString),
      false,
      `${JSON.stringify(notTheStoredString)} must not match the stored role`,
    );
  }
});
