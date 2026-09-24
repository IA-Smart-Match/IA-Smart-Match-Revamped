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

  it("the 202 excluded list words load_full with the Full label (B26 T8d V-G)", () => {
    expect(MATCH_INELIGIBILITY_EXPLANATIONS.load_full).toBe(
      "Full (no override available). Their confirmed and recent engagements exceed the hours they can give, so this run left them out.",
    );
  });
});
