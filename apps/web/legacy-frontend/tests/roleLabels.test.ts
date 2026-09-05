/**
 * The frontend half of the CBA role-presentation map behaves like the Python
 * half.
 *
 * The *parity* assertion — that the two files carry the same four rows — lives
 * in `tests/unit/test_role_presentation.py`, which can read both. What these
 * tests pin is the behaviour a caller in this app relies on: an unmapped role
 * is reported as unmapped rather than rounded to a persona, and the labels are
 * the ones customer §2 asked for.
 *
 * Runs under `node --test tests/`, importing the module by relative path.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  KNOWN_ROLES,
  ROLE_PRESENTATION,
  personaForRole,
  portalDisplayNameForRole,
  visibleRoleLabel,
} from "../src/lib/roleLabels.ts";

test("the stored role vocabulary is unchanged", () => {
  assert.deepEqual([...KNOWN_ROLES].sort(), ["admin", "coordinator", "student", "volunteer"]);
});

test("each stored role carries a complete presentation", () => {
  for (const role of KNOWN_ROLES) {
    const entry = ROLE_PRESENTATION[role];
    assert.ok(entry.persona.length > 0);
    assert.ok(entry.roleLabel.length > 0);
    assert.ok(entry.portalDisplayName.length > 0);
  }
});

test("the customer's personas are the ones shown", () => {
  assert.equal(visibleRoleLabel("student"), "Student");
  assert.equal(visibleRoleLabel("volunteer"), "Event Host");
  assert.equal(visibleRoleLabel("coordinator"), "Speaker Connector");
  assert.equal(personaForRole("coordinator"), "speaker_connector");
  assert.equal(personaForRole("admin"), "speaker_connector");
  // Same persona family, distinguishable label — see
  // `docs/product/cba-role-presentation.md` OQ-1.
  assert.notEqual(visibleRoleLabel("admin"), visibleRoleLabel("coordinator"));
});

test("an unmapped role is reported, never guessed", () => {
  for (const unknown of ["", "   ", "speaker", "dean", "Student", "coordinator "]) {
    assert.equal(personaForRole(unknown), null, `${unknown} must map to no persona`);
    assert.equal(visibleRoleLabel(unknown), null);
    assert.equal(portalDisplayNameForRole(unknown), null);
  }
});

test("inherited object properties are not mistaken for roles", () => {
  // `hasOwnProperty`, not `in`: `"toString"` is on every object's prototype and
  // must not read as a role with a label.
  assert.equal(visibleRoleLabel("toString"), null);
  assert.equal(visibleRoleLabel("constructor"), null);
});

test("no visible label carries the legacy institutional wording", () => {
  const shown = KNOWN_ROLES.map(
    (role) => `${ROLE_PRESENTATION[role].roleLabel} ${ROLE_PRESENTATION[role].portalDisplayName}`,
  )
    .join(" ")
    .toLowerCase();
  for (const banned of ["ia west", "iawest", "insights association", "chapter", "volunteer"]) {
    assert.ok(!shown.includes(banned), `a visible label still says "${banned}"`);
  }
});
