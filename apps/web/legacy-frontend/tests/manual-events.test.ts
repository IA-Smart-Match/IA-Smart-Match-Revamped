/**
 * The manual-event surface survived the Connector Dashboard consolidation.
 *
 * This file used to assert that the *admin shell* carried the manual-event
 * route and nav entry. That shell (`components/Layout.tsx`) is gone: `admin`
 * and `coordinator` are one persona and now share one shell, so the
 * assertions were repointed at the surviving surface rather than deleted.
 * What they guard is unchanged — the canonical unit-scoped API, the
 * draft/publish controls, no raw `fetch`, and a locally generated QR that
 * reports opens only.
 */
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

import { LEGACY_ROUTE_REDIRECTS } from "../src/app/legacyRedirects.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const routes = read("../src/app/routes.tsx");
const api = read("../src/lib/api.ts");
const events = read("../src/app/pages/Events.tsx");
const qr = read("../src/components/QRCodeCard.tsx");
const shell = read("../src/app/components/CoordinatorPortalLayout.tsx");

/** The successor address of a retired one, or `undefined` if it was not retired. */
function redirectFor(from: string): string | undefined {
  return LEGACY_ROUTE_REDIRECTS.find((entry) => entry.from === from)?.to;
}

test("manual event routes use the canonical unit-scoped API", () => {
  assert.match(api, /\/v1\/units\/\$\{encodeURIComponent\(unitId\)\}\/events/);
  assert.match(routes, /path: "events"/);
  // The two admin-shell routes this file used to find at the top level are now
  // children of the one Connector shell, reached from their old addresses by
  // redirect. Both must still resolve to something.
  assert.match(routes, /path: "speaker-requests"/);
  assert.match(routes, /path: "match-runs"/);
  assert.equal(redirectFor("/opportunities"), "/coordinator-portal/speaker-requests");
  assert.equal(redirectFor("/ai-matching"), "/coordinator-portal/match-runs");
  // The original point of this assertion, preserved: Speaker Requests must not
  // be collapsed into the Events page. They are separate surfaces.
  assert.notEqual(redirectFor("/opportunities"), "/coordinator-portal/events");
  assert.match(events, /Save draft/);
  assert.match(events, /Publish event/);
  // The nav entry moved from the deleted admin sidebar to the Connector
  // Dashboard's "Coordinate" group, at the portal-scoped address.
  assert.match(shell, /name: "Events", href: "\/coordinator-portal\/events"/);
});

test("manual event api.ts adapters cover create/get/patch/publish + feedback QR", () => {
  assert.match(api, /export async function createManualEvent/);
  assert.match(api, /export async function fetchManualEvent/);
  assert.match(api, /export async function updateManualEvent/);
  assert.match(api, /export async function publishManualEvent/);
  assert.match(api, /export async function fetchFeedbackQr/);
  assert.match(api, /export async function saveFeedbackQr/);
  assert.match(api, /Idempotency-Key/);
  assert.match(api, /\/feedback-qr/);
});

test("Events.tsx has no raw fetch, no third-party QR endpoint, and surfaces QR-opens wording", () => {
  assert.doesNotMatch(events, /\bfetch\(/);
  assert.doesNotMatch(events, /"\/api\/qr/);
  assert.match(qr, /QR opens/);
});

test("event feedback QR is local, external, stable-link aware, and reports opens only", () => {
  assert.match(qr, /from "qrcode"/);
  assert.match(qr, /Download PNG/);
  assert.match(qr, /Download SVG/);
  assert.match(qr, /QR opens/);
  assert.match(qr, /does not host, inspect, or receive responses/);
  assert.match(qr, /I confirmed this link opens the intended external feedback form/);
  assert.match(qr, /external website/i);
});

test("the referral QR variant used by Volunteers.tsx and Outreach.tsx is preserved", () => {
  assert.match(qr, /variant\?: "referral"/);
  assert.match(qr, /referral_code/);
});
