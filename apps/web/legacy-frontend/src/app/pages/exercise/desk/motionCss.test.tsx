/**
 * Rules in `exercise-motion.css` that jsdom cannot run: asserted on the text.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Vitest runs from the frontend root (see vitest.config.ts).
const css = readFileSync(path.resolve(process.cwd(), "src/styles/exercise-motion.css"), "utf8");

/** The body of the first `selector { … }` rule after `from` (index into css). */
function ruleBody(selector: string, from = 0): string {
  const start = css.indexOf(selector, from);
  if (start < 0) {
    throw new Error(`No ${selector} in exercise-motion.css`);
  }
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

describe("reduced-motion ce-row-join", () => {
  it("holds the gold wash for 900ms and then lets it go", () => {
    const reducedBlock = css.indexOf("@media (prefers-reduced-motion: reduce)");
    const body = ruleBody(".ce-root .ce-row-join", reducedBlock);
    expect(body).toMatch(/ce-kf-hold-gold/);
    expect(body).toMatch(/step-end/);
    // `both` / `forwards` would keep the last keyframe (gold) forever.
    expect(body).not.toMatch(/\b(both|forwards)\b/);
  });
});

describe("ce-seat-fill keyframes", () => {
  it("shows a seat as an open outline before its fill starts (§5.1 step 1)", () => {
    const keyframes = css.slice(css.indexOf("@keyframes ce-kf-seat-fill"));
    const from = ruleBody("from", css.length - keyframes.length);
    expect(from).toMatch(/background-color:\s*transparent/);
    expect(from).toMatch(/outline:\s*2px solid var\(--ce-seat-open-outline\)/);
    expect(from).toMatch(/outline-offset:\s*-2px/);
  });
});
