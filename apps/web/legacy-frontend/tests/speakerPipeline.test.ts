/**
 * The Speaker Pipeline section's presentation rules.
 *
 * What is asserted here is deliberately narrow, because the module under test
 * is deliberately narrow: it decides widths, order and screen-reader text and
 * nothing else. Every business number — counts, conversion rates, the
 * percentage strings — is computed and formatted server-side, and
 * `tests/unit/test_speaker_pipeline.py` is where that arithmetic is pinned.
 *
 * The load-bearing assertions are the ones about *not* inventing: a clamped
 * band width must never be confused with a measured share, an absent share
 * must not acquire a default width, and a metric the server did not send must
 * not appear as a card.
 *
 * Runs under `node --test tests/`, importing the module by relative path.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import type {
  SpeakerPipelineCompanion,
  SpeakerPipelineResponse,
  SpeakerPipelineStage,
} from "../src/lib/api.ts";
import {
  funnelWidthPercent,
  isFunnelStage,
  MAX_FUNNEL_WIDTH_PCT,
  metricCardOrder,
  MIN_FUNNEL_WIDTH_PCT,
  NEUTRAL_TINT,
  STAGE_TINTS,
  stageAccessibleLabel,
  tintFor,
} from "../src/lib/speakerPipeline.ts";

function stage(
  metricName: string,
  value: number | null,
  share: number | null,
  shareDisplay: string,
): SpeakerPipelineStage {
  return {
    metric_name: metricName,
    display_name: metricName,
    description: "",
    definition: "",
    value,
    unknown_reason: value === null ? "No evidence source exists for this metric." : null,
    share_of_baseline_pct: share,
    share_display: shareDisplay,
  };
}

function companion(metricName: string, value: number | null): SpeakerPipelineCompanion {
  return {
    metric_name: metricName,
    display_name: metricName,
    description: "",
    definition: "",
    value,
    unknown_reason: null,
  };
}

function payload(
  stages: SpeakerPipelineStage[],
  companions: SpeakerPipelineCompanion[],
): SpeakerPipelineResponse {
  return {
    unit_id: "00000000-0000-0000-0000-000000000000",
    range: { kind: "all_time", label: "All time", note: "" },
    metrics: [],
    baseline_metric: "pipeline_matched",
    stages,
    companions,
    conversions: [],
    insights: [],
  };
}

// ---------------------------------------------------------------------------
// Band widths
// ---------------------------------------------------------------------------

test("a measured share becomes a drawable width", () => {
  assert.equal(funnelWidthPercent(100), MAX_FUNNEL_WIDTH_PCT);
  assert.equal(funnelWidthPercent(60), 60);
});

test("a tiny share is widened to stay legible, and never drawn above the maximum", () => {
  assert.equal(funnelWidthPercent(1), MIN_FUNNEL_WIDTH_PCT);
  assert.equal(funnelWidthPercent(0), MIN_FUNNEL_WIDTH_PCT);
  assert.equal(funnelWidthPercent(140), MAX_FUNNEL_WIDTH_PCT);
});

test("an absent share yields no width rather than a default one", () => {
  // The caller draws an absence as an outline; a number here would be a width
  // nobody measured, and the clamp above would make it look plausible.
  assert.equal(funnelWidthPercent(null), null);
});

test("a non-finite share is treated as absent, not drawn", () => {
  assert.equal(funnelWidthPercent(Number.NaN), null);
  assert.equal(funnelWidthPercent(Number.POSITIVE_INFINITY), null);
});

// ---------------------------------------------------------------------------
// Tints
// ---------------------------------------------------------------------------

test("every presented metric has an explicit tint", () => {
  for (const name of [
    "pipeline_matched",
    "pipeline_contacted",
    "pipeline_confirmed",
    "pipeline_attended",
    "opportunities",
    "pending_review_items",
  ]) {
    assert.notEqual(STAGE_TINTS[name], undefined, name);
  }
});

test("an unknown metric name falls back to a neutral wash rather than crashing", () => {
  assert.deepEqual(tintFor("pipeline_invented"), NEUTRAL_TINT);
});

test("every tint carries a dark-theme counterpart", () => {
  for (const [name, tint] of Object.entries(STAGE_TINTS)) {
    for (const [slot, value] of Object.entries(tint)) {
      assert.ok(value.includes("dark:"), `${name}.${slot} has no dark variant: ${value}`);
    }
  }
});

// ---------------------------------------------------------------------------
// Card order
// ---------------------------------------------------------------------------

test("all six presented metrics get a card, in the section's reading order", () => {
  const body = payload(
    [
      stage("pipeline_matched", 10, 100, "100%"),
      stage("pipeline_contacted", 4, 40, "40%"),
      stage("pipeline_confirmed", 2, 20, "20%"),
      stage("pipeline_attended", 1, 10, "10%"),
    ],
    [companion("opportunities", 1), companion("pending_review_items", 2)],
  );

  assert.deepEqual(
    metricCardOrder(body).map((entry) => entry.metric_name),
    [
      "pipeline_matched",
      "pipeline_contacted",
      "opportunities",
      "pending_review_items",
      "pipeline_attended",
      "pipeline_confirmed",
    ],
  );
});

test("a metric the server did not send gets no card", () => {
  const body = payload([stage("pipeline_matched", 3, 100, "100%")], []);
  assert.deepEqual(
    metricCardOrder(body).map((entry) => entry.metric_name),
    ["pipeline_matched"],
  );
});

test("a metric this surface has not heard of still gets a card, at the end", () => {
  const body = payload(
    [stage("pipeline_matched", 3, 100, "100%"), stage("pipeline_invented", 1, 33, "33%")],
    [],
  );
  assert.deepEqual(
    metricCardOrder(body).map((entry) => entry.metric_name),
    ["pipeline_matched", "pipeline_invented"],
  );
});

test("a funnel stage and a companion measure stay distinguishable", () => {
  assert.equal(isFunnelStage(stage("pipeline_matched", 1, 100, "100%")), true);
  assert.equal(isFunnelStage(companion("pending_review_items", 1)), false);
});

// ---------------------------------------------------------------------------
// Screen-reader text
// ---------------------------------------------------------------------------

test("a stage's text equivalent quotes the server's own share, not a re-rounded one", () => {
  const label = stageAccessibleLabel(stage("pipeline_contacted", 4, 39.6, "40%"));
  assert.ok(label.includes("4"));
  assert.ok(label.includes("40%"));
  assert.ok(!label.includes("39"));
});

test("a measured zero reads as a number, not as an absence", () => {
  const label = stageAccessibleLabel(stage("pipeline_attended", 0, 0, "0%"));
  assert.ok(label.includes("0"));
  assert.ok(!label.includes("not measured"));
});

test("an unmeasured stage says so and carries the server's reason", () => {
  const label = stageAccessibleLabel(stage("pipeline_attended", null, null, "—"));
  assert.ok(label.includes("not measured"));
  assert.ok(label.includes("No evidence source exists"));
});

test("a stage with a value but no share states the value alone", () => {
  const label = stageAccessibleLabel(stage("pipeline_matched", 7, null, "—"));
  assert.ok(label.includes("7"));
  assert.ok(!label.includes("—"));
});
