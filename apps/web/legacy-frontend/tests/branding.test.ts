import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const landing = readFileSync(new URL("../src/app/pages/LandingPage.tsx", import.meta.url), "utf8");
const adminLayout = readFileSync(new URL("../src/app/components/Layout.tsx", import.meta.url), "utf8");
const volunteers = readFileSync(new URL("../src/app/pages/Volunteers.tsx", import.meta.url), "utf8");
const calendar = readFileSync(new URL("../src/app/pages/Calendar.tsx", import.meta.url), "utf8");
const pipeline = readFileSync(new URL("../src/app/pages/Pipeline.tsx", import.meta.url), "utf8");
const outreach = readFileSync(new URL("../src/app/pages/Outreach.tsx", import.meta.url), "utf8");
const fonts = readFileSync(new URL("../src/styles/fonts.css", import.meta.url), "utf8");
const theme = readFileSync(new URL("../src/styles/theme.css", import.meta.url), "utf8");

test("landing page uses approved public copy without fabricated proof points", () => {
  assert.match(landing, /Match volunteers with events where they can help most\./);
  assert.match(landing, /How Smart Match works/);
  assert.doesNotMatch(landing, /AI-Driven Volunteer Coordination/i);
  assert.doesNotMatch(landing, /View Demo/i);
  assert.doesNotMatch(landing, /2,481|842|94%/);
  assert.doesNotMatch(landing, /demo/i);
});

test("landing page uses the CPP logo and a dynamic copyright year", () => {
  assert.match(landing, /cpp-horizontal-green\.png/);
  assert.match(landing, /alt="Cal Poly Pomona"/);
  assert.match(landing, /new Date\(\)\.getFullYear\(\)/);
  assert.match(landing, /Cal Poly Pomona\. All rights reserved\./);
});

test("landing and administrator headings use the simplified hierarchy", () => {
  assert.doesNotMatch(landing, /Volunteer coordination made clearer|A straightforward process/i);
  assert.doesNotMatch(adminLayout, /currentPage/);
  assert.match(adminLayout, /Sign out/);
  assert.doesNotMatch(volunteers, /Volunteer management/i);
  assert.doesNotMatch(calendar, /Master calendar/i);
  assert.doesNotMatch(pipeline, /<TrendingUp/);
  assert.doesNotMatch(outreach, /<Mail/);
});

test("brand typography and colors have fallbacks", () => {
  assert.match(fonts, /font-family: "Transducer CPP"/);
  assert.match(fonts, /--font-subhead: "proxima-sera", Georgia, serif/);
  assert.match(fonts, /--font-body: "usual", Inter, ui-sans-serif/);
  for (const color of ["#005030", "#ffb81c", "#f2eee8", "#cfbab0", "#a4d65e"]) {
    assert.ok(theme.toLowerCase().includes(color), `missing brand color ${color}`);
  }
});
