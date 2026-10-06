/**
 * "Open this team's work" shows the whole team (issue #319).
 *
 * Ann's checklist of 2026-10-02, section 2: it "shows, for each team: its
 * saved settings with the four numbers, its list of names, its results for
 * each round, its way of asking, and whether it has refreshed."
 *
 * Each of those five is pinned below, plus the two honest edges: a run whose
 * saved setting has been deleted since (the names stay, and the view says so),
 * and a run stored before names were kept (the counts stay, and the view says
 * the names are not there instead of inventing them).
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  InstructorSavedSettingView,
  InvitedProfileView,
  ResultRunView,
  TeamDetailView,
} from "../../../lib/exerciseClient";
import { clockTime } from "./exerciseTime";
import { TeamDetail } from "./InstructorTeamDetail";

const LABELS = {
  same_major: "same major",
  stated_interest_overlap: "said they are interested in this topic",
  career_goal_fit: "career goal fits this event",
  past_event_topic_overlap: "went to similar events before",
};

function person(
  rank: number | null,
  profileNo: number,
  name: string,
  extra: Partial<InvitedProfileView> = {},
): InvitedProfileView {
  return {
    rank,
    profile_no: profileNo,
    display_name: name,
    major: "Accounting",
    class_year: "Senior",
    marker: "completed_card",
    reason: "said they are interested in this topic",
    ...extra,
  };
}

const BRANDON = person(1, 4, "Brandon Soto");
const AVERY = person(2, 1, "Avery Brooks", { major: "Finance", marker: "major_only" });
const CAM = person(3, 3, "Cam Ellis", { class_year: "Junior", marker: "major_plus_events" });

function setting(extra: Partial<InstructorSavedSettingView> = {}): InstructorSavedSettingView {
  return {
    event_key: "E11",
    event_name: "Northline Analytics: Behind the Business",
    round: 1,
    name: "Interest first",
    created_at: "2026-10-16T17:00:00Z",
    weights: {
      same_major: 0.1,
      stated_interest_overlap: 0.6,
      career_goal_fit: 0.2,
      past_event_topic_overlap: 0.1,
    },
    invited: [BRANDON, AVERY, CAM],
    ...extra,
  };
}

function run(extra: Partial<ResultRunView> = {}): ResultRunView {
  return {
    event_key: "E11",
    event_name: "Northline Analytics: Behind the Business",
    round: 1,
    setting_name: "Interest first",
    setting_deleted: false,
    setting_weights: {
      same_major: 0.25,
      stated_interest_overlap: 0.25,
      career_goal_fit: 0.25,
      past_event_topic_overlap: 0.25,
    },
    invited_count: 3,
    signed_up_count: 2,
    attended_count: 1,
    seats_empty: 51,
    created_at: "2026-10-16T17:30:00Z",
    invited: [BRANDON, AVERY, CAM],
    signed_up: [BRANDON, CAM],
    attended: [CAM],
    ...extra,
  };
}

function detail(extra: Partial<TeamDetailView> = {}): TeamDetailView {
  return {
    team_number: 3,
    asking_choice: null,
    refreshed_at: null,
    factor_labels: LABELS,
    saved_settings: [setting()],
    result_runs: [run()],
    ...extra,
  };
}

function view(): HTMLElement {
  return document.querySelector('[data-slot="exercise-instructor-team-detail"]') as HTMLElement;
}

/** The `<details>` whose summary starts with `heading`, inside `scope`. */
function list(scope: HTMLElement, heading: string): HTMLElement {
  const found = Array.from(scope.querySelectorAll("details")).find((block) =>
    (block.querySelector("summary")?.textContent ?? "").startsWith(heading),
  );
  expect(found, heading).toBeDefined();
  return found as HTMLElement;
}

function names(block: HTMLElement): string[] {
  return Array.from(block.querySelectorAll('[data-slot="exercise-instructor-name"] .font-semibold')).map(
    (name) => name.textContent ?? "",
  );
}

afterEach(cleanup);

describe("<TeamDetail /> saved settings", () => {
  it("shows each setting's four numbers under Ann's words, never a factor key", () => {
    render(<TeamDetail detail={detail({ result_runs: [] })} />);
    const numbers = view().querySelector(
      '[data-slot="exercise-instructor-four-numbers"]',
    ) as HTMLElement;

    const rows = Array.from(numbers.querySelectorAll("div")).map((row) => [
      row.querySelector("dt")?.textContent,
      row.querySelector("dd")?.textContent,
    ]);
    expect(rows).toEqual([
      ["same major", "0.10"],
      ["said they are interested in this topic", "0.60"],
      ["career goal fits this event", "0.20"],
      ["went to similar events before", "0.10"],
    ]);
    expect(view().textContent).not.toContain("stated_interest_overlap");
    expect(screen.getByText("Interest first")).toBeDefined();
    expect(view().textContent).toContain("Round 1 · Northline Analytics: Behind the Business");
  });

  it("shows the setting's list of names, in order, with what is on file in words", () => {
    render(<TeamDetail detail={detail({ result_runs: [] })} />);
    const its = list(view(), "Its list");

    expect(its.hasAttribute("open")).toBe(true);
    expect(its.querySelector("summary")?.textContent).toBe("Its list (3)");
    expect(its.querySelector("ol")).not.toBeNull();
    expect(names(its)).toEqual(["Brandon Soto", "Avery Brooks", "Cam Ellis"]);
    expect(its.textContent).toContain("Brandon Soto — Accounting, Senior, completed card");
    expect(its.textContent).toContain("Avery Brooks — Finance, Senior, major only");
    expect(its.textContent).toContain("major plus events attended");
    expect(its.textContent).not.toContain("major_only");
  });

  it("says so when a team has saved nothing, or a setting lists nobody", () => {
    render(<TeamDetail detail={detail({ saved_settings: [], result_runs: [] })} />);
    expect(view().textContent).toContain("No saved settings yet.");
    expect(view().textContent).toContain("No results run yet.");
    cleanup();

    render(
      <TeamDetail detail={detail({ saved_settings: [setting({ invited: [] })], result_runs: [] })} />,
    );
    expect(list(view(), "Its list").textContent).toContain("Nobody on this list.");
  });
});

