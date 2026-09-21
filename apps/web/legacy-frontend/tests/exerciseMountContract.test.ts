/**
 * The rules about the exercise's *source*, not its behaviour.
 *
 * Each of these is a property of the tree rather than of one render, which is
 * why it is asserted by reading files rather than by mounting a component:
 * a rule like "no screen calls `fetch` itself" is only true if it is true of
 * every screen, including the one added next week, and no component test can
 * say that.
 *
 * Runs under `node --test tests/`, which strips TypeScript types but cannot
 * compile JSX — so this file reads the screens as text and never imports one.
 * The rendered behaviour lives in the `*.test.tsx` files beside the screens.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const EXERCISE_DIR = fileURLToPath(new URL("../src/app/pages/exercise/", import.meta.url));
const API_MODULE = fileURLToPath(new URL("../src/lib/exerciseApi.ts", import.meta.url));
const CLIENT_MODULE = fileURLToPath(new URL("../src/lib/exerciseClient.ts", import.meta.url));
const ROUTES = fileURLToPath(new URL("../src/app/routes.tsx", import.meta.url));

/**
 * The module's code with its comments removed.
 *
 * Every rule below is about what the code *does*, and the comments explain at
 * length what it deliberately does not do — an explanation that names `/api`
 * or names the removed reset route would otherwise fail the very test it is
 * explaining. Crude on purpose: it does not need to parse TypeScript, only to
 * drop `/* … *​/` and `//` runs.
 */
function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

/** Every screen and helper in the exercise directory, excluding its tests. */
function exerciseSources(): { name: string; text: string }[] {
  return readdirSync(EXERCISE_DIR)
    .filter((name) => /\.tsx?$/.test(name) && !name.includes(".test."))
    .map((name) => ({ name, text: withoutComments(readFileSync(EXERCISE_DIR + name, "utf8")) }));
}

const CLIENT = withoutComments(readFileSync(CLIENT_MODULE, "utf8"));
const API = withoutComments(readFileSync(API_MODULE, "utf8"));

test("no exercise module ever builds an /api path", () => {
  // The workspace cookie is Path=/v1/exercise and the instructor cookie
  // Path=/v1/exercise/instructor. A call through /api reaches the same backend
  // and carries no cookie: every screen would say "enter your team number"
  // with nothing on the screen explaining why.
  const offenders: string[] = [];
  for (const { name, text } of [
    ...exerciseSources(),
    { name: "lib/exerciseApi.ts", text: API },
    { name: "lib/exerciseClient.ts", text: CLIENT },
  ]) {
    // Match a quoted path beginning `/api`, which is how such a call would be
    // written. The word "api" inside a comment or an identifier is not one.
    if (/["'`]\/api\b/.test(text)) {
      offenders.push(name);
    }
  }
  assert.deepEqual(offenders, []);
});

test("no screen writes the prefix; the transport module states it", () => {
  assert.match(API, /export const EXERCISE_API_BASE = "\/v1\/exercise";/);
  // `exerciseClient.rankedListCsvHref` builds a plain href for an <a download>
  // rather than going through `fetch`, so it is the one other place the prefix
  // is written. Nothing in `pages/exercise/` may write it.
  assert.match(CLIENT, /\/v1\/exercise\/workspaces\/current\/events\//);
  const offenders = exerciseSources()
    .filter(({ text }) => text.includes("/v1/exercise"))
    .map(({ name }) => name);
  assert.deepEqual(offenders, []);
});

test("no exercise screen calls fetch directly", () => {
  // DESIGN.md: pages and presentational components must not call `fetch`;
  // transport lives at a boundary. For this product that boundary is
  // `lib/exerciseApi.ts`, not `lib/api.ts` (ADR-0025 D1).
  const offenders = exerciseSources()
    .filter(({ text }) => /\bfetch\s*\(/.test(text))
    .map(({ name }) => name);
  assert.deepEqual(offenders, []);
});

test("no exercise screen reaches into the CBA app", () => {
  // ADR-0025 D1: no portal shell, no SessionGate, no auth context, no CBA API
  // client on an exercise route. An import edge is how each of those would
  // arrive, so the edge is what is forbidden.
  const forbidden = [
    /from "[^"]*\/lib\/api"/,
    /from "[^"]*useSession"/,
    /from "[^"]*usePortalAccess"/,
    /from "[^"]*PortalGate"/,
    /from "[^"]*SessionGate"/,
    /from "[^"]*queryClient"/,
    /from "[^"]*\/pages\/AIMatching"/,
    /@tanstack\/react-query/,
  ];
  const offenders: string[] = [];
  for (const { name, text } of exerciseSources()) {
    for (const pattern of forbidden) {
      if (pattern.test(text)) {
        offenders.push(`${name}: ${pattern.source}`);
      }
    }
  }
  assert.deepEqual(offenders, []);
});

test("no team screen renders a reset control", () => {
  // PR #186, owner ruling of 2026-09-19: the team's own reset route is removed
  // and answers 404. The only reset is the instructor's, behind the passcode.
  // Every module that may mention one carries `Instructor` in its file name.
  const offenders = exerciseSources()
    .filter(({ name }) => !name.includes("Instructor"))
    // A leading word boundary only: `resetTeamWorkspace` is a hit,
    // `compareSettings` — which contains the letters — is not.
    .filter(({ text }) => /\breset/i.test(text))
    .map(({ name }) => name);
  assert.deepEqual(offenders, []);
});

