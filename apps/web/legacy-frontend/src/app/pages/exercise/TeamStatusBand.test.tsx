/**
 * The team's status line (issue #321; Ann's revisions of 2026-10-02, §1, and
 * her checklist, §8: after a reload "the status line still shows where the
 * team is").
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseScreen } from "./ExerciseScreen";
import { TeamStatusBand, useStatusRevision } from "./TeamStatusBand";

const WORKSPACE = "/v1/exercise/workspaces/current";
const EVENTS = "/v1/exercise/workspaces/current/events";
const ASKING = "/v1/exercise/workspaces/current/asking-choice";

/** A local wall-clock time with no zone, so it reads "10:42 AM" in any zone. */
const AT = "2026-10-16T10:42:00";

function round(key: string, name: string, sequence: number, over: object = {}): object {
  return {
    event_key: key,
    name,
    topic_tags: [],
    target_majors: [],
    is_exercise_event: true,
    sequence,
    description: null,
    results_open: false,
    results_run: false,
    ...over,
  };
}

const NOT_ASKED = {
  choice: null,
  choices: ["better_recommendations", "small_reward", "required"],
  refreshed: false,
  refreshed_at: null,
  refresh_counts: null,
  first_round_results: false,
  first_round_event_name: "Northline",
};

type Answer = { body: unknown; status?: number } | "offline";

let calls: string[] = [];
let answers: Record<string, Answer> = {};

function start(): Record<string, Answer> {
  return {
    [WORKSPACE]: { body: { team_number: 3, dataset_label: "October file", invite_limit: 30 } },
    [EVENTS]: {
      body: { events: [round("northline", "Northline", 11), round("harbor", "Harbor", 12)] },
    },
    [ASKING]: { body: NOT_ASKED },
  };
}

