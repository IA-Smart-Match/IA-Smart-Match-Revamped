/**
 * The passcode field's show/hide toggle (DESIGN.md §6.24).
 *
 * A toggle button with `aria-pressed` switches the field between password and
 * text. It never submits the form, and the passcode never appears anywhere
 * but the field's own value: not in text, not in another attribute, not in
 * the console.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseInstructor } from "./ExerciseInstructor";

const SECRET = "open-sesame-4821";
let calls: string[] = [];

function stub(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(url);
      return Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: "exercise_instructor_session_required",
              message: "Enter the instructor passcode to open this page.",
            },
          }),
          { status: 401 },
        ),
      );
    }),
  );
}

function renderPage(): void {
  const router = createMemoryRouter(
    [{ path: "/exercise/instructor", element: <ExerciseInstructor /> }],
    { initialEntries: ["/exercise/instructor"] },
  );
  render(<RouterProvider router={router} />);
}

afterEach(() => {
  cleanup();
  calls = [];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the passcode show/hide toggle", () => {
  it("switches the field between hidden and shown, with aria-pressed", async () => {
    stub();
    renderPage();
    const field = (await screen.findByLabelText("Passcode")) as HTMLInputElement;
    expect(field.type).toBe("password");

    const show = screen.getByRole("button", { name: "Show what is typed" });
    expect(show.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(show);

    const hide = screen.getByRole("button", { name: "Hide what is typed" });
    expect(hide.getAttribute("aria-pressed")).toBe("true");
    expect(field.type).toBe("text");

    fireEvent.click(hide);
    expect(field.type).toBe("password");
    expect(
      screen.getByRole("button", { name: "Show what is typed" }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("does not submit the form", async () => {
    stub();
    renderPage();
    fireEvent.change(await screen.findByLabelText("Passcode"), { target: { value: SECRET } });
    const before = calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Show what is typed" }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(calls.slice(before).some((url) => url.includes("/login"))).toBe(false);
  });

  it("never puts the passcode anywhere but the field's value, or in the console", async () => {
    stub();
    const consoleCalls = (["log", "info", "warn", "error", "debug"] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation(() => undefined),
    );
    renderPage();
    const field = (await screen.findByLabelText("Passcode")) as HTMLInputElement;
    fireEvent.change(field, { target: { value: SECRET } });
    fireEvent.click(screen.getByRole("button", { name: "Show what is typed" }));

    expect(field.value).toBe(SECRET);
    expect(document.body.textContent).not.toContain(SECRET);
    const elsewhere = [...document.body.querySelectorAll("*")].filter(
      (element) =>
        element !== field &&
        [...element.attributes].some((attribute) => attribute.value.includes(SECRET)),
    );
    expect(elsewhere).toEqual([]);
    for (const spy of consoleCalls) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain(SECRET);
    }
  });
});
