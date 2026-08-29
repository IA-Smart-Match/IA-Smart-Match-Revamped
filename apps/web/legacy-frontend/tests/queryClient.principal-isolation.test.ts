/**
 * Account-switch cache isolation test for plan P4, lane F1.
 *
 * This is the load-bearing safety test for the frontend query cache: it
 * proves that switching from one principal to another can never leak
 * cached data across the switch, and (separately) that the identity seam
 * does not indiscriminately nuke the cache on every call -- only on an
 * actual identity change.
 *
 * Runs under Node's built-in test runner (`node --test tests/`), against
 * the REAL `@tanstack/react-query` `QueryClient`, importing
 * `../src/lib/queryClient.ts` directly by relative path. No mocks, no DOM,
 * no Vite.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { QueryClient } from "@tanstack/react-query";

import {
  createAppQueryClient,
  createPrincipalIdentity,
  drilldownQueryKey,
  metricsQueryKey,
  shouldRetryQuery,
} from "../src/lib/queryClient.ts";

test("metricsQueryKey and drilldownQueryKey differ in their first segment across principals", () => {
  const aMetrics = metricsQueryKey("A", "unit-1");
  const bMetrics = metricsQueryKey("B", "unit-1");
  assert.notEqual(aMetrics[0], bMetrics[0]);
  assert.equal(aMetrics[0], "A");
  assert.equal(bMetrics[0], "B");

  const aDrilldown = drilldownQueryKey("A", "unit-1", "pipeline_matched");
  const bDrilldown = drilldownQueryKey("B", "unit-1", "pipeline_matched");
  assert.notEqual(aDrilldown[0], bDrilldown[0]);
  assert.equal(aDrilldown[0], "A");
  assert.equal(bDrilldown[0], "B");
});

test("account switch: A's cache entry is gone and B gets a fresh miss (zero cache hits on A-keyed entries)", () => {
  const client = createAppQueryClient();
  const identity = createPrincipalIdentity();

  // Principal A signs in and their metrics get cached.
  identity.apply(client, "A");
  client.setQueryData(metricsQueryKey("A", "unit-1"), {
    unit_id: "unit-1",
    metrics: [{ name: "pipeline_matched", display_name: "Matched", definition: "", value: 42, drill_down_url: "" }],
  });
  assert.notEqual(client.getQueryData(metricsQueryKey("A", "unit-1")), undefined);

  // Principal B takes over the session.
  identity.apply(client, "B");

  // A's entry must be completely gone.
  assert.equal(client.getQueryData(metricsQueryKey("A", "unit-1")), undefined);
  // B must get a genuine cache miss -- nothing pre-populated for them either.
  assert.equal(client.getQueryData(metricsQueryKey("B", "unit-1")), undefined);

  client.clear();
});

test("applying the same principal key twice does not clear the cache", () => {
  const client = createAppQueryClient();
  const identity = createPrincipalIdentity();

  identity.apply(client, "A");
  client.setQueryData(metricsQueryKey("A", "unit-1"), {
    unit_id: "unit-1",
    metrics: [],
  });
  assert.notEqual(client.getQueryData(metricsQueryKey("A", "unit-1")), undefined);

  // Re-applying the SAME key must be a no-op with respect to the cache.
  identity.apply(client, "A");

  assert.notEqual(
    client.getQueryData(metricsQueryKey("A", "unit-1")),
    undefined,
    "re-applying the same principal key must not clear A's cached data",
  );

  client.clear();
});

test("a fetchMe() failure, represented as applying null, clears the cache", () => {
  const client = createAppQueryClient();
  const identity = createPrincipalIdentity();

  identity.apply(client, "A");
  client.setQueryData(metricsQueryKey("A", "unit-1"), {
    unit_id: "unit-1",
    metrics: [],
  });
  assert.notEqual(client.getQueryData(metricsQueryKey("A", "unit-1")), undefined);

  // fetchMe() failed -- no known principal.
  identity.apply(client, null);

  assert.equal(client.getQueryData(metricsQueryKey("A", "unit-1")), undefined);
  assert.equal(identity.current, null);

  client.clear();
});

test("ADR-0011: an unknown metric (value: null + unknown_reason) round-trips through the cache intact", () => {
  const client = createAppQueryClient();
  const identity = createPrincipalIdentity();
  identity.apply(client, "A");

  const unknownMetric = {
    name: "pipeline_member_inquiry",
    display_name: "Member Inquiry",
    definition: "Registered metric",
    value: null,
    unknown_reason: "No evidence source yet: S12 Pipeline persistence is not started.",
    drill_down_url: "",
  };

  client.setQueryData(metricsQueryKey("A", "unit-1"), {
    unit_id: "unit-1",
    metrics: [unknownMetric],
  });

  const cached = client.getQueryData(metricsQueryKey("A", "unit-1")) as {
    unit_id: string;
    metrics: Array<{ name: string; value: number | null; unknown_reason?: string | null }>;
  };

  assert.equal(cached.metrics.length, 1);
  const roundTripped = cached.metrics[0];
  // Never turned into 0, never dropped: value stays null, and the
  // unknown_reason -- the ADR-0011 evidence for *why* it's unknown -- stays
  // attached to the entry.
  assert.equal(roundTripped.value, null);
  assert.notEqual(roundTripped.value, 0);
  assert.equal(
    roundTripped.unknown_reason,
    "No evidence source yet: S12 Pipeline persistence is not started.",
  );

  client.clear();
});

test("PrincipalIdentityTracker starts with current === null and reset() restores that", () => {
  const identity = createPrincipalIdentity();
  assert.equal(identity.current, null);

  const client = new QueryClient();
  identity.apply(client, "A");
  assert.equal(identity.current, "A");

  identity.reset();
  assert.equal(identity.current, null);

  client.clear();
});

test("a 4xx is the server's considered answer and is never retried", () => {
  for (const status of [400, 401, 403, 404, 429]) {
    assert.equal(
      shouldRetryQuery(0, { status, name: "ApiRequestError" }),
      false,
      `HTTP ${status} must not be retried`,
    );
  }
});

test("a transient failure is retried a bounded number of times", () => {
  // A 5xx, and an error carrying no status at all (e.g. a network failure).
  for (const error of [{ status: 503 }, new Error("network down")]) {
    assert.equal(shouldRetryQuery(0, error), true);
    assert.equal(shouldRetryQuery(1, error), true);
    assert.equal(shouldRetryQuery(2, error), false, "retries must be bounded");
  }
});
