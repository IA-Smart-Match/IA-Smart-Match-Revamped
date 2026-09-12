/**
 * The student pages' internal links must land on routes the student portal
 * actually registers.
 *
 * The defect this guards was real: the repoint onto the `/v1` student reads
 * left `to="/events"`, `to="/rewards"`, and `to="/speaker-feedback"` behind —
 * absolute paths missing the `student-portal/` prefix. `/events` is a real
 * route, but it is the administrator's manual-events page behind a different
 * shell, so the link did not 404; it walked a student out of their portal
 * onto a surface that is not theirs. The other two pointed at nothing at all.
 *
 * The registered set is parsed out of `routes.tsx` rather than restated
 * here, so a route renamed in the router fails this test on the page that
 * still links to it instead of drifting out of sync with a copied list.
 */
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const routes = read("../src/app/routes.tsx");
const pageFiles = readdirSync(new URL("../src/app/pages/student/", import.meta.url)).filter(
  (name) => name.endsWith(".tsx"),
);

// The student shell's registered paths: `path: "student-portal"` opens the
// block, its `children:` array runs to the first `]` at the same four-space
// indentation, and every `path:` inside — plus the `index:` child — is a URL
// the portal serves.
const studentBlock = routes.match(
  /path: "student-portal"[\s\S]*?children: \[([\s\S]*?)\n {4}\]/,
);
assert.ok(studentBlock, "routes.tsx no longer nests student pages under student-portal");
const registered = new Set<string>(["/student-portal"]);
for (const match of studentBlock[1].matchAll(/path: "([^"]+)"/g)) {
  registered.add(`/student-portal/${match[1]}`);
}

test("the student shell still registers the routes its pages link to", () => {
  // Route-parity pinning: a route dropped from the router must fail loudly
  // here rather than strand a link on a page that still points at it.
  for (const path of ["events", "history", "connect", "rewards", "speaker-feedback"]) {
    assert.ok(
      registered.has(`/student-portal/${path}`),
      `routes.tsx no longer registers /student-portal/${path}`,
    );
  }
});

test("every absolute link target in pages/student/ is a registered student route", () => {
  assert.ok(pageFiles.length > 0, "no student pages found to check");
  for (const file of pageFiles) {
    const source = read(`../src/app/pages/student/${file}`);
    // The scan covers `to="..."` literals. A `to={...}` expression is one it
    // cannot see, so it is forbidden outright rather than skipped.
    assert.doesNotMatch(
      source,
      /\bto=\{/,
      `${file} has a computed Link target this test cannot check`,
    );
    for (const match of source.matchAll(/\bto="([^"]+)"/g)) {
      const target = match[1];
      // Relative targets resolve inside the student shell the page renders
      // under; only absolute ones can escape the portal.
      if (!target.startsWith("/")) continue;
      assert.ok(
        registered.has(target),
        `${file} links to ${target}, which is not a registered student route`,
      );
    }
  }
});
