/**
 * B26 T4 (plan §7, test 32): the shortlist's availability wording, and the
 * stored `excluded` list. Wording by state only; no number but the date.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { MatchAvailability, MatchCandidateExplanation } from "../../lib/api";
import { CandidateCard, ExcludedCandidates, describeAvailability } from "./AIMatching";

afterEach(cleanup);

function availability(overrides: Partial<MatchAvailability>): MatchAvailability {
  return {
    verdict: "eligible",
    state: "available",
    reason: "clear",
    as_of: "2026-10-01",
    paused_until: null,
    changed_since_run: false,
    ...overrides,
  };
}

function candidate(view: MatchAvailability | null): MatchCandidateExplanation {
  return {
    subject_id: "speaker-a",
    heuristic_score: null,
    state: "unknown",
    score_label: "heuristic score",
    registry_version: "2.0.0-approved-oq-cba-004",
    formula_version: "cba-stage-b-1",
    unknown_factor_keys: [],
    factors: [],
    availability: view,
  };
}

function renderCard(view: MatchAvailability | null): string {
  render(
    <ul>
      <CandidateCard candidate={candidate(view)} registryVersion="2.0.0-approved-oq-cba-004" />
    </ul>,
  );
  return document.body.textContent ?? "";
}

describe("describeAvailability", () => {
  it.each([
    [availability({}), "Available"],
    [
      availability({
        verdict: "excluded",
        state: "blacked_out",
        reason: "window",
      }),
      "Unavailable on this date (Speaker's statement)",
    ],
    [
      availability({
        verdict: "excluded",
        state: "blacked_out",
        reason: "paused",
        paused_until: "2027-01-10",
      }),
      "Paused until January 10, 2027",
    ],
    [
      availability({
        verdict: "undetermined",
        state: "unknown",
        reason: "not_stated",
      }),
      "Availability not stated",
    ],
    [
      availability({
        verdict: "undetermined",
        state: "unknown",
        reason: "event_unresolved",
      }),
      "Event date not set, so availability was not checked",
    ],
    [null, "Availability not recorded for this run"],
  ])("words %j as %s", (view, text) => {
    expect(describeAvailability(view)).toBe(text);
  });

  it("appends changed since this run", () => {
    expect(describeAvailability(availability({ changed_since_run: true }))).toBe(
      "Available — changed since this run",
    );
  });
});

describe("CandidateCard", () => {
  it("renders the stored verdict's words", () => {
    const text = renderCard(
      availability({
        verdict: "excluded",
        state: "blacked_out",
        reason: "window",
      }),
    );
    expect(text).toContain("Unavailable on this date (Speaker's statement)");
    expect(text).not.toContain("%");
  });

  it("says not recorded for a run without availability", () => {
    expect(renderCard(null)).toContain("Availability not recorded for this run");
  });

  it("says changed since this run", () => {
    expect(renderCard(availability({ changed_since_run: true }))).toContain(
      "changed since this run",
    );
  });
});

describe("ExcludedCandidates", () => {
  it("words filed_this_request from the stored list", () => {
    render(
      <ExcludedCandidates excluded={[{ subject_id: "host-1", reason: "filed_this_request" }]} />,
    );
    expect(screen.getByText(/Filed this request, so left out of its matching/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("%");
  });

  it("shows the Speaker's name, falling back to the id", () => {
    render(
      <ExcludedCandidates
        excluded={[
          { subject_id: "host-1", reason: "filed_this_request" },
          { subject_id: "unnamed-2", reason: "speaker_profile_not_found" },
        ]}
        names={new Map([["host-1", "Dana Okafor"]])}
      />,
    );
    const text = document.body.textContent ?? "";
    expect(text).toContain("Dana Okafor");
    expect(text).not.toContain("host-1");
    expect(text).toContain("unnamed-2");
  });

  it("renders nothing for an empty list", () => {
    const { container } = render(<ExcludedCandidates excluded={[]} />);
    expect(container.textContent).toBe("");
  });
});
