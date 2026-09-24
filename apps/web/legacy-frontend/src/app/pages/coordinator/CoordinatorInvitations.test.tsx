/**
 * B26 T4 (plan §7, test 33): the compose page words availability on each row
 * and keeps the row selectable (the server decides at compose), and words the
 * two new skip tokens.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RecipientRow, describeSkip } from "./CoordinatorInvitations";

afterEach(cleanup);

describe("describeSkip", () => {
  it("words both availability tokens", () => {
    expect(describeSkip("speaker_unavailable_on_date")).toBe(
      "The Speaker said they cannot speak on this date.",
    );
    expect(describeSkip("speaker_invitations_paused")).toBe("The Speaker has paused invitations.");
  });
});

describe("RecipientRow", () => {
  it("shows the availability and stays selectable", () => {
    render(
      <ul>
        <RecipientRow
          recipient={{
            subjectId: "speaker-a",
            contact: null,
            channels: [],
            channelsError: null,
            availability: {
              verdict: "excluded",
              state: "blacked_out",
              reason: "window",
              as_of: "2026-10-01",
              paused_until: null,
              changed_since_run: false,
            },
          }}
          verdict={{
            selectable: true,
            explanation: "Active.",
            address: "a@synthetic.invalid",
          }}
          selected={false}
          onToggle={() => undefined}
        />
      </ul>,
    );
    expect(screen.getByText(/Unavailable on this date \(Speaker's statement\)/)).toBeTruthy();
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(false);
  });
});
