import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const routes = read("../src/app/routes.tsx");
const api = read("../src/lib/api.ts");
const events = read("../src/app/pages/Events.tsx");
const coordinatorEvents = read("../src/app/pages/coordinator/CoordinatorEvents.tsx");
const qr = read("../src/components/QRCodeCard.tsx");
const outreach = read("../src/app/pages/Outreach.tsx");
const pipeline = read("../src/app/pages/Pipeline.tsx");
const volunteers = read("../src/app/pages/Volunteers.tsx");

test("manual event routes use the canonical unit-scoped API", () => {
  assert.match(api, /\/v1\/units\/\$\{encodeURIComponent\(unitId\)\}\/events/);
  assert.match(routes, /path: "events"/);
  assert.match(routes, /path: "opportunities", element: <Navigate to="\/events" replace/);
  assert.match(events, /Save draft/);
  assert.match(events, /Publish event/);
  assert.match(coordinatorEvents, /fetchManualEvents\(unitId!, "published"\)/);
  assert.doesNotMatch(coordinatorEvents, /feedback-qr|destination_url|QRCodeCard/);
});

test("event feedback QR is local, external, stable-link aware, and reports opens only", () => {
  assert.match(qr, /from "qrcode"/);
  assert.match(qr, /Download PNG/);
  assert.match(qr, /Download SVG/);
  assert.match(qr, /QR opens/);
  assert.match(qr, /does not host, inspect, or receive responses/);
  assert.match(qr, /I confirmed this link opens the intended external feedback form/);
  assert.doesNotMatch(qr, /conversion|ROI|speaker|referral/i);
});

test("retired crawler and referral QR widgets have no visible consumers", () => {
  for (const source of [outreach, pipeline, volunteers]) {
    assert.doesNotMatch(source, /CrawlerFeed|fetchQrStats|generateQrAsset|QRCodeCard/);
  }
  assert.doesNotMatch(outreach, /Referral QR|Web Intelligence/i);
  assert.doesNotMatch(pipeline, /QR ROI|scan-to-conversion|Top referral history/i);
  assert.doesNotMatch(volunteers, /QR history|referral assets/i);
});
