/** Issue #413: a team types its 4-digit code; a browser already in the team skips it. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExerciseEntry, TEAM_CODE_HELPER } from "./ExerciseEntry";

let calls: { url: string; init: RequestInit }[] = [];

function stubFetch(answers: Record<string, { body: unknown; status?: number }>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const answer = answers[url] ?? { body: { error: { code: "test_unstubbed", message: url } }, status: 404 };
      return Promise.resolve(new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }));
    }),
  );
}

function renderEntry() {
  const router = createMemoryRouter(
    [
      { path: "/exercise", element: <ExerciseEntry /> },
      { path: "/exercise/events", element: <p>events page</p> },
    ],
    { initialEntries: ["/exercise"] },
  );
  return render(<RouterProvider router={router} />);
}

const SCOPE = { scope: "class_exercise", team_numbers: [1, 2, 3, 4, 5, 6], synthetic_data: true };
const NO_COOKIE = {
  body: { error: { code: "exercise_workspace_required", message: "Enter your team number." } },
  status: 401,
};
const TEAM_4 = { team_number: 4, dataset_label: "Autumn draft", invite_limit: 60, round_two_open: false };

beforeEach(() => {
  calls = [];
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<ExerciseEntry /> team code", () => {
  it("asks for the code in plain words and keeps only four digits", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": NO_COOKIE });
    renderEntry();
    fireEvent.click(await screen.findByRole("radio", { name: /team 4/i }));
    expect(screen.getByText(TEAM_CODE_HELPER)).toBeDefined();
    const input = screen.getByLabelText("Team code") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "04a8 29" } });
    expect(input.value).toBe("0482");
    expect(screen.getByRole("button", { name: /open this team/i }).getAttribute("aria-disabled")).toBeNull();
  });

  it("keeps the button unavailable until four digits are typed", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": NO_COOKIE });
    renderEntry();
    fireEvent.click(await screen.findByRole("radio", { name: /team 4/i }));
    fireEvent.change(screen.getByLabelText("Team code"), { target: { value: "048" } });
    const button = screen.getByRole("button", { name: /open this team/i });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button);
    expect(calls.some((call) => call.url === "/v1/exercise/workspaces")).toBe(false);
  });

  it("sends the team number and the code, keeping a leading zero", async () => {
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": NO_COOKIE,
      "/v1/exercise/workspaces": { body: TEAM_4 },
    });
    renderEntry();
    fireEvent.click(await screen.findByRole("radio", { name: /team 4/i }));
    fireEvent.change(screen.getByLabelText("Team code"), { target: { value: "0482" } });
    fireEvent.click(screen.getByRole("button", { name: /open this team/i }));
    await screen.findByText("events page");
    const entry = calls.find((call) => call.url === "/v1/exercise/workspaces");
    expect(JSON.parse(String(entry?.init.body))).toEqual({ team_number: 4, code: "0482" });
  });

  it("shows the server's sentence for a wrong code and stays on the screen", async () => {
    const wrong = "That code is not right for this team. Your instructor has it.";
    stubFetch({
      "/v1/exercise": { body: SCOPE },
      "/v1/exercise/workspaces/current": NO_COOKIE,
      "/v1/exercise/workspaces": {
        body: { error: { code: "exercise_team_code_wrong", message: wrong } },
        status: 401,
      },
    });
    renderEntry();
    fireEvent.click(await screen.findByRole("radio", { name: /team 4/i }));
    fireEvent.change(screen.getByLabelText("Team code"), { target: { value: "1111" } });
    fireEvent.click(screen.getByRole("button", { name: /open this team/i }));
    await screen.findByText(wrong);
    expect(screen.queryByText("events page")).toBeNull();
  });

  it("lets a browser already in the team back in without a code", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": { body: TEAM_4 } });
    renderEntry();
    await screen.findByText("This computer is already open as Team 4.");
    expect(screen.queryByLabelText("Team code")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /open this team/i }));
    await screen.findByText("events page");
    expect(calls.some((call) => call.url === "/v1/exercise/workspaces")).toBe(false);
  });

  it("asks for the code when that browser picks a different team", async () => {
    stubFetch({ "/v1/exercise": { body: SCOPE }, "/v1/exercise/workspaces/current": { body: TEAM_4 } });
    renderEntry();
    fireEvent.click(await screen.findByRole("radio", { name: /team 2/i }));
    await waitFor(() => expect(screen.getByLabelText("Team code")).toBeDefined());
  });
});
