/**
 * Guards the CPP design-system port (Track A of the frontend-dev resync).
 *
 * Scoped deliberately to the files Track A owns: `LandingPage.tsx`, the four
 * navigation shells, and the design tokens. `Volunteers.tsx`, `Calendar.tsx`,
 * `Pipeline.tsx`, and `Outreach.tsx` are restyled by other tracks and are not
 * asserted on here — this file must not fail on content this track does not
 * touch.
 */
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const landing = readFileSync(new URL("../src/app/pages/LandingPage.tsx", import.meta.url), "utf8");
const adminLayout = readFileSync(new URL("../src/app/components/Layout.tsx", import.meta.url), "utf8");
const hostLayout = readFileSync(
  new URL("../src/app/components/CoordinatorPortalLayout.tsx", import.meta.url),
  "utf8",
);
const speakerLayout = readFileSync(
  new URL("../src/app/components/VolunteerPortalLayout.tsx", import.meta.url),
  "utf8",
);
const fonts = readFileSync(new URL("../src/styles/fonts.css", import.meta.url), "utf8");
const theme = readFileSync(new URL("../src/styles/theme.css", import.meta.url), "utf8");

/**
 * Strips `/* ... *\/` block comments and `//` line comments before checking
 * for forbidden out-of-scope claims — this file's own doc comments are
 * allowed to *discuss* what was removed (customer §20) without themselves
 * tripping the guard, mirroring `tests/unit/test_cba_surface_composition.py`'s
 * `_strip_comments`.
 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

const landingVisibleCopy = stripComments(landing);

test("landing page uses approved public copy without fabricated proof points", () => {
  assert.match(landing, /Match speakers with events where they can help most\./);
  assert.match(landing, /How Smart Match works/);
  assert.doesNotMatch(landing, /AI-Driven Volunteer Coordination/i);
  assert.doesNotMatch(landing, /View Demo/i);
  assert.doesNotMatch(landingVisibleCopy, /2,481|842|94%/);
  assert.doesNotMatch(landing, /demo/i);
  assert.doesNotMatch(landingVisibleCopy, /scraping|web crawler|CRM|in real-time/i);
});

test("landing page still describes the in-scope product", () => {
  assert.match(landing, /Sign in/);
  assert.match(landing, /Intelligent Matching/);
});

test("visible role names use the approved Smart Match terminology", () => {
  assert.match(adminLayout, /Speaker Connector/);
  assert.match(hostLayout, /Event Host/);
  assert.match(speakerLayout, /Speaker portal/);
  assert.match(landing, /Event Hosts/);
  assert.doesNotMatch(adminLayout, />\s*IA Admin\s*</);
});

test("landing page uses the CPP logo and a dynamic copyright year", () => {
  assert.match(landing, /cpp-horizontal-green\.png/);
  assert.match(landing, /alt="Cal Poly Pomona"/);
  assert.match(landing, /new Date\(\)\.getFullYear\(\)/);
  assert.match(landing, /Cal Poly Pomona\. All rights reserved\./);
});

test("landing and administrator headings use the simplified hierarchy", () => {
  assert.doesNotMatch(landing, /Volunteer coordination made clearer|A straightforward process/i);
  assert.doesNotMatch(adminLayout, /currentPage\.icon.*text-\[#/);
});

test("brand typography and colors have fallbacks", () => {
  assert.match(fonts, /font-family: "Transducer CPP"/);
  assert.match(fonts, /--font-subhead: "proxima-sera", Georgia, serif/);
  assert.match(fonts, /--font-body: "usual", Inter, ui-sans-serif/);
  for (const color of ["#005030", "#ffb81c", "#f2eee8", "#cfbab0", "#a4d65e"]) {
    assert.ok(theme.toLowerCase().includes(color), `missing brand color ${color}`);
  }
});
