/**
 * The weight total (DESIGN.md §6.6, owner ruling 2026-09-28): a plain sum,
 * two decimals, never capped at 1 and never a percentage.
 */
import { describe, expect, it } from "vitest";

import { formatWeightTotal, weightTotal } from "./weightValue";

describe("weightTotal / formatWeightTotal", () => {
  it("adds the four equal defaults to 1.00", () => {
    expect(formatWeightTotal(weightTotal([0.25, 0.25, 0.25, 0.25]))).toBe("1.00");
  });

  it("is safe against float error: 0.1 + 0.2 is 0.30", () => {
    expect(weightTotal([0.1, 0.2])).toBe(0.3);
    expect(formatWeightTotal(weightTotal([0.1, 0.2]))).toBe("0.30");
  });

  it("is not capped at 1", () => {
    expect(formatWeightTotal(weightTotal([2, 1.5, 0.5, 0.5]))).toBe("4.50");
  });

  it("is 0.00 when every weight is 0", () => {
    expect(weightTotal([0, 0, 0, 0])).toBe(0);
    expect(formatWeightTotal(weightTotal([0, 0, 0, 0]))).toBe("0.00");
    expect(formatWeightTotal(weightTotal([]))).toBe("0.00");
  });

  it("never formats as a percentage", () => {
    expect(formatWeightTotal(weightTotal([0.4, 0.25, 0.25, 0.1]))).not.toContain("%");
  });
});
