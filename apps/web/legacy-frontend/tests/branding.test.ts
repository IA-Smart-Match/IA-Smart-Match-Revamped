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
/**
 * The one Speaker Connector shell.
 *
 * There used to be two, and this file read both: `Layout.tsx` for the stored
 * `admin` role and `CoordinatorPortalLayout.tsx` for `coordinator`. They were
 * never two jobs — `role_presentation.py` maps both roles onto the Speaker
 * Connector persona — so `Layout.tsx` is deleted and its addresses redirect
 * here. The brand assertions that used to be split across the two are made
 * once, against the shell that survived.
 */
const connectorLayout = readFileSync(
  new URL("../src/app/components/CoordinatorPortalLayout.tsx", import.meta.url),
  "utf8",
);
/**
 * The Event Host shell — customer §4's name for the `volunteer` persona. It
 * used to call itself "Speaker portal", a leftover from before the host
 * portal was separated from the speaker pages it sat beside; the brand now
 * comes from the portal grant's own `display_name`, as the Connector shell's
 * does.
 */
const hostLayout = readFileSync(
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
  // The Connector shell names the persona it serves. It no longer says "Event
  // Host": that persona is the *volunteer* shell's (customer §4 renamed
  // Volunteer → Event Host), and the coordinator shell saying it was a
  // leftover from before `admin` and `coordinator` were reconciled into one
  // Speaker Connector.
  assert.match(connectorLayout, /Speaker Connector/);
  // The host shell's brand is the server-granted `display_name` ("Event Host
  // Portal" through `role_presentation.py`), never a literal — a hard-coded
  // "Speaker portal" here is how event hosts got called speakers.
  assert.match(hostLayout, /label=\{grant\.display_name\}/);
  assert.doesNotMatch(stripComments(hostLayout), /Speaker portal/);
  assert.match(landing, /Event Hosts/);
  assert.doesNotMatch(connectorLayout, />\s*IA Admin\s*</);
});

test("the Connector shell is one shell for both stored Speaker Connector roles", () => {
  // The brand on screen is the portal descriptor's own `display_name`, which
  // both `coordinator` and `admin` resolve to through the one
  // role-presentation map — not a literal chosen in the component.
  assert.match(connectorLayout, /Connector Dashboard/);
  assert.match(connectorLayout, /label=\{grant\.display_name\}/);
  // One gate for both roles: the portal grant, never a role read in the
  // browser. `hasActiveRole` decides only which nav *group* is drawn.
  assert.match(connectorLayout, /grantedPortal\(portalAccess, "coordinator"\)/);
  assert.doesNotMatch(connectorLayout, /grantedPortal\([^)]*"admin"\)/);
  assert.match(connectorLayout, /hasActiveRole\(session\.me, "admin"\)/);
  // The admin shell had no sign-out at all. Its successor does.
  assert.match(connectorLayout, /Sign out/);
});

test("the Connector shell offers the Option A navigation groups", () => {
  for (const group of ["Inbox", "Coordinate", "People", "Administration"]) {
    assert.match(connectorLayout, new RegExp(`label: "${group}"`), `missing nav group ${group}`);
  }
  for (const item of [
    "Home",
    "Speaker requests",
    "Review queue",
    "Events",
    "Run a match",
    "Invitations",
    "Meetings",
    "Speakers",
    "Contact channels",
    "Matching weights",
  ]) {
    assert.match(connectorLayout, new RegExp(`name: "${item}"`), `missing nav item ${item}`);
  }
});

test("landing page uses the CPP logo and a dynamic copyright year", () => {
  assert.match(landing, /cpp-horizontal-green\.png/);
  assert.match(landing, /alt="Cal Poly Pomona"/);
  assert.match(landing, /new Date\(\)\.getFullYear\(\)/);
  assert.match(landing, /Cal Poly Pomona\. All rights reserved\./);
});

test("landing and Connector headings use the simplified hierarchy", () => {
  assert.doesNotMatch(landing, /Volunteer coordination made clearer|A straightforward process/i);
  // The original assertion banned a hard-coded hex on the deleted admin
  // shell's page-title strip. That strip is gone — `DESIGN.md` forbids a
  // desktop top bar repeating the page name the sidebar already shows — so
  // the successor assertion is the general rule it was an instance of: the
  // shell styles itself from semantic tokens, never a literal colour.
  assert.doesNotMatch(connectorLayout, /currentPage\.icon/);
  assert.doesNotMatch(connectorLayout, /#[0-9a-fA-F]{3,8}\b/);
});

test("brand typography and colors have fallbacks", () => {
  assert.match(fonts, /font-family: "Transducer CPP"/);
  assert.match(fonts, /--font-subhead: "proxima-sera", Georgia, serif/);
  assert.match(fonts, /--font-body: "usual", Inter, ui-sans-serif/);
  for (const color of ["#005030", "#ffb81c", "#f2eee8", "#cfbab0", "#a4d65e"]) {
    assert.ok(theme.toLowerCase().includes(color), `missing brand color ${color}`);
  }
});
