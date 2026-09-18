/**
 * The class exercise's "who is on the list" notice, in plain words.
 *
 * Requirements row "Who is on the list": *"A one-line notice when a major or
 * year that exists among the 300 has nobody on the list."* The Python side
 * (`smartmatch_domain/exercise_list_coverage.py`) decides *which* groups are
 * uncovered; this module decides only how that reads on a screen, so both
 * halves stay testable without a server, a table, or a route.
 *
 * The wording tests below pin the notice's promise: one line, plain words, no
 * count and no percentage (ADR-0025 D8), and nothing at all to say when every
 * group is represented.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { coverageNoticeLine } from "../src/app/pages/exercise/listCoverageNotice.ts";

test("says nothing when every major and year is represented", () => {
  assert.equal(coverageNoticeLine({ missingMajors: [], missingClassYears: [] }), null);
});

test("names one missing major in plain words", () => {
  assert.equal(
    coverageNoticeLine({ missingMajors: ["Finance"], missingClassYears: [] }),
    "Nobody on this list is a Finance major.",
  );
});

test("names one missing year without calling it a major", () => {
  assert.equal(
    coverageNoticeLine({ missingMajors: [], missingClassYears: ["first-year"] }),
    "Nobody on this list is a first-year.",
  );
});

test("joins a major and a year with 'or'", () => {
  assert.equal(
    coverageNoticeLine({ missingMajors: ["Finance"], missingClassYears: ["first-year"] }),
    "Nobody on this list is a Finance major or a first-year.",
  );
});

test("joins three or more groups with commas and a final 'or'", () => {
  assert.equal(
    coverageNoticeLine({
      missingMajors: ["Finance", "Economics"],
      missingClassYears: ["first-year"],
    }),
    "Nobody on this list is a Finance major, an Economics major, or a first-year.",
  );
});

test("chooses the article by the label's own first letter, not by a list of majors", () => {
  assert.equal(
    coverageNoticeLine({ missingMajors: ["Accounting"], missingClassYears: [] }),
    "Nobody on this list is an Accounting major.",
  );
});

test("keeps the order the caller supplied, majors before years", () => {
  assert.equal(
    coverageNoticeLine({
      missingMajors: ["Marketing", "Finance"],
      missingClassYears: ["senior", "junior"],
    }),
    "Nobody on this list is a Marketing major, a Finance major, a senior, or a junior.",
  );
});

test("does not mutate the arrays it is given", () => {
  const missingMajors = ["Finance"];
  const missingClassYears = ["senior"];
  coverageNoticeLine({ missingMajors, missingClassYears });
  assert.deepEqual(missingMajors, ["Finance"]);
  assert.deepEqual(missingClassYears, ["senior"]);
});

test("carries no count, percentage, or score in any wording it can produce", () => {
  const line = coverageNoticeLine({
    missingMajors: ["Finance", "Economics"],
    missingClassYears: ["first-year"],
  });
  assert.ok(line !== null);
  assert.equal(/[0-9]|%|score|confidence/i.test(line), false);
});

const notice = readFileSync(
  new URL("../src/app/pages/exercise/ListCoverageNotice.tsx", import.meta.url),
  "utf8",
);

test("the notice component renders one line from the shared wording helper", () => {
  assert.match(notice, /coverageNoticeLine/);
  // Nothing to say -> nothing rendered, per the requirements row.
  assert.match(notice, /return null/);
});

test("the notice component takes its groups as props rather than fetching them", () => {
  assert.equal(/fetch\(|useQuery|apiFetch/.test(notice), false);
});

test("the notice is sized for a projector", () => {
  // Design spec §16: "Type sizes chosen for a projector at classroom
  // distance." Anything at or below the app's default `text-sm` would not be
  // readable from the back of Dr. Lin's room.
  assert.match(notice, /text-(xl|2xl|3xl)/);
  assert.equal(/text-(xs|sm)\b/.test(notice), false);
});

test("the notice carries no CBA portal shell and no session gate", () => {
  assert.equal(/SessionGate|PortalLayout/.test(notice), false);
});
