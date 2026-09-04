import { test } from "node:test";
import assert from "node:assert/strict";

import { summarizeCalendarCoverage } from "../src/lib/calendarCoverage.ts";

test("unknown coverage is neither counted as open nor folded into a ratio", () => {
  const summary = summarizeCalendarCoverage(["covered", "unknown"]);

  assert.equal(summary.covered, 1);
  assert.equal(summary.explicitlyOpen, 0);
  assert.equal(summary.unknown, 1);
  assert.equal(summary.fullyResolved, false);
  assert.equal(summary.coverageRatio, null);
});

test("fully resolved statuses produce the explicit backlog and exact ratio", () => {
  const summary = summarizeCalendarCoverage([
    "covered",
    "partial",
    "needs_coverage",
    "covered",
  ]);

  assert.equal(summary.explicitlyOpen, 2);
  assert.equal(summary.unknown, 0);
  assert.equal(summary.fullyResolved, true);
  assert.equal(summary.coverageRatio, 0.5);
});

test("an empty calendar has no coverage denominator", () => {
  const summary = summarizeCalendarCoverage([]);

  assert.equal(summary.fullyResolved, true);
  assert.equal(summary.coverageRatio, null);
});
