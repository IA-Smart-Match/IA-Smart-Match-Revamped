/**
 * The "five quick questions" profile-card mock-up (one screen, instructor
 * shows it).
 *
 * Requirements row "Asking for more" — *"A one-screen mock-up of the 'five
 * quick questions' card for the instructor to show"* — and
 * `docs/plans/backlog.md`. The requirements name the card's contents only as
 * "stated interests and career goals"; they never enumerate five questions.
 * The five below are therefore taken from what the documents *do* name as a
 * profile's own fields — design spec §2's `exercise_profile` columns
 * (`major`, `class_year`, `stated_interests`, `career_goal`,
 * `past_event_keys`) — which are exactly the fields the four adjustable
 * factors and the tie-break read. Nothing is invented; `hidden_true_interests`
 * is deliberately not among them (ADR-0025 D6).
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

test("shows exactly five questions", () => {
  const questions = mockup.match(/prompt: "/g) ?? [];
  assert.equal(questions.length, 5);
});

test("the five questions are the profile fields the documents name", () => {
  for (const field of ["major", "class_year", "stated_interests", "career_goal", "past_event"]) {
    assert.ok(mockup.includes(field), `missing question for ${field}`);
  }
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
    assert.match(mockup, /disabled/);
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

test("one route opens it, and it sits behind no authentication", () => {
  assert.match(routes, /ProfileCardMockup/);
  assert.match(routes, /path: "exercise\/profile-card"/);
  // Exactly one mount: one address for the instructor, never a second.
  assert.equal((routes.match(/<ProfileCardMockup /g) ?? []).length, 1);
});