describe("<TeamDetail /> results for each event", () => {
  it("names who was invited, who signed up and who attended, with the counts", () => {
    render(<TeamDetail detail={detail({ saved_settings: [] })} />);

    expect(view().textContent).toContain("Round 1 · Northline Analytics: Behind the Business");
    expect(view().textContent).toContain("Built from the setting “Interest first”.");
    expect(view().textContent).toContain(
      "Invited 3, signed up 2, attended 1. 51 seats are still open.",
    );
    expect(view().textContent).not.toContain("seats empty");
    expect(names(list(view(), "Invited"))).toEqual(["Brandon Soto", "Avery Brooks", "Cam Ellis"]);
    expect(names(list(view(), "Signed up"))).toEqual(["Brandon Soto", "Cam Ellis"]);
    expect(names(list(view(), "Attended"))).toEqual(["Cam Ellis"]);
    expect(list(view(), "Signed up").querySelector("summary")?.textContent).toBe("Signed up (2)");
  });

  it("shows the four numbers the run used, which need not be the setting's now", () => {
    render(<TeamDetail detail={detail()} />);
    const [fromSetting, fromRun] = Array.from(
      view().querySelectorAll('[data-slot="exercise-instructor-four-numbers"]'),
    );

    expect(fromSetting.textContent).toContain("0.60");
    expect(fromRun.textContent).not.toContain("0.60");
    expect(within(fromRun as HTMLElement).getAllByText("0.25")).toHaveLength(4);
  });

  it("keeps a run's names and says so when its setting was deleted since", () => {
    render(
      <TeamDetail
        detail={detail({ saved_settings: [], result_runs: [run({ setting_deleted: true })] })}
      />,
    );

    expect(view().textContent).toContain(
      "Built from the setting “Interest first”. The team has deleted that setting since; this run is unchanged.",
    );
    expect(names(list(view(), "Invited"))).toEqual(["Brandon Soto", "Avery Brooks", "Cam Ellis"]);
  });

  it("shows counts and no invented names for a run stored before names were kept", () => {
    const unranked = [BRANDON, AVERY].map((entry) => ({
      ...entry,
      rank: null,
      marker: null,
      reason: null,
    }));
    render(
      <TeamDetail
        detail={detail({
          saved_settings: [],
          result_runs: [
            run({ invited: unranked, signed_up: [], attended: [], setting_weights: null }),
            run({ event_key: "E12", round: 2, invited: [], signed_up: [], attended: [] }),
          ],
        })}
      />,
    );
    const [backfilled, older] = Array.from(view().querySelectorAll("article")) as HTMLElement[];

    // Names without a rank are a plain list: no order is claimed for them.
    expect(list(backfilled, "Invited").querySelector("ol")).toBeNull();
    expect(names(list(backfilled, "Invited"))).toEqual(["Brandon Soto", "Avery Brooks"]);
    expect(list(backfilled, "Invited").textContent).toContain("Brandon Soto — Accounting, Senior");
    expect(list(backfilled, "Signed up").textContent).toContain("Names were not kept for this run.");
    expect(backfilled.querySelector('[data-slot="exercise-instructor-four-numbers"]')).toBeNull();
    expect(list(older, "Invited").querySelector("summary")?.textContent).toBe("Invited (3)");
    expect(list(older, "Invited").textContent).toContain("Names were not kept for this run.");
    expect(view().textContent).not.toMatch(/Profile \d/);
  });

  it("says “Nobody.” for a list the run's count says is empty", () => {
    render(
      <TeamDetail
        detail={detail({
          saved_settings: [],
          result_runs: [run({ attended_count: 0, attended: [] })],
        })}
      />,
    );

    expect(list(view(), "Attended").textContent).toContain("Nobody.");
    expect(list(view(), "Attended").textContent).not.toContain("Names were not kept");
  });
});

describe("<TeamDetail /> way of asking and whether it has asked", () => {
  it("says a team has neither picked nor asked", () => {
    render(<TeamDetail detail={detail()} />);

    expect(within(view()).getByRole("status").textContent).toBe(
      "Has not picked a way of asking. Has not asked yet.",
    );
  });

  it("names the way of asking in Ann's words, before the team has asked", () => {
    render(<TeamDetail detail={detail({ asking_choice: "small_reward" })} />);

    expect(within(view()).getByRole("status").textContent).toBe(
      "Way of asking: A small reward. Has not asked yet.",
    );
    expect(view().textContent).not.toContain("small_reward");
  });

  it("shows the time the team asked", () => {
    const at = "2026-10-16T17:42:00Z";
    render(<TeamDetail detail={detail({ asking_choice: "required", refreshed_at: at })} />);

    expect(within(view()).getByRole("status").textContent).toBe(
      `Way of asking: Required. Asked at ${clockTime(at)}.`,
    );
  });
});
