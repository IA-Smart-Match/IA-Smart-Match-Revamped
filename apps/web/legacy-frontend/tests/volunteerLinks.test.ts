/**
 * The Event Host pages' internal links must land on routes the volunteer
 * portal actually registers — the sibling of `studentLinks.test.ts` for the
 * host shell.
 *
 * The defect pattern it guards is the same one that file names: an absolute
 * `to="..."` missing the `volunteer-portal/` prefix does not 404 — it walks an
 * Event Host out of their portal onto a surface that is not theirs, or points
 * at nothing at all. The registered set is parsed out of `routes.tsx` rather
 * than restated here, so a route renamed in the router fails this test on the
 * page that still links to it instead of drifting out of sync with a copied
 * list.
 *
 * The detail states (`?request=`) are deliberately out of scope for this scan:
 * they are set with `setSearchParams` on the same address, never with a `to=`
 * literal, which is what keeps them out of the link graph this file checks.
 */
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const routes = read("../src/app/routes.tsx");
const pageFiles = readdirSync(new URL("../src/app/pages/volunteer/", import.meta.url)).filter(
  (name) => name.endsWith(".tsx"),
);

// The volunteer shell's registered paths: `path: "volunteer-portal"` opens the
// block, its `children:` array runs to the first `]` at the same four-space
// indentation, and every `path:` inside — plus the `index:` child — is a URL
// the portal serves.
const volunteerBlock = routes.match(
  /path: "volunteer-portal"[\s\S]*?children: \[([\s\S]*?)\n {4}\]/,
);
assert.ok(volunteerBlock, "routes.tsx no longer nests host pages under volunteer-portal");
const registered = new Set<string>(["/volunteer-portal"]);
for (const match of volunteerBlock[1].matchAll(/path: "([^"]+)"/g)) {
  registered.add(`/volunteer-portal/${match[1]}`);
}

test("the volunteer shell still registers the routes its pages link to", () => {
  // Route-parity pinning: a route dropped from the router must fail loudly
  // here rather than strand a link on a page that still points at it.
  for (const path of ["speaker-request", "my-requests", "organization", "profile"]) {
    assert.ok(
      registered.has(`/volunteer-portal/${path}`),
      `routes.tsx no longer registers /volunteer-portal/${path}`,
    );
  }
});

test("every absolute link target in pages/volunteer/ is a registered volunteer route", () => {
  assert.ok(pageFiles.length > 0, "no volunteer pages found to check");
  for (const file of pageFiles) {
    const source = read(`../src/app/pages/volunteer/${file}`);
    // The scan covers `to="..."` literals. A `to={...}` expression is one it
    // cannot see, so it is forbidden outright rather than skipped.
    assert.doesNotMatch(
      source,
      /\bto=\{/,
      `${file} has a computed Link target this test cannot check`,
    );
    for (const match of source.matchAll(/\bto="([^"]+)"/g)) {
      const target = match[1];
      // Relative targets resolve inside the volunteer shell the page renders
      // under; only absolute ones can escape the portal.
      if (!target.startsWith("/")) continue;
      assert.ok(
        registered.has(target),
        `${file} links to ${target}, which is not a registered volunteer route`,
      );
    }
  }
});
