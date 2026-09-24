/**
 * B26 T4 (plan §7, test 35): Q8's exclusion token is worded, and the table is
 * exported so the shortlist page words the stored list the same way.
 */
import { describe, expect, it } from "vitest";

import { MATCH_INELIGIBILITY_EXPLANATIONS } from "./CoordinatorMatchRuns";

describe("MATCH_INELIGIBILITY_EXPLANATIONS", () => {
  it("words filed_this_request", () => {
    expect(MATCH_INELIGIBILITY_EXPLANATIONS.filed_this_request).toBe(
      "Filed this request, so left out of its matching. To invite them anyway, add them to a batch by hand.",
    );
  });
});
