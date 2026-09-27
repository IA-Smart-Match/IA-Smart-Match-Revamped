/**
 * Every instructor panel returns the page to the passcode form on a 401.
 *
 * The Teams panel already did (`InstructorTeams.signout.test.tsx`). The unlock
 * panel (list and unlock), "Ask for every team" and the data files panel (list,
 * upload, invite limit, re-point) showed the server's 401 sentence but left
 * their controls on screen, every one of which would fail the same way. Now
 * each calls `onSignedOut` on `exercise_instructor_session_required`, and only
 * on that code.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseInstructor } from "./ExerciseInstructor";
import { InstructorDatasets } from "./InstructorDatasets";

interface Answer {
  readonly body: unknown;
  readonly status?: number;
}

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const WORKSPACES = "/v1/exercise/instructor/workspaces";
const DATASETS = "/v1/exercise/instructor/datasets";
const EVENTS = "/v1/exercise/instructor/events";
const REFRESH_ALL = "/v1/exercise/instructor/refresh-all";
const TEAMS_FILE = "11111111-1111-1111-1111-111111111111";

const EXPIRED: Answer = {
  body: {
    error: {
      code: "exercise_instructor_session_required",
      message: "Enter the instructor passcode to open this page.",
    },
  },
  status: 401,
};

const NO_TEAMS_YET: Answer = {
  body: { error: { code: "exercise_no_teams_yet", message: "No team has entered a number yet." } },
  status: 409,
};

const TEAM_LIST: Answer = {
  body: {
    teams: [
      {
        team_number: 1,
        dataset_id: TEAMS_FILE,
        dataset_label: "Autumn draft",
        created_at: "2026-09-21T10:00:00Z",
        saved_setting_count: 1,
        result_run_count: 1,
        asking_choice: null,
        refreshed_at: null,
      },
    ],
    active_dataset_label: "Autumn draft",
  },
};

const DATASET_LIST: Answer = {
  body: [
    {
      dataset_id: TEAMS_FILE,
      label: "Autumn draft",
      source_filename: "autumn.xlsx",
      uploaded_at: "2026-09-21T10:00:00Z",
      row_count: 300,
      event_count: 12,
      checksum: "abc",
      invite_limit: 30,
      license_line: null,
    },
  ],
};

const EVENT_LIST: Answer = {
  body: {
    dataset_id: TEAMS_FILE,
    dataset_label: "Autumn draft",
    events: [{ event_key: "round-one", name: "Round one", unlocked: false }],
  },
};

/** Each key answers from its queue in order; the last answer repeats. */
function stub(answers: Record<string, Answer[]>): void {
  const served: Record<string, number> = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const key = `${init.method ?? "GET"} ${url.split("?")[0]}`;
      const queue = answers[key];
      const index = served[key] ?? 0;
      served[key] = index + 1;
      const answer = queue?.[Math.min(index, queue.length - 1)] ?? {
        body: { error: { code: "test_unstubbed", message: key } },
        status: 404,
      };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

/** A signed-in page whose reads all succeed, with `extra` overriding any route. */
function signedIn(extra: Record<string, Answer[]> = {}): void {
  stub({
    [`GET ${WORKSPACES}`]: [TEAM_LIST],
    [`GET ${DATASETS}`]: [DATASET_LIST],
    [`GET ${EVENTS}`]: [EVENT_LIST],
    ...extra,
  });
}

function renderPage(): void {
  const router = createMemoryRouter(
    [{ path: "/exercise/instructor", element: <ExerciseInstructor /> }],
    { initialEntries: ["/exercise/instructor"] },
  );
  render(<RouterProvider router={router} />);
}

async function expectPasscodeForm(): Promise<void> {
  await screen.findByRole("button", { name: /open the instructor page/i });
  expect(screen.queryByRole("heading", { name: "Data files" })).toBeNull();
}

beforeEach(() => {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => "visible",
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete (document as { visibilityState?: unknown }).visibilityState;
});

describe("<ExerciseInstructor /> returns to the passcode form on a 401", () => {
  it("when the unlock panel's list read is refused", async () => {
    signedIn({ [`GET ${EVENTS}`]: [EXPIRED] });
    renderPage();
    await expectPasscodeForm();
  });

  it("when an unlock is refused", async () => {
    signedIn({ [`POST ${EVENTS}/round-one/unlock`]: [EXPIRED] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^open results$/i }));
    await expectPasscodeForm();
  });

  it("when Ask for every team is refused", async () => {
    signedIn({ [`POST ${REFRESH_ALL}`]: [EXPIRED] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^ask for every team$/i }));
    await expectPasscodeForm();
  });

  it("when the data files list read is refused", async () => {
    signedIn({ [`GET ${DATASETS}`]: [EXPIRED] });
    renderPage();
    await expectPasscodeForm();
  });

  it("when setting the invite limit is refused", async () => {
    signedIn({ [`PATCH ${DATASETS}/${TEAMS_FILE}`]: [EXPIRED] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /set the limit/i }));
    await expectPasscodeForm();
  });

  it("when moving every team is refused", async () => {
    signedIn({ [`POST ${DATASETS}/${TEAMS_FILE}/repoint`]: [EXPIRED] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /move every team to this file/i }));
    fireEvent.click(await screen.findByRole("button", { name: /yes, move every team here/i }));
    await expectPasscodeForm();
  });

  it("when an upload is refused", async () => {
    signedIn({ [`POST ${DATASETS}`]: [EXPIRED] });
    renderPage();
    fireEvent.change(await screen.findByLabelText(/call this file/i), {
      target: { value: "Autumn final" },
    });
    const file = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], "autumn.xlsx", {
      type: XLSX,
    });
    fireEvent.change(screen.getByLabelText(/excel workbook/i), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /upload this file/i }));
    await expectPasscodeForm();
  });

  it("but not on any other refusal", async () => {
    signedIn({ [`POST ${REFRESH_ALL}`]: [NO_TEAMS_YET] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^ask for every team$/i }));
    await screen.findByText("No team has entered a number yet.");
    expect(screen.getByRole("heading", { name: "Data files" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /open the instructor page/i })).toBeNull();
  });
});

describe("<InstructorDatasets /> signs out on an expired session", () => {
  it("when its own list read is refused with a 401", async () => {
    const onSignedOut = vi.fn();
    stub({ [`GET ${DATASETS}`]: [EXPIRED] });
    render(<InstructorDatasets onSignedOut={onSignedOut} />);
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledTimes(1));
  });

  it("not when its list read is refused for another reason", async () => {
    const onSignedOut = vi.fn();
    stub({ [`GET ${DATASETS}`]: [NO_TEAMS_YET] });
    render(<InstructorDatasets onSignedOut={onSignedOut} />);
    await screen.findByText("No team has entered a number yet.");
    expect(onSignedOut).not.toHaveBeenCalled();
  });
});
