/**
 * B26 T4 (plan §7, test 32): the shortlist's availability wording, and the
 * stored `excluded` list. Wording by state only; no number but the date.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  LoadBand,
  LoadReason,
  MatchAvailability,
  MatchCandidateExplanation,
  MatchLoad,
  MatchRunRead,
} from "../../lib/api";
import { CandidateCard, ExcludedCandidates, MatchRunView, describeAvailability } from "./AIMatching";

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

// ---------------------------------------------------------------------------
// B26 T8d V-E: the stored load band on run views (plan §6.2, §7.1)
// ---------------------------------------------------------------------------

function loaded(subjectId: string, load: MatchLoad | null | undefined): MatchCandidateExplanation {
  return { ...candidate(null), subject_id: subjectId, load };
}

function run(overrides: Partial<MatchRunRead> = {}): MatchRunRead {
  return {
    id: "run-one",
    unit_id: "unit-one",
    job_id: "job-one",
    event_need_id: "need-one",
    created_at: "2026-10-06T12:00:00Z",
    supersedes_run_id: null,
    score_label: "heuristic score",
    registry_version: "3.0.0-proposed",
    registry_hash: "hash",
    weights: {},
    optimizer_model_version: "opt",
    solver_name: "solver",
    solver_version: "v",
    route_estimate_source: "route",
    route_estimate_version: "v",
    inputs_hash: "inputs",
    portfolio_size: 2,
    random_seed: 7,
    portfolio_status: "optimal",
    shortlist: [],
    shortlist_available: true,
    shortlist_unavailable_reason: null,
    considered: [],
    unscorable: [],
    availability_recorded: true,
    excluded: [],
    load_recorded: true,
    ...overrides,
  };
}

function cardFor(subjectId: string): HTMLElement {
  const heading = screen.getByRole("heading", { level: 3, name: subjectId });
  return heading.closest("li") as HTMLElement;
}

/** The dd that follows the dt reading "Workload" inside `root`, or null. */
function workloadValue(root: HTMLElement): string | null {
  const term = Array.from(root.querySelectorAll("dt")).find((dt) => dt.textContent === "Workload");
  if (term === undefined) return null;
  return term.nextElementSibling?.textContent ?? null;
}

describe("MatchRunView load (V-E)", () => {
  const moderate: MatchLoad = { band: "moderate", reason: "measured" };

  it("a 2.0.0 run shows Not part of this run's matching and no workload row on any card", () => {
    render(
      <MatchRunView
        run={run({
          registry_version: "2.0.0-approved-oq-cba-004",
          load_recorded: false,
          shortlist: [loaded("short-a", null)],
          unscorable: [loaded("unscorable-a", null)],
          considered: [loaded("considered-a", null)],
        })}
      />,
    );
    const header = screen.getByText("Factor registry").closest("dl") as HTMLElement;
    expect(workloadValue(header)).toBe("Not part of this run's matching");
    for (const id of ["short-a", "unscorable-a", "considered-a"]) {
      expect(workloadValue(cardFor(id))).toBeNull();
      expect(cardFor(id).textContent).not.toContain("Workload");
    }
  });

  it("a 3.x run shows the band word on shortlist, unscorable and considered cards", () => {
    render(
      <MatchRunView
        run={run({
          shortlist: [loaded("short-a", moderate)],
          unscorable: [loaded("unscorable-a", { band: "light", reason: "measured" })],
          considered: [loaded("considered-a", { band: "heavy", reason: "measured" })],
        })}
      />,
    );
    const header = screen.getByText("Factor registry").closest("dl") as HTMLElement;
    expect(workloadValue(header)).toBe("Recorded per Speaker below");
    expect(workloadValue(cardFor("short-a"))).toBe("Moderate");
    expect(workloadValue(cardFor("unscorable-a"))).toBe("Light");
    expect(workloadValue(cardFor("considered-a"))).toBe("Heavy");
  });

  it.each([
    ["light", "measured", "Light", "Workload did not change the ranking."],
    ["moderate", "measured", "Moderate", "Ranked a little lower for workload."],
    ["heavy", "measured", "Heavy", "Ranked lower for workload."],
    [
      "unknown",
      "capacity_not_stated",
      "Load not measurable",
      "No capacity was stated, so workload did not change the ranking.",
    ],
    [
      "unknown",
      "hours_unknown",
      "Load not measurable",
      "Some confirmed engagements had no end time, so workload did not change the ranking. This Speaker's availability on Speaker contacts lists them.",
    ],
  ] as [LoadBand, LoadReason, string, string][])(
    "each run detail sentence follows band and reason (%s, %s)",
    (band, reason, word, detail) => {
      render(
        <ul>
          <CandidateCard
            candidate={loaded("speaker-a", { band, reason })}
            registryVersion="3.0.0-proposed"
            loadRecorded
          />
        </ul>,
      );
      const card = cardFor("speaker-a");
      expect(workloadValue(card)).toBe(word);
      expect(card.textContent).toContain(detail);
    },
  );

  it("excluded load_full reads Full (no override available); full_by_known_hours adds the end-time sentence", () => {
    render(
      <ExcludedCandidates
        excluded={[
          { subject_id: "full-a", reason: "load_full", load: { band: "full", reason: "measured" } },
          {
            subject_id: "full-b",
            reason: "load_full",
            load: { band: "full", reason: "full_by_known_hours" },
          },
        ]}
      />,
    );
    const [first, second] = screen.getAllByRole("listitem");
    expect(first.textContent).toContain(
      "Full (no override available). Their confirmed and recent engagements exceed the hours they can give, so this run left them out.",
    );
    expect(first.textContent).not.toContain("Some of their engagements also have no end time.");
    expect(second.textContent).toContain("Full (no override available).");
    expect(second.textContent).toContain("Some of their engagements also have no end time.");
  });

  it("load_recorded true with a null load reads Workload not recorded for this Speaker", () => {
    render(
      <MatchRunView
        run={run({ shortlist: [loaded("short-a", null), loaded("short-b", undefined)] })}
      />,
    );
    expect(workloadValue(cardFor("short-a"))).toBe("Workload not recorded for this Speaker");
    expect(workloadValue(cardFor("short-b"))).toBe("Workload not recorded for this Speaker");
  });

  it("no % and no digit from the load block on the page", () => {
    const numeric = {
      band: "moderate",
      reason: "measured",
      completed_hours: "47.25",
      confirmed_hours: "12.5",
      capacity_hours: "96.4",
      utilization: 0.6137,
      multiplier: "0.915",
      composite_before_load: 0.7321,
    } as unknown as MatchLoad;
    render(
      <MatchRunView
        run={run({
          shortlist: [loaded("short-a", numeric)],
          excluded: [
            {
              subject_id: "full-a",
              reason: "load_full",
              load: { ...numeric, band: "full" } as MatchLoad,
            },
          ],
        })}
      />,
    );
    const text = document.body.textContent ?? "";
    expect(text).toContain("Moderate");
    expect(text).not.toContain("%");
    for (const value of ["47.25", "12.5", "96.4", "0.6137", "61", "0.915", "0.7321", "73"]) {
      expect(text).not.toContain(value);
    }
  });
});
