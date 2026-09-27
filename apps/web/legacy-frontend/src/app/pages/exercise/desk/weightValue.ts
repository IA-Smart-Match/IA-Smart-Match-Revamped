/**
 * Weight parsing and display for the weight slider (DESIGN.md §6.6).
 *
 * `strictDecimal` and the two field messages are the same rule and the same
 * words `WeightsControls.tsx` ships today, so moving the matching screen onto
 * the slider changes no behaviour and no copy.
 */

export const WEIGHT_MIN = 0;
export const WEIGHT_MAX = 1;
export const WEIGHT_STEP = 0.05;
export const WEIGHT_PAGE_STEP = 0.25;

/**
 * A strict decimal, ASCII digits only, or `null`. Accepts `.5`; rejects `5.`,
 * `1,5`, `0.5abc`, exponents, a leading `+` and the empty string —
 * `Number.parseFloat` would silently read a prefix of most of those.
 */
export function strictDecimal(text: string): number | null {
  if (!/^-?(\d+(\.\d+)?|\.\d+)$/.test(text)) {
    return null;
  }
  return Number(text);
}

/** The field's own message for text that is not a usable number. */
export function weightFieldMessage(text: string): string {
  return text.trim() === ""
    ? "Type a number for this weight."
    : `"${text}" is not a plain number. Use digits and one decimal point, like 0.5.`;
}

/** Keep a weight on the slider's 0–1 range. */
export function clampWeight(value: number): number {
  return Math.min(WEIGHT_MAX, Math.max(WEIGHT_MIN, value));
}

/** Remove binary noise such as 0.45000000000000007, keeping up to 6 places. */
export function tidyWeight(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

/** Two decimals when the value has at most two ("0.40"); otherwise exact ("0.333"). */
export function formatWeight(value: number): string {
  const hundredths = value * 100;
  return Math.abs(hundredths - Math.round(hundredths)) < 1e-9 ? value.toFixed(2) : String(value);
}
