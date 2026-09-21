/**
 * The instructor page: the passcode, the literal instructor path, and the one
 * reset in the product.
 *
 * The instructor cookie is `Path=/v1/exercise/instructor`, narrower than the
 * workspace cookie's, so a prefix mistake here 401s every call with nothing on
 * screen to explain it. And the per-team reset must be *present* on this page,
 * because it is absent everywhere else by design (PR #186).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseInstructor } from "./ExerciseInstructor";

let calls: { url: string; init: RequestInit }[] = [];

function stub(answers: Record<string, { body: unknown; status?: number }>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const path = url.split("?")[0];
      const answer = answers[`${init.method ?? "GET"} ${path}`] ??
        answers[path] ?? {
          body: { error: { code: "test_unstubbed", message: path } },
          status: 404,
        };
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

const LOGIN = "/v1/exercise/instructor/login";
const DATASETS = "/v1/exercise/instructor/datasets";
const WORKSPACES = "/v1/exercise/instructor/workspaces";
const EVENTS = "/v1/exercise/workspaces/current/events";

const TEAM = {
  team_number: 3,
  dataset_id: "11111111-1111-1111-1111-111111111111",
  dataset_label: "Autumn draft",
  created_at: "2026-09-21T10:00:00Z",
  saved_setting_count: 2,
  result_run_count: 1,
  asking_choice: "small_reward",
  refreshed_at: null,
};

function signedInStubs(extra: Record<string, { body: unknown; status?: number }> = {}) {
  return {
    [`POST ${LOGIN}`]: { body: { signed_in: true } },
    [`GET ${DATASETS}`]: { body: [] },
    [`GET ${WORKSPACES}`]: { body: { teams: [TEAM], active_dataset_label: "Autumn draft" } },
    [EVENTS]: { body: { events: [] } },
    ...extra,
  };
}

function renderInstructor() {
  const router = createMemoryRouter([{ path: "/exercise/instructor", element: <ExerciseInstructor /> }], {
    initialEntries: ["/exercise/instructor"],
  });
  return render(<RouterProvider router={router} />);
}

async function signIn(): Promise<void> {
  fireEvent.change(screen.getByLabelText(/passcode/i), { target: { value: "open sesame" } });
  fireEvent.click(screen.getByRole("button", { name: /open the instructor page/i }));
  await waitFor(() => expect(screen.getByText("Data files")).toBeDefined());
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseInstructor />", () => {
  it("marks the screen as synthetic before anyone signs in", () => {
    stub({});
    renderInstructor();
    expect(document.querySelector('[data-slot="synthetic-data-banner"]')).not.toBeNull();
  });

  it("posts the passcode to the literal instructor path, with the header", async () => {
    stub(signedInStubs());
    renderInstructor();
    await signIn();
    const login = calls.find((call) => call.url === LOGIN);
    expect(login).toBeDefined();
    expect(login?.init.method).toBe("POST");
    expect(new Headers(login?.init.headers).get("X-Exercise-Request")).toBe("1");
    expect(LOGIN.startsWith("/api")).toBe(false);
  });

  it("shows a refused passcode in the server's own words", async () => {
    stub({
      [`POST ${LOGIN}`]: {
        body: {
          error: {
            code: "exercise_instructor_passcode_refused",
            message: "That passcode was not recognised.",
          },
        },
        status: 401,
      },
    });
    renderInstructor();
    fireEvent.change(screen.getByLabelText(/passcode/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /open the instructor page/i }));
    await waitFor(() => expect(screen.getByText("That passcode was not recognised.")).toBeDefined());
  });

  it("carries the one per-team reset, which no team screen has", async () => {
    stub(
      signedInStubs({
        [`POST /v1/exercise/instructor/workspaces/3/reset`]: { body: TEAM },
      }),
    );
    renderInstructor();
    await signIn();
    const button = await screen.findByText(/clear team 3's work/i);
    fireEvent.click(button);
    fireEvent.click(await screen.findByRole("button", { name: /yes, clear team 3/i }));
    await waitFor(() => {
      const reset = calls.find((call) => call.url.includes("/reset"));
      expect(reset?.url).toBe(
        "/v1/exercise/instructor/workspaces/3/reset?dataset_id=11111111-1111-1111-1111-111111111111",
      );
      expect(new Headers(reset?.init.headers).get("X-Exercise-Request")).toBe("1");
    });
  });

  it("asks before it clears a team, and says no other team is touched", async () => {
    stub(signedInStubs());
    renderInstructor();
    await signIn();
    fireEvent.click(await screen.findByText(/clear team 3's work/i));
    expect(screen.getByText(/no other team is touched/i)).toBeDefined();
    expect(calls.some((call) => call.url.includes("/reset"))).toBe(false);
  });

  it("does not promise the sign-out reaches other browsers", async () => {
    // Design spec §14 as shipped: a signed cookie, no server-side row, no
    // revocation before its twelve-hour expiry.
    stub(signedInStubs());
    renderInstructor();
    await signIn();
    expect(screen.getByText(/does not sign out anywhere else/i)).toBeDefined();
    expect(document.body.textContent).not.toMatch(/signed out everywhere/i);
  });

  it("says refresh-all is all-or-nothing beside the button", async () => {
    stub(signedInStubs());
    renderInstructor();
    await signIn();
    expect(screen.getByText(/if it cannot be done, no team is changed/i)).toBeDefined();
  });

  it("uploads a data file as a raw text/csv body, not multipart", async () => {
    stub(
      signedInStubs({
        [`POST ${DATASETS}`]: {
          body: {
            dataset: {
              dataset_id: "22222222-2222-2222-2222-222222222222",
              label: "Autumn final",
              source_filename: "autumn.csv",
              uploaded_at: "2026-09-21T10:00:00Z",
              row_count: 300,
              event_count: 12,
              checksum: "abc",
              invite_limit: 30,
              license_line: null,
            },
            report: {
              profile_count: 300,
              event_count: 12,
              exercise_event_count: 2,
              distinct_class_years: ["third"],
              profiles_missing_major: 0,
              profiles_missing_class_year: 0,
              profiles_without_card: 230,
              distinct_stated_interest_terms: 40,
              distinct_topic_tag_terms: 18,
              events_without_topic_tags: 0,
              discarded_list_entries: 0,
              major_only: 230,
              major_plus_events: 0,
              completed_card: 70,
            },
            notice: "The teams are still working in the data file they entered on.",
          },
        },
      }),
    );
    renderInstructor();
    await signIn();

    fireEvent.change(screen.getByLabelText(/call this file/i), {
      target: { value: "Autumn final" },
    });
    const file = new File(["profile_no\n1\n"], "autumn.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/spreadsheet file/i), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /upload this file/i }));

    await waitFor(() => {
      const upload = calls.find((call) => call.url.startsWith(DATASETS + "?"));
      expect(upload).toBeDefined();
      expect(new Headers(upload?.init.headers).get("Content-Type")).toBe("text/csv");
      expect(upload?.init.body).toBe("profile_no\n1\n");
      expect(upload?.url).toContain("label=Autumn+final");
      expect(upload?.url).toContain("source_filename=autumn.csv");
    });
    // The server's own sentence about what an upload did not do.
    await waitFor(() =>
      expect(
        screen.getByText("The teams are still working in the data file they entered on."),
      ).toBeDefined(),
    );
  });
});
