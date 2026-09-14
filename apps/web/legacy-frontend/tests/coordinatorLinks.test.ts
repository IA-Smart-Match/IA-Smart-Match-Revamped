/**
 * The coordinator pages' internal links must land on routes the Connector
 * Dashboard actually registers — the sibling of `studentLinks.test.ts` and
 * `volunteerLinks.test.ts` for the connector shell.
 *
 * The registered set is parsed out of `routes.tsx` rather than restated
 * here, so a route renamed in the router fails this test on the page that
 * still links to it instead of drifting out of sync with a copied list.
 *
 * One exception to the literal-only rule: `CoordinatorHome`'s `ActionRow`
 * takes its target as a prop (`to={to}`). Every call site passes a literal
 * that the literal scan already checks, so the passthrough is whitelisted
 * rather than forbidden — a `to={...}` anywhere else, or a different
 * expression there, still fails.
 */
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const routes = read("../src/app/routes.tsx");
const pageFiles = readdirSync(new URL("../src/app/pages/coordinator/", import.meta.url)).filter(
  (name) => name.endsWith(".tsx"),
);

// The connector shell's registered paths: `path: "coordinator-portal"` opens
// the block, its `children:` array runs to the first `]` at four-space
// indentation, and every `path:` inside — plus the `index:` child — is a URL
// the portal serves.
const coordinatorBlock = routes.match(
  /path: "coordinator-portal"[\s\S]*?children: \[([\s\S]*?)\n {4}\]/,
);
assert.ok(
  coordinatorBlock,
  "routes.tsx no longer nests connector pages under coordinator-portal",
);
const registered = new Set<string>(["/coordinator-portal"]);
for (const match of coordinatorBlock[1].matchAll(/path: "([^"]+)"/g)) {
  registered.add(`/coordinator-portal/${match[1]}`);
}

test("the connector shell still registers the routes its pages link to", () => {
  // Route-parity pinning: a route dropped from the router must fail loudly
  // here rather than strand a link on a page that still points at it.
  for (const path of [
    "speaker-requests",
    "review-queue",
    "events",
    "match-runs",
    "invitations",
    "meetings",
    "speaker-contacts",
    "speaker-feedback",
    "outreach",
    "matching-weights",
  ]) {
    assert.ok(
      registered.has(`/coordinator-portal/${path}`),
      `routes.tsx no longer registers /coordinator-portal/${path}`,
    );
  }
});

test("every absolute link target in pages/coordinator/ is a registered connector route", () => {
  assert.ok(pageFiles.length > 0, "no coordinator pages found to check");
  for (const file of pageFiles) {
    const source = read(`../src/app/pages/coordinator/${file}`);
    // The one sanctioned computed target: `ActionRow`'s `to` prop passthrough
    // in CoordinatorHome, whose call sites all pass literals checked below.
    const computed = source.match(/\bto=\{[^}]+\}/g) ?? [];
    const allowed = file === "CoordinatorHome.tsx" ? ["to={to}"] : [];
    for (const target of computed) {
      assert.ok(
        allowed.includes(target),
        `${file} has a computed Link target ${target} this test cannot check`,
      );
    }
    for (const match of source.matchAll(/\bto="(\/[^"]*)"/g)) {
      const target = match[1].split(/[?#]/)[0];
      assert.ok(
        registered.has(target),
        `${file} links to ${target}, which routes.tsx does not register under coordinator-portal`,
      );
    }
  }
});
