/**
 * The exercise colour tokens: every text pair clears WCAG 2.2 AA (4.5:1),
 * every non-text pair clears 3:1, and the CSS file carries exactly the values
 * the TypeScript table does — so the contrast this test proves is the
 * contrast the room sees.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  CE_COLORS,
  CE_NON_TEXT_PAIRS,
  CE_TEXT_PAIRS,
  contrastRatio,
  type CeColorToken,
} from "./tokens";

// Vitest runs from the frontend root (see vitest.config.ts).
const CSS_PATH = path.resolve(process.cwd(), "src/styles/exercise.css");
const css = readFileSync(CSS_PATH, "utf8");

/** The declarations inside the first rule whose selector list is exactly `selector`. */
function declarationsOf(selector: string): Record<string, string> {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  if (match === null) {
    throw new Error(`No rule for ${selector} in exercise.css`);
  }
  const out: Record<string, string> = {};
  for (const [, name, value] of match[2].matchAll(/(--ce-[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    out[name] = value.trim().toLowerCase();
  }
  return out;
}

describe("contrastRatio", () => {
  it("matches the WCAG reference values", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    // Order does not matter.
    expect(contrastRatio("#005030", "#ffffff")).toBeCloseTo(contrastRatio("#ffffff", "#005030"), 5);
  });
});

describe.each(["light", "dark"] as const)("%s tokens", (mode) => {
  const palette = CE_COLORS[mode];

  it.each(CE_TEXT_PAIRS)("text %s on %s is at least 4.5:1", (fg, bg) => {
    expect(contrastRatio(palette[fg], palette[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(CE_NON_TEXT_PAIRS)("non-text %s on %s is at least 3:1", (fg, bg) => {
    expect(contrastRatio(palette[fg], palette[bg])).toBeGreaterThanOrEqual(3);
  });
});

describe("exercise.css", () => {
  it("defines every light colour token on .ce-root with the table's value", () => {
    const declared = declarationsOf(".ce-root");
    for (const [token, value] of Object.entries(CE_COLORS.light)) {
      expect(declared[`--ce-${token as CeColorToken}`], token).toBe(value.toLowerCase());
    }
  });

  it("defines every dark colour token for .dark .ce-root with the table's value", () => {
    const declared = declarationsOf(".dark .ce-root,\n.ce-root.dark");
    for (const [token, value] of Object.entries(CE_COLORS.dark)) {
      expect(declared[`--ce-${token as CeColorToken}`], token).toBe(value.toLowerCase());
    }
  });

  it("scopes tokens to the exercise and never declares them on :root", () => {
    expect(/:root\s*\{[^}]*--ce-/.test(css)).toBe(false);
  });

  it("puts the logo on an eggwhite plate in dark mode only, with ≥3:1 contrast", () => {
    // The only logo asset is green on transparent; on the dark page it vanishes.
    const dark = /\.dark \.ce-root \.ce-logo\s*\{([^}]*)\}/.exec(css);
    expect(dark).not.toBeNull();
    expect(dark?.[1]).toMatch(/background-color:\s*var\(--cpp-eggwhite\)/);
    // No light-mode plate: light mode renders the logo exactly as CBA does.
    expect(/(^|\n)\.ce-root \.ce-logo\s*\{[^}]*background/.test(css)).toBe(false);
    const eggwhite = "#F2EEE8"; // theme.css --cpp-eggwhite, not redefined under .dark
    const wordmark = "#005030"; // the PNG's CPP Green
    expect(contrastRatio(wordmark, eggwhite)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(eggwhite, CE_COLORS.dark.page)).toBeGreaterThanOrEqual(3);
  });

  it("draws the 3px primary focus ring with a 3px offset", () => {
    expect(css).toMatch(/\.ce-root :focus-visible\s*\{[^}]*outline:\s*3px solid var\(--ce-primary\)/);
    expect(css).toMatch(/\.ce-root :focus-visible\s*\{[^}]*outline-offset:\s*3px/);
  });
});
