/**
 * B26 T4 (plan §7, test 33): the compose page words availability on each row
 * and keeps the row selectable (the server decides at compose), and words the
 * two new skip tokens.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ApiRequestError, type MatchLoad } from "../../../lib/api";
import { RecipientRow, describeComposeRefusal, describeSkip } from "./CoordinatorInvitations";

afterEach(cleanup);

describe("describeSkip", () => {
  it("words both availability tokens", () => {
    expect(describeSkip("speaker_unavailable_on_date")).toBe(
      "The Speaker said they cannot speak on this date.",
    );
    expect(describeSkip("speaker_invitations_paused")).toBe("The Speaker has paused invitations.");
  });
});

describe("describeComposeRefusal", () => {
  it("words a run with no linked Speaker Request for a Connector", () => {
    const refusal = new ApiRequestError(
      "Name the Speaker Request this batch invites for.",
      422,
      "speaker_invitation_request_required",
    );
    expect(describeComposeRefusal(refusal)).toBe(
      "This run was made before Speaker Requests were linked. Start a new match run from the Speaker Request.",
    );
  });

  it("passes any other server refusal through verbatim", () => {
    const refusal = new ApiRequestError("Too many requests.", 429, "rate_limited");
    expect(describeComposeRefusal(refusal)).toBe("Too many requests.");
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

describe("RecipientRow load (B26 T8d V-F)", () => {
  function row(loadRecorded: boolean, load: MatchLoad | null) {
    render(
      <ul>
        <RecipientRow
          recipient={{
            subjectId: "speaker-a",
            contact: null,
            channels: [],
            channelsError: null,
            availability: null,
            load,
          }}
          verdict={{ selectable: true, explanation: "Active.", address: "a@synthetic.invalid" }}
          selected={false}
          onToggle={() => undefined}
          loadRecorded={loadRecorded}
        />
      </ul>,
    );
    return screen.getByRole("listitem").textContent ?? "";
  }

  it("RecipientRow shows Workload when matched for a 3.x run", () => {
    expect(row(true, { band: "moderate", reason: "measured" })).toContain(
      "Workload when matched: Moderate",
    );
  });

  it("says not recorded when a 3.x run carries no load for the row", () => {
    expect(row(true, null)).toContain("Workload not recorded for this Speaker");
  });

  it("nothing for a 2.0.0 run", () => {
    const text = row(false, null);
    expect(text).not.toContain("Workload");
  });
});
