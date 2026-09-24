/**
 * `drilldownRowPreview` for pipeline rows (B26 T8a): a cancelled booking still
 * has `confirmed_at`, so the preview must say "cancelled", not "confirmed".
 */
import { describe, expect, it } from "vitest";

import { drilldownRowPreview } from "./metrics";

const base = {
  id: "row-1",
  matched_at: "2026-09-01T10:00:00Z",
  contacted_at: "2026-09-02T10:00:00Z",
  confirmed_at: "2026-09-03T10:00:00Z",
  attended_at: null,
  member_inquiry_at: null,
};

describe("drilldownRowPreview", () => {
  it('a pipeline drill-down row with cancelled_at previews as "cancelled"', () => {
    expect(drilldownRowPreview({ ...base, cancelled_at: "2026-09-04T10:00:00Z" }).status).toBe(
      "cancelled",
    );
  });

  it("a row without cancelled_at still previews its furthest stage", () => {
    expect(drilldownRowPreview({ ...base, cancelled_at: null }).status).toBe("confirmed");
    expect(drilldownRowPreview({ ...base, confirmed_at: null }).status).toBe("contacted");
  });
});