test("the instructor page is the one that does reset", () => {
  const instructor = exerciseSources().filter(({ name }) => name.includes("Instructor"));
  assert.ok(instructor.length > 0, "the instructor page must exist");
  assert.ok(
    instructor.some(({ text }) => text.includes("resetTeamWorkspace")),
    "the instructor page must offer the per-team reset",
  );
  assert.match(CLIENT, /\/instructor\/workspaces\/\$\{teamNumber\}\/reset/);
  // And the removed team route is not reachable from the client at all.
  assert.ok(!/workspaces\/current\/reset/.test(CLIENT));
});

test("no exercise module writes a factor key as display text", () => {
  // The four rulebook keys are wire names. Ann's words for them arrive on every
  // list response as `factor_labels`, and that is the only thing a screen may
  // print (design spec §16, requirements "Matching" row).
  const keys = [
    "stated_interest_overlap",
    "career_goal_fit",
    "past_event_topic_overlap",
  ];
  for (const { name, text } of exerciseSources()) {
    for (const key of keys) {
      // A key may appear inside a JSX expression only as an object lookup.
      // Between JSX tags — `>same_major<` — it is being rendered.
      assert.ok(
        !new RegExp(`>\\s*${key}\\s*<`).test(text),
        `${name} renders the factor key ${key} instead of its label`,
      );
    }
  }
});

test("the settings cap is read from the response, not written into a screen", () => {
  // `max_settings` comes back on every settings response, so a cap written
  // into a screen would be a second source of truth for a number the server
  // enforces under a lock.
  for (const { name, text } of exerciseSources()) {
    assert.ok(
      !/max_?[Ss]ettings\s*[=:]\s*3\b/.test(text),
      `${name} writes the settings cap into the screen`,
    );
  }
  const panel = exerciseSources().find(({ name }) => name === "SavedSettingsPanel.tsx");
  assert.ok(panel !== undefined, "the saved-settings panel must exist");
  assert.match(panel.text, /saved\.max_settings/);
});

test("the asking screen offers the server's choices, not a list of its own", () => {
  const asking = exerciseSources().find(({ name }) => name === "ExerciseAskingForMore.tsx");
  assert.ok(asking !== undefined, "the asking-for-more screen must exist");
  // The set comes from `choices` on the response; only the wording of each is
  // local, in `askingChoices.ts`, because the API returns no label for them.
  assert.match(asking.text, /asking\.choices\.map/);
  assert.ok(
    !/better_recommendations|small_reward/.test(asking.text),
    "the asking screen writes the choices into itself instead of reading `choices`",
  );
  const labels = exerciseSources().find(({ name }) => name === "askingChoices.ts");
  assert.ok(labels !== undefined);
  // An unrecognised choice falls back to itself rather than being swallowed.
  assert.match(labels.text, /ASKING_CHOICE_LABELS\[choice\] \?\? choice/);
});

/** The six screens design spec §16 names, as the files that render them. */
const SCREENS = [
  "ExerciseEntry.tsx",
  "ExerciseEventPicker.tsx",
  "ExerciseMatching.tsx",
  "ExerciseAskingForMore.tsx",
  "ExerciseResults.tsx",
  "ExerciseInstructor.tsx",
] as const;

test("every exercise screen is framed by ExerciseScreen, which carries the marker", () => {
  // Design spec §16 asks for the synthetic-data marker on every screen. The
  // frame renders it, so "every screen" is kept by every screen using the
  // frame rather than by six screens each remembering.
  const sources = exerciseSources();
  for (const screen of SCREENS) {
    const found = sources.find(({ name }) => name === screen);
    assert.ok(found !== undefined, `${screen} is missing`);
    assert.ok(
      found.text.includes("<ExerciseScreen"),
      `${screen} does not render inside ExerciseScreen, so it carries no synthetic-data marker`,
    );
  }
  assert.ok(
    readFileSync(EXERCISE_DIR + "ExerciseScreen.tsx", "utf8").includes("<SyntheticDataBanner"),
    "ExerciseScreen must render the synthetic-data marker",
  );
});

test("no exercise screen shows a score, a percentage or a confidence", () => {
  // ADR-0025 D8: the exercise shows rank, the four weights the team set, and
  // one reason per name. Counts and seats are fine; anything named like a
  // measurement of a person is not.
  const forbidden = /\b(score|percent|percentage|confidence|probability|likelihood)\b/i;
  for (const screen of SCREENS) {
    const found = exerciseSources().find(({ name }) => name === screen);
    assert.ok(found !== undefined);
    // Comments explain why these words are absent, so only rendered text is
    // checked: anything between a `>` and a `<` inside JSX.
    const rendered = [...found.text.matchAll(/>([^<>{}]{3,})</g)].map((match) => match[1]);
    for (const text of rendered) {
      assert.ok(!forbidden.test(text), `${screen} renders score-shaped text: ${text.trim()}`);
    }
  }
});

test("the exercise routes are mounted", () => {
  const routes = readFileSync(ROUTES, "utf8");
  for (const path of [
    "exercise/profile-card",
    "exercise",
    "exercise/events",
    "exercise/instructor",
  ]) {
    assert.ok(routes.includes(`"${path}"`), `routes.tsx does not mount ${path}`);
  }
});

// ADR-0025 D9 — "the word in code is `exercise`" — is deliberately *not*
// asserted here. `tools/scan_forbidden.py` already enforces it across the
// whole repository, and a copy of the rule in this file would have to spell
// the forbidden identifiers out to match them, which trips the real scanner on
// this very file. The rule has an owner; this file is not it.
