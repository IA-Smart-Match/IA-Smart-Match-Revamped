import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const routes = read("../src/app/routes.tsx");
const api = read("../src/lib/api.ts");
const events = read("../src/app/pages/Events.tsx");
const qr = read("../src/components/QRCodeCard.tsx");
const layout = read("../src/app/components/Layout.tsx");

test("manual event routes use the canonical unit-scoped API", () => {
  assert.match(api, /\/v1\/units\/\$\{encodeURIComponent\(unitId\)\}\/events/);
  assert.match(routes, /path: "events"/);
  // Main's existing routes must survive this port unchanged.
  assert.match(routes, /path: "opportunities"/);
  assert.match(routes, /path: "ai-matching"/);
  assert.doesNotMatch(routes, /path: "opportunities", element: <Navigate to="\/events"/);
  assert.match(events, /Save draft/);
  assert.match(events, /Publish event/);
  assert.match(layout, /name: "Events", href: "\/events"/);
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
