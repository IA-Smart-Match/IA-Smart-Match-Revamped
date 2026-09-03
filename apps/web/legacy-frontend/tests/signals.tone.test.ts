/**
 * Severity-grading tests for the discovery feed's red / yellow / green.
 *
 * The point of these is not that the arithmetic works — it is that the two
 * honesty rules in `src/lib/signals.ts` hold under every input shape:
 *
 *   1. an unmeasured value never renders as "clear" (green), and
 *   2. a truncated count can only *raise* severity, never lower it.
 *
 * Both are the difference between presenting a metric and inventing a score,
 * which is what ADR-0011 and `apps/web/DESIGN.md` §1.9 are about.
 *
 * Runs under `node --test tests/`, importing the module by relative path.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  SIGNAL_TONE_LABELS,
  SIGNAL_TONE_RANK,
  toneForBacklog,
  type SignalThresholds,
} from "../src/lib/signals.ts";
import {
  atLeastValue,
  knownValue,
  unknownValue,
} from "../src/app/components/provenance/types.ts";

const THRESHOLDS: SignalThresholds = {
  criticalAtOrAbove: 20,
  watchAtOrAbove: 1,
  rationale: "test rule",
};

test("a known count is graded at its own cut points", () => {
  assert.equal(toneForBacklog(knownValue(0), THRESHOLDS), "clear");
  assert.equal(toneForBacklog(knownValue(1), THRESHOLDS), "watch");
  assert.equal(toneForBacklog(knownValue(19), THRESHOLDS), "watch");
  assert.equal(toneForBacklog(knownValue(20), THRESHOLDS), "critical");
  assert.equal(toneForBacklog(knownValue(1000), THRESHOLDS), "critical");
});

test("a measured zero really is clear — a real zero is not the defect", () => {
  // ADR-0011 is about `0` standing in for unknown, not about zero itself.
  // If the register measured an empty queue, green is the truthful colour.
  assert.equal(toneForBacklog(knownValue(0), THRESHOLDS), "clear");
});

test("unknown is never green, and never any measured tone", () => {
  const tone = toneForBacklog(unknownValue("the metrics API did not answer"), THRESHOLDS);
  assert.equal(tone, "unknown");
  assert.notEqual(tone, "clear");
  assert.notEqual(tone, "watch");
  assert.notEqual(tone, "critical");
});

test("unknown stays unknown no matter where the cut points sit", () => {
  // The failure mode this guards: a threshold pair chosen so that "nothing
  // measured" happens to fall below `watchAtOrAbove` and reads as clear.
  for (const criticalAtOrAbove of [0, 1, 5, 20]) {
    const thresholds: SignalThresholds = {
      criticalAtOrAbove,
      watchAtOrAbove: 0,
      rationale: "test rule",
    };
    assert.equal(toneForBacklog(unknownValue("no evidence"), thresholds), "unknown");
  }
});

test("a lower bound that already clears a cut point is graded at it", () => {
  // The true count is >= the bound, so a bound of 20 guarantees critical.
  assert.equal(toneForBacklog(atLeastValue(20), THRESHOLDS), "critical");
  assert.equal(toneForBacklog(atLeastValue(45), THRESHOLDS), "critical");
  assert.equal(toneForBacklog(atLeastValue(1), THRESHOLDS), "watch");
});

test("a lower bound below every cut point is unknown, not clear", () => {
  // "We counted 0 so far and stopped" does not license an all-clear: the
  // rows we did not reach could be anything.
  assert.equal(toneForBacklog(atLeastValue(0), THRESHOLDS), "unknown");
});

test("a lower bound never grades softer than the same number known", () => {
  for (let value = 0; value <= 30; value += 1) {
    const known = toneForBacklog(knownValue(value), THRESHOLDS);
    const bound = toneForBacklog(atLeastValue(value), THRESHOLDS);
    assert.ok(
      SIGNAL_TONE_RANK[bound] <= SIGNAL_TONE_RANK[known],
      `at_least(${value}) graded "${bound}" is softer than known(${value}) graded "${known}"`,
    );
  }
});

test("every tone has a text label, so colour is never the only channel", () => {
  for (const tone of ["critical", "watch", "clear", "unknown"] as const) {
    assert.ok(SIGNAL_TONE_LABELS[tone].length > 0);
  }
});

test("feed ordering puts unresolved severity ahead of measured calm", () => {
  assert.ok(SIGNAL_TONE_RANK.critical < SIGNAL_TONE_RANK.watch);
  assert.ok(SIGNAL_TONE_RANK.watch < SIGNAL_TONE_RANK.unknown);
  assert.ok(SIGNAL_TONE_RANK.unknown < SIGNAL_TONE_RANK.clear);
});
