/**
 * No address that worked before the Connector Dashboard consolidation 404s
 * after it.
 *
 * The consolidation deleted a whole shell. `components/Layout.tsx` owned eight
 * top-level addresses and two volunteer-portal pages were folded into
 * siblings, so ten URLs that are in bookmarks, in the pilot walkthrough, in
 * `tests/e2e/test_pilot_clickthrough.py` and in links people pasted at each
 * other stopped having a page of their own. Every one of them still resolves,
 * and this file is what keeps that true through the next merge.
 *
 * Four separate things are checked, because each fails differently:
 *
 *  1. **The table is complete.** Compared against the recorded inventory of
 *     retired addresses below, by exact set equality — so *removing* a
 *     redirect fails here just as loudly as forgetting to add one. A weaker
 *     "contains" assertion would let a dropped entry through.
 *  2. **No retired address is also still a page**, which would shadow its own
 *     redirect and render a page with no shell around it.
 *  3. **Every destination exists.** Each `to` is matched against the path
 *     segments `routes.tsx` actually registers. A redirect pointing at a page
 *     nobody built is a 404 with extra steps, and it is exactly the mistake a
 *     rename in one file and not the other produces.
 *  4. **No redirect points at another redirect**, and none points at itself.
 *     A chain works but doubles the navigation; a self-reference loops.
 *
 * `routes.tsx` is read as *text* rather than imported: it is JSX, and
 * `npm test` is `node --test tests/*.test.ts`, whose type-stripping loader
 * does not compile JSX. That is the same technique `manual-events.test.ts`
 * uses on the same file.
 */
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

import { LEGACY_ROUTE_REDIRECTS } from "../src/app/legacyRedirects.ts";

const routes = readFileSync(new URL("../src/app/routes.tsx", import.meta.url), "utf8");

/**
 * Every address that worked before this change and no longer has a page.
 *
 * Written out here as a literal, deliberately duplicating the production
 * table: a test that derived its expectation from the thing under test would
 * assert nothing at all. This list is the inventory taken from the deleted
 * `Layout.tsx` and from the two retired volunteer-portal routes.
 */
const RETIRED_ADDRESSES: Readonly<Record<string, string>> = {
  "/dashboard": "/coordinator-portal",
  "/opportunities": "/coordinator-portal/speaker-requests",
  "/events": "/coordinator-portal/events",
  "/ai-matching": "/coordinator-portal/match-runs",
  "/pipeline": "/coordinator-portal/speaker-requests",
  "/calendar": "/coordinator-portal/events",
  "/volunteers": "/coordinator-portal/speaker-contacts",
  "/outreach": "/coordinator-portal/outreach",
  "/volunteer-portal/assignments": "/volunteer-portal",
  "/volunteer-portal/confirmed-speaker": "/volunteer-portal/my-requests",
};

test("every retired address is in the redirect table, and nothing else is", () => {
  const actual = Object.fromEntries(LEGACY_ROUTE_REDIRECTS.map((r) => [r.from, r.to]));
  assert.deepEqual(actual, RETIRED_ADDRESSES);
});

test("no retired address is registered as a page as well as a redirect", () => {
  // `path: "dashboard"` (a router child segment) must not reappear: the shell
  // that owned it is deleted, and a surviving registration would win over the
  // redirect and render a page with no chrome around it.
  //
  // `/events` and `/outreach` are the interesting cases. Both words survive as
  // *children of the coordinator portal* (`coordinator-portal/events`), which
  // is a different address from the retired top-level one — so the check is
  // for the exact retired path in the redirect table's own spelling, not for
  // the bare word appearing anywhere in the file.
  for (const { from } of LEGACY_ROUTE_REDIRECTS) {
    assert.doesNotMatch(
      routes,
      new RegExp(`path: "${from}"`),
      `${from} is still registered as a page in routes.tsx as well as a redirect`,
    );
  }
});

test("every redirect destination is a route this router serves", () => {
  for (const { from, to } of LEGACY_ROUTE_REDIRECTS) {
    // Destinations are either a shell root (`/coordinator-portal`,
    // `/volunteer-portal`) or a child of one. A shell root is registered as
    // `path: "coordinator-portal"`; a child as its last segment.
    const segments = to.replace(/^\//, "").split("/");
    const needle = segments[segments.length - 1];
    assert.match(
      routes,
      new RegExp(`path: "${needle}"`),
      `${from} redirects to ${to}, which routes.tsx does not register`,
    );
  }
});

test("no redirect chains into another redirect or into itself", () => {
  const retired = new Set(LEGACY_ROUTE_REDIRECTS.map((r) => r.from));
  for (const { from, to } of LEGACY_ROUTE_REDIRECTS) {
    assert.notEqual(from, to, `${from} redirects to itself`);
    assert.ok(!retired.has(to), `${from} redirects to ${to}, which is itself retired`);
  }
});

test("a retired address whose parameter names a resource keeps it", () => {
  // `/ai-matching?run={id}` was the shortlist's whole address — `run` names the
  // persisted match run, and a redirect that dropped it would land the reader
  // on the submission form with the shortlist orphaned. The entry therefore
  // declares the parameter, and routes.tsx must carry it through: a field the
  // router never reads would be a promise the table makes and nothing keeps.
  const aiMatching = LEGACY_ROUTE_REDIRECTS.find((r) => r.from === "/ai-matching");
  assert.ok(aiMatching, "the /ai-matching redirect is missing");
  assert.deepEqual(
    aiMatching.forwardParams,
    ["run"],
    "/ai-matching must forward its ?run= parameter; the shortlist is unreachable without it",
  );
  assert.match(routes, /forwardParams/, "routes.tsx drops forwardParams — the field is never read");
  assert.match(routes, /useSearchParams/, "routes.tsx never reads the query string to forward it");

  // No other retired address declares parameters to forward: each was a whole
  // page, and a silent forward-everything rule would hand the successors
  // inputs they never agreed to read.
  const forwarding = LEGACY_ROUTE_REDIRECTS.filter((r) => r.forwardParams !== undefined);
  assert.deepEqual(
    forwarding.map((r) => r.from),
    ["/ai-matching"],
    "forwardParams appeared on an address that had no parameter contract",
  );
});

test("the redirects are registered in routes.tsx, not merely exported", () => {
  // The table is only a promise until the router is built from it. This is the
  // line that turns it into behaviour.
  assert.match(routes, /LEGACY_ROUTE_REDIRECTS\.map/);
  // `replace`, so the retired address does not sit in the history stack and
  // trap a reader who presses Back onto it.
  assert.match(routes, /<Navigate to=\{to\} replace \/>/);
});

test("an unknown address renders the honest 404 rather than a framework error", () => {
  assert.match(routes, /path: "\*"/);
  assert.match(routes, /element: <NotFound \/>/);
  assert.match(routes, /errorElement: <NotFound \/>/);
});
