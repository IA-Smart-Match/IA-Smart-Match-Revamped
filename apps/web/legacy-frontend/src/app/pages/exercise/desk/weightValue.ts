/**
 * Weight parsing and display for the weight slider (DESIGN.md §6.6).
 *
 * `strictDecimal` and the two field messages are the same rule and the same
 * words `WeightsControls.tsx` ships today, and a typed weight is committed
 * exactly as typed — never clamped — so moving the matching screen onto the
 * slider changes no behaviour and no copy. The server owns the range: it
 * refuses a negative weight in its own sentence and refuses a fraction or a
 * weight above 10 ("refuse, never repair"). `clampWeight` is for the thumb's position and
 * for values the slider itself produces, never for a typed commit.
 */

export const WEIGHT_MIN = 0;
/** Whole numbers 0-10 (Dr. Wang's 3/3/2/2 defaults). Older saved fractions still display. */
export const WEIGHT_MAX = 10;
export const WEIGHT_STEP = 1;
export const WEIGHT_PAGE_STEP = 5;

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
    : `"${text}" is not a plain number. Use a whole number from 0 to 10, like 3.`;
}

/** Keep a value on the slider's 0–10 range: the thumb's position and slider-driven commits only. */
export function clampWeight(value: number): number {
  return Math.min(WEIGHT_MAX, Math.max(WEIGHT_MIN, value));
}

/** Remove binary noise such as 0.45000000000000007, keeping up to 6 places. */
export function tidyWeight(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

/** A whole weight plain ("3"); an older saved fraction with two decimals ("0.40") or exact ("0.333"). */
export function formatWeight(value: number): string {
  if (Number.isInteger(value)) {
    return String(value);
  }
  const hundredths = value * 100;
  return Math.abs(hundredths - Math.round(hundredths)) < 1e-9 ? value.toFixed(2) : String(value);
}

/**
 * The weights added up, free of binary noise (0.1 + 0.2 is 0.3, not
 * 0.30000000000000004). Never capped at 1 and never rescaled: the scorer
 * divides each weight by this total, so only how the weights compare matters.
 */
export function weightTotal(values: readonly number[]): number {
  return tidyWeight(values.reduce((sum, value) => sum + value, 0));
}

/** The total as the team reads it: "10" for whole weights, two decimals for older fractions ("1.00"). Never a percentage. */
export function formatWeightTotal(total: number): string {
  return Number.isInteger(total) ? String(total) : total.toFixed(2);
}
