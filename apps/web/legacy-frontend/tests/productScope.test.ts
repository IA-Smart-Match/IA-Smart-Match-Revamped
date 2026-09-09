/**
 * The frontend half of the CBA product-scope capability policy behaves like
 * the Python half.
 *
 * The *parity* assertion — that the two files carry the same eleven decisions —
 * lives in `tests/unit/test_cba_scope_policy.py`, which can read both. What
 * these tests pin is the behaviour a caller in this app relies on: the reader
 * fails closed loudly on an unknown name, and the preserved/gated split is the
 * one the customer asked for.
 *
 * Runs under `node --test tests/`, importing the module by relative path.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  CAPABILITIES,
  CBA_CAPABILITY_POLICY,
  CapabilityScopeError,
  enabledCapabilities,
  isCapabilityEnabled,
  type Capability,
} from "../src/lib/productScope.ts";

/** Customer §22 ("Existing Functionality to Preserve") and §4 ("Rewards — Keep"). */
const PRESERVED: readonly Capability[] = [
  "authenticated_login",
  "event_reads",
  // Customer §12 (an Event Host files a Speaker Request) and §13 (a Speaker
  // Connector reads the queue). Its own capability rather than a share of
  // `event_reads` because it is a write — see `product_scope.py`.
  "speaker_request_intake",
  "match_runs",
  "discovery_metrics",
  "consented_outreach",
  "rewards_ledger",
  "operator_record_import",
];

/** Customer §20 ("Explicit Scope Boundaries") and the member_inquiry disposition. */
const GATED: readonly Capability[] = [
  "external_speaker_acquisition",
  "cold_unknown_contact_outreach",
  "chapter_membership_dues",
  "member_inquiry_narrative",
];

test("every capability carries an explicit decision", () => {
  assert.equal(CAPABILITIES.length, PRESERVED.length + GATED.length);
  for (const capability of CAPABILITIES) {
    assert.equal(typeof CBA_CAPABILITY_POLICY[capability], "boolean");
  }
});

test("working in-scope behaviour is preserved", () => {
  for (const capability of PRESERVED) {
    assert.equal(isCapabilityEnabled(capability), true, `${capability} must stay enabled`);
  }
});

test("out-of-scope capabilities are disabled", () => {
  for (const capability of GATED) {
    assert.equal(isCapabilityEnabled(capability), false, `${capability} must be disabled`);
  }
});

test("gating cold outreach does not gate the consented path", () => {
  // The two share a word and nothing else: one contacts people who never
  // agreed to be contacted, the other sends an approved draft to a consented
  // contact. A gate keyed on the word "outreach" would remove a working,
  // in-scope capability.
  assert.equal(isCapabilityEnabled("cold_unknown_contact_outreach"), false);
  assert.equal(isCapabilityEnabled("consented_outreach"), true);
});

test("rewards are not disabled as collateral of removing chapter membership", () => {
  // Customer §4 lists "Rewards / points — Keep" in the same table that removes
  // chapter membership and dues. They are separate decisions.
  assert.equal(isCapabilityEnabled("chapter_membership_dues"), false);
  assert.equal(isCapabilityEnabled("rewards_ledger"), true);
});

test("an unknown capability throws rather than reading as disabled", () => {
  assert.throws(
    () => isCapabilityEnabled("speaker_teleportation" as Capability),
    CapabilityScopeError,
  );
});

test("enabledCapabilities returns exactly the preserved set", () => {
  assert.deepEqual([...enabledCapabilities()].sort(), [...PRESERVED].sort());
});

test("the policy names no live-provider, live-data, or deploy capability", () => {
  // Product scope must not become a second door into gates that already have
  // an owner (ALLOW_LIVE_PROVIDERS / ALLOW_LIVE_DATA / ALLOW_CLOUD_DEPLOY).
  const forbidden = /live|deploy|terraform|credential|secret/i;
  const offenders = CAPABILITIES.filter((capability) => forbidden.test(capability));
  assert.deepEqual(offenders, []);
});
