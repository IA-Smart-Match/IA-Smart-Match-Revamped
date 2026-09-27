/**
 * The class exercise's colour tokens, as data.
 *
 * `src/styles/exercise.css` is what the browser reads; this table is what the
 * contrast test reads, and a parity test keeps the two identical. Values are
 * `docs/design/class-exercise/DESIGN.md` §3.1 (light) and §3.2 (dark). Every
 * one is an alias, tint or shade of a value already in `theme.css`; no new
 * brand colour is introduced.
 *
 * Four "on-*" tokens are added so a text colour is never hard-coded next to
 * a fill: `on-primary-tint` (§3.1 names `#003D24` for it), `on-gold` (§3.1
 * names `#17352A`), `on-danger` (`--destructive-foreground`). In dark mode
 * they take the matching `.dark` theme values so the pairs still pass.
 * `avocado-tint` has no §3.2 value; dark uses `.dark --input` (`#29473B`).
 */

export const CE_COLOR_TOKENS = [
  "page",
  "surface",
  "surface-sunk",
  "ink",
  "ink-muted",
  "primary",
  "on-primary",
  "primary-tint",
  "on-primary-tint",
  "gold",
  "on-gold",
  "gold-tint",
  "gold-ink",
  "avocado",
  "avocado-tint",
  "bay",
  "seat-taken",
  "line",
  "line-strong",
  "danger",
  "on-danger",
] as const;

export type CeColorToken = (typeof CE_COLOR_TOKENS)[number];

export type CePalette = Readonly<Record<CeColorToken, string>>;

export const CE_COLORS: Readonly<{ light: CePalette; dark: CePalette }> = {
  light: {
    page: "#F8F6F1",
    surface: "#FFFFFF",
    "surface-sunk": "#F2EEE8",
    ink: "#163229",
    "ink-muted": "#59665F",
    primary: "#005030",
    "on-primary": "#FFFFFF",
    "primary-tint": "#D9EADF",
    "on-primary-tint": "#003D24",
    gold: "#FFB81C",
    "on-gold": "#17352A",
    "gold-tint": "#FFF1CC",
    "gold-ink": "#7A5200",
    avocado: "#A4D65E",
    "avocado-tint": "#E8F2D8",
    bay: "#CFBAB0",
    "seat-taken": "#8C6D62",
    line: "#D9CBC4",
    "line-strong": "#8F7A70",
    danger: "#BA1A1A",
    "on-danger": "#FFFFFF",
  },
  dark: {
    page: "#10251D",
    surface: "#173228",
    "surface-sunk": "#244237",
    ink: "#F2EEE8",
    "ink-muted": "#CFC5BE",
    primary: "#A4D65E",
    "on-primary": "#10251D",
    "primary-tint": "#315343",
    "on-primary-tint": "#F2EEE8",
    gold: "#FFB81C",
    "on-gold": "#10251D",
    "gold-tint": "#3A3420",
    "gold-ink": "#FFD37A",
    avocado: "#A4D65E",
    "avocado-tint": "#29473B",
    bay: "#CFBAB0",
    "seat-taken": "#B89A8E",
    line: "#496257",
    "line-strong": "#8FA89C",
    danger: "#FFB4AB",
    "on-danger": "#690005",
  },
};

/** Every pair that carries text: [foreground, background]. Must reach 4.5:1. */
export const CE_TEXT_PAIRS: ReadonlyArray<readonly [CeColorToken, CeColorToken]> = [
  ["ink", "page"],
  ["ink", "surface"],
  ["ink", "surface-sunk"],
  ["ink", "gold-tint"],
  ["ink", "avocado-tint"],
  ["ink", "primary-tint"],
  ["ink-muted", "page"],
  ["ink-muted", "surface"],
  ["ink-muted", "surface-sunk"],
  ["primary", "surface"],
  ["primary", "page"],
  ["on-primary", "primary"],
  ["on-primary-tint", "primary-tint"],
  ["on-gold", "gold"],
  ["gold-ink", "surface"],
  ["gold-ink", "page"],
  ["gold-ink", "gold-tint"],
  ["danger", "surface"],
  ["danger", "page"],
  ["on-danger", "danger"],
];

/** Control outlines, seat fills, the slider track and the thumb ring. Must reach 3:1. */
export const CE_NON_TEXT_PAIRS: ReadonlyArray<readonly [CeColorToken, CeColorToken]> = [
  ["line-strong", "page"],
  ["line-strong", "surface"],
  ["seat-taken", "surface"],
  ["primary", "surface"],
  ["primary", "surface-sunk"],
  ["danger", "surface"],
];

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG 2.x relative luminance of a `#RRGGBB` colour. */
export function relativeLuminance(hex: string): number {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (match === null) {
    throw new Error(`Not a #RRGGBB colour: ${hex}`);
  }
  const [r, g, b] = match.slice(1).map((part) => channel(Number.parseInt(part, 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.x contrast ratio between two `#RRGGBB` colours, order-independent. */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
