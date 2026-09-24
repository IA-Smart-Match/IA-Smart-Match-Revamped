/**
 * B26 T4 (plan §7, test 34): a dispatch's `not_dispatched` reasons include the
 * two availability tokens, and the outreach page words them.
 */
import { describe, expect, it } from "vitest";

import { describeSkip } from "./CoordinatorOutreach";

describe("describeSkip", () => {
  it("words both availability tokens", () => {
    expect(describeSkip("speaker_unavailable_on_date")).toBe(
      "The Speaker said they cannot speak on this date.",
    );
    expect(describeSkip("speaker_invitations_paused")).toBe("The Speaker has paused invitations.");
  });

  it("still reports an unknown token verbatim", () => {
    expect(describeSkip("something_new")).toBe('The server reported "something_new".');
  });
});
