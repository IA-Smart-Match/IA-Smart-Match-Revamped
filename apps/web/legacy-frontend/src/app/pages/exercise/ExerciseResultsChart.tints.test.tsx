/** Mass-email bar must be lighter than the list bar in both themes (Ann #413 results item 4). */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync("src/styles/exercise.css", "utf8");

function lum(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function token(block: string, name: string, fallbackBlock: string): string {
  const m = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(block);
  if (m) return m[1]!;
  const alias = new RegExp(`${name}:\\s*var\\((--[a-z-]+)\\)`).exec(fallbackBlock);
  return new RegExp(`${alias![1]}:\\s*(#[0-9a-fA-F]{6})`).exec(block)![1]!;
}

describe("chart tints", () => {
  it("light: mass-email fill lighter than list fill", () => {
    const light = css.slice(0, css.indexOf(".dark .ce-root"));
    const root = css.slice(css.indexOf(".ce-root {\n  /* §3.3"));
    expect(lum(token(light, "--ce-series-invited-fill", root))).toBeGreaterThan(
      lum(token(light, "--ce-series-attended-fill", root)),
    );
  });
  it("dark: mass-email fill lighter than list fill", () => {
    const i = css.lastIndexOf(".dark .ce-root,\n.ce-root.dark {\n  --ce-series-invited-fill");
    const dark = css.slice(i, css.indexOf("}", i));
    expect(lum(token(dark, "--ce-series-invited-fill", ""))).toBeGreaterThan(
      lum(token(dark, "--ce-series-attended-fill", "")),
    );
  });
});