beforeEach(() => {
  calls = [];
  answers = start();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(url);
      const answer = answers[url] ?? {
        body: { error: { code: "test_unstubbed", message: url } },
        status: 404,
      };
      if (answer === "offline") {
        return Promise.reject(new TypeError("offline"));
      }
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function band(): HTMLElement | null {
  return document.querySelector('[data-slot="exercise-team-status"]');
}

function value(key: string): string | null {
  return document.querySelector(`[data-status="${key}"]`)?.textContent ?? null;
}

function renderBand(props: { eventKey?: string; revision?: number } = {}) {
  return render(
    <MemoryRouter>
      <TeamStatusBand {...props} />
    </MemoryRouter>,
  );
}

describe("TeamStatusBand", () => {
  it("shows the team, both rounds, the way of asking and the refresh", async () => {
    renderBand();
    await screen.findByText("You are Team 3");
    expect(screen.getByText("Round 1 · Northline:")).toBeDefined();
    expect(value("round-1")).toBe("Results not used yet (not open yet)");
    expect(screen.getByText("Round 2 · Harbor:")).toBeDefined();
    expect(value("round-2")).toBe("Results not used yet (not open yet)");
    expect(value("asking")).toBe("Not chosen yet");
    expect(value("refresh")).toBe("Not done yet");
    expect(value("file")).toBe("October file");
  });

  it("is a named region, and not a live region for its own first appearance", async () => {
    renderBand();
    await screen.findByText("You are Team 3");
    expect(screen.getByRole("region", { name: "Your team's status" })).toBe(band());
    expect(band()?.getAttribute("role")).toBeNull();
    expect(document.querySelector('[data-slot="exercise-team-status-live"]')?.textContent).toBe("");
  });

  it("marks the round the page is about", async () => {
    renderBand({ eventKey: "harbor" });
    await screen.findByText("Round 2 · Harbor (this page):");
    expect(screen.getByText("Round 1 · Northline:")).toBeDefined();
  });

  it("shows where a team is after a reload: read from the server every time", async () => {
    answers[EVENTS] = {
      body: {
        events: [
          round("northline", "Northline", 11, { results_open: true, results_run: true }),
          round("harbor", "Harbor", 12, { results_open: true }),
        ],
      },
    };
    answers[ASKING] = {
      body: { ...NOT_ASKED, choice: "small_reward", refreshed: true, refreshed_at: AT },
    };
    const first = renderBand();
    await screen.findByText("You are Team 3");
    first.unmount();

    // The reload: a fresh mount, nothing carried over in the browser.
    renderBand();
    await screen.findByText("You are Team 3");
    expect(value("round-1")).toBe("Results used");
    expect(value("round-2")).toBe("Results not used yet (open now)");
    expect(value("asking")).toBe("A small reward");
    expect(value("refresh")).toBe("Done at 10:42 AM");
    expect(calls.filter((url) => url === WORKSPACE)).toHaveLength(2);
  });

  it("reads again when the page says something changed, and says the new line aloud", async () => {
    const view = renderBand({ revision: 0 });
    await screen.findByText("You are Team 3");
    answers[ASKING] = { body: { ...NOT_ASKED, choice: "required" } };

    view.rerender(
      <MemoryRouter>
        <TeamStatusBand revision={1} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(value("asking")).toBe("Required"));
    expect(
      document.querySelector('[data-slot="exercise-team-status-live"]')?.textContent,
    ).toContain("Way of asking: Required.");
  });

  it("offers the way back for a team that picked the wrong number", async () => {
    renderBand();
    const link = await screen.findByRole("link", { name: "Not your team? Pick again" });
    expect(link.getAttribute("href")).toBe("/exercise");
  });

  it("renders nothing when the read is refused: the page says why", async () => {
    answers[WORKSPACE] = {
      body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
      status: 401,
    };
    renderBand();
    await waitFor(() => expect(band()).toBeNull());
  });

  it("says so when the status cannot be read at all", async () => {
    answers[EVENTS] = "offline";
    renderBand();
    await screen.findByText(
      "Your team's status could not be read. Reload the page to read it again.",
    );
  });

  it("keeps the line it has when a later read cannot reach the server", async () => {
    const view = renderBand({ revision: 0 });
    await screen.findByText("You are Team 3");
    answers[ASKING] = "offline";
    view.rerender(
      <MemoryRouter>
        <TeamStatusBand revision={1} />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(document.querySelector('[data-slot="exercise-team-status-stale"]')).not.toBeNull(),
    );
    expect(screen.getByText("You are Team 3")).toBeDefined();
  });

  it("never reads the team number from the browser's own storage", async () => {
    answers[WORKSPACE] = {
      body: { team_number: 5, dataset_label: "October file", invite_limit: 30 },
    };
    renderBand();
    await screen.findByText("You are Team 5");
  });
});

describe("useStatusRevision", () => {
  it("reads the line again only after the page's own re-read has landed", async () => {
    let finish: () => void = () => undefined;
    const reload = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    let latest: ReturnType<typeof useStatusRevision> | null = null;
    function Probe(): null {
      latest = useStatusRevision(reload);
      return null;
    }
    render(<Probe />);
    expect(latest!.revision).toBe(0);

    let done = false;
    await act(async () => {
      void latest!.reloadWithStatus().then(() => (done = true));
      await Promise.resolve();
    });
    expect(reload).toHaveBeenCalledTimes(1);
    expect(latest!.revision).toBe(0);

    await act(async () => {
      finish();
      await Promise.resolve();
    });
    await waitFor(() => expect(done).toBe(true));
    expect(latest!.revision).toBe(1);
  });
});

describe("ExerciseScreen's status slot (§6.1)", () => {
  it("puts the status line between the header and the page's body", () => {
    render(
      <ExerciseScreen title="Results" status={<p data-testid="line">status</p>}>
        <p data-testid="body">body</p>
      </ExerciseScreen>,
    );
    const heading = screen.getByRole("heading", { level: 1 });
    const line = screen.getByTestId("line");
    const body = screen.getByTestId("body");
    expect(heading.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(line.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders no status line on a screen that passes none", () => {
    render(<ExerciseScreen title="Who should we invite?">body</ExerciseScreen>);
    expect(band()).toBeNull();
  });
});
