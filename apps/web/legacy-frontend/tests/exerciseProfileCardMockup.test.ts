/**
 * The profile-card mock-up (one screen, instructor shows it).
 *
 * Requirements row "Asking for more" — *"A one-screen mock-up of the 'five
 * quick questions' card for the instructor to show"* — and
 * `docs/plans/backlog.md`. OQ-CE-11 closed 2026-09-25 (Ann Wang, email reply
 * to the team's question list): the card asks **only** for stated interests
 * and career goal. Major and year are already on file, and past events are
 * recorded by the app, so neither is asked; on activation a student just
 * confirms the major on file. `hidden_true_interests` is never asked
 * (ADR-0025 D6).
 *
 * These are source assertions, matching this suite's existing convention
 * (`branding.test.ts`, `legacyRedirects.test.ts`): the repository has no DOM
 * renderer, and adding one for a static mock-up would be a larger change than
 * the mock-up.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const mockup = readFileSync(
  new URL("../src/app/pages/exercise/ProfileCardMockup.tsx", import.meta.url),
  "utf8",
);
const routes = readFileSync(new URL("../src/app/routes.tsx", import.meta.url), "utf8");

test("asks exactly two questions: stated interests and career goal (OQ-CE-11)", () => {
  const questions = mockup.match(/prompt: "/g) ?? [];
  assert.equal(questions.length, 2);
  for (const field of ["stated_interests", "career_goal"]) {
    assert.ok(mockup.includes(`field: "${field}"`), `missing question for ${field}`);
  }
});

test("never asks for year or past events, which are already on file", () => {
  assert.equal(/class_year|past_event/.test(mockup), false);
});

test("shows the major on file with a confirm step instead of asking for it", () => {
  assert.match(mockup, /data-slot="exercise-card-major-confirm"/);
  assert.match(mockup, /Confirm your major/);
  assert.equal(/field: "major"/.test(mockup), false);
});

test("never asks for the hidden true interests (ADR-0025 D6)", () => {
  assert.equal(/hidden_true_interests|hiddenTrueInterests/.test(mockup), false);
});

test("is marked as synthetic on the screen itself", () => {
  assert.match(mockup, /SyntheticDataBanner/);
  assert.match(mockup, /components\/provenance/);
});

test("has no submit that pretends to save and no success state", () => {
  assert.equal(/onSubmit|<form|useMutation|fetch\(|apiFetch/.test(mockup), false);
  assert.equal(/Thanks|Saved|Submitted|success/i.test(mockup), false);
});

test("any control on the screen is visibly inert and says so", () => {
  // A button is allowed only if it cannot be pressed and is labelled as part
  // of the mock-up, so nobody in the room believes a card was filed.
  if (/<button|<Button/.test(mockup)) {
    // Every button, not just one: count the openings against the `disabled`s.
    const buttons = (mockup.match(/<button\b/g) ?? []).length;
    const disabled = (mockup.match(/<button\b[^>]*\sdisabled\s/g) ?? []).length;
    assert.equal(disabled, buttons);
    assert.match(mockup, /mock-up/i);
  }
});

test("shows no numeric score, percentage, or confidence (ADR-0025 D8)", () => {
  assert.equal(/score|confidence|percent|%/i.test(mockup), false);
});

test("names no speaker and carries no portal shell or session gate", () => {
  assert.equal(/speaker/i.test(mockup), false);
  assert.equal(/SessionGate|PortalLayout/.test(mockup), false);
});

test("is sized for a projector", () => {
  assert.match(mockup, /text-(xl|2xl|3xl|4xl)/);
  assert.equal(/text-(xs|sm)\b/.test(mockup), false);
});

test("the card's contents are confirmed, and the screen is still a mock-up (OQ-CE-11)", () => {
  // OQ-CE-11 closed 2026-09-25 (Ann Wang, email reply). A "stand-in until Ann
  // confirms" left behind would be untrue.
  assert.equal(/stand-in|until Ann confirms|is open too/i.test(mockup), false);
  assert.equal(/Five quick questions/.test(mockup), false, "the heading must not say five");
  assert.match(mockup, /OQ-CE-11 closed 2026-09-25/);
  assert.match(mockup, /Mock-up only/);
});

test("one route opens it, and it sits behind no authentication", () => {
  assert.match(routes, /ProfileCardMockup/);
  assert.match(routes, /path: "exercise\/profile-card"/);
  // Exactly one mount: one address for the instructor, never a second.
  assert.equal((routes.match(/<ProfileCardMockup /g) ?? []).length, 1);
});
