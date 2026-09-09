import { test } from "node:test";
import assert from "node:assert/strict";

import {
  calendarSourceProvenance,
  calendarSyntheticReason,
} from "../src/lib/calendarProvenance.ts";

test("each calendar endpoint retains its own provenance", () => {
  assert.equal(calendarSourceProvenance(true, false), "observed");
  assert.equal(calendarSourceProvenance(true, true), "synthetic");
  assert.equal(calendarSourceProvenance(false, false), "synthetic");
});

test("mixed sources name only the synthetic side", () => {
  const assignmentOnly = calendarSyntheticReason(false, true);
  assert.match(assignmentOnly ?? "", /Assignment overlays/);
  assert.match(assignmentOnly ?? "", /calendar windows retain their own provenance/);

  const eventOnly = calendarSyntheticReason(true, false);
  assert.match(eventOnly ?? "", /Event windows/);
  assert.match(eventOnly ?? "", /assignment overlays retain their own provenance/);
});

test("fully live calendar sources need no synthetic banner", () => {
  assert.equal(calendarSyntheticReason(false, false), null);
});
